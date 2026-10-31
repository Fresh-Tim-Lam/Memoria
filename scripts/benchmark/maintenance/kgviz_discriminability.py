#!/usr/bin/env python
"""task-173｜V2 可辨档数：渲染层可复跑测量（不是人类判读）

## 这个脚本能证明什么 / 不能证明什么（先划清，最重要）

**能证明（确定，可复跑）**：
  1. 在给定 DPI/画布下，不同档半径渲染到屏幕后的**真实像素尺寸**
  2. 相邻档之间的**像素差**（直径差、面积差、面积比）—— 这是**物理量**
  3. 三方方案（C 4 档 / A 5 档 / B 12–13 档）在**同一坐标系下的实际像素间隔**
  4. 若某方案相邻档面积比 < 某阈值，则该方案内部**存在"物理上接近"的档**（必要非充分）

**不能证明（必须明确声明）**：
  ❌ **人类是否可辨** —— 需要真人判读实验，本脚本完全不能替代
  ❌ 任何"可辨阈值 px" 的**正确性** —— 3px/4px 仍是经验值，本脚本只是把经验值代入算档数

**⇒ 本脚本的正确用法**：把"三个方案各自的物理像素间隔"摆在同一张表上，
   让 Phase 4 看到 —— **三方的差异不是"谁对"，而是"套用了不同的经验阈值 + 不同的档数定义"**。

## 关键发现（脚本会算出来）
B 的 12–13 档是【数据分桶数】，不是【可辨档数】—— 两者是不同概念。

用法:
    python scripts/benchmark/maintenance/kgviz_discriminability.py [--json out.json] [--render]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
os.environ.setdefault("MEMORIA_CONFIG_DIR", tempfile.mkdtemp(prefix="memoria-cfg-"))


# ─────────────────────────────────────────────────────────────
# 三方方案的物理参数（全部取自各自提案原文，带 ev 身份）
# ─────────────────────────────────────────────────────────────

SCHEMES = {
    "C_4档_3px": {
        "source": "PROPOSAL-metrics-baseline.md（C）",
        "ev": "ev:file:artifacts/agent/verify/debate/kgviz/PROPOSAL-metrics-baseline.md#L~§3.3",
        "radii_px": [6.0, 9.0, 12.0, 15.0],
        "claimed_tiers": 4,
        "threshold_stmt": "相邻档半径差 ≥ max(3.0px, 20%·r)",
        "threshold_px": 3.0,
    },
    "A_5档_4px": {
        "source": "PROPOSAL-render-perf.md#L39,L69-L70（A）",
        "ev": "ev:file:artifacts/agent/verify/debate/kgviz/PROPOSAL-render-perf.md#L39",
        "radii_px": [4.0, 6.0, 8.0, 10.0, 12.0],
        "claimed_tiers": 5,
        "threshold_stmt": "直径差 ≥4px（半径差 2px）",
        "threshold_px": 2.0,   # 半径差
    },
    "B_12到13档": {
        "source": "PROPOSAL-todo-owner.md#L60-L62（B）",
        "ev": "ev:file:artifacts/agent/verify/debate/kgviz/PROPOSAL-todo-owner.md#L62",
        "radii_expr": "r = 5 + 13*sqrt(t), t=(p-0.10)/0.80",
        "claimed_tiers": "12 (degree) / 13 (content)",
        "note": "原文『实测桶：degree 12 档、内容 13 档』——这是【数据分桶数】，不是可辨档数",
        "r_min": 5.0, "r_max": 18.0,
    },
}


def px_metrics(radii: list[float]) -> dict:
    """给定半径序列，算相邻档的像素差"""
    rows = []
    for i in range(len(radii) - 1):
        r0, r1 = radii[i], radii[i + 1]
        d0, d1 = r0 * 2, r1 * 2
        a0, a1 = math.pi * r0 ** 2, math.pi * r1 ** 2
        rows.append({
            "from_r": r0, "to_r": r1,
            "radius_delta_px": round(r1 - r0, 2),
            "diameter_delta_px": round(d1 - d0, 2),
            "area_ratio": round(a1 / a0, 3),
            "area_delta_pct": round((a1 - a0) / a0 * 100, 1),
        })
    return {"tiers": len(radii), "radii": radii, "adjacent": rows}


def scheme_c_analysis() -> dict:
    """C 的 4 档：检查是否满足自己的判据"""
    s = SCHEMES["C_4档_3px"]
    m = px_metrics(s["radii_px"])
    # 逐档检查 3px / 20% 判据
    checks = []
    for a in m["adjacent"]:
        need = max(s["threshold_px"], a["from_r"] * 0.20)
        ok = a["radius_delta_px"] >= need - 1e-9
        checks.append({"pair": f"{a['from_r']}→{a['to_r']}",
                       "delta": a["radius_delta_px"], "needed": round(need, 2), "pass": ok})
    return {"scheme": "C", "metrics": m, "self_consistent": all(c["pass"] for c in checks),
            "checks": checks}


def scheme_a_analysis() -> dict:
    """A 的 5 档：检查是否满足其 2px 半径差判据（=4px 直径差）"""
    s = SCHEMES["A_5档_4px"]
    m = px_metrics(s["radii_px"])
    checks = []
    for a in m["adjacent"]:
        need = s["threshold_px"]  # 半径差 2px
        ok = a["radius_delta_px"] >= need - 1e-9
        checks.append({"pair": f"{a['from_r']}→{a['to_r']}",
                       "delta": a["radius_delta_px"], "needed": need, "pass": ok})
    return {"scheme": "A", "metrics": m, "self_consistent": all(c["pass"] for c in checks),
            "checks": checks}


def scheme_b_analysis() -> dict:
    """B 的 12–13 档：关键 —— 这是【数据桶数】还是【可辨档数】？

    B 的映射 r = 5 + 13*sqrt(t)，t∈[0,1] 连续。
    若度数有 12 个不同取值，则产生 12 个不同半径 —— 但**相邻半径差可能远小于任何可辨阈值**。
    本函数计算：12 等分 t 时，相邻半径差是多少。
    """
    s = SCHEMES["B_12到13档"]
    n = 12
    radii = []
    for i in range(n):
        t = i / (n - 1)
        r = 5 + 13 * math.sqrt(t)
        radii.append(round(r, 2))
    m = px_metrics(radii)
    deltas = [a["radius_delta_px"] for a in m["adjacent"]]
    area_ratios = [a["area_ratio"] for a in m["adjacent"]]
    return {
        "scheme": "B",
        "metrics": m,
        "radii_12buckets": radii,
        "min_radius_delta_px": min(deltas),
        "max_radius_delta_px": max(deltas),
        "min_area_ratio": min(area_ratios),
        "under_3px_count": sum(1 for d in deltas if d < 3.0),
        "under_2px_count": sum(1 for d in deltas if d < 2.0),
        "note": ("若 B 的 12 档相邻半径差大多 <2px，则这些档在物理上接近，"
                 "『12 档可辨』不成立；但换算成实际数据桶后又可能极少同时出现在近似度区间"),
    }


# ─────────────────────────────────────────────────────────────
# 渲染层实测：用 PIL 真实画出不同直径的圆，量像素边界
# ─────────────────────────────────────────────────────────────

def render_margin_test() -> dict:
    """渲染层实测：反锯齿会让实际像素边界比标称半径大多少？

    这解决一个三方都没提的问题：**标称半径 ≠ 屏幕实际占位**。
    若反锯齿导致每个圆多出 ~1px 边缘，那么相邻档的实际差可能与标称差不同。
    """
    try:
        from PIL import Image, ImageDraw
    except Exception as e:
        return {"available": False, "error": f"{type(e).__name__}: {e}"}

    results = []
    SS = 4  # 超采样倍率
    for r in [4.0, 5.0, 6.0, 8.0, 9.0, 10.0, 12.0, 15.0, 18.0]:
        size = int(math.ceil(r * 2 + 8))
        W = H = size * SS
        img = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(img)
        cx = cy = W / 2
        rr = r * SS
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=255)
        # 降采样
        small = img.resize((size, size), Image.LANCZOS)
        px = small.load()
        # 扫中心横线，找第一个 >32 的像素（可见边界）
        mid = int(size // 2)
        left = None
        for x in range(size):
            if px[x, mid] > 32:
                left = x
                break
        right = None
        for x in range(size - 1, -1, -1):
            if px[x, mid] > 32:
                right = x
                break
        measured_d = (right - left + 1) if (left is not None and right is not None) else None
        results.append({
            "nominal_r": r,
            "nominal_d": round(r * 2, 1),
            "measured_d_px": measured_d,
            "overflow_px": round(measured_d - r * 2, 1) if measured_d else None,
        })
    return {"available": True, "supersample": SS, "rows": results}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--render", action="store_true", help="跑 PIL 渲染实测（慢一点）")
    args = ap.parse_args()

    c = scheme_c_analysis()
    a = scheme_a_analysis()
    b = scheme_b_analysis()
    render = render_margin_test() if args.render else {"available": False, "note": "加 --render 启用"}

    payload = {
        "schema": "kgviz-discriminability/v1",
        "measured_at": datetime.now().astimezone().isoformat(),
        "head": os.popen(f'git -C "{REPO}" rev-parse HEAD').read().strip(),
        "SCOPE_DISCLOSURE": {
            "CAN_PROVE": [
                "各方案的相邻档像素差 / 面积比（物理量，可复跑）",
                "各方案是否自洽（是否符合自己声明的阈值）",
                "B 的 12 档相邻半径差是否 <2px（若是，『12 档可辨』物理上不成立）",
            ],
            "CANNOT_PROVE": [
                "人类是否可辨 —— 需真人判读实验，本脚本不能替代",
                "3px / 4px 阈值的正确性 —— 仍是经验值",
            ],
            "CRITICAL_DISTINCTION": "渲染后像素差 ≠ 人类可辨；本文件只给前者",
        },
        "schemes": {
            "C": {"params": SCHEMES["C_4档_3px"], "analysis": c},
            "A": {"params": SCHEMES["A_5档_4px"], "analysis": a},
            "B": {"params": SCHEMES["B_12到13档"], "analysis": b},
        },
        "render_margin": render,
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    payload["artifactSha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    print("=" * 78)
    print("V2 可辨档数：渲染层物理量对照（★ 不等于人类可辨）")
    print("=" * 78)
    print()
    print("【C 的 4 档】半径 6/9/12/15px，判据 max(3px, 20%·r)")
    for ck in c["checks"]:
        print(f"  {ck['pair']:<10} 半径差={ck['delta']}px  需≥{ck['needed']}px  "
              f"{'✅' if ck['pass'] else '❌'}")
    print(f"  自洽性: {'✅ 通过' if c['self_consistent'] else '❌ 不通过'}")
    print()
    print("【A 的 5 档】半径 4/6/8/10/12px，判据直径差≥4px（半径差 2px）")
    for ck in a["checks"]:
        print(f"  {ck['pair']:<10} 半径差={ck['delta']}px  需≥{ck['needed']}px  "
              f"{'✅' if ck['pass'] else '❌'}")
    print(f"  自洽性: {'✅ 通过' if a['self_consistent'] else '❌ 不通过'}")
    print()
    print("【B 的 12 档】r = 5 + 13·sqrt(t)，t 均分 12 份")
    print(f"  半径序列: {b['radii_12buckets']}")
    print(f"  相邻半径差: min={b['min_radius_delta_px']}px  max={b['max_radius_delta_px']}px")
    print(f"  相邻面积比: min={b['min_area_ratio']}")
    print(f"  ★ 半径差 <3px 的相邻档数: {b['under_3px_count']}/11")
    print(f"  ★ 半径差 <2px 的相邻档数: {b['under_2px_count']}/11")
    print()
    print("【关键判定】")
    print("  若 B 的相邻半径差大量 <2px ⇒ 『12 档可辨』在物理上不成立（是数据桶数不是可辨档数）")
    print()
    if render.get("available"):
        print("【渲染层实测】反锯齿导致的实际像素溢出（超采样 ×%d）" % render["supersample"])
        for row in render["rows"]:
            print(f"  标称 r={row['nominal_r']:<5} d={row['nominal_d']:<5} "
                  f"实测d={row['measured_d_px']}  溢出={row['overflow_px']}px")
    else:
        print("【渲染层实测】未启用（加 --render）")
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
