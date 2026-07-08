"""侧车语义边类型（designV0 §3.3 / §9）。

- sidecar ``links[].edge_type`` / ``edges[].type``：唯一权威来源
- 正文 ``[[target]]`` 不含 ``#类型``；遗留 ``#prerequisite`` 等仅在 kb 同步时
  读入 sidecar 并自正文剥离（见 ``link_md.strip_known_wikilink_edge_hints``）
"""

from __future__ import annotations

EDGE_CONTAIN = "contain"
EDGE_REFERENCE = "reference"
EDGE_EXTEND = "extend"

EDGE_TYPES = frozenset({EDGE_CONTAIN, EDGE_REFERENCE, EDGE_EXTEND})

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


def normalize_link_edge_type(raw: str | None) -> str:
    """links[].edge_type：仅 reference / extend，默认 reference。"""
    normalized = normalize_edge_type(raw)
    if normalized == EDGE_EXTEND:
        return EDGE_EXTEND
    return EDGE_REFERENCE


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
