# -*- coding: utf-8 -*-
"""px → rem 批量转换（基准 16px）。

转换规则：
- 转换列表内属性的 px 值 → rem（保留最多 4 位小数，去尾零）
- 保留 px：border*/outline*/box-shadow/border-radius/transform/媒体查询断点/@keyframes 内
"""
import re
import sys

BASE = 16.0

# 参与 rem 化的属性（精确匹配属性名；简写 border/margin 等不匹配这里，因为带方向后缀）
CONVERT = re.compile(
    r"(?<![\w-])("
    r"font-size|padding|padding-top|padding-right|padding-bottom|padding-left|"
    r"margin|margin-top|margin-right|margin-bottom|margin-left|"
    r"width|height|min-width|max-width|min-height|max-height|"
    r"top|right|bottom|left|inset|"
    r"gap|row-gap|column-gap|letter-spacing|text-indent|line-height|flex-basis|"
    r"text-underline-offset|vertical-align"
    r")\s*:\s*([\d.]+)px"
)

SKIP_LINE = re.compile(r"^\s*@(media|supports|keyframes|container)\b")
KEYFRAME_BLOCK = re.compile(r"^\s*@keyframes\b")


def fmt(n: float) -> str:
    v = round(n / BASE, 4)
    # 去尾零
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s if s else "0"


def convert_line(line: str, in_keyframes: bool) -> str:
    if in_keyframes:
        return line
    if SKIP_LINE.match(line):
        return line
    return CONVERT.sub(lambda m: f"{m.group(1)}: {fmt(float(m.group(2)))}rem", line)


def process(path: str) -> tuple[int, int]:
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    total = 0
    in_kf = False
    for i, ln in enumerate(lines):
        if KEYFRAME_BLOCK.match(ln):
            in_kf = True
        elif in_kf and ln.strip() == "}":
            in_kf = False
        before = len(CONVERT.findall(ln))
        new = convert_line(ln, in_kf)
        if new != ln:
            lines[i] = new
            total += before
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.writelines(lines)
    return total, len(lines)


def main() -> None:
    files = sys.argv[1:]
    if not files:
        print("usage: python _px2rem.py <css...>")
        return
    for p in files:
        n, total_lines = process(p)
        print(f"{p}: converted {n} px -> rem ({total_lines} lines)")


if __name__ == "__main__":
    main()
