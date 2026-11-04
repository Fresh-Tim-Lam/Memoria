"""I-03 `RegistryService`：维度注册表 / 版本 / 不可变 history（S1 冻结契约）。

## 冻结依据

- **字段表**：``S1-2`` 的 18 个字段（含 ``basis.kind`` 派生校验、``registry_sha`` 计算域）；
  S6-3 明写「字段/枚举按 S1」⇒ **S1-2 为准**（S6-3 只是摘要）。
- **registry_sha**：``sha256(canonical(registry 去掉 registry_sha 字段))``。
- **history**（R-S1-9）：不可变 append-only，``content_sha`` 为 id；每版条目**自包含**
  （``version`` / ``relation_sources`` / ``active_dimensions`` / ``previous_sha`` / ``decision_id``）
  ⇒ 验证器**不需要外部旧 registry** 就能证明跨版本 ``new ⊇ old``。
- **只增不删**（S1-6）：``relation_sources`` 跨版本只增；删除/改名 ⇒ ``S0_REOPEN_REQUIRED``。
- **可选签名**（S6-3/R-S6-4）：``signature?{alg:"ed25519"|"hmac-sha256", key_id, sig}``；
  ``content_sha`` **不含 signature**；无签名 ⇒ ``signed=false``（合法）；
  有签名但验证失败 ⇒ **``GRAPH_HISTORY_SIGNATURE_INVALID``**（冻结 canonical 码）。

## 失败码口径（重要）

S1-2 的 ``DIM_*`` 是 **S1 内部细分码**。S6 §S6-9 只允许 ``GRAPH_*`` 作为 canonical，
且任务明确「新码须 ADDENDUM，**不得自造**」；而 ENGINEERING-PLAN I-03 写的
``GRAPH_REGISTRY_*`` **在 S6/ADD-1/ADD-2 三份冻结文档里并不存在**。
⇒ 本模块：canonical 一律 ``GRAPH_INTERNAL``（唯一兜底），S1 细分码放在
``detail["dim_code"]`` 里保留可诊断性；**不自造** ``GRAPH_REGISTRY_*``。
（已在交付报告中上报：若需要独立码，须走 S6 ADDENDUM。）
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable, Mapping, Sequence

from memoria.graph.multilevel.datasource import E_RELATION_MIN
from memoria.graph.multilevel.errors import (
    GRAPH_HISTORY_SIGNATURE_INVALID,
    GRAPH_INTERNAL,
    GraphError,
)

#: ``kind`` 枚举（S1-2）。
DIM_KINDS: tuple[str, ...] = ("hierarchy_navigation", "relation_expansion")

#: ``basis.kind`` 是派生字段，必须等于 ``map(kind)``（S1-2 唯一规范字段是 kind）。
KIND_BASIS_MAP: dict[str, str] = {
    "hierarchy_navigation": "level_partition",
    "relation_expansion": "relation_neighborhood",
}

#: 三态状态机（S1-11；R-S1-6：deprecated→active 只能重开 S1）。
DIM_STATUSES: tuple[str, ...] = ("reserved", "active", "deprecated")

DIRECTIONS: tuple[str, ...] = ("down", "up", "both", "out", "in")
HOP_UNITS: tuple[str, ...] = ("edge", "n/a")
FALLBACK_POLICIES: tuple[str, ...] = ("allow", "forbidden")

#: S1-2 冻结字段表（**缺字段 fail-closed**）。
DIMENSION_FIELDS: tuple[str, ...] = (
    "id", "name", "kind", "basis", "relation_sources", "direction", "hop_unit",
    "hop_default", "hop_max", "termination", "status", "priority", "version",
    "history_ref",
)

_SIGNATURE_ALGS = ("ed25519", "hmac-sha256")


# ── 规范字节 / sha ──────────────────────────────────────────────────────


def canonical_bytes(payload: object) -> bytes:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def sha256_canonical(payload: object) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


#: 不进哈希计算域的**指针字段**。
#: ``registry_sha`` 自然排除（S1-2 明文）；``history_ref`` 是指向 history 尾条的内容 sha，
#: 若把它算进哈希域会与 ``content_sha == registry_sha`` 形成**互为因果的循环**
#: （history_ref ← content_sha ← sha(body 含 history_ref)）⇒ 两者同为指针字段，均排除。
_SHA_EXCLUDED_FIELDS: tuple[str, ...] = ("registry_sha", "history_ref")


def compute_registry_sha(registry: Mapping) -> str:
    """``sha256(canonical(registry 去掉指针字段))``。

    指针字段 = ``registry_sha``（S1-2 明文排除）+ ``history_ref``（见上，避免循环）。
    """
    body = {k: v for k, v in registry.items() if k not in _SHA_EXCLUDED_FIELDS}
    return sha256_canonical(body)


# ── 维度构造与校验 ──────────────────────────────────────────────────────


def make_dimension(
    *,
    dim_id: str,
    name: str,
    kind: str,
    status: str = "reserved",
    priority: int = 0,
    version: str = "v1",
    relation_sources: Sequence[str] | None = None,
    direction: str | None = None,
    hop_default: int | None = None,
    hop_max: int | None = None,
    max_nodes: int | None = None,
    history_ref: str = "",
) -> dict:
    """按 S1-2 最小规则构造维度条目（默认值取 S1-2 的"默认"列）。"""
    is_h = kind == "hierarchy_navigation"
    if relation_sources is None:
        relation_sources = [] if is_h else list(E_RELATION_MIN)
    if direction is None:
        direction = "down" if is_h else "both"
    if is_h:
        hop_default = None
        hop_max = None
    else:
        hop_default = 1 if hop_default is None else hop_default
        hop_max = 2 if hop_max is None else hop_max
    return {
        "id": dim_id,
        "name": name,
        "kind": kind,
        "basis": {"kind": KIND_BASIS_MAP.get(kind, "")},
        "relation_sources": list(relation_sources),
        "direction": direction,
        "hop_unit": "n/a" if is_h else "edge",
        "hop_default": hop_default,
        "hop_max": hop_max,
        "termination": {
            "max_nodes": max_nodes,
            "leaf_required": is_h,
            "stop_on_no_new": True,
        },
        "status": status,
        "priority": priority,
        "version": version,
        "history_ref": history_ref,
    }


@dataclass(frozen=True)
class DimProblem:
    """一条 S1 细分问题（``dim_code`` 保留 S1-2 的失败码身份）。"""

    dim_code: str
    path: str
    message: str

    def to_dict(self) -> dict:
        return {"dim_code": self.dim_code, "path": self.path, "message": self.message}


def validate_dimension(dim: Mapping) -> list[DimProblem]:
    """按 S1-2 字段表校验单个维度（**fail-closed**，返回全部问题）。"""
    problems: list[DimProblem] = []

    def bad(code: str, path: str, msg: str) -> None:
        problems.append(DimProblem(code, path, msg))

    if not isinstance(dim, Mapping):
        bad("DIM_ID_INVALID", "$", "维度必须是对象")
        return problems

    missing = [f for f in DIMENSION_FIELDS if f not in dim]
    if missing:
        bad("DIM_ID_INVALID", "$", f"缺 S1-2 必填字段：{missing}")
        return problems

    if not isinstance(dim["id"], str) or not dim["id"]:
        bad("DIM_ID_INVALID", "$.id", "id 必须是非空字符串")
    if not isinstance(dim["name"], str) or not dim["name"]:
        bad("DIM_NAME_INVALID", "$.name", "name 必须是非空字符串")
    if not isinstance(dim["version"], str) or not dim["version"]:
        bad("DIM_VERSION_INVALID", "$.version", "version 必须是非空字符串")

    kind = dim["kind"]
    if kind not in DIM_KINDS:
        bad("DIM_KIND_INVALID", "$.kind", f"kind 必须是 {DIM_KINDS} 之一")
    else:
        basis = dim.get("basis")
        expected_basis = KIND_BASIS_MAP[kind]
        actual = basis.get("kind") if isinstance(basis, Mapping) else None
        if actual != expected_basis:
            bad("DIM_KIND_MISMATCH", "$.basis.kind",
                f"basis.kind 必须等于 map(kind)={expected_basis!r}，实际 {actual!r}")

    if dim["status"] not in DIM_STATUSES:
        bad("DIM_STATUS_INVALID", "$.status", f"status 必须是 {DIM_STATUSES} 之一")

    if not isinstance(dim["priority"], int) or isinstance(dim["priority"], bool):
        bad("DIM_PRIORITY_DUPLICATE", "$.priority", "priority 必须是整数")

    srcs = dim["relation_sources"]
    if not isinstance(srcs, list) or any(not isinstance(s, str) for s in srcs):
        bad("DIM_SOURCES_INVALID", "$.relation_sources", "relation_sources 必须是字符串数组")
    elif kind == "hierarchy_navigation":
        if srcs:
            bad("DIM_SOURCES_INVALID", "$.relation_sources",
                "H（层次导航）必须 relation_sources=[]（S1-4/R-S1-1）")
    elif kind == "relation_expansion":
        missing_rel = [r for r in E_RELATION_MIN if r not in srcs]
        if missing_rel:
            bad("DIM_SOURCES_INVALID", "$.relation_sources",
                f"A（关联扩展）relation_sources 必须 ⊇ E_relation_min，缺 {missing_rel}")

    direction = dim["direction"]
    if direction not in DIRECTIONS:
        bad("DIM_DIRECTION_INVALID", "$.direction", f"direction 必须是 {DIRECTIONS} 之一")
    elif kind == "hierarchy_navigation" and direction != "down":
        bad("DIM_DIRECTION_INVALID", "$.direction", "H 的 direction 必须是 down（S1-4）")

    hop_unit = dim["hop_unit"]
    if hop_unit not in HOP_UNITS:
        bad("DIM_HOP_UNIT_INVALID", "$.hop_unit", f"hop_unit 必须是 {HOP_UNITS} 之一")
    elif kind == "hierarchy_navigation" and hop_unit != "n/a":
        bad("DIM_HOP_UNIT_INVALID", "$.hop_unit",
            "H（层次导航）的 hop_unit 必须是 n/a（S1-4：无关系跳预算）")
    elif hop_unit == "n/a":
        if dim["hop_default"] is not None or dim["hop_max"] is not None:
            bad("DIM_HOP_INVALID", "$.hop_unit", "hop_unit=n/a 时 hop_default/hop_max 必须为 null")
    else:  # edge
        hd, hm = dim["hop_default"], dim["hop_max"]
        if not isinstance(hd, int) or isinstance(hd, bool):
            bad("DIM_HOP_INVALID", "$.hop_default", "hop_unit=edge 时 hop_default 必须是 int")
        if not isinstance(hm, int) or isinstance(hm, bool):
            bad("DIM_HOP_INVALID", "$.hop_max", "hop_unit=edge 时 hop_max 必须是 int")
        if isinstance(hd, int) and isinstance(hm, int):
            if not (1 <= hd <= hm):
                bad("DIM_HOP_INVALID", "$.hop_default", "必须满足 1 ≤ hop_default ≤ hop_max")
            if hm > 2:
                bad("DIM_HOP_INVALID", "$.hop_max", "v1 hop_max ≤ 2（R-S1-5/R-S1-10）")

    term = dim["termination"]
    if not isinstance(term, Mapping):
        bad("DIM_TERMINATION_INVALID", "$.termination", "termination 必须是对象")
    else:
        for key in ("max_nodes", "leaf_required", "stop_on_no_new"):
            if key not in term:
                bad("DIM_TERMINATION_INVALID", f"$.termination.{key}", "缺 termination 字段")
        mn = term.get("max_nodes")
        if mn is not None and (not isinstance(mn, int) or isinstance(mn, bool) or mn <= 0):
            bad("DIM_TERMINATION_INVALID", "$.termination.max_nodes",
                "max_nodes 必须是 >0 整数或 null")
        if not isinstance(term.get("leaf_required"), bool):
            bad("DIM_TERMINATION_INVALID", "$.termination.leaf_required", "必须是 bool")
        elif kind == "hierarchy_navigation" and term["leaf_required"] is not True:
            bad("DIM_TERMINATION_INVALID", "$.termination.leaf_required", "H 必须 leaf_required=true")
        if not isinstance(term.get("stop_on_no_new"), bool):
            bad("DIM_TERMINATION_INVALID", "$.termination.stop_on_no_new", "必须是 bool")

    hr = dim["history_ref"]
    if not isinstance(hr, str):
        bad("DIM_HISTORY_REF_INVALID", "$.history_ref", "history_ref 必须是字符串")

    return problems


def validate_registry(registry: Mapping) -> list[DimProblem]:
    """校验整个 registry（唯一 id / priority / status / history_ref 尾 / registry_sha）。"""
    problems: list[DimProblem] = []
    dims = registry.get("dimensions")
    if not isinstance(dims, list):
        problems.append(DimProblem("DIM_ID_INVALID", "$.dimensions", "dimensions 必须是数组"))
        return problems

    ids: list[str] = []
    priorities: list[int] = []
    for idx, dim in enumerate(dims):
        for p in validate_dimension(dim):
            problems.append(DimProblem(p.dim_code, f"$.dimensions[{idx}]{p.path[1:]}", p.message))
        if isinstance(dim, Mapping):
            ids.append(str(dim.get("id")))
            pr = dim.get("priority")
            if isinstance(pr, int) and not isinstance(pr, bool):
                priorities.append(pr)

    dups = sorted({i for i in ids if ids.count(i) > 1})
    if dups:
        problems.append(DimProblem("DIM_ID_INVALID", "$.dimensions", f"id 重复：{dups}"))
    pdup = sorted({p for p in priorities if priorities.count(p) > 1})
    if pdup:
        problems.append(DimProblem("DIM_PRIORITY_DUPLICATE", "$.dimensions",
                                   f"priority 重复：{pdup}"))

    fb = registry.get("fallback_policy", "allow")
    if fb not in FALLBACK_POLICIES:
        problems.append(DimProblem("DIM_FALLBACK_POLICY_INVALID", "$.fallback_policy",
                                   f"fallback_policy 必须是 {FALLBACK_POLICIES} 之一"))

    declared = registry.get("registry_sha")
    if declared is not None:
        if not isinstance(declared, str) or len(declared) != 64:
            problems.append(DimProblem("DIM_REGISTRY_SHA_INVALID", "$.registry_sha",
                                       "registry_sha 必须是 64 位 hex"))
        else:
            actual = compute_registry_sha(registry)
            if declared != actual:
                problems.append(DimProblem("DIM_REGISTRY_SHA_INVALID", "$.registry_sha",
                                           f"registry_sha 不符：声明 {declared[:16]}… 实际 {actual[:16]}…"))
    return problems


# ── 不可变 history（R-S1-9）──────────────────────────────────────────────


@dataclass(frozen=True)
class HistoryEntry:
    """一版 history 条目（**自包含**：不依赖外部旧 registry 即可证明 new⊇old）。

    ## 为什么条目内联 ``registry_body``

    S1-2 定义 ``registry_sha = sha256(canonical(registry 去掉 registry_sha))``；
    R-S1-9 又要求「registry 的 ``history_ref`` 末条 ``content_sha == registry_sha``」。
    两条**同时成立**的唯一自洽读法：条目 ``content_sha`` 就是**该版 registry 内容**的 sha
    ⇒ 条目必须内联该版 ``registry_body``（= registry 去掉 ``registry_sha``）。
    这样 ``content_sha`` 可**从条目自身复算**，跨版本 ``new ⊇ old`` 也无需外部旧 registry。
    """

    content_sha: str
    previous_sha: str
    registry_version: str
    registry_body: dict
    relation_sources: tuple[str, ...]
    active_dimensions: tuple[str, ...]
    decision_id: str
    created_at: str
    created_by: str
    version: str
    signature: dict | None = None

    def content_body(self) -> dict:
        """``content_sha`` 的计算体 —— 即该版 registry 内容（**不含 signature**）。"""
        return dict(self.registry_body)

    def to_dict(self) -> dict:
        out = {
            "content_sha": self.content_sha,
            "previous_sha": self.previous_sha,
            "registry_version": self.registry_version,
            "registry_body": copy.deepcopy(self.registry_body),
            "relation_sources": list(self.relation_sources),
            "active_dimensions": list(self.active_dimensions),
            "decision_id": self.decision_id,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "version": self.version,
        }
        if self.signature is not None:
            out["signature"] = dict(self.signature)
        return out

    def signature_payload(self) -> dict:
        """签名覆盖的内容（= content_body + 链/决策元数据；**不含 signature 自身**）。"""
        return {
            "active_dimensions": list(self.active_dimensions),
            "content_sha": self.content_sha,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "decision_id": self.decision_id,
            "previous_sha": self.previous_sha,
            "registry_version": self.registry_version,
            "relation_sources": list(self.relation_sources),
            "version": self.version,
        }


def make_history_entry(
    *,
    registry_body: Mapping,
    previous_sha: str,
    registry_version: str,
    version: str,
    relation_sources: Iterable[str],
    active_dimensions: Iterable[str],
    decision_id: str,
    created_by: str,
    created_at: str | None = None,
    signature: Mapping | None = None,
) -> HistoryEntry:
    """构造条目：``content_sha = sha256(canonical(registry_body))``（**不含 signature**）。"""
    body = copy.deepcopy(dict(registry_body))
    for key in _SHA_EXCLUDED_FIELDS:
        body.pop(key, None)
    return HistoryEntry(
        content_sha=sha256_canonical(body),
        previous_sha=str(previous_sha),
        registry_version=str(registry_version),
        registry_body=body,
        relation_sources=tuple(sorted({str(s) for s in relation_sources})),
        active_dimensions=tuple(sorted(str(d) for d in active_dimensions)),
        decision_id=str(decision_id),
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
        created_by=str(created_by),
        version=str(version),
        signature=dict(signature) if signature else None,
    )


def verify_history_chain(
    entries: Sequence[HistoryEntry],
    *,
    verifier: Callable[[HistoryEntry], bool] | None = None,
    require_signature_verification: bool = False,
) -> list[str]:
    """不可变链校验：``content_sha`` 可复算、``previous_sha`` 首尾相接、只增不删、签名。

    ``require_signature_verification=False``（默认）时只做**结构**校验：条目带签名但
    没有 verifier 只记为"未验证"，不算失败（构造期不该因"还没接签名后端"而爆炸）；
    显式校验签名时（:meth:`RegistryService.verify_signatures`）传 ``True`` ⇒ **fail-closed**。
    """
    problems: list[str] = []
    prev = ""
    seen_sources: set[str] = set()
    seen_dims: set[str] = set()

    for idx, e in enumerate(entries):
        recomputed = sha256_canonical(e.content_body())
        if recomputed != e.content_sha:
            problems.append(f"history[{idx}] content_sha 不可复算（声明 {e.content_sha[:12]}… 实际 {recomputed[:12]}…）")
        if e.previous_sha != prev:
            problems.append(f"history[{idx}] 断链：previous_sha={e.previous_sha[:12]!r} 期望 {prev[:12]!r}")
        # 只增不删（跨版本 source_union(new) ⊇ old）
        cur_sources = set(e.relation_sources)
        if not cur_sources >= seen_sources:
            problems.append(f"history[{idx}] relation_sources 减少（只增不删）：缺 {sorted(seen_sources - cur_sources)}")
        seen_sources |= cur_sources
        cur_dims = set(e.active_dimensions)
        if not cur_dims >= seen_dims:
            problems.append(f"history[{idx}] active_dimensions 减少：缺 {sorted(seen_dims - cur_dims)}")
        seen_dims |= cur_dims
        # 签名（可选；有签名才验，验不过 ⇒ 冻结码）
        if e.signature is not None:
            alg = e.signature.get("alg")
            if alg not in _SIGNATURE_ALGS:
                problems.append(f"history[{idx}] 签名 alg 非法：{alg!r}")
            elif verifier is None:
                if require_signature_verification:
                    problems.append(f"history[{idx}] 有条目签名但未提供 verifier（无法证明，fail-closed）")
            elif not verifier(e):
                problems.append(f"history[{idx}] 签名验证失败")
        prev = e.content_sha
    return problems


def verify_registry_history_binding(registry: Mapping,
                                    entries: Sequence[HistoryEntry]) -> list[str]:
    """``history_ref`` 必须指向 history 尾条，且尾条 ``content_sha == registry_sha``（R-S1-9）。

    维度上的 ``history_ref`` 为空串表示"继承 registry 级指针"（合法）；非空则必须等于尾条。
    """
    problems: list[str] = []
    if not entries:
        return ["history 为空（registry 必须引用至少一版）"]
    tail = entries[-1]
    if tail.content_sha != registry.get("registry_sha"):
        problems.append("registry_sha != history 尾条 content_sha（R-S1-9）")
    reg_ref = registry.get("history_ref")
    if reg_ref is not None and reg_ref != tail.content_sha:
        problems.append("registry.history_ref 未指向 history 尾条")
    for idx, dim in enumerate(registry.get("dimensions") or []):
        ref = dim.get("history_ref") if isinstance(dim, Mapping) else None
        if ref not in (None, "") and ref != tail.content_sha:
            problems.append(f"dimensions[{idx}].history_ref 未指向 history 尾条")
    return problems


# ── RegistryService ────────────────────────────────────────────────────


@dataclass
class RegistryService:
    """维度注册表服务：构建 / 解析 / 追加（**只增不删**）。

    注册表是**版本化配置**，不是事实源（S1-11）；本服务不写任何 KB 文件。
    """

    registry: dict
    history: list[HistoryEntry] = field(default_factory=list)
    contract_version: str = "s1-v1"

    # -- 构建 ----------------------------------------------------------
    @classmethod
    def create(
        cls,
        dimensions: Sequence[Mapping],
        *,
        registry_version: str,
        decision_id: str,
        created_by: str,
        created_at: str | None = None,
        fallback_policy: str = "allow",
        signature: Mapping | None = None,
    ) -> "RegistryService":
        """从维度表构建 registry + 首版 history。任何不合规 ⇒ fail-closed。"""
        if not isinstance(registry_version, str) or not registry_version:
            raise GraphError(GRAPH_INTERNAL, "registry_version 不能为空",
                             detail={"dim_code": "DIM_VERSION_INVALID"})
        registry: dict = {
            "registry_version": registry_version,
            "contract_version": "s1-v1",
            "dimensions": [copy.deepcopy(dict(d)) for d in dimensions],
            "fallback_policy": fallback_policy,
        }
        registry["registry_sha"] = compute_registry_sha(registry)

        problems = validate_registry(registry)
        if problems:
            first = problems[0]
            raise GraphError(
                GRAPH_INTERNAL,
                f"维度注册表校验失败：{first.path} {first.message}",
                detail={"dim_code": first.dim_code, "problems": [p.to_dict() for p in problems]},
            )

        entry = make_history_entry(
            registry_body=registry,
            previous_sha="",
            registry_version=registry_version,
            version=registry_version,
            relation_sources=_union_sources(registry),
            active_dimensions=_active_ids(registry),
            decision_id=decision_id,
            created_by=created_by,
            created_at=created_at,
            signature=signature,
        )
        svc = cls(registry=registry, history=[entry])
        # 指针字段（不进哈希域）：registry 指向 history 尾条
        svc.registry["history_ref"] = entry.content_sha
        svc._assert_self_consistent()
        return svc

    # -- 查询 ----------------------------------------------------------
    def resolve(self, dimension_id: str) -> dict:
        """取 ``active`` 维度；未知 ⇒ fail-closed；reserved/deprecated ⇒ fail-closed。"""
        for dim in self.registry.get("dimensions") or []:
            if dim.get("id") == dimension_id:
                status = dim.get("status")
                if status != "active":
                    raise GraphError(
                        GRAPH_INTERNAL,
                        f"维度 {dimension_id!r} 状态为 {status}，不可用于取景（fail-closed）",
                        detail={"dim_code": "DIM_NOT_ACTIVE", "status": status},
                    )
                return copy.deepcopy(dict(dim))
        raise GraphError(GRAPH_INTERNAL, f"未知维度：{dimension_id!r}",
                         detail={"dim_code": "DIM_UNKNOWN"})

    def active_dimensions(self) -> list[dict]:
        return [copy.deepcopy(dict(d)) for d in self.registry.get("dimensions") or []
                if d.get("status") == "active"]

    # -- 追加（只增不删）------------------------------------------------
    def append_version(
        self,
        dimensions: Sequence[Mapping],
        *,
        registry_version: str,
        decision_id: str,
        created_by: str,
        created_at: str | None = None,
        signature: Mapping | None = None,
    ) -> "RegistryService":
        """发布新版本：**只增不删**；删/改 relation_sources ⇒ ``S0_REOPEN_REQUIRED``。"""
        new_registry: dict = {
            "registry_version": registry_version,
            "contract_version": self.contract_version,
            "dimensions": [copy.deepcopy(dict(d)) for d in dimensions],
            "fallback_policy": self.registry.get("fallback_policy", "allow"),
        }
        new_registry["registry_sha"] = compute_registry_sha(new_registry)

        problems = validate_registry(new_registry)
        if problems:
            first = problems[0]
            raise GraphError(
                GRAPH_INTERNAL,
                f"新版本注册表校验失败：{first.path} {first.message}",
                detail={"dim_code": first.dim_code, "problems": [p.to_dict() for p in problems]},
            )

        old_sources = _union_sources(self.registry)
        new_sources = _union_sources(new_registry)
        removed = sorted(old_sources - new_sources)
        if removed:
            raise GraphError(
                GRAPH_INTERNAL,
                f"relation_sources 减少 ⇒ 必须重开 S0（S1-6/R-S1-3）：{removed}",
                detail={"dim_code": "S0_REOPEN_REQUIRED", "removed": removed},
            )
        old_ids = {d.get("id") for d in self.registry.get("dimensions") or []}
        new_ids = {d.get("id") for d in new_registry.get("dimensions") or []}
        dropped = sorted(old_ids - new_ids)
        if dropped:
            raise GraphError(
                GRAPH_INTERNAL,
                f"删除维度 ⇒ 必须重开 S0（只增不删）：{dropped}",
                detail={"dim_code": "S0_REOPEN_REQUIRED", "dropped": dropped},
            )

        entry = make_history_entry(
            registry_body=new_registry,
            previous_sha=self.history[-1].content_sha,
            registry_version=registry_version,
            version=registry_version,
            relation_sources=new_sources,
            active_dimensions=_active_ids(new_registry),
            decision_id=decision_id,
            created_by=created_by,
            created_at=created_at,
            signature=signature,
        )
        svc = RegistryService(registry=new_registry, history=[*self.history, entry],
                              contract_version=self.contract_version)
        svc.registry["history_ref"] = entry.content_sha
        svc._assert_self_consistent()
        return svc

    # -- 自检 ----------------------------------------------------------
    def _assert_self_consistent(self) -> None:
        problems = verify_history_chain(self.history)
        problems += verify_registry_history_binding(self.registry, self.history)
        problems += [f"{p.path} {p.message}" for p in validate_registry(self.registry)]
        if problems:
            raise GraphError(
                GRAPH_INTERNAL,
                f"registry/history 自检失败：{problems[0]}",
                detail={"problems": problems[:10]},
            )

    def verify_signatures(self, verifier: Callable[[HistoryEntry], bool]) -> None:
        """用给定 verifier 校验全部签名；失败/缺失 ⇒ ``GRAPH_HISTORY_SIGNATURE_INVALID``。"""
        problems = [
            p for p in verify_history_chain(
                self.history, verifier=verifier, require_signature_verification=True
            )
            if "签名" in p
        ]
        if problems:
            raise GraphError(GRAPH_HISTORY_SIGNATURE_INVALID,
                             f"history 签名校验失败：{problems[0]}",
                             detail={"problems": problems})

    def history_signed(self) -> bool:
        """G6 的 ``history_signed`` 标记：全部条目都带签名才算 signed。"""
        return bool(self.history) and all(e.signature is not None for e in self.history)

    def to_dict(self) -> dict:
        return {
            "registry": copy.deepcopy(self.registry),
            "history": [e.to_dict() for e in self.history],
            "history_signed": self.history_signed(),
        }


def _union_sources(registry: Mapping) -> set[str]:
    out: set[str] = set()
    for dim in registry.get("dimensions") or []:
        if isinstance(dim, Mapping):
            out |= {str(s) for s in dim.get("relation_sources") or []}
    return out


def _active_ids(registry: Mapping) -> set[str]:
    return {
        str(d.get("id")) for d in registry.get("dimensions") or []
        if isinstance(d, Mapping) and d.get("status") == "active"
    }
