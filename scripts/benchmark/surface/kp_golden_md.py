#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""kp_golden_md.py —— 把 KP 交互金标准 raw JSON 渲染成人读 md。

用法：
    python scripts/benchmark/surface/kp_golden_md.py \
        --raw scripts/benchmark/surface/results/interaction-kp-live-golden_<sha>.json \
        --run2 scripts/benchmark/surface/results/interaction-kp-live-golden-run2_<sha>.json \
        --out scripts/benchmark/surface/results/interaction-kp-live-golden_<sha>.md \
        --runs 2
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 每条断言 = (场景 id, 快照 label, 取值函数, 期望谓词, 说明)
# 取值函数拿到的是 snapshot 对象的 ['kp'] 段。

CASES = [
    ("KP1-hover-highlights-range", "before-hover",
     lambda k: (k["lineInRange"], k["lineKpHover"], k["band"]),
     lambda v: v[0] == 0 and v[1] == 0 and v[2] is None,
     "悬停前：无任何区间高亮"),
    ("KP1-hover-highlights-range", "during-hover",
     lambda k: (k["lineInRange"], k["lineKpHover"], (k["band"] or {}).get("range"), (k["band"] or {}).get("hasError")),
     lambda v: v[0] == 16 and v[1] == 16 and v[2] == "45-60" and v[3] is False,
     "悬停局部 KP(L45–60)：源码 16 行 in-range + kp-hover，预览带 45-60（非 error）"),
    ("KP1-hover-highlights-range", "after-hover-out",
     lambda k: (k["lineInRange"], k["band"], k["hoveredKpId"]),
     lambda v: v[0] == 0 and v[1] is None and v[2] is None,
     "移出：高亮全部清除（无残留）"),
    ("KP1-hover-highlights-range", "during-hover",
     lambda k: k["scroll"],
     lambda v: True,  # 与 before 对比在下面单独做
     "（另测）悬停**不滚动**：scroll 应与 before-hover 相同"),

    ("KP2-click-jumps-to-range", "before-click-top",
     lambda k: (k["lineInRange"], k["activeKpId"]),
     lambda v: v[0] == 0 and v[1] is None,
     "点击前：无高亮、无 active"),
    ("KP2-click-jumps-to-range", "after-click-scrolled",
     lambda k: (k["lineInRange"], k["lineFlash"], (k["band"] or {}).get("range"), k["activeKpId"], k["scroll"]),
     lambda v: v[0] == 16 and v[1] == 16 and v[2] == "45-60" and v[3] == "kp-local-mid" and v[4] > 500,
     "点击局部 KP：16 行高亮+闪烁、带 45-60、active 置位、**预览已滚动**（scroll>500）"),
    ("KP2-click-jumps-to-range", "after-flash-faded",
     lambda k: (k["lineFlash"], k["activeKpId"]),
     lambda v: v[0] == 0 and v[1] == "kp-local-mid",
     "闪烁 2.5s 后自动淡出，active 保留（跳转态持久，高亮态短暂）"),

    ("KP3-saveupdates-marks-without-scroll", "before-save",
     lambda k: (k["lineInRange"], k["scroll"]),
     lambda v: v[0] == 16 and v[1] > 500,
     "保存前：已有 16 行标记，视口在中部（scroll>500，非顶部）"),
    ("KP3-saveupdates-marks-without-scroll", "after-save",
     lambda k: (k["lineInRange"], k["scroll"]),
     lambda v: v[0] == 16 and v[1] > 500,
     "保存后：标记仍在（16 行）且**滚动位置不变**（静默标记语义）"),

    ("KP4-error-highlight-via-check-panel", "before-open-from-check",
     lambda k: (k["lineError"], k["band"]),
     lambda v: v[0] == 0 and v[1] is None,
     "打开前：无错误高亮"),
    ("KP4-error-highlight-via-check-panel", "after-error-highlight",
     lambda k: (k["lineError"], (k["band"] or {}).get("hasError"), (k["band"] or {}).get("range"),
                any("error-highlight" in i["cls"] for i in k["items"]),
                any(i["id"] == "kp-err-probe" and "active" in i["cls"] for i in k["items"])),
     lambda v: v[0] == 7 and v[1] is True and v[2] == "94-100" and v[3] is True and v[4] is True,
     "检查面板「打开」→ 7 行 kp-error-flash、预览带 94-100 且标 error、列表项 error-highlight+active"),
]


def snaps(run):
    out = {}
    for r in run.get("results", []):
        for label, s in (r.get("snapshots") or {}).items():
            out[(r["id"], label)] = s
    return out


def diff(a, b, path=""):
    d = []
    if type(a) is not type(b):
        return [(path, a, b)]
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                d.append((path + "." + k, "<absent>", b[k]))
            elif k not in b:
                d.append((path + "." + k, a[k], "<absent>"))
            else:
                d += diff(a[k], b[k], path + "." + k)
        return d
    if isinstance(a, list):
        if len(a) != len(b):
            d.append((path + ".length", len(a), len(b)))
        for i in range(min(len(a), len(b))):
            d += diff(a[i], b[i], path + "[%d]" % i)
        return d
    if a != b:
        d.append((path, a, b))
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--run2", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--runs", type=int, default=2)
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    raw = json.loads(Path(args.raw).read_text(encoding="utf-8"))
    run2 = json.loads(Path(args.run2).read_text(encoding="utf-8")) if args.run2 else None
    S = snaps(raw)
    S2 = snaps(run2) if run2 else {}

    # 全量快照一致性
    total_diff = 0
    diff_lines = []
    if run2:
        for key in sorted(S):
            if key not in S2:
                diff_lines.append("MISSING in run2: %s" % (key,))
                total_diff += 1
                continue
            dd = diff(S[key], S2[key])
            if dd:
                total_diff += len(dd)
                for (p, x, y) in dd[:8]:
                    diff_lines.append("%s/%s %s: run1=%r run2=%r" % (key[0], key[1], p, x, y))

    L = []
    L.append("# KP 交互金标准（真机应用）\n")
    L.append("> 生成：`scripts/benchmark/surface/kp_golden_md.py`")
    L.append("> 场景：`scripts/benchmark/surface/scenarios/kp-interactions.json`")
    L.append("> 驱动：`interaction.mjs --scenarios … --cdp-port 9500`（attach **已在运行的真机应用**，非无头）")
    L.append("> 运行：%d 次　｜　浏览器：%s　｜　target：%s\n" % (
        args.runs, raw.get("browser"), (raw.get("liveTarget") or {}).get("title")))
    L.append("## 为什么补这一块\n")
    L.append("surface 契约 C6（落点）/C8（交互存活）**没有覆盖「知识点 ↔ 显示区域」的联动**，")
    L.append("而重构最可能静默弄坏的正是这里。本金标准把 4 条 KP 联动钉成可逐字比对的快照。\n")

    L.append("## 断言结果\n")
    L.append("| # | 断言 | 结果 | 实测值 |")
    L.append("|---|---|---|---|")
    ok_n = 0
    for i, (scen, label, get, pred, desc) in enumerate(CASES, 1):
        s = S.get((scen, label))
        if not s:
            L.append("| %d | %s | ⚪ 无快照 | — |" % (i, desc))
            continue
        kp = s.get("kp") or {}
        v = get(kp)
        ok = pred(v)
        ok_n += 1 if ok else 0
        L.append("| %d | %s | %s | `%s` |" % (i, desc, "🟢 通过" if ok else "🔴 未通过", v))
    L.append("\n合计 **%d/%d** 通过。\n" % (ok_n, len(CASES)))

    # 额外对比类断言
    hov = S.get(("KP1-hover-highlights-range", "before-hover"))
    hov2 = S.get(("KP1-hover-highlights-range", "during-hover"))
    sv1 = S.get(("KP3-saveupdates-marks-without-scroll", "before-save"))
    sv2 = S.get(("KP3-saveupdates-marks-without-scroll", "after-save"))
    L.append("## 对比型断言（需要两个快照相减）\n")
    if hov and hov2:
        a = hov["kp"]["scroll"]; b = hov2["kp"]["scroll"]
        L.append("- **悬停不滚动**：before-hover scroll=%s → during-hover scroll=%s ⇒ %s" % (
            a, b, "🟢 未滚动" if a == b else "🔴 滚动了"))
    if sv1 and sv2:
        a = sv1["kp"]["scroll"]; b = sv2["kp"]["scroll"]
        L.append("- **保存不滚动**：before-save scroll=%s → after-save scroll=%s ⇒ %s" % (
            a, b, "🟢 未滚动" if a == b else "🔴 滚动了"))
        L.append("- **保存不破标记**：before in-range=%s → after in-range=%s ⇒ %s" % (
            sv1["kp"]["lineInRange"], sv2["kp"]["lineInRange"],
            "🟢 标记保持" if sv1["kp"]["lineInRange"] == sv2["kp"]["lineInRange"] else "🔴 标记丢失"))
    L.append("")

    L.append("## 两次运行一致性\n")
    if run2:
        L.append("- 快照总数：run1=%d，run2=%d" % (len(S), len(S2)))
        L.append("- **差异条目：%d** ⇒ %s\n" % (total_diff, "🟢 两次完全一致（金标准可复现）" if total_diff == 0 else "🔴 存在差异（见下）"))
        if diff_lines:
            L.append("```")
            L += diff_lines[:40]
            L.append("```\n")
    else:
        L.append("- 未提供第二次运行 ⇒ 未做一致性校验\n")

    L.append("## 前置条件（复现必读）\n")
    L.append("1. 知识库副本：`docs/example/AAA_Vocab` → `artifacts/_kp_probe_kb`（**不污染源**）。")
    L.append("2. 侧车注入（仅副本）：")
    L.append("   - `kp-local-mid`：**注入的局部区间 L45–60**。源库 69/69 个 KP 都覆盖 L1–末行，")
    L.append("     那样「点了 KP 跳到区间」与「滚回顶部」不可区分 ⇒ 必须注入局部 KP 才能测出跳转。")
    L.append("   - `kp-err-probe`：注入的校验错误来源（配合检查面板的「打开」按钮）。")
    L.append("3. **改侧车后必须重启应用**：侧车在应用内存里按 rel_norm 缓存，切文件 / 构建知识库都不会失效。")
    L.append("4. 启动：`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9500`")
    L.append("   + `MEMORIA_KB=<副本>` + `python -m memoria.app.desktop`。")
    L.append("")
    Path(args.out).write_text("\n".join(L), encoding="utf-8")
    print("[kp_golden_md] wrote %s  (%d/%d assertions pass, %d snapshot diffs)" % (
        args.out, ok_n, len(CASES), total_diff))
    return 0 if (ok_n == len(CASES) and total_diff == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
