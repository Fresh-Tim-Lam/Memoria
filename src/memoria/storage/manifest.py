"""知识库 manifest：磁盘快照与启动 diff（M3 L4）。"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

from memoria.storage.constants import MEMORIA_DIR
from memoria.storage.scanner import collect_md_files
from memoria.storage.sidecar import save_sidecar, sidecar_path_for

MANIFEST_SCHEMA_VERSION = 1
MANIFEST_FILENAME = "manifest.yaml"

CODE_MANIFEST_ADDED = "manifest_added"
CODE_MANIFEST_REMOVED = "manifest_removed"
CODE_MANIFEST_MD_CHANGED = "manifest_md_changed"
CODE_MANIFEST_SIDECAR_CHANGED = "manifest_sidecar_changed"


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def manifest_path(kb_path: str) -> str:
    return str(Path(kb_path) / MEMORIA_DIR / MANIFEST_FILENAME)


def _stat_file(path: Path) -> dict | None:
    if not path.is_file():
        return None
    raw = path.read_bytes()
    st = path.stat()
    return {
        "mtime": st.st_mtime,
        "size": st.st_size,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def entry_for_md(kb_path: str, rel_md: str) -> dict:
    rel = _norm(rel_md)
    md_full = Path(kb_path) / rel
    sc_full = Path(sidecar_path_for(md_full, kb_path))
    md_stat = _stat_file(md_full)
    if not md_stat:
        raise FileNotFoundError(rel)
    sc_stat = _stat_file(sc_full)
    return {
        "path": rel,
        "md_mtime": md_stat["mtime"],
        "md_size": md_stat["size"],
        "md_sha256": md_stat["sha256"],
        "sidecar_mtime": sc_stat["mtime"] if sc_stat else None,
        "sidecar_sha256": sc_stat["sha256"] if sc_stat else None,
    }


def build_manifest_entries(kb_path: str) -> dict[str, dict]:
    entries: dict[str, dict] = {}
    for rel in collect_md_files(kb_path):
        try:
            entries[_norm(rel)] = entry_for_md(kb_path, rel)
        except FileNotFoundError:
            continue
    return entries


def load_manifest(kb_path: str) -> dict | None:
    path = manifest_path(kb_path)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        return None
    files = data.get("files")
    if not isinstance(files, list):
        return None
    by_path: dict[str, dict] = {}
    for row in files:
        if isinstance(row, dict) and row.get("path"):
            by_path[_norm(str(row["path"]))] = row
    return {
        "schema_version": data.get("schema_version", MANIFEST_SCHEMA_VERSION),
        "updated_at": data.get("updated_at"),
        "files_by_path": by_path,
    }


def save_manifest(kb_path: str, entries: dict[str, dict]) -> None:
    path = Path(manifest_path(kb_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "files": [entries[k] for k in sorted(entries.keys())],
    }
    save_sidecar(path, payload)


def ensure_manifest_baseline(kb_path: str) -> bool:
    """若 manifest 不存在则根据当前磁盘建立基线。返回是否新建。"""
    if load_manifest(kb_path):
        return False
    save_manifest(kb_path, build_manifest_entries(kb_path))
    return True


def touch_manifest_entry(kb_path: str, rel_md: str) -> None:
    """Memoria 写入侧车/md 后更新单条 manifest 记录。"""
    rel = _norm(rel_md)
    manifest = load_manifest(kb_path)
    entries = (manifest or {}).get("files_by_path") or {}
    if not manifest:
        entries = build_manifest_entries(kb_path)
    else:
        md_full = Path(kb_path) / rel
        if md_full.is_file():
            entries[rel] = entry_for_md(kb_path, rel)
        else:
            entries.pop(rel, None)
    save_manifest(kb_path, entries)


def rebuild_manifest(kb_path: str) -> dict:
    entries = build_manifest_entries(kb_path)
    save_manifest(kb_path, entries)
    return {
        "status": "ok",
        "file_count": len(entries),
        "path": manifest_path(kb_path),
    }


def _issue(code: str, message: str, *, severity: str, path: str) -> dict:
    return {"code": code, "message": message, "severity": severity, "paths": [path]}


def filter_manifest_diff_for_path_moves(
    manifest_diff: dict, path_moves: list[dict]
) -> dict:
    """从 manifest diff 中剔除已由 path_moves 解释的增删项，避免与「修复路径」重复提示。"""
    if not path_moves:
        return manifest_diff
    move_from = {_norm(m["from"]) for m in path_moves}
    move_to = {_norm(m["to"]) for m in path_moves}
    kept: list[dict] = []
    for w in manifest_diff.get("warnings") or []:
        code = w.get("code")
        path = _norm((w.get("paths") or [""])[0])
        if code == CODE_MANIFEST_REMOVED and path in move_from:
            continue
        if code == CODE_MANIFEST_ADDED and path in move_to:
            continue
        kept.append(w)
    errors = list(manifest_diff.get("errors") or [])
    summary = dict(manifest_diff.get("summary") or {})
    summary["warning_count"] = len(kept)
    summary["error_count"] = len(errors)
    summary["added_count"] = sum(1 for w in kept if w.get("code") == CODE_MANIFEST_ADDED)
    summary["removed_count"] = sum(
        1 for w in kept if w.get("code") == CODE_MANIFEST_REMOVED
    )
    summary["md_changed_count"] = sum(
        1 for w in kept if w.get("code") == CODE_MANIFEST_MD_CHANGED
    )
    summary["sidecar_changed_count"] = sum(
        1 for w in kept if w.get("code") == CODE_MANIFEST_SIDECAR_CHANGED
    )
    out = dict(manifest_diff)
    out["errors"] = errors
    out["warnings"] = kept
    out["summary"] = summary
    return out


def audit_manifest_diff(kb_path: str) -> dict:
    """对比 manifest 与当前磁盘；首次打开会先建立基线。"""
    created = ensure_manifest_baseline(kb_path)
    if created:
        entries = build_manifest_entries(kb_path)
        return {
            "baseline_created": True,
            "errors": [],
            "warnings": [],
            "summary": {
                "error_count": 0,
                "warning_count": 0,
                "added_count": 0,
                "removed_count": 0,
                "md_changed_count": 0,
                "sidecar_changed_count": 0,
            },
            "manifest_path": manifest_path(kb_path),
            "file_count": len(entries),
        }

    stored = load_manifest(kb_path) or {}
    stored_entries: dict[str, dict] = stored.get("files_by_path") or {}
    current = build_manifest_entries(kb_path)

    errors: list[dict] = []
    warnings: list[dict] = []

    for path in sorted(set(stored_entries) - set(current)):
        warnings.append(
            _issue(
                CODE_MANIFEST_REMOVED,
                f"文件清单中的文档已被删除：{path}",
                severity="warning",
                path=path,
            )
        )

    for path in sorted(set(current) - set(stored_entries)):
        warnings.append(
            _issue(
                CODE_MANIFEST_ADDED,
                f"发现新文档（尚未记入文件清单）：{path}",
                severity="warning",
                path=path,
            )
        )

    for path in sorted(set(stored_entries) & set(current)):
        old = stored_entries[path]
        new = current[path]
        if old.get("md_sha256") != new.get("md_sha256"):
            warnings.append(
                _issue(
                    CODE_MANIFEST_MD_CHANGED,
                    f"文档内容已在外部被修改：{path}",
                    severity="warning",
                    path=path,
                )
            )
        old_sc = old.get("sidecar_sha256")
        new_sc = new.get("sidecar_sha256")
        if old_sc != new_sc:
            if old_sc is None and new_sc is not None:
                msg = f"已新增元数据配置：{path}"
            elif old_sc is not None and new_sc is None:
                msg = f"元数据配置已删除：{path}"
            else:
                msg = f"配置内容已在外部被修改：{path}"
            warnings.append(
                _issue(
                    CODE_MANIFEST_SIDECAR_CHANGED,
                    msg,
                    severity="warning",
                    path=path,
                )
            )

    return {
        "baseline_created": False,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "error_count": len(errors),
            "warning_count": len(warnings),
            "added_count": sum(1 for w in warnings if w["code"] == CODE_MANIFEST_ADDED),
            "removed_count": sum(1 for w in warnings if w["code"] == CODE_MANIFEST_REMOVED),
            "md_changed_count": sum(
                1 for w in warnings if w["code"] == CODE_MANIFEST_MD_CHANGED
            ),
            "sidecar_changed_count": sum(
                1 for w in warnings if w["code"] == CODE_MANIFEST_SIDECAR_CHANGED
            ),
        },
        "manifest_path": manifest_path(kb_path),
        "file_count": len(current),
    }
