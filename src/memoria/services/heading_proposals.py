"""标题辅助：为 ##–###### 提议候选 range。"""

from __future__ import annotations

import re

from memoria.range.constants import SNIPPET_MAX_LEN

_HEADING_RE = re.compile(r"^(#{2,6})\s+")


def propose_ranges_from_headings(body: str) -> list[dict]:
    lines = body.splitlines()
    headings: list[tuple[int, int, str]] = []
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m:
            headings.append((i, len(m.group(1)), line.strip()))

    proposals: list[dict] = []
    for idx, (line_i, depth, title) in enumerate(headings):
        end_i = len(lines) - 1
        for j in range(idx + 1, len(headings)):
            next_i, next_d, _ = headings[j]
            if next_d <= depth:
                end_i = next_i - 1
                break
        while end_i > line_i and not lines[end_i].strip():
            end_i -= 1
        end_line = lines[end_i].strip() if end_i >= line_i else title
        proposals.append({
            "name": title.lstrip("#").strip(),
            "range": {
                "start": {"snippet": title, "line_hint": line_i + 1},
                "end": {"snippet": end_line[:SNIPPET_MAX_LEN], "line_hint": end_i + 1},
            },
            "proposed": True,
        })
    return proposals
