"""KP metadata 提议：tags / description（M4 · 规则 + Lexical）。"""

from __future__ import annotations

import re
from collections import Counter

from memoria.services.lexical_tokenizer import tokenize

_MD_NOISE = re.compile(r"^#{1,6}\s+|^[-*+]\s+|\[\[.*?\]\]|\$\$?[^$]+\$\$?", re.M)
_SENTENCE_END = re.compile(r"[。！？.!?…]+")
_TAG_DELIM = re.compile(r"[,，、;；|]+")
_MIN_TAG_SUGGEST_SCORE = 12.0
_TRIVIAL_TOKENS = frozenset({
    "的", "了", "是", "在", "与", "和", "或", "及", "等", "为", "之", "其", "这", "那",
    "a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "is", "are",
})


def _meaningful_token_overlap(query_tokens: set[str], tag_tokens: set[str]) -> set[str]:
    return {
        t
        for t in (query_tokens & tag_tokens)
        if len(t) >= 2 and t.lower() not in _TRIVIAL_TOKENS
    }


def _is_valid_tag_label(tag: str) -> bool:
    t = (tag or "").strip()
    if len(t) < 2 or len(t) > 48:
        return False
    if _TAG_DELIM.search(t):
        return False
    meaningful = sum(
        1 for c in t if c.isalnum() or ("\u4e00" <= c <= "\u9fff")
    )
    return meaningful >= max(1, len(t) // 3)


def _expand_tag_vocab(vocab: Counter[str]) -> Counter[str]:
    """将 sidecar 中误写的「func、分段」类复合 tag 拆成独立候选。"""
    out: Counter[str] = Counter()
    for tag, freq in vocab.items():
        raw = str(tag).strip()
        if not raw:
            continue
        parts = [p.strip() for p in _TAG_DELIM.split(raw) if p.strip()]
        if len(parts) > 1:
            for part in parts:
                if _is_valid_tag_label(part):
                    out[part] += freq
        elif _is_valid_tag_label(raw):
            out[raw] += freq
    return out


def _kp_body_excerpt(lines: list[str], kp: dict, *, max_chars: int = 2400) -> str:
    rng = kp.get("range") or {}
    start = int((rng.get("start") or {}).get("line_hint") or 1)
    end = int((rng.get("end") or {}).get("line_hint") or start)
    if start < 1:
        start = 1
    if end < start:
        end = start
    chunk = lines[max(0, start - 1) : end]
    text = "\n".join(chunk)
    text = _MD_NOISE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _kb_tag_vocab(kb_path: str) -> Counter[str]:
    import os

    from memoria.storage.scanner import collect_md_files
    from memoria.storage.sidecar import load_sidecar_for_md

    counts: Counter[str] = Counter()
    for rel in collect_md_files(kb_path):
        full = os.path.join(kb_path, rel)
        sidecar = load_sidecar_for_md(full, kb_path) or {}
        for rec in sidecar.get("knowledge_points") or []:
            if not isinstance(rec, dict):
                continue
            for tag in rec.get("tags") or []:
                t = str(tag).strip()
                if t:
                    counts[t] += 1
    return counts


# --- Tag vocabulary cache (avoids O(N²) when rebuilding aux for many KPs) ---
_KB_TAG_VOCAB_CACHE: dict[str, Counter[str]] = {}


def _cached_tag_vocab(kb_path: str) -> Counter[str]:
    """Return tag vocabulary for *kb_path*, cached per-KB to avoid O(N²) traversal."""
    cached = _KB_TAG_VOCAB_CACHE.get(kb_path)
    if cached is not None:
        return cached
    vocab = _kb_tag_vocab(kb_path)
    _KB_TAG_VOCAB_CACHE[kb_path] = vocab
    return vocab


def clear_tag_vocab_cache(kb_path: str | None = None) -> None:
    """Invalidate tag vocabulary cache. If *kb_path* is None, clear all."""
    if kb_path is None:
        _KB_TAG_VOCAB_CACHE.clear()
    else:
        _KB_TAG_VOCAB_CACHE.pop(kb_path, None)


def suggest_tags(
    *,
    kb_path: str,
    rel_path: str,
    kp_id: str,
    lines: list[str],
    kp: dict,
    limit: int = 8,
) -> dict:
    kid = (kp_id or "").strip()
    if not kb_path or not kid:
        return {"status": "ok", "available": False, "suggestions": [], "kp_id": kid}

    body = _kp_body_excerpt(lines, kp)
    if not body:
        return {"status": "ok", "available": True, "suggestions": [], "kp_id": kid}

    existing = {str(t).strip().lower() for t in (kp.get("tags") or []) if str(t).strip()}
    vocab = _expand_tag_vocab(_cached_tag_vocab(kb_path))
    query_tokens = set(tokenize(body, kb_path=kb_path))

    scored: list[tuple[float, str]] = []
    for tag, freq in vocab.items():
        tl = tag.lower()
        if tl in existing:
            continue
        tag_tokens = set(tokenize(tag, kb_path=kb_path))
        overlap = _meaningful_token_overlap(query_tokens, tag_tokens)
        in_body = tag.lower() in body.lower()
        if not overlap and not in_body:
            continue
        if not overlap and len(tag.strip()) < 4:
            continue
        score = len(overlap) * 10.0 + min(freq, 5) * 2.0
        if in_body:
            score += 8.0
        if score < _MIN_TAG_SUGGEST_SCORE:
            continue
        scored.append((score, tag))

    scored.sort(key=lambda x: (-x[0], x[1].lower()))
    suggestions = [{"tag": t, "score": round(s, 1)} for s, t in scored[: max(1, int(limit))]]
    return {
        "status": "ok",
        "available": True,
        "suggestions": suggestions,
        "kp_id": kid,
        "file": rel_path.replace("\\", "/"),
    }


def suggest_description(
    *,
    kb_path: str | None,
    rel_path: str,
    kp_id: str,
    lines: list[str],
    kp: dict,
    max_len: int = 200,
) -> dict:
    kid = (kp_id or "").strip()
    _ = kb_path
    body = _kp_body_excerpt(lines, kp, max_chars=3000)
    if not body:
        return {
            "status": "ok",
            "available": True,
            "suggested": "",
            "kp_id": kid,
            "file": rel_path.replace("\\", "/"),
        }

    first = body
    m = _SENTENCE_END.search(body)
    if m:
        first = body[: m.end()].strip()
    elif len(body) > max_len:
        first = body[:max_len].rsplit(" ", 1)[0].strip() or body[:max_len]

    first = first[:max_len].strip()
    name = str(kp.get("name") or kid).strip()
    if name and first.startswith(name):
        rest = first[len(name) :].lstrip(" ：:，,")
        if len(rest) >= 8:
            first = rest

    return {
        "status": "ok",
        "available": True,
        "suggested": first,
        "kp_id": kid,
        "file": rel_path.replace("\\", "/"),
    }
