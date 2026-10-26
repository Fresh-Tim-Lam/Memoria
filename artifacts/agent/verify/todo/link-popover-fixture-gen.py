"""task-161 真机夹具 v2：多候选 5 个（3 类徽标）+ tags + 纯文件引用 + 区域缺失。

docs/a.md            单链接 [[target-kp|单目标]]；多链接 [[multi-kp|多目标]]（5 个候选）；断链 [[ghost-kp]]
docs/target.md       target-kp（range_ok, tags）+ target-second-kp（同文件第二个 KP，用于"按文件去重"验证）
docs/other.md        other-kp（range_ok, tags）
docs/plain-note.md   无 KP 的文件（纯文件引用：kp_id=None）
docs/broken-range.md norang-kp（range_ok=False：snippet 在正文中不存在）
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "artifacts" / "agent" / "verify" / "todo" / "link-popover-fixture"
KB = OUT / "kb"

A_MD = """# A 文档（链接面板 v2 探针）

单链接：[[target-kp|单目标]] 应出单候选面板（无列表）。

多链接：[[multi-kp|多目标]] 应出候选列表（知识点 / 纯文件引用 / 区域缺失三类）。

断链：[[ghost-kp]] 应走原有「编辑链接」弹窗。
"""
TARGET_MD = """# 目标文档

目标知识点第一行：这是被拉取到编辑区的区域正文。

目标知识点第二行：用于验证区域预览只取该知识点范围。

目标知识点第三行：区域结束标记。

## 第二个知识点

第二个知识点第一行：与 target-kp 同文件，用于验证按文件去重。
"""
OTHER_MD = """# 另一目标文档

另一个知识点第一行：多目标候选之一。

另一个知识点第二行：用于多候选列表预览。
"""
PLAIN_MD = """# 纯文件引用目标

这个文件没有任何知识点（sidecar 无 KP）。
链接指向它时，候选类型应为「纯文件引用」：kp_id=None、整文件预览、仍可拉到编辑区。
"""
BROKEN_RANGE_MD = """# 区域缺失目标

这个文件有一个知识点，但它的 range snippet 在正文中不存在。
"""


def sidecar(rel: str, kps: list[str], links: str | None = None) -> str:
    lines = ["schema_version: 1", "file: " + rel]
    if not kps:
        lines.append("knowledge_points: []")
    else:
        lines.append("knowledge_points:")
        lines.extend(kps)
    lines.append(links if links is not None else "links: []")
    lines.append("edges: []")
    return "\n".join(lines) + "\n"


def kp(kp_id: str, name: str, desc: str, tags: list[str], start: str, end: str,
       start_line: int, end_line: int, missing: bool = False) -> str:
    snippet_end = "不存在的结束片段 XYZ" if missing else end
    return "\n".join(
        [
            "- id: " + kp_id,
            "  name: " + name,
            "  description: " + desc,
            "  tags: [" + ", ".join(tags) + "]",
            "  tag_candidates: []",
            "  aliases: []",
            "  alias_candidates: []",
            "  description_candidates: []",
            "  range:",
            "    start:",
            "      snippet: '" + start + "'",
            "      line_hint: " + str(start_line),
            "    end:",
            "      snippet: '" + snippet_end + "'",
            "      line_hint: " + str(end_line),
        ]
    )


A_SIDECAR = sidecar(
    "docs/a.md", [],
    "links:\n"
    "- anchor_text: multi-kp\n"
    "  targets:\n"
    "  - target-kp\n"
    "  - target-second-kp\n"
    "  - other-kp\n"
    "  - plain-note\n"
    "  - norang-kp\n"
    "  instances:\n"
    "  - line: 5\n",
)


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT, ignore_errors=True)
    (KB / "docs").mkdir(parents=True)
    sc = KB / ".memoria" / "sidecars" / "docs"
    sc.mkdir(parents=True)
    now = datetime.now(timezone.utc).isoformat()
    (KB / ".memoria" / "manifest.yaml").write_text(
        "schema_version: 1\nupdated_at: '%s'\nfiles: []\n" % now, encoding="utf-8")
    (KB / ".memoria" / "pending.yaml").write_text(
        "schema_version: 1\nupdated_at: '%s'\nitems: []\n" % now, encoding="utf-8")
    for name, body in (("a.md", A_MD), ("target.md", TARGET_MD), ("other.md", OTHER_MD),
                       ("plain-note.md", PLAIN_MD), ("broken-range.md", BROKEN_RANGE_MD)):
        (KB / "docs" / name).write_text(body, encoding="utf-8", newline="\n")

    (sc / "a.memoria.yaml").write_text(A_SIDECAR, encoding="utf-8", newline="\n")
    (sc / "target.memoria.yaml").write_text(
        sidecar("docs/target.md", [
            kp("target-kp", "目标知识点", "这是目标知识点的 description（来自侧车）。",
               ["目标", "区域预览", "标签三", "标签四"], "# 目标文档",
               "目标知识点第三行：区域结束标记。", 1, 5),
            kp("target-second-kp", "第二知识点", "同文件第二个知识点，用于验证按文件去重。",
               ["第二"], "## 第二个知识点", "第二个知识点第一行：与 target-kp 同文件，用于验证按文件去重。", 7, 8),
        ]),
        encoding="utf-8", newline="\n")
    (sc / "other.memoria.yaml").write_text(
        sidecar("docs/other.md", [
            kp("other-kp", "另一知识点", "这是另一知识点的 description。",
               ["对照"], "# 另一目标文档", "另一个知识点第二行：用于多候选列表预览。", 1, 4),
        ]),
        encoding="utf-8", newline="\n")
    (sc / "broken-range.memoria.yaml").write_text(
        sidecar("docs/broken-range.md", [
            kp("norang-kp", "区域缺失知识点", "有 KP 但 range snippet 不存在（构造样本）。",
               ["构造"], "# 区域缺失目标", "结束片段", 1, 3, missing=True),
        ]),
        encoding="utf-8", newline="\n")
    print("fixture:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
