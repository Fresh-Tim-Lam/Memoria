"""文本归一化与拼音检索测试。"""

import pytest

from memoria.services.lexical_index import rebuild_lexical_index, search_lexical
from memoria.services.text_normalize import normalize_math_for_semantic
from memoria.services.lexical_tokenizer import pinyin_compact


def test_normalize_math_latex_command():
    assert "varepsilon" in normalize_math_for_semantic(r"$\varepsilon$ 的选择很关键")


@pytest.fixture
def pinyin_kb(tmp_path):
    pytest.importorskip("pypinyin")
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "rl.md").write_text("# RL\n\n马尔可夫决策过程简介。\n", encoding="utf-8")
    sidecar_dir = kb / ".memoria" / "sidecars"
    sidecar_dir.mkdir(parents=True)
    (sidecar_dir / "rl.memoria.yaml").write_text(
        """schema_version: 1
file: rl.md
knowledge_points:
  - id: markov-decision
    name: 马尔可夫决策过程
    range:
      start: { line_hint: 3 }
      end: { line_hint: 3 }
""",
        encoding="utf-8",
    )
    rebuild_lexical_index(str(kb))
    return str(kb)


def test_pinyin_homophone_typo(pinyin_kb):
    assert pinyin_compact("嘛而科夫") == pinyin_compact("马尔可夫")
    res = search_lexical("嘛而科夫", kb_path=pinyin_kb, limit=5)
    assert any(r["kp_id"] == "markov-decision" for r in res["results"])
