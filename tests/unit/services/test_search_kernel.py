"""Lexical SearchKernel 测试。"""

from pathlib import Path

from memoria.services.lexical_index import rebuild_lexical_index, search_lexical
from memoria.services.search_kernel import search, suggest_group_label, suggest_kp_merge

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "m3_rename_kb"


def test_search_finds_kp_by_name():
    kb = str(FIXTURE)
    rebuild_lexical_index(kb)
    res = search("待重命名", kb_path=kb, limit=10)
    assert res["available"] is True
    assert res["results"]
    hit = res["results"][0]
    assert hit["kp_id"] == "rename-kp"
    assert hit["file"] == "alpha.md"
    assert hit["score"] >= 65


def test_search_finds_kp_by_id():
    kb = str(FIXTURE)
    res = search_lexical("rename-kp", kb_path=kb, limit=5)
    assert res["available"] is True
    ids = [r["kp_id"] for r in res["results"]]
    assert "rename-kp" in ids


def test_search_empty_query():
    kb = str(FIXTURE)
    res = search("", kb_path=kb)
    assert res["available"] is True
    assert res["results"] == []


def test_search_no_kb():
    res = search("q", kb_path=None)
    assert res["available"] is False
    assert res["reason"] == "kb_not_open"


def test_search_file_scope():
    kb = str(FIXTURE)
    rebuild_lexical_index(kb)
    res = search("待重命名", kb_path=kb, scope="file", rel_path="alpha.md", limit=10)
    assert res["available"] is True
    assert res["scope"] == "file"
    assert res["results"]
    assert all(r["file"] == "alpha.md" for r in res["results"])

    res_other = search("待重命名", kb_path=kb, scope="file", rel_path="missing.md", limit=10)
    assert res_other["results"] == []


def test_search_semantic_mode_stub():
    from memoria.storage.ui_settings import save_ui_settings

    save_ui_settings({"search": {"embedding_enabled": False}})
    kb = str(FIXTURE)
    res = search("rename-kp", kb_path=kb, modes="semantic", limit=5)
    assert res["available"] is False
    assert res.get("reason") == "embedding_not_enabled"


def test_suggest_kp_merge_by_name():
    kb = str(FIXTURE)
    rebuild_lexical_index(kb)
    res = suggest_kp_merge("rename-kp", kb_path=kb, rel_path="alpha.md")
    assert res["available"] is True
    assert isinstance(res["suggestions"], list)


def test_suggest_group_label_uses_shared_tag():
    kb = str(FIXTURE)
    rebuild_lexical_index(kb)
    res = suggest_group_label(
        kb_path=kb,
        node_ids=["rename-kp"],
        hub_id="rename-kp",
        hub_name="待重命名",
    )
    assert res["available"] is True
    assert res.get("suggested")
