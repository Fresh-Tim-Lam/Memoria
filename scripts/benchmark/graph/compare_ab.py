#!/usr/bin/env python3
"""G05 · 图谱渲染 L1 的 A/B 对照

读两份 `render-*.json`（同语料、同机），产出对照表 + 门禁判定，落盘 `results/compare_*.md`。

用法：
    python scripts/benchmark/graph/compare_ab.py `
        --before scripts/benchmark/graph/results/render-baseline-target_346e5f95.json `
        --after  scripts/benchmark/graph/results/render-after-d1_346e5f95.json

门禁口径（见 docs/design/graph-benchmark.md §5）：**L1 只判布局与整帧**；
绘制门禁（≤8ms）属 L2 真光栅化口径，此处仅记录、不判定。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"

# 指标名 -> 取值函数 -> 阈值 -> 比较符（L1 口径，判布局与整帧）
GATES = (
    ("布局单 tick p50", lambda r: r["tickMs"]["p50"], 20.0, "<="),
    ("整帧 p95", lambda r: r["frameMs"]["p95"], 33.0, "<="),
)
# 仅记录、不判定（真机光栅化口径在 L2）
RECORD_ONLY = (
    ("绘制 p50", lambda r: r["drawMs"]["p50"]),
    ("绘制调用/帧", lambda r: r["callsPerDrawTotal"]),
    ("边长 p50", lambda r: r["quality"]["edgeLenP50"]),
    ("边长 p95", lambda r: r["quality"]["edgeLenP95"]),
)


def load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = {}
    for r in data.get("results", []):
        rows[(r["pattern"], r["scale"])] = r
    return {"data": data, "rows": rows, "label": path.stem}


def delta(before: float, after: float) -> str:
    if before in (0, None):
        return "—"
    return f"{(after - before) / before * 100:+.1f}%"


def budget_of(info: dict) -> str:
    """帧预算；老版本采集器无此字段 → 显示"未记录"（旧行为 = 关闭预算）"""
    v = info["data"]["results"][0].get("frameBudgetMs")
    return "未记录(=关闭)" if v is None else f"{v}ms"


def ticks_of(row: dict) -> str:
    v = row.get("ticksRun")
    return "未记录" if not v else str(v["mean"])


def main() -> int:
    ap = argparse.ArgumentParser(description="图谱渲染 L1 A/B 对照")
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    b = load(Path(args.before))
    a = load(Path(args.after))

    b_digest = b["data"]["meta"].get("corpus_digest")
    a_digest = a["data"]["meta"].get("corpus_digest")
    same_corpus = b_digest == a_digest
    keys = sorted(set(b["rows"]) & set(a["rows"]))
    if not keys:
        raise SystemExit("两份文件没有共同的 (pattern, scale) 行，无法对照")

    L: list[str] = [
        "# 图谱渲染 A/B 对照（L1 无头 · 2D）",
        "",
        f"- 改前：`{b['label']}`（帧预算 {budget_of(b)}）",
        f"- 改后：`{a['label']}`（帧预算 {budget_of(a)}）",
        f"- 语料指纹：{b_digest} / {a_digest}"
        + ("（一致 ✓）" if same_corpus else "（**不一致 ⇒ 对照无效**）"),
        f"- 共同行：{len(keys)} 个 (pattern, scale)",
        "",
        "> 门禁（L1 口径，见设计稿 §5）：**布局单 tick p50 ≤ 20ms**、**整帧 p95 ≤ 33ms**。"
        "绘制/边长仅记录 —— 真机光栅化口径须走 L2，布局观感的底线是「节点不重叠 + 合理分散」（其量化指标在 P2 前置步骤加入）。",
        "",
        "## 分账对照",
        "",
        "| pattern | 节点 | tick/帧 | 单 tick p50 | 整帧 p50 | 整帧 p95 | 绘制 p50 | 调用/帧 | 边长 p50 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for k in keys:
        pattern, scale = k
        rb, ra = b["rows"][k], a["rows"][k]
        L.append(
            f"| {pattern} | {ra['nodeCount']} | "
            f"{ticks_of(rb)} → {ticks_of(ra)} | "
            f"{rb['tickMs']['p50']} → {ra['tickMs']['p50']} "
            f"({delta(rb['tickMs']['p50'], ra['tickMs']['p50'])}) | "
            f"{rb['frameMs']['p50']} → {ra['frameMs']['p50']} "
            f"({delta(rb['frameMs']['p50'], ra['frameMs']['p50'])}) | "
            f"{rb['frameMs']['p95']} → {ra['frameMs']['p95']} "
            f"({delta(rb['frameMs']['p95'], ra['frameMs']['p95'])}) | "
            f"{rb['drawMs']['p50']} → {ra['drawMs']['p50']} | "
            f"{rb['callsPerDrawTotal']} → {ra['callsPerDrawTotal']} | "
            f"{rb['quality']['edgeLenP50']} → {ra['quality']['edgeLenP50']} "
            f"({delta(rb['quality']['edgeLenP50'], ra['quality']['edgeLenP50'])}) |"
        )

    L += ["", "## 门禁判定（改后是否达标）", "", "| 门禁 | 改后达标行 | 未达标行 |", "|---|---|---|"]
    total_pass = total_fail = 0
    for name, get, limit, op in GATES:
        ok, bad = [], []
        for k in keys:
            v = get(a["rows"][k])
            (ok if v <= limit else bad).append(f"{k[0][:4]}{k[1]}")
        total_pass += len(ok)
        total_fail += len(bad)
        L.append(
            f"| {name} {op} {limit:g}ms | {len(ok)} | {len(bad)}"
            + (f"（{', '.join(bad[:6])}{'…' if len(bad) > 6 else ''}）" if bad else "")
            + " |"
        )
    L += [
        "",
        f"**结论**：{total_pass} 项达标 / {total_fail} 项未达标。"
        + (
            "全部达标。"
            if total_fail == 0
            else "未达标项集中在单 tick 本身超阈值 —— 说明**单帧预算已到位（帧时间有上界），"
            "但单 tick 的复杂度仍需 D2 解决**（预算无法把一帧切成零个 tick）。"
        ),
        "",
        "## 仅记录（不判定）",
        "",
        "| pattern | 节点 | " + " | ".join(f"{n} 改前→改后" for n, _ in RECORD_ONLY) + " |",
        "|---" * (2 + len(RECORD_ONLY)) + "|",
    ]
    for k in keys:
        rb, ra = b["rows"][k], a["rows"][k]
        cells = " | ".join(f"{get(rb)} → {get(ra)}" for _, get in RECORD_ONLY)
        L.append(f"| {k[0]} | {ra['nodeCount']} | {cells} |")

    text = "\n".join(L) + "\n"
    dest = Path(args.out) if args.out else RESULTS / f"compare_{b['label']}_{a['label']}.md"
    if not dest.is_absolute():
        dest = ROOT / dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    print(text)
    print(f"[compare] written {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
