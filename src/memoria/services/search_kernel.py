"""Lexical 检索内核（M4）。

统一 ``search()`` 与各 ``suggest_*`` 的接入点；Embedding 层可选开启。
"""

from __future__ import annotations

from collections import Counter

from memoria.services.body_locate import is_body_locate_enabled, search_body_locate
from memoria.services.lexical_index import ensure_lexical_index, search_lexical
from memoria.services.model_router import query_plan_stub
from memoria.services.retrieval_fusion import annotate_lexical_results, fuse_search_results


def _attach_body_locate(
    payload: dict,
    query: str,
    *,
    kb_path: str,
    scope: str,
    rel_path: str | None,
    limit: int,
) -> dict:
    if not is_body_locate_enabled():
        payload["body_locate"] = []
        return payload
    payload["body_locate"] = search_body_locate(
        query,
        kb_path=kb_path,
        scope=scope,
        rel_path=rel_path,
        limit=min(15, max(1, int(limit))),
    )
    return payload


def search(
    query: str,
    *,
    scope: str = "kb",
    limit: int = 20,
    modes: str | None = None,
    kb_path: str | None = None,
    rel_path: str | None = None,
) -> dict:
    """全局 / 文件内检索。"""
    if not kb_path:
        q = (query or "").strip()
        return {
            "status": "ok",
            "available": False,
            "reason": "kb_not_open",
            "query": q,
            "scope": scope,
            "results": [],
        }
    mode = (modes or "lexical").lower()
    q = (query or "").strip()
    semantic: dict | None = None
    use_rrf = mode in ("both", "full")

    if mode in ("semantic", "both", "full"):
        from memoria.services.embedding_provider import search_semantic

        semantic = search_semantic(
            query,
            kb_path=kb_path,
            scope=scope,
            rel_path=rel_path,
            limit=limit if not use_rrf else max(limit, 50),
        )
        if mode == "semantic":
            from memoria.services.retrieval_fusion import annotate_lexical_results as _ann

            sem_results = _ann(semantic.get("results") or []) if semantic.get("available") else []
            out = {
                **semantic,
                "query": q,
                "scope": scope,
                "modes": mode,
                "results": sem_results,
                "query_plan": query_plan_stub(kb_path=kb_path),
            }
            return _attach_body_locate(
                out, q, kb_path=kb_path, scope=scope, rel_path=rel_path, limit=limit
            )

    lexical = search_lexical(
        query,
        kb_path=kb_path,
        scope=scope,
        rel_path=rel_path,
        limit=limit if mode == "lexical" else max(limit, 50),
    )
    lexical["query"] = q
    lexical["scope"] = scope
    lexical["modes"] = mode
    lexical["query_plan"] = query_plan_stub(kb_path=kb_path)

    if mode == "lexical":
        lexical["results"] = annotate_lexical_results(lexical.get("results") or [])
    elif use_rrf and semantic and semantic.get("available"):
        merged = fuse_search_results(
            lexical_hits=lexical.get("results") or [],
            semantic_hits=semantic.get("results") or [],
            limit=limit,
        )
        # P3: Embed-Rerank（可选 cross-encoder 精排）
        try:
            from memoria.services.rerank_provider import is_rerank_enabled, rerank_search_results

            if is_rerank_enabled():
                merged = rerank_search_results(
                    q, merged, kb_path=kb_path, top_k=limit
                )
        except Exception:
            pass
        lexical["results"] = merged
        lexical["semantic"] = semantic
        lexical["fusion"] = "rrf"
        if is_rerank_enabled():
            lexical["fusion"] = "rrf+rerank"
    elif use_rrf:
        lexical["results"] = annotate_lexical_results(lexical.get("results") or [])[:limit]
        if semantic:
            lexical["semantic"] = semantic
    else:
        lexical["results"] = annotate_lexical_results(lexical.get("results") or [])

    return _attach_body_locate(
        lexical, q, kb_path=kb_path, scope=scope, rel_path=rel_path, limit=limit
    )


def suggest_kp_merge(
    kp_id: str,
    *,
    kb_path: str | None = None,
    rel_path: str | None = None,
) -> dict:
    """近重复知识点合并建议（Lexical name 相似度）。"""
    kid = (kp_id or "").strip()
    if not kb_path or not kid:
        return {
            "status": "ok",
            "available": False,
            "reason": "search_kernel_not_available",
            "suggestions": [],
            "kp_id": kid,
        }

    index = ensure_lexical_index(kb_path)
    target_name = ""
    for rec in index.get("records") or []:
        if rec.get("kp_id") == kid:
            target_name = str(rec.get("name") or "").strip()
            break
    if not target_name:
        return {
            "status": "ok",
            "available": True,
            "suggestions": [],
            "kp_id": kid,
        }

    res = search_lexical(target_name, kb_path=kb_path, scope="kb", limit=12)
    name_sources = frozenset({
        "name_exact",
        "name_contains",
        "name-fuzzy",
        "name_pinyin",
        "id_exact",
        "id_prefix",
        "id_contains",
        "id_pinyin",
    })
    suggestions = []
    for item in res.get("results") or []:
        if item.get("kp_id") == kid:
            continue
        sources = set(item.get("sources") or [])
        score = float(item.get("score") or 0)
        if not sources & name_sources:
            continue
        if score < 55.0:
            continue
        suggestions.append({
            "kp_id": item.get("kp_id"),
            "name": item.get("name"),
            "file": item.get("file"),
            "score": item.get("score"),
            "sources": list(sources),
        })
    return {
        "status": "ok",
        "available": True,
        "suggestions": suggestions[:5],
        "kp_id": kid,
    }


def suggest_group_label(
    *,
    kb_path: str | None,
    node_ids: list[str],
    hub_id: str | None = None,
    hub_name: str | None = None,
) -> dict:
    """节点群智能页签名：库内 tag 共现优先，否则 Hub 名称。"""
    ids = [str(x).strip() for x in (node_ids or []) if str(x).strip()]
    default = (hub_name or hub_id or (ids[0] if ids else "")).strip()
    if not kb_path or not ids:
        return {
            "status": "ok",
            "available": False,
            "reason": "search_kernel_not_available",
            "suggested": None,
            "default": default,
            "hub_id": hub_id,
        }

    index = ensure_lexical_index(kb_path)
    id_set = set(ids)
    tag_counter: Counter[str] = Counter()
    names: dict[str, str] = {}
    for rec in index.get("records") or []:
        kid = str(rec.get("kp_id") or "")
        if kid not in id_set:
            continue
        names[kid] = str(rec.get("name") or kid)
        for tag in rec.get("tags") or []:
            t = str(tag).strip()
            if t:
                tag_counter[t] += 1

    suggested: str | None = None
    if tag_counter:
        tag, count = tag_counter.most_common(1)[0]
        if count >= 2 or (len(ids) <= 3 and count >= 1):
            suggested = tag

    if not suggested:
        suggested = names.get(str(hub_id or ""), "") or default

    return {
        "status": "ok",
        "available": True,
        "suggested": suggested or default,
        "default": default,
        "hub_id": hub_id,
    }


def suggest_group_labels(
    *,
    kb_path: str | None,
    groups: list[dict],
) -> dict:
    """批量群命名。"""
    labels: dict[str, str] = {}
    for g in groups or []:
        gid = str(g.get("id") or g.get("rootId") or "")
        if not gid:
            continue
        res = suggest_group_label(
            kb_path=kb_path,
            node_ids=g.get("nodeIds") or g.get("node_ids") or [],
            hub_id=g.get("hubId") or g.get("hub_id"),
            hub_name=g.get("hubName") or g.get("hub_name"),
        )
        labels[gid] = str(res.get("suggested") or res.get("default") or gid)
    return {"status": "ok", "labels": labels}


def _norm_path(p: str | None) -> str:
    return str(p or "").replace("\\", "/")
