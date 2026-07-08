"""M1 链接解析测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from memoria.services.kp_index import build_kp_index
from memoria.services.link_resolver import (
    build_link_overrides,
    collect_link_alias_anchors,
    resolve_link_target,
    resolve_link_targets,
    scan_wikilinks,
)

EXAMPLES = Path(__file__).resolve().parents[3] / "examples"


@pytest.fixture
def kb_path() -> str:
    if not EXAMPLES.is_dir():
        pytest.skip("examples 目录不存在")
    return str(EXAMPLES)


def test_scan_wikilinks_display_and_type():
    body = "参见 [[q-learning#extend|Q-Learning 算法]] 与 [[mdp#prerequisite]]。"
    links = scan_wikilinks(body)
    assert len(links) == 2
    assert links[0]["target_id"] == "q-learning"
    assert links[0]["edge_hint"] == "extend"
    assert links[0]["display"] == "Q-Learning 算法"
    assert links[1]["target_id"] == "mdp"


def test_resolve_kp_id(kb_path: str):
    res = resolve_link_target(kb_path, "mdp")
    assert res["status"] == "ok"
    assert res["candidates"][0]["file"] == "mdp.md"
    assert res["candidates"][0]["kp_id"] == "mdp"


def test_resolve_file_stem(kb_path: str):
    res = resolve_link_target(kb_path, "q-learning")
    assert res["status"] == "ok"
    assert res["candidates"][0]["file"] == "q-learning.md"


def test_resolve_not_found(kb_path: str):
    res = resolve_link_target(kb_path, "bellman")
    assert res["status"] == "not_found"


def test_resolve_multi_targets(kb_path: str):
    res = resolve_link_targets(kb_path, ["q-learning", "policy-gradient"])
    assert res["status"] == "multi"
    assert len(res["candidates"]) == 2
    files = {c["file"] for c in res["candidates"]}
    assert "q-learning.md" in files
    assert "policy-gradient.md" in files


def test_build_link_overrides_aliases_by_display_label():
    sidecar = {
        "links": [
            {"anchor_text": "nav-rl-triangle", "targets": ["rl", "mdp", "q-learning"]},
            {"anchor_text": "RL 三角：概览、MDP、Q-Learning", "targets": ["rl"]},
        ]
    }
    body = (
        "[[nav-rl-triangle|RL 三角：概览、MDP、Q-Learning]]\n"
        "[[RL 三角：概览、MDP、Q-Learning]]"
    )
    overrides = build_link_overrides(sidecar, body)
    assert overrides["nav-rl-triangle"] == ["rl", "mdp", "q-learning"]
    assert overrides["RL 三角：概览、MDP、Q-Learning"] == ["rl", "mdp", "q-learning"]


def test_collect_link_alias_anchors():
    body = (
        "[[nav-rl-triangle|RL 三角：概览、MDP、Q-Learning]]\n"
        "[[RL 三角：概览、MDP、Q-Learning]]"
    )
    canonical, aliases = collect_link_alias_anchors(
        body, "RL 三角：概览、MDP、Q-Learning", None
    )
    assert canonical == "nav-rl-triangle"
    assert "nav-rl-triangle" in aliases
    assert "RL 三角：概览、MDP、Q-Learning" in aliases


def test_build_link_overrides():
    sidecar = {
        "links": [
            {
                "anchor_text": "nav-multi",
                "targets": ["q-learning", "policy-gradient"],
            }
        ]
    }
    overrides = build_link_overrides(sidecar)
    assert overrides["nav-multi"] == ["q-learning", "policy-gradient"]
