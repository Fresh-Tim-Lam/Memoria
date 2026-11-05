#!/usr/bin/env python
"""标注者文件校验器：schema / span 越界 / 重叠 / section / 端点 / quote sha / 数量。

用途：human-kit 或 protocol v2 的 agent 标注者提交前运行；**不合规必须红**（exit 1）。
`--annotator-type human|agent` 决定角色标记：human→annotator-a/b，agent→agent-a/b。
本脚本只读标注文件与语料快照，**不生成任何标签**、不生成 IAA 数值。

检查范围：
- KP 文件：行 JSON、必填字段、id 唯一、单 span、越界、单 section、两两不重叠、
  section_key 与 span 所属 section 一致、concept_type 枚举、数量区间、annotator 角色标记；
- 候选池判定文件：pair_id 覆盖池内全部 60 对且不重复、label∈{edge,no_edge}、
  edge 必须有 S0 type/方向/置信/理由/断言 span，断言 span 越界或 quote/sha 不符即失败；
  no_edge 不得带类型/方向；池外追加只允许 pair_id=extra-*，端点必须在池/草案 KP id 内。

退出码：0 = 全绿；1 = 校验失败；2 = 输入缺失/参数错误。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

S0_TYPES = {"contain", "reference", "extend"}
CONFIDENCE = {"high", "medium", "low"}
DIRECTIONS = {"source->target", "target->source", "both"}
KP_TYPES = {"concept", "term", "formula", "mechanism", "procedure", "example"}
HUMAN_STATUS = "human_annotator_draft"
AGENT_STATUS = "agent_annotator_draft"
ANNOTATOR_TYPE_ROLES = {
    "human": {"a": "annotator-a", "b": "annotator-b"},
    "agent": {"a": "agent-a", "b": "agent-b"},
}
ROLE_ANNOTATOR = ANNOTATOR_TYPE_ROLES["human"]


class Checker:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    def check(self, cid: str, ok: bool, detail: str = "") -> bool:
        self.checks.append({"id": cid, "ok": bool(ok), "detail": detail})
        return bool(ok)

    @property
    def ok(self) -> bool:
        return all(c["ok"] for c in self.checks)

    def failures(self) -> list[str]:
        return [c["id"] for c in self.checks if not c["ok"]]


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} 第 {i} 行不是合法 JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path} 第 {i} 行不是对象")
        rows.append(row)
    return rows


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _section_of(sections: list[dict], start: int, end: int) -> dict | None:
    for sec in sections:
        if sec["start"] <= start and end <= sec["end"]:
            return sec
    return None


def _as_span(row: dict) -> tuple[int, int] | None:
    spans = row.get("spans")
    if not isinstance(spans, list) or len(spans) != 1:
        return None
    span = spans[0]
    if not isinstance(span, dict):
        return None
    start, end = span.get("start"), span.get("end")
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
        return None
    return start, end


def validate_kps(c: Checker, rows: list[dict], *, role: str, chapter: str,
                 sections: list[dict], min_kps: int, max_kps: int,
                 annotator_type: str = "human") -> None:
    expected_annotator = ANNOTATOR_TYPE_ROLES[annotator_type][role]
    expected_status = HUMAN_STATUS if annotator_type == "human" else AGENT_STATUS
    c.check("kps.count", min_kps <= len(rows) <= max_kps,
            f"KP 数 {len(rows)} 不在 [{min_kps},{max_kps}]")
    if not rows:
        return
    ids: set[str] = set()
    covered: list[tuple[int, int]] = []
    for idx, row in enumerate(rows, 1):
        rid = row.get("id")
        cid = rid if isinstance(rid, str) and rid else f"row{idx}"
        c.check(f"kp.required:{cid}",
                all(k in row for k in ("id", "spans", "section_key", "concept_type", "annotator")),
                "缺必填字段 (id/spans/section_key/concept_type/annotator)")
        c.check(f"kp.annotator:{cid}", row.get("annotator") == expected_annotator,
                f"annotator={row.get('annotator')!r} != {expected_annotator!r}")
        if "status" in row:
            c.check(f"kp.status:{cid}", row.get("status") == expected_status,
                    f"status={row.get('status')!r} 应为 {expected_status!r}")
        c.check(f"kp.id_unique:{cid}", isinstance(rid, str) and rid not in ids, "id 唯一且非空")
        if isinstance(rid, str):
            ids.add(rid)
        c.check(f"kp.concept_type:{cid}", row.get("concept_type") in KP_TYPES,
                f"concept_type={row.get('concept_type')!r}")
        if "type_uncertain" in row:
            c.check(f"kp.type_uncertain:{cid}", isinstance(row["type_uncertain"], bool),
                    "type_uncertain 必须是 bool")
        span = _as_span(row)
        c.check(f"kp.spans:{cid}", span is not None, "spans 必须是 1 段合法 [start,end)")
        if span is None:
            continue
        start, end = span
        c.check(f"kp.bounds:{cid}", 0 <= start < end <= len(chapter),
                f"span [{start},{end}) 越界（chapter 长度 {len(chapter)}）")
        sec = _section_of(sections, start, end)
        c.check(f"kp.single_section:{cid}", sec is not None, "span 必须落在单个 section 内")
        if sec is not None:
            c.check(f"kp.section_key:{cid}", row.get("section_key") == sec["page_id"],
                    f"section_key={row.get('section_key')!r} != {sec['page_id']!r}")
        for a, b in covered:
            if start < b and a < end:
                c.check(f"kp.no_overlap:{cid}", False, f"与 [{a},{b}) 重叠")
        covered.append((start, end))


def validate_pool(c: Checker, rows: list[dict], *, role: str, chapter: str,
                  pool: list[dict], a_kp_ids: set[str], expected_pool: int,
                  allow_extra: bool, annotator_type: str = "human") -> None:
    expected_annotator = ANNOTATOR_TYPE_ROLES[annotator_type][role]
    pool_by_id = {p["pair_id"]: p for p in pool}
    c.check("pool.count", len(rows) >= expected_pool,
            f"池判定 {len(rows)} 行 < 期望 {expected_pool}")
    seen: set[str] = set()
    extra = 0
    for idx, row in enumerate(rows, 1):
        pair_id = row.get("pair_id")
        cid = pair_id if isinstance(pair_id, str) and pair_id else f"row{idx}"
        c.check(f"pool.annotator:{cid}", row.get("annotator") == expected_annotator,
                f"annotator={row.get('annotator')!r} != {expected_annotator!r}")
        c.check(f"pool.pair_id:{cid}", isinstance(pair_id, str) and bool(pair_id),
                "pair_id 非空")
        if not isinstance(pair_id, str):
            continue
        if pair_id.startswith("extra-"):
            extra += 1
            c.check(f"pool.extra_allowed:{cid}", allow_extra, "不允许池外追加")
            c.check(f"pool.extra_endpoints:{cid}",
                    row.get("source") in a_kp_ids and row.get("target") in a_kp_ids,
                    "extra 边端点必须是已知 KP id")
        else:
            c.check(f"pool.known_pair:{cid}", pair_id in pool_by_id,
                    f"未知 pair_id（池内无此对）: {pair_id}")
            if pair_id in pool_by_id:
                p = pool_by_id[pair_id]
                c.check(f"pool.endpoints:{cid}",
                        row.get("source") == p["source"] and row.get("target") == p["target"],
                        "source/target 必须与池内该对完全一致（方向只写在 direction）")
        c.check(f"pool.pair_unique:{cid}", pair_id not in seen, "pair_id 重复")
        seen.add(pair_id)
        label = row.get("label")
        c.check(f"pool.label:{cid}", label in ("edge", "no_edge"), f"label={label!r}")
        if label == "no_edge":
            c.check(f"pool.no_edge_clean:{cid}",
                    not any(row.get(k) for k in ("type", "direction", "confidence")),
                    "no_edge 不得带 type/direction/confidence")
            continue
        if label != "edge":
            continue
        etype = row.get("type")
        c.check(f"pool.type:{cid}", etype in S0_TYPES, f"type={etype!r} ∈ S0")
        direction = row.get("direction")
        c.check(f"pool.direction:{cid}", direction in DIRECTIONS,
                f"direction={direction!r}")
        c.check(f"pool.confidence:{cid}", row.get("confidence") in CONFIDENCE,
                f"confidence={row.get('confidence')!r}")
        c.check(f"pool.rationale:{cid}", len((row.get("rationale") or "").strip()) >= 8,
                "rationale 非空（>=8 字符）")
        span = row.get("assertion_span")
        c.check(f"pool.assertion_present:{cid}", isinstance(span, dict),
                "edge 必须有 assertion_span")
        if not isinstance(span, dict):
            continue
        start, end = span.get("start"), span.get("end")
        c.check(f"pool.assertion_bounds:{cid}",
                isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(chapter),
                f"assertion_span [{start},{end}) 越界")
        if not (isinstance(start, int) and isinstance(end, int)
                and 0 <= start < end <= len(chapter)):
            continue
        quote = span.get("quote")
        slice_text = chapter[start:end]
        c.check(f"pool.assertion_quote:{cid}",
                isinstance(quote, str) and quote == slice_text,
                "assertion_span.quote 必须与 chapter.txt 该区间逐字一致")
        if "quote_sha256" in span and span["quote_sha256"]:
            c.check(f"pool.assertion_sha:{cid}",
                    span["quote_sha256"] == sha256_text(slice_text),
                    "assertion_span.quote_sha256 与区间内容不符")
    missing = sorted(set(pool_by_id) - seen)
    c.check("pool.coverage", not missing, f"缺少池内判定: {missing[:8]}{'…' if len(missing) > 8 else ''}")
    if extra:
        c.check("pool.extra_reported", True, f"池外追加 {extra} 条（报告会单列）")


def run(role: str, kps_path: Path, pool_path: Path, chapter_path: Path,
        sections_path: Path, pool_file: Path, a_kps_path: Path,
        min_kps: int = 45, max_kps: int = 55, expected_pool: int = 60,
        allow_extra: bool = True, annotator_type: str = "human") -> dict:
    missing = [str(p) for p in (kps_path, pool_path, chapter_path, sections_path,
                                pool_file, a_kps_path) if not p.exists()]
    if missing:
        return {"schema": "human-label-validation/v1", "ok": False, "status": "missing_input",
                "missing": missing, "checks": []}
    chapter = chapter_path.read_text(encoding="utf-8")
    sections = json.loads(sections_path.read_text(encoding="utf-8"))["sections"]
    pool = read_jsonl(pool_file)
    a_kp_ids = {k["id"] for k in read_jsonl(a_kps_path)}
    c = Checker()
    c.check("role", role in ("a", "b"), f"role={role!r}")
    c.check("annotator_type", annotator_type in ANNOTATOR_TYPE_ROLES,
            f"annotator_type={annotator_type!r}")
    c.check("chapter_no_crlf_no_bom",
            "\r" not in chapter and not chapter_path.read_bytes().startswith(b"\xef\xbb\xbf"),
            "chapter.txt 为 LF/UTF-8 无 BOM")
    try:
        kps_rows = read_jsonl(kps_path)
        pool_rows = read_jsonl(pool_path)
    except ValueError as exc:
        c.check("jsonl_parse", False, str(exc))
        return {"schema": "human-label-validation/v1", "ok": False, "status": "invalid",
                "checks": c.checks, "failed": c.failures()}
    validate_kps(c, kps_rows, role=role, chapter=chapter, sections=sections,
                 min_kps=min_kps, max_kps=max_kps, annotator_type=annotator_type)
    validate_pool(c, pool_rows, role=role, chapter=chapter, pool=pool,
                  a_kp_ids=a_kp_ids, expected_pool=expected_pool,
                  allow_extra=allow_extra, annotator_type=annotator_type)
    return {
        "schema": "human-label-validation/v1",
        "ok": c.ok,
        "status": "pass" if c.ok else "fail",
        "role": role,
        "annotator_type": annotator_type,
        "inputs": {"kps": str(kps_path), "pool_judgments": str(pool_path),
                   "kps_sha256": sha256_file(kps_path),
                   "pool_judgments_sha256": sha256_file(pool_path)},
        "counts": {"kp": len(kps_rows), "pool_judgments": len(pool_rows),
                   "expected_pool": expected_pool},
        "checks": c.checks,
        "failed": c.failures(),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate human annotator labels (KPs + pool judgments)")
    ap.add_argument("--role", required=True, choices=["a", "b"])
    ap.add_argument("--annotator-type", choices=["human", "agent"], default="human",
                    help="标注来源：human=human-kit（annotator-a/b）；agent=protocol v2（agent-a/b）")
    ap.add_argument("--kps", required=True)
    ap.add_argument("--pool-judgments", required=True)
    ap.add_argument("--chapter", default="artifacts/corpus/pilot/source/chapter.txt")
    ap.add_argument("--sections", default="artifacts/corpus/pilot/source/sections.json")
    ap.add_argument("--pool", default="artifacts/corpus/pilot/iaa/edge-candidate-pool.jsonl")
    ap.add_argument("--a-kps", default="artifacts/corpus/pilot/annotations/kps.single.jsonl")
    ap.add_argument("--min-kps", type=int, default=45)
    ap.add_argument("--max-kps", type=int, default=55)
    ap.add_argument("--expected-pool", type=int, default=60)
    ap.add_argument("--no-extra-pairs", action="store_true")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args(argv)

    report = run(args.role, Path(args.kps), Path(args.pool_judgments), Path(args.chapter),
                 Path(args.sections), Path(args.pool), Path(args.a_kps),
                 min_kps=args.min_kps, max_kps=args.max_kps,
                 expected_pool=args.expected_pool, allow_extra=not args.no_extra_pairs,
                 annotator_type=args.annotator_type)
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8", newline="\n")
    if report.get("status") == "missing_input":
        print(json.dumps({"ok": False, "status": "missing_input",
                          "missing": report["missing"]}, ensure_ascii=False, indent=2),
              file=sys.stderr)
        return 2
    summary = {"ok": report["ok"], "status": report["status"],
               "counts": report.get("counts"), "failed": report.get("failed", [])[:20],
               "failed_count": len(report.get("failed", []))}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
