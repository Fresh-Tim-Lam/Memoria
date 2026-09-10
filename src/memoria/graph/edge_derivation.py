"""从 KP range 几何与 sidecar links[] 推导图谱边。"""



from __future__ import annotations



from dataclasses import dataclass



from memoria.graph.edge_types import (

    EDGE_CONTAIN,

    EDGE_EXTEND,

    EDGE_REFERENCE,

    default_relevance,

    normalize_edge_type,

    normalize_link_edge_type,
    edge_props_for_link_target,
    relevance_for_link,

)

from memoria.services.kp_index import build_kp_index

from memoria.services.kp_resolver import resolve_knowledge_points





@dataclass(frozen=True)

class KpRange:

    kp_id: str

    start: int

    end: int





def strictly_contains(outer: KpRange, inner: KpRange) -> bool:

    """outer 严格包含 inner（同 range 不算包含）。"""

    if outer.kp_id == inner.kp_id:

        return False

    if outer.start > inner.start or inner.end > outer.end:

        return False

    return outer.start < inner.start or inner.end < outer.end





def line_in_kp(line: int, kp: KpRange) -> bool:

    return kp.start <= line <= kp.end





def kp_ranges_from_resolved(kps: list[dict]) -> list[KpRange]:

    out: list[KpRange] = []

    for kp in kps:

        kp_id = (kp.get("id") or "").strip()

        if not kp_id:

            continue

        rr = kp.get("range_resolved") or {}

        if not rr.get("ok"):

            continue

        sl, el = rr.get("start_line"), rr.get("end_line")

        if sl is None or el is None:

            continue

        out.append(KpRange(kp_id=kp_id, start=int(sl), end=int(el)))

    return out





def minimal_kps_for_line(line: int, ranges: list[KpRange]) -> list[str]:

    """行落在哪些 KP 上；嵌套时只保留最内层；部分交叉则保留多个。"""

    hits = [r for r in ranges if line_in_kp(line, r)]

    if not hits:

        return []

    return [

        r.kp_id

        for r in hits

        if not any(

            r.kp_id != other.kp_id and strictly_contains(r, other) for other in hits

        )

    ]


def containing_kps_for_line(line: int, ranges: list[KpRange]) -> list[str]:
    """行落在哪些 KP range 内（含父层，不做最内层筛选）。"""
    return [r.kp_id for r in ranges if line_in_kp(line, r)]


def line_in_any_kp(line: int, ranges: list[KpRange]) -> bool:
    """行是否落入至少一个 KP range（含父与子之间的空隙区）。"""
    return bool(containing_kps_for_line(line, ranges))


def sources_for_link_instance(
    line: int,
    ranges: list[KpRange],
    link: dict | None = None,
) -> list[str]:
    """实例行对应的图谱 source KP；嵌套取最内层，否则回退 link.source_id。"""
    sources = minimal_kps_for_line(line, ranges)
    if sources:
        return sources
    if not link:
        return []
    sid = str(link.get("source_id") or "").strip()
    if not sid:
        return []
    for r in ranges:
        if r.kp_id == sid and line_in_kp(line, r):
            return [sid]
    return []



def build_target_kp_resolver(kb_path: str):

    """图谱边 target：仅当 raw 为已存在的 KP id 时才解析（不用文件 stem→首个 KP）。"""

    index = build_kp_index(kb_path)

    known_kp_ids = set(index["by_id"])

    file_stems: dict[str, str] = index["file_stems"]

    cache: dict[str, str | None] = {}



    def resolve(raw: str) -> str | None:

        tid = (raw or "").strip()

        if not tid:

            return None

        if tid in cache:

            return cache[tid]

        if tid in known_kp_ids:

            cache[tid] = tid

            return tid

        # 文件 stem 仅当该文件内有同 id 的 KP 时才建边（如 mdp.md 的 id=mdp）

        if tid in file_stems:

            rel = file_stems[tid]

            if any(

                e.kp_id == tid and e.file.replace("\\", "/") == rel.replace("\\", "/")

                for e in index["entries"]

            ):

                cache[tid] = tid

                return tid

            cache[tid] = None

            return None

        cache[tid] = None

        return None



    return resolve


# ── G5：由全库轻量快照构造 resolver（读路径零构建，语义与上文一致）────────────
# 快照来自 memoria.services.kp_index.collect_kp_targets：ids / file_stems / (文件, kp_id) 对。
# 触发点约束见 docs/to-dolist.md §12：交互热路径只读快照，不构建全库索引。

def build_target_kp_resolver_from(
    known_kp_ids: set[str] | None,
    file_stems: dict[str, str] | None,
    pairs: set[tuple[str, str]] | None,
):

    """图谱边 target：仅当 raw 为已存在的 KP id 时才解析（不用文件 stem→首个 KP）。"""

    known = set(known_kp_ids or ())

    stems: dict[str, str] = dict(file_stems or {})

    present = {(f.replace("\\", "/"), k) for f, k in (pairs or ())}

    cache: dict[str, str | None] = {}



    def resolve(raw: str) -> str | None:

        tid = (raw or "").strip()

        if not tid:

            return None

        if tid in cache:

            return cache[tid]

        if tid in known:

            cache[tid] = tid

            return tid

        if tid in stems:

            rel = stems[tid].replace("\\", "/")

            if (rel, tid) in present:

                cache[tid] = tid

                return tid

            cache[tid] = None

            return None

        cache[tid] = None

        return None



    return resolve





def derive_contain_edges(
    ranges: list[KpRange],
    *,
    no_build_set: set[tuple[str, str]] | None = None,
) -> list[dict]:

    edges: list[dict] = []

    seen: set[tuple[str, str]] = set()

    for inner in ranges:
        # Find direct parents: outers that strictly contain inner, but are not
        # themselves contained by another outer that also contains inner.
        # Only generate edges for direct parent-child pairs, skipping transitive
        # relationships (e.g. a→c when a contains b and b contains c).
        direct_parents: list[KpRange] = []
        for outer in ranges:
            if not strictly_contains(outer, inner):
                continue
            # outer is a candidate parent; check if any other candidate
            # is a tighter parent (contained by outer but still contains inner)
            is_direct = True
            for mid in ranges:
                if mid.kp_id == outer.kp_id or mid.kp_id == inner.kp_id:
                    continue
                if strictly_contains(outer, mid) and strictly_contains(mid, inner):
                    is_direct = False
                    break
            if is_direct:
                direct_parents.append(outer)

        for outer in direct_parents:
            key = (outer.kp_id, inner.kp_id)
            if key in seen:
                continue
            seen.add(key)
            edge: dict = {
                "type": "contain",
                "source_id": outer.kp_id,
                "targets": [inner.kp_id],
                "relevance": default_relevance("contain"),
                "derived": True,
                "origin": "range",
            }
            if no_build_set and key in no_build_set:
                edge["no_build"] = True
            edges.append(edge)

    return edges





def _normalize_targets(raw: object) -> list[str]:

    if raw is None:

        return []

    if isinstance(raw, str):

        s = raw.strip()

        return [s] if s else []

    if isinstance(raw, list):

        return [str(t).strip() for t in raw if isinstance(t, str) and str(t).strip()]

    return []





def _edge_type_for_link(link: dict) -> str:

    return normalize_link_edge_type(link.get("edge_type"))





def _add_edge(

    edges: list[dict],

    seen: set[tuple[str, str, str]],

    *,

    edge_type: str,

    source_id: str,

    target_id: str,

    file: str,

    origin: str,

    line: int | None = None,

    relevance: float | None = None,

) -> None:

    if not source_id or not target_id or source_id == target_id:

        return

    key = (edge_type, source_id, target_id)

    if key in seen:

        return

    seen.add(key)

    edges.append(

        {

            "type": edge_type,

            "source_id": source_id,

            "targets": [target_id],

            "relevance": (
                default_relevance(edge_type)
                if relevance is None
                else max(0.0, min(1.0, float(relevance)))
            ),

            "derived": True,

            "origin": origin,

            "file": file,

            **({"line": line} if line is not None else {}),

        }

    )





def _resolve_edge_targets(

    raw_targets: list[str],

    *,

    resolve_target_kp,

) -> list[str]:

    resolved: list[str] = []

    seen: set[str] = set()

    for raw in raw_targets:

        kp_id = resolve_target_kp(raw)

        if not kp_id or kp_id in seen:

            continue

        seen.add(kp_id)

        resolved.append(kp_id)

    return resolved





def derive_link_edges(

    rel_path: str,

    body: str,

    sidecar: dict | None,

    kps: list[dict],

    *,

    resolve_target_kp,

) -> list[dict]:

    """仅从侧车 links[]（含 instances）推导 reference/extend 边；不扫描正文 wikilink。"""

    ranges = kp_ranges_from_resolved(kps)

    if not ranges:

        return []



    sidecar = sidecar or {}

    edges: list[dict] = []

    seen: set[tuple[str, str, str]] = set()



    for link in sidecar.get("links") or []:

        if not isinstance(link, dict):

            continue

        targets = _resolve_edge_targets(

            _normalize_targets(link.get("targets")),

            resolve_target_kp=resolve_target_kp,

        )

        if not targets:

            continue



        edge_type = _edge_type_for_link(link)

        instances = link.get("instances") or []

        lines: list[int] = []

        for inst in instances:

            if isinstance(inst, dict) and inst.get("line") is not None:

                lines.append(int(inst["line"]))



        if not lines:

            continue



        for line in lines:

            sources = sources_for_link_instance(line, ranges, link)

            if not sources:

                continue

            for source_id in sources:

                for target_id in targets:

                    tgt_type, tgt_rel = edge_props_for_link_target(link, target_id)

                    _add_edge(

                        edges,

                        seen,

                        edge_type=tgt_type,

                        source_id=source_id,

                        target_id=target_id,

                        file=rel_path,

                        origin="link",

                        line=line,

                        relevance=tgt_rel,

                    )



    return edges





def dedupe_graph_edges(edges: list[dict]) -> list[dict]:

    """按 (type, source, target, no_build) 去重；保留 derived 原值。"""

    out: list[dict] = []

    seen: set[tuple[str, str, str, bool]] = set()



    for e in edges:

        edge_type = normalize_edge_type(e.get("type")) or (e.get("type") or "")

        source_id = (e.get("source_id") or "").strip()

        no_build = bool(e.get("no_build"))

        for target_id in _normalize_targets(e.get("targets")):

            key = (edge_type, source_id, target_id, no_build)

            if not edge_type or not source_id or not target_id or key in seen:

                continue

            seen.add(key)

            item = dict(e)

            item["type"] = edge_type

            item["targets"] = [target_id]

            if no_build:
                item["no_build"] = True

            out.append(item)

    return out





def derive_sidecar_edges(
    rel_path: str,
    sidecar: dict | None,
    *,
    resolve_target_kp,
) -> list[dict]:
    """从 sidecar edges[] 字段读取纯边（不含 no_build 的 contain 标记条目）。"""
    sidecar = sidecar or {}
    edges: list[dict] = []
    for edge in sidecar.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        # no_build 条目仅用于抑制 contain 边，不作为纯边生成
        if edge.get("no_build"):
            continue
        source_id = (edge.get("source_id") or "").strip()
        edge_type = normalize_edge_type(edge.get("type"))
        if not source_id or not edge_type:
            continue
        targets = _resolve_edge_targets(
            _normalize_targets(edge.get("targets")),
            resolve_target_kp=resolve_target_kp,
        )
        for target_id in targets:
            edges.append({
                "type": edge_type,
                "source_id": source_id,
                "targets": [target_id],
                "relevance": edge.get("relevance") or default_relevance(edge_type),
                "derived": False,
                "origin": "sidecar_edge",
                "file": rel_path,
            })
    return edges


def _read_no_build_set(sidecar: dict | None) -> set[tuple[str, str]]:
    """从 sidecar edges[] 中提取 contain 类型的 no_build 标记。"""
    sidecar = sidecar or {}
    no_build: set[tuple[str, str]] = set()
    for edge in sidecar.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        if not edge.get("no_build"):
            continue
        et = normalize_edge_type(edge.get("type"))
        if et != EDGE_CONTAIN:
            continue
        source_id = (edge.get("source_id") or "").strip()
        if not source_id:
            continue
        for tgt in _normalize_targets(edge.get("targets")):
            no_build.add((source_id, tgt))
    return no_build


def derive_file_graph_edges(

    rel_path: str,

    body: str,

    sidecar: dict | None,

    *,

    resolve_target_kp,

) -> tuple[list[dict], list[dict], list[dict]]:

    """返回 (contain_edges, link_edges, sidecar_edges)。"""

    kps = resolve_knowledge_points(body, sidecar)

    ranges = kp_ranges_from_resolved(kps)

    no_build_set = _read_no_build_set(sidecar)

    contain = derive_contain_edges(ranges, no_build_set=no_build_set)

    link_edges = derive_link_edges(

        rel_path, body, sidecar, kps, resolve_target_kp=resolve_target_kp

    )

    sidecar_edges = derive_sidecar_edges(
        rel_path, sidecar, resolve_target_kp=resolve_target_kp
    )

    return contain, link_edges, sidecar_edges

