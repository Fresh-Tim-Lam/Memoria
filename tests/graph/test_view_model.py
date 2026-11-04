"""B3 · I-06 `ViewModelBuilder` 测试（S3-12 白名单 + S3-ADDENDUM-1，**P0**）。

## 这个文件守的 P0 门禁

| 门禁 | 落点 |
|---|---|
| VM 字段白名单（顶层/节点/边）+ ADDENDUM-1 的 presence/rule_id | `test_vm_whitelist_*` |
| `data_edge_ids` **仅审计、Renderer 禁读** | `test_renderer_projection_strips_data_edge_ids` + `test_static_no_forbidden_access_in_renderer_path` |
| 簇/run/metrics/导航字段**不进 VM** | `test_vm_has_no_cluster_run_metrics_or_nav` |
| 事务化 diff=0（同输入两次 VM sha 一致） | `test_vm_is_deterministic_2x` |
| Renderer 只渲染 shown（禁幽灵边） | `test_shown_only_filters_suppressed` |
| `layout_group` 仅 semantic=false 且非 cluster | `test_layout_group_rules` |
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from memoria.graph.multilevel import view_model as vm_mod
from memoria.graph.multilevel.admission import (
    AdmissionService,
    check_x_rule,
    make_frame_spec,
)
from memoria.graph.multilevel.datasource import E_RELATION_MIN, DataSource
from memoria.graph.multilevel.errors import GRAPH_INTERNAL, GraphError
from memoria.graph.multilevel.graph_view import GraphViewBuilder, ViewFamily
from memoria.graph.multilevel.view_model import (
    FORBIDDEN_ACCESS_PATTERNS,
    RENDERER_FORBIDDEN_EDGE_FIELDS,
    RENDERER_READABLE_EDGE_FIELDS,
    VM_EDGE_FIELDS,
    VM_EDGE_REQUIRED,
    VM_EDGE_STATES,
    VM_NODE_FIELDS,
    VM_NODE_KINDS,
    VM_NODE_REQUIRED,
    VM_NODE_ROLES,
    VM_TOP_FIELDS,
    ViewModelBuilder,
    assert_renderer_payload_clean,
    audit_data_edges,
    renderer_projection,
    shown_only,
    validate_vm,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
VM_FIXTURE = FIXTURES / "vm" / "valid-vm.json"
MODULE_PATH = Path(vm_mod.__file__)


def _edge(etype: str, src: str, tgt: str, **kw) -> dict:
    return {"type": etype, "source_id": src, "targets": [tgt], **kw}


def _ds(ids, edges=()) -> DataSource:
    return DataSource(status="ok", canonical_id="f" * 64, e_relation_min=E_RELATION_MIN,
                      kps=tuple({"id": i, "kind": "kp"} for i in ids), edges=tuple(edges))


def _vf(dim: str = "A") -> ViewFamily:
    return ViewFamily(family_id="fam-a", basis="relation_neighborhood",
                      dimension_id=dim, level_chain=("L0", "L1"))


def _admission(ds, *, focus="a", max_nodes=200, max_edges=400, level="L1"):
    gv = GraphViewBuilder().build(ds, level=level, view_family=_vf(), has_semantic=True)
    return AdmissionService().admit(
        frame_spec=make_frame_spec(level=level, view_family="fam-a", dimension_id="A",
                                   focus=focus, max_nodes=max_nodes, max_edges=max_edges),
        graph_view=gv, datasource=ds,
    )


# ── 白名单（S3-12 + ADDENDUM-1）──────────────────────────────────────


def test_vm_whitelist_constants_are_frozen() -> None:
    assert VM_TOP_FIELDS == (
        "view_model_id", "level_id", "level_label", "dimension_id", "view_family_id",
        "nodes", "edges",
    )
    assert VM_NODE_FIELDS == (
        "id", "kind", "label", "role",
        "member_count", "aggregate_count", "representative", "root_exempt", "range_ok",
        "layout_group",
        "presence", "rule_id",          # S3-ADDENDUM-1
    )
    assert VM_EDGE_FIELDS == ("id", "type", "state", "presence", "data_edge_ids")
    assert VM_NODE_KINDS == ("kp", "cluster")
    assert VM_NODE_ROLES == ("member",)          # R-S3-3：v1 无 bridge 视觉
    assert VM_EDGE_STATES == ("bridge_only",)


def test_vm_top_level_fields_exact() -> None:
    ds = _ds(["a", "b"], [_edge("contain", "a", "b")])
    vm = ViewModelBuilder().build(_admission(ds), level_label="L1")
    assert set(vm) == set(VM_TOP_FIELDS)
    assert validate_vm(vm) == []


def test_vm_nodes_carry_presence_and_rule_id() -> None:
    """ADDENDUM-1：节点可带 presence/rule_id，且 non-shown 必须有 rule_id。"""
    ds = _ds(["a", "b", "c"], [_edge("contain", "a", "b"), _edge("contain", "b", "c")])
    vm = ViewModelBuilder().build(_admission(ds))
    assert all("presence" in n for n in vm["nodes"])
    for node in vm["nodes"]:
        if node["presence"] != "shown":
            assert node.get("rule_id"), f"non-shown 节点缺 rule_id：{node['id']}"


def test_vm_node_required_fields_and_role() -> None:
    ds = _ds(["a", "b"], [_edge("contain", "a", "b")])
    vm = ViewModelBuilder().build(_admission(ds))
    for node in vm["nodes"]:
        for field_name in VM_NODE_REQUIRED:
            assert field_name in node
        assert node["role"] == "member"
        assert node["kind"] in VM_NODE_KINDS


def test_vm_edges_have_no_rule_id_field() -> None:
    """S3-12 边白名单**不含** rule_id ⇒ VM 边不得带（边的 rule 归属查 AdmissionResult）。"""
    ds = _ds(["a", "b", "c"], [_edge("contain", "a", "b"), _edge("contain", "b", "c")])
    vm = ViewModelBuilder().build(_admission(ds))
    for edge in vm["edges"]:
        assert "rule_id" not in edge
        assert set(edge) <= set(VM_EDGE_FIELDS)


def test_vm_has_no_cluster_run_metrics_or_nav() -> None:
    """S3-12/S4-11/S2-11：簇/run/候选状态/metrics/导航字段都不得进 VM。"""
    ds = _ds(["a", "b"], [_edge("contain", "a", "b")])
    vm = ViewModelBuilder().build(_admission(ds))
    for forbidden in ("clusters", "run_id", "dendrogram", "metrics", "candidates",
                      "frame_id", "nav", "mode", "focus", "hop", "capabilities"):
        assert forbidden not in vm


def test_vm_fixture_validates() -> None:
    vm = json.loads(VM_FIXTURE.read_text(encoding="utf-8"))
    assert validate_vm(vm) == [], validate_vm(vm)


# ── data_edge_ids：仅审计 / Renderer 禁读（R-S3-9）──────────────────


def test_renderer_readable_fields_exclude_data_edge_ids() -> None:
    assert RENDERER_FORBIDDEN_EDGE_FIELDS == ("data_edge_ids",)
    assert "data_edge_ids" not in RENDERER_READABLE_EDGE_FIELDS
    assert set(RENDERER_READABLE_EDGE_FIELDS) | set(RENDERER_FORBIDDEN_EDGE_FIELDS) == set(VM_EDGE_FIELDS)


def test_aggregated_edges_carry_data_edge_ids_for_audit() -> None:
    """聚合边（多条数据边 → 一条视图边）必须保留 data_edge_ids 供审计/expand。"""
    # 同一对端点、同 type 的两条数据边 ⇒ 聚合为一条视图边（aggregate_count=2）
    ds = _ds(["a", "b", "c"],
             [_edge("contain", "a", "b"), _edge("contain", "a", "b"),
              _edge("reference", "a", "c")])
    vm = ViewModelBuilder().build(_admission(ds))
    with_ids = [e for e in vm["edges"] if "data_edge_ids" in e]
    assert with_ids, "聚合边应带 data_edge_ids"
    assert all(len(e["data_edge_ids"]) >= 2 for e in with_ids)
    # 审计入口可读
    audit = audit_data_edges(vm)
    assert audit and all(isinstance(v, list) for v in audit.values())


def test_renderer_projection_strips_data_edge_ids() -> None:
    """Renderer 唯一输入入口必须剥掉禁读字段。"""
    ds = _ds(["a", "b", "c"],
             [_edge("contain", "a", "b"), _edge("contain", "a", "b")])
    vm = ViewModelBuilder().build(_admission(ds))
    assert any("data_edge_ids" in e for e in vm["edges"])
    projected = renderer_projection(vm)
    assert all("data_edge_ids" not in e for e in projected["edges"])
    assert all(set(e) <= set(RENDERER_READABLE_EDGE_FIELDS) for e in projected["edges"])
    # 节点投影仍是白名单
    assert all(set(n) <= set(VM_NODE_FIELDS) for n in projected["nodes"])


def test_renderer_payload_gate_rejects_forbidden_field() -> None:
    """Renderer 输入闸门：含 data_edge_ids ⇒ 抛错（fail-closed，不静默忽略）。"""
    dirty = {"view_model_id": "vm_x", "nodes": [],
             "edges": [{"id": "e1", "type": "contain", "data_edge_ids": ["d1"]}]}
    with pytest.raises(GraphError) as ei:
        assert_renderer_payload_clean(dirty)
    assert ei.value.code == GRAPH_INTERNAL
    assert "data_edge_ids" in json.dumps(ei.value.detail, ensure_ascii=False)


def test_renderer_payload_gate_accepts_projection() -> None:
    ds = _ds(["a", "b", "c"], [_edge("contain", "a", "b"), _edge("contain", "a", "c")])
    vm = ViewModelBuilder().build(_admission(ds))
    assert_renderer_payload_clean(renderer_projection(vm))     # 不抛即通过


def test_static_no_forbidden_access_in_renderer_path() -> None:
    """**静态断言**：``data_edge_ids`` 只允许出现在**非渲染**职责里，且 Renderer 入口必剥。

    三类合法访问（都不是"Renderer 读取"）：
    - ``audit_data_edges``：显式审计导出（B5 AuditLog / S2-9 expand）；
    - ``build``：VM **生产**侧，把数据边的 id 转存成审计字段；
    - ``validate_vm``：schema 类型校验（只检查是不是数组）。

    **真正要守的是 Renderer 侧**：``renderer_projection`` / ``shown_only``（Renderer 唯一
    允许消费的两个入口）里不得出现任何直接读取；并且可读字段白名单不含该字段。
    """
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    allowed = {"audit_data_edges", "build", "validate_vm"}
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        segment = ast.get_source_segment(source, node) or ""
        if any(pat in segment for pat in FORBIDDEN_ACCESS_PATTERNS):
            if node.name not in allowed:
                offenders.append(node.name)
    assert not offenders, f"非审计/非生产路径出现 data_edge_ids 直接读取：{offenders}"

    # Renderer 消费入口必须干净（这是 P0 断言）：只看**访问模式**，不看文档字符串里的
    # 字段名提及（docstring 说明"读不到它"是合法的）。
    for fn_name in ("renderer_projection", "shown_only"):
        fn = next((n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == fn_name), None)
        assert fn is not None, f"缺 Renderer 入口函数 {fn_name}"
        segment = ast.get_source_segment(source, fn) or ""
        hits = [pat for pat in FORBIDDEN_ACCESS_PATTERNS if pat in segment]
        assert not hits, f"{fn_name} 出现 data_edge_ids 读取模式 {hits}（Renderer 禁读）"

    # 白名单层面也必须挡住
    assert "data_edge_ids" not in RENDERER_READABLE_EDGE_FIELDS


# ── Renderer 只渲染 shown（S3-5 禁幽灵边）─────────────────────────────


def test_shown_only_filters_suppressed() -> None:
    ds = _ds(["a", "b", "c"], [_edge("contain", "a", "b"), _edge("contain", "b", "c")])
    vm = ViewModelBuilder().build(_admission(ds))
    visible = shown_only(vm)
    assert all(n["presence"] == "shown" for n in visible["nodes"])
    assert all(e["presence"] == "shown" for e in visible["edges"])
    assert len(visible["nodes"]) < len(vm["nodes"]), "用例应含 non-shown 节点"


# ── layout_group（S3-12 约束）───────────────────────────────────────


def test_layout_group_rules() -> None:
    ds = _ds(["a", "b"], [_edge("contain", "a", "b")])
    adm = _admission(ds)
    vm = ViewModelBuilder().build(adm, layout_groups={"a": {"semantic": False}})
    node = next(n for n in vm["nodes"] if n["id"] == "a")
    assert node["layout_group"] == {"semantic": False}

    with pytest.raises(GraphError):
        ViewModelBuilder().build(adm, layout_groups={"a": {"semantic": True}})


def test_layout_group_not_allowed_on_cluster() -> None:
    ds = _ds(["a", "b"], [_edge("contain", "a", "b")])
    adm = _admission(ds)
    # 伪造一个 cluster 节点看约束是否生效
    from dataclasses import replace
    cluster_nodes = tuple(
        {**n, "kind": "cluster"} if n["id"] == "a" else n for n in adm.nodes
    )
    fake = replace(adm, nodes=cluster_nodes)
    with pytest.raises(GraphError) as ei:
        ViewModelBuilder().build(fake, layout_groups={"a": {"semantic": False}})
    assert "layout_group" in ei.value.message


# ── 校验器活性（能拦住不合规 VM）─────────────────────────────────


def _valid_vm() -> dict:
    return json.loads(VM_FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("mutate,needle", [
    (lambda v: v.update({"clusters": []}), "非白名单"),
    (lambda v: v["nodes"][0].update({"color": "red"}), "非白名单"),
    (lambda v: v["nodes"][0].update({"role": "bridge"}), "role"),
    (lambda v: v["nodes"][0].update({"kind": "node"}), "kind"),
    (lambda v: v["nodes"][0].update({"presence": "maybe"}), "presence"),
    (lambda v: v["edges"][0].update({"endpoints": ["a", "b"]}), "非白名单"),
    (lambda v: v["edges"][0].update({"state": "highlight"}), "state"),
    (lambda v: v["nodes"][2].pop("rule_id"), "rule_id"),
])
def test_validate_vm_catches_violations(mutate, needle: str) -> None:
    vm = _valid_vm()
    mutate(vm)
    problems = validate_vm(vm)
    assert problems, "不合规 VM 竟通过校验"
    assert any(needle in p for p in problems), f"未指出 {needle}：{problems}"


def test_builder_rejects_non_admission_input() -> None:
    with pytest.raises(GraphError):
        ViewModelBuilder().build({"nodes": []})       # type: ignore[arg-type]


# ── 端到端 + 事务化 ────────────────────────────────────────────────


def test_vm_end_to_end_from_admission() -> None:
    """端到端：DataSource → GraphView → Admission → VM，且 X-RULE/subset 口径仍成立。"""
    ds = _ds(["a", "b", "c", "d"],
             [_edge("contain", "a", "b"), _edge("contain", "b", "c"),
              _edge("reference", "a", "d")])
    adm = _admission(ds)
    vm = ViewModelBuilder().build(adm, level_label="知识点")
    assert validate_vm(vm) == []
    assert check_x_rule(adm)["pass"] is True
    # VM 的 shown 集合与 Admission 的 shown 集合一致（唯一裁剪者，无二次裁剪）
    assert {n["id"] for n in shown_only(vm)["nodes"]} == set(adm.shown_node_ids())


def test_vm_is_deterministic_2x() -> None:
    """事务化 diff=0：同输入两次 VM sha 一致。"""
    ds = _ds(["a", "b", "c"], [_edge("contain", "a", "b"), _edge("contain", "b", "c")])
    v1 = ViewModelBuilder().build(_admission(ds), level_label="L1")
    v2 = ViewModelBuilder().build(_admission(ds), level_label="L1")
    assert v1["view_model_id"] == v2["view_model_id"]
    assert v1 == v2


def test_vm_id_changes_with_content() -> None:
    """防"恒定 sha"假确定性：内容变则 view_model_id 变。"""
    ds1 = _ds(["a", "b"], [_edge("contain", "a", "b")])
    ds2 = _ds(["a", "b", "c"], [_edge("contain", "a", "b"), _edge("contain", "a", "c")])
    v1 = ViewModelBuilder().build(_admission(ds1))
    v2 = ViewModelBuilder().build(_admission(ds2))
    assert v1["view_model_id"] != v2["view_model_id"]
