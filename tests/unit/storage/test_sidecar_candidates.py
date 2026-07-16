"""sidecar 候选字段校验（v1.5）。"""

from memoria.storage.sidecar_validate import validate_sidecar


def test_alias_and_description_candidates_valid():
    data = {
        "schema_version": 1,
        "file": "a.md",
        "knowledge_points": [
            {
                "id": "kp1",
                "name": "Test",
                "range": {
                    "start": {"snippet": "# Test"},
                    "end": {"snippet": "end."},
                },
                "alias_candidates": [
                    {"alias": "T1", "source": "feedback", "status": "candidate"},
                ],
                "description_candidates": [
                    {"text": "A summary.", "source": "system", "status": "candidate"},
                ],
            }
        ],
    }
    v = validate_sidecar(data, "a.md")
    assert v["ok"] is True


def test_tag_candidates_accepts_feedback_source():
    data = {
        "schema_version": 1,
        "file": "a.md",
        "knowledge_points": [
            {
                "id": "kp1",
                "name": "Test",
                "range": {
                    "start": {"snippet": "# Test"},
                    "end": {"snippet": "end."},
                },
                "tag_candidates": [
                    {"tag": "from-query", "source": "feedback"},
                ],
            }
        ],
    }
    v = validate_sidecar(data, "a.md")
    assert v["ok"] is True


def test_alias_candidates_rejects_bad_source():
    data = {
        "schema_version": 1,
        "file": "a.md",
        "knowledge_points": [
            {
                "id": "kp1",
                "name": "Test",
                "range": {
                    "start": {"snippet": "# Test"},
                    "end": {"snippet": "end."},
                },
                "alias_candidates": [{"alias": "x", "source": "magic"}],
            }
        ],
    }
    v = validate_sidecar(data, "a.md")
    assert v["ok"] is False
