"""I-02 `GraphViewBuilder`：``DataSource`` + ``(level, view_family)`` → ``GraphView``。

## 冻结依据

- **S6-2**：GraphView 按 ``(level, view_family)`` **partition**；``data_state ∈ {ok,
  empty_nosemantic}``；节点 ``kind ∈ {kp, cluster}``；**只读事实、不缓存事实、不写 sidecar**。
- **R-2（S0-3 冻结）**：``view_family = ⟨family_id, basis, dimension_id, level_chain⟩``；
  partition 断言的对象是 ``(level, view_family)``，**不是** ``(level, dimension)``。
- **S0-2 V1–V6**（``validate_level_view``，fail-closed）：
  - V1 每个**非叶**节点 ``kind=cluster``
  - V2 每个**叶**节点 ``kind=kp`` 且 ``id ∈ K``（collector KP 集）
  - V3 cluster 成员**非空**
  - V4 **无** ``cluster`` 叶节点
  - V5 同一 ``(level, view_family)`` 内成员集合**互不相交**且**并集 = 该层全集**
  - V6 ``expand_cluster_to_kp`` 递归展开到底**全为 KP**

## 为什么 B2 的"叶视图"不造假簇

S2-1 / S2-12 冻结：**不得拿结构/引用边伪造语义簇**。因此在没有 cluster run 时，
本 builder **不构造任何 cluster**，只输出"该层 = 全部 KP 各自成格"的**叶视图** ——
这天然满足 V1–V6（V1/V3/V4 空真，V5 每格单点仍互斥且并集完整），
且**不涉及任何语义判定**。簇节点只能来自 I-04 产出的 run（B2 由调用方传入）。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from memoria.graph.multilevel.errors import GRAPH_INTERNAL, GraphError

#: ``data_state`` 枚举（S6-2）。
DATA_STATES: tuple[str, ...] = ("ok", "empty_nosemantic")

#: ``view_family`` 冻结字段（R-2）。
VIEW_FAMILY_FIELDS: tuple[str, ...] = ("family_id", "basis", "dimension_id", "level_chain")

NODE_KINDS: tuple[str, ...] = ("kp", "cluster")


def canonical_bytes(payload: object) -> bytes:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def sha256_canonical(payload: object) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


# ── view_family（R-2）──────────────────────────────────────────────────


@dataclass(frozen=True)
class ViewFamily:
    """``⟨family_id, basis, dimension_id, level_chain⟩``（R-2 冻结四元组）。"""

    family_id: str
    basis: str
    dimension_id: str
    level_chain: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.family_id or not isinstance(self.family_id, str):
            raise GraphError(GRAPH_INTERNAL, "view_family.family_id 必须非空",
                             detail={"s0_code": "V0_VIEW_FAMILY_INVALID"})
        if not self.basis or not isinstance(self.basis, str):
            raise GraphError(GRAPH_INTERNAL, "view_family.basis 必须非空",
                             detail={"s0_code": "V0_VIEW_FAMILY_INVALID"})
        if not self.dimension_id or not isinstance(self.dimension_id, str):
            raise GraphError(GRAPH_INTERNAL, "view_family.dimension_id 必须非空",
                             detail={"s0_code": "V0_VIEW_FAMILY_INVALID"})
        if not self.level_chain:
            raise GraphError(GRAPH_INTERNAL, "view_family.level_chain 不能为空",
                             detail={"s0_code": "V0_VIEW_FAMILY_INVALID"})

    def to_dict(self) -> dict:
        return {
            "family_id": self.family_id,
            "basis": self.basis,
            "dimension_id": self.dimension_id,
            "level_chain": list(self.level_chain),
        }

    @property
    def leaf_level(self) -> str:
        return self.level_chain[-1]


# ── GraphView ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GraphView:
    """某一 ``(level, view_family)`` 的只读视图（**派生，不是事实**）。"""

    level: str
    view_family: ViewFamily
    data_state: str
    nodes: tuple[dict, ...]
    clusters: tuple[dict, ...] = ()   # 仅 cluster 节点：{cluster_id, members, size, representative}

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "view_family": self.view_family.to_dict(),
            "data_state": self.data_state,
            "nodes": [dict(n) for n in self.nodes],
            "clusters": [dict(c) for c in self.clusters],
        }

    def canonical_sha(self) -> str:
        return sha256_canonical(self.to_dict())

    def cluster_members(self) -> dict[str, tuple[str, ...]]:
        return {str(c["cluster_id"]): tuple(c["members"]) for c in self.clusters}

    def node_ids(self) -> tuple[str, ...]:
        return tuple(str(n["id"]) for n in self.nodes)


# ── 构建 ────────────────────────────────────────────────────────────────


class GraphViewBuilder:
    """按 ``(level, view_family)`` 构建视图。**纯函数式：不写任何文件。**"""

    def build(
        self,
        datasource,
        *,
        level: str,
        view_family: ViewFamily,
        cluster_run=None,
        has_semantic: bool | None = None,
    ) -> GraphView:
        if not isinstance(view_family, ViewFamily):
            raise GraphError(GRAPH_INTERNAL, "view_family 必须是 ViewFamily 实例",
                             detail={"s0_code": "V0_VIEW_FAMILY_INVALID"})
        if not isinstance(level, str) or not level:
            raise GraphError(GRAPH_INTERNAL, "level 必须是非空字符串",
                             detail={"s0_code": "V0_LEVEL_INVALID"})
        if level not in view_family.level_chain:
            raise GraphError(
                GRAPH_INTERNAL,
                f"level {level!r} 不在 view_family.level_chain {list(view_family.level_chain)} 内",
                detail={"s0_code": "V0_LEVEL_INVALID"},
            )

        kp_ids = tuple(sorted(
            str(k.get("id")) for k in (datasource.kps or ()) if k.get("id")
        ))
        if has_semantic is None:
            has_semantic = _infer_has_semantic(datasource)
        data_state = "ok" if has_semantic else "empty_nosemantic"

        is_leaf_level = level == view_family.leaf_level
        if cluster_run is not None:
            view = self._build_cluster_level(
                level=level, view_family=view_family, data_state=data_state,
                cluster_run=cluster_run,
            )
        elif is_leaf_level:
            view = self._build_leaf_level(
                level=level, view_family=view_family, data_state=data_state, kp_ids=kp_ids
            )
        else:
            # 非叶层但没有 cluster run ⇒ 只能输出空分区（并集=全集会不成立）
            # ⇒ 明确 fail-closed，不伪造 cluster（S2-12）
            raise GraphError(
                GRAPH_INTERNAL,
                f"level {level!r} 是非叶层但未提供 cluster_run（不得用结构边伪造簇）",
                detail={"s0_code": "V3_CLUSTER_REQUIRED", "level": level,
                        "leaf_level": view_family.leaf_level},
            )

        problems = validate_level_view(view, kp_ids=kp_ids)
        if problems:
            raise GraphError(
                GRAPH_INTERNAL,
                f"level view 校验失败（V1–V6 fail-closed）：{problems[0]}",
                detail={"v_problems": problems[:10], "level": level},
            )
        return view

    # -- 叶视图（全部 KP 各自成格，无 cluster）------------------------
    @staticmethod
    def _build_leaf_level(*, level: str, view_family: ViewFamily,
                         data_state: str, kp_ids: Sequence[str]) -> GraphView:
        nodes = tuple({"id": kp, "kind": "kp"} for kp in kp_ids)
        return GraphView(level=level, view_family=view_family, data_state=data_state,
                         nodes=nodes, clusters=())

    # -- 簇层视图（簇节点来自 I-04 run）-------------------------------
    @staticmethod
    def _build_cluster_level(*, level: str, view_family: ViewFamily,
                            data_state: str, cluster_run) -> GraphView:
        clusters = tuple(
            {
                "cluster_id": str(c["cluster_id"]),
                "members": tuple(sorted(str(m) for m in c.get("members") or ())),
                "size": len(c.get("members") or ()),
                "representative": bool(c.get("representative", False)),
            }
            for c in (cluster_run.clusters or ())
        )
        nodes = tuple({"id": c["cluster_id"], "kind": "cluster"} for c in clusters)
        return GraphView(level=level, view_family=view_family, data_state=data_state,
                         nodes=nodes, clusters=clusters)


def _infer_has_semantic(datasource) -> bool:
    """从 DataSource 推断是否存在语义边（B1 边无 ``contain_kind`` ⇒ 恒 False ⇒ 无簇状态）。

    这里**不猜**：委托 I-04 的 ``G_sem`` 判定（单一真源），对 B1 形状的边如实返回 False。
    """
    from memoria.graph.multilevel.cluster_run import select_semantic_edges

    return bool(select_semantic_edges(datasource.edges or ()))


# ── V1–V6 校验（S0-2）──────────────────────────────────────────────────


def validate_level_view(view: GraphView, *, kp_ids: Iterable[str]) -> list[str]:
    """S0-2 ``validate_level_view`` 的 V1–V6，返回问题列表（空 = 通过）。"""
    problems: list[str] = []
    kset = set(str(k) for k in kp_ids)
    nodes = list(view.nodes)
    members_map = view.cluster_members()

    # V1 每个非叶节点 kind=cluster ；V4 无 cluster 叶节点（叶与否按"是否在 clusters 里"判定）
    for n in nodes:
        nid = str(n.get("id"))
        kind = n.get("kind")
        if kind not in NODE_KINDS:
            problems.append(f"V1 非法 kind={kind!r}（节点 {nid}）")
            continue
        if kind == "cluster" and nid not in members_map:
            problems.append(f"V4 cluster 节点 {nid} 没有成员表（cluster 叶）")

    # V2 每个叶节点 kind=kp 且 id ∈ K
    for n in nodes:
        if n.get("kind") == "kp" and str(n.get("id")) not in kset:
            problems.append(f"V2 叶节点 {n.get('id')!r} 不在 KP 集内")

    # V3 cluster 成员非空；V2' 成员必须是 KP
    for cid, members in members_map.items():
        if not members:
            problems.append(f"V3 cluster {cid} 成员为空（空簇禁止）")
        for m in members:
            if m not in kset:
                problems.append(f"V3 cluster {cid} 的成员 {m!r} 不是 KP")

    # V5 同一 (level, view_family) 内成员互不相交且并集 = 该层全集
    if members_map:
        seen: dict[str, str] = {}
        for cid, members in sorted(members_map.items()):
            for m in members:
                if m in seen and seen[m] != cid:
                    problems.append(f"V5 成员 {m!r} 同时属于 {seen[m]} 与 {cid}（分区不互斥）")
                seen[m] = cid
        union = set(seen)
        missing = sorted(kset - union)
        extra = sorted(union - kset)
        if missing:
            problems.append(f"V5 并集缺 {missing[:5]}（应等于该层全集）")
        if extra:
            problems.append(f"V5 并集多出 {extra[:5]}")

    # V6 展开到底全为 KP
    expanded = expand_cluster_to_kp(view)
    non_kp = [x for x in expanded if x not in kset]
    if non_kp:
        problems.append(f"V6 展开后出现非 KP：{non_kp[:5]}")
    return problems


def expand_cluster_to_kp(view: GraphView) -> set[str]:
    """递归展开：本实现簇的成员已是 KP（单层），返回全部成员并校验（V6）。"""
    out: set[str] = set()
    for cid, members in view.cluster_members().items():
        out |= set(members)
    return out


def assert_partition_scope(views: Sequence[GraphView]) -> list[str]:
    """R-2：partition 断言的对象是 ``(level, view_family)``，跨族/跨层允许重叠。"""
    problems: list[str] = []
    seen: dict[tuple[str, str], set[str]] = {}
    for v in views:
        key = (v.level, v.view_family.family_id)
        members = expand_cluster_to_kp(v) if v.clusters else set(v.node_ids())
        prev = seen.get(key)
        if prev is not None and prev != members:
            problems.append(
                f"同一 (level, view_family)={key} 出现两个不同分区（应唯一）"
            )
        seen[key] = members
    return problems
