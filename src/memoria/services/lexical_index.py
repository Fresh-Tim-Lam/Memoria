"""Lexical 倒排索引：KP 元数据 + range 正文 token（M4 v2）。"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone

from memoria.services.lexical_tokenizer import pinyin_compact, tokenize, tokenize_identifier
from memoria.storage.markdown import strip_frontmatter
from memoria.storage.scanner import collect_md_files
from memoria.storage.sidecar import load_sidecar_for_md

SCHEMA_VERSION = 4

WEIGHTS = {
    "id_exact": 100.0,
    "id_prefix": 88.0,
    "name_exact": 85.0,
    "name_contains": 72.0,
    "id_contains": 65.0,
    "tag_exact": 55.0,
    "tag_contains": 48.0,
    "kp_description": 35.0,
    "file_description": 25.0,
    "body_token": 15.0,
    "name_pinyin": 78.0,
    "id_pinyin": 70.0,
    # v1.5 implicit (below user tag / name)
    "auto_tag_exact": 47.0,
    "auto_tag_contains": 41.0,
    "alias_exact": 63.0,
    "alias_contains": 58.0,
    "summary": 26.0,
    "key_phrase": 24.0,
    "query_hit": 32.0,
}

POSTING_FIELD_WEIGHT = {
    "id": WEIGHTS["id_contains"],
    "name": WEIGHTS["name_contains"],
    "tag": WEIGHTS["tag_contains"],
    "kp_description": WEIGHTS["kp_description"],
    "file_description": WEIGHTS["file_description"],
    "body": WEIGHTS["body_token"],
    "pinyin_name": WEIGHTS["name_pinyin"],
    "pinyin_id": WEIGHTS["id_pinyin"],
    "auto_tag": WEIGHTS["auto_tag_contains"],
    "alias": WEIGHTS["alias_contains"],
    "summary": WEIGHTS["summary"],
    "key_phrase": WEIGHTS["key_phrase"],
    "query_hit": WEIGHTS["query_hit"],
}


def lexical_cache_path(kb_path: str) -> str:
    return os.path.join(kb_path, ".memoria", "cache", "lexical", "index.json")


def _norm_path(p: str | None) -> str:
    return str(p or "").replace("\\", "/")


def _kp_body_text(lines: list[str], kp: dict, *, max_chars: int = 2400) -> str:
    rng = kp.get("range") or {}
    start = int((rng.get("start") or {}).get("line_hint") or 1)
    end = int((rng.get("end") or {}).get("line_hint") or start)
    if start < 1:
        start = 1
    if end < start:
        end = start
    chunk = lines[max(0, start - 1) : end]
    return "\n".join(chunk)[:max_chars]


def _add_posting(
    inverted: dict[str, list[dict]],
    seen: set[tuple[str, int, str]],
    token: str,
    rec_idx: int,
    field: str,
) -> None:
    key = (token.lower(), rec_idx, field)
    if not token or key in seen:
        return
    seen.add(key)
    inverted.setdefault(token.lower(), []).append({"r": rec_idx, "f": field})


def _build_inverted(records: list[dict], kb_path: str) -> dict[str, list[dict]]:
    inverted: dict[str, list[dict]] = {}
    seen: set[tuple[str, int, str]] = set()
    for idx, rec in enumerate(records):
        for tok in tokenize_identifier(str(rec.get("kp_id") or "")):
            _add_posting(inverted, seen, tok, idx, "id")
        for tok in tokenize(str(rec.get("name") or ""), kb_path=kb_path):
            _add_posting(inverted, seen, tok, idx, "name")
        py_name = pinyin_compact(str(rec.get("name") or ""))
        if py_name:
            _add_posting(inverted, seen, py_name, idx, "pinyin_name")
        py_id = pinyin_compact(str(rec.get("kp_id") or ""))
        if py_id:
            _add_posting(inverted, seen, py_id, idx, "pinyin_id")
        for tag in rec.get("tags") or []:
            for tok in tokenize(str(tag), kb_path=kb_path):
                _add_posting(inverted, seen, tok, idx, "tag")
        for alias in rec.get("aliases_explicit") or []:
            for tok in tokenize(str(alias), kb_path=kb_path):
                _add_posting(inverted, seen, tok, idx, "alias")
            for tok in tokenize_identifier(str(alias)):
                _add_posting(inverted, seen, tok, idx, "alias")
        for tok in tokenize(str(rec.get("kp_description") or ""), kb_path=kb_path):
            _add_posting(inverted, seen, tok, idx, "kp_description")
        for tok in tokenize(str(rec.get("file_description") or ""), kb_path=kb_path):
            _add_posting(inverted, seen, tok, idx, "file_description")
        for tok in tokenize(str(rec.get("body_excerpt") or ""), kb_path=kb_path):
            _add_posting(inverted, seen, tok, idx, "body")
        for tag in rec.get("auto_tags") or []:
            for tok in tokenize(str(tag), kb_path=kb_path):
                _add_posting(inverted, seen, tok, idx, "auto_tag")
        for alias in rec.get("aliases") or []:
            for tok in tokenize(str(alias), kb_path=kb_path):
                _add_posting(inverted, seen, tok, idx, "alias")
            for tok in tokenize_identifier(str(alias)):
                _add_posting(inverted, seen, tok, idx, "alias")
        for phrase in rec.get("key_phrases") or []:
            for tok in tokenize(str(phrase), kb_path=kb_path):
                _add_posting(inverted, seen, tok, idx, "key_phrase")
        for tok in tokenize(str(rec.get("summary_1l") or ""), kb_path=kb_path):
            _add_posting(inverted, seen, tok, idx, "summary")
        for hit in rec.get("query_hits") or []:
            for tok in tokenize(str(hit), kb_path=kb_path):
                _add_posting(inverted, seen, tok, idx, "query_hit")
    return inverted


def build_lexical_index(kb_path: str) -> dict:
    from memoria.services.search_aux import aux_lexical_fields, load_all_aux, rebuild_search_aux

    try:
        rebuild_search_aux(kb_path)
    except OSError:
        pass
    aux_by_kp = load_all_aux(kb_path)

    records: list[dict] = []
    for rel in collect_md_files(kb_path):
        rel_norm = rel.replace("\\", "/")
        full = os.path.join(kb_path, rel)
        sidecar = load_sidecar_for_md(full, kb_path) or {}
        file_desc = str(sidecar.get("description") or "").strip()
        lines: list[str] = []
        try:
            with open(full, "r", encoding="utf-8") as f:
                raw = f.read()
            body, _ = strip_frontmatter(raw)
            lines = body.splitlines()
        except OSError:
            lines = []

        for kp in sidecar.get("knowledge_points") or []:
            if not isinstance(kp, dict):
                continue
            kp_id = str(kp.get("id") or "").strip()
            if not kp_id:
                continue
            tags = [
                str(t).strip()
                for t in (kp.get("tags") or [])
                if str(t).strip()
            ]
            aliases = [
                str(a).strip()
                for a in (kp.get("aliases") or [])
                if str(a).strip()
            ]
            implicit = aux_lexical_fields(aux_by_kp.get(kp_id))
            records.append({
                "kp_id": kp_id,
                "file": rel_norm,
                "name": str(kp.get("name") or kp_id).strip(),
                "tags": tags,
                "aliases_explicit": aliases,
                "kp_description": str(kp.get("description") or "").strip(),
                "file_description": file_desc,
                "body_excerpt": _kp_body_text(lines, kp),
                **implicit,
            })

    inverted = _build_inverted(records, kb_path)
    return {
        "schema_version": SCHEMA_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "token_count": len(inverted),
        "records": records,
        "inverted": inverted,
    }


def save_lexical_index(kb_path: str, index: dict) -> str:
    path = lexical_cache_path(kb_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    return path


def load_lexical_index(kb_path: str) -> dict | None:
    path = lexical_cache_path(kb_path)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        if int(data.get("schema_version") or 0) != SCHEMA_VERSION:
            return None
        if not isinstance(data.get("inverted"), dict):
            return None
        return data
    except (OSError, json.JSONDecodeError):
        return None


def rebuild_lexical_index(kb_path: str) -> dict:
    index = build_lexical_index(kb_path)
    save_lexical_index(kb_path, index)
    return index


def ensure_lexical_index(kb_path: str) -> dict:
    cached = load_lexical_index(kb_path)
    if cached is not None:
        return cached
    return rebuild_lexical_index(kb_path)


def _score_record(rec: dict, q_lower: str) -> tuple[float, list[str]] | None:
    score = 0.0
    sources: list[str] = []

    kp_id = str(rec.get("kp_id") or "")
    name = str(rec.get("name") or "")
    kid_lower = kp_id.lower()
    name_lower = name.lower()

    if kid_lower == q_lower:
        score = max(score, WEIGHTS["id_exact"])
        sources.append("id-exact")
    if kid_lower.startswith(q_lower) and q_lower:
        score = max(score, WEIGHTS["id_prefix"])
        sources.append("id-prefix")
    if name_lower == q_lower:
        score = max(score, WEIGHTS["name_exact"])
        sources.append("name-exact")
    if q_lower and q_lower in name_lower:
        score = max(score, WEIGHTS["name_contains"])
        sources.append("name-fuzzy")
    if q_lower and q_lower in kid_lower:
        score = max(score, WEIGHTS["id_contains"])
        sources.append("id-fuzzy")

    for tag in rec.get("tags") or []:
        tl = str(tag).lower()
        if tl == q_lower:
            score = max(score, WEIGHTS["tag_exact"])
            sources.append("tag-exact")
        elif q_lower and q_lower in tl:
            score = max(score, WEIGHTS["tag_contains"])
            sources.append("tag-fuzzy")

    for alias in rec.get("aliases_explicit") or []:
        al = str(alias).lower()
        if al == q_lower:
            score = max(score, WEIGHTS["alias_exact"])
            sources.append("alias-explicit-exact")
        elif q_lower and q_lower in al:
            score = max(score, WEIGHTS["alias_contains"])
            sources.append("alias-explicit-fuzzy")

    kp_desc = str(rec.get("kp_description") or "").lower()
    if q_lower and q_lower in kp_desc:
        score = max(score, WEIGHTS["kp_description"])
        sources.append("kp-description")

    file_desc = str(rec.get("file_description") or "").lower()
    if q_lower and q_lower in file_desc:
        score = max(score, WEIGHTS["file_description"])
        sources.append("file-description")

    body = str(rec.get("body_excerpt") or "").lower()
    if q_lower and q_lower in body:
        score = max(score, WEIGHTS["body_token"])
        sources.append("body-fuzzy")

    for tag in rec.get("auto_tags") or []:
        tl = str(tag).lower()
        if tl == q_lower:
            score = max(score, WEIGHTS["auto_tag_exact"])
            sources.append("auto-tag-exact")
        elif q_lower and q_lower in tl:
            score = max(score, WEIGHTS["auto_tag_contains"])
            sources.append("auto-tag-fuzzy")

    for alias in rec.get("aliases") or []:
        al = str(alias).lower()
        if al == q_lower:
            score = max(score, WEIGHTS["alias_exact"])
            sources.append("alias-exact")
        elif q_lower and q_lower in al:
            score = max(score, WEIGHTS["alias_contains"])
            sources.append("alias-fuzzy")

    summary = str(rec.get("summary_1l") or "").lower()
    if q_lower and q_lower in summary:
        score = max(score, WEIGHTS["summary"])
        sources.append("summary-fuzzy")

    for phrase in rec.get("key_phrases") or []:
        pl = str(phrase).lower()
        if q_lower and (q_lower == pl or q_lower in pl):
            score = max(score, WEIGHTS["key_phrase"])
            sources.append("key-phrase-fuzzy")
            break

    for hit in rec.get("query_hits") or []:
        hl = str(hit).lower()
        if q_lower and q_lower in hl:
            score = max(score, WEIGHTS["query_hit"])
            sources.append("query-hit-fuzzy")
            break

    py_q = pinyin_compact(q_lower)
    if py_q:
        py_name = pinyin_compact(name)
        py_id = pinyin_compact(kp_id)
        if py_name and py_q == py_name:
            score = max(score, WEIGHTS["name_pinyin"])
            sources.append("name-pinyin")
        elif py_name and len(py_q) >= 2 and py_q in py_name:
            score = max(score, WEIGHTS["name_pinyin"] * 0.85)
            sources.append("name-pinyin")
        if py_id and py_q == py_id:
            score = max(score, WEIGHTS["id_pinyin"])
            sources.append("id-pinyin")

    if score <= 0 and len(q_lower) >= 3:
        ratio = _edit_ratio(q_lower, name_lower)
        if ratio >= 0.72:
            score = WEIGHTS["name_contains"] * ratio
            sources.append("name-edit")
        else:
            ratio_id = _edit_ratio(q_lower, kid_lower)
            if ratio_id >= 0.72:
                score = WEIGHTS["id_contains"] * ratio_id
                sources.append("id-edit")

    if score <= 0:
        return None
    return score, list(dict.fromkeys(sources))


def _token_posting_score(
    inverted: dict[str, list[dict]],
    query_tokens: list[str],
) -> dict[int, tuple[float, list[str]]]:
    acc: dict[int, float] = defaultdict(float)
    sources: dict[int, list[str]] = defaultdict(list)
    for tok in query_tokens:
        tl = tok.lower()
        for post in inverted.get(tl) or []:
            idx = int(post["r"])
            field = str(post.get("f") or "body")
            w = POSTING_FIELD_WEIGHT.get(field, WEIGHTS["body_token"])
            acc[idx] += w
            src = f"token-{field}"
            if src not in sources[idx]:
                sources[idx].append(src)
    return {i: (acc[i], sources[i]) for i in acc}


def _edit_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if len(a) > len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(ins, delete, sub))
        prev = cur
    dist = prev[-1]
    return 1.0 - dist / max(len(a), len(b))


def search_lexical(
    query: str,
    *,
    kb_path: str,
    scope: str = "kb",
    rel_path: str | None = None,
    limit: int = 20,
) -> dict:
    q = (query or "").strip()
    if not kb_path:
        return {
            "status": "error",
            "message": "未打开知识库",
            "available": False,
            "query": q,
            "results": [],
        }
    if not q:
        return {
            "status": "ok",
            "available": True,
            "query": q,
            "scope": scope,
            "results": [],
        }

    index = ensure_lexical_index(kb_path)
    records = index.get("records") or []
    inverted = index.get("inverted") or {}
    q_lower = q.lower()
    scope_norm = (scope or "kb").lower()
    file_filter = _norm_path(rel_path) if scope_norm == "file" else None

    query_tokens = tokenize(q, kb_path=kb_path)
    if q_lower not in query_tokens:
        query_tokens.append(q_lower)
    py_q = pinyin_compact(q)
    if py_q and py_q not in query_tokens:
        query_tokens.append(py_q)

    token_scores = _token_posting_score(inverted, query_tokens)
    candidate_indices: set[int] = set(token_scores.keys())

    if not candidate_indices:
        candidate_indices = set(range(len(records)))

    scored: list[tuple[float, str, dict]] = []
    for idx in candidate_indices:
        if idx < 0 or idx >= len(records):
            continue
        rec = records[idx]
        if not isinstance(rec, dict):
            continue
        if file_filter and _norm_path(rec.get("file")) != file_filter:
            continue

        score = 0.0
        sources: list[str] = []
        substr_hit = _score_record(rec, q_lower)
        if substr_hit:
            score, sources = substr_hit
        if idx in token_scores:
            ts, tsrc = token_scores[idx]
            score = max(score, ts)
            for s in tsrc:
                if s not in sources:
                    sources.append(s)
        if score <= 0:
            continue
        scored.append((score, str(rec.get("kp_id") or ""), {**rec, "score": score, "sources": sources}))

    scored.sort(key=lambda x: (-x[0], x[1]))
    results = []
    for _, _, item in scored[: max(1, int(limit))]:
        lex = round(float(item["score"]), 1)
        results.append({
            "kp_id": item["kp_id"],
            "id": item["kp_id"],
            "label": item.get("name") or item["kp_id"],
            "name": item.get("name") or item["kp_id"],
            "file": item.get("file") or "",
            "score": lex,
            "lexical_score": lex,
            "sources": item.get("sources") or [],
        })

    return {
        "status": "ok",
        "available": True,
        "query": q,
        "scope": scope_norm,
        "results": results,
        "index_records": index.get("record_count", 0),
        "index_tokens": index.get("token_count", 0),
    }
