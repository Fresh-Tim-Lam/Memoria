"""正文定位搜索。"""

from pathlib import Path

from memoria.services.body_locate import search_body_locate
from memoria.services.search_kernel import search
from memoria.storage.ui_settings import save_ui_settings

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "m4_merge_kb"


def test_body_locate_finds_line():
    kb = str(FIXTURE)
    hits = search_body_locate("离散控制", kb_path=kb, limit=5)
    assert hits
    assert hits[0]["kind"] == "body-locate"
    assert hits[0]["file"] == "tag-bridge-b.md"
    assert hits[0]["line"] >= 1


def test_search_attaches_body_locate_when_enabled():
    save_ui_settings({"search": {"body_locate_enabled": True, "embedding_enabled": False}})
    try:
        kb = str(FIXTURE)
        res = search("烹饪", kb_path=kb, limit=5)
        assert res["available"] is True
        assert res.get("body_locate")
        files = {h["file"] for h in res["body_locate"]}
        assert "unrelated.md" in files
    finally:
        save_ui_settings({"search": {"body_locate_enabled": False}})


def test_search_body_locate_off_by_default():
    save_ui_settings({"search": {"body_locate_enabled": False}})
    kb = str(FIXTURE)
    res = search("烹饪", kb_path=kb, limit=5)
    assert res.get("body_locate") == []
