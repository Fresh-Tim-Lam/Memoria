"""知识库全局 KP 索引（M1 链接跳转）。"""

from __future__ import annotations

import os
from dataclasses import dataclass

from memoria.services.kp_resolver import resolve_knowledge_points
from memoria.storage.markdown import strip_frontmatter
from memoria.storage.scanner import collect_md_files
from memoria.storage.sidecar import load_sidecar_for_md


@dataclass(frozen=True)
class KpIndexEntry:
    file: str
    kp_id: str
    name: str
    range_ok: bool
    start_line: int | None
    end_line: int | None


def _read_body(kb_path: str, rel: str) -> tuple[str, list[str]]:
    full = os.path.join(kb_path, rel)
    with open(full, "r", encoding="utf-8") as f:
        raw = f.read()
    body, _ = strip_frontmatter(raw)
    lines = body.splitlines()
    return body, lines


def build_kp_index(kb_path: str) -> dict:
    """构建 { by_id, file_stems, entries }。"""
    by_id: dict[str, list[KpIndexEntry]] = {}
    file_stems: dict[str, str] = {}
    entries: list[KpIndexEntry] = []

    for rel in collect_md_files(kb_path):
        rel_norm = rel.replace("\\", "/")
        stem = os.path.splitext(os.path.basename(rel_norm))[0]
        file_stems[stem] = rel_norm

        full = os.path.join(kb_path, rel)
        body, _ = _read_body(kb_path, rel)
        sidecar = load_sidecar_for_md(full, kb_path)
        kps = resolve_knowledge_points(body, sidecar)

        for kp in kps:
            kp_id = kp.get("id") or ""
            if not kp_id:
                continue
            rr = kp.get("range_resolved") or {}
            entry = KpIndexEntry(
                file=rel_norm,
                kp_id=kp_id,
                name=kp.get("name") or kp_id,
                range_ok=bool(rr.get("ok")),
                start_line=rr.get("start_line") if rr.get("ok") else None,
                end_line=rr.get("end_line") if rr.get("ok") else None,
            )
            entries.append(entry)
            by_id.setdefault(kp_id, []).append(entry)

    return {
        "by_id": by_id,
        "file_stems": file_stems,
        "entries": entries,
    }


def entry_to_dict(entry: KpIndexEntry) -> dict:
    return {
        "file": entry.file,
        "kp_id": entry.kp_id,
        "name": entry.name,
        "range_ok": entry.range_ok,
        "start_line": entry.start_line,
        "end_line": entry.end_line,
    }
