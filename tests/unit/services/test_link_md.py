"""link_md 单元测试。"""

from __future__ import annotations

from memoria.services.link_md import (
    format_wikilink,
    remove_wikilink,
    update_wikilink,
    wrap_plain_text,
)


def test_format_wikilink_display():
    assert format_wikilink("rl", display="强化学习") == "[[rl|强化学习]]"
    assert format_wikilink("mdp", edge_hint="prerequisite") == "[[mdp]]"


def test_strip_known_wikilink_edge_hints():
    from memoria.services.link_md import strip_known_wikilink_edge_hints

    body = "参见 [[mdp#prerequisite]] 与 [[mdp#贝尔曼方程]]。"
    new, n = strip_known_wikilink_edge_hints(body)
    assert n == 1
    assert new == "参见 [[mdp]] 与 [[mdp#贝尔曼方程]]。"


def test_remove_wikilink_keeps_display():
    body = "见 [[rl|强化学习]] 一节。"
    new, ok = remove_wikilink(body, "rl", display="强化学习")
    assert ok
    assert new == "见 强化学习 一节。"


def test_update_wikilink_anchor_and_display():
    body = "[[nav-old|旧标题]]"
    new, ok = update_wikilink(
        body,
        "nav-old",
        new_anchor="nav-new",
        display="新标题",
    )
    assert ok
    assert new == "[[nav-new|新标题]]"


def test_wrap_plain_text():
    body = "RL 三角：概览、MDP、Q-Learning"
    new, ok = wrap_plain_text(
        body,
        "RL 三角：概览、MDP、Q-Learning",
        "RL 三角：概览、MDP、Q-Learning",
        display="RL 三角：概览、MDP、Q-Learning",
    )
    assert ok
    assert new.startswith("[[RL 三角：概览、MDP、Q-Learning]]")


def test_wrap_plain_text_skips_inside_wikilink():
    body = "见 [[查看二者|链接]] 与 查看二者 两处。"
    new, ok = wrap_plain_text(body, "查看二者", "查看二者")
    assert ok
    assert new == "见 [[查看二者|链接]] 与 [[查看二者]] 两处。"


def test_wrap_plain_text_navigation_demo_line():
    body = (
        "连续动作空间方法常同时涉及 [[q-learning]] 与 [[policy-gradient]] 两类思想；"
        "可继续点 [[ddpg]] 查看二者在深度 RL 中的结合。"
    )
    new, ok = wrap_plain_text(body, "查看二者", "查看二者")
    assert ok
    assert "[[ddpg]] [[查看二者]]在深度 RL" in new


def test_wrap_plain_text_rejects_prefix_of_longer_word():
    body = "按顺序点击（每跳一次后可用工具栏 ← 返回）："
    new, ok = wrap_plain_text(body, "按顺序点", "按顺序点")
    assert not ok
    assert new == body
