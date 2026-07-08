"""S5：定义句模式提议 KP range。"""

from __future__ import annotations

import re

from memoria.range.constants import SNIPPET_MAX_LEN
from memoria.services.mention_proposals import _enclosing_heading_end, _is_heading, _paragraph_end

_NAME_CHARS = r"[^\s，,。.!！?？；;：:\"'()（）\[\]{}<>《》「」『』]{2,48}"

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "所谓",
        re.compile(rf"所谓[「\"']?(?P<name>{_NAME_CHARS})[」\"']?"),
    ),
    (
        "paren-en",
        re.compile(rf"(?P<name>{_NAME_CHARS})\s*[（(][A-Za-z][^）)]{{1,48}}[）)]"),
    ),
    (
        "是",
        re.compile(rf"(?P<name>{_NAME_CHARS})\s*是(?:指|一种|一个|用于)?"),
    ),
    (
        "指的是",
        re.compile(rf"(?P<name>{_NAME_CHARS})\s*指的是"),
    ),
    (
        "定义为",
        re.compile(rf"(?P<name>{_NAME_CHARS})\s*定义为"),
    ),
]


def _normalize_name(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").lower())


def _clean_name(raw: str) -> str:
    name = (raw or "").strip().strip("「」\"'《》")
    name = re.sub(r"\s+", " ", name)
    return name[:80]


def _extend_for_examples(lines: list[str], end_i: int) -> int:
    """定义段后若紧跟非空段（例证），纳入 range。"""
    i = end_i + 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or _is_heading(lines[i]):
        return end_i
    if re.match(r"^[-*+]\s", lines[i].strip()) or re.match(r"^\d+[.)]\s", lines[i].strip()):
        return _paragraph_end(lines, i)
    return end_i


def propose_ranges_from_definitions(body: str) -> list[dict]:
    lines = body.splitlines()
    proposals: list[dict] = []
    seen_names: set[str] = set()
    in_code = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not stripped or _is_heading(line):
            continue

        for _kind, pat in _PATTERNS:
            m = pat.search(stripped)
            if not m:
                continue
            name = _clean_name(m.group("name"))
            if len(name) < 2:
                continue
            key = _normalize_name(name)
            if key in seen_names:
                break
            seen_names.add(key)

            start_i = i
            end_i = _paragraph_end(lines, start_i)
            if end_i - start_i < 1:
                end_i = _enclosing_heading_end(lines, start_i)
            end_i = _extend_for_examples(lines, end_i)

            start_line = lines[start_i].strip()
            end_line = lines[end_i].strip()
            proposals.append({
                "name": name,
                "strategy": "definition",
                "definition_kind": _kind,
                "range": {
                    "start": {
                        "snippet": start_line[:SNIPPET_MAX_LEN],
                        "line_hint": start_i + 1,
                    },
                    "end": {
                        "snippet": end_line[:SNIPPET_MAX_LEN],
                        "line_hint": end_i + 1,
                    },
                },
                "proposed": True,
            })
            break

    return proposals
