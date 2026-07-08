"""Lexical 检索内核（M4）。

统一 ``search()`` 与各 ``suggest_*`` 的接入点；Embedding 层可选开启。
"""

from __future__ import annotations

from collections import Counter

from memoria.services.body_locate import is_body_locate_enabled, search_body_locate
from memoria.services.lexical_index import ensure_lexical_index, search_lexical


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

    if mode in ("semantic", "both"):
        from memoria.services.embedding_provider import search_semantic

        semantic = search_semantic(
            query,
            kb_path=kb_path,
            scope=scope,
            rel_path=rel_path,
            limit=limit,
        )
        if mode == "semantic":
            out = {
                **semantic,
                "query": q,
                "scope": scope,
                "modes": mode,
            }
            return _attach_body_locate(
                out, q, kb_path=kb_path, scope=scope, rel_path=rel_path, limit=limit
            )

    lexical = search_lexical(
        query,
        kb_path=kb_path,
        scope=scope,
        rel_path=rel_path,
        limit=limit if mode != "both" else max(limit, 50),
    )
    lexical["query"] = q
    lexical["scope"] = scope
    lexical["modes"] = mode

    if mode == "both" and semantic and semantic.get("available"):
        merged = _merge_results(
            lexical.get("results") or [],
            semantic.get("results") or [],
            limit=limit,
        )
        lexical["results"] = merged
        lexical["semantic"] = semantic
    return _attach_body_locate(
        lexical, q, kb_path=kb_path, scope=scope, rel_path=rel_path, limit=limit
    )


def _merge_results(
    lexical_hits: list[dict],
    semantic_hits: list[dict],
    *,
    limit: int,
) -> list[dict]:
    by_id: dict[str, dict] = {}
    for item in lexical_hits:
        kid = str(item.get("kp_id") or "")
        if not kid:
            continue
        row = dict(item)
        if row.get("lexical_score") is None and row.get("score") is not None:
            row["lexical_score"] = row["score"]
        by_id[kid] = row

    for item in semantic_hits:
        kid = str(item.get("kp_id") or "")
        if not kid:
            continue
        sem_score = float(item.get("semantic_score") or item.get("score") or 0)
        if kid in by_id:
            row = by_id[kid]
            lex_score = float(row.get("lexical_score") or row.get("score") or 0)
            row["lexical_score"] = round(lex_score, 1)
            row["semantic_score"] = round(sem_score, 1)
            row["confidence"] = round(sem_score, 1)
            row["score"] = round(lex_score * 0.65 + sem_score * 0.35, 1)
            src = list(row.get("sources") or [])
            if "semantic" not in src:
                src.append("semantic")
            row["sources"] = src
        else:
            row = dict(item)
            row["semantic_score"] = round(sem_score, 1)
            row["confidence"] = round(sem_score, 1)
            row["score"] = round(sem_score, 1)
            by_id[kid] = row

    out = sorted(by_id.values(), key=lambda r: (-float(r.get("score") or 0), str(r.get("kp_id") or "")))
    return out[: max(1, int(limit))]


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
