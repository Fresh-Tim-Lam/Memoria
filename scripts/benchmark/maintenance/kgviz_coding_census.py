#!/usr/bin/env python
"""task-149｜可视化研讨会 Phase 1 —— 可跑的最小机检（不是设计，是真能跑）

本脚本做三件事，全部**现在可跑**（无外部依赖、无埋点需求）：

  ① **视觉编码现状 census**：把 graph-*.js 里"哪些视觉通道被使用、怎么映射"机读出来
     → 输出每个通道：是否启用 / 映射函数 / 取值范围 / 作用域（galaxy-only？）

  ② **节点大小可辨性计算**：给定当前映射（6px→9px）与候选映射，
     按"屏幕最小可辨差异"算 **能分出几档**（Webber 判据：Δ ≥ 3px 才可靠区分）

  ③ **机检：提案质量自检器**（本研讨会的验收工具，先证明它能跑，且能报红）

用法:
    python scripts/benchmark/maintenance/kgviz_coding_census.py [--json out.json]
    python scripts/benchmark/maintenance/kgviz_coding_census.py --selfcheck
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
os.environ.setdefault("MEMORIA_CONFIG_DIR", tempfile.mkdtemp(prefix="memoria-cfg-"))

JS_DIR = os.path.join(REPO, "src", "memoria", "ui", "static", "app", "js")


# ─────────────────────────────────────────────────────────────
# ① 视觉编码现状 census（读代码，不是读文档）
# ─────────────────────────────────────────────────────────────

def read(p: str) -> str:
    try:
        return open(p, encoding="utf-8").read()
    except Exception:
        return ""


def census_node_radius() -> dict:
    """节点大小编码：是否启用、映射函数、取值范围、作用域"""
    v2 = read(os.path.join(JS_DIR, "graph-view-2d.js"))
    v3 = read(os.path.join(JS_DIR, "graph-view-3d.js"))
    out = {}

    # 默认半径
    m = re.search(r"nodeRadius:\s*([\d.]+)", v2)
    base_2d = float(m.group(1)) if m else None
    m3 = re.search(r"nodeRadius:\s*([\d.]+)", v3)
    base_3d = float(m3.group(1)) if m3 else None
    out["base_radius_2d"] = base_2d
    out["base_radius_3d"] = base_3d

    # 2D：度数 → 半径的映射表达式（关键：找到 r * (1 + ratio * X) 这类）
    scale = re.search(r"r\s*=\s*r\s*\*\s*\(\s*1\s*\+\s*ratio\s*\*\s*([\d.]+)\s*\)", v2)
    out["2d_degree_scale_factor"] = float(scale.group(1)) if scale else None
    # 作用域：gStats 只在 galaxy 时非 null？
    out["2d_scope_galaxy_only"] = bool(
        re.search(r"const\s+gStats\s*=\s*galaxy\s*\?", v2)
    )
    # galaxy 判定
    out["2d_galaxy_gate"] = bool(re.search(r'opts\.graphStyle\s*===\s*"galaxy"', v2))

    # 3D 是否也有同样的度数缩放（半径）——注意：3D 只按 ratio 改颜色，不改半径
    v3_radius_by_deg = bool(
        re.search(r"nodeRadius\s*\*\s*\(\s*1\s*\+\s*ratio", v3)
    )
    out["3d_has_degree_radius_scale"] = v3_radius_by_deg
    out["3d_has_degree_color_only"] = bool(
        re.search(r"galaxyColor3D\(\s*ratio\s*\)", v3)
    )

    # 计算实际取值范围
    if base_2d is not None and out.get("2d_degree_scale_factor"):
        k = out["2d_degree_scale_factor"]
        out["2d_radius_range"] = [base_2d, round(base_2d * (1 + k), 2)]
        out["2d_radius_delta_px"] = round(base_2d * k, 2)
    return out


def census_other_channels() -> dict:
    """颜色 / 形状 / 标签 / 深度线索"""
    eng = read(os.path.join(JS_DIR, "graph-engine.js"))
    lbl = read(os.path.join(JS_DIR, "graph-label.js"))
    v3 = read(os.path.join(JS_DIR, "graph-view-3d.js"))
    v2 = read(os.path.join(JS_DIR, "graph-view-2d.js"))
    st = read(os.path.join(JS_DIR, "graph-settings.js"))

    out = {}

    # 颜色：边颜色按类型
    m = re.search(r"EDGE_COLORS\s*=\s*\{(.*?)\}", eng, re.S)
    out["edge_color_by_type"] = bool(m)
    if m:
        out["edge_color_keys"] = re.findall(r"(\w+)\s*:", m.group(1))

    # 节点颜色：是否按度数映射（galaxyNodeColor2D）
    out["node_color_by_degree"] = "galaxyNodeColor2D" in v2
    out["node_color_scope_galaxy_only"] = bool(
        re.search(r"galaxyNodeColor2D\(ratio\)", v2) and re.search(r"galaxy\s*\?", v2)
    )

    # 形状：搜索 ellipse/rect/polygon 等非圆绘制
    out["node_shape_variants"] = bool(
        re.search(r"ctx\.(ellipse|rect|polygon|triangle)", v2)
    )

    # 标签
    out["label_mode_default"] = (re.search(r'labelMode:\s*"(\w+)"', st) or [None, None])[1]
    m2 = re.search(r"labelMaxLen:\s*(\d+)", st)
    out["label_max_len"] = int(m2.group(1)) if m2 else None
    out["label_smart_available"] = bool(re.search(r"smart:\s*\{[^}]*available:\s*true", lbl))
    out["label_modes_available"] = re.findall(
        r"(\w+):\s*\{\s*labelKey:[^}]*available:\s*(true|false)", lbl
    )

    # 3D 深度线索：fog（雾）是最强的深度提示
    out["3d_fog"] = bool(re.search(r"\bfog\b|FogExp2|Fog\(", v3))
    out["3d_depth_opacity"] = bool(re.search(r"opacity\x20*=|material\.opacity", v3))
    # 3D 是否按距离缩放节点
    out["3d_distance_scaling"] = bool(
        re.search(r"distanceTo|length\(\)\s*\*", v3)
    )
    return out


def census_telemetry() -> dict:
    """现有埋点：可视化交互是否有**统计消费**（不是"有没有 handler"）

    2026-10-25 修正：初版把 `on("nodeClick", cb)` 记为 consume=True，有歧义。
    真实情况：回调做的是 jumpToTarget（导航），**没有任何统计/持久化记录**。
    ⇒ 字段改名为 has_handler_not_stats，并单独判 has_graph_stats。
    """
    app = read(os.path.join(JS_DIR, "app.js"))
    v2 = read(os.path.join(JS_DIR, "graph-view-2d.js"))
    v3 = read(os.path.join(JS_DIR, "graph-view-3d.js"))
    out = {}
    out["emit_nodeClick"] = ("nodeClick" in v2) or ("nodeClick" in v3)
    out["has_nodeClick_handler"] = bool(re.search(r'on\(\s*"nodeClick"', app))
    # 真正的统计/持久化（排除 UI settings 持久化）
    stat_pat = r"(graph_nav|graphStats|graphTelemetry|trackGraph|analytics)"
    out["has_graph_stats"] = bool(re.search(stat_pat, app, re.I))
    out["emit_edgeClick"] = ("edgeClick" in v2) or ("edgeClick" in v3)
    out["emit_zoom"] = bool(re.search(r'_emit\(\s*"zoom"', v2 + v3))
    # 注意：这是"节点 hover"事件，不是"标签 hover"
    out["emit_node_hover"] = bool(re.search(r'_emit\(\s*"hover"', v2 + v3))
    out["emit_label_hover"] = bool(re.search(r'_emit\(\s*"labelHover"', v2 + v3))
    # 图停留时长：必须找"图相关"的 duration，不是 toast 动画的 duration
    out["graph_dwell_tracked"] = bool(
        re.search(r"(graphDwell|graphVisitDuration|graphOpenAt|graphSessionStart)", app)
    )
    return out


# ─────────────────────────────────────────────────────────────
# ② 节点大小可辨性（离散档位计算）
# ─────────────────────────────────────────────────────────────

# Webber (2009) / Cleveland-McGill 的"大小通道"可辨性经验：面积差异需 ≥ ~20%，
# 直径差异需 ≥ ~3px 才能在单次注视下可靠区分（这是保守取法，需 A/B 验证）
MIN_DELTA_PX = 3.0
MIN_RATIO = 0.20


def discriminable_tiers(r_min: float, r_max: float) -> dict:
    """给定半径范围，算能分出几档（按直径差 ≥3px 且比例 ≥20% 的保守约束）"""
    if r_max <= r_min:
        return {"tiers": 1, "r_values": [r_min], "spacing_px": 0,
                "note": "范围为零 ⇒ 只能 1 档"}
    tiers = 1
    r = r_min
    values = [round(r, 2)]
    while True:
        step = max(MIN_DELTA_PX, r * MIN_RATIO)      # 直径差（半径步长）
        nr = r + step
        if nr > r_max + 1e-9:
            break
        values.append(round(nr, 2))
        tiers += 1
        r = nr
        if tiers > 12:
            break
    return {
        "tiers": tiers,
        "r_values": values,
        "spacing_px": round(max(MIN_DELTA_PX, r_min * MIN_RATIO), 2),
        "constraint": f"半径步长 ≥ max({MIN_DELTA_PX}px, {int(MIN_RATIO*100)}%·r)",
        "note": "3px = 保守下限，需 A/B 判读验证；真实阈值可能更低（2px）或更高（4px）",
    }


# ─────────────────────────────────────────────────────────────
# ③ 提案质量自检器（本研讨会验收工具，先证明能报红）
# ─────────────────────────────────────────────────────────────

PROPOSAL_CHECKS = [
    ("C1_has_evidence", r"ev:(file|bench|measure|commit|spec)"),
    ("C2_has_falsifier", r"撤回|falsifier|则不成立"),
    ("C3_has_not_doing", r"not_doing|明确不做|不做："),
    ("C4_has_unknowns", r"unknowns|未知"),
    ("C5_threshold_has_source", r"(阈值|判据).{0,200}(ev:|来源|实测|待测|无基线)"),
    # C6 修正（2026-10-26）：初版是 (多数|一致).{0,300}…，但"一致"在中文里大量用于
    # 无关语义（"重复2次一致"、"与主题一致"）⇒ 对干净文档误报。
    # 改为只匹配**主张性共识措辞**，要求同一段内出现独立根数。
    ("C6_majority_has_roots",
     r"(多数认为|多数共识|多方一致认为|三方共识|四方共识|全体一致|一致认为)"
     r".{0,300}(independent_roots|独立根)"),
]


def check_proposal(path: str) -> dict:
    txt = read(path)
    res = {}
    for name, pat in PROPOSAL_CHECKS:
        hits = len(re.findall(pat, txt, re.S))
        res[name] = {"pass": hits > 0, "hits": hits}
    all_pass = all(v["pass"] for v in res.values())
    return {"file": os.path.basename(path), "pass": all_pass, "checks": res}


def selfcheck() -> int:
    """必红 fixture：造一份缺项提案，验证检查器会报红；再造一份合规的，验证报绿"""
    tmp = tempfile.mkdtemp()
    bad = os.path.join(tmp, "PROPOSAL-bad.md")
    good = os.path.join(tmp, "PROPOSAL-good.md")
    open(bad, "w", encoding="utf-8").write("# 坏提案\n只有主张，没有证据也没有撤回条件。\n")
    open(good, "w", encoding="utf-8").write(
        "# 好提案\n"
        "主张 X。ev:file:src/memoria/ui/static/app/js/graph-view-2d.js#L631\n"
        "若观察到 Y 则不成立（撤回条件）。\n"
        "## not_doing\n不做 Z\n## unknowns\nU1 未知\n"
        "阈值：3px，来源=实测待补\n"
        "多数认为其合理（independent_roots=2）\n"
    )
    rb = check_proposal(bad)
    rg = check_proposal(good)
    print("=== 自检：必红 fixture ===")
    print(f"  坏提案 pass={rb['pass']}  (期望 False)")
    for k, v in rb["checks"].items():
        print(f"    {k}: {'PASS' if v['pass'] else 'FAIL'} (hits={v['hits']})")
    print(f"  好提案 pass={rg['pass']}  (期望 True)")
    for k, v in rg["checks"].items():
        if not v["pass"]:
            print(f"    ⚠️ {k}: FAIL (hits={v['hits']})")
    ok = (rb["pass"] is False) and (rg["pass"] is True)
    print()
    print("=== 结论: " + ("✅ 检查器可用（能报红也能报绿）" if ok else "❌ 检查器有问题") + " ===")
    return 0 if ok else 1


# ─────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--check-proposal", default="")
    args = ap.parse_args()

    if args.selfcheck:
        return selfcheck()

    if args.check_proposal:
        r = check_proposal(args.check_proposal)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r["pass"] else 1

    node = census_node_radius()
    other = census_other_channels()
    tele = census_telemetry()

    tiers_cur = discriminable_tiers(node["base_radius_2d"], node["2d_radius_range"][1]) \
        if node.get("2d_radius_range") else None
    # 候选：若把上限提到 2.5× 基底（6 → 15px）
    tiers_cand = discriminable_tiers(node["base_radius_2d"], node["base_radius_2d"] * 2.5) \
        if node.get("base_radius_2d") else None

    payload = {
        "schema": "kgviz-coding-census/v1",
        "measured_at": datetime.now().astimezone().isoformat(),
        "head": os.popen(f'git -C "{REPO}" rev-parse HEAD').read().strip(),
        "node_size": node,
        "other_channels": other,
        "telemetry": tele,
        "discriminability": {
            "current_mapping": tiers_cur,
            "candidate_2_5x": tiers_cand,
            "constraint_note": "3px/20% 是保守经验值，必须 A/B 判读验证（本脚本只给上界估计）",
        },
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    payload["artifactSha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    print(f"HEAD: {payload['head']}")
    print()
    print("=== ① 节点大小编码现状 ===")
    for k, v in node.items():
        print(f"  {k:<28} {v}")
    print()
    print("=== ② 其他视觉通道 ===")
    for k, v in other.items():
        print(f"  {k:<32} {v}")
    print()
    print("=== ③ 现有埋点 ===")
    for k, v in tele.items():
        print(f"  {k:<28} {v}")
    print()
    print("=== ④ 大小可辨性 ===")
    if tiers_cur:
        print(f"  当前映射 ({node['2d_radius_range'][0]}→{node['2d_radius_range'][1]}px): "
              f"可分 {tiers_cur['tiers']} 档 {tiers_cur['r_values']}")
    if tiers_cand:
        print(f"  候选 2.5× (6→15px): 可分 {tiers_cand['tiers']} 档 {tiers_cand['r_values']}")
    print(f"  约束: {tiers_cur['constraint'] if tiers_cur else '-'}")
    print()
    print(f"sha256: {payload['artifactSha256'][:16]}…")

    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(REPO, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        print(f"wrote: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
