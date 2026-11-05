#!/usr/bin/env python
"""C0 GATE-RET 可执行契约：三层评测 + 分型 gate + graph soft-until-pilot。

契约（C0a / C0-corpus-v1.md §3）：
- 唯一命令：本脚本；内部调用既有 `scripts/verify/eval-retrieval.py`（不复制指标实现）。
- P0（阻断）：keyword/vector/hybrid 适用分型全部达 S9 provisional 阈值 +
  2× 确定性；`NOT_APPLICABLE` 不参与。
- graph：仅当库 semantic_edges>0 时适用；pilot 前阈值 **soft**（报告但不阻断 exit）；
  0 命中/determinism 失败可见记录，pilot 达标后再转硬门禁。
- 产物：`artifacts/agent/verify/graph/corpus/C0-GATE-RET.json`；
  `json_sha256 = sha256(canonical(payload without json_sha256))`。
- exit：0=P0 PASS（graph soft 可非 PASS）；1=P0 FAIL/执行失败；2=用法错误。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
EVAL = REPO / "scripts" / "verify" / "eval-retrieval.py"
DEFAULT_OUT = REPO / "artifacts" / "agent" / "verify" / "graph" / "corpus"
NON_GRAPH_TYPES = ("keyword", "vector", "hybrid")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_bytes(obj: object) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _gate_ok(type_breakdown: dict, applicable: list[str], qtype: str) -> bool:
    if qtype not in applicable or qtype not in type_breakdown:
        return True
    gates = type_breakdown[qtype].get("_gates")
    if gates is None:
        return True
    return all(v for v in gates.values() if v is not None)


def run(kb: Path, golden: Path, out_path: Path, *, graph_soft: bool = True) -> dict:
    if not EVAL.is_file():
        raise RuntimeError(f"eval 脚本缺失：{EVAL}")
    with tempfile.TemporaryDirectory(prefix="c0-gate-ret-") as td:
        raw = Path(td) / "eval.json"
        cmd = [sys.executable, str(EVAL), "--kb", str(kb), "--golden", str(golden), "--out", str(raw)]
        cp = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, encoding="utf-8")
        if not raw.is_file():
            raise RuntimeError(f"eval 未产出 JSON（exit={cp.returncode}）：{cp.stderr[-800:]}")
        payload = json.loads(raw.read_text(encoding="utf-8"))

    applicable = list(payload.get("applicable_types") or [])
    tb = dict(payload.get("type_breakdown") or {})
    type_gates = dict(payload.get("type_gates") or {})
    for qtype, gates in type_gates.items():
        tb.setdefault(qtype, {})["_gates"] = gates
    non_graph_ok = all(_gate_ok(tb, applicable, q) for q in NON_GRAPH_TYPES)
    det_ok = bool((payload.get("determinism") or {}).get("2x"))
    p0_ok = non_graph_ok and det_ok

    graph = tb.get("graph") or {}
    graph_applicable = "graph" in applicable
    graph_pass = None
    if graph_applicable:
        graph_pass = all(v for v in (type_gates.get("graph") or {}).values() if v is not None)
        if not graph_soft:
            p0_ok = p0_ok and bool(graph_pass)
    # 清理内部字段，避免污染 type_breakdown 的冻结形状
    for v in tb.values():
        v.pop("_gates", None)

    result = {
        "gate": "C0-GATE-RET",
        "semantics": "typed P0 (keyword/vector/hybrid) + graph soft-until-pilot",
        "inputs": {
            "kb": str(kb), "golden": str(golden),
            "golden_sha256": sha256_file(golden),
            "kb_edition_sha": payload.get("golden_edition"),
        },
        "command": " ".join(str(x) for x in cmd),
        "p0": {
            "ok": p0_ok,
            "non_graph_ok": non_graph_ok,
            "determinism_2x": det_ok,
            "blocking_types": list(NON_GRAPH_TYPES),
        },
        "graph": {
            "applicable": graph_applicable,
            "status": graph.get("status"),
            "reason": graph.get("reason"),
            "pass": graph_pass,
            "policy": "soft_until_pilot" if graph_soft else "hard",
        },
        "metrics": payload.get("metrics"),
        "type_breakdown": tb,
        "applicable_types": applicable,
        "not_applicable_types": payload.get("not_applicable_types"),
        "provisional": True,
        "exit_code": 0 if p0_ok else 1,
        "generated_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
    }
    # 去掉短暂字段后计算 JSON sha（可复算）
    core = {k: v for k, v in result.items() if k not in {"generated_at", "json_sha256", "exit_code"}}
    result["json_sha256"] = sha256_bytes(canonical_bytes(core))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="C0 GATE-RET executable contract")
    ap.add_argument("--kb", required=True, help="KB 根目录（含 .memoria/）")
    ap.add_argument("--golden", required=True, help="edition-pinned golden JSON")
    ap.add_argument("--out", default=str(DEFAULT_OUT / "C0-GATE-RET.json"))
    ap.add_argument("--hard-graph", action="store_true", help="pilot 达标后把 graph 转硬门禁")
    args = ap.parse_args(argv)
    kb, golden = Path(args.kb), Path(args.golden)
    if not kb.is_dir() or not golden.is_file():
        print(json.dumps({"ok": False, "error": "usage", "message": "kb/golden 不存在"},
                         ensure_ascii=False), file=sys.stderr)
        return 2
    try:
        res = run(kb, golden, Path(args.out), graph_soft=not args.hard_graph)
        print(json.dumps(res, ensure_ascii=False, indent=2, sort_keys=True))
        return int(res["exit_code"])
    except Exception as exc:  # noqa: BLE001 —— 门禁可见失败
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)},
                         ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
