"""Lexical v2 倒排索引测试。"""

from pathlib import Path

from memoria.services.lexical_index import (
    SCHEMA_VERSION,
    build_lexical_index,
    rebuild_lexical_index,
    search_lexical,
)
from memoria.services.lexical_tokenizer import tokenize

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "m3_rename_kb"


def test_build_index_v2_has_inverted():
    kb = str(FIXTURE)
    index = rebuild_lexical_index(kb)
    assert index["schema_version"] == SCHEMA_VERSION
    assert index["token_count"] > 0
    assert isinstance(index.get("inverted"), dict)
    assert index["inverted"]


def test_tokenize_chinese():
    toks = tokenize("待重命名知识点")
    assert toks
    assert "待重命名知识点" in toks or any("待" in t or "重命名" in t for t in toks)


def test_search_via_inverted_chinese_name():
    kb = str(FIXTURE)
    rebuild_lexical_index(kb)
    res = search_lexical("重命名", kb_path=kb, limit=5)
    assert res["results"]
    assert res["results"][0]["kp_id"] == "rename-kp"
