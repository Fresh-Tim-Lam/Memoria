"""知识库待确认提议：跨会话持久化（M3 P2）。"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

from memoria.storage.atomic_yaml import atomic_write_yaml
from memoria.storage.constants import MEMORIA_DIR, PENDING_FILENAME
from memoria.storage.markdown import strip_frontmatter
from memoria.storage.scanner import collect_md_files
from memoria.storage.sidecar import load_sidecar_for_md

PENDING_SCHEMA_VERSION = 1


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def pending_path(kb_path: str) -> str:
    return str(Path(kb_path) / MEMORIA_DIR / PENDING_FILENAME)


def load_pending(kb_path: str) -> dict | None:
    path = pending_path(kb_path)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        return None
    items = data.get("items")
    if not isinstance(items, list):
        data["items"] = []
    return data


def save_pending(kb_path: str, data: dict) -> None:
    Path(kb_path, MEMORIA_DIR).mkdir(parents=True, exist_ok=True)
    atomic_write_yaml(pending_path(kb_path), data)


def make_pending_id(rel_file: str, proposal: dict) -> str:
    r = proposal.get("range") or {}
    start = r.get("start", {}).get("line_hint") or 0
    kind = proposal.get("strategy") or "heading"
    name = (proposal.get("name") or "").strip()
    key = f"{_norm(rel_file)}|{kind}|{name}|{start}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def is_proposal_covered(proposal: dict, kps: list[dict]) -> bool:
    name = (proposal.get("name") or "").strip()
    cid = (proposal.get("concept_id") or "").strip()
    for kp in kps:
        kid = (kp.get("id") or "").strip()
        kn = (kp.get("name") or "").strip()
        if name and (kid == name or kn == name):
            return True
        if cid and kid == cid:
            return True
    return False


def _proposal_to_item(rel_file: str, proposal: dict, kind: str) -> dict:
    pid = make_pending_id(rel_file, {**proposal, "strategy": kind})
    item: dict = {
        "pending_id": pid,
        "file": _norm(rel_file),
        "kind": kind,
        "name": proposal.get("name") or "",
        "range": proposal.get("range") or {},
        "status": "pending",
    }
    if proposal.get("concept_id"):
        item["concept_id"] = proposal["concept_id"]
    return item


def pending_item_to_proposal(item: dict) -> dict:
    proposal = {
        "name": item.get("name") or "",
        "strategy": item.get("kind") or "heading",
        "range": item.get("range") or {},
        "proposed": True,
        "pending_id": item.get("pending_id"),
    }
    if item.get("concept_id"):
        proposal["concept_id"] = item["concept_id"]
    return proposal


def proposals_for_file(
    kb_path: str, rel_path: str
) -> tuple[list[dict], list[dict], list[dict]]:
    rel = _norm(rel_path)
    data = load_pending(kb_path) or {"items": []}
    heading: list[dict] = []
    mention: list[dict] = []
    definition: list[dict] = []
    for item in data.get("items") or []:
        if not isinstance(item, dict):
            continue
        if item.get("status") == "dismissed":
            continue
        if _norm(item.get("file") or "") != rel:
            continue
        proposal = pending_item_to_proposal(item)
        kind = item.get("kind") or "heading"
        if kind == "mention":
            mention.append(proposal)
        elif kind == "definition":
            definition.append(proposal)
        else:
            heading.append(proposal)
    return heading, mention, definition


def sync_kb_pending(kb_path: str) -> dict:
    from memoria.services.kp_resolver import resolve_knowledge_points
    from memoria.services.range_proposals import propose_all_ranges

    existing = load_pending(kb_path) or {}
    dismissed: dict[str, dict] = {}
    for item in existing.get("items") or []:
        if not isinstance(item, dict):
            continue
        if item.get("status") == "dismissed" and item.get("pending_id"):
            dismissed[item["pending_id"]] = item

    md_files = {_norm(rel) for rel in collect_md_files(kb_path)}
    kept_dismissed = [
        item for item in dismissed.values()
        if _norm(item.get("file") or "") in md_files
    ]
    dismissed_ids = {item["pending_id"] for item in kept_dismissed}

    pending_items: list[dict] = []
    for rel in sorted(md_files):
        full = os.path.join(kb_path, rel)
        if not os.path.isfile(full):
            continue
        with open(full, "r", encoding="utf-8") as f:
            raw = f.read()
        body, fm = strip_frontmatter(raw)
        sidecar = load_sidecar_for_md(full, kb_path)
        kps = resolve_knowledge_points(body, sidecar)
        heading, mention, definition, _ = propose_all_ranges(body, fm)
        for p in heading:
            if is_proposal_covered(p, kps):
                continue
            item = _proposal_to_item(rel, p, "heading")
            if item["pending_id"] in dismissed_ids:
                continue
            pending_items.append(item)
        for p in mention:
            if is_proposal_covered(p, kps):
                continue
            item = _proposal_to_item(rel, p, "mention")
            if item["pending_id"] in dismissed_ids:
                continue
            pending_items.append(item)
        for p in definition:
            if is_proposal_covered(p, kps):
                continue
            item = _proposal_to_item(rel, p, "definition")
            if item["pending_id"] in dismissed_ids:
                continue
            pending_items.append(item)

    now = datetime.now(timezone.utc).isoformat()
    data = {
        "schema_version": PENDING_SCHEMA_VERSION,
        "updated_at": now,
        "items": pending_items + kept_dismissed,
    }
    save_pending(kb_path, data)
    heading_count = sum(1 for i in pending_items if i.get("kind") == "heading")
    mention_count = sum(1 for i in pending_items if i.get("kind") == "mention")
    definition_count = sum(1 for i in pending_items if i.get("kind") == "definition")
    return {
        "pending_count": len(pending_items),
        "heading_count": heading_count,
        "mention_count": mention_count,
        "definition_count": definition_count,
        "dismissed_count": len(kept_dismissed),
    }


def dismiss_pending_item(kb_path: str, pending_id: str) -> bool:
    pending_id = (pending_id or "").strip()
    if not pending_id:
        return False
    data = load_pending(kb_path) or {
        "schema_version": PENDING_SCHEMA_VERSION,
        "items": [],
    }
    items = data.setdefault("items", [])
    for item in items:
        if isinstance(item, dict) and item.get("pending_id") == pending_id:
            item["status"] = "dismissed"
            data["updated_at"] = datetime.now(timezone.utc).isoformat()
            save_pending(kb_path, data)
            return True
    return False


def summarize_kb_pending(kb_path: str) -> dict:
    data = load_pending(kb_path) or {"items": []}
    pending = [
        i for i in (data.get("items") or [])
        if isinstance(i, dict) and i.get("status") != "dismissed"
    ]
    by_file: dict[str, int] = {}
    for item in pending:
        f = _norm(item.get("file") or "")
        by_file[f] = by_file.get(f, 0) + 1
    heading = sum(1 for i in pending if i.get("kind") == "heading")
    mention = sum(1 for i in pending if i.get("kind") == "mention")
    return {
        "total": len(pending),
        "heading": heading,
        "mention": mention,
        "by_file": by_file,
        "items": pending,
    }
