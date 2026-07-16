"""SearchKernel v1.5a：KP 隐式检索 aux（持久化 + 规则生成）。"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from memoria.services.lexical_tokenizer import tokenize
from memoria.services.suggest_metadata import _kp_body_excerpt, _TRIVIAL_TOKENS, clear_tag_vocab_cache, suggest_description, suggest_tags
from memoria.storage.markdown import strip_frontmatter
from memoria.storage.scanner import collect_md_files
from memoria.storage.sidecar import load_sidecar_for_md

AUX_SCHEMA_VERSION = 1
MODEL_SET_ID = "memoria-v1.5a-rule"

_MD_NOISE = re.compile(r"^#{1,6}\s+|^[-*+]\s+|\[\[.*?\]\]|\$\$?[^$]+\$\$?", re.M)


def search_aux_dir(kb_path: str) -> str:
    return os.path.join(kb_path, ".memoria", "cache", "search_aux")


def search_aux_manifest_path(kb_path: str) -> str:
    return os.path.join(search_aux_dir(kb_path), "manifest.json")


def _kp_aux_path(kb_path: str, kp_id: str) -> str:
    safe = re.sub(r"[^\w\-.]", "_", kp_id)[:120] or "kp"
    return os.path.join(search_aux_dir(kb_path), "kp", f"{safe}.json")


def _fingerprint(*, kp_id: str, name: str, tags: list[str], description: str, body: str) -> str:
    payload = {
        "kp_id": kp_id,
        "name": name,
        "tags": sorted(tags),
        "description": description,
        "body": body[:4000],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _first_sentence(text: str, *, max_len: int = 240) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    m = re.search(r"[。！？.!?…]", text)
    if m:
        text = text[: m.end()].strip()
    if len(text) > max_len:
        cut = text[:max_len]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        text = cut + "…"
    return text


def _key_phrases_from_body(body: str, *, kb_path: str, limit: int = 8) -> list[str]:
    cleaned = _MD_NOISE.sub(" ", body)
    tokens = tokenize(cleaned, kb_path=kb_path)
    counts: Counter[str] = Counter()
    for tok in tokens:
        t = tok.strip()
        if len(t) < 2 or t.lower() in _TRIVIAL_TOKENS:
            continue
        counts[t] += 1
    ranked = [t for t, _ in counts.most_common(limit * 2)]
    out: list[str] = []
    seen: set[str] = set()
    for t in ranked:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
        if len(out) >= limit:
            break
    return out


def _rule_aliases(*, kp_id: str, name: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    name_s = name.strip()
    kid = kp_id.strip()

    def add(val: str) -> None:
        v = val.strip()
        if not v or len(v) < 2:
            return
        key = v.lower()
        if key in seen or key == name_s.lower():
            return
        seen.add(key)
        out.append(v)

    if kid and kid.lower() != name_s.lower():
        add(kid)
    if name_s.isascii() and " " in name_s:
        add(name_s.replace(" ", "-").lower())
    return out[:6]


def _embed_text_block(
    *,
    kp_id: str,
    name: str,
    tags: list[str],
    description: str,
    auto_tags: list[str],
    aliases: list[str],
    key_phrases: list[str],
    summary: str,
    body_head: str,
) -> str:
    parts = [
        kp_id,
        name,
        " ".join(tags),
        description,
        " ".join(auto_tags),
        " ".join(aliases),
        " ".join(key_phrases),
        summary,
        body_head[:800],
    ]
    return " ".join(p for p in parts if p).strip()


def generate_aux_for_kp(
    *,
    kb_path: str,
    rel_path: str,
    kp: dict,
    lines: list[str],
) -> dict[str, Any]:
    kp_id = str(kp.get("id") or "").strip()
    name = str(kp.get("name") or kp_id).strip()
    tags = [str(t).strip() for t in (kp.get("tags") or []) if str(t).strip()]
    description = str(kp.get("description") or "").strip()
    body = _kp_body_excerpt(lines, kp)

    fp = _fingerprint(kp_id=kp_id, name=name, tags=tags, description=description, body=body)

    tag_suggest = suggest_tags(
        kb_path=kb_path,
        rel_path=rel_path,
        kp_id=kp_id,
        lines=lines,
        kp=kp,
        limit=12,
    )
    existing = {t.lower() for t in tags}
    auto_tags: list[str] = []
    for item in tag_suggest.get("suggestions") or []:
        tag = str(item.get("tag") or "").strip()
        if tag and tag.lower() not in existing:
            auto_tags.append(tag)

    desc_suggest = suggest_description(
        kb_path=kb_path,
        rel_path=rel_path,
        kp_id=kp_id,
        lines=lines,
        kp=kp,
    )
    summary = str(desc_suggest.get("suggested") or "").strip()
    if not summary and body:
        summary = _first_sentence(body)

    aliases = _rule_aliases(kp_id=kp_id, name=name)
    key_phrases = _key_phrases_from_body(body, kb_path=kb_path)

    body_head = body[:800]
    embed_text = _embed_text_block(
        kp_id=kp_id,
        name=name,
        tags=tags,
        description=description,
        auto_tags=auto_tags,
        aliases=aliases,
        key_phrases=key_phrases,
        summary=summary,
        body_head=body_head,
    )

    return {
        "schema_version": AUX_SCHEMA_VERSION,
        "kp_id": kp_id,
        "source_fingerprint": fp,
        "model_set_id": MODEL_SET_ID,
        "auto_tags": auto_tags,
        "aliases": aliases,
        "key_phrases": key_phrases,
        "summary_1l": summary,
        "query_hits": [],
        "embed_text": embed_text,
        "generated_by": [
            {"field": "auto_tags", "pipeline": "suggest_tags"},
            {"field": "summary_1l", "pipeline": "suggest_description"},
            {"field": "aliases", "pipeline": "rule"},
            {"field": "key_phrases", "pipeline": "body_tokens"},
        ],
        "promoted": {"auto_tags": [], "aliases": []},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def load_kp_aux(kb_path: str, kp_id: str) -> dict[str, Any] | None:
    path = _kp_aux_path(kb_path, kp_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and str(data.get("kp_id") or "") == kp_id:
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return None


def save_kp_aux(kb_path: str, aux: dict[str, Any]) -> str:
    kp_id = str(aux.get("kp_id") or "").strip()
    if not kp_id:
        raise ValueError("aux missing kp_id")
    base = search_aux_dir(kb_path)
    os.makedirs(os.path.join(base, "kp"), exist_ok=True)
    path = _kp_aux_path(kb_path, kp_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(aux, f, ensure_ascii=False, indent=2)
    return path


def load_all_aux(kb_path: str) -> dict[str, dict[str, Any]]:
    kp_dir = os.path.join(search_aux_dir(kb_path), "kp")
    out: dict[str, dict[str, Any]] = {}
    if not os.path.isdir(kp_dir):
        return out
    for name in os.listdir(kp_dir):
        if not name.endswith(".json"):
            continue
        path = os.path.join(kp_dir, name)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                kid = str(data.get("kp_id") or "").strip()
                if kid:
                    out[kid] = data
        except (OSError, json.JSONDecodeError):
            continue
    return out


def rebuild_search_aux(kb_path: str) -> dict[str, Any]:
    """增量重建全库 aux；返回 manifest 摘要。"""
    # Clear tag vocab cache so stale data isn't used after KB changes
    clear_tag_vocab_cache(kb_path)

    updated = 0
    skipped = 0
    existing = load_all_aux(kb_path)

    for rel in collect_md_files(kb_path):
        rel_norm = rel.replace("\\", "/")
        full = os.path.join(kb_path, rel)
        sidecar = load_sidecar_for_md(full, kb_path) or {}
        lines: list[str] = []
        try:
            with open(full, encoding="utf-8") as f:
                body, _ = strip_frontmatter(f.read())
            lines = body.splitlines()
        except OSError:
            lines = []

        for kp in sidecar.get("knowledge_points") or []:
            if not isinstance(kp, dict):
                continue
            kp_id = str(kp.get("id") or "").strip()
            if not kp_id:
                continue

            name = str(kp.get("name") or kp_id).strip()
            tags = [str(t).strip() for t in (kp.get("tags") or []) if str(t).strip()]
            description = str(kp.get("description") or "").strip()
            body_excerpt = _kp_body_excerpt(lines, kp)
            fp = _fingerprint(
                kp_id=kp_id,
                name=name,
                tags=tags,
                description=description,
                body=body_excerpt,
            )

            prev = existing.get(kp_id)
            if prev and prev.get("source_fingerprint") == fp:
                skipped += 1
                continue

            aux = generate_aux_for_kp(
                kb_path=kb_path,
                rel_path=rel_norm,
                kp=kp,
                lines=lines,
            )
            save_kp_aux(kb_path, aux)
            existing[kp_id] = aux
            updated += 1

    manifest = {
        "schema_version": AUX_SCHEMA_VERSION,
        "model_set_id": MODEL_SET_ID,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "kp_count": len(existing),
        "updated": updated,
        "skipped": skipped,
    }
    os.makedirs(search_aux_dir(kb_path), exist_ok=True)
    with open(search_aux_manifest_path(kb_path), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest


def aux_lexical_fields(aux: dict[str, Any] | None) -> dict[str, Any]:
    """供 lexical_index 合并的隐式字段。"""
    if not aux:
        return {
            "auto_tags": [],
            "aliases": [],
            "key_phrases": [],
            "summary_1l": "",
            "query_hits": [],
        }
    promoted = aux.get("promoted") if isinstance(aux.get("promoted"), dict) else {}
    prom_tags = {str(t).lower() for t in (promoted.get("auto_tags") or [])}
    prom_aliases = {str(a).lower() for a in (promoted.get("aliases") or [])}

    auto_tags = [
        str(t).strip()
        for t in (aux.get("auto_tags") or [])
        if str(t).strip() and str(t).lower() not in prom_tags
    ]
    aliases = [
        str(a).strip()
        for a in (aux.get("aliases") or [])
        if str(a).strip() and str(a).lower() not in prom_aliases
    ]
    return {
        "auto_tags": auto_tags,
        "aliases": aliases,
        "key_phrases": [str(p).strip() for p in (aux.get("key_phrases") or []) if str(p).strip()],
        "summary_1l": str(aux.get("summary_1l") or "").strip(),
        "query_hits": [str(q).strip() for q in (aux.get("query_hits") or []) if str(q).strip()],
    }


def mark_aux_promoted(
    kb_path: str,
    kp_id: str,
    *,
    auto_tags: list[str] | None = None,
    aliases: list[str] | None = None,
) -> None:
    """用户采纳隐式字段后标记 promoted（避免重复提议）。"""
    aux = load_kp_aux(kb_path, kp_id)
    if not aux:
        return
    promoted = aux.get("promoted")
    if not isinstance(promoted, dict):
        promoted = {"auto_tags": [], "aliases": []}
    for field, values in (("auto_tags", auto_tags), ("aliases", aliases)):
        if not values:
            continue
        bucket = promoted.setdefault(field, [])
        if not isinstance(bucket, list):
            bucket = []
            promoted[field] = bucket
        seen = {str(x).lower() for x in bucket}
        for val in values:
            v = str(val).strip()
            if v and v.lower() not in seen:
                bucket.append(v)
                seen.add(v.lower())
    aux["promoted"] = promoted
    save_kp_aux(kb_path, aux)
