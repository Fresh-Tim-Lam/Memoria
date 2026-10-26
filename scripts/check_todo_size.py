#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""台账守卫（P6b 2026-10-22；2026-10-26 索引化扩展）。

断言 docs/todo.md：
  1. 体积 ≤ 预算（当前 64 KB；Batch A+B 实测后按人批准改 56 KB）；
  2. 无「≥20 连续空格」；
  3. 表格单元格 ≤200 B（存量超限按基线清单冻结，只允许变小）；
  4. 【新】相对链接必须存在（死链 = FAIL；锚点指向 docs/todo/ 时须存在对应 <a id>）；
  5. 【新】docs/todo/*.md 必须被 todo.md 引用（孤儿 = WARN）；
  6. 【新】todo.md 某节既无链接且正文 >400 B（疑似未索引化 = WARN）。

用法：python scripts/check_todo_size.py [--file docs/todo.md] [--selftest]
退出码：0 通过（WARN 不阻断）；1 失败（打印全部违规项）。
"""
import argparse
import io
import os
import re
import sys
import tempfile

MAX_BYTES = 56 * 1024  # 2026-10-26 Batch A+B 实测后 64->56 KB（人批准）
PAD = re.compile(r" {20,}")
PIPE = re.compile(r"(?<!\\)\|")
SEP = re.compile(r"^\|[\s|:\-]+\|?\s*$")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
ANCHOR_ID = re.compile(r'<a id="([^"]+)"')
HEADING = re.compile(r"^## (.+)$", re.M)

BASELINE_OVERSIZE = {
    ("G05", 2): 707, ("E14", 2): 256, ("E22", 1): 279, ("E22", 2): 504,
    ("E23", 1): 291, ("DOC02", 1): 209, ("T04", 2): 507, ("P06", 2): 242,
    ("P07", 1): 229, ("P07", 2): 235, ("V06", 1): 219, ("AG105", 1): 228,
    ("AG59", 1): 209, ("AG91", 1): 204, ("2026-08", 2): 403,
    ("2026-08-29", 2): 220, ("2026-08-30", 2): 308, ("2026-09-03/04", 2): 275,
    ("2026-09-05", 2): 270, ("2026-09-09/10", 2): 399, ("2026-09-14", 2): 365,
    ("2026-09-15", 2): 320, ("2026-09-19", 2): 461, ("历史", 2): 241,
}
# 存量死链基线（当前为空；新增死链一律 FAIL）
BASELINE_BROKEN_LINKS = set()


def split_cells(s):
    parts = PIPE.split(s)
    if not parts or parts[0].strip() != "" or parts[-1].strip() != "":
        return None
    return [c.strip() for c in parts[1:-1]]


def _resolve(target, docs_dir):
    root = os.path.dirname(docs_dir)
    cands = [
        os.path.normpath(os.path.join(docs_dir, target)),
        os.path.normpath(os.path.join(root, target)),
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def _anchors(path):
    try:
        text = io.open(path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return set()
    return set(ANCHOR_ID.findall(text))


def analyze(todo_path, docs_dir):
    fails, warns = [], []
    raw = io.open(todo_path, encoding="utf-8").read()
    lines = raw.split("\n")
    size = len(raw.encode("utf-8"))
    if size > MAX_BYTES:
        fails.append("体积 %d B > 预算 %d B" % (size, MAX_BYTES))

    for i, s in enumerate(lines):
        if PAD.search(s):
            fails.append("L%d 含 ≥20 连续空格" % (i + 1))

    for i, s in enumerate(lines):
        if not s.startswith("|") or SEP.match(s):
            continue
        cells = split_cells(s)
        if cells is None:
            fails.append("L%d 表格行列结构异常" % (i + 1))
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
                fails.append("L%d %s 第%d列 %dB > 200B 且不在基线（新增超限）" % (i + 1, eid, k, nb))
            elif nb > allowed:
                fails.append("L%d %s 第%d列 %dB > 基线 %dB" % (i + 1, eid, k, nb, allowed))

    # 4) 链接存在性
    for m in LINK.finditer(raw):
        url = m.group(1)
        if url.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target, _, anchor = url.partition("#")
        if not target:
            continue
        if target in BASELINE_BROKEN_LINKS:
            continue
        path = _resolve(target, docs_dir)
        if path is None:
            fails.append("死链：%s（文件不存在）" % url)
            continue
        if anchor and os.path.normpath(path).startswith(os.path.normpath(os.path.join(docs_dir, "todo"))):
            if anchor not in _anchors(path):
                fails.append("死链锚点：%s（附件中无 <a id=\"%s\">）" % (url, anchor))

    # 5) 孤儿附件（WARN）
    att_dir = os.path.join(docs_dir, "todo")
    if os.path.isdir(att_dir):
        for fn in sorted(os.listdir(att_dir)):
            if not fn.endswith(".md") or fn == "README.md":
                continue
            if ("todo/" + fn) not in raw:
                warns.append("孤儿附件：docs/todo/%s 未被 todo.md 引用" % fn)

    # 6) 未索引化启发式（WARN）：节内无链接且 >400B
    heads = [(m.start(), m.group(1)) for m in HEADING.finditer(raw)]
    for idx, (pos, h) in enumerate(heads):
        end = heads[idx + 1][0] if idx + 1 < len(heads) else len(raw)
        seg = raw[pos:end]
        if "]( " not in seg and "]( " not in seg and "](" not in seg and len(seg.encode("utf-8")) > 400:
            warns.append("未索引化：§%s 无详情链接且 %d B >400" % (h[:24], len(seg.encode("utf-8"))))
    return fails, warns


def run(todo_path, docs_dir):
    fails, warns = analyze(todo_path, docs_dir)
    if fails:
        sys.stdout.write("FAIL: 台账守卫未通过（%d 项）\n" % len(fails))
        for e in fails:
            sys.stdout.write("  - " + e + "\n")
        for w in warns:
            sys.stdout.write("  WARN " + w + "\n")
        return 1
    sys.stdout.write("PASS: todo.md = %d B / %d 行；无死链；WARN=%d\n"
                     % (os.path.getsize(todo_path), len(io.open(todo_path, encoding="utf-8").read().split("\n")), len(warns)))
    for w in warns:
        sys.stdout.write("  WARN " + w + "\n")
    return 0


def selftest():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        docs = os.path.join(td, "docs")
        att = os.path.join(docs, "todo")
        os.makedirs(att)
        io.open(os.path.join(att, "a.md"), "w", encoding="utf-8").write('# a\n<a id="x"></a>\n')
        good = os.path.join(docs, "todo.md")
        io.open(good, "w", encoding="utf-8").write("# t\n\n## 1. x\n\n| ID | 详情 |\n| --- | --- |\n| A | [a](todo/a.md#x) |\n")
        fails, warns = analyze(good, docs)
        if fails or warns:
            ok = False
            print("SELFTEST clean FAIL", fails, warns)
        dead = os.path.join(docs, "dead.md")
        txt = io.open(good, encoding="utf-8").read()
        io.open(dead, "w", encoding="utf-8").write(txt.replace("todo/a.md#x", "todo/missing.md"))
        f2, _ = analyze(dead, docs)
        if not any("死链" in x for x in f2):
            ok = False
            print("SELFTEST dead-link not caught", f2)
        io.open(os.path.join(att, "orphan.md"), "w", encoding="utf-8").write("# orphan\n")
        _, w3 = analyze(good, docs)
        if not any("孤儿" in x for x in w3):
            ok = False
            print("SELFTEST orphan not warned", w3)
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=os.path.join(os.path.dirname(__file__), "..", "docs", "todo.md"))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    path = os.path.abspath(args.file)
    return run(path, os.path.dirname(path))


if __name__ == "__main__":
    sys.exit(main())
