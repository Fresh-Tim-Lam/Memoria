"""G5b expected-delta 生成器：从基线 + 实现后的 collect 输出，自动算出"新增字段增量"。

## 为什么有这个脚本（裁决 2 硬要求）

expected-delta.json **不许手写** —— 否则等于把期望值写成实现输出（自证循环）。
本脚本的职责是：拿【改动前基线 collect-before.json】和【改动后当前 collect 输出】，
自动 diff 出"每条边新增了哪些 provenance 键"，逐边落入 expected-delta.json。

生成后，回归闸用它做"新增字段增量 == expected-delta 精确匹配"校验
（多一个键 / 少一个键都 FAIL）。

## 只读，不写任何 KB。

用法：
  python scripts/agent/g5_gen_expected_delta.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASELINE = REPO / "artifacts" / "agent" / "verify" / "graph-utility" / "g5b" / "baseline" / "collect-before.json"
WORKING = REPO / "artifacts" / "agent" / "verify" / "graph-utility" / "g5b" / "working" / "数字通信原理"
OUT = REPO / "artifacts" / "agent" / "verify" / "graph-utility" / "g5b" / "baseline" / "expected-delta.json"

#: base 字段（G5b-1 口径 A，Lead 确认）；新增 provenance 键 = 全部键 - base - targets 展开键
BASE_KEYS = ("type", "source_id", "targets", "relevance", "derived", "origin", "file", "line", "no_build")

#: provenance 键（白名单，与 edge_derivation.SIDECAR_EDGE_PROVENANCE_KEYS 一致）
PROVENANCE_KEYS = (
    "derived_by", "provenance_state", "assertion_source", "instances",
    "generator_version", "valid_from", "valid_to", "confidence",
)


def _edge_identity(edge: dict) -> tuple:
    """边的稳定身份：用于把基线与当前的同一条边配对。"""
    return (edge.get("type"), edge.get("source_id"), tuple(edge.get("targets") or []))


def main() -> int:
    if not BASELINE.is_file():
        print(f"[NOT_RUN] 基线不存在：{BASELINE}")
        return 2
    if not WORKING.is_dir():
        print(f"[NOT_RUN] working 副本不存在：{WORKING}")
        return 2

    sys.path.insert(0, str(REPO / "src"))
    from memoria.graph.collector import collect_graph_data

    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    before_edges = baseline.get("edges") or []
    after_edges = collect_graph_data(str(WORKING)).get("edges") or []

    # 按身份建索引（同一个 (type, source, targets) 只会出现一次，因为 dedupe 保证）
    before_by_id = {_edge_identity(e): e for e in before_edges}
    after_by_id = {_edge_identity(e): e for e in after_edges}

    delta: list[dict] = []
    base_diff: list[str] = []

    # 1. base 字段逐边一致（口径 A）
    all_ids = sorted(set(before_by_id) | set(after_by_id), key=str)
    for ident in all_ids:
        b = before_by_id.get(ident)
        a = after_by_id.get(ident)
        if b is None or a is None:
            base_diff.append(f"边 {ident} 只在一侧存在（基线/当前）")
            continue
        for key in BASE_KEYS:
            bv = b.get(key)
            av = a.get(key)
            # targets 是 list，比较稳定顺序（dedupe 后有序）
            if bv != av:
                base_diff.append(f"边 {ident} 键 {key!r} 变：{bv!r} → {av!r}")

    # 2. 新增 provenance 键（逐边）
    for ident in all_ids:
        b = before_by_id.get(ident)
        a = after_by_id.get(ident)
        if b is None or a is None:
            continue
        added = {}
        for key in PROVENANCE_KEYS:
            if key in a and key not in b:
                added[key] = a[key]
            elif key in a and key in b:
                # 键两侧都有（理论上旧语料不应有，但若出现也算"非新增"）
                pass
        if added:
            delta.append({
                "identity": {"type": ident[0], "source_id": ident[1], "targets": list(ident[2])},
                "added_keys": added,
            })

    # 3. 校验：新增键必须全在 PROVENANCE_KEYS 白名单内（防实现偷偷加别的键）
    unknown_added = []
    for ident in all_ids:
        a = after_by_id.get(ident)
        b = before_by_id.get(ident)
        if a is None or b is None:
            continue
        added_keys = set(a.keys()) - set(b.keys())
        rogue = added_keys - set(PROVENANCE_KEYS)
        if rogue:
            unknown_added.append({"identity": list(ident), "rogue_keys": sorted(rogue)})

    payload = {
        "schema": "g5b-expected-delta/v1",
        "generated_from": {
            "baseline": str(BASELINE),
            "working": str(WORKING),
        },
        "counts": {
            "before_edges": len(before_edges),
            "after_edges": len(after_edges),
            "delta_edges": len(delta),
            "base_diff": len(base_diff),
        },
        "base_keys": list(BASE_KEYS),
        "provenance_keys": list(PROVENANCE_KEYS),
        "base_diff": base_diff,          # 应为空；非空 = 口径 A 已被破坏
        "unknown_added_keys": unknown_added,
        "delta": delta,
    }

    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] expected-delta 已生成：{OUT}")
    print(f"  边数：before={len(before_edges)} after={len(after_edges)}")
    print(f"  有新增键的边：{len(delta)}")
    print(f"  base diff 数：{len(base_diff)}  （必须为 0）")
    print(f"  白名单外新增键：{len(unknown_added)}  （必须为 0）")

    # 按 origin 汇总（便于人读）
    from collections import Counter
    db_counter = Counter()
    gv_counter = Counter()
    for d in delta:
        for k, v in d["added_keys"].items():
            if k == "derived_by":
                db_counter[v] += 1
            elif k == "generator_version":
                gv_counter[v] += 1
    print(f"  derived_by 增量：{dict(db_counter)}")
    print(f"  generator_version 增量：{dict(gv_counter)}")

    if base_diff or unknown_added:
        print("[WARN] base diff 或白名单外键非空，请在回归闸里 FAIL")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
