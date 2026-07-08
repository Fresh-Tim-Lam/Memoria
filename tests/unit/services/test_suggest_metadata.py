"""metadata suggest 测试。"""

from memoria.services.suggest_metadata import suggest_description, suggest_tags


def test_suggest_description_first_sentence():
    kp = {
        "id": "demo",
        "name": "Demo",
        "range": {"start": {"line_hint": 1}, "end": {"line_hint": 3}},
    }
    lines = ["# Demo", "", "这是第一句。这是第二句。"]
    res = suggest_description(
        kb_path=None,
        rel_path="demo.md",
        kp_id="demo",
        lines=lines,
        kp=kp,
    )
    assert "这是第一句" in res["suggested"]


def test_suggest_tags_from_vocab(tmp_path):
    kb = tmp_path / "kb"
    md = kb / "a.md"
    sc_dir = kb / ".memoria" / "sidecars"
    sc_dir.mkdir(parents=True)
    md.write_text("# A\n\nRL policy gradient.\n", encoding="utf-8")
    sc_dir.joinpath("a.memoria.yaml").write_text(
        """schema_version: 1
file: a.md
knowledge_points:
- id: src-kp
  name: Source
  tags: [rl, policy]
  range:
    start: {line_hint: 1}
    end: {line_hint: 3}
""",
        encoding="utf-8",
    )
    kp = {
        "id": "tgt-kp",
        "name": "Target",
        "tags": [],
        "range": {"start": {"line_hint": 1}, "end": {"line_hint": 3}},
    }
    from memoria.services.lexical_index import rebuild_lexical_index

    rebuild_lexical_index(str(kb))
    res = suggest_tags(
        kb_path=str(kb),
        rel_path="a.md",
        kp_id="tgt-kp",
        lines=md.read_text(encoding="utf-8").splitlines(),
        kp=kp,
        limit=5,
    )
    tags = [s["tag"] for s in res["suggestions"]]
    assert "rl" in tags or "policy" in tags


def test_suggest_tags_splits_compound_vocab(tmp_path):
    kb = tmp_path / "kb"
    md = kb / "a.md"
    sc_dir = kb / ".memoria" / "sidecars"
    sc_dir.mkdir(parents=True)
    md.write_text("# A\n\n分段函数与 cases 环境。\n", encoding="utf-8")
    sc_dir.joinpath("a.memoria.yaml").write_text(
        """schema_version: 1
file: a.md
knowledge_points:
- id: src-kp
  name: Source
  tags: [func、分段]
  range:
    start: {line_hint: 1}
    end: {line_hint: 3}
""",
        encoding="utf-8",
    )
    kp = {
        "id": "tgt-kp",
        "name": "Target",
        "tags": [],
        "range": {"start": {"line_hint": 1}, "end": {"line_hint": 3}},
    }
    from memoria.services.lexical_index import rebuild_lexical_index

    rebuild_lexical_index(str(kb))
    res = suggest_tags(
        kb_path=str(kb),
        rel_path="a.md",
        kp_id="tgt-kp",
        lines=md.read_text(encoding="utf-8").splitlines(),
        kp=kp,
        limit=5,
    )
    tags = [s["tag"] for s in res["suggestions"]]
    assert "func、分段" not in tags
    assert "分段" in tags


def test_suggest_tags_ignores_trivial_token_overlap(tmp_path):
    kb = tmp_path / "kb"
    md = kb / "a.md"
    sc_dir = kb / ".memoria" / "sidecars"
    sc_dir.mkdir(parents=True)
    md.write_text("# BERT\n\nBidirectional Encoder 表示。\n", encoding="utf-8")
    sc_dir.joinpath("a.memoria.yaml").write_text(
        """schema_version: 1
file: a.md
knowledge_points:
- id: junk
  name: Junk
  tags: [你妹的]
  range:
    start: {line_hint: 1}
    end: {line_hint: 2}
""",
        encoding="utf-8",
    )
    kp = {
        "id": "bert",
        "name": "BERT",
        "tags": [],
        "range": {"start": {"line_hint": 1}, "end": {"line_hint": 3}},
    }
    from memoria.services.lexical_index import rebuild_lexical_index

    rebuild_lexical_index(str(kb))
    res = suggest_tags(
        kb_path=str(kb),
        rel_path="a.md",
        kp_id="bert",
        lines=md.read_text(encoding="utf-8").splitlines(),
        kp=kp,
        limit=5,
    )
    tags = [s["tag"] for s in res["suggestions"]]
    assert "你妹的" not in tags
