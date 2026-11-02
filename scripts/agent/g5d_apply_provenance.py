#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G5d-2 写回器（**只允许副本演练**）：把 M6 建议写进 sidecar 的副本，并留闭环证据。

⚠️ B1 阻塞点（必须随产物一起读）：
    contain(33)/link(3) 的 provenance 写进 sidecar 后，**当前产品不消费**：
    · contain 由 edge_derivation.derive_contain_edges 从 KP range 每次重派生（硬编码
      derived_by=system_range/generator_version=contain-v1），sidecar 无 contain 存储位；
    · link 由 derive_link_edges 从 links[].instances 重派生（硬编码 derived_by=system_link），
      links[]/edges[] 的新键都不透传；
    · collector 先拼 contain+link+sidecar 再 dedupe(先到先得) ⇒ sidecar 影子条目被丢弃。
    因此本轮写回是 **影子写（consumer_effect=none）**：不改变 agent 可见事实。
    G5d 用户库写回前必须先补消费通路（或人裁确认不需要写回）。
    唯一可被产品消费的写回路径 = 作者边 edges[] 的 assertion_source（本轮按契约不写；
    另有 copy-only 正证 positive-control 证明该路径真实生效）。

用法（cwd = 仓库根）：
  # 1) 副本演练（先快照）
  python scripts/agent/g5d_apply_provenance.py --kb <副本KB> --snapshot <snap> --out <apply目录> --dry-run
  python scripts/agent/g5d_apply_provenance.py --kb <副本KB> --snapshot <snap> --out <apply目录> --confirm-copy
  # 2) 幂等复核（第二次写；应 0 变更）
  python scripts/agent/g5d_apply_provenance.py --kb <副本KB> --snapshot <snap> --out <apply目录2> --confirm-copy
  # 3) copy-only 正证：作者边 assertion_source 被产品真实消费
  python scripts/agent/g5d_apply_provenance.py --positive-control --kb <副本KB> --out <ok.json> --confirm-copy

安全闸：目标必须位于 <repo>/artifacts/** 或系统临时目录；拒绝 frozen 原目录与一切用户库；
        写副本必须 --confirm-copy；写前必须 --snapshot 且快照与当前 KB 状态一致；否则不写。

退出码：0 OK｜1 check/不一致｜2 用法/安全闸拒绝｜3 契约不符（62/26-3-33）｜4 快照缺失/不匹配｜
        5 规则冲突（白名单外键/锚点 hash 不符/结构异常，不写）｜6 写失败。
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
FROZEN = REPO / "artifacts/agent/verify/debate/kg-retrieval/round2/frozen/数字通信原理"
FROZEN_ROOT = FROZEN.parent
SUGGESTIONS = REPO / "artifacts/agent/verify/graph-utility/g5d/edges-suggestions.jsonl"
SNAPSHOT_SCHEMA = "g5-snapshot/v1"
EXPECTED_EDGES = 62
EXPECTED_ORIGIN = {"sidecar_edge": 26, "link": 3, "range": 33}
WRITE_ORIGINS = {"range", "link"}
WRITE_KEYS = {"provenance_state", "derived_by", "generator_version", "assertion_source"}
BASE_KEYS = {"type", "source_id", "targets"}
FORBIDDEN_KEYS = {"confidence", "valid_from", "valid_to", "edge_id", "schema_version", "instances"}
PROVENANCE_KEYS_8 = ("derived_by", "provenance_state", "assertion_source", "instances",
                     "generator_version", "valid_from", "valid_to", "confidence")
CONTAIN_GENERATOR = "contain-v1"
B1_CONSUMER = ("B1: contain/link provenance 当前无产品消费通路；写回不改变 agent 可见事实；"
               "G5d 用户库写回前必须先补消费通路或经人裁确认不需要写回")
B1_EVIDENCE = {
    "collector_assembly": "src/memoria/graph/collector.py:82-86（contain + link_edges + sidecar_edges）",
    "dedupe_first_wins": "src/memoria/graph/edge_derivation.py:624-666（key=(type,source,target,no_build)，先到先得）",
    "contain_rederived": "src/memoria/graph/edge_derivation.py:317-371（KP range 几何派生；硬编码 system_range/contain-v1）",
    "link_rederived": "src/memoria/graph/edge_derivation.py:459-462,506-...（links[].instances 派生；硬编码 system_link）",
    "sidecar_passthrough_scope": "src/memoria/graph/edge_derivation.py:702-707（仅 edges[] 作者边白名单透传）",
    "empirical": "临时副本写 1 contain + 1 link 到 sidecar edges[] 后 collect：edges 仍 62，输出无 provenance_state/assertion_source",
}


def ensure_utf8_stdio() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def quote_sha256_from_slice(text: str) -> str:
    """dec-20261102-92be93d8：sha256(UTF-8(切片行按 "\\n" 连接，无尾随换行，不 strip))。"""
    return sha256_text(text)


def load_product():
    sys.path.insert(0, str(REPO / "src"))
    os.environ.setdefault("MEMORIA_CONFIG_DIR", os.path.join(tempfile.gettempdir(), "g5d2-cfg"))
    from memoria.graph.collector import collect_graph_data  # noqa: E402
    from memoria.services.document import DocumentService  # noqa: E402
    from memoria.storage.sidecar import load_sidecar, save_sidecar  # noqa: E402
    return collect_graph_data, DocumentService, load_sidecar, save_sidecar


def find_manifest(kb: Path) -> tuple[Path | None, dict]:
    for cand in (kb / "MANIFEST.json", kb.parent / "MANIFEST.json", FROZEN_ROOT / "MANIFEST.json"):
        if cand.is_file():
            try:
                return cand, json.loads(cand.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return cand, {}
    return None, {}


def corpus_identity(kb: Path) -> dict:
    mp, man = find_manifest(kb)
    cid = sha256_file(mp) if mp is not None else None
    if cid is None:
        h = hashlib.sha256()
        for p in sorted((kb / ".memoria/sidecars").rglob("*.memoria.yaml")):
            h.update(p.relative_to(kb).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
        cid = h.hexdigest()
    return {"kb_name": kb.name, "manifest_path": (mp.relative_to(REPO).as_posix() if mp and mp.is_relative_to(REPO) else (mp.name if mp else None)),
            "manifest_sha256": sha256_file(mp) if mp else None, "corpus_id": cid}


def sidecar_rel_for_md(md_rel: str) -> str:
    stem = md_rel[:-3] if md_rel.endswith(".md") else md_rel
    return f".memoria/sidecars/{stem}.memoria.yaml"


def read_slice(kb: Path, file_rel: str, start: int, end: int) -> tuple[str, bool]:
    p = kb / file_rel
    if not p.is_file():
        return "", False
    lines = p.read_text(encoding="utf-8-sig").splitlines()
    if not (1 <= start <= end <= len(lines)):
        return "", False
    text = "\n".join(lines[start - 1:end])
    return text, bool(text.strip())


def snapshot_files_of(kb: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in kb.rglob("*.md"):
        rel = p.relative_to(kb).as_posix()
        if not rel.startswith(".memoria/"):
            out[rel] = sha256_file(p)
    for p in (kb / ".memoria/sidecars").rglob("*.memoria.yaml"):
        rel = p.relative_to(kb).as_posix()
        out[rel] = sha256_file(p)
    return out


def check_snapshot_matches(kb: Path, snap: Path) -> str | None:
    if not snap.is_dir() or not (snap / "manifest.json").is_file() or not (snap / "counts.json").is_file():
        return f"快照不存在/不完整: {snap}"
    try:
        m = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return f"快照 manifest 非法: {exc}"
    if m.get("schema") != SNAPSHOT_SCHEMA:
        return f"快照 schema 不匹配: {m.get('schema')}"
    cur = snapshot_files_of(kb)
    snap_files = {e["rel"]: e["sha256"] for e in m.get("files") or []}
    if set(cur) != set(snap_files):
        return f"快照文件集与当前 KB 不一致（cur={len(cur)}, snap={len(snap_files)}）"
    bad = [rel for rel, sh in snap_files.items() if cur.get(rel) != sh]
    if bad:
        return f"快照与当前 KB 不一致（{len(bad)} 文件 sha 不同，如 {bad[:2]}）"
    return None


def safety_gate(kb: Path, confirm_copy: bool, snapshot: Path | None, *, writing: bool, require_snapshot: bool = True) -> str | None:
    if not kb.exists() or not kb.is_dir():
        return f"目标 KB 不存在或不是目录: {kb}"
    if not (kb / ".memoria/sidecars").is_dir():
        return f"不是 Memoria KB（缺 .memoria/sidecars）: {kb}"
    kb_r = kb.resolve()
    if kb_r == FROZEN.resolve() or FROZEN.resolve() in kb_r.parents or \
       kb_r == FROZEN_ROOT.resolve() or FROZEN_ROOT.resolve() in kb_r.parents:
        return f"拒绝：frozen 原目录只读，不允许写回: {kb_r}"
    allowed = [REPO / "artifacts", Path(tempfile.gettempdir()).resolve()]
    if not any(kb_r.is_relative_to(a.resolve()) for a in allowed if a.exists() or a == REPO / "artifacts"):
        return f"拒绝：目标不在副本区（仅允许 <repo>/artifacts/** 或 %TEMP%/**）: {kb_r}"
    if writing and not confirm_copy:
        return "拒绝：写副本需要显式 --confirm-copy（防止误写用户库）"
    if writing and require_snapshot and snapshot is None:
        return "拒绝：写回前必须提供 --snapshot（写前快照）"
    return None


def load_suggestions(path: Path) -> tuple[list[dict], dict | None, str | None]:
    """建议 JSONL 每行不含 corpus（G5d-1 口径）；语料身份取同目录 backfill-report.json.corpus。"""
    if not path.is_file():
        return [], None, f"建议文件不存在: {path}"
    rows = []
    corpus = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("schema") != "gue-g5d-suggestions/v1":
            return [], None, f"建议 schema 不符: {r.get('schema')}"
        corpus = r.get("corpus") or corpus
        rows.append(r)
    if corpus is None:
        rp = path.parent / "backfill-report.json"
        if rp.is_file():
            try:
                corpus = (json.loads(rp.read_text(encoding="utf-8")) or {}).get("corpus")
            except json.JSONDecodeError:
                corpus = None
    if len(rows) != EXPECTED_EDGES:
        return [], corpus, f"建议条数 {len(rows)} != {EXPECTED_EDGES}"
    if not corpus or not corpus.get("corpus_id"):
        return [], corpus, "建议语料身份缺失（无 row.corpus 且无同目录 backfill-report.json.corpus）"
    return rows, corpus, None


def plan_writes(suggestions: list[dict], corpus: dict) -> tuple[list[dict], list[str]]:
    plan, errors = [], []
    for s in suggestions:
        origin = s.get("origin")
        if origin not in WRITE_ORIGINS:
            continue
        pf = s.get("proposed_fields") or {}
        bad = sorted(set(pf) - WRITE_KEYS)
        if bad:
            errors.append(f"{s.get('edge_fingerprint')}: 白名单外键 {bad}")
        forbidden = sorted(set(pf) & FORBIDDEN_KEYS)
        if forbidden:
            errors.append(f"{s.get('edge_fingerprint')}: 禁止写键 {forbidden}")
        edge = s.get("edge") or {}
        item = {
            "fingerprint": s["edge_fingerprint"],
            "origin": origin,
            "type": edge.get("type"),
            "source_id": edge.get("source_id"),
            "target_id": edge.get("target_id"),
            "file": edge.get("file"),
            "proposed_fields": {k: v for k, v in pf.items() if k in WRITE_KEYS},
        }
        if origin == "link":
            anchor = (pf.get("assertion_source") or {})
            if set(anchor) != {"file", "line_start", "line_end", "quote_sha256"}:
                errors.append(f"{item['fingerprint']}: link assertion_source 四键不齐: {sorted(anchor)}")
                continue
            if not isinstance(anchor.get("line_start"), int) or not isinstance(anchor.get("line_end"), int):
                errors.append(f"{item['fingerprint']}: link 行号非整数")
                continue
            if anchor.get("file") != item["file"]:
                errors.append(f"{item['fingerprint']}: link anchor.file 与 edge.file 不一致")
                continue
        plan.append(item)
    counts = {"range": 0, "link": 0}
    for p in plan:
        counts[p["origin"]] += 1
    if counts != {"range": 33, "link": 3}:
        errors.append(f"写回计划 origin 分布 {counts} != {{'range':33,'link':3}}")
    return plan, errors


def apply_plan_to_kb(kb: Path, plan: list[dict]) -> tuple[dict, list[str], dict]:
    """在给定 KB（副本）上执行影子写；返回 (diff, errors, stats)。幂等：已存在同值则跳过。"""
    collect_graph_data, DocumentService, load_sidecar, save_sidecar = load_product()
    errors: list[str] = []
    files_changed: dict[str, dict] = {}
    edges_changed: list[dict] = []
    key_counts: dict[str, int] = {}
    already = 0
    for item in plan:
        sc_rel = sidecar_rel_for_md(item["file"])
        sc_path = kb / sc_rel
        if not sc_path.is_file():
            errors.append(f"{item['fingerprint']}: sidecar 不存在: {sc_rel}")
            continue
        before_sha = sha256_file(sc_path)
        data = yaml.safe_load(sc_path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            errors.append(f"{sc_rel}: sidecar 结构非法")
            continue
        edges = data.get("edges")
        if not isinstance(edges, list):
            edges = []
        # link 锚点：写前重读切片，hash 必须与建议一致（C4）
        fields = dict(item["proposed_fields"])
        if item["origin"] == "link":
            anchor = fields.get("assertion_source") or {}
            text, non_empty = read_slice(kb, anchor["file"], anchor["line_start"], anchor["line_end"])
            if not non_empty:
                errors.append(f"{item['fingerprint']}: link 锚点切片为空（不写）")
                continue
            want = quote_sha256_from_slice(text)
            if anchor.get("quote_sha256") != want:
                errors.append(f"{item['fingerprint']}: link 锚点 quote_sha256 不符（建议值 stale，不写）")
                continue
            fields["assertion_source"] = {"file": anchor["file"], "line_start": anchor["line_start"],
                                          "line_end": anchor["line_end"], "quote_sha256": want}
        # 幂等：已存在同身份且同值的影子条目 ⇒ 跳过
        existing = None
        for e in edges:
            if not isinstance(e, dict):
                continue
            if (e.get("type"), e.get("source_id"), (e.get("targets") or [None])[0]) == \
               (item["type"], item["source_id"], item["target_id"]):
                existing = e
                break
        if existing is not None:
            if all(existing.get(k) == v for k, v in fields.items()):
                already += 1
                continue
            errors.append(f"{item['fingerprint']}: sidecar 已存在不同值的同名边条目（拒绝覆盖）")
            continue
        shadow = {"type": item["type"], "source_id": item["source_id"], "targets": [item["target_id"]]}
        shadow.update(fields)
        edges.append(shadow)
        data["edges"] = edges
        save_sidecar(sc_path, data)
        # 产品 writer 会留 .bak；副本演练清理之，避免污染快照/差异面
        bak = sc_path.with_name(sc_path.name + ".bak")
        if bak.is_file():
            bak.unlink()
        after_sha = sha256_file(sc_path)
        files_changed.setdefault(sc_rel, {"rel": sc_rel, "before_sha256": before_sha,
                                          "after_sha256": after_sha, "shadow_edges_added": 0})
        files_changed[sc_rel]["shadow_edges_added"] += 1
        for k in fields:
            key_counts[k] = key_counts.get(k, 0) + 1
        edges_changed.append({"edge_fingerprint": item["fingerprint"], "origin": item["origin"],
                              "type": item["type"], "source_id": item["source_id"],
                              "target_id": item["target_id"], "action": "shadow_edge_added",
                              "keys_added": sorted(fields.keys()),
                              "consumer_visible": False})
    stats = {"shadow_edges_written": len(edges_changed), "already_applied": already,
             "files_changed": len(files_changed), "key_counts": key_counts}
    return {"files": sorted(files_changed.values(), key=lambda x: x["rel"]),
            "edges": edges_changed}, errors, stats


def build_expected_diff(plan: list[dict], diff: dict, stats: dict, corpus: dict) -> dict:
    return {
        "schema": "gue-g5d-expected-diff/v1",
        "consumer_effect": "none",
        "blocker": B1_CONSUMER,
        "blocker_evidence": B1_EVIDENCE,
        "corpus": corpus,
        "write_plan": {"range": 33, "link": 3, "author": 0,
                       "author_note": "作者边本轮按契约 Q2 不写（不写 asserted，也不写 missing）"},
        "files": diff["files"],
        "edges": diff["edges"],
        "key_counts": stats["key_counts"],
        "summary": {
            "shadow_edges_written_this_run": stats["shadow_edges_written"],
            "already_applied_before_this_run": stats["already_applied"],
            "files_changed_this_run": stats["files_changed"],
            "consumer_visible_edges": 0,
            "whitelist_only": True,
            "forbidden_keys_written": [],
        },
        "expected_collect_delta": {"nodes": 0, "edges": 0, "provenance_visible": 0,
                                   "reason": "B1：dedupe 先到先得 + contain/link 每次重派生，sidecar 影子条目被丢弃"},
    }


def validate_plan_anchors(kb: Path, plan: list[dict]) -> list[str]:
    """写前锚点校验（C4）：所有 link 锚点必须可读、非空、quote_sha256 与切片一致；否则整批不写。"""
    errors: list[str] = []
    for item in plan:
        if item["origin"] != "link":
            continue
        anchor = item["proposed_fields"].get("assertion_source") or {}
        text, non_empty = read_slice(kb, anchor.get("file", ""),
                                     anchor.get("line_start"), anchor.get("line_end"))
        if not non_empty:
            errors.append(f"{item['fingerprint']}: link 锚点切片为空（不写）")
            continue
        want = quote_sha256_from_slice(text)
        if anchor.get("quote_sha256") != want:
            errors.append(f"{item['fingerprint']}: link 锚点 quote_sha256 不符（建议值 stale，不写）")
    return errors


def is_fully_applied(kb: Path, plan: list[dict]) -> bool:
    """幂等判定：计划中的影子条目是否已全部存在且值一致（用于第二次写回 diff=0）。"""
    cache: dict[str, dict] = {}
    for item in plan:
        sc_rel = sidecar_rel_for_md(item["file"])
        if sc_rel not in cache:
            scp = kb / sc_rel
            if not scp.is_file():
                return False
            cache[sc_rel] = yaml.safe_load(scp.read_text(encoding="utf-8-sig")) or {}
        edges = cache[sc_rel].get("edges") or []
        hit = None
        for e in edges:
            if isinstance(e, dict) and (e.get("type"), e.get("source_id"),
                                        (e.get("targets") or [None])[0]) == \
               (item["type"], item["source_id"], item["target_id"]):
                hit = e
                break
        if hit is None or any(hit.get(k) != v for k, v in item["proposed_fields"].items()):
            return False
    return True


def measure_counts(kb: Path) -> dict:
    collect_graph_data, DocumentService, *_ = load_product()
    g = collect_graph_data(str(kb))
    from collections import Counter
    svc = DocumentService(kb_path=str(kb))
    v = svc.validate_kb()
    return {"nodes": len(g.get("nodes") or []), "edges": len(g.get("edges") or []),
            "edge_origins": dict(sorted(Counter(e.get("origin") for e in g.get("edges") or []).items())),
            "validate_kb": {k: v.get(k) for k in ("status", "files_checked", "issues_count", "errors", "warnings")}}


def mode_apply(a) -> int:
    kb, out, snap = Path(a.kb).resolve(), Path(a.out).resolve(), (Path(a.snapshot).resolve() if a.snapshot else None)
    gate = safety_gate(kb, a.confirm_copy, snap, writing=not a.dry_run)
    if gate:
        print(f"SAFETY REFUSED: {gate}")
        return 2
    suggestions, sug_corpus, err = load_suggestions(Path(a.suggestions).resolve())
    if err:
        print(f"CONTRACT ERROR: {err}")
        return 3
    if not sug_corpus:
        print("CONTRACT ERROR: 建议缺 corpus 身份")
        return 3
    corpus = corpus_identity(kb)
    if sug_corpus.get("corpus_id") != corpus.get("corpus_id"):
        print(f"CONTRACT ERROR: 语料身份不一致（建议={sug_corpus.get('corpus_id')} 实际={corpus.get('corpus_id')}）")
        return 3
    plan, errors = plan_writes(suggestions, corpus)
    if not a.dry_run and not is_fully_applied(kb, plan):
        snap_err = check_snapshot_matches(kb, snap)
        if snap_err:
            print(f"SNAPSHOT REFUSED: {snap_err}")
            return 4
    if not errors:
        errors.extend(validate_plan_anchors(kb, plan))
    if errors:
        print("RULE CONFLICT（不写）:")
        for e in errors[:20]:
            print(f"  - {e}")
        return 5
    out.mkdir(parents=True, exist_ok=True)
    if a.dry_run:
        tmp = Path(tempfile.mkdtemp(prefix="g5d2-dry-"))
        try:
            work = tmp / "kb"
            shutil.copytree(kb, work)
            diff, errs, stats = apply_plan_to_kb(work, plan)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    else:
        diff, errs, stats = apply_plan_to_kb(kb, plan)
    if errs:
        print("RULE CONFLICT（部分未写/失败）:")
        for e in errs[:20]:
            print(f"  - {e}")
        return 5
    report = build_expected_diff(plan, diff, stats, corpus)
    (out / "expected-diff.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                                            encoding="utf-8")
    print(f"OK apply: shadow_written={stats['shadow_edges_written']} already={stats['already_applied']} "
          f"files={stats['files_changed']} keys={stats['key_counts']} consumer_visible=0")
    print(f"  → {out / 'expected-diff.json'}")
    return 0


def mode_positive_control(a) -> int:
    kb, out_path = Path(a.kb).resolve(), Path(a.out).resolve()
    gate = safety_gate(kb, a.confirm_copy, None, writing=True, require_snapshot=False)
    if gate:
        print(f"SAFETY REFUSED: {gate}")
        return 2
    collect_graph_data, DocumentService, load_sidecar, save_sidecar = load_product()
    suggestions, _, err = load_suggestions(Path(a.suggestions).resolve())
    if err:
        print(f"CONTRACT ERROR: {err}")
        return 3
    author = [s for s in suggestions if s.get("origin") == "sidecar_edge"]
    if not author:
        print("CONTRACT ERROR: 无作者边建议")
        return 3
    item = sorted(author, key=lambda s: s["edge_fingerprint"])[0]
    edge = item["edge"]
    sc_rel = sidecar_rel_for_md(edge["file"])
    sc_path = kb / sc_rel
    data = yaml.safe_load(sc_path.read_text(encoding="utf-8-sig"))
    edges = data.get("edges") or []
    target = None
    for e in edges:
        if (e.get("type"), e.get("source_id"), (e.get("targets") or [None])[0]) == \
           (edge["type"], edge["source_id"], edge["target_id"]):
            target = e
            break
    if target is None:
        print(f"RULE CONFLICT: 作者边不在 sidecar edges[]: {sc_rel}")
        return 5
    g0 = collect_graph_data(str(kb))
    before = {k: dict(v) for k, v in _edge_index(g0).items()}
    # 源 KP range → 真实切片
    nodes = {n["id"]: n for n in g0.get("nodes") or []}
    node = nodes.get(edge["source_id"])
    if not node or not node.get("start_line") or not node.get("end_line"):
        print("RULE CONFLICT: 作者边源 KP 无 range 可作锚点")
        return 5
    text, non_empty = read_slice(kb, node["file"], node["start_line"], node["end_line"])
    if not non_empty:
        print("RULE CONFLICT: 正文切片为空")
        return 5
    anchor = {"file": node["file"], "line_start": node["start_line"],
              "line_end": node["end_line"], "quote_sha256": quote_sha256_from_slice(text)}
    target["provenance_state"] = "asserted"
    target["derived_by"] = "author"
    target["assertion_source"] = anchor
    save_sidecar(sc_path, data)
    bak = sc_path.with_name(sc_path.name + ".bak")
    if bak.is_file():
        bak.unlink()
    g1 = collect_graph_data(str(kb))
    after = {k: dict(v) for k, v in _edge_index(g1).items()}
    fp = item["edge_fingerprint"]
    key = (edge["type"], edge["source_id"], edge["target_id"])
    got = after.get(key)
    keys_written = ["derived_by", "provenance_state", "assertion_source"]
    present = {k: got.get(k) for k in keys_written if got and k in got} if got else {}
    values_ok = bool(got) and all(got.get(k) == v for k, v in
                                  (("derived_by", "author"), ("provenance_state", "asserted"))) \
        and got.get("assertion_source") == anchor
    other_changed = [k for k in before if k != key and before[k] != after.get(k)]
    report = {
        "schema": "gue-g5d-positive-control/v1",
        "copy_only": True,
        "caveat": "copy-only positive control：仅证明作者边 assertion_source 会被产品消费；"
                  "本轮生产写回仍不写作者边 asserted（契约 Q2），本文件不并入 expected-diff。",
        "edge_fingerprint": fp,
        "canonical_id": item["canonical_id"],
        "sidecar": sc_rel,
        "anchor": anchor,
        "keys_written": keys_written,
        "keys_seen_in_collect_output": present,
        "all_written_values_roundtrip": values_ok,
        "whitelist_8_state": {k: ("present" if got and k in got else "absent") for k in PROVENANCE_KEYS_8},
        "nodes_before": len(g0.get("nodes") or []), "edges_before": len(g0.get("edges") or []),
        "nodes_after": len(g1.get("nodes") or []), "edges_after": len(g1.get("edges") or []),
        "other_61_edges_unchanged": not other_changed,
        "changed_other_edges": other_changed,
        "consumer_effect": "positive-control-only（真实消费路径）",
    }
    ok = values_ok and not other_changed and len(g0.get("edges") or []) == 62 == len(g1.get("edges") or [])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{'OK' if ok else 'FAIL'} positive-control: {fp[:12]}… "
          f"keys={present.keys()} values_ok={values_ok} other_unchanged={not other_changed}")
    if not ok:
        return 1
    return 0


def _edge_index(g: dict) -> dict:
    idx = {}
    for e in g.get("edges") or []:
        idx[(e["type"], e["source_id"], e["targets"][0])] = e
    return idx


def main() -> int:
    ensure_utf8_stdio()
    ap = argparse.ArgumentParser(description="G5d-2 写回器（仅副本演练）")
    ap.add_argument("--kb", required=True)
    ap.add_argument("--out", required=True, help="输出 expected-diff.json 的目录（必须显式给出；禁止默认覆盖）")
    ap.add_argument("--suggestions", default=str(SUGGESTIONS))
    ap.add_argument("--snapshot", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--confirm-copy", action="store_true")
    ap.add_argument("--positive-control", action="store_true")
    a = ap.parse_args()
    if a.positive_control:
        return mode_positive_control(a)
    return mode_apply(a)


if __name__ == "__main__":
    sys.exit(main())
