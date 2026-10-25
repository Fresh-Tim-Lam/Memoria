"""task-134 修复：把「文档资源附件」块（原 L7118-7282，IIFE 门面 return 之后）整体前移到 return 之前。

纯搬运：块内逻辑一行不改；只更新块头「落点纪律」注释（改成正确说法 + 历史锚，Lead 加码 1）。
"""

from __future__ import annotations

from pathlib import Path

PATH = Path(r"D:\AAA_Jupyter\Memoria\src\memoria\ui\static\app\js\agent-panel.js")
lines = PATH.read_text(encoding="utf-8").splitlines(keepends=True)

# 1) 定位块：分隔线 + "2026-10-13 追加：**文档资源附件**"
start = None
for i, line in enumerate(lines):
    if "2026-10-13 追加：**文档资源附件**" in line:
        start = i - 1
        break
assert start is not None, "找不到文档资源附件块"
assert lines[start].strip().startswith("// ═"), lines[start][:60]

# 末尾 `})();` 是最后一行；块 = start .. len-2（去掉其前的空行）
end = len(lines) - 1
assert lines[end].strip() == "})();", lines[end][:40]
# 找块的实际结束：从本块之后到 `})();` 之前，只应有空行
block = lines[start:end]
while block and not block[-1].strip():
    block.pop()
assert block, "块为空"

# 2) 删除原块
del lines[start:end]

# 3) 插入到门面 `  return {` 之前
insert_at = None
for i in range(len(lines) - 1, -1, -1):
    if lines[i].rstrip("\n") == "  return {":
        insert_at = i
        break
assert insert_at is not None, "找不到门面 return {"
if not block[-1].endswith("\n"):
    block[-1] += "\n"
block.append("\n")
lines[insert_at:insert_at] = block

text = "".join(lines)

# 4) 修正块头的错误约定注释（正确说法 + 历史锚；Lead 加码 1）
old_rule = (
    "  //   落点纪律：整块追加在 IIFE 末尾（`})();` 之前）；需要改既有行为处一律**按名包装**\n"
    "  //   （`intakeImageFiles` / `renderAttachStrip` / `callAskStart`）⇒ 上方所有 `<文件>:<行号>` 锚点零漂移。\n"
)
new_rule = (
    "  //   落点纪律：整块追加在 IIFE 内、门面 `return {` **之前**。\n"
    "  //   `return` 之后的顶层语句**永不执行**（只有 `function` 声明会 hoist，但同样不该放那里）。\n"
    "  //   历史（2026-10-25 task-134 取证）：2f9a88f9(09-19) 起 11 个 commit / 19 个块都遵守「return 之前」的正确写法；\n"
    "  //   1fe97fa7(10-19) 误改成「`})();` 之前」，导致**本块出生即死**（10-19~10-25 用户拖 PDF/Word/TXT/MD 一律报「只支持图片」）。\n"
    "  //   需要改既有行为处一律**按名包装**（`intakeImageFiles` / `renderAttachStrip` / `callAskStart`）⇒ 不改既有函数体。\n"
)
assert old_rule in text, "找不到待替换的落点纪律注释"
text = text.replace(old_rule, new_rule, 1)

PATH.write_text(text, encoding="utf-8")
new_lines = text.splitlines()
print("block moved:", len(block), "lines")
print("new total:", len(new_lines), "lines")
for i, l in enumerate(new_lines, 1):
    if "落点纪律" in l and "return {` **之前**" in l:
        print("new rule at line", i)
    if l.rstrip() == "  return {":
        print("facade return now at line", i)
    if l.strip() == "})();":
        print("iife close at line", i)
