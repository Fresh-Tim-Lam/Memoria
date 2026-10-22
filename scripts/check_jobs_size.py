#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""作业登记表（maintenance-jobs.md §5）体积与索引/归档等价守卫（W4.2，2026-10-23）。

断言：
  1. §5 体积 ≤ 8 KB（8,192 B，与 docs-management.md §4.2 一致）；
  2. §5 无「≥20 连续空格」（禁止等宽填充对齐）；
  3. §5 每行 5 列，且每个单元格 ≤200 B（索引列，叙述体进归档）；
  4. §5 索引与 `maintenance-jobs-archive-2026-10.md` 原表**语义等价**：
     作业 kind 集合 / 条数 / 优先级 / 去重键一致，触发点中的标识符不丢失；
  5. `--verify-verbatim REV`：归档原表逐字等于 `REV:docs/design/maintenance-jobs.md §5`
     （用于证明迁出未改语义；默认不跑，需显式指定历史版本）。

超限后的正规动作（docs-management.md §4.2）：
  - 明细（实现状态/证据锚/对账修正原文）进归档，§5 只留索引列；
  - 不得调高预算、删作业或删证据锚达标；预算调整须人批准并注明日期/理由。

用法：
  python scripts/check_jobs_size.py [--file docs/design/maintenance-jobs.md]
                                    [--archive docs/design/maintenance-jobs-archive-2026-10.md]
                                    [--verify-verbatim 56690378]
退出码：0 通过；1 失败（打印全部违规项）。
"""
import argparse
import io
import os
import re
import subprocess
import sys

MAX_BYTES = 8 * 1024
MAX_CELL_BYTES = 200
PAD = re.compile(r" {20,}")
SEP = re.compile(r"^\|[\s|:\-]+\|?\s*$")
PIPE = re.compile(r"(?<!\\)\|")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MD = os.path.join(ROOT, "docs", "design", "maintenance-jobs.md")
DEFAULT_ARCHIVE = os.path.join(ROOT, "docs", "design",
                               "maintenance-jobs-archive-2026-10.md")


def split_cells(line):
    parts = PIPE.split(line.strip())
    if not parts or parts[0].strip() != "" or parts[-1].strip() != "":
        return None
    return [c.strip() for c in parts[1:-1]]


def section_lines(lines, start="## 5.", end="## 6."):
    try:
        s = next(i for i, l in enumerate(lines) if l.startswith(start))
        e = next(i for i, l in enumerate(lines) if l.startswith(end))
    except StopIteration:
        return None
    return lines[s:e]


def data_rows(lines):
    """Return table data rows (skip header + separator)."""
    table = [l for l in lines if l.startswith("|")]
    rows = [l for l in table if not SEP.match(l)]
    return rows[1:] if rows else []


def kinds(cell):
    return [k.strip() for k in cell.split(" / ") if k.strip()]


def norm_merge(s):
    """Normalize merge/dedupe cells: drop status marks, parentheses, whitespace."""
    return re.sub(r"[✅❌\s（）()]", "", s)


IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+ms")


def idents(s):
    return set(IDENT.findall(s))


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=DEFAULT_MD)
    ap.add_argument("--archive", default=DEFAULT_ARCHIVE)
    ap.add_argument("--verify-verbatim", metavar="REV", default=None,
                    help="additionally prove archive rows are verbatim from REV")
    args = ap.parse_args()
    md = os.path.abspath(args.file)
    archive_path = os.path.abspath(args.archive)
    raw = io.open(md, encoding="utf-8").read()
    lines = raw.split("\n")
    sec = section_lines(lines)
    errors = []

    if sec is None:
        print("FAIL: 未找到 §5 或 §6 标题")
        return 1

    size = len("\n".join(sec).encode("utf-8"))
    if size > MAX_BYTES:
        errors.append("§5 体积 %d B > 预算 %d B（超 %d B）" % (size, MAX_BYTES, size - MAX_BYTES))

    pad_lines = [(i + 1, s) for i, s in enumerate(sec) if PAD.search(s)]
    for ln, s in pad_lines[:10]:
        errors.append("§5 L%d 含 ≥20 连续空格（禁止等宽填充）：%s" % (ln, s[:80]))

    rows = data_rows(sec)
    parsed = []
    for i, s in enumerate(rows):
        cells = split_cells(s)
        if cells is None:
            errors.append("§5 第 %d 数据行表格结构异常（管道未转义？）：%s" % (i + 1, s[:80]))
            continue
        if len(cells) != 5:
            errors.append("§5 第 %d 数据行有 %d 列（应为 5）：%s" % (i + 1, len(cells), s[:80]))
            continue
        for k, c in enumerate(cells):
            nb = len(c.encode("utf-8"))
            if nb > MAX_CELL_BYTES:
                errors.append("§5 %s 第%d列 %d B > %d B（索引列禁止叙述体，明细进归档）"
                              % (cells[0], k, nb, MAX_CELL_BYTES))
        parsed.append(cells)

    if not parsed:
        print("FAIL: §5 无作业行")
        return 1

    # ---- index/archive semantic equivalence ----
    if not os.path.exists(archive_path):
        errors.append("归档文件不存在：%s" % os.path.relpath(archive_path, ROOT))
        arch_rows = []
    else:
        arch_raw = io.open(archive_path, encoding="utf-8").read()
        arch_sec = section_lines(arch_raw.split("\n"), "## A.", "## B.")
        arch_rows = []
        if arch_sec is None:
            errors.append("归档缺少 `## A.` / `## B.` 段")
        else:
            for s in data_rows(arch_sec):
                c = split_cells(s)
                if c is not None:
                    arch_rows.append(c)

    if arch_rows:
        if len(parsed) != len(arch_rows):
            errors.append("条数不一致：§5 %d 行 vs 归档 %d 行" % (len(parsed), len(arch_rows)))
        a_map, i_map = {}, {}
        for c in arch_rows:
            key = frozenset(kinds(c[0]))
            if key in a_map:
                errors.append("归档 kind 重复：%s" % c[0])
            a_map[key] = c
        for c in parsed:
            key = frozenset(kinds(c[0]))
            if key in i_map:
                errors.append("§5 kind 重复：%s" % c[0])
            i_map[key] = c
        if set(a_map) != set(i_map):
            only_a = sorted(" / ".join(sorted(k)) for k in set(a_map) - set(i_map))
            only_i = sorted(" / ".join(sorted(k)) for k in set(i_map) - set(a_map))
            if only_a:
                errors.append("归档有、§5 缺：%s" % ", ".join(only_a))
            if only_i:
                errors.append("§5 有、归档缺：%s" % ", ".join(only_i))
        for key in sorted(set(a_map) & set(i_map), key=lambda x: sorted(x)):
            a, i = a_map[key], i_map[key]
            name = " / ".join(kinds(a[0]))
            if a[2] != i[2]:
                errors.append("%s 优先级不一致：归档 %s vs §5 %s" % (name, a[2], i[2]))
            na, ni = norm_merge(a[3]), norm_merge(i[3])
            if na and na != ni:
                errors.append("%s 去重键语义不一致：归档 %r vs §5 %r" % (name, na, ni))
            if not i[3].strip():
                errors.append("%s 去重键为空" % name)
            lost = idents(a[1]) - idents(i[1])
            if lost:
                errors.append("%s 触发点丢失标识符：%s" % (name, ", ".join(sorted(lost))))
            if not i[4].strip():
                errors.append("%s 归属为空" % name)

    # ---- optional verbatim proof ----
    if args.verify_verbatim:
        rel = os.path.relpath(md, ROOT).replace("\\", "/")
        try:
            old = subprocess.check_output(
                ["git", "show", "%s:%s" % (args.verify_verbatim, rel)],
                cwd=ROOT, stderr=subprocess.STDOUT).decode("utf-8")
        except Exception as e:
            errors.append("git show %s:%s 失败：%s" % (args.verify_verbatim, rel, e))
        else:
            old_sec = section_lines(old.split("\n"))
            old_rows = data_rows(old_sec) if old_sec else []
            if len(old_rows) != len(arch_rows):
                errors.append("verbatim: 归档 %d 行 vs %s 原表 %d 行"
                              % (len(arch_rows), args.verify_verbatim, len(old_rows)))
            missing = [r for r in old_rows if arch_raw.count(r) != 1]
            if missing:
                errors.append("verbatim: %d 行未逐字保留（示例：%s）"
                              % (len(missing), missing[0][:80]))

    if errors:
        print("FAIL: §5 作业登记表守卫未通过（%d 项）" % len(errors))
        for e in errors:
            print("  - " + e)
        print("\n正规动作：明细进归档，§5 只留索引列；不得调高预算或删作业达标。"
              "见 docs/conventions/docs-management.md §4.2。")
        return 1

    max_cell = max(len(c.encode("utf-8")) for row in parsed for c in row)
    nk = sum(len(kinds(c[0])) for c in parsed)
    print("PASS: §5 = %d B / %d B；%d 行 / %d 个 kind；单元格最大 %d B；"
          "无 ≥20 连续空格；索引与归档等价（归档 %d B）。"
          % (size, MAX_BYTES, len(parsed), nk, max_cell,
             len(io.open(archive_path, encoding="utf-8").read().encode("utf-8"))))
    if args.verify_verbatim:
        print("PASS: 归档原表逐字等于 %s:%s §5。" % (args.verify_verbatim,
                                                    os.path.relpath(md, ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
