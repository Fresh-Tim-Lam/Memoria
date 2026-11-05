#!/usr/bin/env python
"""从人工撰写的标注 spec 生成 pilot 语料包（KP/边/负例/query），并做构建期自检。

为什么先生成再校验：
- 手工写 JSONL 的字符 offset 极易错一位；本脚本用**唯一**的 block/sentence 坐标算法
  （`build_source_snapshot.collect`）把 `block + sentence range` 解析成 UTF-8 字符 span，
  并写入 evidence 引文的 sha256；
- `scripts/corpus/validate_pilot.py` 再从磁盘独立校验一遍（不复用本脚本的生成逻辑），
  构成“生成/校验”双实现，避免同源自证。

spec（唯一人工创作输入）：`artifacts/corpus/pilot/annotations/pilot-spec.json`
  - kp[]：id/block/sentences/name/name_zh/description/concept_type/granularity/section_key
  - edges[]：id/type/source/target/confidence/rationale/assertion(block+sentences)/optional contain_kind
  - negatives[]：id/source/target/proposed_type/reason/kind
  - queries[]：id/query_type/text/expected_kp_ids/control/rationale/difficulty/split

用法：
  python scripts/corpus/make_annotations.py check-source
  python scripts/corpus/make_annotations.py dump-block --block-index 5
  python scripts/corpus/make_annotations.py build
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_source_snapshot import collect  # noqa: E402

SCHEMA_SPEC = "corpus-pilot-annotation-spec/v1"
SCHEMA_KP = "corpus-pilot-kp/v1"
SCHEMA_EDGE = "corpus-pilot-semantic-edge/v1"
SCHEMA_NEG = "corpus-pilot-negative-edge/v1"
SCHEMA_QUERY = "corpus-pilot-queries/v1"
MANUAL_VERSION = "v1.0"
ANNOTATOR = "corpus-pilot-builder (single annotator, LLM-assisted)"
STATUS = "single_annotator_draft"
CHAPTER_FILE = "artifacts/corpus/pilot/source/chapter.txt"

S0_TYPES = {"contain", "reference", "extend"}
CONTAIN_KINDS = {"structural", "semantic"}
CONFIDENCE = {"high", "medium", "low"}
KP_TYPES = {"concept", "term", "formula", "mechanism", "procedure", "example"}
GRANULARITY = {"concept_explanation", "proposition"}
QUERY_TYPES = {"keyword", "vector", "hybrid", "graph"}

ABBREVIATIONS = {
    "u.s.", "u.k.", "u.s.a.", "e.g.", "i.e.", "vs.", "etc.", "inc.", "corp.",
    "co.", "ltd.", "mr.", "mrs.", "ms.", "dr.", "prof.", "st.", "jr.", "sr.",
    "no.", "fig.", "exhibit", "approx.", "dept.", "univ.", "assn.", "bros.",
}
_ABBREV_STEMS = {a.rstrip(".") for a in ABBREVIATIONS}


def split_sentences(text: str) -> list[tuple[int, int]]:
    """确定性地切句；返回块内 [start,end) 相对偏移列表。

    规则：句末标点 `.?!` 后接空白 + 下一句以大写/引号/数字/美元/括号开头；
    排除常见缩写（U.S./Inc./e.g.）、单字母缩写；不做语言模型推断。
    """
    spans: list[tuple[int, int]] = []
    start = 0
    for m in re.finditer(r"[.!?](?=\s|$)", text):
        end = m.end()
        j = end
        while j < len(text) and text[j].isspace():
            j += 1
        if j >= len(text):
            continue
        nxt = text[j]
        if not (nxt.isupper() or nxt in "\"“'$0123456789("):
            continue
        prev = re.search(r"([A-Za-z][A-Za-z.]*)$", text[: end - 1])
        token = prev.group(1).lower() if prev else ""
        if token.rstrip(".") in _ABBREV_STEMS:
            continue
        if len(token) == 1 and token.isalpha() and text[end - 2:end - 1].isupper():
            continue  # 人名缩写 A. Smith
        spans.append((start, end))
        start = j
    if start < len(text):
        spans.append((start, len(text)))
    if not spans:
        spans = [(0, len(text))]
    return spans


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SourceIndex:
    def __init__(self, pages_path: Path) -> None:
        self.collected = collect(pages_path)
        self.text: str = self.collected["chapter_text"]
        self.blocks: list[dict] = self.collected["blocks"]
        self.sections: list[dict] = self.collected["sections"]
        self.section_by_page = {s["page_id"]: s for s in self.sections}
        for block in self.blocks:
            rel = self.text[block["start"]:block["end"]]
            block["text"] = rel
            block["sentences"] = split_sentences(rel)

    def block(self, index: int) -> dict:
        if not (0 <= index < len(self.blocks)):
            raise ValueError(f"block index 越界: {index}")
        return self.blocks[index]

    def span_of(self, block_index: int, sentences: str) -> tuple[int, int]:
        """`sentences` 形如 "all" / "2" / "2-4"；返回 chapter.txt 绝对 span。"""
        block = self.block(block_index)
        segs = block["sentences"]
        if sentences == "all":
            first, last = 1, len(segs)
        else:
            m = re.fullmatch(r"(\d+)(?:-(\d+))?", str(sentences))
            if not m:
                raise ValueError(f"非法 sentences 表达式: {sentences!r}")
            first = int(m.group(1))
            last = int(m.group(2) or first)
        if not (1 <= first <= last <= len(segs)):
            raise ValueError(f"block {block_index} 只有 {len(segs)} 句，收到 {sentences!r}")
        return block["start"] + segs[first - 1][0], block["start"] + segs[last - 1][1]

    def section_of_block(self, block_index: int) -> dict:
        block = self.block(block_index)
        for sec in self.sections:
            if sec["start"] <= block["start"] and block["end"] <= sec["end"]:
                return sec
        raise ValueError(f"block {block_index} 不在任何 section 内")

    def resolve_span(self, item: dict) -> tuple[int, int]:
        """支持单 block（block+sentences）或跨相邻 block（blocks=[a,b] + sentences_start/end）。"""
        if "block" in item:
            return self.span_of(int(item["block"]), item.get("sentences", "all"))
        blocks = item.get("blocks")
        if not isinstance(blocks, list) or len(blocks) != 2:
            raise ValueError(f"spec 项必须给 block 或 blocks=[start,end]: {item!r}")
        first = self.span_of(int(blocks[0]), item.get("sentences_start", "all"))[0]
        last = self.span_of(int(blocks[1]), item.get("sentences_end", "all"))[1]
        if last <= first:
            raise ValueError(f"非法跨 block span: {item!r}")
        return first, last


def _evidence(span: tuple[int, int], text: str) -> dict:
    start, end = span
    quote = text[start:end]
    return {"file": CHAPTER_FILE, "start": start, "end": end,
            "quote": quote, "quote_sha256": _sha(quote)}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def build(source_dir: Path, spec_path: Path, out_dir: Path) -> dict:
    spec = _load_json(spec_path)
    if spec.get("schema") != SCHEMA_SPEC:
        raise ValueError(f"spec schema 不符: {spec.get('schema')!r}")
    index = SourceIndex(source_dir / "pages.json")
    text = index.text

    meta = _load_json(source_dir / "snapshot-meta.json")
    if meta.get("chapter_sha256") != _sha(text):
        raise ValueError("chapter.txt 与 snapshot-meta 的 sha 不一致（先重建快照）")
    lic = _load_json(source_dir / "license-evidence.json")
    if lic["book"].get("license_tier") != "A":
        raise ValueError("pilot 发布包只允许 Tier A 源")

    out_dir.mkdir(parents=True, exist_ok=True)

    # ---------------- KP ----------------
    kps: list[dict] = []
    seen_ids: set[str] = set()
    covered: list[tuple[int, int]] = []
    for item in spec["kp"]:
        kp_id = item["id"]
        if kp_id in seen_ids:
            raise ValueError(f"重复 KP id: {kp_id}")
        seen_ids.add(kp_id)
        block_index = item.get("block", item.get("blocks"))
        start, end = index.resolve_span(item)
        sec = index.section_of_block(int(block_index) if isinstance(block_index, int) else int(item["blocks"][0]))
        if not (sec["start"] <= start and end <= sec["end"]):
            raise ValueError(f"{kp_id} span 跨 section")
        for a, b in covered:
            if start < b and a < end:
                raise ValueError(f"{kp_id} 与其他 KP span 重叠: {(start, end)} vs {(a, b)}")
        covered.append((start, end))
        name = item["name"].strip()
        desc = item["description"].strip()
        if not name or len(name) > 120:
            raise ValueError(f"{kp_id} name 为空或 >120 字符")
        if not desc or len(desc) > 500:
            raise ValueError(f"{kp_id} description 为空或 >500 字符")
        granularity = item.get("granularity", "concept_explanation")
        concept_type = item.get("concept_type", "concept")
        if concept_type not in KP_TYPES:
            raise ValueError(f"{kp_id} concept_type 非法: {concept_type}")
        if granularity not in GRANULARITY:
            raise ValueError(f"{kp_id} granularity 非法: {granularity}")
        anchor = {
            "page_id": sec["page_id"],
            "url": sec["url"],
            "block": item.get("block"),
            "blocks": item.get("blocks"),
            "sentences": item.get("sentences", "all"),
            "sentences_start": item.get("sentences_start"),
            "sentences_end": item.get("sentences_end"),
        }
        kps.append({
            "id": kp_id,
            "file": CHAPTER_FILE,
            "spans": [{"start": start, "end": end}],
            "name": name,
            "name_zh": item.get("name_zh", "").strip(),
            "description": desc,
            "section_key": sec["page_id"],
            "section_num": sec.get("section_num"),
            "concept_type": concept_type,
            "granularity": granularity,
            "evidence": [_evidence((start, end), text)],
            "anchor": anchor,
            "status": STATUS,
            "annotator": ANNOTATOR,
            "annotation_method": "single annotator draft; IAA not run (needs independent second annotator)",
            "manual_version": MANUAL_VERSION,
        })
    kps.sort(key=lambda x: x["id"])
    if len(kps) != 50:
        raise ValueError(f"pilot 需要 50 KP，spec 给了 {len(kps)}")

    # ---------------- 语义边 ----------------
    kp_by_id = {k["id"]: k for k in kps}
    edges: list[dict] = []
    seen_edges: set[tuple] = set()
    for item in spec["edges"]:
        edge_id = item["id"]
        source_id, target_id = item["source"], item["target"]
        if source_id not in kp_by_id or target_id not in kp_by_id:
            raise ValueError(f"{edge_id} 端点不存在: {source_id}/{target_id}")
        if source_id == target_id:
            raise ValueError(f"{edge_id} 自环")
        etype = item["type"]
        if etype not in S0_TYPES:
            raise ValueError(f"{edge_id} 类型不在 S0: {etype}")
        contain_kind = item.get("contain_kind")
        if etype == "contain":
            if contain_kind not in CONTAIN_KINDS:
                raise ValueError(f"{edge_id} contain 必须给 contain_kind∈{CONTAIN_KINDS}")
        elif contain_kind is not None:
            raise ValueError(f"{edge_id} 非 contain 不得带 contain_kind")
        label = item.get("label", "semantic")
        if label != "semantic":
            raise ValueError(f"{edge_id} 语义边 label 必须为 semantic")
        direction = item.get("direction", "source->target")
        if direction not in ("source->target", "both"):
            raise ValueError(f"{edge_id} direction 非法: {direction}")
        confidence = item.get("confidence")
        if confidence not in CONFIDENCE:
            raise ValueError(f"{edge_id} confidence 非法: {confidence}")
        rationale = item.get("rationale", "").strip()
        if not rationale:
            raise ValueError(f"{edge_id} 缺 rationale")
        key = (source_id, target_id, etype, direction)
        if key in seen_edges:
            raise ValueError(f"{edge_id} 重复 tuple: {key}")
        seen_edges.add(key)
        assertion = item.get("assertion")
        if not assertion:
            raise ValueError(f"{edge_id} 缺 assertion 证据")
        a_start, a_end = index.resolve_span(assertion)
        assert_span = _evidence((a_start, a_end), text)
        src = kp_by_id[source_id]
        tgt = kp_by_id[target_id]
        e = {
            "id": edge_id,
            "type": etype,
            "label": label,
            "source": source_id,
            "target": target_id,
            "direction": direction,
            "confidence": confidence,
            "rationale": rationale,
            "e_sem": True,
            "evidence": {
                "source_span": _span_ref(src["spans"][0], text),
                "target_span": _span_ref(tgt["spans"][0], text),
                "assertion_span": assert_span,
            },
            "status": STATUS,
            "annotator": ANNOTATOR,
            "annotation_method": "single annotator draft; IAA not run (needs independent second annotator)",
            "manual_version": MANUAL_VERSION,
        }
        if etype == "contain":
            e["contain_kind"] = contain_kind
        edges.append(e)
    edges.sort(key=lambda x: x["id"])
    if len(edges) != 30:
        raise ValueError(f"pilot 需要 30 条语义边，spec 给了 {len(edges)}")

    # ---------------- 负例 ----------------
    negatives: list[dict] = []
    for item in spec.get("negatives", []):
        source_id, target_id = item["source"], item["target"]
        if source_id not in kp_by_id or target_id not in kp_by_id:
            raise ValueError(f"{item['id']} 端点不存在")
        negatives.append({
            "id": item["id"],
            "candidate_source": source_id,
            "candidate_target": target_id,
            "proposed_type": item.get("proposed_type"),
            "contain_kind": item.get("contain_kind"),
            "negative_kind": item["kind"],
            "reason": item["reason"].strip(),
            "must_not_appear_in": "edges.single.jsonl",
            "status": STATUS,
            "annotator": ANNOTATOR,
            "manual_version": MANUAL_VERSION,
        })
    if len(negatives) < 10:
        raise ValueError(f"负例应 >=10 条，spec 给了 {len(negatives)}")

    # ---------------- query ----------------
    queries: list[dict] = []
    qids: set[str] = set()
    for item in spec["queries"]:
        qid = item["id"]
        if qid in qids:
            raise ValueError(f"重复 query id: {qid}")
        qids.add(qid)
        qtype = item["query_type"]
        if qtype not in QUERY_TYPES:
            raise ValueError(f"{qid} query_type 非法: {qtype}")
        expected = item.get("expected_kp_ids", [])
        if not expected:
            raise ValueError(f"{qid} 缺 expected_kp_ids")
        for kid in expected:
            if kid not in kp_by_id:
                raise ValueError(f"{qid} expected 引用了不存在的 KP: {kid}")
        expected_edges = item.get("expected_edge_ids", [])
        edge_ids = {e["id"] for e in edges}
        for eid in expected_edges:
            if eid not in edge_ids:
                raise ValueError(f"{qid} expected_edge_ids 引用了不存在的边: {eid}")
        control = bool(item.get("control", False))
        if control and qtype == "graph":
            raise ValueError(f"{qid} no-semantic control 不应是 graph 型")
        queries.append({
            "id": qid,
            "query_type": qtype,
            "query": item["query"],
            "expected_kp_ids": expected,
            "expected_edge_ids": expected_edges,
            "control": control,
            "control_kind": item.get("control_kind") if control else None,
            "rationale": item["rationale"].strip(),
            "difficulty": item.get("difficulty", "medium"),
            "split": item.get("split", "dev"),
            "status": STATUS,
            "manual_version": MANUAL_VERSION,
        })
    queries.sort(key=lambda x: x["id"])
    if len(queries) != 20:
        raise ValueError(f"pilot 需要 20 query，spec 给了 {len(queries)}")

    # ---------------- 写盘（确定性：固定字段顺序 + sort_keys + LF） ----------------
    def dump_jsonl(path: Path, rows: list[dict]) -> None:
        path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
                        encoding="utf-8", newline="\n")

    dump_jsonl(out_dir / "kps.single.jsonl", kps)
    dump_jsonl(out_dir / "edges.single.jsonl", edges)
    dump_jsonl(out_dir / "edges.negative.single.jsonl", negatives)
    (out_dir / "queries.json").write_text(
        json.dumps({
            "schema": SCHEMA_QUERY,
            "source_edition": meta["chapter_sha256"],
            "kp_file": "artifacts/corpus/pilot/annotations/kps.single.jsonl",
            "edge_file": "artifacts/corpus/pilot/annotations/edges.single.jsonl",
            "status": STATUS,
            "manual_version": MANUAL_VERSION,
            "dev_test_note": ("pilot 仅 1 章，dev/test 无法按章隔离；按 query id 预分"
                              " dev/test，仅用于流程演练，不作为统计推断（主集按章隔离）。"),
            "queries": queries,
        }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

    manifest = {
        "schema": "corpus-pilot-annotations-manifest/v1",
        "source_chapter_sha256": meta["chapter_sha256"],
        "spec_sha256": _sha(spec_path.read_text(encoding="utf-8")),
        "counts": {"kp": len(kps), "semantic_edges": len(edges),
                   "negative_edges": len(negatives), "queries": len(queries)},
        "files": {
            "kps": "artifacts/corpus/pilot/annotations/kps.single.jsonl",
            "edges": "artifacts/corpus/pilot/annotations/edges.single.jsonl",
            "negative_edges": "artifacts/corpus/pilot/annotations/edges.negative.single.jsonl",
            "queries": "docs/design/corpus-seminar/pilot/queries.json",
        },
        "file_sha256": {
            "kps.single.jsonl": hashlib.sha256((out_dir / "kps.single.jsonl").read_bytes()).hexdigest(),
            "edges.single.jsonl": hashlib.sha256((out_dir / "edges.single.jsonl").read_bytes()).hexdigest(),
            "edges.negative.single.jsonl": hashlib.sha256(
                (out_dir / "edges.negative.single.jsonl").read_bytes()).hexdigest(),
            "queries.json": hashlib.sha256((out_dir / "queries.json").read_bytes()).hexdigest(),
        },
        "status": STATUS,
        "manual_version": MANUAL_VERSION,
    }
    manifest["edition"] = edition_of(manifest["source_chapter_sha256"],
                                     manifest["file_sha256"], MANUAL_VERSION)
    manifest["edition_formula"] = ("sha256('corpus-pilot-edition/v1' + chapter_sha + "
                                   "kps/edges/negative/queries sha + manual_version)")
    (out_dir / "annotations-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    return manifest


def _span_ref(span: dict, text: str) -> dict:
    start, end = span["start"], span["end"]
    quote = text[start:end]
    return {"file": CHAPTER_FILE, "start": start, "end": end,
            "quote": quote, "quote_sha256": _sha(quote)}


def edition_of(chapter_sha: str, file_sha: dict, manual_version: str) -> str:
    """C7 edition = sha256(文件内容 + 标注 JSONL + 手册版本)。"""
    names = ["kps.single.jsonl", "edges.single.jsonl", "edges.negative.single.jsonl", "queries.json"]
    payload = "\n".join(["corpus-pilot-edition/v1", chapter_sha]
                        + [file_sha[n] for n in names] + [manual_version])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dump_block(source_dir: Path, block_index: int) -> dict:
    index = SourceIndex(source_dir / "pages.json")
    block = index.block(block_index)
    sec = index.section_of_block(block_index)
    segs = block["sentences"]
    return {
        "block_index": block_index,
        "page_id": sec["page_id"],
        "section_num": sec.get("section_num"),
        "type": block["type"],
        "absolute_start": block["start"],
        "absolute_end": block["end"],
        "text": block["text"],
        "sentence_count": len(segs),
        "sentences": [
            {"n": i + 1, "start": block["start"] + s, "end": block["start"] + e,
             "text": block["text"][s:e]}
            for i, (s, e) in enumerate(segs)
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build corpus pilot annotation package from spec")
    ap.add_argument("command", choices=["check-source", "dump-block", "build"])
    ap.add_argument("--source", default="artifacts/corpus/pilot/source")
    ap.add_argument("--spec", default="artifacts/corpus/pilot/annotations/pilot-spec.json")
    ap.add_argument("--out", default="artifacts/corpus/pilot/annotations")
    ap.add_argument("--queries-out", default="docs/design/corpus-seminar/pilot/queries.json")
    ap.add_argument("--block-index", type=int, default=0)
    args = ap.parse_args(argv)
    try:
        source_dir = Path(args.source)
        if args.command == "check-source":
            index = SourceIndex(source_dir / "pages.json")
            meta = _load_json(source_dir / "snapshot-meta.json")
            actual = _sha(index.text)
            print(json.dumps({"ok": meta["chapter_sha256"] == actual,
                              "chapter_sha256": actual,
                              "chapter_chars": len(index.text),
                              "blocks": len(index.blocks)}, ensure_ascii=False, indent=2))
            return 0 if meta["chapter_sha256"] == actual else 1
        if args.command == "dump-block":
            print(json.dumps(dump_block(source_dir, args.block_index),
                             ensure_ascii=False, indent=2))
            return 0
        manifest = build(source_dir, Path(args.spec), Path(args.out))
        # queries 同时写到 docs 交付路径（若目录存在/可建）
        queries_src = Path(args.out) / "queries.json"
        queries_dst = Path(args.queries_out)
        if queries_src.exists():
            queries_dst.parent.mkdir(parents=True, exist_ok=True)
            queries_dst.write_bytes(queries_src.read_bytes())
            manifest["files"]["queries"] = str(queries_dst).replace("\\", "/")
        print(json.dumps({"ok": True, **manifest["counts"],
                          "manifest": "artifacts/corpus/pilot/annotations/annotations-manifest.json"},
                         ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001 —— 失败必须可见
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)},
                         ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
