#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""确定性规模档位生成器（tests/probe-kb/scale）。

用法：
    python tests/probe-kb/scale/gen_scale.py

行为：
    读取本文件内嵌的模板单元（UNIT），按倍数展开，生成
    scale-1k.md / scale-5k.md / scale-10k.md 三个文件，
    目标行数分别为 1000 / 5000 / 10000（精确命中）。

确定性：
    不使用任何随机数或时间；同一脚本重复执行，输出逐字节相同
    （固定 UTF-8 编码 + LF 换行 + 固定模板与拼接顺序）。

模板单元刻意混合多种块：标题 / 段落 / 有序与无序列表 / 表格 /
围栏代码块（python）/ 行内公式 / `$$` 公式块 / mermaid / 图片 /
wikilink —— 使每一档都同时具备规模与构造多样性。
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 一档 = 目标行数
TARGETS = {
    "scale-1k.md": 1000,
    "scale-5k.md": 5000,
    "scale-10k.md": 10000,
}

# 模板单元：末尾保留一个空行作为块分隔（保证拼接后 markdown 有效）。
UNIT = [
    "## 规模档位 · 单元 {i}",
    "",
    "这是用于压力测试的段落：中文连续文本、mixed English 文本，以及全角标点，。！？：；「」。",
    "",
    "- 列表项一",
    "- 列表项二",
    "  - 嵌套项 A",
    "  - 嵌套项 B",
    "",
    "1. 有序项一",
    "2. 有序项二",
    "",
    "| 列 A | 列 B | 列 C |",
    "|:---|:---:|---:|",
    "| 值 1 | 值 2 | 值 3 |",
    "| 值 4 | 值 5 | 值 6 |",
    "",
    "```python",
    "def f(x):",
    "    # 注释与 = 号 test",
    "    return x * 2",
    "```",
    "",
    "行内公式 $x^2 + y^2 = z^2$ 与行内代码 `code` 混排。",
    "",
    "$$",
    "\\int_0^1 x^2 \\, dx = \\tfrac{1}{3}",
    "$$",
    "",
    "```mermaid",
    "graph LR; A-->B;",
    "```",
    "",
    "![占位图](./.memoria/images/scale-placeholder-{i}.png)",
    "",
    "跳转示例：[[目标-规模-{i}]] 与 [[另一个链接-{i}]]。",
    "",
]

# 余数补齐用的独立段落行（每行自成一段，保证 markdown 有效）。
FILLER = [
    "填充段落（确定性，无随机）：用于把总行数精确补齐到目标档位。",
    "第二行填充文本；与上一行连续时合并为同一段，仍为有效 markdown。",
]


def build(target_lines: int) -> list:
    """按整单元展开到不超过目标行数，再用 FILLER 补齐到精确目标行数。"""
    lines = []
    i = 0
    while len(lines) + len(UNIT) <= target_lines:
        for tpl in UNIT:
            lines.append(tpl.replace("{i}", str(i)))
        i += 1
    k = 0
    while len(lines) < target_lines:
        lines.append(FILLER[k % len(FILLER)])
        k += 1
    return lines


def write_one(name: str, target_lines: int) -> None:
    lines = build(target_lines)
    text = "\n".join(lines) + "\n"
    path = HERE / name
    path.write_text(text, encoding="utf-8", newline="\n")
    size = len(text.encode("utf-8"))
    print(f"{name}: {len(lines)} lines, {size} bytes")


def main() -> None:
    for name, target in TARGETS.items():
        write_one(name, target)


if __name__ == "__main__":
    main()
