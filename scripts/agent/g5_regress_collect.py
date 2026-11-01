"""G5b 回归闸：旧语料 collect_graph_data() 逐边一致（diff=0）+ 证红（task-280 M5）。

## 职责

1. `--baseline`：跑一次 collect_graph_data()，落盘基线 JSON（含语料身份）。
2. `--verify`：再跑一次，与基线逐边对比，diff≠0 ⇒ exit 1。
3. 证红：`--verify --tamper` 会**人为改基线一条边的 relevance** 再对比，
   用来证明闸"能捕获 diff"（不是写完就绿的假守卫）。

## 为什么先写这个（不是先改 M1/M2/M3）

G5b-1 是硬验收第一关："旧语料 collect 输出与改动前逐边一致，且先证红"。
必须先有这把"改动前基线 + 注入必红"的尺子，才能证明后续改 M2/M3 时没破坏边生成逻辑。

## 边界

- 只读 frozen 副本的 working 复制；绝不写 frozen 原目录、绝不写用户库。
- 基线 JSON 只读对比；`--tamper` 改的是**内存副本**，不落盘。

用法：
  python scripts/agent/g5_regress_collect.py --baseline
  python scripts/agent/g5_regress_collect.py --verify
  python scripts/agent/g5_regress_collect.py --verify --tamper   # 必须 exit 1
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

WORKING = REPO / "artifacts" / "agent" / "verify" / "graph-utility" / "g5b" / "working" / "数字通信原理"
BASELINE = REPO / "artifacts" / "agent" / "verify" / "graph-utility" / "g5b" / "baseline" / "collect-before.json"
EXPECTED_DELTA = REPO / "artifacts" / "agent" / "verify" / "graph-utility" / "g5b" / "baseline" / "expected-delta.json"
MANIFEST = REPO / "artifacts" / "agent" / "verify" / "debate" / "kg-retrieval" / "round2" / "frozen" / "MANIFEST.json"

#: base 字段（G5b-1 口径 A，Lead 确认键名 targets 为数组）
BASE_KEYS = ("type", "source_id", "targets", "relevance", "derived", "origin", "file", "line", "no_build")

#: provenance 键（与 edge_derivation.SIDECAR_EDGE_PROVENANCE_KEYS 一致）
PROVENANCE_KEYS = (
    "derived_by", "provenance_state", "assertion_source", "instances",
    "generator_version", "valid_from", "valid_to", "confidence",
)


def _collect(kb_path: str) -> dict:
    from memoria.graph.collector import collect_graph_data

    return collect_graph_data(kb_path)


def _canonical_edge(edge: dict) -> dict:
    """把边规范成可比较的稳定序（键排序 + 内容不变形），避免 dict 顺序/浮点噪声干扰 diff。"""
    e = copy.deepcopy(edge)
    # 边对象是 dict；排序键做字节级稳定比较
    if isinstance(e, dict):
        return _stable(e)
    return e


def _stable(obj):
    if isinstance(obj, dict):
        return {k: _stable(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, list):
        return [_stable(x) for x in obj]
    return obj


def _identity(baseline: dict) -> dict:
    """从 baseline 提取语料身份（MANIFEST sha / frozen_at / build_state）。"""
    man = {}
    if MANIFEST.is_file():
        try:
            man = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {
        "source": man.get("source"),
        "frozen_at": man.get("frozen_at"),
        "manifest_sha256": _sha_of_file(MANIFEST) if MANIFEST.is_file() else None,
        "build_state": "pre_build",
    }


def _sha_of_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_baseline() -> None:
    if not WORKING.is_dir():
        print(f"[NOT_RUN] working 副本不存在：{WORKING}")
        print("  先复制 frozen：robocopy frozen/数字通信原理 g5b/working/数字通信原理 /E")
        raise SystemExit(2)
    out = _collect(str(WORKING))
    payload = {
        "schema": "g5b-collect-baseline/v1",
        "identity": _identity(out),
        "status": out.get("status"),
        "node_count": len(out.get("nodes") or []),
        "edge_count": len(out.get("edges") or []),
        "edges": [_canonical_edge(e) for e in (out.get("edges") or [])],
        "nodes": [_canonical_edge(n) for n in (out.get("nodes") or [])],
    }
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 基线已落盘：{BASELINE}")
    print(f"  nodes={payload['node_count']}  edges={payload['edge_count']}")
    print(f"  语料身份：{payload['identity']['frozen_at']} / {payload['identity']['manifest_sha256'][:16]}…")


def _edge_identity(edge: dict) -> tuple:
    return (edge.get("type"), edge.get("source_id"), tuple(edge.get("targets") or []))


def _verify(tamper: bool) -> None:
    if not BASELINE.is_file():
        print("[NOT_RUN] 基线不存在，先跑 --baseline")
        raise SystemExit(2)
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    baseline_edges = baseline.get("edges") or []

    if tamper:
        # 证红：改基线里第一条边的 relevance（内存副本，不落盘）
        if not baseline_edges:
            print("[NOT_RUN] 基线无边，无法证红")
            raise SystemExit(2)
        baseline_edges = copy.deepcopy(baseline_edges)
        baseline_edges[0]["relevance"] = 0.999 if baseline_edges[0].get("relevance") != 0.999 else 0.5
        print("[TAMPER] 已人为改基线第 1 条边的 relevance（内存副本）")

    out = _collect(str(WORKING))
    current_edges = list(out.get("edges") or [])

    before_by_id = {_edge_identity(e): e for e in baseline_edges}
    after_by_id = {_edge_identity(e): e for e in current_edges}

    # ── 口径 A：base 9 键逐边一致 ────────────────────────────────
    base_diffs: list[str] = []
    all_ids = sorted(set(before_by_id) | set(after_by_id), key=str)
    for ident in all_ids:
        b = before_by_id.get(ident)
        a = after_by_id.get(ident)
        if b is None or a is None:
            base_diffs.append(f"边 {ident} 只在一侧存在")
            continue
        for key in BASE_KEYS:
            if b.get(key) != a.get(key):
                base_diffs.append(f"边 {ident} 键 {key!r}：{b.get(key)!r} → {a.get(key)!r}")

    # ── 口径 B：新增字段增量 == expected-delta 精确匹配 ────────────
    delta_diffs: list[str] = []
    expected = None
    if EXPECTED_DELTA.is_file():
        expected = json.loads(EXPECTED_DELTA.read_text(encoding="utf-8"))
        exp_delta = expected.get("delta") or []
        exp_by_id = {
            (d["identity"]["type"], d["identity"]["source_id"], tuple(d["identity"]["targets"])): d["added_keys"]
            for d in exp_delta
        }
        # 1. 当前新增键集合必须 == expected（多/少都 FAIL）
        actual_added: dict[tuple, dict] = {}
        for ident in all_ids:
            b = before_by_id.get(ident)
            a = after_by_id.get(ident)
            if b is None or a is None:
                continue
            added = {}
            for key in PROVENANCE_KEYS:
                if key in a and key not in b:
                    added[key] = a[key]
            if added:
                actual_added[ident] = added

        # 逐边精确匹配
        for ident in sorted(set(exp_by_id) | set(actual_added), key=str):
            exp = exp_by_id.get(ident)
            act = actual_added.get(ident)
            if exp != act:
                delta_diffs.append(
                    f"边 {ident} 新增键不符：expected={exp} actual={act}"
                )
        # 白名单外新增键（防实现偷偷加别的键）
        for ident in all_ids:
            b = before_by_id.get(ident)
            a = after_by_id.get(ident)
            if b is None or a is None:
                continue
            rogue = (set(a.keys()) - set(b.keys())) - set(PROVENANCE_KEYS)
            if rogue:
                delta_diffs.append(f"边 {ident} 出现白名单外的新键：{sorted(rogue)}")
    else:
        delta_diffs.append("expected-delta.json 不存在，先跑 g5_gen_expected_delta.py")

    # ── 汇总 ─────────────────────────────────────────────────────
    if base_diffs:
        print(f"[口径A FAIL] base 字段不一致 {len(base_diffs)} 处：")
        for d in base_diffs:
            print(f"  ✗ {d}")
    else:
        print(f"[口径A OK] base 9 键逐边一致（diff=0，{len(before_by_id)} 条边）")

    if delta_diffs:
        print(f"[口径B FAIL] 新增字段增量不符 {len(delta_diffs)} 处：")
        for d in delta_diffs:
            print(f"  ✗ {d}")
    else:
        exp_n = len((expected or {}).get("delta") or [])
        print(f"[口径B OK] 新增字段增量 == expected-delta 精确匹配（{exp_n} 条边有增量）")

    if base_diffs or delta_diffs:
        raise SystemExit(1)
    print(f"[OK] G5b 回归通过：nodes={len(out.get('nodes') or [])} edges={len(out.get('edges') or [])}")
    raise SystemExit(0)


def main() -> int:
    ap = argparse.ArgumentParser(description="G5b collect 回归闸")
    ap.add_argument("--baseline", action="store_true", help="落基线")
    ap.add_argument("--verify", action="store_true", help="跑当前 collect 并与基线对比")
    ap.add_argument("--tamper", action="store_true", help="证红：人为改基线再对比（必须 exit 1）")
    args = ap.parse_args()

    if args.baseline:
        _write_baseline()
        return 0
    if args.verify:
        _verify(tamper=args.tamper)
        return 0
    ap.print_help()
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
