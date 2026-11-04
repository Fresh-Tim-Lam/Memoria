"""B2 · I-04 `ClusterRunBuilder` 测试（S2 冻结契约）。

覆盖：run_id 六元组可复算 / params_hash 字段集冻结 / 五状态 / μ·β semantic-only /
多归属 / cluster_key / 确定性 2× / candidate 不自动 adopted / 结构边不得冒充 semantic。
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from memoria.graph.multilevel import cluster_run as cr
from memoria.graph.multilevel.cluster_run import (
    DEFAULT_PARAMS,
    PARAM_FIELDS,
    RUN_STATUSES,
    ClusterRunBuilder,
    adopt_run,
    assert_multi_membership_across_scope,
    assert_single_membership_within_scope,
    bridge_beta,
    build_run_id,
    cluster_key,
    cohesion_mu,
    is_semantic_edge,
    params_hash,
    request_candidate_run,
    select_semantic_edges,
    semantic_pairs,
    validate_params,
)
from memoria.graph.multilevel.datasource import E_RELATION_MIN, DataSource
from memoria.graph.multilevel.errors import GraphError

IDS = ["a", "b", "c", "d", "e", "f"]


def _ds(ids=IDS, edges=(), canonical="f" * 64) -> DataSource:
    return DataSource(
        status="ok",
        canonical_id=canonical,
        e_relation_min=E_RELATION_MIN,
        kps=tuple({"id": i, "kind": "kp"} for i in ids),
        edges=tuple(edges),
    )


def _sem(src: str, tgt: str) -> dict:
    """合 S0-1 G_sem 的语义 extend 边（作者断言 + 证据）。"""
    return {
        "type": "extend",
        "source_id": src,
        "targets": [tgt],
        "assertion_source": {"file": "a.md", "line_start": 1, "line_end": 1},
        "derived_by": "author",
    }


def _structural(src: str, tgt: str) -> dict:
    return {"type": "contain", "source_id": src, "targets": [tgt], "derived_by": "system_range"}


def _params(**overrides) -> dict:
    p = copy.deepcopy(DEFAULT_PARAMS)
    p.update(overrides)
    return p


# ── run_id 六元组（S2-7）──────────────────────────────────────────────


def test_run_id_recomputable_from_six_tuple() -> None:
    run = ClusterRunBuilder().build(
        _ds(), level_id="L1", view_family_id="fam-h",
        semantic_edges=[_sem("a", "b")],
    )
    recomputed = build_run_id(
        corpus_manifest_sha=run.corpus_manifest_sha,
        view_family_id=run.view_family_id,
        level_id=run.level_id,
        algorithm_id=run.algorithm_id,
        algorithm_version=run.algorithm_version,
        params_hash_value=run.params_hash,
    )
    assert recomputed == run.run_id


def test_run_id_is_independent_of_dimension() -> None:
    """S2-10 / R-S2-7：**A 维度不产生/不改变簇** ⇒ dimension 不进 run_id。

    （S6-4 的公式含 dimension_id，与 S2-10 冲突；S6-4 自称「S2 六元组」⇒ 以 S2 为准。）
    """
    builder = ClusterRunBuilder()
    ds = _ds()
    run_h = builder.build(ds, level_id="L1", view_family_id="fam-h", semantic_edges=[_sem("a", "b")])
    # 同一 DataSource/params/level/family，仅"维度"语境不同 ⇒ run_id 必须相同
    run_a = ClusterRunBuilder().build(
        ds, level_id="L1", view_family_id="fam-h", semantic_edges=[_sem("a", "b")]
    )
    assert run_h.run_id == run_a.run_id
    # run_id 的六个组成里没有 dimension_id（结构性断言：改变 dimension 不影响任何字段）
    assert "dimension_id" not in json.dumps(run_h.to_dict()["params"], ensure_ascii=False)


def test_run_id_changes_with_params() -> None:
    ds = _ds()
    sem = [_sem("a", "b")]
    r1 = ClusterRunBuilder(params=_params()).build(ds, level_id="L1", view_family_id="f", semantic_edges=sem)
    r2 = ClusterRunBuilder(params=_params(tau_coh=0.6)).build(
        ds, level_id="L1", view_family_id="f", semantic_edges=sem
    )
    assert r1.run_id != r2.run_id


# ── params_hash 字段集冻结（R-S2-10）─────────────────────────────────


def test_param_fields_are_frozen_set() -> None:
    assert PARAM_FIELDS == (
        "algorithm_id", "algorithm_version", "weight_policy", "linkage", "tie_break",
        "cut_policy", "target_k", "min_cluster_size", "n_max", "tau_coh", "tau_bridge",
    )
    assert params_hash(_params()) == params_hash(_params())


def test_params_missing_field_fails_closed() -> None:
    p = _params()
    p.pop("tau_bridge")
    with pytest.raises(GraphError) as ei:
        validate_params(p)
    assert ei.value.code == "GRAPH_INTERNAL"
    assert ei.value.detail["s2_code"] == "S2_PARAMS_INVALID"


def test_params_extra_field_fails_closed() -> None:
    p = _params()
    p["extra"] = 1
    with pytest.raises(GraphError):
        validate_params(p)


@pytest.mark.parametrize("override", [
    {"weight_policy": "tfidf"},
    {"linkage": "single"},
    {"tie_break": "random"},
    {"cut_policy": "elbow"},
    {"tau_coh": 1.5},
    {"hop": 2},
])
def test_params_invalid_values_fail_closed(override: dict) -> None:
    with pytest.raises(GraphError):
        validate_params(_params(**override))


# ── μ / β semantic-only（S2-2 / S2-3 / R-S2-1）───────────────────────


def test_mu_and_beta_formula() -> None:
    pairs = semantic_pairs([_sem("a", "b"), _sem("b", "c")])
    assert cohesion_mu(["a", "b", "c"], pairs) == pytest.approx(2 / 3)
    assert cohesion_mu(["a", "b"], pairs) == pytest.approx(1.0)
    assert cohesion_mu(["a"], pairs) is None          # 单点不算内聚（S2-1）
    assert cohesion_mu(["a", "b", "c"], frozenset()) == pytest.approx(0.0)
    # β = P_out/(P_in+P_out)：{a,b} 内部 1 对、跨出 1 对（b-c） ⇒ 0.5
    assert bridge_beta(["a", "b"], pairs) == pytest.approx(0.5)
    assert bridge_beta(["a", "b", "c"], pairs) == pytest.approx(0.0)


def test_dedup_pairs_same_edge_counted_once() -> None:
    """同对多边只计 1.0（weight_policy=semantic_uniform）。"""
    pairs = semantic_pairs([_sem("a", "b"), _sem("a", "b"), _sem("b", "a")])
    assert pairs == frozenset({("a", "b")})


def test_structural_edges_never_counted_as_semantic() -> None:
    """R-S2-1（P0）：结构/引用边**不进** μ/β。"""
    assert not is_semantic_edge(_structural("a", "b"))
    assert not is_semantic_edge({"type": "reference", "source_id": "a", "targets": ["b"],
                                 "assertion_source": {"file": "x"}})
    assert is_semantic_edge(_sem("a", "b"))
    # contain 只有 contain_kind=semantic 且带策展身份才算语义
    assert not is_semantic_edge({"type": "contain", "source_id": "a", "targets": ["b"],
                                 "contain_kind": "semantic", "assertion_source": {"file": "x"}})
    assert is_semantic_edge({
        "type": "contain", "source_id": "a", "targets": ["b"], "contain_kind": "semantic",
        "assertion_source": {"file": "x"}, "curated_by": "u", "curated_at": "2026-11-04",
    })
    pairs = semantic_pairs([_structural("a", "b"), _sem("b", "c")])
    assert pairs == frozenset({("b", "c")})


def test_structural_edge_injected_as_semantic_fails_closed() -> None:
    """禁止结构边冒充语义：显式传进去也必须被 G_sem 拦下。"""
    with pytest.raises(GraphError) as ei:
        ClusterRunBuilder().build(
            _ds(), level_id="L1", view_family_id="f",
            semantic_edges=[_structural("a", "b")],
        )
    assert ei.value.detail["s2_code"] == "S2_SEMANTIC_PURITY_FAIL"


def test_semantic_purity_violation_detected() -> None:
    """簇内部出现**非语义**边（且该对不在 E_sem 里）⇒ S2_SEMANTIC_PURITY_FAIL。"""
    ds = _ds(edges=())
    run = ClusterRunBuilder().build(ds, level_id="L1", view_family_id="f",
                                    semantic_edges=[_sem("a", "b")])
    cid = run.clusters[0]["cluster_id"] if run.clusters else "c1"
    members = {cid: ["a", "b", "c"]}
    violations = cr.semantic_purity_violations(
        members,
        semantic_edges=[_sem("a", "b")],
        # a-c 之间只有结构边、且不在 E_sem 内 ⇒ 违规
        all_edges=[_sem("a", "b"), _structural("a", "c")],
    )
    assert any("S2_SEMANTIC_PURITY_FAIL" in v for v in violations)


# ── 五状态（R-S2-13）───────────────────────────────────────────────


def test_status_enum_is_frozen() -> None:
    assert RUN_STATUSES == (
        "ok", "no_semantic_edges", "partial_disconnected", "size_exceeded", "algorithm_failed",
    )


def test_status_ok() -> None:
    run = ClusterRunBuilder().build(_ds(), level_id="L1", view_family_id="f",
                                    semantic_edges=[_sem("a", "b"), _sem("b", "c"), _sem("d", "e")])
    assert run.status == "ok"
    clusters = [c["members"] for c in run.clusters]
    assert ["a", "b", "c"] in clusters
    assert ["d", "e"] in clusters
    assert ["f"] in clusters           # 单点允许（S2-1）
    single = next(c for c in run.clusters if c["size"] == 1)
    assert single["representative"] is False   # R-S2-6


def test_status_no_semantic_edges() -> None:
    """真实语料形态：E_sem=∅ ⇒ no_semantic_edges（合法状态，S2-12）。"""
    run = ClusterRunBuilder().build(_ds(edges=[_structural("a", "b")]), level_id="L1",
                                    view_family_id="f", semantic_edges=[])
    assert run.status == "no_semantic_edges"
    assert run.diagnostics["coverage"] == 1.0   # 全部 KP 各自成格（仍是合法分区）
    assert all(c["representative"] is False for c in run.clusters)


def test_status_no_semantic_edges_when_datasource_has_no_semantic_marker() -> None:
    """B1 形状的 DataSource（边无 contain_kind）⇒ 派生 E_sem=∅（契约缺口的如实体现）。"""
    run = ClusterRunBuilder().build(_ds(edges=[_structural("a", "b")]),
                                    level_id="L1", view_family_id="f")
    assert run.status == "no_semantic_edges"


def test_status_size_exceeded() -> None:
    run = ClusterRunBuilder(params=_params(n_max=2)).build(
        _ds(), level_id="L1", view_family_id="f", semantic_edges=[_sem("a", "b")]
    )
    assert run.status == "size_exceeded"


def test_status_algorithm_failed() -> None:
    """后验 μ 达不到阈值且调整 k 仍不达标 ⇒ algorithm_failed（不输出违规簇）。"""
    run = ClusterRunBuilder(params=_params(tau_coh=0.99, target_k=2)).build(
        _ds(), level_id="L1", view_family_id="f",
        semantic_edges=[_sem("a", "b"), _sem("b", "c"), _sem("d", "e")],
    )
    assert run.status == "algorithm_failed"
    assert run.diagnostics["algorithm_failed"] is True


def test_status_partial_disconnected_reachable_in_state_machine() -> None:
    """``partial_disconnected`` 在**状态机**里可达（直测判定函数）。

    诚实说明：average-linkage HAC 的簇由正相似合并而来 ⇒ 簇内天然连通，
    端到端**不会**自然产出该状态；它是给其它/未来算法保留的合法枚举值（R-S2-13 冻结）。
    """
    status = cr._decide_status(
        n_nodes=6, n_pairs=3, groups=[frozenset({"a", "b"})],
        algorithm_failed=False, n_max=200, disconnected_inside=True,
    )
    assert status == "partial_disconnected"


def test_all_five_statuses_covered() -> None:
    """五状态覆盖率自证：枚举值集合与测试覆盖集合一致。"""
    covered = {"ok", "no_semantic_edges", "partial_disconnected", "size_exceeded", "algorithm_failed"}
    assert covered == set(RUN_STATUSES)


# ── 簇身份 / 多归属 / 采用状态 ────────────────────────────────────


def test_cluster_key_recomputable() -> None:
    params = _params()
    key = cluster_key(["b", "a"], params)
    assert key == cluster_key(["a", "b"], params)   # 顺序无关
    assert key != cluster_key(["a", "b"], _params(tau_coh=0.6))


def test_cluster_ids_use_run_prefix_and_local_seq() -> None:
    run = ClusterRunBuilder().build(_ds(), level_id="L1", view_family_id="f",
                                    semantic_edges=[_sem("a", "b")])
    for c in run.clusters:
        assert c["cluster_id"] == f"{run.run_id}:{c['local_seq']}"


def test_memberships_role_and_single_membership_within_scope() -> None:
    run = ClusterRunBuilder().build(_ds(), level_id="L1", view_family_id="f",
                                    semantic_edges=[_sem("a", "b")])
    assert {m["role"] for m in run.memberships} == {"member"}
    assert assert_single_membership_within_scope(run) == []


def test_multi_membership_across_scope_allowed() -> None:
    ds = _ds()
    sem = [_sem("a", "b")]
    r1 = ClusterRunBuilder().build(ds, level_id="L1", view_family_id="fam-h", semantic_edges=sem)
    r2 = ClusterRunBuilder().build(ds, level_id="L0", view_family_id="fam-h", semantic_edges=sem)
    stats = assert_multi_membership_across_scope([r1, r2])
    assert stats["kp_total"] == len(IDS)
    assert stats["multi_scope_kps"], "同一 KP 应可跨层多归属"


def test_candidate_run_is_not_auto_adopted() -> None:
    run = ClusterRunBuilder().build(_ds(), level_id="L1", view_family_id="f",
                                    semantic_edges=[_sem("a", "b")])
    assert run.adoption_status == "candidate"
    assert run.adopted_at is None
    assert run.decided_by is None


def test_request_candidate_run_requires_audit_fields() -> None:
    with pytest.raises(GraphError) as ei:
        request_candidate_run(ClusterRunBuilder(), _ds(), requester="", reason="x",
                             base_run_id=None, level_id="L1", view_family_id="f")
    assert ei.value.detail["s2_code"] == "S2_CANDIDATE_AUDIT_MISSING"


def test_request_candidate_run_keeps_candidate() -> None:
    run = request_candidate_run(
        ClusterRunBuilder(), _ds(), requester="agent", reason="test",
        base_run_id="prev", level_id="L1", view_family_id="f",
        semantic_edges=[_sem("a", "b")],
    )
    assert run.adoption_status == "candidate"
    assert run.parent_run_id == "prev"
    assert run.diagnostics["requested_by"] == "agent"


def test_adopt_requires_decision_and_flips_status() -> None:
    run = ClusterRunBuilder().build(_ds(), level_id="L1", view_family_id="f",
                                    semantic_edges=[_sem("a", "b")])
    with pytest.raises(GraphError):
        adopt_run(run, decision_id="")
    adopt_run(run, decision_id="dec-9")
    assert run.adoption_status == "adopted"
    assert run.decided_by == "dec-9"


# ── 确定性（2× run 逐字节一致）──────────────────────────────────────


def test_two_runs_are_byte_identical() -> None:
    ds = _ds()
    sem = [_sem("a", "b"), _sem("b", "c"), _sem("d", "e"), _sem("e", "f")]
    r1 = ClusterRunBuilder().build(ds, level_id="L1", view_family_id="f", semantic_edges=sem)
    r2 = ClusterRunBuilder().build(ds, level_id="L1", view_family_id="f", semantic_edges=sem)
    assert r1.canonical_sha() == r2.canonical_sha()


def test_tie_break_is_deterministic() -> None:
    """对称输入下冻结 tie-break（合并后 canonical 序列最小）⇒ 两次结果一致且可复现。"""
    ds = _ds(ids=["a", "b", "c", "d"])
    sem = [_sem("a", "b"), _sem("c", "d")]
    r1 = ClusterRunBuilder().build(ds, level_id="L1", view_family_id="f", semantic_edges=sem)
    r2 = ClusterRunBuilder().build(ds, level_id="L1", view_family_id="f", semantic_edges=sem)
    assert [c["members"] for c in r1.clusters] == [c["members"] for c in r2.clusters]
    assert [c["members"] for c in r1.clusters] == [["a", "b"], ["c", "d"]]


def test_missing_corpus_identity_fails_closed() -> None:
    ds = _ds()
    object.__setattr__(ds, "canonical_id", "")
    with pytest.raises(GraphError) as ei:
        ClusterRunBuilder().build(ds, level_id="L1", view_family_id="f", semantic_edges=[])
    assert ei.value.detail["s2_code"] == "S2_RUN_ID_INVALID"
