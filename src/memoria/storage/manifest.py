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
CODE_MANIFEST_SIDECAR_ADDED = "manifest_sidecar_added"
CODE_MANIFEST_SIDECAR_REMOVED = "manifest_sidecar_removed"
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


# M6a：延迟落盘的 manifest 单条更新（kb_path → {rel: True}）。
# 热路径（正文保存）只入 pending；读盘时叠加 pending（内存可见，不落盘）；
# 任一 manifest 写操作或 durable_flush 屏障会把 pending 一并落盘后清空。
_PENDING_TOUCH: dict[str, dict[str, bool]] = {}


def defer_manifest_touch(kb_path: str, rel_md: str) -> None:
    """登记一条延迟的 manifest 更新（正文保存等高频写路径使用）。"""
    _PENDING_TOUCH.setdefault(str(kb_path), {})[_norm(rel_md)] = True


def _apply_pending(entries: dict[str, dict], kb_path: str) -> None:
    for rel in _PENDING_TOUCH.get(str(kb_path), {}):
        md_full = Path(kb_path) / rel
        if md_full.is_file():
            try:
                entries[rel] = entry_for_md(kb_path, rel)
            except FileNotFoundError:
                entries.pop(rel, None)
        else:
            entries.pop(rel, None)


def clear_pending_touches(kb_path: str) -> None:
    _PENDING_TOUCH.pop(str(kb_path), None)


def flush_manifest_deferred(kb_path: str) -> int:
    """把该 KB 的 pending manifest 更新批量落盘（屏障/显式 flush 调用）。"""
    pending = _PENDING_TOUCH.get(str(kb_path))
    if not pending:
        return 0
    update_manifest_entries(kb_path, sorted(pending))
    return len(pending)


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
    # M6a：叠加 pending（读侧一致，不在此落盘）
    if str(kb_path) in _PENDING_TOUCH:
        _apply_pending(by_path, str(kb_path))
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


def update_manifest_entries(kb_path: str, rel_mds: list[str]) -> None:
    """批量更新多条 manifest 记录（M6a：一次 load + 一次落盘，避免逐条全量重写）。

    每条按「文件当前存在则重算 entry，不存在则移除」处理；与 touch_manifest_entry 单条语义一致。
    """
    if not rel_mds:
        return
    manifest = load_manifest(kb_path)
    entries = (manifest or {}).get("files_by_path") or {}
    if not manifest:
        entries = build_manifest_entries(kb_path)
    for rel in rel_mds:
        rel = _norm(rel)
        md_full = Path(kb_path) / rel
        if md_full.is_file():
            entries[rel] = entry_for_md(kb_path, rel)
        else:
            entries.pop(rel, None)
    save_manifest(kb_path, entries)
    # 整份已由叠加后的 entries 重写，pending 一并落盘，清空
    clear_pending_touches(kb_path)


def touch_manifest_entry(kb_path: str, rel_md: str) -> None:
    """Memoria 写入侧车/md 后更新单条 manifest 记录。"""
    update_manifest_entries(kb_path, [rel_md])


def rebuild_manifest(kb_path: str) -> dict:
    entries = build_manifest_entries(kb_path)
    save_manifest(kb_path, entries)
    return {
        "status": "ok",
        "file_count": len(entries),
        "path": manifest_path(kb_path),
    }


def _issue(code: str, message: str, *, severity: str, path: str, params: dict | None = None) -> dict:
    return {"code": code, "message": message, "severity": severity, "paths": [path], **({"params": params} if params else {})}


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
        1
        for w in kept
        if w.get("code")
        in (CODE_MANIFEST_SIDECAR_CHANGED, CODE_MANIFEST_SIDECAR_ADDED, CODE_MANIFEST_SIDECAR_REMOVED)
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
                params={"path": path},
            )
        )

    for path in sorted(set(current) - set(stored_entries)):
        warnings.append(
            _issue(
                CODE_MANIFEST_ADDED,
                f"发现新文档（尚未记入文件清单）：{path}",
                severity="warning",
                path=path,
                params={"path": path},
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
                    params={"path": path},
                )
            )
        old_sc = old.get("sidecar_sha256")
        new_sc = new.get("sidecar_sha256")
        if old_sc != new_sc:
            if old_sc is None and new_sc is not None:
                code = CODE_MANIFEST_SIDECAR_ADDED
                msg = f"已新增元数据配置：{path}"
            elif old_sc is not None and new_sc is None:
                code = CODE_MANIFEST_SIDECAR_REMOVED
                msg = f"元数据配置已删除：{path}"
            else:
                code = CODE_MANIFEST_SIDECAR_CHANGED
                msg = f"配置内容已在外部被修改：{path}"
            warnings.append(
                _issue(
                    code,
                    msg,
                    severity="warning",
                    path=path,
                    params={"path": path},
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
                1
                for w in warnings
                if w["code"]
                in (CODE_MANIFEST_SIDECAR_CHANGED, CODE_MANIFEST_SIDECAR_ADDED, CODE_MANIFEST_SIDECAR_REMOVED)
            ),
        },
        "manifest_path": manifest_path(kb_path),
        "file_count": len(current),
    }
