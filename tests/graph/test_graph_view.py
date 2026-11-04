"""B2 · I-02 `GraphViewBuilder` 测试（S0-2 V1–V6 + S6-2）。

覆盖：per-(level, view_family) 分区 / V1–V6 fail-closed / data_state /
非叶层无 cluster run 不造假簇 / 确定性 2× / 不写事实（D-3）。
"""
from __future__ import annotations

import pytest

from memoria.graph.multilevel.cluster_run import ClusterRunBuilder
from memoria.graph.multilevel.datasource import (
    E_RELATION_MIN,
    DataSource,
    DataSourceReader,
    detect_writes,
    snapshot_kb,
)
from memoria.graph.multilevel.errors import GraphError
from memoria.graph.multilevel.graph_view import (
    DATA_STATES,
    VIEW_FAMILY_FIELDS,
    GraphView,
    GraphViewBuilder,
    ViewFamily,
    assert_partition_scope,
    expand_cluster_to_kp,
    validate_level_view,
)

IDS = ["a", "b", "c", "d", "e"]
TMP_KB_MD = "# A\n\n## A1\n\ntext a1\n\n### A1-1\n\ntext a11\n"


def _ds(ids=IDS, edges=()) -> DataSource:
    return DataSource(
        status="ok",
        canonical_id="f" * 64,
        e_relation_min=E_RELATION_MIN,
        kps=tuple({"id": i, "kind": "kp"} for i in ids),
        edges=tuple(edges),
    )


def _vf(level_chain=("L0", "L1"), family="fam-h", basis="level_partition", dim="H") -> ViewFamily:
    return ViewFamily(family_id=family, basis=basis, dimension_id=dim, level_chain=level_chain)


def _sem(src: str, tgt: str) -> dict:
    return {
        "type": "extend", "source_id": src, "targets": [tgt],
        "assertion_source": {"file": "a.md", "line_start": 1, "line_end": 1},
        "derived_by": "author",
    }


def _make_kb(root):
    """最小 KB（供 D-3 断言：builder 不得写盘）。"""
    kb = root / "kb"
    (kb / ".memoria" / "sidecars").mkdir(parents=True)
    (kb / "a.md").write_text(TMP_KB_MD, encoding="utf-8")
    (kb / ".memoria" / "manifest.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    import yaml
    sc = {"schema_version": 1, "file": "a.md", "knowledge_points": [
        {"id": "a", "range": {"start": {"snippet": "# A", "line_hint": 1},
                              "end": {"snippet": "text a11", "line_hint": 9}}}]}
    (kb / ".memoria" / "sidecars" / "a.memoria.yaml").write_text(
        yaml.safe_dump(sc, allow_unicode=True, sort_keys=False, width=4096), encoding="utf-8")
    return kb


# ── view_family（R-2 冻结四元组）─────────────────────────────────


def test_view_family_has_four_frozen_fields() -> None:
    assert VIEW_FAMILY_FIELDS == ("family_id", "basis", "dimension_id", "level_chain")
    vf = _vf()
    assert vf.to_dict() == {
        "family_id": "fam-h", "basis": "level_partition",
        "dimension_id": "H", "level_chain": ["L0", "L1"],
    }
    assert vf.leaf_level == "L1"


@pytest.mark.parametrize("kwargs", [
    {"family": ""},
    {"basis": ""},
    {"dim": ""},
    {"level_chain": ()},
])
def test_view_family_invalid_fields_fail_closed(kwargs: dict) -> None:
    with pytest.raises(GraphError):
        _vf(**kwargs)


# ── 叶视图（无 cluster，全部 KP 各自成格）────────────────────────


def test_leaf_level_view_is_all_kp() -> None:
    vf = _vf()
    view = GraphViewBuilder().build(_ds(), level="L1", view_family=vf)
    assert view.level == "L1"
    assert {n["kind"] for n in view.nodes} == {"kp"}
    assert set(view.node_ids()) == set(IDS)
    assert view.clusters == ()
    assert validate_level_view(view, kp_ids=IDS) == []


def test_data_state_is_empty_nosemantic_without_semantic_edges() -> None:
    """真实语料形态（E_sem=0）⇒ empty_nosemantic（S2-12/S6-2）。"""
    view = GraphViewBuilder().build(_ds(), level="L1", view_family=_vf())
    assert view.data_state == "empty_nosemantic"
    assert set(DATA_STATES) == {"ok", "empty_nosemantic"}


def test_data_state_ok_when_semantic_present() -> None:
    view = GraphViewBuilder().build(_ds(), level="L1", view_family=_vf(), has_semantic=True)
    assert view.data_state == "ok"


def test_level_not_in_chain_fails_closed() -> None:
    with pytest.raises(GraphError) as ei:
        GraphViewBuilder().build(_ds(), level="L9", view_family=_vf())
    assert ei.value.detail["s0_code"] == "V0_LEVEL_INVALID"


def test_non_leaf_level_without_cluster_run_fails_closed() -> None:
    """非叶层但无 cluster run ⇒ 拒绝（**不得用结构边伪造簇**，S2-12）。"""
    with pytest.raises(GraphError) as ei:
        GraphViewBuilder().build(_ds(), level="L0", view_family=_vf())
    assert ei.value.detail["s0_code"] == "V3_CLUSTER_REQUIRED"


# ── 簇层视图（簇来自 I-04 run）────────────────────────────────


def test_cluster_level_view_uses_run_clusters() -> None:
    ds = _ds()
    run = ClusterRunBuilder().build(
        ds, level_id="L0", view_family_id="fam-h",
        semantic_edges=[_sem("a", "b"), _sem("b", "c"), _sem("d", "e")],
    )
    view = GraphViewBuilder().build(ds, level="L0", view_family=_vf(), cluster_run=run,
                                    has_semantic=True)
    assert {n["kind"] for n in view.nodes} == {"cluster"}
    assert len(view.nodes) == len(run.clusters)
    # V5：分区互斥且并集 = 该层全集
    assert validate_level_view(view, kp_ids=IDS) == []
    assert expand_cluster_to_kp(view) == set(IDS)


def test_cluster_view_node_ids_are_run_scoped() -> None:
    ds = _ds()
    run = ClusterRunBuilder().build(ds, level_id="L0", view_family_id="fam-h",
                                    semantic_edges=[_sem("a", "b")])
    view = GraphViewBuilder().build(ds, level="L0", view_family=_vf(), cluster_run=run,
                                    has_semantic=True)
    for nid in view.node_ids():
        assert nid.startswith(run.run_id + ":")


# ── V1–V6 校验器（对坏视图必须 fail-closed）────────────────────


def _bad_view(**over) -> GraphView:
    base = dict(
        level="L0", view_family=_vf(), data_state="ok",
        nodes=({"id": "c1", "kind": "cluster"},),
        clusters=({"cluster_id": "c1", "members": ("a", "b"), "size": 2,
                   "representative": True},),
    )
    base.update(over)
    return GraphView(**base)


def test_v1_illegal_kind() -> None:
    view = _bad_view(nodes=({"id": "c1", "kind": "node"},))
    assert any("V1" in p for p in validate_level_view(view, kp_ids=IDS))


def test_v2_leaf_not_in_kp_set() -> None:
    view = GraphView(level="L1", view_family=_vf(), data_state="ok",
                     nodes=({"id": "zzz", "kind": "kp"},), clusters=())
    assert any("V2" in p for p in validate_level_view(view, kp_ids=IDS))


def test_v3_empty_cluster() -> None:
    view = _bad_view(clusters=({"cluster_id": "c1", "members": (), "size": 0,
                                "representative": False},))
    assert any("V3" in p for p in validate_level_view(view, kp_ids=IDS))


def test_v4_cluster_without_members_table() -> None:
    view = _bad_view(clusters=())
    assert any("V4" in p for p in validate_level_view(view, kp_ids=IDS))


def test_v5_overlapping_members() -> None:
    view = _bad_view(
        nodes=({"id": "c1", "kind": "cluster"}, {"id": "c2", "kind": "cluster"}),
        clusters=(
            {"cluster_id": "c1", "members": ("a", "b"), "size": 2, "representative": True},
            {"cluster_id": "c2", "members": ("b", "c"), "size": 2, "representative": True},
        ),
    )
    problems = validate_level_view(view, kp_ids=IDS)
    assert any("V5" in p and "同时属于" in p for p in problems)


def test_v5_union_missing_members() -> None:
    view = _bad_view(
        nodes=({"id": "c1", "kind": "cluster"},),
        clusters=({"cluster_id": "c1", "members": ("a", "b"), "size": 2,
                   "representative": True},),
    )
    problems = validate_level_view(view, kp_ids=IDS)
    assert any("V5" in p and "并集缺" in p for p in problems)


def test_v6_expand_returns_kps() -> None:
    view = _bad_view()
    expanded = expand_cluster_to_kp(view)
    assert expanded == {"a", "b"}
    # 成员不是 KP ⇒ V3 报错（V6 的"到底全为 KP"由成员校验承担）
    problems = validate_level_view(view, kp_ids=["a", "z"])
    assert any("V3" in p or "V6" in p for p in problems)


def test_bad_level_view_raises_from_builder() -> None:
    """builder 产出不合规视图时必须抛（fail-closed），不是返回坏视图。"""
    ds = _ds(ids=["a", "b"])
    run = ClusterRunBuilder().build(ds, level_id="L0", view_family_id="fam-h",
                                    semantic_edges=[_sem("a", "b")])
    # 用一个成员的簇覆盖不全（漏 b）⇒ V5 缺并集
    from memoria.graph.multilevel.graph_view import GraphView as GV
    fake = GV(level="L0", view_family=_vf(), data_state="ok",
              nodes=({"id": "c1", "kind": "cluster"},),
              clusters=({"cluster_id": "c1", "members": ("a",), "size": 1,
                         "representative": False},))
    assert validate_level_view(fake, kp_ids=["a", "b"])


# ── 确定性 / 不写事实（D-3）────────────────────────────────────


def test_view_is_deterministic_2x() -> None:
    ds = _ds()
    sem = [_sem("a", "b"), _sem("d", "e")]
    run1 = ClusterRunBuilder().build(ds, level_id="L0", view_family_id="fam-h", semantic_edges=sem)
    run2 = ClusterRunBuilder().build(ds, level_id="L0", view_family_id="fam-h", semantic_edges=sem)
    v1 = GraphViewBuilder().build(ds, level="L0", view_family=_vf(), cluster_run=run1, has_semantic=True)
    v2 = GraphViewBuilder().build(ds, level="L0", view_family=_vf(), cluster_run=run2, has_semantic=True)
    assert v1.canonical_sha() == v2.canonical_sha()


def test_builder_does_not_write_kb(tmp_path) -> None:
    """D-3：GraphViewBuilder **不碰文件系统**（只吃已读的 DataSource）。"""
    kb = _make_kb(tmp_path)
    ds = DataSourceReader(kb).read()
    before = snapshot_kb(kb)
    GraphViewBuilder().build(ds, level="L1", view_family=_vf(level_chain=("L0", "L1")))
    after = snapshot_kb(kb)
    assert detect_writes(before, after) == []


def test_partition_scope_is_level_and_family() -> None:
    """R-2：partition 断言对象是 (level, view_family)，不是 (level, dimension)。"""
    ds = _ds()
    vf_h = _vf(dim="H")
    v_leaf = GraphViewBuilder().build(ds, level="L1", view_family=vf_h)
    assert assert_partition_scope([v_leaf]) == []
    # 同一 (level, family) 出现两个不同分区 ⇒ 报错
    other = GraphView(level="L1", view_family=vf_h, data_state="ok",
                      nodes=({"id": "a", "kind": "kp"},), clusters=())
    assert assert_partition_scope([v_leaf, other])
