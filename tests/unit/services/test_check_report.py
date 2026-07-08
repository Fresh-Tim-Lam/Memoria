"""check_report 计数与 UI 规则一致。"""

from __future__ import annotations

from memoria.services.check_report import normalize_check_severity, summarize_check_counts


def test_normalize_check_severity():
    assert normalize_check_severity("error") == "error"
    assert normalize_check_severity("warn") == "warning"
    assert normalize_check_severity("warning") == "warning"
    assert normalize_check_severity(None) == "warning"


def test_summarize_graph_audit_as_warnings_only():
    errors, warnings = summarize_check_counts(
        kb_integrity={"errors": [], "warnings": []},
        manifest_diff={"errors": [], "warnings": []},
        path_moves=[],
        files_report=[],
        graph_audit={
            "files": [
                {
                    "file": "a.md",
                    "issues": [
                        {"severity": "warning", "message": "gap"},
                        {"severity": "warn", "message": "legacy"},
                    ],
                }
            ]
        },
    )
    assert errors == 0
    assert warnings == 2


def test_summarize_path_moves_as_errors():
    errors, warnings = summarize_check_counts(
        kb_integrity={"errors": [], "warnings": []},
        manifest_diff={"errors": [], "warnings": []},
        path_moves=[{"severity": "error", "from": "a.md", "to": "b.md"}],
        files_report=[],
        graph_audit={"files": []},
    )
    assert errors == 1
    assert warnings == 0
