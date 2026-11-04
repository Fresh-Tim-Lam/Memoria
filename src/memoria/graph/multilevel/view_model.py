"""I-06 `ViewModelBuilder`：Admission 结果 → VM（**S3 白名单投影**）。

## 冻结依据

- **S3-12 VM 字段白名单**（冻结）：
  - 顶层：``view_model_id/level_id/level_label/dimension_id/view_family_id/nodes/edges``
  - 节点：``id/kind/label/role/member_count?/aggregate_count?/representative?/
    root_exempt?/range_ok?/layout_group?{semantic:false}``
  - 边：``id/type/state/presence?/data_edge_ids?``
  - **簇/run/dendrogram/候选状态不进 VM**；**``metrics`` 不进 VM**（用显式
    ``member_count``/``aggregate_count``）。
- **S3-ADDENDUM-1**：节点白名单扩展 ``presence?/rule_id?``（均为 view-status 字段，
  不改变节点事实）；Renderer 仍只渲染 ``presence=shown``。
- **R-S3-9 / S4-10**：``data_edge_ids`` 仅审计与 ``expand_data_edges`` 用，
  **Renderer 必须拒绝读取**；``aggregate_count`` 由取景层显式给出，不遍历 ``data_edge_ids``。
- **S3-1/S3-5**：``kind ∈ {kp, cluster}``（禁第三类型）；``role ∈ {member}``（v1 只有 member，
  **无 role=bridge 视觉**）；边 ``state`` 仅用于 bridge 叠加（``state="bridge_only"``，不改 type；
  桥分类归 S4/S3 视觉，B3 不计算 ⇒ 本模块默认不输出 ``state``）。
- **S4-11 / S2-11**：VM **不含导航字段**、不含 frame/mode、不含簇/run/候选状态。

## ``data_edge_ids`` 的「Renderer 禁读」怎么被机器保证

1. 白名单常量 :data:`RENDERER_READABLE_EDGE_FIELDS` **不含** ``data_edge_ids``；
2. :func:`renderer_projection` 是 Renderer 唯一允许的输入入口，它**剥掉**禁读字段；
3. :func:`assert_renderer_payload_clean` 对任何"含禁读字段"的 Renderer 输入**抛错**；
4. 测试用**静态扫描**断言：除标注为审计用途的函数外，模块内不出现对
   ``data_edge_ids`` 的实质读取（``.get("data_edge_ids")``/``["data_edge_ids"]``）。
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from memoria.graph.multilevel.admission import (
    PRESENCE_SHOWN,
    PRESENCE_VALUES,
    AdmissionResult,
)
from memoria.graph.multilevel.errors import GRAPH_INTERNAL, GraphError

# ── 白名单（S3-12 + S3-ADDENDUM-1，冻结）───────────────────────────────

VM_TOP_FIELDS: tuple[str, ...] = (
    "view_model_id", "level_id", "level_label", "dimension_id", "view_family_id",
    "nodes", "edges",
)

VM_NODE_FIELDS: tuple[str, ...] = (
    "id", "kind", "label", "role",
    "member_count", "aggregate_count", "representative", "root_exempt", "range_ok",
    "layout_group",
    "presence", "rule_id",            # S3-ADDENDUM-1（view-status）
)

VM_NODE_REQUIRED: tuple[str, ...] = ("id", "kind", "label", "role")

VM_EDGE_FIELDS: tuple[str, ...] = ("id", "type", "state", "presence", "data_edge_ids")

VM_EDGE_REQUIRED: tuple[str, ...] = ("id", "type")

#: VM 节点 kind / role（S3-1、R-S3-3：v1 只有 member，无 bridge 视觉）。
VM_NODE_KINDS: tuple[str, ...] = ("kp", "cluster")
VM_NODE_ROLES: tuple[str, ...] = ("member",)

#: 边 ``state`` 唯一合法值（bridge 叠加；B3 不计算桥 ⇒ 默认不产出）。
VM_EDGE_STATES: tuple[str, ...] = ("bridge_only",)

#: **Renderer 禁读**字段（R-S3-9）：仅审计/expand 用。
RENDERER_FORBIDDEN_EDGE_FIELDS: tuple[str, ...] = ("data_edge_ids",)

#: Renderer 允许读取的边字段 = 白名单 − 禁读。
RENDERER_READABLE_EDGE_FIELDS: tuple[str, ...] = tuple(
    f for f in VM_EDGE_FIELDS if f not in RENDERER_FORBIDDEN_EDGE_FIELDS
)

#: 禁读字段的**静态扫描**标记：代码里出现该访问模式即视为 Renderer 读取。
FORBIDDEN_ACCESS_PATTERNS: tuple[str, ...] = (
    '.get("data_edge_ids")',
    ".get('data_edge_ids')",
    '["data_edge_ids"]',
    "['data_edge_ids']",
)


def canonical_bytes(payload: object) -> bytes:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def sha256_canonical(payload: object) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


# ── 构建 ────────────────────────────────────────────────────────────────


@dataclass
class ViewModelBuilder:
    """把 AdmissionResult 投影成 VM。**纯函数式、确定、事务化**（同输入 ⇒ 同 VM sha）。"""

    def build(
        self,
        admission: AdmissionResult,
        *,
        level_label: str = "",
        labels: Mapping[str, str] | None = None,
        layout_groups: Mapping[str, Mapping] | None = None,
    ) -> dict:
        """构造 VM。

        :param labels: 可选 ``{节点id: label}``（簇视觉 label 公式归 S3/B4；B3 缺省用稳定 id）
        :param layout_groups: 可选 ``{节点id: {"semantic": False, ...}}``；
            仅 ``no_semantic_edges`` 状态可用（S3-12），且必须 ``semantic=false``、非 cluster。
        """
        if not isinstance(admission, AdmissionResult):
            raise GraphError(GRAPH_INTERNAL, "build 需要 AdmissionResult",
                             detail={"s3_code": "S3_VM_INPUT_INVALID"})
        labels = dict(labels or {})
        layout_groups = dict(layout_groups or {})

        nodes: list[dict] = []
        for rec in admission.nodes:
            nid = str(rec["id"])
            node = {
                "id": nid,
                "kind": str(rec["kind"]),
                "label": str(labels.get(nid) or nid),   # 确定性占位；S3-1 公式归 B4
                "role": "member",
                "presence": str(rec["presence"]),
            }
            rule_id = rec.get("rule_id")
            if rule_id:
                node["rule_id"] = str(rule_id)
            if nid in layout_groups:
                node["layout_group"] = _clean_layout_group(layout_groups[nid], node["kind"])
            nodes.append(_project(node, VM_NODE_FIELDS))

        edges: list[dict] = []
        for rec in admission.edges:
            edge = {
                "id": str(rec["id"]),
                "type": str(rec["type"]),
                "presence": str(rec["presence"]),
            }
            # 聚合边才需要 data_edge_ids（审计/expand；Renderer 禁读）
            data_ids = [str(x) for x in (rec.get("data_edge_ids") or ())]
            if int(rec.get("aggregate_count") or 0) > 1 and data_ids:
                edge["data_edge_ids"] = data_ids
            edges.append(_project(edge, VM_EDGE_FIELDS))

        nodes.sort(key=lambda n: n["id"])
        edges.sort(key=lambda e: e["id"])

        body = {
            "level_id": admission.frame_spec.level,
            "level_label": str(level_label),
            "dimension_id": admission.frame_spec.dimension_id,
            "view_family_id": admission.frame_spec.view_family,
            "nodes": nodes,
            "edges": edges,
        }
        vm = {"view_model_id": f"vm_{sha256_canonical(body)[:32]}", **body}
        problems = validate_vm(vm)
        if problems:
            raise GraphError(
                GRAPH_INTERNAL,
                f"VM 不合 S3 白名单：{problems[0]}",
                detail={"problems": problems[:10], "s3_code": "S3_VM_WHITELIST_VIOLATION"},
            )
        return vm


def _project(source: Mapping, whitelist: Sequence[str]) -> dict:
    """只保留白名单字段（``None`` 不落盘 ⇒ 输出稳定）。"""
    return {k: source[k] for k in whitelist if k in source and source[k] is not None}


def _clean_layout_group(group: Mapping, kind: str) -> dict:
    """S3-12：``layout_group`` 必须 ``semantic=false``、非 cluster（不得产生簇徽标）。"""
    if kind == "cluster":
        raise GraphError(GRAPH_INTERNAL, "layout_group 不得用于 cluster 节点（S3-12）",
                         detail={"s3_code": "S3_LAYOUT_GROUP_INVALID"})
    if group.get("semantic") is not False:
        raise GraphError(GRAPH_INTERNAL, "layout_group.semantic 必须为 false（S3-12）",
                         detail={"s3_code": "S3_LAYOUT_GROUP_INVALID"})
    return {"semantic": False}


# ── 校验 ────────────────────────────────────────────────────────────────


def validate_vm(vm: Mapping) -> list[str]:
    """按 S3-12 + ADDENDUM-1 校验 VM；返回问题列表（空 = 合规）。"""
    problems: list[str] = []
    if not isinstance(vm, Mapping):
        return ["VM 必须是对象"]

    extra_top = sorted(set(vm) - set(VM_TOP_FIELDS))
    if extra_top:
        problems.append(f"VM 顶层出现非白名单字段：{extra_top}")
    for field_name in VM_TOP_FIELDS:
        if field_name not in vm and field_name not in ("nodes", "edges"):
            problems.append(f"VM 缺字段 {field_name}")

    for idx, node in enumerate(vm.get("nodes") or []):
        extra = sorted(set(node) - set(VM_NODE_FIELDS))
        if extra:
            problems.append(f"nodes[{idx}] 非白名单字段：{extra}")
        for field_name in VM_NODE_REQUIRED:
            if field_name not in node:
                problems.append(f"nodes[{idx}] 缺必填 {field_name}")
        if node.get("kind") not in VM_NODE_KINDS:
            problems.append(f"nodes[{idx}] kind 非法：{node.get('kind')!r}")
        if node.get("role") not in VM_NODE_ROLES:
            problems.append(f"nodes[{idx}] role 非法：{node.get('role')!r}（v1 只有 member）")
        if "presence" in node and node["presence"] not in PRESENCE_VALUES:
            problems.append(f"nodes[{idx}] presence 非法：{node['presence']!r}")
        if node.get("presence") != PRESENCE_SHOWN and not node.get("rule_id"):
            problems.append(f"nodes[{idx}] non-shown 缺 rule_id（X-RULE）")
        if "layout_group" in node:
            if node["kind"] == "cluster":
                problems.append(f"nodes[{idx}] layout_group 不得用于 cluster")
            if node["layout_group"].get("semantic") is not False:
                problems.append(f"nodes[{idx}] layout_group.semantic 必须 false")

    for idx, edge in enumerate(vm.get("edges") or []):
        extra = sorted(set(edge) - set(VM_EDGE_FIELDS))
        if extra:
            problems.append(f"edges[{idx}] 非白名单字段：{extra}")
        for field_name in VM_EDGE_REQUIRED:
            if field_name not in edge:
                problems.append(f"edges[{idx}] 缺必填 {field_name}")
        if "presence" in edge and edge["presence"] not in PRESENCE_VALUES:
            problems.append(f"edges[{idx}] presence 非法：{edge['presence']!r}")
        if edge.get("presence") != PRESENCE_SHOWN and not edge.get("rule_id") \
                and edge.get("presence") is not None:
            # VM 边白名单不含 rule_id（S3-12）；边的 rule 归属查 AdmissionResult。
            # 因此这里只要求 presence 合法，不要求 rule_id（避免与冻结白名单冲突）。
            pass
        if "state" in edge and edge["state"] not in VM_EDGE_STATES:
            problems.append(f"edges[{idx}] state 非法：{edge['state']!r}")
        if "data_edge_ids" in edge and not isinstance(edge["data_edge_ids"], list):
            problems.append(f"edges[{idx}] data_edge_ids 必须是数组（仅审计用）")

    # 簇/run/候选状态不得进 VM（S3-12/S4-11/S2-11）
    forbidden_top = {"clusters", "run_id", "dendrogram", "metrics", "candidates",
                     "frame_id", "nav", "mode", "focus", "hop", "capabilities"}
    leaked = sorted(forbidden_top & set(vm))
    if leaked:
        problems.append(f"VM 泄漏了不得进 VM 的字段：{leaked}")
    return problems


# ── Renderer 边界（R-S3-9）──────────────────────────────────────────────


def renderer_projection(vm: Mapping) -> dict:
    """Renderer **唯一允许**的输入构造：剥掉禁读字段，保留只读白名单。

    Renderer 拿到这份投影后再也读不到 ``data_edge_ids``（R-S3-9/S3-12）。
    """
    out = {k: copy.deepcopy(vm[k]) for k in VM_TOP_FIELDS if k in vm}
    out_edges: list[dict] = []
    for edge in vm.get("edges") or []:
        out_edges.append({k: copy.deepcopy(edge[k]) for k in RENDERER_READABLE_EDGE_FIELDS
                          if k in edge})
    out["edges"] = out_edges
    out_nodes: list[dict] = []
    for node in vm.get("nodes") or []:
        out_nodes.append({k: copy.deepcopy(node[k]) for k in VM_NODE_FIELDS if k in node})
    out["nodes"] = out_nodes
    return out


def assert_renderer_payload_clean(payload: Mapping) -> None:
    """Renderer 输入闸门：含任何禁读字段 ⇒ 抛错（fail-closed，不静默忽略）。"""
    leaked: list[str] = []
    for edge in payload.get("edges") or ():
        if isinstance(edge, Mapping):
            leaked.extend(sorted(set(edge) & set(RENDERER_FORBIDDEN_EDGE_FIELDS)))
    if leaked:
        raise GraphError(
            GRAPH_INTERNAL,
            f"Renderer 输入含禁读字段 {sorted(set(leaked))}（R-S3-9 fail-closed）",
            detail={"s3_code": "S3_RENDERER_FORBIDDEN_READ",
                    "fields": sorted(set(leaked))},
        )


def shown_only(vm: Mapping) -> dict:
    """Renderer 视图：只保留 ``presence=shown`` 的节点与边（S3-5：禁幽灵边）。"""
    out = {k: copy.deepcopy(vm[k]) for k in VM_TOP_FIELDS if k in vm}
    out["nodes"] = [copy.deepcopy(n) for n in vm.get("nodes") or ()
                    if n.get("presence") == PRESENCE_SHOWN]
    out["edges"] = [copy.deepcopy(e) for e in vm.get("edges") or ()
                    if e.get("presence") == PRESENCE_SHOWN]
    return out


def audit_data_edges(vm: Mapping) -> dict[str, list[str]]:
    """**导出**审计视图（B5 AuditLog / S2-9 ``expand_data_edges`` 用；Renderer 不得调用）。

    这是唯一允许"读" ``data_edge_ids`` 的位置，且只做**转存**，不参与任何渲染决策。
    """
    return {
        str(edge["id"]): [str(x) for x in (edge.get("data_edge_ids") or ())]
        for edge in vm.get("edges") or ()
        if isinstance(edge, Mapping) and edge.get("data_edge_ids")
    }
