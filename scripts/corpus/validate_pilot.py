#!/usr/bin/env python
"""pilot 语料包独立校验（schema / span 越界 / 证据 / 许可 / Tier / 数量 / 2× 可复现）。

设计原则（C0 C2/C4/C6/C7/C8/C10 + R-C0-1/2/3）：
- **独立实现**：不复用 `make_annotations.py` 的生成逻辑；span 只按 `sections.json`
  与 `chapter.txt` 重新核对，evidence 引文按 sha256 重新计算；
- **失败可见**：任何一项失败都返回非 0 并打印结构化错误，不静默跳过；
- **2× 可复现**：从 `pages.json` 重新抽取快照、从 `pilot-spec.json` 重新生成标注，
  两次产物与仓库内文件逐字节一致才通过；
- 只读：不修改任何仓库文件（临时目录除外）。

用法：
  python scripts/corpus/validate_pilot.py
  python scripts/corpus/validate_pilot.py --json-out artifacts/agent/verify/corpus/pilot/validate.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(".").resolve()

SOURCE = "artifacts/corpus/pilot/source"
ANNO = "artifacts/corpus/pilot/annotations"
DOCS = "docs/design/corpus-seminar/pilot"
CHAPTER = f"{SOURCE}/chapter.txt"
CHAPTER_REL = "artifacts/corpus/pilot/source/chapter.txt"

S0_TYPES = {"contain", "reference", "extend"}
CONTAIN_KINDS = {"structural", "semantic"}
CONFIDENCE = {"high", "medium", "low"}
KP_TYPES = {"concept", "term", "formula", "mechanism", "procedure", "example"}
STATUS = "single_annotator_draft"
QUERY_TYPES = {"keyword", "vector", "hybrid", "graph"}
TIER_A_SPDX = {"CC-BY-4.0", "CC-BY-SA-4.0", "CC0-1.0", "PD"}


class Checker:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.checks: list[dict] = []

    def check(self, cid: str, ok: bool, detail: str = "") -> bool:
        self.checks.append({"id": cid, "ok": bool(ok), "detail": detail})
        return bool(ok)

    @property
    def ok(self) -> bool:
        return all(c["ok"] for c in self.checks)

    def failures(self) -> list[str]:
        return [c["id"] for c in self.checks if not c["ok"]]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} 第 {i} 行不是合法 JSON: {exc}") from exc
    return rows


def canonical_sha(path: Path) -> str:
    data = path.read_bytes()
    if b"\r" in data:
        raise ValueError(f"{path} 含 CR")
    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"{path} 含 UTF-8 BOM")
    return sha256_bytes(data)


def sections_of_source(root: Path) -> tuple[dict, list[dict], str]:
    src = root / SOURCE
    meta = read_json(src / "snapshot-meta.json")
    secs_doc = read_json(src / "sections.json")
    chapter = (root / CHAPTER_REL).read_text(encoding="utf-8")
    return meta, secs_doc["sections"], chapter


def section_for_span(sections: list[dict], start: int, end: int) -> dict | None:
    for sec in sections:
        if sec["start"] <= start and end <= sec["end"]:
            return sec
    return None


def check_source(c: Checker) -> tuple[dict, list[dict], str]:
    src = c.root / SOURCE
    meta = read_json(src / "snapshot-meta.json")
    secs_doc = read_json(src / "sections.json")
    sections = secs_doc["sections"]
    chapter = (c.root / CHAPTER_REL).read_text(encoding="utf-8")

    c.check("source.chapter_hash", sha256_bytes(chapter.encode("utf-8")) == meta["chapter_sha256"],
            "chapter.txt sha256 与 snapshot-meta 一致")
    c.check("source.chapter_no_crlf_no_bom",
            "\r" not in chapter and not (c.root / CHAPTER_REL).read_bytes().startswith(b"\xef\xbb\xbf"),
            "chapter.txt 为 LF/UTF-8 无 BOM")
    c.check("source.chapter_chars", len(chapter) == meta["chapter_chars"],
            f"字符数 {len(chapter)} == {meta['chapter_chars']}")
    c.check("source.sections_hash", sha256_file(src / "sections.json") == meta["sections_sha256"],
            "sections.json sha256 与 snapshot-meta 一致")
    c.check("source.sections_cover_chapter",
            bool(sections) and sections[0]["start"] == 0 and sections[-1]["end"] == len(chapter),
            "sections 首尾覆盖整个 chapter.txt")
    gaps = [(a["end"], b["start"]) for a, b in zip(sections, sections[1:]) if a["end"] != b["start"]]
    c.check("source.sections_contiguous", not gaps, f"section 区间连续（gap 数={len(gaps)}）")

    pages = read_json(src / "pages.json")
    c.check("source.pages_schema", pages.get("schema") == "corpus-pilot-source-pages/v1",
            "pages.json schema")
    c.check("source.page_count", len(pages["pages"]) == 11, f"正文页数 {len(pages['pages'])} == 11")
    book = pages["book"]
    c.check("source.tier_a", book.get("license_tier") == "A", "来源 Tier=A 可发布")
    c.check("source.spdx", book.get("spdx") in TIER_A_SPDX, f"SPDX={book.get('spdx')} ∈ Tier A")
    c.check("source.license", book.get("license") in {"CC BY 4.0", "CC BY-SA 4.0", "CC0", "PD"},
            f"license={book.get('license')}")

    fetch = read_json(src / "fetch-log.json")
    records = fetch.get("records", [])
    c.check("source.fetch_records", len(records) == 15, f"抓取记录 {len(records)} == 15")
    for rec in records:
        rel = rec["local_path"]
        path = c.root / rel
        if not path.exists():
            c.check(f"source.exists:{rel}", False, "文件缺失")
            continue
        c.check(f"source.sha:{rel}", sha256_file(path) == rec["sha256"], "raw sha256 一致")
        c.check(f"source.http200:{rel}", rec.get("http_status") == 200,
                f"HTTP {rec.get('http_status')}")
        c.check(f"source.title:{rel}", bool((rec.get("title") or "").strip()), "页面标题非空")
        c.check(f"source.verified_at:{rel}", bool((rec.get("verified_at") or "").strip()),
                "记录 verified_at")

    lic = read_json(src / "license-evidence.json")
    ev = lic.get("evidence", [])
    c.check("source.license_evidence_count", len(ev) == 4, f"许可证据 {len(ev)} == 4")
    for item in ev:
        c.check(f"source.license_evidence_200:{item['name']}", item.get("http_status") == 200,
                "许可证据 HTTP 200")
        c.check(f"source.license_evidence_title:{item['name']}",
                bool((item.get("title") or "").strip()), "许可证据标题非空")
        c.check(f"source.license_evidence_sha:{item['name']}",
                sha256_file(c.root / item["local_path"]) == item["sha256"], "许可证据 sha256 一致")
    c.check("source.license_evidence_types",
            {"book_license_statement", "spdx_license_definition"} <=
            {i["evidence_kind"] for i in ev}, "含图书许可声明 + SPDX 定义两类证据")

    # 许可文档存在且写明 Tier A / CC BY
    lic_md = c.root / DOCS / "SOURCE-LICENSE.md"
    text = lic_md.read_text(encoding="utf-8") if lic_md.exists() else ""
    c.check("source.SOURCE_LICENSE.md", lic_md.exists() and "CC BY 4.0" in text and "Tier A" in text,
            "SOURCE-LICENSE.md 存在且标注 CC BY 4.0 / Tier A")
    # PII 轻量扫描（邮箱/电话），命中即失败（C2：PII 不入库）
    pii = re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+|\+?\d[\d -]{8}\d", chapter)
    c.check("source.pii_scan", not pii, f"轻量 PII 扫描命中 {len(pii)} 处")
    return meta, sections, chapter


def check_kps(c: Checker, sections: list[dict], chapter: str) -> list[dict]:
    path = c.root / ANNO / "kps.single.jsonl"
    kps = read_jsonl(path)
    c.check("kp.count", len(kps) == 50, f"KP 数 {len(kps)} == 50")
    ids = [k["id"] for k in kps]
    c.check("kp.ids_unique", len(ids) == len(set(ids)), "KP id 唯一")
    c.check("kp.ids_sorted", ids == sorted(ids), "KP 按 id 排序")
    required = {"id", "file", "spans", "name", "description", "name_zh", "section_key",
                "section_num", "concept_type", "granularity", "evidence", "anchor",
                "status", "annotator", "annotation_method", "manual_version"}
    covered: list[tuple[int, int]] = []
    for kp in kps:
        kid = kp["id"]
        missing = required - set(kp)
        c.check(f"kp.fields:{kid}", not missing, f"缺字段 {sorted(missing)}" if missing else "")
        c.check(f"kp.status:{kid}", kp.get("status") == STATUS, "status=single_annotator_draft")
        c.check(f"kp.iaa_honest:{kid}",
                "IAA not run" in kp.get("annotation_method", ""), "明示 IAA 未做")
        c.check(f"kp.file:{kid}", kp.get("file") == CHAPTER_REL, "file 指向 chapter.txt")
        spans = kp.get("spans") or []
        c.check(f"kp.span_count:{kid}", len(spans) == 1, "单文件连续 span（1 段）")
        if len(spans) != 1:
            continue
        start, end = spans[0].get("start"), spans[0].get("end")
        c.check(f"kp.span_bounds:{kid}",
                isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(chapter),
                f"span [{start},{end}) 在 [0,{len(chapter)}) 内")
        if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(chapter)):
            continue
        sec = section_for_span(sections, start, end)
        c.check(f"kp.single_section:{kid}", sec is not None, "span 落在单个 section 内")
        if sec:
            c.check(f"kp.section_ref:{kid}", kp.get("section_key") == sec["page_id"],
                    f"section_key={kp.get('section_key')} == {sec['page_id']}")
            c.check(f"kp.section_num:{kid}", kp.get("section_num") == sec.get("section_num"),
                    "section_num 与快照一致")
        for a, b in covered:
            if start < b and a < end:
                c.check(f"kp.overlap:{kid}", False, f"与 [{a},{b}) 重叠")
        covered.append((start, end))
        quote = chapter[start:end]
        ev = (kp.get("evidence") or [{}])[0]
        c.check(f"kp.evidence_span:{kid}",
                ev.get("start") == start and ev.get("end") == end and ev.get("file") == CHAPTER_REL,
                "evidence span 与 KP span 一致")
        c.check(f"kp.evidence_quote:{kid}", ev.get("quote") == quote, "evidence quote 与原文一致")
        c.check(f"kp.evidence_sha:{kid}", ev.get("quote_sha256") == sha256_bytes(quote.encode("utf-8")),
                "evidence quote sha256 一致")
        c.check(f"kp.name:{kid}", 0 < len(kp.get("name", "")) <= 120, "name 1..120")
        c.check(f"kp.description:{kid}", 0 < len(kp.get("description", "")) <= 500,
                "description 1..500")
        c.check(f"kp.concept_type:{kid}", kp.get("concept_type") in KP_TYPES,
                f"concept_type={kp.get('concept_type')}")
        c.check(f"kp.granularity:{kid}",
                kp.get("granularity") in {"concept_explanation", "proposition"},
                "granularity 合法")
    c.check("kp.single_annotator_no_fake_iaa",
            not any("iaa" in k and isinstance(k, (int, float)) for k in kps[0]),
            "KP 记录不含伪造 IAA 数值字段")
    return kps


def check_edges(c: Checker, kps: list[dict], sections: list[dict], chapter: str) -> list[dict]:
    kp_ids = {k["id"] for k in kps}
    edges = read_jsonl(c.root / ANNO / "edges.single.jsonl")
    c.check("edge.count", len(edges) == 30, f"语义边 {len(edges)} == 30")
    eids = [e["id"] for e in edges]
    c.check("edge.ids_unique", len(eids) == len(set(eids)), "edge id 唯一")
    c.check("edge.ids_sorted", eids == sorted(eids), "edge 按 id 排序")
    seen: set[tuple] = set()
    tuples: set[tuple] = set()
    per_type: dict[str, int] = {}
    for e in edges:
        eid = e["id"]
        etype = e.get("type")
        per_type[etype] = per_type.get(etype, 0) + 1
        c.check(f"edge.type:{eid}", etype in S0_TYPES, f"type={etype} ∈ S0")
        c.check(f"edge.label:{eid}", e.get("label") == "semantic", "label=semantic")
        c.check(f"edge.e_sem:{eid}", e.get("e_sem") is True, "e_sem=true")
        if etype == "contain":
            c.check(f"edge.contain_kind:{eid}", e.get("contain_kind") in CONTAIN_KINDS,
                    "contain 必须 contain_kind∈{structural,semantic}")
            c.check(f"edge.semantic_contain:{eid}", e.get("contain_kind") == "semantic",
                    "E_sem 要求 contain_kind=semantic")
        else:
            c.check(f"edge.no_contain_kind:{eid}", "contain_kind" not in e,
                    "非 contain 不得带 contain_kind")
        c.check(f"edge.endpoints:{eid}",
                e.get("source") in kp_ids and e.get("target") in kp_ids, "端点 KP 存在")
        c.check(f"edge.no_self_loop:{eid}", e.get("source") != e.get("target"), "无自环")
        c.check(f"edge.direction:{eid}", e.get("direction") in {"source->target", "both"},
                "direction 合法")
        c.check(f"edge.confidence:{eid}", e.get("confidence") in CONFIDENCE, "置信三档")
        c.check(f"edge.rationale:{eid}", len((e.get("rationale") or "").strip()) >= 8, "理由非空")
        key = (e.get("source"), e.get("target"), etype, e.get("direction"))
        c.check(f"edge.tuple_unique:{eid}", key not in seen, "tuple 唯一")
        seen.add(key)
        tuples.add(key)
        ev = e.get("evidence") or {}
        for slot in ("source_span", "target_span", "assertion_span"):
            ref = ev.get(slot)
            if not ref:
                c.check(f"edge.evidence_{slot}:{eid}", False, "缺证据 span")
                continue
            s, t = ref.get("start"), ref.get("end")
            in_bounds = isinstance(s, int) and isinstance(t, int) and 0 <= s < t <= len(chapter)
            c.check(f"edge.evidence_bounds:{eid}:{slot}", in_bounds, f"span [{s},{t}) 越界")
            if not in_bounds:
                continue
            c.check(f"edge.evidence_span_in_section:{eid}:{slot}",
                    section_for_span(sections, s, t) is not None, "证据 span 落在单 section 内")
            quote = chapter[s:t]
            c.check(f"edge.evidence_quote:{eid}:{slot}", ref.get("quote") == quote,
                    "证据引文与原文一致")
            c.check(f"edge.evidence_sha:{eid}:{slot}",
                    ref.get("quote_sha256") == sha256_bytes(quote.encode("utf-8")),
                    "证据引文 sha256 一致")
    c.check("edge.type_minimums",
            per_type.get("contain", 0) >= 10 and per_type.get("reference", 0) >= 1
            and per_type.get("extend", 0) >= 1,
            f"类型分布 {per_type}")
    return edges


def check_negatives(c: Checker, edges: list[dict]) -> list[dict]:
    path = c.root / ANNO / "edges.negative.single.jsonl"
    c.check("neg.file_exists", path.exists(), "负例文件存在")
    negs = read_jsonl(path)
    c.check("neg.count", len(negs) >= 10, f"负例 {len(negs)} >= 10")
    positive = {(e["source"], e["target"], e["type"], e.get("direction")) for e in edges}
    for n in negs:
        nid = n["id"]
        c.check(f"neg.status:{nid}", n.get("status") == STATUS, "status=single_annotator_draft")
        c.check(f"neg.reason:{nid}", len((n.get("reason") or "").strip()) >= 10, "理由非空")
        c.check(f"neg.kind:{nid}", bool(n.get("negative_kind")), "negative_kind 非空")
        candidate = (n.get("candidate_source"), n.get("candidate_target"),
                     n.get("proposed_type"), "source->target")
        c.check(f"neg.not_in_positive:{nid}", candidate not in positive,
                "负例不得同时作为正例出现")
    kinds = {n.get("negative_kind") for n in negs}
    c.check("neg.kinds_diverse", len(kinds) >= 4, f"负例类型 {len(kinds)} 类 >= 4")
    return negs


def check_queries(c: Checker, kps: list[dict], edges: list[dict]) -> dict:
    path = c.root / DOCS / "queries.json"
    c.check("query.file_exists", path.exists(), "queries.json 存在")
    doc = read_json(path)
    c.check("query.schema", doc.get("schema") == "corpus-pilot-queries/v1", "queries schema")
    qs = doc.get("queries", [])
    c.check("query.count", len(qs) == 20, f"query {len(qs)} == 20")
    c.check("query.status", doc.get("status") == STATUS, "status=single_annotator_draft")
    counts: dict[str, int] = {}
    kp_ids = {k["id"] for k in kps}
    edge_ids = {e["id"] for e in edges}
    for q in qs:
        qid = q["id"]
        counts[q["query_type"]] = counts.get(q["query_type"], 0) + 1
        c.check(f"query.type:{qid}", q.get("query_type") in QUERY_TYPES, "query_type 合法")
        c.check(f"query.text:{qid}", len((q.get("query") or "").strip()) >= 5, "query 非空")
        expected = q.get("expected_kp_ids") or []
        c.check(f"query.expected:{qid}", bool(expected), "expected_kp_ids 非空")
        c.check(f"query.expected_exist:{qid}", all(e in kp_ids for e in expected),
                "expected KP id 均存在")
        c.check(f"query.expected_edges_exist:{qid}",
                all(e in edge_ids for e in (q.get("expected_edge_ids") or [])),
                "expected edge id 均存在")
        if q.get("query_type") == "graph":
            c.check(f"query.graph_has_edges:{qid}", bool(q.get("expected_edge_ids")),
                    "graph query 必须引用语义边")
        if q.get("control"):
            c.check(f"query.control_not_graph:{qid}", q.get("query_type") != "graph",
                    "no-semantic 对照不是 graph 型")
            c.check(f"query.control_kind:{qid}", bool(q.get("control_kind")), "control_kind 非空")
    c.check("query.type_balance", all(counts.get(t, 0) == 5 for t in QUERY_TYPES),
            f"四种类型各 5 条: {counts}")
    controls = [q for q in qs if q.get("control")]
    c.check("query.controls", len(controls) >= 2, f"no-semantic 对照 {len(controls)} >= 2")
    c.check("query.split_present", all(q.get("split") in {"dev", "test"} for q in qs),
            "dev/test 标注存在")
    c.check("query.dev_test_note", bool((doc.get("dev_test_note") or "").strip()),
            "单章 dev/test 限制说明存在")
    return doc


def check_manifest(c: Checker) -> None:
    path = c.root / ANNO / "annotations-manifest.json"
    c.check("manifest.exists", path.exists(), "annotations-manifest.json 存在")
    if not path.exists():
        return
    man = read_json(path)
    c.check("manifest.counts",
            man.get("counts") == {"kp": 50, "semantic_edges": 30,
                                 "negative_edges": 14, "queries": 20},
            f"manifest counts={man.get('counts')}")
    src_meta = read_json(c.root / SOURCE / "snapshot-meta.json")
    c.check("manifest.chapter_sha",
            man.get("source_chapter_sha256") == src_meta["chapter_sha256"], "绑定快照 sha")
    for name, rel in (("kps.single.jsonl", f"{ANNO}/kps.single.jsonl"),
                      ("edges.single.jsonl", f"{ANNO}/edges.single.jsonl"),
                      ("edges.negative.single.jsonl", f"{ANNO}/edges.negative.single.jsonl")):
        c.check(f"manifest.sha:{name}", man["file_sha256"].get(name) == sha256_file(c.root / rel),
                "文件 sha 与 manifest 一致")
    c.check("manifest.queries_sha",
            man["file_sha256"].get("queries.json") ==
            sha256_file(c.root / DOCS / "queries.json"), "queries.json sha 与 manifest 一致")
    # edition 独立重算（C7：sha256(文件内容 + 标注 JSONL + 手册版本)）
    names = ["kps.single.jsonl", "edges.single.jsonl", "edges.negative.single.jsonl", "queries.json"]
    payload = "\n".join(["corpus-pilot-edition/v1", man["source_chapter_sha256"]]
                        + [man["file_sha256"][n] for n in names] + [man["manual_version"]])
    c.check("manifest.edition",
            man.get("edition") == sha256_bytes(payload.encode("utf-8")),
            "edition 独立重算一致")


def check_repro(c: Checker) -> None:
    """2× 可复现：重新抽取快照 + 重新生成标注，和仓库文件逐字节比对。"""
    sys.path.insert(0, str(c.root / "scripts" / "corpus"))
    try:
        import build_source_snapshot as bss
        import make_annotations as ma
    except Exception as exc:  # noqa: BLE001
        c.check("repro.import", False, f"无法导入脚本: {exc}")
        return
    src = c.root / SOURCE
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        try:
            bss.build(src / "pages.json", tmp / "source")
            ma.build(src, c.root / ANNO / "pilot-spec.json", tmp / "annotations")
        except Exception as exc:  # noqa: BLE001
            c.check("repro.run", False, f"重跑失败: {type(exc).__name__}: {exc}")
            return
        c.check("repro.chapter", sha256_file(tmp / "source" / "chapter.txt") ==
                sha256_file(c.root / CHAPTER_REL), "chapter.txt 2× 一致")
        c.check("repro.sections", sha256_file(tmp / "source" / "sections.json") ==
                sha256_file(src / "sections.json"), "sections.json 2× 一致")
        c.check("repro.snapshot_meta", sha256_file(tmp / "source" / "snapshot-meta.json") ==
                sha256_file(src / "snapshot-meta.json"), "snapshot-meta.json 2× 一致")
        for name in ("kps.single.jsonl", "edges.single.jsonl", "edges.negative.single.jsonl"):
            c.check(f"repro.{name}", sha256_file(tmp / "annotations" / name) ==
                    sha256_file(c.root / ANNO / name), f"{name} 2× 一致")
        c.check("repro.queries", sha256_file(tmp / "annotations" / "queries.json") ==
                sha256_file(c.root / DOCS / "queries.json"), "queries.json 2× 一致")
        c.check("repro.annotations_manifest",
                sha256_file(tmp / "annotations" / "annotations-manifest.json") ==
                sha256_file(c.root / ANNO / "annotations-manifest.json"),
                "annotations-manifest.json 2× 一致")


def check_docs(c: Checker) -> None:
    manual = c.root / DOCS / "ANNOTATION-MANUAL.md"
    plan = c.root / DOCS / "PILOT-PLAN.md"
    notice = c.root / SOURCE / "NOTICE.md"
    c.check("docs.manual_exists", manual.exists(), "ANNOTATION-MANUAL.md 存在")
    c.check("docs.plan_exists", plan.exists(), "PILOT-PLAN.md 存在")
    c.check("docs.notice_exists", notice.exists(), "source/NOTICE.md 存在")
    if manual.exists():
        text = manual.read_text(encoding="utf-8")
        # 30+ 正例 / 30+ 负例 / 20+ 边界例：手册用固定标题分节，按小节内条目计数
        c.check("docs.manual_positive", len(re.findall(r"^- P\d+", text, re.M)) >= 30,
                f"正例条目 {len(re.findall(r'^- P\\d+', text, re.M))} >= 30")
        c.check("docs.manual_negative", len(re.findall(r"^- N\d+", text, re.M)) >= 30,
                f"负例条目 {len(re.findall(r'^- N\\d+', text, re.M))} >= 30")
        c.check("docs.manual_boundary", len(re.findall(r"^- B\d+", text, re.M)) >= 20,
                f"边界例条目 {len(re.findall(r'^- B\\d+', text, re.M))} >= 20")
        for token in ("A/B/C", "裁决", "培训", "试标"):
            c.check(f"docs.manual_token:{token}", token in text, f"手册含 {token}")
    if notice.exists():
        text = notice.read_text(encoding="utf-8")
        c.check("docs.notice_attribution", "OpenStax" in text and "CC BY 4.0" in text,
                "NOTICE 含署名与许可")


def run(root: Path, check_reproducibility: bool = True) -> dict:
    c = Checker(root)
    meta, sections, chapter = check_source(c)
    kps = check_kps(c, sections, chapter)
    edges = check_edges(c, kps, sections, chapter)
    check_negatives(c, edges)
    check_queries(c, kps, edges)
    check_manifest(c)
    check_docs(c)
    if check_reproducibility:
        check_repro(c)
    return {
        "schema": "corpus-pilot-validation/v1",
        "ok": c.ok,
        "check_count": len(c.checks),
        "passed": sum(1 for x in c.checks if x["ok"]),
        "failed": c.failures(),
        "checks": c.checks,
        "counts": {"kp": len(kps), "edges": len(edges),
                   "chapter_chars": len(chapter)},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate corpus pilot package")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json-out", default="")
    ap.add_argument("--no-repro", action="store_true", help="跳过 2× 可复现检查（调试用）")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        report = run(root, check_reproducibility=not args.no_repro)
    except Exception as exc:  # noqa: BLE001 —— 校验器自身失败也必须可见
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    if args.json_out:
        out = Path(args.json_out)
        if not out.is_absolute():
            out = root / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8", newline="\n")
    summary = {k: report[k] for k in ("ok", "check_count", "passed", "failed", "counts")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
