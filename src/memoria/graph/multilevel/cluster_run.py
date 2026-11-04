"""I-04 `ClusterRunBuilder`：语义簇 run 的确定性构建（S2 冻结契约）。

## 冻结依据

- **簇只由 semantic 边构成**（S2-1/S2-2/S2-3，R-S2-1）：μ/β 的输入边集 **必须** == ``E_sem``；
  ``reference`` / ``contain(structural)`` / 非 semantic ``extend`` 权重为 0，**绝不参与** μ/β。
- **run 身份六元组**（S2-7）：``run_id = sha256(canonical(corpus_manifest_sha, view_family_id,
  level_id, algorithm_id, algorithm_version, params_hash))``。
  ⚠️ 注意 S6-4 的公式含 ``dimension_id``，与 S2-10「A 维度不改变簇」**冲突**；
  S6-4 自称「（S2 六元组）」⇒ 以 S2 为准（``dimension_id`` 不进 run_id）。
- **params_hash 规范字段集**（R-S2-10）固定 11 项，任一变化 ⇒ 新 run。
- **五状态**（R-S2-13）：``ok / no_semantic_edges / partial_disconnected / size_exceeded /
  algorithm_failed`` —— 不得用 "degraded" 含糊覆盖。
- **多归属**（S2-6）：同一 ``(level, view_family)`` 内单归属，跨族/层/维多归属；``role="member"``。
- **candidate 不自动 adopted**（S2-13）：agent 只能建 candidate run。

## 一个必须说清的契约缺口（B1 → B2）

``E_sem`` 的判定需要 ``contain_kind``（S0-1 ``G_sem``），而 **B1 的 ``DataSource`` 边未携带该字段**
（``contracts/schemas/edge.json`` 无 ``contain_kind``）。因此本模块：
- 提供 :func:`is_semantic_edge` 严格实现 S0-1 ``G_sem``（容忍字段存在时按规则判定）；
- ``build()`` 接受**显式** ``semantic_edges``（测试/未来 B3+ 由上层注入真实 E_sem）；
- 不显式传时从 ``DataSource.edges`` 派生 ⇒ 现有语料得到空集 ⇒ 状态 ``no_semantic_edges``
  —— 这**正是** S2-12 冻结的真实状态（本仓库 frozen 语料 ``E_sem=0``），不是降级。
- **补 ``contain_kind`` 属契约变更**（S6a/ADDENDUM），已在交付报告中上报，不在此自造字段。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from itertools import combinations
from typing import Iterable, Mapping, Sequence

from memoria.graph.multilevel.errors import GRAPH_INTERNAL, GraphError

#: 五状态（R-S2-13 冻结；顺序即优先级判定顺序，见 :func:`_decide_status`）。
RUN_STATUSES: tuple[str, ...] = (
    "ok",
    "no_semantic_edges",
    "partial_disconnected",
    "size_exceeded",
    "algorithm_failed",
)

#: params_hash 规范字段集（R-S2-10 冻结；**缺字段 fail-closed**）。
PARAM_FIELDS: tuple[str, ...] = (
    "algorithm_id",
    "algorithm_version",
    "weight_policy",
    "linkage",
    "tie_break",
    "cut_policy",
    "target_k",
    "min_cluster_size",
    "n_max",
    "tau_coh",
    "tau_bridge",
)

#: 冻结默认参数（τ 出处：R-S2-11 合成语义夹具 probe；真实语料 E_sem=0 故为合成标定）。
DEFAULT_PARAMS: dict = {
    "algorithm_id": "hac-average",
    "algorithm_version": "v1",
    "weight_policy": "semantic_uniform",   # 同对多边只计 1.0（S2-2）
    "linkage": "average",                  # 纯自实现 average-linkage（S2-4）
    "tie_break": "min_canonical_id",       # 合并后成员集合 canonical 序列字典序最小（S2-4）
    "cut_policy": "target_k",
    "target_k": None,                      # None ⇒ 按 max_sim>0 自然停止
    "min_cluster_size": 2,
    "n_max": 200,
    "tau_coh": 0.5,                        # R-S2-11
    "tau_bridge": 0.25,                    # R-S2-11
}

_CUT_POLICIES = ("target_k", "min_cluster_size")
_MEMBERSHIP_ROLES = ("member",)
_ADOPTION_STATUSES = ("candidate", "adopted")

#: 后验不达标时允许调整 k 的最大步数（S2-4「按 cut_policy 调整 k 重切」的实现常量）。
#: 归 ``algorithm_version`` 语义，**不进 params_hash**（R-S2-10 字段集冻结）。
_MAX_K_ADJUST = 2


# ── 规范字节 ─────────────────────────────────────────────────────────────


def canonical_bytes(payload: object) -> bytes:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def sha256_canonical(payload: object) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


# ── E_sem 判定（S0-1 G_sem）─────────────────────────────────────────────


def is_semantic_edge(edge: Mapping) -> bool:
    """S0-1 ``G_sem``：只有断言性、带证据/策展身份的边才是语义边。

    - ``reference`` **永不是**语义（S0-1 明文）；
    - ``contain`` 仅当 ``contain_kind="semantic"`` 且带 ``assertion_source`` +
      ``curated_by`` + ``curated_at``；
    - ``extend`` 按作者断言/证据判定（要求 ``assertion_source``）；
    - 其它类型（含未知）一律**不是**语义（fail-closed 到结构侧）。

    ⚠️ B1 的 ``DataSource.edges`` 不含这些字段 ⇒ 本函数对其返回 False（⇒ 无簇状态），
    这是契约缺口的如实体现，**不是**把结构边当语义的退路。
    """
    if not isinstance(edge, Mapping):
        return False
    etype = str(edge.get("type") or "")
    if etype == "reference":
        return False
    if etype == "contain":
        if str(edge.get("contain_kind") or "") != "semantic":
            return False
        return bool(
            edge.get("assertion_source")
            and edge.get("curated_by")
            and edge.get("curated_at")
        )
    if etype == "extend":
        return bool(edge.get("assertion_source"))
    return False


def select_semantic_edges(edges: Iterable[Mapping]) -> tuple[dict, ...]:
    """从边集合里筛出 ``E_sem``（保序、确定性）。"""
    return tuple(dict(e) for e in edges if is_semantic_edge(e))


# ── 参数校验 / params_hash ──────────────────────────────────────────────


def validate_params(params: Mapping) -> dict:
    """校验并补全参数；缺字段/多余字段/非法值一律 fail-closed。"""
    if not isinstance(params, Mapping):
        raise GraphError(GRAPH_INTERNAL, "params 必须是映射",
                         detail={"s2_code": "S2_PARAMS_INVALID"})
    missing = [f for f in PARAM_FIELDS if f not in params]
    extra = [k for k in params if k not in PARAM_FIELDS]
    if missing or extra:
        raise GraphError(
            GRAPH_INTERNAL,
            "params 字段集不符 R-S2-10（缺/多均 fail-closed）",
            detail={"s2_code": "S2_PARAMS_INVALID", "missing": missing, "extra": extra},
        )
    p = dict(params)
    if p["weight_policy"] != "semantic_uniform":
        raise GraphError(GRAPH_INTERNAL, "v1 只支持 weight_policy=semantic_uniform",
                         detail={"s2_code": "S2_PARAMS_INVALID"})
    if p["linkage"] != "average":
        raise GraphError(GRAPH_INTERNAL, "v1 只支持 linkage=average",
                         detail={"s2_code": "S2_PARAMS_INVALID"})
    if p["tie_break"] != "min_canonical_id":
        raise GraphError(GRAPH_INTERNAL, "v1 只支持 tie_break=min_canonical_id",
                         detail={"s2_code": "S2_PARAMS_INVALID"})
    if p["cut_policy"] not in _CUT_POLICIES:
        raise GraphError(GRAPH_INTERNAL, f"cut_policy 非法：{p['cut_policy']!r}",
                         detail={"s2_code": "S2_PARAMS_INVALID"})
    if not isinstance(p["algorithm_id"], str) or not p["algorithm_id"]:
        raise GraphError(GRAPH_INTERNAL, "algorithm_id 非法",
                         detail={"s2_code": "S2_PARAMS_INVALID"})
    if not isinstance(p["algorithm_version"], str) or not p["algorithm_version"]:
        raise GraphError(GRAPH_INTERNAL, "algorithm_version 非法",
                         detail={"s2_code": "S2_PARAMS_INVALID"})
    tk = p["target_k"]
    if tk is not None and (not isinstance(tk, int) or isinstance(tk, bool) or tk < 1):
        raise GraphError(GRAPH_INTERNAL, "target_k 必须是 ≥1 整数或 null",
                         detail={"s2_code": "S2_PARAMS_INVALID"})
    mcs = p["min_cluster_size"]
    if not isinstance(mcs, int) or isinstance(mcs, bool) or mcs < 1:
        raise GraphError(GRAPH_INTERNAL, "min_cluster_size 必须是 ≥1 整数",
                         detail={"s2_code": "S2_PARAMS_INVALID"})
    nmax = p["n_max"]
    if not isinstance(nmax, int) or isinstance(nmax, bool) or nmax < 1:
        raise GraphError(GRAPH_INTERNAL, "n_max 必须是 ≥1 整数",
                         detail={"s2_code": "S2_PARAMS_INVALID"})
    for key in ("tau_coh", "tau_bridge"):
        val = p[key]
        if not isinstance(val, (int, float)) or isinstance(val, bool) or not (0.0 <= val <= 1.0):
            raise GraphError(GRAPH_INTERNAL, f"{key} 必须在 [0,1]",
                             detail={"s2_code": "S2_PARAMS_INVALID"})
    return p


def params_hash(params: Mapping) -> str:
    """``params_hash = sha256(canonical(params))``；先校验字段集（fail-closed）。"""
    return sha256_canonical(validate_params(params))


def build_run_id(
    *,
    corpus_manifest_sha: str,
    view_family_id: str,
    level_id: str,
    algorithm_id: str,
    algorithm_version: str,
    params_hash_value: str,
) -> str:
    """S2-7 六元组 run_id（**不含 dimension_id**，见模块 docstring 的冲突说明）。"""
    for name, val in (
        ("corpus_manifest_sha", corpus_manifest_sha),
        ("view_family_id", view_family_id),
        ("level_id", level_id),
        ("algorithm_id", algorithm_id),
        ("algorithm_version", algorithm_version),
        ("params_hash", params_hash_value),
    ):
        if not isinstance(val, str) or not val:
            raise GraphError(GRAPH_INTERNAL, f"run_id 六元组字段非法：{name}",
                             detail={"s2_code": "S2_RUN_ID_INVALID"})
    return sha256_canonical({
        "algorithm_id": algorithm_id,
        "algorithm_version": algorithm_version,
        "corpus_manifest_sha": corpus_manifest_sha,
        "level_id": level_id,
        "params_hash": params_hash_value,
        "view_family_id": view_family_id,
    })


# ── μ / β（S2-2 / S2-3 semantic-only）───────────────────────────────────


def _pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def semantic_pairs(edges: Iterable[Mapping]) -> frozenset[tuple[str, str]]:
    """``E_sem`` 的去重无序端点对（同对多边只计一次 ⇒ 权重恒 1.0）。"""
    pairs: set[tuple[str, str]] = set()
    for e in edges:
        if not is_semantic_edge(e):
            continue
        src = str(e.get("source_id") or "")
        for tgt in e.get("targets") or []:
            tgt = str(tgt)
            if src and tgt and src != tgt:
                pairs.add(_pair(src, tgt))
    return frozenset(pairs)


def cohesion_mu(members: Sequence[str], pairs: frozenset[tuple[str, str]]) -> float | None:
    """``μ(C) = P_in / (|C|(|C|-1)/2)``；``|C|<2`` ⇒ ``None``（单点不算内聚）。"""
    n = len(members)
    if n < 2:
        return None
    mset = set(members)
    p_in = sum(1 for a, b in pairs if a in mset and b in mset)
    denom = n * (n - 1) / 2
    return p_in / denom


def bridge_beta(members: Sequence[str], pairs: frozenset[tuple[str, str]]) -> float:
    """``β(C) = P_out / (P_in + P_out)``；分母 0 ⇒ 0.0（无任何语义边）。"""
    mset = set(members)
    p_in = 0
    p_out = 0
    for a, b in pairs:
        ina, inb = a in mset, b in mset
        if ina and inb:
            p_in += 1
        elif ina or inb:
            p_out += 1
    total = p_in + p_out
    return 0.0 if total == 0 else p_out / total


def semantic_purity_violations(
    cluster_members: Mapping[str, Sequence[str]],
    *,
    semantic_edges: Iterable[Mapping],
    all_edges: Iterable[Mapping],
) -> list[str]:
    """S2-2 纯度守卫：簇内部边必须全在 ``E_sem`` 内。

    若某个簇的成员对之间存在**非 semantic** 边（结构/引用），说明有人拿结构边当语义
    ⇒ 报 ``S2_SEMANTIC_PURITY_FAIL``（机器可判，见测试）。
    """
    problems: list[str] = []
    sem = semantic_pairs(semantic_edges)
    non_sem_pairs: set[tuple[str, str]] = set()
    for e in all_edges:
        if is_semantic_edge(e):
            continue
        src = str(e.get("source_id") or "")
        for tgt in e.get("targets") or []:
            tgt = str(tgt)
            if src and tgt and src != tgt:
                non_sem_pairs.add(_pair(src, tgt))
    for cid, members in cluster_members.items():
        mset = set(members)
        for a, b in non_sem_pairs:
            if a in mset and b in mset and (a, b) not in sem and len(mset) > 1:
                problems.append(
                    f"S2_SEMANTIC_PURITY_FAIL: 簇 {cid} 内部存在非语义边 {a}-{b}"
                )
                break
    return problems


# ── 确定性 HAC（S2-4）──────────────────────────────────────────────────


def _average_similarity(a: frozenset[str], b: frozenset[str],
                        pairs: frozenset[tuple[str, str]]) -> float:
    """average linkage：两簇之间语义端点对数 / (|A|·|B|)。"""
    shared = 0
    for x, y in pairs:
        if (x in a and y in b) or (x in b and y in a):
            shared += 1
    return shared / (len(a) * len(b))


@dataclass(frozen=True)
class _Merge:
    left: tuple[str, ...]
    right: tuple[str, ...]
    merged: tuple[str, ...]
    similarity: float


def _hac_merges(nodes: Sequence[str], pairs: frozenset[tuple[str, str]]) -> list[_Merge]:
    """完整 dendrogram（average-linkage + 冻结 tie-break），**纯确定性**。"""
    clusters: list[frozenset[str]] = [frozenset([n]) for n in sorted(nodes)]
    merges: list[_Merge] = []
    while len(clusters) > 1:
        best: tuple[float, tuple[str, ...], int, int, frozenset[str]] | None = None
        for i, j in combinations(range(len(clusters)), 2):
            sim = _average_similarity(clusters[i], clusters[j], pairs)
            if sim <= 0.0:
                continue
            merged = clusters[i] | clusters[j]
            canon = tuple(sorted(merged))
            # 冻结 tie-break：sim 最大 → 合并后成员集合 canonical 序列字典序最小
            cand = (sim, canon, i, j, merged)
            if best is None:
                best = cand
            else:
                if sim > best[0]:
                    best = cand
                elif sim == best[0] and canon < best[1]:
                    best = cand
        if best is None:
            break  # 无正相似 ⇒ 自然停止（语义连通分量）
        _, _, i, j, merged = best
        left = tuple(sorted(clusters[i]))
        right = tuple(sorted(clusters[j]))
        merges.append(_Merge(left=left, right=right, merged=tuple(sorted(merged)),
                             similarity=best[0]))
        for idx in sorted((i, j), reverse=True):
            clusters.pop(idx)
        clusters.append(frozenset(merged))
        clusters.sort(key=lambda c: tuple(sorted(c)))
    return merges


def _cut(merges: Sequence[_Merge], nodes: Sequence[str], k: int) -> list[frozenset[str]]:
    """在前 ``n-k`` 次合并后切分（k = 目标簇数）。"""
    n = len(nodes)
    k = max(1, min(k, n))
    need = n - k
    groups: list[frozenset[str]] = [frozenset([x]) for x in sorted(nodes)]
    for m in merges[:need]:
        groups = [g for g in groups if tuple(sorted(g)) not in (m.left, m.right)]
        groups.append(frozenset(m.merged))
        groups.sort(key=lambda g: tuple(sorted(g)))
    return groups


def _decide_status(
    *,
    n_nodes: int,
    n_pairs: int,
    groups: Sequence[frozenset[str]],
    algorithm_failed: bool,
    n_max: int,
    disconnected_inside: bool,
) -> str:
    """状态判定（顺序文档化，避免"含糊覆盖"）。"""
    if n_pairs == 0:
        return "no_semantic_edges"
    if n_nodes > n_max:
        return "size_exceeded"
    if algorithm_failed:
        return "algorithm_failed"
    if disconnected_inside:
        return "partial_disconnected"
    return "ok"


# ── run 构建 ────────────────────────────────────────────────────────────


@dataclass
class ClusterRun:
    """一次簇划分 run（**派生缓存**，不是事实；S2-11）。"""

    run_id: str
    level_id: str
    view_family_id: str
    algorithm_id: str
    algorithm_version: str
    params_hash: str
    params: dict
    corpus_manifest_sha: str
    status: str
    clusters: list[dict] = field(default_factory=list)
    memberships: list[dict] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)
    adoption_status: str = "candidate"
    adopted_at: str | None = None
    decided_by: str | None = None
    parent_run_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "level_id": self.level_id,
            "view_family_id": self.view_family_id,
            "algorithm_id": self.algorithm_id,
            "algorithm_version": self.algorithm_version,
            "params_hash": self.params_hash,
            "params": dict(self.params),
            "corpus_manifest_sha": self.corpus_manifest_sha,
            "status": self.status,
            "clusters": [dict(c) for c in self.clusters],
            "memberships": [dict(m) for m in self.memberships],
            "diagnostics": dict(self.diagnostics),
            "adoption_status": self.adoption_status,
            "adopted_at": self.adopted_at,
            "decided_by": self.decided_by,
            "parent_run_id": self.parent_run_id,
        }

    def canonical_sha(self) -> str:
        return sha256_canonical(self.to_dict())


def cluster_key(member_ids: Sequence[str], params: Mapping) -> str:
    """S0-4 D-2：``sha256(canonical(sorted(member_ids)) + algorithm_id + version + params_hash)``。"""
    p = validate_params(params)
    return sha256_canonical({
        "algorithm_id": p["algorithm_id"],
        "algorithm_version": p["algorithm_version"],
        "members": sorted(str(m) for m in member_ids),
        "params_hash": params_hash(p),
    })


class ClusterRunBuilder:
    """从 ``DataSource`` + 语义边构建候选 run（**只读事实，不写任何 KB**）。"""

    def __init__(self, *, params: Mapping | None = None) -> None:
        self.params = validate_params(params if params is not None else DEFAULT_PARAMS)

    # -- 主入口 --------------------------------------------------------
    def build(
        self,
        datasource,
        *,
        level_id: str,
        view_family_id: str,
        semantic_edges: Sequence[Mapping] | None = None,
        corpus_manifest_sha: str | None = None,
        parent_run_id: str | None = None,
    ) -> ClusterRun:
        """构建候选 run。**adoption_status 恒为 candidate**（S2-13：不自动 adopted）。"""
        if not level_id or not view_family_id:
            raise GraphError(GRAPH_INTERNAL, "level_id / view_family_id 不能为空",
                             detail={"s2_code": "S2_RUN_ID_INVALID"})

        all_edges = tuple(dict(e) for e in (datasource.edges or ()))
        sem_edges = tuple(dict(e) for e in semantic_edges) if semantic_edges is not None \
            else select_semantic_edges(all_edges)
        # 纯度：显式传入的语义边也必须真的满足 G_sem（不信调用方）
        for e in sem_edges:
            if not is_semantic_edge(e):
                raise GraphError(
                    GRAPH_INTERNAL,
                    "semantic_edges 里含不满足 S0-1 G_sem 的边（禁止结构边冒充语义）",
                    detail={"s2_code": "S2_SEMANTIC_PURITY_FAIL",
                            "edge": {k: e.get(k) for k in ("type", "source_id", "targets")}},
                )

        corpus_sha = corpus_manifest_sha or str(getattr(datasource, "canonical_id", "") or "")
        if not corpus_sha:
            raise GraphError(GRAPH_INTERNAL, "缺少语料身份（corpus_manifest_sha）",
                             detail={"s2_code": "S2_RUN_ID_INVALID"})

        nodes = tuple(sorted(str(k.get("id")) for k in (datasource.kps or ()) if k.get("id")))
        pairs = semantic_pairs(sem_edges)

        merges = _hac_merges(nodes, pairs) if nodes else []
        groups, algorithm_failed = self._cut_with_validation(
            nodes=nodes, merges=merges, pairs=pairs
        )

        # 组内语义连通性（用于 partial_disconnected 判定）
        disconnected_inside = any(
            self._is_disconnected(g, pairs) for g in groups if len(g) > 1
        )
        status = _decide_status(
            n_nodes=len(nodes),
            n_pairs=len(pairs),
            groups=groups,
            algorithm_failed=algorithm_failed,
            n_max=int(self.params["n_max"]),
            disconnected_inside=disconnected_inside,
        )

        # 簇与成员（local_seq 按最小 canonical member id 排序；S2-7）
        ordered = sorted(groups, key=lambda g: min(g) if g else "")
        clusters: list[dict] = []
        memberships: list[dict] = []
        for seq, g in enumerate(ordered):
            cid = f"{self._pending_run_id(level_id, view_family_id, corpus_sha)}:{seq}"
            members = sorted(g)
            mu = cohesion_mu(members, pairs)
            beta = bridge_beta(members, pairs)
            single = len(members) == 1
            clusters.append({
                "cluster_id": cid,
                "local_seq": seq,
                "members": members,
                "size": len(members),
                "mu": mu,
                "beta": beta,
                # 单点块允许，但 representative=false（S2-1/R-S2-6）
                "representative": (not single) and mu is not None
                and mu >= float(self.params["tau_coh"]),
                "root_exempt": False,
                "cluster_key": cluster_key(members, self.params),
            })
            for m in members:
                memberships.append({
                    "cluster_id": cid,
                    "cluster_key": clusters[-1]["cluster_key"],
                    "kp_id": m,
                    "role": "member",   # S2-6/R-S2-7：不复用 bridge
                    "weight": 1.0,
                })

        purity = semantic_purity_violations(
            {c["cluster_id"]: c["members"] for c in clusters},
            semantic_edges=sem_edges,
            all_edges=all_edges,
        ) if status == "ok" else []

        run = ClusterRun(
            run_id="",  # 下方用最终 params 计算后回填
            level_id=level_id,
            view_family_id=view_family_id,
            algorithm_id=str(self.params["algorithm_id"]),
            algorithm_version=str(self.params["algorithm_version"]),
            params_hash=params_hash(self.params),
            params=dict(self.params),
            corpus_manifest_sha=corpus_sha,
            status=status,
            clusters=clusters,
            memberships=memberships,
            diagnostics={
                "n_nodes": len(nodes),
                "n_semantic_pairs": len(pairs),
                "n_clusters": len(clusters),
                "merges": len(merges),
                "algorithm_failed": algorithm_failed,
                "disconnected_inside": disconnected_inside,
                "purity_violations": purity,
                "coverage": (
                    sum(c["size"] for c in clusters) / len(nodes) if nodes else 0.0
                ),
            },
            parent_run_id=parent_run_id,
        )
        run.run_id = build_run_id(
            corpus_manifest_sha=corpus_sha,
            view_family_id=view_family_id,
            level_id=level_id,
            algorithm_id=run.algorithm_id,
            algorithm_version=run.algorithm_version,
            params_hash_value=run.params_hash,
        )
        # 回填 cluster_id 前缀为真实 run_id
        for c in run.clusters:
            c["cluster_id"] = f"{run.run_id}:{c['local_seq']}"
        for m in run.memberships:
            m["cluster_id"] = f"{run.run_id}:" + m["cluster_id"].split(":")[-1]
        return run

    # -- 切分 + 后验质量校验（S2-4：μ/β 只作后验，不作合并门控）------
    def _cut_with_validation(
        self, *, nodes: Sequence[str], merges: Sequence[_Merge],
        pairs: frozenset[tuple[str, str]],
    ) -> tuple[list[frozenset[str]], bool]:
        """切分并用 μ/β 做**后验**校验；不达标则按 S2-4 调整 k 重切，仍不达标 ⇒ failed。

        调整窗口 ``_MAX_K_ADJUST`` 属**算法实现常量**（归 ``algorithm_version``），
        不进 ``params_hash``（R-S2-10 字段集冻结，不得扩展）。
        """
        if not nodes:
            return [], False
        tau_coh = float(self.params["tau_coh"])
        tau_beta = float(self.params["tau_bridge"])
        n = len(nodes)

        def groups_ok(groups: Sequence[frozenset[str]]) -> bool:
            for g in groups:
                if len(g) < 2:
                    continue
                mu = cohesion_mu(sorted(g), pairs)
                beta = bridge_beta(sorted(g), pairs)
                if mu is None or mu < tau_coh or beta > tau_beta:
                    return False
            return True

        requested = self.params["target_k"]
        if self.params["cut_policy"] == "target_k" and requested is not None:
            k_start = int(requested)
            k_end = min(n, k_start + _MAX_K_ADJUST)
        else:
            # 自然停止（无 target_k）或 min_cluster_size：从 k=1 起，靠 merge 数上限自然收敛
            k_start, k_end = 1, n

        last: list[frozenset[str]] = [frozenset(nodes)]
        for k in range(k_start, k_end + 1):
            groups = _cut(merges, nodes, k)
            last = groups
            if groups_ok(groups):
                return groups, False
        return last, True

    @staticmethod
    def _is_disconnected(group: frozenset[str], pairs: frozenset[tuple[str, str]]) -> bool:
        """组内语义子图是否不连通（不连通 ⇒ partial_disconnected）。"""
        if len(group) < 2:
            return False
        members = set(group)
        adj: dict[str, set[str]] = {n: set() for n in members}
        for a, b in pairs:
            if a in members and b in members:
                adj[a].add(b)
                adj[b].add(a)
        start = min(members)
        seen = {start}
        stack = [start]
        while stack:
            cur = stack.pop()
            for nxt in adj[cur]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen != members

    def _pending_run_id(self, level_id: str, view_family_id: str, corpus_sha: str) -> str:
        return build_run_id(
            corpus_manifest_sha=corpus_sha,
            view_family_id=view_family_id,
            level_id=level_id,
            algorithm_id=str(self.params["algorithm_id"]),
            algorithm_version=str(self.params["algorithm_version"]),
            params_hash_value=params_hash(self.params),
        )


# ── 多归属 / 采用状态机 ────────────────────────────────────────────────


def assert_single_membership_within_scope(run: ClusterRun) -> list[str]:
    """S2-6：同一 ``(level, view_family)`` 内**单归属** —— 一个 KP 只能在一个簇里。"""
    seen: dict[str, str] = {}
    problems: list[str] = []
    for m in run.memberships:
        kp = str(m["kp_id"])
        cid = str(m["cluster_id"])
        if kp in seen and seen[kp] != cid:
            problems.append(f"S2_MULTI_MEMBERSHIP_IN_SCOPE: {kp} 同时在 {seen[kp]} 与 {cid}")
        seen[kp] = cid
    return problems


def assert_multi_membership_across_scope(runs: Sequence[ClusterRun]) -> dict:
    """S2-6：跨 ``(level, view_family)`` **允许**多归属（返回统计，不是错误）。"""
    per_kp: dict[str, set[str]] = {}
    for run in runs:
        scope = (run.level_id, run.view_family_id)
        for m in run.memberships:
            per_kp.setdefault(str(m["kp_id"]), set()).add(str(scope))
    multi = {kp: sorted(scopes) for kp, scopes in per_kp.items() if len(scopes) > 1}
    return {"kp_total": len(per_kp), "multi_scope_kps": multi}


def request_candidate_run(builder: ClusterRunBuilder, datasource, *,
                          requester: str, reason: str, base_run_id: str | None,
                          level_id: str, view_family_id: str,
                          semantic_edges: Sequence[Mapping] | None = None) -> ClusterRun:
    """S2-13：agent 只能请求**候选** run（审计字段必填，绝不自动 adopted）。"""
    if not requester or not reason:
        raise GraphError(GRAPH_INTERNAL, "candidate run 必须带 requester 与 reason（审计）",
                         detail={"s2_code": "S2_CANDIDATE_AUDIT_MISSING"})
    run = builder.build(
        datasource,
        level_id=level_id,
        view_family_id=view_family_id,
        semantic_edges=semantic_edges,
        parent_run_id=base_run_id,
    )
    run.adoption_status = "candidate"
    run.adopted_at = None
    run.decided_by = None
    run.diagnostics["requested_by"] = requester
    run.diagnostics["request_reason"] = reason
    run.diagnostics["base_run_id"] = base_run_id
    return run


def adopt_run(run: ClusterRun, *, decision_id: str) -> ClusterRun:
    """显式采用（唯一把 candidate → adopted 的路径；S2-13）。"""
    if not decision_id:
        raise GraphError(GRAPH_INTERNAL, "adopt 必须带 decision_id",
                         detail={"s2_code": "S2_ADOPT_DECISION_MISSING"})
    if run.adoption_status not in _ADOPTION_STATUSES:
        raise GraphError(GRAPH_INTERNAL, f"非法 adoption_status：{run.adoption_status!r}",
                         detail={"s2_code": "S2_ADOPTION_STATUS_INVALID"})
    run.adoption_status = "adopted"
    run.decided_by = decision_id
    return run
