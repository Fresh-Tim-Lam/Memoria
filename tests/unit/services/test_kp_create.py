"""KP 新建与 id 校验。"""

from __future__ import annotations

from memoria.services.document import DocumentService


def _write_two_file_kb(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "a.md").write_text("# Alpha\n\nAlpha body.\n", encoding="utf-8")
    (kb / "b.md").write_text("# Beta\n\nBeta body.\n", encoding="utf-8")
    sidecar = kb / ".memoria" / "sidecars"
    sidecar.mkdir(parents=True)
    (sidecar / "a.memoria.yaml").write_text(
        """schema_version: 1
file: a.md
knowledge_points:
- id: shared-id
  name: Alpha
  range:
    start: {snippet: '# Alpha', line_hint: 1}
    end: {snippet: Alpha body., line_hint: 2}
links: []
""",
        encoding="utf-8",
    )
    return kb


def test_check_kp_id_available(tmp_path):
    kb = _write_two_file_kb(tmp_path)
    svc = DocumentService(kb_path=str(kb))
    assert svc.check_kp_id("new-kp")["available"] is True
    assert svc.check_kp_id("shared-id")["available"] is False
    assert svc.check_kp_id("shared-id", "a.md")["available"] is True
    assert svc.check_kp_id("shared-id", "a.md")["exists_in_file"] is True


def test_confirm_kp_range_creates_new_kp(tmp_path):
    kb = _write_two_file_kb(tmp_path)
    svc = DocumentService(kb_path=str(kb))
    res = svc.confirm_kp_range("b.md", "beta-kp", "Beta KP", 1, 3)
    assert res["status"] == "ok", res.get("message")
    ids = [k["id"] for k in res["knowledge_points"]]
    assert "beta-kp" in ids


def test_confirm_kp_range_rejects_global_duplicate(tmp_path):
    kb = _write_two_file_kb(tmp_path)
    svc = DocumentService(kb_path=str(kb))
    res = svc.confirm_kp_range("b.md", "shared-id", "Dup", 1, 2)
    assert res["status"] == "error"
    assert "已存在" in res.get("message", "")


def test_confirm_kp_range_rejects_empty_end_line(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "a.md").write_text("## Title\n\nBody.\n\n\nTail.\n", encoding="utf-8")
    svc = DocumentService(kb_path=str(kb))
    res = svc.confirm_kp_range("a.md", "kp", "KP", 1, 4)
    assert res["status"] == "error"
    assert "为空" in res.get("message", "")


def test_search_api_lexical(tmp_path):
    kb = _write_two_file_kb(tmp_path)
    svc = DocumentService(kb_path=str(kb))
    res = svc.search_api("alpha")
    assert res["status"] == "ok"
    assert res["available"] is True
    assert isinstance(res["results"], list)
