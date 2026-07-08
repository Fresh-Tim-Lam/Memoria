"""文件/文件夹 rename/move 的路径级联（M3 §6.4）。"""

from __future__ import annotations

import os
from pathlib import Path

from memoria.storage.constants import MEMORIA_DIR
from memoria.storage.manifest import (
    audit_manifest_diff,
    build_manifest_entries,
    load_manifest,
    rebuild_manifest,
    save_manifest,
)
from memoria.storage.scanner import collect_md_files
from memoria.storage.sidecar import (
    collect_sidecar_md_rels,
    load_sidecar,
    save_sidecar,
    sidecar_path_for,
)

CODE_PATH_MOVE = "path_move_detected"
CODE_PATH_DRIFT = "sidecar_path_drift"


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def _move_entry(stored: dict[str, dict], old: str, new: str) -> None:
    row = stored.pop(old, None)
    if row:
        row = dict(row)
        row["path"] = new
        stored[new] = row


def detect_path_moves(kb_path: str) -> list[dict]:
    """根据 manifest 增删 + 内容 hash 推断 rename/move。"""
    audit_manifest_diff(kb_path)
    stored = load_manifest(kb_path) or {}
    stored_entries: dict[str, dict] = dict(stored.get("files_by_path") or {})
    current = build_manifest_entries(kb_path)

    removed = sorted(set(stored_entries) - set(current))
    added = sorted(set(current) - set(stored_entries))
    used_added: set[str] = set()
    moves: list[dict] = []

    for old in removed:
        old_hash = stored_entries[old].get("md_sha256")
        if not old_hash:
            continue
        match = None
        for new in added:
            if new in used_added:
                continue
            if current[new].get("md_sha256") == old_hash:
                match = new
                break
        if match:
            used_added.add(match)
            moves.append({
                "from": old,
                "to": match,
                "kind": "md_sha256",
                "code": CODE_PATH_MOVE,
                "severity": "error",
            })

    md_rels = {_norm(p) for p in collect_md_files(kb_path)}
    for sc_rel in collect_sidecar_md_rels(kb_path):
        if sc_rel not in md_rels:
            continue
        sc_path = sidecar_path_for(Path(kb_path) / sc_rel, kb_path)
        data = load_sidecar(sc_path)
        if not data:
            continue
        declared = _norm(str(data.get("file") or ""))
        if declared and declared != sc_rel:
            key = f"{declared}->{sc_rel}"
            if any(f"{m['from']}->{m['to']}" == key for m in moves):
                continue
            moves.append({
                "from": declared,
                "to": sc_rel,
                "kind": "sidecar_drift",
                "code": CODE_PATH_DRIFT,
                "severity": "error",
            })

    return moves


def _relocate_sidecar_file(kb_path: str, old_rel: str, new_rel: str) -> bool:
    kb = Path(kb_path)
    old_sc = Path(sidecar_path_for(kb / old_rel, kb_path))
    new_sc = Path(sidecar_path_for(kb / new_rel, kb_path))
    if not old_sc.is_file():
        return False
    if old_sc.resolve() == new_sc.resolve():
        return True
    new_sc.parent.mkdir(parents=True, exist_ok=True)
    if new_sc.is_file():
        new_sc.unlink()
    old_sc.replace(new_sc)
    return True


def _update_sidecar_file_field(kb_path: str, new_rel: str) -> bool:
    new_rel = _norm(new_rel)
    sc_path = sidecar_path_for(Path(kb_path) / new_rel, kb_path)
    data = load_sidecar(sc_path)
    if not data:
        return False
    if _norm(str(data.get("file") or "")) == new_rel:
        return False
    updated = dict(data)
    updated["file"] = new_rel
    save_sidecar(sc_path, updated)
    return True


def _update_pending_paths(kb_path: str, old_rel: str, new_rel: str) -> int:
    from memoria.storage.pending import load_pending, save_pending

    old_rel = _norm(old_rel)
    new_rel = _norm(new_rel)
    data = load_pending(kb_path)
    if not data:
        return 0
    changed = 0
    for item in data.get("items") or []:
        if not isinstance(item, dict):
            continue
        if _norm(str(item.get("file") or "")) == old_rel:
            item["file"] = new_rel
            changed += 1
    if changed:
        save_pending(kb_path, data)
    return changed


def apply_path_move(kb_path: str, old_rel: str, new_rel: str) -> dict:
    """单条路径级联：侧车镜像移动 + file: 字段 + pending。"""
    old_rel = _norm(old_rel)
    new_rel = _norm(new_rel)
    if not old_rel or not new_rel or old_rel == new_rel:
        return {"status": "error", "message": "路径无效"}

    new_md = Path(kb_path) / new_rel
    if not new_md.is_file():
        return {"status": "error", "message": f"目标文档不存在：{new_rel}"}

    sidecar_moved = _relocate_sidecar_file(kb_path, old_rel, new_rel)
    sidecar_updated = _update_sidecar_file_field(kb_path, new_rel)
    pending_updated = _update_pending_paths(kb_path, old_rel, new_rel)

    manifest = load_manifest(kb_path) or {}
    entries: dict[str, dict] = dict(manifest.get("files_by_path") or {})
    if old_rel in entries or new_rel not in entries:
        _move_entry(entries, old_rel, new_rel)
        if new_rel not in entries:
            from memoria.storage.manifest import entry_for_md

            entries[new_rel] = entry_for_md(kb_path, new_rel)
        save_manifest(kb_path, entries)

    return {
        "status": "ok",
        "from": old_rel,
        "to": new_rel,
        "sidecar_moved": sidecar_moved,
        "sidecar_updated": sidecar_updated,
        "pending_updated": pending_updated,
    }


def reconcile_path_cascade(kb_path: str, *, apply: bool = False) -> dict:
    """检测并可选应用路径级联修复。"""
    if not os.path.isdir(kb_path):
        return {"status": "error", "message": f"目录不存在: {kb_path}"}

    moves = detect_path_moves(kb_path)
    if not apply:
        return {
            "status": "ok",
            "dry_run": True,
            "move_count": len(moves),
            "moves": moves,
        }

    applied: list[dict] = []
    errors: list[dict] = []
    for move in moves:
        result = apply_path_move(kb_path, move["from"], move["to"])
        if result.get("status") == "ok":
            applied.append({**move, **result})
        else:
            errors.append({**move, "error": result.get("message", "失败")})

    rebuild_manifest(kb_path)
    return {
        "status": "ok" if not errors else "partial",
        "dry_run": False,
        "move_count": len(moves),
        "applied_count": len(applied),
        "applied": applied,
        "errors": errors,
        "moves": moves,
    }
