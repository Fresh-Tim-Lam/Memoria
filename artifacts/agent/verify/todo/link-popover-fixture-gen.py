"""task-145 真机夹具：单链接 / 多目标链接 / 断链 + 带 description 与区域范围的 KP。

KB 结构（全部在 artifacts/agent/verify/todo/link-popover-fixture/kb）：
  docs/a.md          —— 单链接 [[target-kp|单目标]] / 多目标 [[multi-kp|多目标]] / 断链 [[ghost-kp]]
  docs/target.md     —— KP target-kp（description + 区域行 1-5）
  docs/other.md      —— KP other-kp（description + 区域行 1-5）
  .memoria/sidecars/docs/*.memoria.yaml —— 侧车（KP/链接池）
  .memoria/manifest.yaml / pending.yaml  —— 最小 KB 装载文件
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "artifacts" / "agent" / "verify" / "todo" / "link-popover-fixture"
KB = OUT / "kb"

A_MD = """# A 文档（链接浮层探针）

单链接：[[target-kp|单目标]] 应出单卡片浮层。

多链接：[[multi-kp|多目标]] 应出候选列表 + 全部打开。

断链：[[ghost-kp]] 应走原有「编辑链接」弹窗。
"""
TARGET_MD = """# 目标文档

目标知识点第一行：这是被拉取到编辑区的区域正文。

目标知识点第二行：用于验证区域预览只取该知识点范围。

目标知识点第三行：区域结束标记。
"""
OTHER_MD = """# 另一目标文档

另一个知识点第一行：多目标候选之一。

另一个知识点第二行：用于多候选列表预览。
"""


def kp_yaml(kp_id: str, name: str, desc: str, start: str, end: str, start_line: int, end_line: int) -> str:
    return "\n".join(
        [
            "schema_version: 1",
            "file: docs/{}".format("target.md" if kp_id == "target-kp" else "other.md"),
            "knowledge_points:",
            "- id: {}".format(kp_id),
            "  name: {}".format(name),
            "  description: {}".format(desc),
            "  range:",
            "    start:",
            "      snippet: '{}'".format(start),
            "      line_hint: {}".format(start_line),
            "    end:",
            "      snippet: '{}'".format(end),
            "      line_hint: {}".format(end_line),
            "links: []",
            "edges: []",
            "",
        ]
    )


A_SIDECAR = """schema_version: 1
file: docs/a.md
knowledge_points: []
links:
- anchor_text: multi-kp
  targets:
  - target-kp
  - other-kp
  instances:
  - line: 5
edges: []
"""


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
    (KB / "docs" / "a.md").write_text(A_MD, encoding="utf-8", newline="\n")
    (KB / "docs" / "target.md").write_text(TARGET_MD, encoding="utf-8", newline="\n")
    (KB / "docs" / "other.md").write_text(OTHER_MD, encoding="utf-8", newline="\n")
    sc = KB / ".memoria" / "sidecars" / "docs"
    (sc / "a.memoria.yaml").write_text(A_SIDECAR, encoding="utf-8", newline="\n")
    (sc / "target.memoria.yaml").write_text(
        kp_yaml("target-kp", "目标知识点", "这是目标知识点的 description（来自侧车）。",
                "# 目标文档", "目标知识点第三行：区域结束标记。", 1, 5),
        encoding="utf-8", newline="\n")
    (sc / "other.memoria.yaml").write_text(
        kp_yaml("other-kp", "另一知识点", "这是另一知识点的 description。",
                "# 另一目标文档", "另一个知识点第二行：用于多候选列表预览。", 1, 4),
        encoding="utf-8", newline="\n")
    print("fixture:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
