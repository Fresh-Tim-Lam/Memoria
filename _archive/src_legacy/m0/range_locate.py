"""M0：snippet + line_hint 双端 range 重定位"""

from __future__ import annotations

SNIPPET_MAX_LEN = 80
HINT_WINDOW = 40


def _norm(line: str) -> str:
    return line.strip()


def _truncate(snippet: str) -> str:
    s = _norm(snippet)
    if len(s) > SNIPPET_MAX_LEN:
        return s[:SNIPPET_MAX_LEN]
    return s


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

    if line_hint is not None and line_hint >= 1:
        h = line_hint - 1
        scan(max(start, h - HINT_WINDOW), min(len(lines), h + HINT_WINDOW + 1))
    if not candidates and not forward_only:
        scan(start, len(lines))
    elif not candidates and forward_only:
        scan(start, len(lines))

    if not candidates:
        return None, []

    if line_hint is not None and line_hint >= 1:
        hint = line_hint - 1
        best = min(candidates, key=lambda i: abs(i - hint))
        return best, candidates

    return candidates[0], candidates


def resolve_range(
    lines: list[str],
    start_spec: dict,
    end_spec: dict,
) -> dict:
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
