"""侧车语义边类型（designV0 §3.3 / §9）。

- sidecar ``links[].edge_type`` / ``edges[].type``：唯一权威来源
- 正文 ``[[target]]`` 不含 ``#类型``；遗留 ``#prerequisite`` 等仅在 kb 同步时
  读入 sidecar 并自正文剥离（见 ``link_md.strip_known_wikilink_edge_hints``）

## 允许集合只有一份（KG-v0 D-KG-04①，2026-10-26）

历史缺陷：`EDGE_TYPES`（3 种）与 `services/agent/plan.py::PLAN_EDGE_TYPES`（2 种）
是**两个平级常量**，描述同一个语义空间 ⇒ 同一个枚举两端不对称。
D-KG-04① 明确：去 agent 参数不能消除它（不对称在**常量**里，被 `plan` 用作原值白名单）。

现在的建模（唯一事实 + 派生关系）：

    EDGE_TYPES              全部语义类型（唯一允许集合）
    DERIVE_ONLY_EDGE_TYPES  其中*只能由系统派生、不可手写*的子集（`contain`）
    PLAN_EDGE_TYPES         := EDGE_TYPES - DERIVE_ONLY_EDGE_TYPES   （在 plan.py 里这样算）

⇒ "可手写"不再是手抄的第二份清单，而是**从唯一集合算出来的**。
`tests/test_kg_contract_consistency.py` 恒等断言锁住这一点。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

EDGE_CONTAIN = "contain"
EDGE_REFERENCE = "reference"
EDGE_EXTEND = "extend"

EDGE_TYPES = frozenset({EDGE_CONTAIN, EDGE_REFERENCE, EDGE_EXTEND})

#: **只能派生、不可手写**的边类型（D-KG-04①）。
#: `contain` 由标题层级 / KP 行区间推导（`edge_derivation.derive_contain_edges`），
#: 作者与 agent 都不应手写它 —— 但它仍属于 `EDGE_TYPES`（图谱里可以有这种边）。
DERIVE_ONLY_EDGE_TYPES = frozenset({EDGE_CONTAIN})

# 遗留 wikilink #fragment → 语义类型（仅迁移读入 sidecar，不再写入正文）
WIKILINK_HINT_ALIASES: dict[str, str] = {
    "prerequisite": EDGE_REFERENCE,
    "analogy": EDGE_REFERENCE,
    "ref": EDGE_REFERENCE,
    "reference": EDGE_REFERENCE,
    "extend": EDGE_EXTEND,
    "contain": EDGE_CONTAIN,
}

_DEFAULT_RELEVANCE: dict[str, float] = {
    EDGE_CONTAIN: 0.9,
    EDGE_REFERENCE: 0.7,
    EDGE_EXTEND: 0.6,
}


def normalize_edge_type(raw: str | None) -> str | None:
    """归一化侧车 edges[].type；无效则返回 None。"""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    if s in EDGE_TYPES:
        return s
    return WIKILINK_HINT_ALIASES.get(s)


def normalize_wikilink_edge_hint(raw: str | None) -> str | None:
    """遗留正文 ``[[id#hint]]`` 中的 hint → 语义类型（迁移用）。"""
    return normalize_edge_type(raw)


def is_wikilink_edge_type_fragment(raw: str | None) -> bool:
    """hint 是否为已注册的边类型片段（非正文锚点如 ``#贝尔曼方程``）。"""
    return normalize_edge_type(raw) is not None


def default_relevance(edge_type: str | None) -> float:
    if edge_type in _DEFAULT_RELEVANCE:
        return _DEFAULT_RELEVANCE[edge_type]
    return 0.5


def normalize_link_edge_type_with_warn(raw: str | None) -> str:
    """`links[].edge_type` 归一化，**回落时留痕**（KG-v0 D-KG-04② / task-86 D3(c)）。

    ## 为什么需要它

    `contain` 只能由系统派生（`DERIVE_ONLY_EDGE_TYPES`），写到 link 上是**无意义输入**：
    旧实现直接把它（以及任何未知值，如 `prerequisite`）**静默**改写成 `reference`。
    静默回落违反已经裁过的 D3(c)「回落留痕 warn」—— 数据里"有人想写 prerequisite、
    被悄悄变成 reference"这件事，事后完全不可见。

    ## 留痕口径（只 warn，不改返回值）

    - **返回值语义保持不变**：`reference` / `extend` / 默认 `reference`
      （改返回值会静默改变图谱数据，那不是本裁决要的）
    - **只在真的发生"语义改写"时 warn**：`reference` / `extend` / 缺省 ⇒ 零日志（避免噪音）
    - **按【原始输入】判定，不按归一化结果判定** —— 这点很关键：
      `WIKILINK_HINT_ALIASES` 会把 `prerequisite` / `analogy` 先映射成 `reference`，
      若按归一化结果判定，它们会被误判为"合法值"而**不留痕**，
      但用户的真实意图（前置依赖 / 类比）已经丢失 ⇒ 必须 warn。
    """
    raw_text = "" if raw is None else str(raw).strip()
    lowered = raw_text.lower()

    # ① 本来就是合法可手写值（含缺省）⇒ 直接返回，不留痕。
    if not lowered or lowered in (EDGE_REFERENCE, EDGE_EXTEND):
        return normalize_edge_type(lowered) or EDGE_REFERENCE

    normalized = normalize_edge_type(lowered)
    # ② 派生专用类型（contain）：不可手写 ⇒ 留痕。
    if normalized in DERIVE_ONLY_EDGE_TYPES:
        logger.warning(
            "links[].edge_type=%r 属于派生专用类型（不可手写）⇒ 回落为 %r；"
            "若要表达包含关系请改由标题层级/KP 范围派生",
            raw_text,
            EDGE_REFERENCE,
        )
        return EDGE_REFERENCE
    # ③ 遗留别名（prerequisite / analogy / ref …）：映射到 reference，但**语义已丢失** ⇒ 留痕。
    if normalized is not None:
        logger.warning(
            "links[].edge_type=%r 是遗留别名 ⇒ 回落为 %r（原始语义已丢失；"
            "v0 类型空间只有 %s）",
            raw_text,
            normalized,
            ", ".join(sorted(EDGE_TYPES)),
        )
        return normalized
    # ④ 完全未知值 ⇒ 留痕。
    logger.warning(
        "links[].edge_type=%r 不是已知边类型（允许 %s）⇒ 回落为 %r",
        raw_text,
        ", ".join(sorted(EDGE_TYPES)),
        EDGE_REFERENCE,
    )
    return EDGE_REFERENCE


def normalize_link_edge_type(raw: str | None) -> str:
    """links[].edge_type：仅 reference / extend，默认 reference。

    **返回值语义不变**（KG-v0 D-KG-04②：留痕是增强可观测性，不是语义变更）；
    实际实现委托给带留痕版本，所以任何回落都会留下 warn。
    """
    return normalize_link_edge_type_with_warn(raw)


def normalize_link_relevance(
    raw: object,
    *,
    edge_type: str | None = None,
) -> float:
    """links[].relevance：0～1；缺省按 edge_type 默认。"""
    et = normalize_link_edge_type(edge_type) if edge_type else EDGE_REFERENCE
    if raw is None or raw == "":
        return default_relevance(et)
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return default_relevance(et)
    return max(0.0, min(1.0, v))


def relevance_for_link(link: dict) -> float:
    """从 sidecar link 条目读取图谱边 relevance（link 级 fallback，优先用 target_edges）。"""
    edge_type = normalize_link_edge_type(link.get("edge_type"))
    if link.get("relevance") is not None:
        return normalize_link_relevance(link.get("relevance"), edge_type=edge_type)
    return default_relevance(edge_type)


def edge_props_for_link_target(link: dict, target_id: str) -> tuple[str, float]:
    """单条 links[] → 目标 KP 的图谱边属性（type + relevance）。"""
    tid = str(target_id or "").strip()
    te = link.get("target_edges")
    if isinstance(te, dict) and tid:
        item = te.get(tid)
        if isinstance(item, dict):
            et = normalize_link_edge_type(item.get("edge_type") or link.get("edge_type"))
            rel = normalize_link_relevance(item.get("relevance"), edge_type=et)
            return et, rel
    et = normalize_link_edge_type(link.get("edge_type"))
    rel = relevance_for_link(link)
    return et, rel


def normalize_target_edges(
    raw: object,
    *,
    target_ids: list[str],
    link: dict | None = None,
) -> dict[str, dict]:
    """归一化 links[].target_edges：每个跳转目标一条语义边配置。"""
    link = link or {}
    default_et = normalize_link_edge_type(link.get("edge_type"))
    default_rel = relevance_for_link(link)
    out: dict[str, dict] = {}

    existing = raw if isinstance(raw, dict) else link.get("target_edges")
    if not isinstance(existing, dict):
        existing = {}

    for tid in target_ids:
        tid = str(tid or "").strip()
        if not tid:
            continue
        item = existing.get(tid)
        if isinstance(item, dict):
            et = normalize_link_edge_type(item.get("edge_type") or default_et)
            rel = normalize_link_relevance(item.get("relevance"), edge_type=et)
        else:
            et = default_et
            rel = default_rel
        out[tid] = {"edge_type": et, "relevance": rel}
    return out
