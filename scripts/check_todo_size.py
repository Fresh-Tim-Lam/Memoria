#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""台账体积/格式守卫（P6b，2026-10-22 Lead 批准）。

断言 docs/todo.md：
  1. 体积 ≤ 64 KB（65,536 B）；
  2. 无「≥20 连续空格」（禁止等宽填充对齐）；
  3. 表格单元格 ≤200 B —— 存量超限单元格按**基线允许清单**冻结（只允许变小，不允许变大/新增）。

超限后的正规动作（写进 docs-management.md）：
  - 优先把**已收口条目**按 P1 先例归档到 `docs/design/**`（原文逐字、可 git log -S 追溯），台账只留索引行；
  - 不得靠调高预算解决（预算调整须人批准并注明日期/理由）；
  - 不得用删除条目/删证据锚的方式「达标」。

用法：python scripts/check_todo_size.py [--file docs/todo.md]
退出码：0 通过；1 失败（打印全部违规项）。
"""
import argparse
import io
import os
import re
import sys

MAX_BYTES = 64 * 1024
PAD = re.compile(r" {20,}")
PIPE = re.compile(r"(?<!\\)\|")
SEP = re.compile(r"^\|[\s|:\-]+\|?\s*$")

# 存量超 200B 单元格基线（2026-10-22 P5 后冻结；键=(首列 ID/日期, 列序号)，值=允许的最大字节数）。
# 只允许单元格**变小**；新增超限或变大即失败。迁移/归档后应同步收紧此表。
BASELINE_OVERSIZE = {
    ("G05", 2): 707,
    ("E14", 2): 256,
    ("E22", 1): 279,
    ("E22", 2): 504,
    ("E23", 1): 291,
    ("DOC02", 1): 209,
    ("T04", 2): 507,
    ("P06", 2): 242,
    ("P07", 1): 229,
    ("P07", 2): 235,
    ("V06", 1): 219,
    ("AG105", 1): 228,
    ("AG59", 1): 209,
    ("AG91", 1): 204,
    ("2026-08", 2): 403,
    ("2026-08-29", 2): 220,
    ("2026-08-30", 2): 308,
    ("2026-09-03/04", 2): 275,
    ("2026-09-05", 2): 270,
    ("2026-09-09/10", 2): 399,
    ("2026-09-14", 2): 365,
    ("2026-09-15", 2): 320,
    ("2026-09-19", 2): 461,
    ("历史", 2): 241,
}


def split_cells(s):
    parts = PIPE.split(s)
    if not parts or parts[0].strip() != "" or parts[-1].strip() != "":
        return None
    return [c.strip() for c in parts[1:-1]]


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=os.path.join(os.path.dirname(__file__), "..", "docs", "todo.md"))
    args = ap.parse_args()
    path = os.path.abspath(args.file)
    raw = io.open(path, encoding="utf-8").read()
    lines = raw.split("\n")
    errors = []

    size = len(raw.encode("utf-8"))
    if size > MAX_BYTES:
        errors.append("体积 %d B > 预算 %d B（超 %d B）" % (size, MAX_BYTES, size - MAX_BYTES))

    pad_lines = [(i + 1, s) for i, s in enumerate(lines) if PAD.search(s)]
    for ln, s in pad_lines[:10]:
        errors.append("L%d 含 ≥20 连续空格（禁止等宽填充）：%s" % (ln, s[:80]))
    if len(pad_lines) > 10:
        errors.append("… 另有 %d 行含 ≥20 连续空格" % (len(pad_lines) - 10))

    for i, s in enumerate(lines):
        if not s.startswith("|") or SEP.match(s):
            continue
        cells = split_cells(s)
        if cells is None:
            errors.append("L%d 表格行列结构异常（管道未转义？）：%s" % (i + 1, s[:80]))
            continue
        if not cells:
            continue
        eid = cells[0]
        for k, c in enumerate(cells):
            nb = len(c.encode("utf-8"))
            if nb <= 200:
                continue
            allowed = BASELINE_OVERSIZE.get((eid, k))
            if allowed is None:
                errors.append("L%d %s 第%d列 %dB > 200B 且不在基线允许清单（新增超限）" % (i + 1, eid, k, nb))
            elif nb > allowed:
                errors.append("L%d %s 第%d列 %dB > 基线 %dB（存量超限不得变大）" % (i + 1, eid, k, nb, allowed))

    if errors:
        print("FAIL: docs/todo.md 台账守卫未通过（%d 项）" % len(errors))
        for e in errors:
            print("  - " + e)
        print("\n超限后的正规动作：把已收口条目按 P1 先例归档到 docs/design/**（原文逐字），台账只留索引；"
              "不得调高预算或删条目达标。见 docs/conventions/docs-management.md §4.2。")
        return 1
    print("PASS: docs/todo.md = %d B / %d 行；无 ≥20 连续空格；无新增超限单元格。" % (size, len(lines)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
