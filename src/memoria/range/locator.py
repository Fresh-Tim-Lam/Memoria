"""snippet + line_hint 双端 range 重定位。"""

from __future__ import annotations

from memoria.domain.range import RangeResolved
from memoria.range.constants import HINT_WINDOW, SNIPPET_MAX_LEN


def _norm(line: str) -> str:
    return line.strip()


def _truncate(snippet: str) -> str:
    s = _norm(snippet)
    return s[:SNIPPET_MAX_LEN] if len(s) > SNIPPET_MAX_LEN else s


def locate_snippet(
    lines: list[str],
    snippet: str,
    line_hint: int | None = None,
    search_from: int = 0,
    forward_only: bool = False,
) -> tuple[int | None, list[int]]:
    """在 lines 中定位 snippet。返回 (0-based line index, 所有候选 indices)。"""
    needle = _truncate(snippet)
    if not needle:
        return None, []

    candidates: list[int] = []
    start = max(0, search_from) if forward_only else 0

    def scan(i0: int, i1: int) -> None:
        for i in range(i0, min(i1, len(lines))):
            if needle in _norm(lines[i]):
                candidates.append(i)

    # Trust line_hint first: if the hint line contains the snippet, use it
    # directly without searching the full window. This prevents the locator
    # from matching an earlier occurrence of the same snippet text.
    if line_hint is not None and 1 <= line_hint <= len(lines):
        h = line_hint - 1
        if needle in _norm(lines[h]):
            # Build candidate list from the window for transparency, but
            # pin the result to the hint line.
            scan(max(start, h - HINT_WINDOW), min(len(lines), h + HINT_WINDOW + 1))
            return h, candidates or [h]

    if line_hint is not None and line_hint >= 1:
        h = line_hint - 1
        scan(max(start, h - HINT_WINDOW), min(len(lines), h + HINT_WINDOW + 1))
    if not candidates:
        scan(start, len(lines))

    if not candidates:
        return None, []

    if line_hint is not None and line_hint >= 1:
        hint = line_hint - 1
        return min(candidates, key=lambda i: abs(i - hint)), candidates

    return candidates[0], candidates


def resolve_range(
    lines: list[str],
    start_spec: dict,
    end_spec: dict,
) -> RangeResolved:
    """解析 KP range，返回 line 区间与状态。"""
    s_idx, s_cands = locate_snippet(
        lines,
        start_spec.get("snippet", ""),
        start_spec.get("line_hint"),
        search_from=0,
        forward_only=False,
    )
    if s_idx is None:
        return {
            "ok": False,
            "error": "start_snippet_not_found",
            "start_candidates": s_cands,
            "end_candidates": [],
        }

    e_idx, e_cands = locate_snippet(
        lines,
        end_spec.get("snippet", ""),
        end_spec.get("line_hint"),
        search_from=s_idx,
        forward_only=True,
    )
    if e_idx is None:
        return {
            "ok": False,
            "error": "end_snippet_not_found",
            "start_line": s_idx + 1,
            "start_candidates": s_cands,
            "end_candidates": e_cands,
        }

    if e_idx < s_idx:
        return {
            "ok": False,
            "error": "end_before_start",
            "start_line": s_idx + 1,
            "end_line": e_idx + 1,
            "start_candidates": s_cands,
            "end_candidates": e_cands,
        }

    return {
        "ok": True,
        "start_line": s_idx + 1,
        "end_line": e_idx + 1,
        "start_candidates": s_cands,
        "end_candidates": e_cands,
    }
