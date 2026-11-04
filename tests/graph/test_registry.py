"""B2 · I-03 `RegistryService` 测试（S1 冻结契约）。

覆盖：S1-2 字段表 fail-closed / registry_sha 可复算 / history 链可复算·只增不删·
跨版本 new⊇old（自包含，不需旧 registry）/ 可选签名（失败 ⇒ GRAPH_HISTORY_SIGNATURE_INVALID）/
resolve 三态 fail-closed / 确定性。
"""
from __future__ import annotations

import copy

import pytest

from memoria.graph.multilevel.datasource import E_RELATION_MIN
from memoria.graph.multilevel.errors import GraphError
from memoria.graph.multilevel.registry import (
    DIM_KINDS,
    DIM_STATUSES,
    DIMENSION_FIELDS,
    KIND_BASIS_MAP,
    HistoryEntry,
    RegistryService,
    compute_registry_sha,
    make_dimension,
    make_history_entry,
    validate_dimension,
    validate_registry,
    verify_history_chain,
    verify_registry_history_binding,
)

T0 = "2026-11-04T00:00:00+00:00"
T1 = "2026-11-04T01:00:00+00:00"


def _h(status: str = "active", **kw) -> dict:
    return make_dimension(dim_id="H", name="层次维", kind="hierarchy_navigation",
                          status=status, **kw)


def _a(status: str = "active", priority: int = 1, **kw) -> dict:
    return make_dimension(dim_id="A", name="关联维", kind="relation_expansion",
                          status=status, priority=priority, **kw)


def _svc(dims=None, version="v1") -> RegistryService:
    return RegistryService.create(
        dims if dims is not None else [_h(), _a()],
        registry_version=version, decision_id="dec-1", created_by="tester", created_at=T0,
    )


# ── 字段表与枚举（S1-2）────────────────────────────────────────────


def test_dimension_fields_are_frozen_set() -> None:
    assert set(DIMENSION_FIELDS) == {
        "id", "name", "kind", "basis", "relation_sources", "direction", "hop_unit",
        "hop_default", "hop_max", "termination", "status", "priority", "version",
        "history_ref",
    }
    assert DIM_KINDS == ("hierarchy_navigation", "relation_expansion")
    assert DIM_STATUSES == ("reserved", "active", "deprecated")
    assert KIND_BASIS_MAP == {
        "hierarchy_navigation": "level_partition",
        "relation_expansion": "relation_neighborhood",
    }


def test_valid_h_and_a_dimensions_pass() -> None:
    assert validate_dimension(_h()) == []
    assert validate_dimension(_a()) == []


def test_kind_basis_mismatch_fails() -> None:
    bad = _h()
    bad["basis"]["kind"] = "relation_neighborhood"
    codes = {p.dim_code for p in validate_dimension(bad)}
    assert "DIM_KIND_MISMATCH" in codes


def test_h_rules_enforced() -> None:
    # H 必须 relation_sources=[]、hop 为 null、direction=down、leaf_required=true
    bad1 = _h()
    bad1["relation_sources"] = list(E_RELATION_MIN)
    assert "DIM_SOURCES_INVALID" in {p.dim_code for p in validate_dimension(bad1)}

    bad2 = _h()
    bad2["direction"] = "both"
    assert "DIM_DIRECTION_INVALID" in {p.dim_code for p in validate_dimension(bad2)}

    bad3 = _h()
    bad3["hop_unit"] = "edge"
    bad3["hop_default"] = 1
    bad3["hop_max"] = 2
    assert "DIM_HOP_UNIT_INVALID" in {p.dim_code for p in validate_dimension(bad3)}

    bad4 = _h()
    bad4["termination"]["leaf_required"] = False
    assert "DIM_TERMINATION_INVALID" in {p.dim_code for p in validate_dimension(bad4)}


def test_a_rules_enforced() -> None:
    # A 必须 ⊇ E_relation_min
    bad = _a()
    bad["relation_sources"] = ["reference"]
    assert "DIM_SOURCES_INVALID" in {p.dim_code for p in validate_dimension(bad)}

    # hop_max ≤ 2
    bad2 = _a()
    bad2["hop_max"] = 3
    bad2["hop_default"] = 1
    assert "DIM_HOP_INVALID" in {p.dim_code for p in validate_dimension(bad2)}

    # 1 ≤ hop_default ≤ hop_max
    bad3 = _a()
    bad3["hop_default"] = 3
    bad3["hop_max"] = 2
    assert "DIM_HOP_INVALID" in {p.dim_code for p in validate_dimension(bad3)}


def test_invalid_kind_status_and_priority_fail() -> None:
    bad = _h()
    bad["kind"] = "density"
    assert "DIM_KIND_INVALID" in {p.dim_code for p in validate_dimension(bad)}

    bad2 = _h()
    bad2["status"] = "frozen"
    assert "DIM_STATUS_INVALID" in {p.dim_code for p in validate_dimension(bad2)}

    # registry 级：priority 重复 / id 重复
    reg = {
        "registry_version": "v1", "contract_version": "s1-v1",
        "dimensions": [_h(), _a(priority=0)], "fallback_policy": "allow",
    }
    reg["registry_sha"] = compute_registry_sha(reg)
    codes = {p.dim_code for p in validate_registry(reg)}
    assert "DIM_PRIORITY_DUPLICATE" in codes

    reg2 = copy.deepcopy(reg)
    reg2["dimensions"] = [_h(), dict(_h(), priority=5)]
    reg2["registry_sha"] = compute_registry_sha(reg2)
    assert "DIM_ID_INVALID" in {p.dim_code for p in validate_registry(reg2)}


def test_missing_field_fails_closed() -> None:
    bad = _h()
    bad.pop("direction")
    assert validate_dimension(bad), "缺字段必须 fail-closed"


# ── registry_sha（S1-2 计算域）────────────────────────────────────


def test_registry_sha_recomputable() -> None:
    svc = _svc()
    assert svc.registry["registry_sha"] == compute_registry_sha(svc.registry)


def test_registry_sha_changes_with_content() -> None:
    r1 = _svc().registry["registry_sha"]
    r2 = _svc([_h(), _a(priority=2)]).registry["registry_sha"]
    assert r1 != r2


def test_tampered_registry_sha_detected() -> None:
    reg = _svc().registry
    reg["registry_sha"] = "0" * 64
    assert "DIM_REGISTRY_SHA_INVALID" in {p.dim_code for p in validate_registry(reg)}


# ── history 链（R-S1-9）──────────────────────────────────────────


def test_history_tail_content_sha_equals_registry_sha() -> None:
    svc = _svc()
    assert svc.history[-1].content_sha == svc.registry["registry_sha"]
    assert verify_registry_history_binding(svc.registry, svc.history) == []


def test_history_content_sha_recomputable_from_entry_alone() -> None:
    """自包含：仅凭条目即可复算 content_sha（不需旧 registry）。"""
    svc = _svc()
    entry = svc.history[-1]
    from memoria.graph.multilevel.registry import sha256_canonical
    assert sha256_canonical(entry.content_body()) == entry.content_sha


def test_history_chain_links_previous_sha() -> None:
    svc = _svc()
    res = make_dimension(dim_id="RES", name="时间维", kind="relation_expansion",
                         status="reserved", priority=2)
    svc2 = svc.append_version([_h(), _a(), res],
                              registry_version="v2", decision_id="dec-2",
                              created_by="tester", created_at=T1)
    assert svc2.history[1].previous_sha == svc2.history[0].content_sha
    assert verify_history_chain(svc2.history) == []


def test_broken_chain_detected() -> None:
    svc = _svc()
    broken = list(svc.history)
    e = broken[0]
    broken[0] = HistoryEntry(
        content_sha=e.content_sha, previous_sha="deadbeef", registry_version=e.registry_version,
        registry_body=e.registry_body, relation_sources=e.relation_sources,
        active_dimensions=e.active_dimensions, decision_id=e.decision_id,
        created_at=e.created_at, created_by=e.created_by, version=e.version,
    )
    assert any("断链" in p for p in verify_history_chain(broken))


def test_content_sha_tampering_detected() -> None:
    svc = _svc()
    e = svc.history[0]
    tampered = HistoryEntry(
        content_sha="0" * 64, previous_sha=e.previous_sha,
        registry_version=e.registry_version, registry_body=e.registry_body,
        relation_sources=e.relation_sources, active_dimensions=e.active_dimensions,
        decision_id=e.decision_id, created_at=e.created_at, created_by=e.created_by,
        version=e.version,
    )
    assert any("不可复算" in p for p in verify_history_chain([tampered]))


# ── 只增不删 / 跨版本 new⊇old（S1-6 / R-S1-3）───────────────────


def test_cross_version_new_superset_of_old() -> None:
    """跨版本 new⊇old：仅凭 history 条目自包含字段即可判定（不需旧 registry）。"""
    svc = _svc()
    svc2 = svc.append_version([_h(), _a()], registry_version="v2",
                              decision_id="dec-2", created_by="tester", created_at=T1)
    old = set(svc2.history[0].relation_sources)
    new = set(svc2.history[1].relation_sources)
    assert new >= old
    old_active = set(svc2.history[0].active_dimensions)
    new_active = set(svc2.history[1].active_dimensions)
    assert new_active >= old_active


def test_deleting_dimension_requires_s0_reopen() -> None:
    svc = _svc()
    with pytest.raises(GraphError) as ei:
        svc.append_version([_h()], registry_version="v2", decision_id="dec-2",
                           created_by="tester", created_at=T1)
    assert ei.value.detail["dim_code"] == "S0_REOPEN_REQUIRED"


def test_reducing_relation_sources_requires_s0_reopen() -> None:
    """relation_sources 只增不删：v1 多一个源、v2 去掉它 ⇒ S0_REOPEN_REQUIRED。

    （A 的 ``relation_sources`` 必须 ⊇ ``E_relation_min``，所以只能在**额外源**上做减法。）
    """
    wide = _a()
    wide["relation_sources"] = list(E_RELATION_MIN) + ["navigation"]
    svc = _svc([_h(), wide])
    assert validate_dimension(wide) == []

    narrowed = _a()   # 只剩 E_relation_min ⇒ 合法 A，但相对 v1 是"减少"
    with pytest.raises(GraphError) as ei:
        svc.append_version([_h(), narrowed], registry_version="v2", decision_id="dec-2",
                           created_by="tester", created_at=T1)
    assert ei.value.detail["dim_code"] == "S0_REOPEN_REQUIRED"


def test_history_is_append_only_new_object() -> None:
    """append_version 返回**新对象**，旧 svc 的 history 不被改写（不可变）。"""
    svc = _svc()
    before = list(svc.history)
    svc.append_version([_h(), _a()], registry_version="v2", decision_id="dec-2",
                       created_by="tester", created_at=T1)
    assert svc.history == before


# ── 三态 / resolve fail-closed（S1-11 / S1-14）───────────────────


def test_resolve_active_ok() -> None:
    svc = _svc()
    assert svc.resolve("A")["id"] == "A"
    assert {d["id"] for d in svc.active_dimensions()} == {"H", "A"}


def test_dimension_status_three_states_accepted() -> None:
    """三态（reserved/active/deprecated）都是合法注册值（S1-11 状态机）。"""
    for i, status in enumerate(DIM_STATUSES):
        dim = make_dimension(dim_id=f"D{i}", name=f"维{i}", kind="relation_expansion",
                             status=status, priority=i)
        assert validate_dimension(dim) == [], f"{status} 应为合法状态"


def test_resolve_unknown_and_not_active() -> None:
    res = make_dimension(dim_id="RES", name="时间维", kind="relation_expansion",
                         status="reserved", priority=2)
    svc = _svc([_h(), _a(), res])
    with pytest.raises(GraphError) as ei:
        svc.resolve("RES")
    assert ei.value.detail["dim_code"] == "DIM_NOT_ACTIVE"
    with pytest.raises(GraphError) as ei2:
        svc.resolve("NOPE")
    assert ei2.value.detail["dim_code"] == "DIM_UNKNOWN"


# ── 可选签名（S6-3 / R-S6-4）──────────────────────────────────────


def test_unsigned_history_is_allowed_and_marked_unsigned() -> None:
    svc = _svc()
    assert svc.history_signed() is False
    assert verify_history_chain(svc.history) == []


def test_valid_signature_accepted() -> None:
    def verifier(entry) -> bool:
        return entry.signature is not None and entry.signature.get("key_id") == "k1"

    entry = make_history_entry(
        registry_body=_svc().registry, previous_sha="", registry_version="v1",
        version="v1", relation_sources=set(E_RELATION_MIN), active_dimensions={"H", "A"},
        decision_id="dec-1", created_by="tester", created_at=T0,
        signature={"alg": "hmac-sha256", "key_id": "k1", "sig": "deadbeef"},
    )
    assert verify_history_chain([entry], verifier=verifier) == []


def test_invalid_signature_fails_with_frozen_code() -> None:
    """有签名但验证不过 ⇒ 冻结码 ``GRAPH_HISTORY_SIGNATURE_INVALID``（不新造码）。"""
    svc = RegistryService.create(
        [_h(), _a()], registry_version="v1", decision_id="dec-1", created_by="tester",
        created_at=T0, signature={"alg": "hmac-sha256", "key_id": "k1", "sig": "bad"},
    )
    with pytest.raises(GraphError) as ei:
        svc.verify_signatures(lambda entry: False)
    assert ei.value.code == "GRAPH_HISTORY_SIGNATURE_INVALID"


def test_signature_without_verifier_fails_closed() -> None:
    """声明校验签名但没给 verifier ⇒ fail-closed（不当作"已验证"）。"""
    svc = RegistryService.create(
        [_h(), _a()], registry_version="v1", decision_id="dec-1", created_by="tester",
        created_at=T0, signature={"alg": "ed25519", "key_id": "k1", "sig": "x"},
    )
    # 构造期只做结构校验（允许"尚未接签名后端"）
    assert verify_history_chain(svc.history) == []
    # 显式要求验证却没 verifier ⇒ 报问题
    problems = verify_history_chain(svc.history, require_signature_verification=True)
    assert any("未提供 verifier" in p for p in problems)


def test_bad_signature_alg_fails_closed() -> None:
    entry = make_history_entry(
        registry_body=_svc().registry, previous_sha="", registry_version="v1", version="v1",
        relation_sources=set(), active_dimensions=set(), decision_id="d",
        created_by="t", created_at=T0,
        signature={"alg": "md5", "key_id": "k", "sig": "x"},
    )
    assert any("alg 非法" in p for p in verify_history_chain([entry]))


# ── 确定性 ────────────────────────────────────────────────────────


def test_registry_creation_is_deterministic() -> None:
    a = _svc()
    b = _svc()
    assert a.registry["registry_sha"] == b.registry["registry_sha"]
    assert a.history[-1].content_sha == b.history[-1].content_sha
    assert a.to_dict() == b.to_dict()
