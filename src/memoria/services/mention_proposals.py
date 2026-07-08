"""S2：从 frontmatter concepts 首次出现段落提议 range。"""

from __future__ import annotations

import re

from memoria.range.constants import SNIPPET_MAX_LEN


def _normalize_name(s: str) -> str:
    return re.sub(r"\s+", "", s.lower())


def _line_mentions(line: str, name: str) -> bool:
    if not name or not line.strip():
        return False
    plain = line.replace("*", "").replace("`", "")
    if name in plain:
        return True
    # ε-greedy vs epsilon-greedy 等
    key = _normalize_name(name)
    return key in _normalize_name(plain)


def _is_heading(line: str) -> bool:
    return bool(re.match(r"^#{1,6}\s", line.strip()))


def _paragraph_end(lines: list[str], start_i: int) -> int:
    """从 start_i 到段落末（空行或标题前）。"""
    end_i = start_i
    for j in range(start_i + 1, len(lines)):
        stripped = lines[j].strip()
        if not stripped:
            break
        if _is_heading(lines[j]):
            break
        end_i = j
    return end_i


def _enclosing_heading_end(lines: list[str], start_i: int) -> int:
    """若段落过短，扩展到 enclosing ## 段末（下一同级标题前）。"""
    depth = 0
    heading_i = None
    for j in range(start_i, -1, -1):
        m = re.match(r"^(#{1,6})\s", lines[j].strip())
        if m:
            heading_i = j
            depth = len(m.group(1))
            break
    if heading_i is None:
        return _paragraph_end(lines, start_i)

    end_i = len(lines) - 1
    for j in range(heading_i + 1, len(lines)):
        m = re.match(r"^(#{1,6})\s", lines[j].strip())
        if m and len(m.group(1)) <= depth:
            end_i = j - 1
            break
    return max(end_i, start_i)


def propose_ranges_from_mentions(
    body: str,
    frontmatter: dict | None,
    *,
    skip_heading_lines: bool = True,
    min_paragraph_lines: int = 2,
) -> list[dict]:
    """为 fm.concepts 中尚未被标题覆盖的首次 mention 提议段落 range。"""
    concepts = (frontmatter or {}).get("concepts") or []
    if not concepts:
        return []

    lines = body.splitlines()
    proposals: list[dict] = []

    for concept in concepts:
        name = (concept.get("name") or concept.get("id") or "").strip()
        if not name:
            continue

        start_i = None
        for i, line in enumerate(lines):
            if skip_heading_lines and _is_heading(line):
                continue
            if _line_mentions(line, name):
                start_i = i
                break
        if start_i is None:
            continue

        end_i = _paragraph_end(lines, start_i)
        if end_i - start_i + 1 < min_paragraph_lines:
            end_i = _enclosing_heading_end(lines, start_i)

        start_line = lines[start_i].strip()
        end_line = lines[end_i].strip()
        proposals.append({
            "name": name,
            "strategy": "mention",
            "concept_id": concept.get("id"),
            "range": {
                "start": {"snippet": start_line[:SNIPPET_MAX_LEN], "line_hint": start_i + 1},
                "end": {"snippet": end_line[:SNIPPET_MAX_LEN], "line_hint": end_i + 1},
            },
            "proposed": True,
        })

    return proposals
