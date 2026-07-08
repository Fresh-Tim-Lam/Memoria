"""链接 relevance 建议（M4 SearchKernel Lexical 层）。"""



from __future__ import annotations



from memoria.graph.edge_types import normalize_link_edge_type, normalize_link_relevance

from memoria.services.lexical_index import search_lexical





def suggest_link_relevance(

    *,

    anchor_text: str,

    target_ids: list[str] | None = None,

    edge_type: str | None = None,

    source_id: str | None = None,

    kb_path: str | None = None,

) -> dict:

    """根据锚文本与目标 id 的 Lexical 匹配推荐 ``links[].relevance``（0～1）。"""

    et = normalize_link_edge_type(edge_type)

    default = normalize_link_relevance(None, edge_type=et)

    anchor = (anchor_text or "").strip()

    targets = [str(t).strip() for t in (target_ids or []) if str(t).strip()]



    if not kb_path or not anchor:

        return {

            "status": "ok",

            "suggested": None,

            "reason": "search_kernel_not_available",

            "default": default,

            "edge_type": et,

        }



    res = search_lexical(anchor, kb_path=kb_path, scope="kb", limit=20)

    scores: dict[str, float] = {}

    for item in res.get("results") or []:

        kid = str(item.get("kp_id") or "").strip()

        if not kid:

            continue

        scores[kid] = max(scores.get(kid, 0.0), min(1.0, float(item.get("score") or 0) / 100.0))



    if targets:

        best_id = max(targets, key=lambda t: scores.get(t, 0.0))

        best = scores.get(best_id, 0.0)

        if best > 0:

            return {

                "status": "ok",

                "suggested": round(best, 2),

                "available": True,

                "best_target_id": best_id,

                "default": default,

                "edge_type": et,

            }



    if scores:

        best_id = max(scores, key=scores.get)

        return {

            "status": "ok",

            "suggested": round(scores[best_id], 2),

            "available": True,

            "best_target_id": best_id,

            "default": default,

            "edge_type": et,

        }



    return {

        "status": "ok",

        "suggested": None,

        "reason": "no_lexical_match",

        "default": default,

        "edge_type": et,

    }

