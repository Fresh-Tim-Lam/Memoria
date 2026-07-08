"""正文定位搜索：在 md 行内 substring 匹配（非 KP 索引层）。"""

from __future__ import annotations

import os

from memoria.storage.markdown import strip_frontmatter
from memoria.storage.scanner import collect_md_files
from memoria.storage.ui_settings import load_ui_settings


def is_body_locate_enabled() -> bool:
    raw = load_ui_settings().get("search")
    if not isinstance(raw, dict):
        return False
    return bool(raw.get("body_locate_enabled"))


def search_body_locate(
    query: str,
    *,
    kb_path: str,
    scope: str = "kb",
    rel_path: str | None = None,
    limit: int = 15,
) -> list[dict]:
    """扫描 md 正文行，返回定位命中（kind=body-locate）。"""
    q = (query or "").strip()
    if not q or not kb_path:
        return []
    q_lower = q.lower()
    if len(q_lower) < 2:
        return []

    scope_norm = (scope or "kb").lower()
    file_norm = str(rel_path or "").replace("\\", "/")
    out: list[dict] = []

    for rel in collect_md_files(kb_path):
        rel_norm = rel.replace("\\", "/")
        if scope_norm == "file" and file_norm and rel_norm != file_norm:
            continue
        full = os.path.join(kb_path, rel_norm)
        try:
            with open(full, "r", encoding="utf-8") as f:
                raw = f.read()
            body, _ = strip_frontmatter(raw)
            lines = body.splitlines()
        except OSError:
            continue

        for i, line in enumerate(lines, start=1):
            if q_lower not in line.lower():
                continue
            snippet = line.strip()
            if len(snippet) > 120:
                idx = line.lower().find(q_lower)
                if idx < 0:
                    idx = 0
                start = max(0, idx - 24)
                snippet = line[start : start + 120].strip()
            out.append({
                "kind": "body-locate",
                "file": rel_norm,
                "line": i,
                "label": snippet or f"第 {i} 行",
                "snippet": snippet,
                "score": 10.0,
                "sources": ["body-locate"],
            })
            if len(out) >= max(1, int(limit)):
                return out

    return out
