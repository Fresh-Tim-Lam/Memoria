"""task-380 P0 后端机检：demo KB 默认 hub focus + Presentation-only groups。"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "artifacts/demo-kb/corpus-pilot-split"

pytestmark = pytest.mark.skipif(not DEMO.is_dir(), reason="demo KB artifact 缺失（本地 P0 证据库）")


def _build(**params):
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from memoria.presentation.api.ui import _mlvm_build

    return _mlvm_build(str(DEMO), params)


def _degrees():
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from memoria.graph.multilevel.datasource import DataSourceReader

    ds = DataSourceReader(str(DEMO)).read()
    deg = {str(k["id"]): 0 for k in ds.kps if k.get("id")}
    for e in ds.edges:
        src = str(e.get("source_id") or "")
        if src in deg:
            deg[src] += 1
        for t in e.get("targets") or []:
            if str(t) in deg:
                deg[str(t)] += 1
    return deg


def test_default_focus_is_highest_degree_hub_not_isolated() -> None:
    from memoria.graph.multilevel.admission import make_frame_spec

    deg = _degrees()
    hub = sorted(deg.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    assert deg[hub] > 0, "hub 不应是孤立点"
    r = _build()
    vm = r["vm"]
    shown = [n for n in vm["nodes"] if (n.get("presence") or "shown") == "shown"]
    assert len(shown) >= 2, f"默认 shown={len(shown)}，P0 要求 >=2"
    assert hub in {str(n["id"]) for n in shown}, "默认 shown 未包含 hub"
    expected = make_frame_spec(
        level="LL", view_family="default", dimension_id="A",
        focus=hub, hop=1, new_hop=False, mode="default",
        max_nodes=200, max_edges=400,
    ).canonical_sha()
    assert r["frame_id"] == expected, "默认 frame 的 focus 不是 hub"
    assert r["rule_histogram"].get("hop.budget", 0) > 0, "demo 仍应有候选被裁剪（正常）"


def test_presentation_groups_only_and_cover_shown() -> None:
    r = _build()
    vm, pres = r["vm"], r["presentation"]
    groups = pres.get("groups") or []
    assert groups, "缺 presentation.groups"
    shown = {str(n["id"]) for n in vm["nodes"] if (n.get("presence") or "shown") == "shown" and n.get("kind") == "kp"}
    members = set()
    for g in groups:
        assert g["presentation_only"] is True
        assert "kind" not in g and "presence" not in g, "group 不得伪造 VM 字段"
        assert g["member_ids"], "空组"
        members.update(g["member_ids"])
    assert members == shown, "groups.member_ids 未覆盖全部 shown KP"
    # VM 仍是 KP-only；group 未写入 VM
    assert {n.get("kind") for n in vm["nodes"]} == {"kp"}
    assert all("group" not in n and "groups" not in n for n in vm["nodes"])
    # 其它 Pres 字段照旧
    assert set(pres) >= {"degrees", "files", "groups"}


def test_explicit_focus_still_wins_and_changes_frame() -> None:
    hub = _build()  # 默认 hub
    explicit = _build(focus="kp-005")
    assert explicit["frame_id"] != hub["frame_id"]
    assert any(str(n["id"]) == "kp-005" and (n.get("presence") or "shown") == "shown" for n in explicit["vm"]["nodes"])
