"""知识点 id 全库重命名（M3）：侧车引用 + 正文 wikilink 联动。"""

from __future__ import annotations

import os
import re
from typing import Any

from memoria.services.kp_index import build_kp_index
from memoria.storage.markdown import compose_markdown, strip_frontmatter
from memoria.storage.scanner import collect_md_files
from memoria.storage.sidecar import load_sidecar_for_md, save_sidecar_for_md
from memoria.storage.manifest import touch_manifest_entry
from memoria.storage.sidecar_validate import validate_sidecar


def _normalize_targets(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        s = raw.strip()
        return [s] if s else []
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if isinstance(t, str) and str(t).strip()]
    return []


def replace_link_id_in_markdown(content: str, old_id: str, new_id: str) -> tuple[str, int]:
    """正文 [[oldId]] / [[oldId|text]] 替换为 [[newId|preserved]]。"""
    if not old_id or not new_id or old_id == new_id:
        return content, 0
    pattern = re.compile(
        rf"\[\[{re.escape(old_id)}(#[^\]|]*)?(\|([^\]]*))?\]\]"
    )
    count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        anchor = m.group(1) or ""
        text = m.group(3)
        preserved = text if text is not None and text != "" else old_id
        return f"[[{new_id}{anchor}|{preserved}]]"

    return pattern.sub(repl, content), count


def migrate_sidecar_kp_refs(sidecar: dict, old_id: str, new_id: str) -> int:
    """更新侧车内对 old_id 的引用；若含该 KP 则改 id。返回变更计数。"""
    if not sidecar or not old_id or not new_id or old_id == new_id:
        return 0
    changes = 0

    for kp in sidecar.get("knowledge_points") or []:
        if not isinstance(kp, dict):
            continue
        if str(kp.get("id") or "").strip() == old_id:
            kp["id"] = new_id
            changes += 1

    for edge in sidecar.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        if str(edge.get("source_id") or "").strip() == old_id:
            edge["source_id"] = new_id
            changes += 1
        targets = _normalize_targets(edge.get("targets"))
        if old_id in targets:
            edge["targets"] = [new_id if t == old_id else t for t in targets]
            changes += 1

    for link in sidecar.get("links") or []:
        if not isinstance(link, dict):
            continue
        if str(link.get("source_id") or "").strip() == old_id:
            link["source_id"] = new_id
            changes += 1
        targets = _normalize_targets(link.get("targets"))
        if old_id in targets:
            link["targets"] = [new_id if t == old_id else t for t in targets]
            changes += 1
        te = link.get("target_edges")
        if isinstance(te, dict) and old_id in te:
            te[new_id] = te.pop(old_id)
            changes += 1
        pool = link.get("pool")
        if isinstance(pool, list) and old_id in pool:
            link["pool"] = [new_id if p == old_id else p for p in pool]
            changes += 1

    return changes


def rename_kp_in_kb(kb_path: str, old_id: str, new_id: str) -> dict[str, Any]:
    """全库重命名 KP id：所有侧车 + 所有 md 正文 wikilink。"""
    old_id = (old_id or "").strip()
    new_id = (new_id or "").strip()
    if not old_id:
        return {"status": "error", "message": "原 id 不能为空"}
    if not new_id:
        return {"status": "error", "message": "新 id 不能为空"}
    if old_id == new_id:
        return {"status": "ok", "old_id": old_id, "new_id": new_id, "changed": False}

    index = build_kp_index(kb_path)
    if old_id not in index["by_id"]:
        return {"status": "error", "message": f"知识点不存在：{old_id}"}
    if new_id in index["by_id"]:
        return {"status": "error", "message": f"目标 id 已存在：{new_id}"}

    md_files: list[dict] = []
    sidecar_files: list[str] = []
    md_replacements = 0

    for rel in collect_md_files(kb_path):
        rel_norm = rel.replace("\\", "/")
        full = os.path.join(kb_path, rel)
        with open(full, "r", encoding="utf-8") as f:
            raw = f.read()
        body, fm = strip_frontmatter(raw)
        new_body, n = replace_link_id_in_markdown(body, old_id, new_id)
        if n:
            text = compose_markdown(new_body, fm)
            tmp = full + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, full)
            md_replacements += n
            md_files.append({"path": rel_norm, "replacements": n})
            touch_manifest_entry(kb_path, rel_norm)

    known_ids = set(index["by_id"].keys())
    known_ids.discard(old_id)
    known_ids.add(new_id)

    for rel in collect_md_files(kb_path):
        rel_norm = rel.replace("\\", "/")
        full = os.path.join(kb_path, rel)
        sidecar = load_sidecar_for_md(full, kb_path)
        if not sidecar:
            continue
        changes = migrate_sidecar_kp_refs(sidecar, old_id, new_id)
        if not changes:
            continue
        sidecar["schema_version"] = sidecar.get("schema_version") or 1
        sidecar["file"] = rel_norm
        with open(full, "r", encoding="utf-8") as f:
            raw = f.read()
        body, _fm = strip_frontmatter(raw)
        lines = body.splitlines()
        validation = validate_sidecar(
            sidecar, rel_norm, lines, known_kp_ids=known_ids
        )
        if not validation["ok"]:
            return {
                "status": "error",
                "message": "配置校验失败: "
                + "; ".join(validation["errors"]),
                "path": rel_norm,
                "validation": validation,
            }
        save_sidecar_for_md(full, kb_path, sidecar)
        touch_manifest_entry(kb_path, rel_norm)
        sidecar_files.append(rel_norm)

    return {
        "status": "ok",
        "old_id": old_id,
        "new_id": new_id,
        "changed": bool(md_files or sidecar_files),
        "md_replacements": md_replacements,
        "md_files": md_files,
        "sidecar_files": sidecar_files,
    }
