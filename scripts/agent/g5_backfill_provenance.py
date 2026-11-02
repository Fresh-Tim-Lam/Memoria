#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G5d-1 / G5 §2.2-3 M6：provenance 回填器（研究侧，只读 frozen 副本，产出建议值，不写用户库）。

为 **62 条边**产出三态建议（不写产品、不写用户库、不改 frozen）：
  作者边 26（origin=sidecar_edge）→ missing（无锚点；asserted 需作者流程，不得冒充）
  link 投影 3（origin=link）      → inferred + assertion_source{file,line_start,line_end,quote_sha256}
  contain 派生 33（origin=range） → inferred + derived_by=system_range + generator_version=contain-v1
                                     （不产 assertion_source；出处由 KP range 复算）

用法（cwd = 仓库根）：
  python scripts/agent/g5_backfill_provenance.py --kb <frozen副本> --out <g5d目录>
  python scripts/agent/g5_backfill_provenance.py --kb <frozen副本> --out <g5d目录> --check
  --check：不写盘；重算并与既有 edges-suggestions.jsonl / backfill-report.json 逐字节比对，
           一致 exit 0，不一致 exit 1（幂等/防漂移）。

退出码：
  0 成功 / check 一致
  1 --check 与既有产物不一致
  2 输入非法（路径不存在/不是 KB/结构缺失）
  3 边数或 origin 分布不符合冻结契约（62 = 26/3/33）
  4 数据不足以按规定规则产出（如 link 边找不到 instances/line；**停下报告，不猜**）

边界：只读 --kb（先复制到临时目录再 collect，绝不写 frozen/用户库）；不写 src/**、不 commit。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("CONFIG ERROR: 需要 PyYAML")
    sys.exit(2)

REPO = Path(__file__).resolve().parents[2]
FROZEN_DEFAULT = REPO / "artifacts/agent/verify/debate/kg-retrieval/round2/frozen/数字通信原理"
DEFAULT_OUT = REPO / "artifacts/agent/verify/graph-utility/g5d"
EXPECTED_EDGES = 62
EXPECTED_ORIGIN = {"sidecar_edge": 26, "link": 3, "range": 33}
CONTAIN_GENERATOR = "contain-v1"
SUGGESTIONS = "edges-suggestions.jsonl"
REPORT = "backfill-report.json"
SCHEMA_VERSION = "gue-g5d-suggestions/v1"


def ensure_utf8_stdio() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def find_manifest(kb: Path) -> tuple[Path | None, dict]:
    """MANIFEST 定位：kb/MANIFEST.json → kb.parent/MANIFEST.json → 仓库 frozen/MANIFEST.json。"""
    for cand in (kb / "MANIFEST.json", kb.parent / "MANIFEST.json",
                 REPO / "artifacts/agent/verify/debate/kg-retrieval/round2/frozen/MANIFEST.json"):
        if cand.is_file():
            try:
                return cand, json.loads(cand.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return cand, {}
    return None, {}


def corpus_identity(kb: Path) -> dict:
    man_path, man = find_manifest(kb)
    corpus = {"kb_name": kb.name}
    if man_path is not None:
        corpus.update({
            "manifest_path": man_path.relative_to(REPO).as_posix() if man_path.is_relative_to(REPO) else man_path.name,
            "manifest_sha256": sha256_file(man_path),
            "taken_at": man.get("taken_at") or man.get("frozen_at"),
            "build_state": man.get("build_state"),
        })
        corpus["corpus_id"] = corpus["manifest_sha256"]
    else:
        sidecars = sorted((kb / ".memoria/sidecars").rglob("*.memoria.yaml"))
        h = hashlib.sha256()
        for p in sidecars:
            h.update(p.relative_to(kb).as_posix().encode("utf-8") + b"\0" + p.read_bytes() + b"\0")
        corpus.update({"manifest_path": None, "manifest_sha256": None,
                       "taken_at": None, "build_state": None, "corpus_id": h.hexdigest()})
    return corpus


def edge_fingerprint(edge: dict, corpus: dict) -> str:
    """DM-P1：canonical id = type|source_id|target_id；研究侧指纹 = sha256(canonical + corpus identity)。"""
    canonical = f"{edge['type']}|{edge['source_id']}|{edge['targets'][0]}"
    return hashlib.sha256(f"{canonical}|{corpus['corpus_id']}".encode("utf-8")).hexdigest()


def load_kb_copy(kb: Path) -> tuple[dict, dict, Path, Path]:
    """复制到临时目录后 collect（确保对 --kb 只读），返回 (graph, nodes, kb_copy, tmp_root)。"""
    tmp = Path(tempfile.mkdtemp(prefix="g5d-backfill-"))
    os.environ.setdefault("MEMORIA_CONFIG_DIR", str(tmp / "cfg"))
    kb_copy = tmp / "kb"
    shutil.copytree(kb, kb_copy)
    sys.path.insert(0, str(REPO / "src"))
    from memoria.graph.collector import collect_graph_data  # noqa: E402
    graph = collect_graph_data(str(kb_copy))
    nodes = {n["id"]: n for n in graph.get("nodes") or []}
    return graph, nodes, kb_copy, tmp


def sidecar_for_md(kb: Path, md_rel: str) -> Path | None:
    """md 相对路径 → .memoria/sidecars/<...>.memoria.yaml（仓库约定）。"""
    stem = md_rel[:-3] if md_rel.endswith(".md") else md_rel
    cand = kb / ".memoria/sidecars" / (stem + ".memoria.yaml")
    return cand if cand.is_file() else None


def read_slice(kb: Path, file_rel: str, line_start: int, line_end: int) -> tuple[str, bool]:
    p = kb / file_rel
    if not p.is_file():
        return "", False
    lines = p.read_text(encoding="utf-8-sig").splitlines()
    if not (1 <= line_start <= line_end <= len(lines)):
        return "", False
    text = "\n".join(lines[line_start - 1:line_end])
    return text, bool(text.strip())


def suggestion_for_author(edge: dict, corpus: dict) -> dict:
    return {
        "schema": SCHEMA_VERSION,
        "edge_fingerprint": edge_fingerprint(edge, corpus),
        "canonical_id": f"{edge['type']}|{edge['source_id']}|{edge['targets'][0]}",
        "edge": {"type": edge["type"], "source_id": edge["source_id"],
                 "target_id": edge["targets"][0], "file": edge.get("file")},
        "origin": edge.get("origin"),
        "suggested_state": "missing",
        "proposed_fields": {"provenance_state": "missing"},
        "rationale": "作者纯边（origin=sidecar_edge）在 sidecar edges[] 中无行锚点；默认 missing。"
                     "真正的 asserted 只能由作者流程补 assertion_source，本回填器不得冒充。",
        "evidence": {"file": edge.get("file"), "line_start": None, "line_end": None,
                     "quote_sha256": None, "anchor_available": False},
        "assertion_needed": True,
    }


def suggestion_for_link(edge: dict, corpus: dict, kb: Path) -> dict | (None, str):
    """link 投影：用 links[].instances.line（→ 单点 assertion_source）投影为 inferred。"""
    file_rel = edge.get("file")
    line = edge.get("line")
    target = edge["targets"][0]
    if not file_rel or not isinstance(line, int):
        return None, f"link 边缺少 file/line（source={edge['source_id']} target={target}）"
    sc_path = sidecar_for_md(kb, file_rel)
    if sc_path is None:
        return None, f"link 边找不到来源 sidecar：{file_rel}"
    sc = yaml.safe_load(sc_path.read_text(encoding="utf-8-sig")) or {}
    links = [x for x in (sc.get("links") or []) if isinstance(x, dict)]
    hit = None
    for l in links:
        lines = [i.get("line") for i in (l.get("instances") or []) if isinstance(i, dict)]
        if target in (l.get("targets") or []) and line in lines:
            hit = l
            break
    if hit is None:
        return None, (f"link 边在 sidecar links[] 中找不到 instances.line={line}/target={target}"
                      f"（file={file_rel}）——按契约应存在，停下报告")
    text, non_empty = read_slice(kb, file_rel, line, line)
    if not non_empty:
        return None, f"link 边锚点正文切片为空：{file_rel}:{line}"
    anchor = {"file": file_rel, "line_start": line, "line_end": line,
              "quote_sha256": sha256_text(text)}
    anchor_text = hit.get("anchor_text")
    return {
        "schema": SCHEMA_VERSION,
        "edge_fingerprint": edge_fingerprint(edge, corpus),
        "canonical_id": f"{edge['type']}|{edge['source_id']}|{target}",
        "edge": {"type": edge["type"], "source_id": edge["source_id"],
                 "target_id": target, "file": file_rel},
        "origin": "link",
        "suggested_state": "inferred",
        "proposed_fields": {
            "provenance_state": "inferred",
            "derived_by": "system_link",
            "assertion_source": anchor,
        },
        "rationale": "link 投影边：锚点来自 sidecar links[].instances[].line（单点投影），"
                     "按 G5 §2.2.1b 只能标 inferred（弱证据），不得写成 asserted。",
        "evidence": {**anchor, "anchor_available": True,
                     "anchor_source_field": "links[].instances[].line",
                     "anchor_text": anchor_text},
        "assertion_needed": False,
    }


def suggestion_for_contain(edge: dict, corpus: dict, nodes: dict, kb: Path) -> dict:
    """contain 派生：system_range/contain-v1，不产 assertion_source；出处由 KP range 复算。"""
    src = nodes.get(edge["source_id"]) or {}
    tgt = nodes.get(edge["targets"][0]) or {}
    file_rel = edge.get("file") or src.get("file")
    s_start, s_end = src.get("start_line"), src.get("end_line")
    evidence = {"file": file_rel, "line_start": s_start, "line_end": s_end,
                "quote_sha256": None, "anchor_available": False,
                "range_source": "source KP range", "target_range": [tgt.get("start_line"), tgt.get("end_line")]}
    if file_rel and isinstance(s_start, int) and isinstance(s_end, int):
        text, non_empty = read_slice(kb, file_rel, s_start, s_end)
        if non_empty:
            evidence.update({"quote_sha256": sha256_text(text), "anchor_available": True})
    return {
        "schema": SCHEMA_VERSION,
        "edge_fingerprint": edge_fingerprint(edge, corpus),
        "canonical_id": f"{edge['type']}|{edge['source_id']}|{edge['targets'][0]}",
        "edge": {"type": edge["type"], "source_id": edge["source_id"],
                 "target_id": edge["targets"][0], "file": file_rel},
        "origin": "range",
        "suggested_state": "inferred",
        "proposed_fields": {
            "provenance_state": "inferred",
            "derived_by": "system_range",
            "generator_version": CONTAIN_GENERATOR,
        },
        "rationale": "contain 由 KP range 几何派生（system_range），不需要作者断言；"
                     "出处由源/目标 KP range 复算，按定义标 inferred（系统弱证据），不写 assertion_source。",
        "evidence": evidence,
        "assertion_needed": False,
    }


def contract_errors(graph: dict) -> list[str]:
    errors: list[str] = []
    edges = graph.get("edges") or []
    if len(edges) != EXPECTED_EDGES:
        errors.append(f"边数 {len(edges)} != 冻结契约 {EXPECTED_EDGES}")
    origin_counts: dict[str, int] = {}
    for e in edges:
        origin_counts[e.get("origin")] = origin_counts.get(e.get("origin"), 0) + 1
    if origin_counts != EXPECTED_ORIGIN:
        errors.append(f"origin 分布 {origin_counts} != 冻结契约 {EXPECTED_ORIGIN}")
    return errors


def build_suggestions(graph: dict, nodes: dict, kb: Path, corpus: dict) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    edges = graph.get("edges") or []
    out = []
    for e in edges:
        origin = e.get("origin")
        if origin == "sidecar_edge":
            out.append(suggestion_for_author(e, corpus))
        elif origin == "link":
            r = suggestion_for_link(e, corpus, kb)
            if isinstance(r, tuple):
                errors.append(r[1])
            else:
                out.append(r)
        elif origin == "range":
            out.append(suggestion_for_contain(e, corpus, nodes, kb))
        else:
            errors.append(f"未知 origin={origin!r}（edge={e.get('source_id')}→{e.get('targets')}）")
    out.sort(key=lambda x: x["edge_fingerprint"])
    return out, errors


def build_report(suggestions: list[dict], corpus: dict) -> dict:
    by_state = {"asserted": 0, "inferred": 0, "missing": 0}
    by_origin = {k: 0 for k in EXPECTED_ORIGIN}
    cross: dict[str, dict[str, int]] = {}
    for s in suggestions:
        by_state[s["suggested_state"]] += 1
        by_origin[s["origin"]] = by_origin.get(s["origin"], 0) + 1
        cross.setdefault(s["origin"], {}).setdefault(s["suggested_state"], 0)
        cross[s["origin"]][s["suggested_state"]] += 1
    total = len(suggestions)
    report = {
        "schema": "gue-g5d-backfill-report/v1",
        "protocol": "G5 §2.2-1b / DM-P1..P8 / M6",
        "corpus": corpus,
        "counting_discipline": "三态 = asserted / inferred / missing；asserted 比例才是可核断言比例（本阶段 0）",
        "by_state": by_state,
        "by_state_ratio": {k: round(v / total, 6) if total else 0 for k, v in by_state.items()},
        "by_origin": by_origin,
        "cross_origin_state": cross,
        "total": total,
        "origin_contract": EXPECTED_ORIGIN,
        "asserted_written": False,
        "assertion_needed": {"sidecar_edge": 26, "link": 0, "range": 0},
        "system_derived_no_assertion": {"origin": "range", "count": by_origin.get("range", 0),
                                        "derived_by": "system_range", "generator_version": CONTAIN_GENERATOR},
        "notes": [
            "作者边 26 条只能 missing：sidecar edges[] 无锚点，asserted 需作者流程（本器不冒充）。",
            "link 3 条按 links[].instances[].line 投影为 inferred + assertion_source。",
            "contain 33 条为 system_range/contain-v1，不产 assertion_source，单列'系统派生，不需要断言'。",
            "26/3/33 是 origin 分布；三态计数为 asserted=0 / inferred=36 / missing=26。",
            "只读 frozen 副本；不写用户库、不改 src/**、未 commit。",
        ],
    }
    return report


def dump_suggestions(suggestions: list[dict]) -> bytes:
    return "".join(json.dumps(s, ensure_ascii=False, sort_keys=True) + "\n"
                   for s in suggestions).encode("utf-8")


def dump_report(report: dict) -> bytes:
    return (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode("utf-8")


def validate_input(kb: Path) -> str | None:
    if not kb.exists():
        return f"输入路径不存在: {kb}"
    if not kb.is_dir():
        return f"输入不是目录: {kb}"
    if not (kb / ".memoria/sidecars").is_dir():
        return f"不是 Memoria KB 目录（缺 .memoria/sidecars）: {kb}"
    mds = [p for p in kb.rglob("*.md") if ".memoria" not in p.parts]
    if not mds:
        return f"KB 目录下没有 .md 文件: {kb}"
    return None


def main() -> int:
    ensure_utf8_stdio()
    ap = argparse.ArgumentParser(description="G5d-1 M6 provenance 回填器（只读建议值）")
    ap.add_argument("--kb", default=str(FROZEN_DEFAULT))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--check", action="store_true", help="重算并与既有产物逐字节比对，不写盘")
    a = ap.parse_args()

    kb = Path(a.kb).resolve()
    out = Path(a.out).resolve()
    err = validate_input(kb)
    if err:
        print(f"INPUT ERROR: {err}")
        return 2

    corpus = corpus_identity(kb)
    graph, nodes, kb_copy, tmp = load_kb_copy(kb)
    try:
        c_errs = contract_errors(graph)
        if c_errs:
            print("CONTRACT ERROR（输入不符合冻结契约，拒绝产出建议）:")
            for e in c_errs:
                print(f"  - {e}")
            return 3
        suggestions, errors = build_suggestions(graph, nodes, kb_copy, corpus)
        if errors:
            print("RULE CONFLICT（不猜，停下报告）:")
            for e in errors[:20]:
                print(f"  - {e}")
            return 4
        report = build_report(suggestions, corpus)
        s_bytes, r_bytes = dump_suggestions(suggestions), dump_report(report)
        if a.check:
            s_path, r_path = out / SUGGESTIONS, out / REPORT
            if not s_path.is_file() or not r_path.is_file():
                print(f"CHECK FAIL: 既有产物缺失（{s_path if not s_path.is_file() else r_path}）")
                return 1
            if s_path.read_bytes() != s_bytes:
                print(f"CHECK FAIL: {SUGGESTIONS} 与重算结果不一致（漂移/非幂等）")
                return 1
            if r_path.read_bytes() != r_bytes:
                print(f"CHECK FAIL: {REPORT} 与重算结果不一致（漂移/非幂等）")
                return 1
            print(f"CHECK OK: {SUGGESTIONS} + {REPORT} 逐字节一致（total={report['total']}）")
            return 0
        out.mkdir(parents=True, exist_ok=True)
        (out / SUGGESTIONS).write_bytes(s_bytes)
        (out / REPORT).write_bytes(r_bytes)
        print(f"OK backfill: total={report['total']} "
              f"asserted={report['by_state']['asserted']} inferred={report['by_state']['inferred']} "
              f"missing={report['by_state']['missing']} by_origin={report['by_origin']}")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
