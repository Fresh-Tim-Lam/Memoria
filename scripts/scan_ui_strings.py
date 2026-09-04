#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UI 界面文案清单扫描器（i18n 盘点）。

范围：桌面应用前端界面文案（src/memoria/ui/static/app/index.html + app/js/*.js +
      app/css/*.css 的 content: 文案）。排除 lib/vendor/mathjax 等第三方库与
      纯注释文件。输出写入 docs/reference/i18n-inventory.md（可重复生成，
      迁移过程中人工维护「状态」口径见该文档头部说明）。

用法：python scripts/scan_ui_strings.py
"""
from __future__ import annotations

import io
import os
import re
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "src", "memoria", "ui", "static", "app")
OUT = os.path.join(ROOT, "docs", "reference", "i18n-inventory.md")

CJK = re.compile(r"[\u4e00-\u9fff]")
MAX_SNIP = 110
DEV_LOG_RE = re.compile(
    r"\bconsole\s*\.\s*[A-Za-z]+\s*\(|\b(?:syncLog|debugLog|traceLog|warnLog)\s*\(|\blog\s*\(\s*\"[A-Za-z_][A-Za-z0-9_]*\""
)


def iter_files():
    js_dir = os.path.join(APP, "js")
    css_dir = os.path.join(APP, "css")
    yield os.path.join(APP, "index.html")
    for fn in sorted(os.listdir(js_dir)):
        if fn.endswith(".js"):
            yield os.path.join(js_dir, fn)
    for fn in sorted(os.listdir(css_dir)):
        if fn.endswith(".css"):
            yield os.path.join(css_dir, fn)


def skip_comment_lines(lines, ext):
    """返回布尔列表 True=整行处于注释中。处理跨行块注释。"""
    in_block = False
    res = []
    for raw in lines:
        line = raw.strip()
        skip = False
        if in_block:
            skip = True
            if "*/" in line or ("-->" in line and ext == "html"):
                in_block = False
        else:
            if ext == "html":
                if line.startswith("<!--"):
                    skip = True
                    if "-->" not in line:
                        in_block = True
            elif ext in ("js", "css"):
                if line.startswith(("//", "/*", "*")):
                    skip = True
                    if line.startswith("/*") and "*/" not in line:
                        in_block = True
        res.append(skip)
    return res


def remove_inline_comments(raw, ext):
    """去除行内 // 与 /* */ 注释（字符串内不处理），返回剥离后的文本。"""
    out = []
    i, n = 0, len(raw)
    quote = None
    while i < n:
        ch = raw[i]
        if quote:
            out.append(ch)
            if ch == "\\":
                if i + 1 < n:
                    out.append(raw[i + 1])
                    i += 2
                    continue
            elif ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'`":
            quote = ch
            out.append(ch)
            i += 1
            continue
        two = raw[i : i + 2]
        if two == "//" and ext in ("js",):
            return "".join(out)
        if two == "/*" and ext in ("js", "css", "html"):
            j = raw.find("*/", i + 2)
            if j == -1:
                return "".join(out)
            i = j + 2
            continue
        if two == "<!--" and ext == "html":
            j = raw.find("-->", i + 4)
            if j == -1:
                return "".join(out)
            i = j + 3
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def snippet(line: str) -> str:
    m = CJK.search(line)
    if m:
        start = max(0, m.start() - 40)
        s = line[start : m.start() + 70].strip()
    else:
        s = line.strip()
    s = s.replace("|", "丨")
    if len(s) > MAX_SNIP:
        s = s[:MAX_SNIP] + "…"
    return s


def collect(rel_path, lines, skip):
    ext = os.path.splitext(rel_path)[1].lstrip(".").lower()
    rows = []
    for i, raw in enumerate(lines):
        if skip[i]:
            continue
        line = remove_inline_comments(raw, ext).strip()
        if not line:
            continue
        # 开发日志/控制台输出（console.*/syncLog 等）非产品界面文案，剔除
        if ext == "js" and DEV_LOG_RE.search(line):
            continue
        # 静态节点已挂 data-i18n/data-i18n-attr：界面文案由语言包驱动，
        # 标记行中的中文只是默认值/占位（i18n.md §2 硬规则），不再视为硬编码候选
        if ext == "html" and "data-i18n" in line:
            continue
        # css：仅 content: '文案'
        if ext == "css" and "content:" not in line:
            continue
        if not CJK.search(line):
            continue
        rows.append((i + 1, line, snippet(line)))
    return rows


def main():
    buf = []
    P = buf.append
    P("# UI 界面文案清单（i18n Inventory）")
    P("")
    P("> **用途**：登记桌面应用**前端界面**全部含中文的用户可见文案与定位（文件+行号），作为 i18n 迁移（抽键→语言包）与后续新增 UI 自查的依据。")
    P("> **目标读者**：项目负责人 / AI Agent（迁移文案、新增 UI、审阅语言包前必查）。")
    P("> **关联文档**：[i18n.md](../conventions/i18n.md)（语言系统维护规范）；[docs-management.md](../conventions/docs-management.md)（docs 组织规则）。")
    P("> **范围/边界**：仅统计 `src/memoria/ui/static/app/` 下 index.html、app/js/*.js、app/css 的 `content:` 文案；**不含** lib/vendor/mathjax 第三方库、纯注释文件（lexer/parser/ast 等中文均为注释，不属界面文案）；后端 Python 返回给界面的消息（document.py/import_engine.py/ui.py 等）为另一分区，机制落地后另行登记。")
    P("> **剔除规则**：开发日志 `console.*`/`syncLog` 等（i18n.md §2 非界面文案）；HTML 中已挂 `data-i18n`/`data-i18n-attr` 的静态节点（行内含标记即视为已迁移，中文仅为默认值/占位）。")
    P("> **生成**：`python scripts/scan_ui_strings.py`（确定性输出，可重复执行覆盖本文）。状态口径：`☐ 未迁移` 表示仍硬编码中文；迁移为 `t('key')` 后人工将对应文件状态置 `✔ 已迁移`（脚本重跑会重置，可在本文末尾「迁移记录」人工维护）。")
    P("> 生成日期：%s" % date.today().isoformat())
    P("")
    P("## 统计总览")
    P("")
    P("| 文件 | 含中文候选行数 | 状态 |")
    P("|------|------|------|")
    total = 0
    per = []
    for path in iter_files():
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        raw = io.open(path, encoding="utf-8", errors="replace").read()
        lines = raw.splitlines()
        ext = os.path.splitext(path)[1].lstrip(".").lower()
        skip = skip_comment_lines(lines, ext)
        rows = collect(rel, lines, skip)
        if not rows:
            continue
        per.append((rel, rows))
        total += len(rows)
    per.sort(key=lambda r: -len(r[1]))
    for rel, rows in per:
        P("| `%s` | %d | ☐ 未迁移 |" % (rel, len(rows)))
    P("| **合计** | **%d** | — |" % total)
    P("")
    P("## 逐文件清单")
    P("")
    for rel, rows in per:
        P("### %s" % rel)
        P("")
        for ln, line, sn in rows:
            P("- L%d: %s" % (ln, sn))
        P("")
    P("## 迁移记录")
    P("")
    P("| 日期 | 文件/区域 | 动作 | 结果 |")
    P("|------|------|------|------|")
    P("|（初始生成）| 全部 | 盘点登记 | — |")
    P("")
    io.open(OUT, "w", encoding="utf-8").write("\n".join(buf) + "\n")
    print("files=%d rows=%d -> %s" % (len(per), total, OUT))


if __name__ == "__main__":
    main()
