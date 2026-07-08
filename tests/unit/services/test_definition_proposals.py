"""S5 定义句 range 提议测试。"""

from memoria.services.definition_proposals import propose_ranges_from_definitions


def test_definition_proposal_x_is():
    body = """# 标题

强化学习是序列决策问题的一种形式。

- 例子一
"""
    props = propose_ranges_from_definitions(body)
    assert props
    hit = next(p for p in props if "强化学习" in p["name"])
    assert hit["strategy"] == "definition"
    assert hit["range"]["start"]["line_hint"] == 3


def test_definition_proposal_suowei():
    body = """所谓「马尔可夫决策过程」是 RL 的数学框架。

后续段落。
"""
    props = propose_ranges_from_definitions(body)
    assert any("马尔可夫" in p["name"] for p in props)


def test_definition_skips_code_block():
    body = """```
强化学习是指代码块内
```
"""
    props = propose_ranges_from_definitions(body)
    assert props == []
