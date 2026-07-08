"""检查报告：统一错误/警告计数（与 UI 展示规则一致）。"""

from __future__ import annotations


def normalize_check_severity(severity: str | None, *, default: str = "warning") -> str:
    """与前端 checkItemHtml 一致：仅 ``error`` 为错误，其余为警告。"""
    s = (severity or default).lower()
    return "error" if s == "error" else "warning"


def summarize_check_counts(
    *,
    kb_integrity: dict,
    manifest_diff: dict,
    path_moves: list[dict],
    files_report: list[dict],
    graph_audit: dict,
) -> tuple[int, int]:
    """按各条目的 severity 汇总，保证与检查面板徽章一致。"""
    errors = 0
    warnings = 0

    def add(severity: str | None, *, default: str = "warning") -> None:
        nonlocal errors, warnings
        if normalize_check_severity(severity, default=default) == "error":
            errors += 1
        else:
            warnings += 1

    for issue in kb_integrity.get("errors") or []:
        add(issue.get("severity"), default="error")
    for issue in kb_integrity.get("warnings") or []:
        add(issue.get("severity"), default="warning")
    for move in path_moves or []:
        add(move.get("severity"), default="error")
    for issue in manifest_diff.get("errors") or []:
        add(issue.get("severity"), default="error")
    for issue in manifest_diff.get("warnings") or []:
        add(issue.get("severity"), default="warning")
    for fr in files_report or []:
        errors += len(fr.get("errors") or [])
        warnings += len(fr.get("warnings") or [])
    for gf in graph_audit.get("files") or []:
        for issue in gf.get("issues") or []:
            add(issue.get("severity"), default="warning")

    return errors, warnings
