# -*- coding: utf-8 -*-
"""task-170 真机夹具：分栏编辑 mermaid 源码的复现文档（长文档 + mermaid 块在中部）。"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "artifacts" / "agent" / "verify" / "todo" / "split-mermaid-fixture"
KB = OUT / "kb"

PARAS = []
for i in range(1, 451):
    PARAS.append(f"第 {i} 段：这是用于把 mermaid 块推到文档中部、让源码区可滚动而构造的长正文。")
    PARAS.append("")

BEFORE = "\n".join(PARAS[:600])
AFTER = "\n".join(PARAS[600:])

DOC = (
    "# Mermaid 分栏编辑复现\n\n"
    + BEFORE
    + "\n## 图形\n\n"
    + "```mermaid\n"
    + "graph TD\n"
    + "  A[开始] --> B[处理]\n"
    + "  B --> C[结束]\n"
    + "```\n\n"
    + "## 代码块\n\n```js\nconst a = 1;\nconst b = 2;\n```\n\n"
    + "## 公式块\n\n$$\nx + y = z\n$$\n\n"
    + "## 表格\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n"
    + AFTER
    + "\n## 文末\n\n最后一行。\n"
)


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT, ignore_errors=True)
    (KB / "docs").mkdir(parents=True)
    (KB / ".memoria" / "sidecars" / "docs").mkdir(parents=True)
    now = datetime.now(timezone.utc).isoformat()
    (KB / ".memoria" / "manifest.yaml").write_text(
        "schema_version: 1\nupdated_at: '%s'\nfiles: []\n" % now, encoding="utf-8")
    (KB / ".memoria" / "pending.yaml").write_text(
        "schema_version: 1\nupdated_at: '%s'\nitems: []\n" % now, encoding="utf-8")
    (KB / "docs" / "mermaid-edit.md").write_text(DOC, encoding="utf-8", newline="\n")
    (KB / ".memoria" / "sidecars" / "docs" / "mermaid-edit.memoria.yaml").write_text(
        "schema_version: 1\nfile: docs/mermaid-edit.md\nknowledge_points: []\nlinks: []\nedges: []\n",
        encoding="utf-8", newline="\n")
    print("fixture:", OUT, "lines:", len(DOC.splitlines()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
