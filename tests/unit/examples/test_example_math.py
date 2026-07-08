"""检查 examples/*.md 是否含未用 $ 包裹的伪公式行。"""

from __future__ import annotations

import re
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[3] / "examples"

MATH_RE = re.compile(
    r"[=^\\_∈Σπγαβτελρσφω√·←→]|"
    r"\\sum|\\prod|\\max|\\min|\\exp|"
    r"\bsoftmax\b|\bscore\s*\(|\bQ\s*\(|\bV\s*\^|\bE_|"
    r"\bmax_\{|\|S\||∇"
)

SKIP_PREFIX = re.compile(r"^(#{1,6}\s|[-*+]\s|\d+\.\s|>|```|---|\[\[)")


def has_math_delimiters(line: str) -> bool:
    return bool(re.search(r"\$\$|\$[^$\n]+\$|\\\(|\\\[", line))


def chinese_ratio(line: str) -> float:
    m = re.findall(r"[\u4e00-\u9fff]", line)
    return len(m) / len(line) if line else 0.0


def is_bare_formula_line(line: str) -> bool:
    t = line.strip()
    if not t or t == "$$":
        return False
    if SKIP_PREFIX.match(t):
        return False
    if has_math_delimiters(t):
        return False
    if not MATH_RE.search(t):
        return False
    if chinese_ratio(t) > 0.35:
        return False
    return True


def scan_examples() -> list[tuple[str, int, str]]:
    issues: list[tuple[str, int, str]] = []
    for md in sorted(EXAMPLES.glob("*.md")):
        if md.name.startswith("."):
            continue
        text = md.read_text(encoding="utf-8")
        in_fm = False
        in_block = False
        for i, line in enumerate(text.splitlines(), 1):
            if i == 1 and line.strip() == "---":
                in_fm = True
                continue
            if in_fm:
                if line.strip() == "---":
                    in_fm = False
                continue
            if line.strip() == "$$":
                in_block = not in_block
                continue
            if in_block:
                continue
            if is_bare_formula_line(line):
                issues.append((md.name, i, line.strip()[:72]))
    return issues


def test_all_examples_have_delimited_math():
    issues = scan_examples()
    assert not issues, "未包裹公式:\n" + "\n".join(
        f"  {f}:{ln}: {txt}" for f, ln, txt in issues
    )
