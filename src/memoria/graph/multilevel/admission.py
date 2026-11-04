"""I-05 `AdmissionService`：S4 取景层——**presence 的唯一裁剪者**（P0）。

## 冻结依据

- **S4-1**：``presence ∈ {shown, suppressed, unknown}`` 只由本层产生；只改取景，**不改事实**
  （type/label/contain_kind 原样）。Renderer 只校验/渲染已选 VM。
- **S4-2**：排序键冻结 ``(tier, hop, relation_class, label_rank, canonical_id)``；
  ``relation_class = semantic < structural < navigation < reference``；同输入同结果，无静默截断。
- **S4-3/S4-4**：默认只看 focus 的**一跳**（``F={focus}``，每端点最多一条边进入）；
  **不闭包、不带背后图**；``max_hop(shown) ≤ hop_budget``（默认 1）；2 跳只能由 S5 显式触发。
- **S4-5**：``MANDATORY``：A 维 ``{focus}``；H 维 ``{focus} ∪ first K children(focus)``，
  v1 ``K = MANDATORY_CONTEXT_CAP = 2``；预算内先保 MANDATORY；**仅 MANDATORY 超预算**
  才 fail-visible（``GRAPH_BUDGET_INVALID``）。
- **S4-6**：``rule_id`` 11 类统一；``unknown`` **仅**由后 4 类触发
  （``endpoint.unresolved/source.unavailable/admission.undecided/invalid.data``）。
- **S4-9 / R-S4-7 / R-S4-9**：全展开与默认走同一 ``admit``；subset 由**构造**保证：
  ① ``candidates(full) ⊇ candidates(default)``；② ``reserved(full) == shown(default)``；
  ③ ``budget_full ≥ budget_default``。三前提任一不成立 ⇒ 失败**可见**，不静默补入。
- **S6-6**：``S4_FRAME_SPEC{level, view_family, dimension_id, focus, hop, new_hop, mode, budget}``
  ——**严格 8 字段**，不得加导航字段（frame_id/edition 由 S5 派生，不进 S4 输入）。
- **R-B2-5**：``contain_kind=semantic`` 或 ``label=semantic`` 但缺
  ``assertion_source``/``curated_by``/``curated_at`` ⇒ **显式报 ``GRAPH_EDGE_SEMANTIC_MISMATCH``**
  （可见失败），不得静默当非语义；结构边不要求这些字段；读取路径不重算 ``quote_sha256``。

## 度量（S8）

- ``X-RULE = (non-shown 节点中有 rule_id 的 + non-shown 边中有 rule_id 的) /
  (全部 non-shown 节点 + 全部 non-shown 边) = 100%``，分项 ``X-NODE-RULE`` / ``X-EDGE-RULE``；
  **rule_id 为 null 即 FAIL**。本模块用 :func:`check_x_rule` 计算，并在产出时**fail-closed
  自检**（任何 non-shown 缺 rule_id ⇒ 抛内部错误，不会"安静地"返回不合格结果）。
- ``closure_violations``：shown 项里 hop > hop_budget 的条目数（必须 0）。
- ``behind_violations``：shown 里出现"一跳端点的邻居"（= 2 跳）的条目数（必须 0）。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from memoria.graph.multilevel.errors import (
    GRAPH_BUDGET_INVALID,
    GRAPH_EDGE_SEMANTIC_MISMATCH,
    GRAPH_INTERNAL,
    GraphError,
)

# ── 冻结枚举 ────────────────────────────────────────────────────────────

PRESENCE_SHOWN = "shown"
PRESENCE_SUPPRESSED = "suppressed"
PRESENCE_UNKNOWN = "unknown"

#: S4-6 / R-S4-5：三值闭合。
PRESENCE_VALUES: tuple[str, ...] = (PRESENCE_SHOWN, PRESENCE_SUPPRESSED, PRESENCE_UNKNOWN)

#: S4-6：``rule_id`` 11 类（顺序即文档顺序，不得增删——增删须 S4 修订）。
RULE_IDS: tuple[str, ...] = (
    "dimension.sources",
    "dimension.direction",
    "dimension.level.cross_layer",
    "hop.budget",
    "node.budget",
    "edge.budget",
    "cluster.folded",
    "endpoint.unresolved",
    "source.unavailable",
    "admission.undecided",
    "invalid.data",
)

#: S4-6：**只有**这 4 类可以触发 ``unknown``（"unknown ≠ 无关系"）。
UNKNOWN_RULE_IDS: frozenset[str] = frozenset({
    "endpoint.unresolved",
    "source.unavailable",
    "admission.undecided",
    "invalid.data",
})

#: S4-5 / R-S4-10：H 维 MANDATORY 的上下文子节点上限（v1 冻结 = 2）。
MANDATORY_CONTEXT_CAP = 2

#: S4-2：关系类排序（``semantic < structural < navigation < reference``）。
RELATION_CLASS_ORDER: dict[str, int] = {
    "semantic": 0,
    "structural": 1,
    "navigation": 2,
    "reference": 3,
}

#: S6-6：``S4_FRAME_SPEC`` 严格 8 字段（多一个少一个都 fail-closed）。
FRAME_SPEC_FIELDS: tuple[str, ...] = (
    "level", "view_family", "dimension_id", "focus", "hop", "new_hop", "mode", "budget",
)

#: S4-9：模式（default = 默认取景；full = 全展开）。S5 的导航模式不在此。
ADMISSION_MODES: tuple[str, ...] = ("default", "full")

#: S8 冻结预算（P0 结构断言用）。
DEFAULT_BUDGET: dict[str, int] = {"max_nodes": 200, "max_edges": 400}

#: 维度 → ``E_relation(D)``（S0-3/S1-4/S1-5）。
#: H（层次导航）= 只沿 contain 下钻、无 hop 预算；A（关联扩展）= ``E_relation_min`` 全集合。
_A_RELATION_TYPES: tuple[str, ...] = ("contain", "reference", "extend")
_H_RELATION_TYPES: tuple[str, ...] = ("contain",)

#: 语义标记的两个来源（R-B2-5）。
_SEMANTIC_MARKER_KEYS: tuple[str, ...] = ("contain_kind", "label")


def canonical_bytes(payload: object) -> bytes:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def sha256_canonical(payload: object) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


# ── FrameSpec（S6-6 严格 8 字段）─────────────────────────────────────────


@dataclass(frozen=True)
class FrameSpec:
    """``S4_FRAME_SPEC``：**严格 S4 冻结字段**，不含 frame_id / edition（S5 派生）。"""

    level: str
    view_family: str
    dimension_id: str
    focus: str
    hop: int = 1
    new_hop: bool = False
    mode: str = "default"
    budget: tuple[tuple[str, int], ...] = tuple(sorted(DEFAULT_BUDGET.items()))

    def __post_init__(self) -> None:
        for name in ("level", "view_family", "dimension_id", "focus"):
            val = getattr(self, name)
            if not isinstance(val, str) or not val:
                raise GraphError(GRAPH_INTERNAL, f"frame_spec.{name} 必须是非空字符串",
                                 detail={"s4_code": "S4_FRAME_SPEC_INVALID"})
        if not isinstance(self.hop, int) or isinstance(self.hop, bool) or self.hop < 1:
            raise GraphError(GRAPH_INTERNAL, "frame_spec.hop 必须是 ≥1 整数",
                             detail={"s4_code": "S4_FRAME_SPEC_INVALID"})
        if self.hop > 2:
            raise GraphError(GRAPH_INTERNAL, "v1 hop 上限为 2（S1-5）",
                             detail={"s4_code": "S4_FRAME_SPEC_INVALID"})
        if not isinstance(self.new_hop, bool):
            raise GraphError(GRAPH_INTERNAL, "frame_spec.new_hop 必须是 bool",
                             detail={"s4_code": "S4_FRAME_SPEC_INVALID"})
        if self.mode not in ADMISSION_MODES:
            raise GraphError(GRAPH_INTERNAL, f"frame_spec.mode 必须是 {ADMISSION_MODES} 之一",
                             detail={"s4_code": "S4_FRAME_SPEC_INVALID"})
        if not isinstance(self.budget, tuple) or not self.budget:
            raise GraphError(GRAPH_INTERNAL, "frame_spec.budget 必须是非空 (key,int) 序列",
                             detail={"s4_code": "S4_FRAME_SPEC_INVALID"})
        budget = dict(self.budget)
        for key in ("max_nodes", "max_edges"):
            if key not in budget:
                raise GraphError(GRAPH_INTERNAL, f"frame_spec.budget 缺 {key}",
                                 detail={"s4_code": "S4_FRAME_SPEC_INVALID"})
            val = budget[key]
            if not isinstance(val, int) or isinstance(val, bool) or val < 1:
                raise GraphError(GRAPH_INTERNAL, f"budget.{key} 必须是 ≥1 整数",
                                 detail={"s4_code": "S4_FRAME_SPEC_INVALID"})

    def budget_dict(self) -> dict[str, int]:
        return dict(self.budget)

    def to_dict(self) -> dict:
        """canonical S4_FRAME_SPEC（8 字段，budget 展开为对象）。"""
        return {
            "level": self.level,
            "view_family": self.view_family,
            "dimension_id": self.dimension_id,
            "focus": self.focus,
            "hop": self.hop,
            "new_hop": self.new_hop,
            "mode": self.mode,
            "budget": self.budget_dict(),
        }

    def canonical_sha(self) -> str:
        return sha256_canonical(self.to_dict())


def make_frame_spec(
    *, level: str, view_family: str, dimension_id: str, focus: str,
    hop: int = 1, new_hop: bool = False, mode: str = "default",
    max_nodes: int = DEFAULT_BUDGET["max_nodes"],
    max_edges: int = DEFAULT_BUDGET["max_edges"],
) -> FrameSpec:
    return FrameSpec(
        level=level, view_family=view_family, dimension_id=dimension_id, focus=focus,
        hop=hop, new_hop=new_hop, mode=mode,
        budget=tuple(sorted({"max_nodes": max_nodes, "max_edges": max_edges}.items())),
    )


# ── 结果载体 ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AdmissionResult:
    """Admission 结果：**全部候选**逐条 presence+rule_id（S4-10/R-S4-4）。"""

    frame_spec: FrameSpec
    nodes: tuple[dict, ...] = ()
    edges: tuple[dict, ...] = ()
    mandatory_node_ids: tuple[str, ...] = ()
    rule_histogram: tuple[tuple[str, int], ...] = ()
    closure_violations: tuple[str, ...] = ()
    behind_violations: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    # -- 派生 --------------------------------------------------------
    def shown_node_ids(self) -> tuple[str, ...]:
        return tuple(n["id"] for n in self.nodes if n["presence"] == PRESENCE_SHOWN)

    def shown_edge_ids(self) -> tuple[str, ...]:
        return tuple(e["id"] for e in self.edges if e["presence"] == PRESENCE_SHOWN)

    def suppressed_summary(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for item in (*self.nodes, *self.edges):
            if item["presence"] != PRESENCE_SHOWN:
                out[item["rule_id"]] = out.get(item["rule_id"], 0) + 1
        return dict(sorted(out.items()))

    def counts(self) -> dict:
        return {
            "candidate_nodes": len(self.nodes),
            "candidate_edges": len(self.edges),
            "shown_nodes": len(self.shown_node_ids()),
            "shown_edges": len(self.shown_edge_ids()),
            "mandatory_nodes": len(self.mandatory_node_ids),
            "suppressed": sum(1 for i in (*self.nodes, *self.edges)
                              if i["presence"] == PRESENCE_SUPPRESSED),
            "unknown": sum(1 for i in (*self.nodes, *self.edges)
                           if i["presence"] == PRESENCE_UNKNOWN),
        }

    def max_hop_shown(self) -> int:
        hops = [int(i.get("hop") or 0) for i in (*self.nodes, *self.edges)
                if i["presence"] == PRESENCE_SHOWN]
        return max(hops) if hops else 0

    def to_dict(self) -> dict:
        return {
            "frame_spec": self.frame_spec.to_dict(),
            "nodes": [dict(n) for n in self.nodes],
            "edges": [dict(e) for e in self.edges],
            "mandatory_node_ids": list(self.mandatory_node_ids),
            "rule_histogram": dict(self.rule_histogram),
            "closure_violations": list(self.closure_violations),
            "behind_violations": list(self.behind_violations),
            "notes": list(self.notes),
        }

    def canonical_sha(self) -> str:
        return sha256_canonical(self.to_dict())


# ── 度量（S8）───────────────────────────────────────────────────────────


def check_x_rule(result: AdmissionResult) -> dict:
    """``X-RULE`` 节点+边联合 + 分项（S8/R-S8-1）；``null`` 即 FAIL。"""
    def ratio(items: Sequence[dict]) -> tuple[int, int, float | None]:
        non_shown = [i for i in items if i["presence"] != PRESENCE_SHOWN]
        if not non_shown:
            return 0, 0, 1.0            # 无 non-shown ⇒ 空真，记 100%
        with_rule = sum(1 for i in non_shown if i.get("rule_id"))
        return with_rule, len(non_shown), with_rule / len(non_shown)

    n_ok, n_total, n_ratio = ratio(result.nodes)
    e_ok, e_total, e_ratio = ratio(result.edges)
    ok_all = n_ok + e_ok
    total_all = n_total + e_total
    joint = 1.0 if total_all == 0 else ok_all / total_all
    return {
        "x_node_rule": n_ratio,
        "x_edge_rule": e_ratio,
        "x_rule": joint,
        "node_with_rule": n_ok,
        "node_non_shown": n_total,
        "edge_with_rule": e_ok,
        "edge_non_shown": e_total,
        "pass": joint == 1.0 and n_ratio == 1.0 and e_ratio == 1.0,
    }


# ── R-B2-5 语义标记证据检查 ──────────────────────────────────────────────


def assert_semantic_marker_evidence(edges: Iterable[Mapping]) -> None:
    """R-B2-5：标了 semantic 就必须带全证据，否则**显式失败**（不静默降级）。

    命中条件：``contain_kind == "semantic"`` **或** ``label == "semantic"``。
    要求：``assertion_source``（含 file/line_start/line_end）+ ``curated_by`` + ``curated_at``。
    结构边（缺省 / ``structural``）**不要求**这些字段。
    读取路径**不**重算 ``quote_sha256``（B5/G6 范畴）。
    """
    for edge in edges:
        if not isinstance(edge, Mapping):
            continue
        marked = any(str(edge.get(k) or "") == "semantic" for k in _SEMANTIC_MARKER_KEYS)
        if not marked:
            continue
        problems: list[str] = []
        source = edge.get("assertion_source")
        if not isinstance(source, Mapping):
            problems.append("缺 assertion_source")
        else:
            if not source.get("file"):
                problems.append("assertion_source.file 缺失")
            for key in ("line_start", "line_end"):
                if not isinstance(source.get(key), int) or isinstance(source.get(key), bool):
                    problems.append(f"assertion_source.{key} 缺失或非整数")
        if not str(edge.get("curated_by") or "").strip():
            problems.append("缺 curated_by")
        if not str(edge.get("curated_at") or "").strip():
            problems.append("缺 curated_at")
        if problems:
            raise GraphError(
                GRAPH_EDGE_SEMANTIC_MISMATCH,
                "边标了 semantic 但证据不全（R-B2-5：可见失败，不得静默当非语义）",
                detail={
                    "edge_type": edge.get("type"),
                    "source_id": edge.get("source_id"),
                    "targets": list(edge.get("targets") or []),
                    "problems": problems,
                },
            )


# ── AdmissionService ────────────────────────────────────────────────────


@dataclass
class AdmissionService:
    """S4 取景。**纯函数式**：不改事实、不写盘、无导航状态。"""

    mandatory_context_cap: int = MANDATORY_CONTEXT_CAP

    # -- 公共入口 ------------------------------------------------------
    def admit(
        self,
        *,
        frame_spec: FrameSpec,
        graph_view,
        datasource=None,
        run=None,
        relation_sources: Sequence[str] | None = None,
        source_available: bool = True,
        reserved: Iterable[str] | None = None,
    ) -> AdmissionResult:
        """对 ``(frame_spec, graph_view)`` 做一次取景。

        :param reserved: 仅 ``mode="full"`` 用：``shown(default)`` 必须**全部保留**（R-S4-7 ②）。

        未知/保留维度 ⇒ fail-closed（S4-7/S1-2）；MANDATORY 超预算 ⇒ ``GRAPH_BUDGET_INVALID``。
        """
        if not isinstance(frame_spec, FrameSpec):
            raise GraphError(GRAPH_INTERNAL, "frame_spec 必须是 FrameSpec",
                             detail={"s4_code": "S4_FRAME_SPEC_INVALID"})
        relation_types = self._relation_types(frame_spec, relation_sources)

        nodes_meta, id_map = self._partition(graph_view)
        if frame_spec.focus not in nodes_meta:
            # 焦点不在本层 ⇒ 无输出（fail-closed），不是"空视图"静默
            raise GraphError(
                GRAPH_INTERNAL,
                f"focus {frame_spec.focus!r} 不在 level {frame_spec.level!r} 的分区内",
                detail={"s4_code": "S4_FOCUS_UNRESOLVED"},
            )

        # R-B2-5：先做语义标记证据检查（数据层，先于任何取景判断）
        raw_edges = tuple(getattr(datasource, "edges", ()) or ()) if datasource is not None else ()
        assert_semantic_marker_evidence(raw_edges)

        budget = frame_spec.budget_dict()
        max_nodes = int(budget["max_nodes"])
        max_edges = int(budget["max_edges"])

        # ① MANDATORY（S4-5）
        mandatory = self._mandatory_ids(frame_spec, raw_edges, id_map, relation_types)
        if len(mandatory) > max_nodes:
            raise GraphError(
                GRAPH_BUDGET_INVALID,
                f"MANDATORY 必选集 {len(mandatory)} 超 max_nodes={max_nodes}（仅必选超预算才失败）",
                detail={"mandatory": sorted(mandatory), "max_nodes": max_nodes},
            )

        # ② 边分类（数据边 → 视图边，含聚合 data_edge_ids）
        edge_records, edge_unknown = self._classify_edges(
            frame_spec=frame_spec, raw_edges=raw_edges, id_map=id_map,
            relation_types=relation_types, source_available=source_available,
            datasource_present=datasource is not None,
        )

        # ③ 一跳 + 排序 + 预算（S4-2/S4-3/S4-4）
        hop_nodes = self._one_hop_nodes(frame_spec, edge_records)
        ordered_nodes = self._order_nodes(
            nodes_meta=nodes_meta, mandatory=mandatory, one_hop=hop_nodes,
            focus=frame_spec.focus,
        )
        shown_nodes, _node_counts = self._select(
            ordered_nodes, budget=max_nodes, reserved=reserved,
            hop_budget=frame_spec.hop,
        )

        edge_candidates = sorted(
            edge_records,
            key=lambda r: (
                0 if r["incident"] else 1,                       # tier：先 focus 相关
                int(r["hop"]),
                RELATION_CLASS_ORDER.get(r["relation_class"], 9),
                r["label_rank"],
                r["id"],
            ),
        )
        shown_edge_ids, _edge_counts = self._select_edge_records(
            edge_candidates, budget=max_edges, reserved=reserved,
        )

        # ④ 组装 nodes/edges（含 non-shown 的 rule_id）
        nodes_out = self._assemble_nodes(
            ordered_nodes=ordered_nodes, shown=shown_nodes, mandatory=mandatory,
            focus=frame_spec.focus, source_available=source_available,
            datasource_present=datasource is not None,
            hop_budget=frame_spec.hop,
        )
        edges_out = self._assemble_edges(
            edge_candidates=edge_candidates, shown=shown_edge_ids,
        )

        result = AdmissionResult(
            frame_spec=frame_spec,
            nodes=tuple(nodes_out),
            edges=tuple(edges_out),
            mandatory_node_ids=tuple(sorted(mandatory)),
            # 直方图**从实际结果统计**（含所有 non-shown 的 rule_id），
            # 不能只记预算类，否则与 S4 suppressed_summary 口径不一致（X-SUMMARY 门禁）。
            rule_histogram=(),
            notes=tuple(edge_unknown),
        )
        result = AdmissionResult(
            frame_spec=result.frame_spec, nodes=result.nodes, edges=result.edges,
            mandatory_node_ids=result.mandatory_node_ids,
            rule_histogram=tuple(sorted(result.suppressed_summary().items())),
            closure_violations=result.closure_violations,
            behind_violations=result.behind_violations,
            notes=result.notes,
        )

        # ⑤ S4 自洽性机检（构造性保证 → 但必须**验证**，不能只声称）
        violations = self._self_check(result)
        result = AdmissionResult(
            frame_spec=result.frame_spec, nodes=result.nodes, edges=result.edges,
            mandatory_node_ids=result.mandatory_node_ids,
            rule_histogram=result.rule_histogram,
            closure_violations=tuple(violations["closure"]),
            behind_violations=tuple(violations["behind"]),
            notes=result.notes,
        )
        # X-RULE 必须 100%：任何 non-shown 缺 rule_id ⇒ 立即失败（不返回不合格结果）
        x = check_x_rule(result)
        if not x["pass"]:
            raise GraphError(
                GRAPH_INTERNAL,
                "X-RULE < 100%（non-shown 缺 rule_id，S8/R-S8-1 直接 FAIL）",
                detail={"x_rule": x},
            )
        return result

    # -- 全展开 + subset 构造（S4-9 / R-S4-7）------------------------
    def admit_with_subset(
        self,
        *,
        frame_spec: FrameSpec,
        graph_view,
        datasource=None,
        run=None,
        relation_sources: Sequence[str] | None = None,
        source_available: bool = True,
        full_budget: Mapping[str, int] | None = None,
    ) -> tuple[AdmissionResult, AdmissionResult, dict]:
        """跑 default + full 并验证 subset 三前提（R-S4-7），返回 ``(default, full, report)``。"""
        default = self.admit(
            frame_spec=frame_spec, graph_view=graph_view, datasource=datasource,
            run=run, relation_sources=relation_sources, source_available=source_available,
        )
        fb = dict(full_budget or DEFAULT_BUDGET)
        dbudget = frame_spec.budget_dict()
        budget_ok = int(fb["max_nodes"]) >= int(dbudget["max_nodes"]) and \
                    int(fb["max_edges"]) >= int(dbudget["max_edges"])
        if not budget_ok:
            raise GraphError(
                GRAPH_BUDGET_INVALID,
                "budget_full < budget_default ⇒ subset 构造前提不成立（R-S4-7/R-S4-9）",
                detail={"budget_full": fb, "budget_default": dbudget},
            )
        full_spec = make_frame_spec(
            level=frame_spec.level, view_family=frame_spec.view_family,
            dimension_id=frame_spec.dimension_id, focus=frame_spec.focus,
            # S4-4：**2 跳只能由 S5 EXPLICIT_NEW_HOP 触发** ⇒ full 也**不加跳**，
            # 只放开预算（全展开 = 显示全部 hop≤budget 的候选，不是看得更远）。
            hop=frame_spec.hop,
            new_hop=frame_spec.new_hop, mode="full",
            max_nodes=int(fb["max_nodes"]), max_edges=int(fb["max_edges"]),
        )
        default_shown = set(default.shown_node_ids())
        full = self.admit(
            frame_spec=full_spec, graph_view=graph_view, datasource=datasource,
            run=run, relation_sources=relation_sources,
            source_available=source_available, reserved=default_shown,
        )
        # R-S4-7 三前提
        candidates_superset = (
            {n["id"] for n in full.nodes} >= {n["id"] for n in default.nodes}
        )
        reserved_ok = set(full.shown_node_ids()) >= default_shown
        subset_ok = candidates_superset and reserved_ok and budget_ok and \
            default_shown <= set(full.shown_node_ids())
        report = {
            "candidates_superset": candidates_superset,
            "reserved_equals_default_shown": reserved_ok,
            "budget_ok": budget_ok,
            "subset_ok": subset_ok,
            "default_shown": sorted(default_shown),
            "full_shown": sorted(full.shown_node_ids()),
            "budget_default": dbudget,
            "budget_full": fb,
        }
        if not subset_ok:
            raise GraphError(
                GRAPH_BUDGET_INVALID,
                "subset_ok=false（R-S4-7 构造前提不成立，禁止静默补入）",
                detail=report,
            )
        return default, full, report

    # ── 内部：分区与关系类型 ────────────────────────────────────────
    @staticmethod
    def _relation_types(frame_spec: FrameSpec,
                        relation_sources: Sequence[str] | None) -> tuple[str, ...]:
        """维度 → ``E_relation(D)``。未知维度 fail-closed（S4-7/S1-2）。"""
        if relation_sources is not None:
            types = tuple(dict.fromkeys(str(t) for t in relation_sources))
            if not types:
                raise GraphError(GRAPH_INTERNAL, "relation_sources 不能为空",
                                 detail={"s4_code": "S4_DIMENSION_INVALID"})
            return types
        if frame_spec.dimension_id == "H":
            return _H_RELATION_TYPES
        if frame_spec.dimension_id == "A":
            return _A_RELATION_TYPES
        raise GraphError(
            GRAPH_INTERNAL,
            f"未知/未注册维度 {frame_spec.dimension_id!r}（S4-7 fail-closed）",
            detail={"s4_code": "S4_DIMENSION_INVALID",
                    "rule_id": "admission.undecided"},
        )

    @staticmethod
    def _partition(graph_view) -> tuple[dict[str, dict], dict[str, str]]:
        """返回 ``(视图节点元数据, 数据节点→视图节点 映射)``。

        叶视图：恒等映射；簇视图：成员 KP → 所属簇节点（聚合）。
        """
        meta: dict[str, dict] = {}
        for node in graph_view.nodes or ():
            nid = str(node["id"])
            meta[nid] = dict(node)
        clusters = tuple(getattr(graph_view, "clusters", ()) or ())
        if not clusters:
            return meta, {nid: nid for nid in meta}
        id_map: dict[str, str] = {}
        for cluster in clusters:
            cid = str(cluster["cluster_id"])
            for member in cluster.get("members") or ():
                id_map[str(member)] = cid
        return meta, id_map

    # ── 内部：MANDATORY ────────────────────────────────────────────
    def _mandatory_ids(self, frame_spec: FrameSpec, raw_edges: Sequence[Mapping],
                       id_map: Mapping[str, str], relation_types: Sequence[str]) -> set[str]:
        """S4-5：A = {focus}；H = {focus} ∪ first K children(focus)。"""
        focus = frame_spec.focus
        mandatory: set[str] = {focus}
        if frame_spec.dimension_id != "H":
            return mandatory
        children = sorted({
            id_map.get(str(t))
            for e in raw_edges
            if str(e.get("type")) in relation_types and str(e.get("source_id")) == focus
            for t in (e.get("targets") or [])
            if id_map.get(str(t)) and id_map.get(str(t)) != focus
        })
        mandatory.update(children[: self.mandatory_context_cap])
        return mandatory

    # ── 内部：边分类 ───────────────────────────────────────────────
    def _classify_edges(
        self, *, frame_spec: FrameSpec, raw_edges: Sequence[Mapping],
        id_map: Mapping[str, str], relation_types: Sequence[str],
        source_available: bool, datasource_present: bool,
    ) -> tuple[list[dict], list[str]]:
        """数据边 → 视图边候选（含 suppressed/unknown 的 rule_id 归属）。

        返回 ``(records, notes)``；``records`` 已按"视角端点"聚合（多条数据边 → 一条视图边，
        ``data_edge_ids`` 保留审计信息，Renderer 禁读）。
        """
        notes: list[str] = []
        if not datasource_present:
            # 没有边来源 ⇒ 无法判定（unknown，admission.undecided），不是"无关系"
            return [], ["datasource 缺失：边判定为 unknown/admission.undecided"]
        if not source_available:
            return [], ["source 不可用：边判定为 unknown/source.unavailable"]

        focus = frame_spec.focus
        grouped: dict[str, dict] = {}

        for edge in raw_edges:
            etype = edge.get("type")
            src = edge.get("source_id")
            targets = edge.get("targets")
            malformed = (
                not isinstance(etype, str) or not etype
                or not isinstance(src, str) or not src
                or not isinstance(targets, (list, tuple)) or not targets
            )
            if malformed:
                key = f"invalid|{etype}|{src}|{targets}"
                grouped.setdefault(key, {
                    "id": key, "type": str(etype or ""),
                    "presence": PRESENCE_UNKNOWN, "rule_id": "invalid.data",
                    "relation_class": "structural", "label_rank": 0,
                    "hop": 99, "incident": False, "data_edge_ids": [],
                    "src_view": None, "tgt_view": None,
                })
                continue

            for tgt in targets:
                tgt = str(tgt)
                src_v = id_map.get(src)
                tgt_v = id_map.get(tgt)
                if src_v is None or tgt_v is None:
                    key = f"unresolved|{etype}|{src}|{tgt}"
                    grouped.setdefault(key, {
                        "id": key, "type": etype,
                        "presence": PRESENCE_UNKNOWN, "rule_id": "endpoint.unresolved",
                        "relation_class": "structural", "label_rank": 0,
                        "hop": 99, "incident": False, "data_edge_ids": [],
                        "src_view": src_v, "tgt_view": tgt_v,
                    })
                    continue

                # 视图级边 id（聚合后）：type|视图源|视图目标
                vid = f"{etype}|{src_v}|{tgt_v}"
                record = grouped.get(vid)
                if record is None:
                    record = {
                        "id": vid, "type": etype,
                        "src_view": src_v, "tgt_view": tgt_v,
                        "data_edge_ids": [],
                        "presence": None, "rule_id": None,
                        "relation_class": self._relation_class(edge),
                        "label_rank": 0,
                        "hop": 99, "incident": False,
                        "cross_layer": bool(edge.get("cross_layer")),
                        "aggregate_count": 0,
                    }
                    grouped[vid] = record
                record["data_edge_ids"].append(f"{etype}|{src}|{tgt}")
                record["aggregate_count"] = len(record["data_edge_ids"])

                # ── 逐条判定（优先级即 S4 语义顺序）────────────────
                if etype not in relation_types:
                    record["presence"] = PRESENCE_SUPPRESSED
                    record["rule_id"] = record["rule_id"] or "dimension.sources"
                    continue
                if frame_spec.dimension_id == "H" and src_v != focus:
                    record["presence"] = PRESENCE_SUPPRESSED
                    record["rule_id"] = record["rule_id"] or "dimension.direction"
                    continue
                if record["cross_layer"]:
                    record["presence"] = PRESENCE_SUPPRESSED
                    record["rule_id"] = record["rule_id"] or "dimension.level.cross_layer"
                    continue
                if src_v == tgt_v:
                    # 簇内折起（聚合节点自环）⇒ 不画但可见（cluster.folded）
                    record["presence"] = PRESENCE_SUPPRESSED
                    record["rule_id"] = record["rule_id"] or "cluster.folded"
                    continue
                incident = focus in (src_v, tgt_v)
                record["incident"] = record["incident"] or incident
                record["hop"] = 1 if incident else 2
                if record["presence"] is None or record["presence"] == PRESENCE_SHOWN:
                    # 一跳候选；2 跳一律 suppressed（S4-4 禁隐式第二跳）
                    record["presence"] = PRESENCE_SHOWN if incident else PRESENCE_SUPPRESSED
                    record["rule_id"] = None if incident else "hop.budget"

        # 仍然 presence 未定的（只有 theory 上不会发生）⇒ fail-closed 到 unknown
        for record in grouped.values():
            if record["presence"] is None:
                record["presence"] = PRESENCE_UNKNOWN
                record["rule_id"] = "admission.undecided"
                notes.append(f"边 {record['id']} 判定未定 ⇒ unknown/admission.undecided")
        return list(grouped.values()), notes

    @staticmethod
    def _relation_class(edge: Mapping) -> str:
        """S4-2 的 ``relation_class``：由 S0-1 语义标签推导（semantic 最优先）。"""
        if str(edge.get("contain_kind") or "") == "semantic" or \
                str(edge.get("label") or "") == "semantic":
            return "semantic"
        etype = str(edge.get("type") or "")
        if etype == "reference":
            return "reference"
        if str(edge.get("origin") or "") == "range":
            return "structural"
        return "navigation" if etype == "contain" else "structural"

    # ── 内部：一跳节点 ────────────────────────────────────────────
    @staticmethod
    def _one_hop_nodes(frame_spec: FrameSpec, edge_records: Sequence[dict]) -> set[str]:
        """``one_hop(F) = {v | ∃e ∈ E_relation(D) 连接 F 与 v, v∉F}``（S4-3）。"""
        focus = frame_spec.focus
        out: set[str] = set()
        for rec in edge_records:
            if rec["presence"] not in (PRESENCE_SHOWN, PRESENCE_SUPPRESSED):
                continue
            if rec["rule_id"] in {"dimension.sources", "dimension.direction",
                                  "dimension.level.cross_layer", "cluster.folded"}:
                continue
            if focus in (rec["src_view"], rec["tgt_view"]):
                other = rec["tgt_view"] if rec["src_view"] == focus else rec["src_view"]
                if other and other != focus:
                    out.add(str(other))
        return out

    # ── 内部：排序与预算 ──────────────────────────────────────────
    @staticmethod
    def _order_nodes(*, nodes_meta: Mapping[str, dict], mandatory: set[str],
                     one_hop: set[str], focus: str) -> list[dict]:
        """S4-2 排序键：``(tier, hop, relation_class, label_rank, canonical_id)``。"""
        out: list[dict] = []
        for nid, meta in nodes_meta.items():
            is_mandatory = nid in mandatory
            hop = 0 if is_mandatory else (1 if nid in one_hop else 2)
            out.append({
                "id": nid,
                "kind": str(meta.get("kind") or "kp"),
                "mandatory": is_mandatory,
                "hop": hop,
                "focus": nid == focus,
                "tier": 0 if is_mandatory else (1 if nid in one_hop else 2),
            })
        out.sort(key=lambda n: (n["tier"], n["hop"], n["id"]))
        return out

    @staticmethod
    def _select(ordered: Sequence[dict], *, budget: int,
                reserved: Iterable[str] | None,
                hop_budget: int = 1) -> tuple[set[str], dict[str, int]]:
        """按序填预算；reserved（full 模式下 = shown(default)）先全保留（R-S4-7 ②）。

        **S4-4 硬约束**：``hop > hop_budget`` 的节点**一律不可 shown**（禁隐式第二跳），
        与预算无关 —— 否则 closure_violations > 0。这是 P0 不变量。
        """
        keep: set[str] = set()
        counts: dict[str, int] = {}
        reserved_set = set(reserved or ())
        for node in ordered:
            nid = node["id"]
            if nid in reserved_set:
                keep.add(nid)
                continue
            if int(node.get("hop") or 0) > hop_budget:
                counts["hop.budget"] = counts.get("hop.budget", 0) + 1
                continue
            if len(keep) < budget:
                keep.add(nid)
            else:
                counts["node.budget"] = counts.get("node.budget", 0) + 1
        return keep, counts

    @staticmethod
    def _select_edge_records(records: Sequence[dict], *, budget: int,
                             reserved: Iterable[str] | None) -> tuple[set[str], dict[str, int]]:
        keep: set[str] = set()
        counts: dict[str, int] = {}
        reserved_set = set(reserved or ())
        for rec in records:
            if rec["presence"] != PRESENCE_SHOWN:
                continue
            if rec["id"] in reserved_set:
                keep.add(rec["id"])
                continue
            if len(keep) < budget:
                keep.add(rec["id"])
            else:
                rec["presence"] = PRESENCE_SUPPRESSED
                rec["rule_id"] = "edge.budget"
                counts["edge.budget"] = counts.get("edge.budget", 0) + 1
        return keep, counts

    # ── 内部：组装 ────────────────────────────────────────────────
    @staticmethod
    def _assemble_nodes(*, ordered_nodes: Sequence[dict], shown: set[str],
                        mandatory: set[str], focus: str,
                        source_available: bool, datasource_present: bool,
                        hop_budget: int = 1) -> list[dict]:
        out: list[dict] = []
        for node in ordered_nodes:
            nid = node["id"]
            rec = {
                "id": nid,
                "kind": node["kind"],
                "hop": node["hop"],
                "mandatory": nid in mandatory,
                "focus": nid == focus,
                "presence": None,
                "rule_id": None,
            }
            if nid in shown:
                rec["presence"] = PRESENCE_SHOWN
            elif not datasource_present:
                rec["presence"] = PRESENCE_UNKNOWN
                rec["rule_id"] = "admission.undecided"
            elif not source_available:
                rec["presence"] = PRESENCE_UNKNOWN
                rec["rule_id"] = "source.unavailable"
            elif int(node["hop"]) > hop_budget:
                # 超出跳预算 ⇒ 与预算无关地抑制（S4-4：禁隐式第二跳）
                rec["presence"] = PRESENCE_SUPPRESSED
                rec["rule_id"] = "hop.budget"
            elif nid in mandatory:
                # MANDATORY 一定 shown（预算已先校验）；此处防御性分支
                rec["presence"] = PRESENCE_SUPPRESSED
                rec["rule_id"] = "node.budget"
            elif node["hop"] <= 1:
                rec["presence"] = PRESENCE_SUPPRESSED
                rec["rule_id"] = "node.budget"
            else:
                rec["presence"] = PRESENCE_SUPPRESSED
                rec["rule_id"] = "hop.budget"
            out.append(rec)
        out.sort(key=lambda n: (0 if n["presence"] == PRESENCE_SHOWN else 1, n["id"]))
        return out

    @staticmethod
    def _assemble_edges(*, edge_candidates: Sequence[dict], shown: set[str]) -> list[dict]:
        out: list[dict] = []
        for rec in edge_candidates:
            presence = rec["presence"]
            rule_id = rec["rule_id"]
            if rec["id"] in shown and presence == PRESENCE_SHOWN:
                presence, rule_id = PRESENCE_SHOWN, None
            elif presence == PRESENCE_SHOWN:
                # 没进 shown 但仍是 shown ⇒ 预算收口
                presence, rule_id = PRESENCE_SUPPRESSED, "edge.budget"
            out.append({
                "id": rec["id"],
                "type": rec["type"],
                "src_view": rec["src_view"],
                "tgt_view": rec["tgt_view"],
                "relation_class": rec["relation_class"],
                "hop": rec["hop"],
                "aggregate_count": rec.get("aggregate_count", 0),
                "data_edge_ids": list(rec.get("data_edge_ids") or ()),
                "presence": presence,
                "rule_id": rule_id,
            })
        out.sort(key=lambda e: (0 if e["presence"] == PRESENCE_SHOWN else 1, e["id"]))
        return out

    # ── 内部：自洽性机检（closure / behind）───────────────────────
    @staticmethod
    def _self_check(result: AdmissionResult) -> dict[str, list[str]]:
        budget = result.frame_spec.hop
        closure: list[str] = []
        behind: list[str] = []
        shown_nodes = {n["id"]: n for n in result.nodes if n["presence"] == PRESENCE_SHOWN}
        shown_edges = [e for e in result.edges if e["presence"] == PRESENCE_SHOWN]
        focus = result.frame_spec.focus

        # closure：shown 的 hop 不得超过 hop_budget（S4-4）
        for item in (*result.nodes, *result.edges):
            if item["presence"] != PRESENCE_SHOWN:
                continue
            if int(item.get("hop") or 0) > budget:
                closure.append(f"shown 超过 hop_budget：{item['id']} hop={item.get('hop')}")

        # behind：shown 里不得出现"一跳端点的邻居"（= 2 跳，U-17）
        one_hop = {
            (e["tgt_view"] if e["src_view"] == focus else e["src_view"])
            for e in shown_edges
            if focus in (e["src_view"], e["tgt_view"])
        } - {focus}
        two_hop: set[str] = set()
        for e in shown_edges:
            for a, b in ((e["src_view"], e["tgt_view"]), (e["tgt_view"], e["src_view"])):
                if a in one_hop and b not in one_hop and b != focus:
                    two_hop.add(str(b))
        for nid in shown_nodes:
            if nid in two_hop and nid not in one_hop:
                behind.append(f"shown 带入了 2 跳邻居：{nid}（U-17 禁止背后图）")
        return {"closure": closure, "behind": behind}


def assert_single_presence_source(module_globals: Mapping | None = None) -> list[str]:
    """S4-1 机检辅助：presence 只应由本模块产生。

    返回问题列表（当前实现只能静态检查本包内是否另有模块定义 presence 常量）。
    """
    problems: list[str] = []
    consts = module_globals or {}
    for name, value in consts.items():
        if name.startswith("PRESENCE_") and name not in (
            "PRESENCE_SHOWN", "PRESENCE_SUPPRESSED", "PRESENCE_UNKNOWN", "PRESENCE_VALUES",
        ):
            problems.append(f"疑似重复定义 presence 常量：{name}={value!r}")
    return problems
