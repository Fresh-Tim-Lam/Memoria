"""Range 领域类型（snippet + line_hint 双端定位）。"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict


class RangeAnchor(TypedDict):
    snippet: str
    line_hint: NotRequired[int]


class RangeSpec(TypedDict):
    start: RangeAnchor
    end: RangeAnchor


class RangeResolved(TypedDict, total=False):
    ok: bool
    error: str
    start_line: int
    end_line: int
    start_candidates: list[int]
    end_candidates: list[int]


LocateError = Literal[
    "start_snippet_not_found",
    "end_snippet_not_found",
    "end_before_start",
    "missing_snippet",
]
