"""B3 · I-05 `AdmissionService` 测试（S4 冻结契约，**P0**）。

## 这个文件守的 P0 门禁（S8）

| 门禁 | 落点 |
|---|---|
| `X-RULE = 100%`（节点+边联合，null=FAIL，分项 X-NODE-/X-EDGE-） | `test_x_rule_is_100_percent` + `test_x_rule_detects_missing_rule_id` |
| `subset_ok = true`（S4-9/R-S4-7 三前提） | `test_subset_holds_by_construction` |
| `closure_violations = 0`（≤ hop_budget，禁隐式第二跳） | `test_no_implicit_second_hop_even_with_huge_budget` |
| `behind_violations = 0`（不带背后图，U-17） | 同上 |
| presence 三值 / 11 类 rule_id / unknown 触发面 | `test_rule_id_enum_closure_and_coverage` 等 |
| MANDATORY（A={focus}；H={focus}+first K children） | `test_mandatory_*` |
| 事务化 diff=0 | `test_admission_is_deterministic_2x` |
| R-B2-5 语义标记证据缺失 ⇒ 可见失败 | `test_semantic_marker_without_evidence_fails_visibly` |
"""
from __future__ import annotations

import pytest

from memoria.graph.multilevel import admission as adm
from memoria.graph.multilevel.admission import (
    ADMISSION_MODES,
    DEFAULT_BUDGET,
    FRAME_SPEC_FIELDS,
    MANDATORY_CONTEXT_CAP,
    PRESENCE_SUPPRESSED,
    PRESENCE_UNKNOWN,
    PRESENCE_VALUES,
    RELATION_CLASS_ORDER,
    RULE_IDS,
    UNKNOWN_RULE_IDS,
    AdmissionResult,
    AdmissionService,
    FrameSpec,
    assert_semantic_marker_evidence,
    check_x_rule,
    make_frame_spec,
)
from memoria.graph.multilevel.cluster_run import ClusterRunBuilder
from memoria.graph.multilevel.datasource import E_RELATION_MIN, DataSource
from memoria.graph.multilevel.errors import (
    GRAPH_BUDGET_INVALID,
    GRAPH_EDGE_SEMANTIC_MISMATCH,
    GRAPH_INTERNAL,
    GraphError,
)
from memoria.graph.multilevel.graph_view import GraphViewBuilder, ViewFamily

IDS = ["a", "b", "c", "d", "e"]


def _edge(etype: str, src: str, tgt: str, **kw) -> dict:
    return {"type": etype, "source_id": src, "targets": [tgt], **kw}


def _sem_edge(src: str, tgt: str) -> dict:
    """合法 semantic extend 边（含 S0-1 G_sem 要求的全部证据）。"""
    return {
        "type": "extend", "source_id": src, "targets": [tgt],
        "assertion_source": {"file": "a.md", "line_start": 1, "line_end": 1,
                             "quote_sha256": "a" * 64},
        "curated_by": "human:tester", "curated_at": "2026-11-04T00:00:00+08:00",
    }


def _ds(ids=IDS, edges=(), canonical="f" * 64) -> DataSource:
    return DataSource(
        status="ok", canonical_id=canonical, e_relation_min=E_RELATION_MIN,
        kps=tuple({"id": i, "kind": "kp"} for i in ids), edges=tuple(edges),
    )


def _vf(dim: str = "A", family: str = "fam-a"):
    return ViewFamily(family_id=family, basis="relation_neighborhood",
                      dimension_id=dim, level_chain=("L0", "L1"))


def _gv(ds: DataSource, dim: str = "A"):
    return GraphViewBuilder().build(ds, level="L1", view_family=_vf(dim), has_semantic=True)


def _frame(focus="a", dim="A", *, max_nodes=200, max_edges=400, hop=1, mode="default",
           new_hop=False) -> FrameSpec:
    return make_frame_spec(level="L1", view_family="fam-a", dimension_id=dim, focus=focus,
                           hop=hop, new_hop=new_hop, mode=mode,
                           max_nodes=max_nodes, max_edges=max_edges)


def _admit(ds, *, focus="a", dim="A", graph_view=None, **kw) -> AdmissionResult:
    return AdmissionService().admit(
        frame_spec=_frame(focus, dim, **{k: v for k, v in kw.items()
                                         if k in ("max_nodes", "max_edges", "hop", "mode")}),
        graph_view=graph_view if graph_view is not None else _gv(ds, dim),
        datasource=ds,
        **{k: v for k, v in kw.items() if k in ("relation_sources", "source_available", "run")},
    )


# ── 枚举闭合 ────────────────────────────────────────────────────────────


def test_presence_enum_is_three_values() -> None:
    assert PRESENCE_VALUES == ("shown", "suppressed", "unknown")


def test_rule_ids_are_exactly_eleven() -> None:
    assert RULE_IDS == (
        "dimension.sources", "dimension.direction", "dimension.level.cross_layer",
        "hop.budget", "node.budget", "edge.budget", "cluster.folded",
        "endpoint.unresolved", "source.unavailable", "admission.undecided", "invalid.data",
    )
    assert len(RULE_IDS) == 11


def test_unknown_only_from_four_rules() -> None:
    """S4-6：``unknown`` 仅由后 4 类触发（unknown ≠ 无关系）。"""
    assert UNKNOWN_RULE_IDS == {
        "endpoint.unresolved", "source.unavailable", "admission.undecided", "invalid.data",
    }
    assert len(UNKNOWN_RULE_IDS) == 4


def test_relation_class_order_frozen() -> None:
    assert RELATION_CLASS_ORDER == {"semantic": 0, "structural": 1, "navigation": 2, "reference": 3}


def test_mandatory_context_cap_is_two() -> None:
    assert MANDATORY_CONTEXT_CAP == 2


# ── FrameSpec（S6-6 严格 8 字段）───────────────────────────────────────


def test_frame_spec_has_exactly_eight_frozen_fields() -> None:
    import dataclasses
    names = tuple(f.name for f in dataclasses.fields(FrameSpec))
    assert names == FRAME_SPEC_FIELDS
    assert len(FRAME_SPEC_FIELDS) == 8
    # 导航字段不得进 S4 输入（S4-11 / R-S6-2）
    for forbidden in ("frame_id", "edition", "edition_sha", "nav_id"):
        assert forbidden not in FRAME_SPEC_FIELDS


@pytest.mark.parametrize("kwargs", [
    {"hop": 0},
    {"hop": 3},
    {"mode": "weird"},
    {"new_hop": "yes"},
    {"focus": ""},
    {"max_nodes": 0},
])
def test_frame_spec_invalid_fails_closed(kwargs: dict) -> None:
    with pytest.raises(GraphError) as ei:
        _frame(**kwargs)
    assert ei.value.code == GRAPH_INTERNAL


def test_frame_spec_canonical_sha_is_stable() -> None:
    assert _frame().canonical_sha() == _frame().canonical_sha()
    assert _frame(max_nodes=3).canonical_sha() != _frame().canonical_sha()


# ── P0：X-RULE ─────────────────────────────────────────────────────────


def test_x_rule_is_100_percent() -> None:
    """non-shown 节点+边**都必须**有 rule_id；分项也须 100%。"""
    ds = _ds(edges=[_edge("contain", "a", "b"), _edge("contain", "b", "c")])
    result = _admit(ds)
    x = check_x_rule(result)
    assert x["pass"] is True
    assert x["x_rule"] == 1.0
    assert x["x_node_rule"] == 1.0
    assert x["x_edge_rule"] == 1.0
    assert x["node_non_shown"] > 0 and x["edge_non_shown"] > 0, "用例必须真的含 non-shown 项"
    # 每个 non-shown 都带 rule_id 且属于 11 类
    for item in (*result.nodes, *result.edges):
        if item["presence"] != "shown":
            assert item["rule_id"] in RULE_IDS


def test_x_rule_detects_missing_rule_id() -> None:
    """**守卫活性对照**：构造一个缺 rule_id 的 non-shown 项 ⇒ 度量为 FAIL（null=FAIL）。"""
    bad = AdmissionResult(
        frame_spec=_frame(),
        nodes=({"id": "x", "kind": "kp", "presence": "suppressed", "rule_id": None,
                "hop": 2, "mandatory": False, "focus": False},),
        edges=(),
    )
    x = check_x_rule(bad)
    assert x["pass"] is False
    assert x["x_node_rule"] == 0.0
    assert x["x_rule"] == 0.0


def test_admit_refuses_to_return_below_100_percent(monkeypatch) -> None:
    """X-RULE<100% 时 admit **必须抛**，不能安静返回不合格结果。"""
    ds = _ds(edges=[_edge("contain", "a", "b")])
    monkeypatch.setattr(adm, "check_x_rule", lambda r: {
        "x_node_rule": 0.5, "x_edge_rule": 0.5, "x_rule": 0.5,
        "node_with_rule": 0, "node_non_shown": 1, "edge_with_rule": 0,
        "edge_non_shown": 1, "pass": False,
    })
    with pytest.raises(GraphError) as ei:
        _admit(ds)
    assert "X-RULE" in ei.value.message


# ── P0：一跳 / 无隐式第二跳 / 无背后图 ─────────────────────────────────


def test_only_focus_one_hop_is_shown() -> None:
    """S4-3/S4-4：默认只显示 focus 的一跳；2 跳一律 suppressed。"""
    ds = _ds(edges=[_edge("contain", "a", "b"), _edge("contain", "b", "c")])
    result = _admit(ds)
    assert set(result.shown_node_ids()) == {"a", "b"}
    assert result.max_hop_shown() == 1
    assert result.edges and all(
        e["presence"] != "shown" or e["hop"] <= 1 for e in result.edges
    )


def test_no_implicit_second_hop_even_with_huge_budget() -> None:
    """**P0**：预算再大也不得把 2 跳带进来（closure/behind 必须 0）。"""
    ds = _ds(ids=["a", "b", "c", "d", "e"],
             edges=[_edge("contain", "a", "b"), _edge("contain", "b", "c"),
                    _edge("contain", "c", "d"), _edge("reference", "d", "e")])
    result = _admit(ds, max_nodes=10_000, max_edges=10_000)
    assert result.closure_violations == ()
    assert result.behind_violations == ()
    assert result.max_hop_shown() == 1
    shown = set(result.shown_node_ids())
    assert "c" not in shown and "d" not in shown and "e" not in shown


def test_self_check_detects_closure_violation() -> None:
    """**守卫活性**：若真有 hop>budget 的 shown，检测器必须报出来（不是恒返回空）。"""
    bad = AdmissionResult(
        frame_spec=_frame("a", hop=1),
        nodes=(
            {"id": "a", "kind": "kp", "hop": 0, "mandatory": True, "focus": True,
             "presence": "shown", "rule_id": None},
            {"id": "c", "kind": "kp", "hop": 2, "mandatory": False, "focus": False,
             "presence": "shown", "rule_id": None},          # ← 故意违规
        ),
        edges=(),
    )
    violations = AdmissionService._self_check(bad)
    assert violations["closure"], "closure 违规未被检出（检测器失效）"
    assert any("hop_budget" in v for v in violations["closure"])


def test_self_check_detects_behind_violation() -> None:
    """**守卫活性**：若把 2 跳邻居 shown 出来，behind 检测器必须报（U-17）。"""
    bad = AdmissionResult(
        frame_spec=_frame("a", hop=2),
        nodes=(
            {"id": "a", "kind": "kp", "hop": 0, "mandatory": True, "focus": True,
             "presence": "shown", "rule_id": None},
            {"id": "b", "kind": "kp", "hop": 1, "mandatory": False, "focus": False,
             "presence": "shown", "rule_id": None},
            {"id": "c", "kind": "kp", "hop": 2, "mandatory": False, "focus": False,
             "presence": "shown", "rule_id": None},          # ← 一跳端点的邻居
        ),
        edges=(
            {"id": "contain|a|b", "type": "contain", "src_view": "a", "tgt_view": "b",
             "relation_class": "structural", "hop": 1, "aggregate_count": 1,
             "data_edge_ids": [], "presence": "shown", "rule_id": None},
            {"id": "contain|b|c", "type": "contain", "src_view": "b", "tgt_view": "c",
             "relation_class": "structural", "hop": 2, "aggregate_count": 1,
             "data_edge_ids": [], "presence": "shown", "rule_id": None},
        ),
    )
    violations = AdmissionService._self_check(bad)
    assert violations["behind"], "behind 违规未被检出（检测器失效）"
    assert any("2 跳" in v for v in violations["behind"])


def test_hop_two_only_with_explicit_frame_hop() -> None:
    """2 跳不是绝对禁止，而是**必须显式**给 hop=2（S5 EXPLICIT_NEW_HOP 的接口位）。"""
    ds = _ds(edges=[_edge("contain", "a", "b"), _edge("contain", "b", "c")])
    result = _admit(ds, hop=2, max_nodes=100)
    assert result.max_hop_shown() == 2
    assert result.closure_violations == ()


# ── P0：subset（S4-9 / R-S4-7 构造性保证）─────────────────────────────


def _star_ds(n: int = 6) -> DataSource:
    """focus=a，a 与 b..f 一跳相连（用于 subset 用例）。"""
    ids = ["a"] + [f"n{i}" for i in range(1, n)]
    edges = [_edge("contain", "a", x) for x in ids[1:]]
    return _ds(ids=ids, edges=edges)


def test_subset_holds_by_construction() -> None:
    """default(小预算) ⊆ full(大预算)，且三前提全部成立（R-S4-7）。"""
    ds = _star_ds()
    gv = _gv(ds)
    default, full, report = AdmissionService().admit_with_subset(
        frame_spec=_frame("a", max_nodes=3),
        graph_view=gv,
        datasource=ds,
        full_budget={"max_nodes": 100, "max_edges": 400},
    )
    assert report["subset_ok"] is True
    assert report["candidates_superset"] is True
    assert report["reserved_equals_default_shown"] is True
    assert report["budget_ok"] is True
    d_shown, f_shown = set(default.shown_node_ids()), set(full.shown_node_ids())
    assert d_shown < f_shown, "full 必须真的比 default 显示更多（否则 subset 用例是空真）"
    assert d_shown <= f_shown


def test_full_does_not_add_hops() -> None:
    """S4-4：full 也只放开预算，**不加跳**（2 跳仅 S5 显式）。"""
    ds = _star_ds()
    _, full, _ = AdmissionService().admit_with_subset(
        frame_spec=_frame("a", max_nodes=3), graph_view=_gv(ds), datasource=ds,
        full_budget={"max_nodes": 100, "max_edges": 400},
    )
    assert full.max_hop_shown() <= 1
    assert full.closure_violations == ()


def test_subset_rejects_smaller_full_budget() -> None:
    """budget_full < budget_default ⇒ 可见失败（R-S4-9，不静默）。"""
    ds = _star_ds()
    with pytest.raises(GraphError) as ei:
        AdmissionService().admit_with_subset(
            frame_spec=_frame("a", max_nodes=5), graph_view=_gv(ds), datasource=ds,
            full_budget={"max_nodes": 2, "max_edges": 400},
        )
    assert ei.value.code == GRAPH_BUDGET_INVALID


# ── MANDATORY（S4-5）───────────────────────────────────────────────────


def test_mandatory_a_dimension_is_focus_only() -> None:
    ds = _ds(edges=[_edge("contain", "a", "b"), _edge("contain", "a", "c")])
    result = _admit(ds, dim="A")
    assert result.mandatory_node_ids == ("a",)


def test_mandatory_h_dimension_is_focus_plus_capped_children() -> None:
    """H：``{focus} ∪ first K children(focus)``，K=2（children 按 canonical id 排序）。"""
    ds = _ds(ids=["a", "b", "c", "d"],
             edges=[_edge("contain", "a", "b"), _edge("contain", "a", "c"),
                    _edge("contain", "a", "d")])
    result = _admit(ds, dim="H")
    assert result.mandatory_node_ids == ("a", "b", "c")   # 前 2 个 child
    assert set(result.mandatory_node_ids) <= set(result.shown_node_ids())


def test_mandatory_over_budget_fails_visibly() -> None:
    """S4-5：**仅 MANDATORY 超预算**才 fail-visible（其他情况只抑制）。"""
    ds = _ds(ids=["a", "b", "c"], edges=[_edge("contain", "a", "b"), _edge("contain", "a", "c")])
    with pytest.raises(GraphError) as ei:
        _admit(ds, dim="H", max_nodes=2)     # mandatory = {a,b,c} 3 > 2
    assert ei.value.code == GRAPH_BUDGET_INVALID
    assert ei.value.detail["mandatory"] == ["a", "b", "c"]


def test_non_mandatory_over_budget_is_suppressed_not_error() -> None:
    ds = _ds(ids=["a", "b", "c"], edges=[_edge("contain", "a", "b"), _edge("contain", "a", "c")])
    result = _admit(ds, dim="A", max_nodes=2)     # mandatory={a}，c 被抑制
    assert set(result.shown_node_ids()) == {"a", "b"}
    suppressed = {n["id"]: n["rule_id"] for n in result.nodes if n["presence"] == "suppressed"}
    assert suppressed.get("c") == "node.budget"


# ── 11 类 rule_id 全部可达（逐条构造）─────────────────────────────────


def test_rule_id_enum_closure_and_coverage() -> None:
    """11 类 rule_id 都能被真实取景场景产出（不是只写在常量里）。"""
    emitted: set[str] = set()

    # 1 dimension.sources / 2 dimension.direction：H 维 + 非 contain 边 / 反向边
    ds_h = _ds(ids=["a", "b", "x"],
               edges=[_edge("reference", "a", "b"), _edge("contain", "x", "a"),
                      _edge("contain", "a", "x")])
    r = AdmissionService().admit(frame_spec=_frame("a", "H"), graph_view=_gv(ds_h, "H"),
                                 datasource=ds_h)
    emitted |= {i["rule_id"] for i in (*r.nodes, *r.edges) if i["rule_id"]}

    # 3 cross_layer：边显式标跨层
    ds_cl = _ds(ids=["a", "b"], edges=[_edge("contain", "a", "b", cross_layer=True)])
    r = AdmissionService().admit(frame_spec=_frame("a"), graph_view=_gv(ds_cl), datasource=ds_cl)
    emitted |= {i["rule_id"] for i in (*r.nodes, *r.edges) if i["rule_id"]}

    # 4 hop.budget：2 跳
    ds_hop = _ds(ids=["a", "b", "c"], edges=[_edge("contain", "a", "b"),
                                             _edge("contain", "b", "c")])
    r = AdmissionService().admit(frame_spec=_frame("a"), graph_view=_gv(ds_hop),
                                 datasource=ds_hop)
    emitted |= {i["rule_id"] for i in (*r.nodes, *r.edges) if i["rule_id"]}

    # 5 node.budget：预算压到只剩 MANDATORY
    ds_nb = _ds(ids=["a", "b", "c"], edges=[_edge("contain", "a", "b"),
                                            _edge("contain", "a", "c")])
    r = AdmissionService().admit(frame_spec=_frame("a", max_nodes=2), graph_view=_gv(ds_nb),
                                 datasource=ds_nb)
    emitted |= {i["rule_id"] for i in (*r.nodes, *r.edges) if i["rule_id"]}

    # 6 edge.budget：边预算 1
    ds_eb = _ds(ids=["a", "b", "c"], edges=[_edge("contain", "a", "b"),
                                            _edge("contain", "a", "c")])
    r = AdmissionService().admit(frame_spec=_frame("a", max_edges=1), graph_view=_gv(ds_eb),
                                 datasource=ds_eb)
    emitted |= {i["rule_id"] for i in (*r.nodes, *r.edges) if i["rule_id"]}

    # 7 cluster.folded / 8 endpoint.unresolved：簇层视图
    #   ⚠️ 视图的簇必须覆盖"视图内 KP"，否则 V5 直接红；
    #   因此用 4 个 KP 建 run/视图，再用"多一个 ghost 端点"的数据源做 admit
    #   ⇒ c→ghost 的 ghost 不在任何簇 ⇒ endpoint.unresolved。
    ds_clu = _ds(ids=["a", "b", "c", "d"],
                 edges=[_edge("extend", "a", "b"), _edge("extend", "c", "d"),
                        _edge("contain", "a", "b")])          # 簇内（折叠）
    run = ClusterRunBuilder().build(ds_clu, level_id="L0", view_family_id="fam-a",
                                    semantic_edges=[_sem_edge("a", "b"), _sem_edge("c", "d")])
    gv_clu = GraphViewBuilder().build(ds_clu, level="L0", view_family=_vf("A"),
                                      cluster_run=run, has_semantic=True)
    ds_with_ghost = DataSource(
        status="ok", canonical_id=ds_clu.canonical_id, e_relation_min=E_RELATION_MIN,
        kps=tuple({"id": i, "kind": "kp"} for i in ["a", "b", "c", "d", "ghost"]),
        edges=tuple(ds_clu.edges) + (_edge("contain", "c", "ghost"),),
    )
    focus_cluster = run.clusters[0]["cluster_id"]
    r = AdmissionService().admit(
        frame_spec=make_frame_spec(level="L0", view_family="fam-a", dimension_id="A",
                                   focus=focus_cluster),
        graph_view=gv_clu, datasource=ds_with_ghost, run=run)
    emitted |= {i["rule_id"] for i in (*r.nodes, *r.edges) if i["rule_id"]}

    # 9 source.unavailable
    r = AdmissionService().admit(frame_spec=_frame("a"), graph_view=_gv(ds_hop),
                                 datasource=ds_hop, source_available=False)
    emitted |= {i["rule_id"] for i in (*r.nodes, *r.edges) if i["rule_id"]}

    # 10 admission.undecided：无 datasource
    r = AdmissionService().admit(frame_spec=_frame("a"), graph_view=_gv(ds_hop), datasource=None)
    emitted |= {i["rule_id"] for i in (*r.nodes, *r.edges) if i["rule_id"]}

    # 11 invalid.data：畸形边
    bad_edge = {"type": "contain", "source_id": "a"}      # 缺 targets
    ds_bad = DataSource(status="ok", canonical_id="f" * 64, e_relation_min=E_RELATION_MIN,
                        kps=tuple({"id": i, "kind": "kp"} for i in ("a", "b")),
                        edges=(bad_edge,))
    r = AdmissionService().admit(frame_spec=_frame("a"), graph_view=_gv(ds_bad),
                                 datasource=ds_bad)
    emitted |= {i["rule_id"] for i in (*r.nodes, *r.edges) if i["rule_id"]}

    missing = set(RULE_IDS) - emitted
    assert not missing, f"这些 rule_id 未被任何场景产出：{sorted(missing)}"
    assert emitted <= set(RULE_IDS)


def test_unknown_only_from_allowed_rules_across_scenarios() -> None:
    """任何场景下 ``presence=unknown`` 的项，其 rule_id 必须属于那 4 类。"""
    ds = _ds(ids=["a", "b"], edges=[_edge("contain", "a", "b")])
    scenarios = [
        dict(datasource=ds, source_available=True),
        dict(datasource=ds, source_available=False),
        dict(datasource=None),
    ]
    for kw in scenarios:
        r = AdmissionService().admit(
            frame_spec=_frame("a"), graph_view=_gv(ds), **kw)
        for item in (*r.nodes, *r.edges):
            if item["presence"] == PRESENCE_UNKNOWN:
                assert item["rule_id"] in UNKNOWN_RULE_IDS
            if item["presence"] == PRESENCE_SUPPRESSED:
                assert item["rule_id"] not in UNKNOWN_RULE_IDS


# ── R-B2-5：语义标记证据缺失 ⇒ 可见失败 ───────────────────────────────


def test_semantic_marker_without_evidence_fails_visibly() -> None:
    """R-B2-5：标了 semantic 但缺证据 ⇒ ``GRAPH_EDGE_SEMANTIC_MISMATCH``（不静默降级）。"""
    bad = {"type": "contain", "source_id": "a", "targets": ["b"], "contain_kind": "semantic"}
    ds = DataSource(status="ok", canonical_id="f" * 64, e_relation_min=E_RELATION_MIN,
                    kps=tuple({"id": i, "kind": "kp"} for i in ("a", "b")), edges=(bad,))
    with pytest.raises(GraphError) as ei:
        AdmissionService().admit(frame_spec=_frame("a"), graph_view=_gv(ds), datasource=ds)
    assert ei.value.code == GRAPH_EDGE_SEMANTIC_MISMATCH


def test_semantic_marker_complete_evidence_passes() -> None:
    good = dict(_sem_edge("a", "b"), type="contain", contain_kind="semantic")
    ds = _ds(ids=["a", "b"], edges=[good])
    result = AdmissionService().admit(frame_spec=_frame("a"), graph_view=_gv(ds), datasource=ds)
    assert check_x_rule(result)["pass"] is True


def test_structural_edges_do_not_require_evidence() -> None:
    """结构边（缺省/structural）不要求证据字段 —— 不得误伤。"""
    ds = _ds(ids=["a", "b"], edges=[_edge("contain", "a", "b", contain_kind="structural")])
    result = AdmissionService().admit(frame_spec=_frame("a"), graph_view=_gv(ds), datasource=ds)
    assert "b" in result.shown_node_ids()


@pytest.mark.parametrize("missing", ["assertion_source", "curated_by", "curated_at"])
def test_each_missing_evidence_field_fails(missing: str) -> None:
    edge = dict(_sem_edge("a", "b"), type="contain", contain_kind="semantic")
    edge.pop(missing)
    with pytest.raises(GraphError) as ei:
        assert_semantic_marker_evidence([edge])
    assert ei.value.code == GRAPH_EDGE_SEMANTIC_MISMATCH


def test_label_semantic_marker_also_requires_evidence() -> None:
    """R-B2-5 也覆盖 ``label=semantic``（不只 contain_kind）。"""
    edge = {"type": "extend", "source_id": "a", "targets": ["b"], "label": "semantic"}
    with pytest.raises(GraphError) as ei:
        assert_semantic_marker_evidence([edge])
    assert ei.value.code == GRAPH_EDGE_SEMANTIC_MISMATCH


# ── 事实不变 / fail-closed / 确定性 ──────────────────────────────────


def test_presence_does_not_change_facts() -> None:
    """S4-1/S4-12：presence 只改取景，不改 type/kind。"""
    ds = _ds(ids=["a", "b"], edges=[_edge("reference", "a", "b")])
    result = _admit(ds, dim="H")     # H 下 reference 被 dimension.sources 抑制
    ref_edges = [e for e in result.edges if e["type"] == "reference"]
    assert ref_edges and ref_edges[0]["presence"] == "suppressed"
    assert ref_edges[0]["type"] == "reference"       # 事实未被改写


def test_unknown_dimension_fails_closed() -> None:
    ds = _ds(ids=["a", "b"], edges=[_edge("contain", "a", "b")])
    with pytest.raises(GraphError) as ei:
        AdmissionService().admit(
            frame_spec=make_frame_spec(level="L1", view_family="fam-a",
                                       dimension_id="RESERVED_X", focus="a"),
            graph_view=_gv(ds), datasource=ds)
    assert ei.value.code == GRAPH_INTERNAL


def test_focus_not_in_partition_fails_closed() -> None:
    ds = _ds(ids=["a", "b"], edges=[_edge("contain", "a", "b")])
    with pytest.raises(GraphError) as ei:
        AdmissionService().admit(frame_spec=_frame("zzz"), graph_view=_gv(ds), datasource=ds)
    assert "focus" in ei.value.message


def test_admission_is_deterministic_2x() -> None:
    """事务化：同输入两次 ⇒ AdmissionResult canonical sha 一致。"""
    ds = _star_ds()
    r1 = _admit(ds)
    r2 = _admit(ds)
    assert r1.canonical_sha() == r2.canonical_sha()


def test_suppressed_summary_and_histogram_align() -> None:
    """X-SUMMARY 对齐 S4 ``suppressed_summary{rule_id:count}``（S8）。"""
    ds = _ds(ids=["a", "b", "c"], edges=[_edge("contain", "a", "b"),
                                         _edge("contain", "b", "c")])
    result = _admit(ds)
    summary = result.suppressed_summary()
    assert summary
    # 直方图与 summary 一致（仅统计 non-shown）
    hist = dict(result.rule_histogram)
    for rule_id, count in summary.items():
        assert hist.get(rule_id) == count


def test_admission_modes_are_frozen() -> None:
    assert ADMISSION_MODES == ("default", "full")
    assert DEFAULT_BUDGET == {"max_nodes": 200, "max_edges": 400}


def test_only_admission_produces_presence() -> None:
    """S4-1 唯一裁剪者：GraphView/DataSource 侧不产生 presence。"""
    ds = _ds(ids=["a", "b"], edges=[_edge("contain", "a", "b")])
    gv = _gv(ds)
    assert all("presence" not in n for n in gv.nodes)
    result = _admit(ds)
    assert all("presence" in n for n in result.nodes)
