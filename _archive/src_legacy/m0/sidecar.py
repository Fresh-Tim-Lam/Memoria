"""M0：侧车 .memoria.yaml 读写与 md 扫描"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from .range_locate import resolve_range

SIDECAR_SUFFIX = ".memoria.yaml"


def sidecar_path_for(md_path: str) -> str:
    p = Path(md_path)
    return str(p.with_suffix(SIDECAR_SUFFIX))


def strip_frontmatter(text: str) -> tuple[str, dict | None]:
    if not text.startswith("---"):
        return text, None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return text, None
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return text, None
    body = parts[2].lstrip("\n")
    return body, fm


def load_sidecar(path: str) -> dict | None:
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else None


def save_sidecar(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def collect_md_files(kb_root: str) -> list[str]:
    skip = {".memoria", ".git", ".build", "__pycache__", "node_modules"}
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(kb_root):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
        for name in filenames:
            if name.endswith(".md"):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, kb_root).replace("\\", "/")
                out.append(rel)
    return sorted(out)


def resolve_knowledge_points(body: str, sidecar: dict | None) -> list[dict]:
    lines = body.splitlines()
    kps = (sidecar or {}).get("knowledge_points") or []
    resolved = []
    for kp in kps:
        item = dict(kp)
        rng = kp.get("range") or {}
        start_spec = rng.get("start") or {}
        end_spec = rng.get("end") or {}
        if start_spec.get("snippet") and end_spec.get("snippet"):
            loc = resolve_range(lines, start_spec, end_spec)
            item["range_resolved"] = loc
        else:
            item["range_resolved"] = {"ok": False, "error": "missing_snippet"}
        resolved.append(item)
    return resolved


def propose_ranges_from_headings(body: str) -> list[dict]:
    """标题辅助：为 ## / ### 提议候选 range（未写入侧车，供 UI 确认）。"""
    lines = body.splitlines()
    headings: list[tuple[int, int, str]] = []
    for i, line in enumerate(lines):
        if line.startswith("### "):
            headings.append((i, 3, line.strip()))
        elif line.startswith("## "):
            headings.append((i, 2, line.strip()))

    proposals = []
    for idx, (line_i, depth, title) in enumerate(headings):
        end_i = len(lines) - 1
        for j in range(idx + 1, len(headings)):
            next_i, next_d, _ = headings[j]
            if next_d <= depth:
                end_i = next_i - 1
                break
        end_line = lines[end_i].strip() if end_i >= line_i else title
        proposals.append({
            "name": title.lstrip("#").strip(),
            "range": {
                "start": {"snippet": title, "line_hint": line_i + 1},
                "end": {"snippet": end_line[:80], "line_hint": end_i + 1},
            },
            "proposed": True,
        })
    return proposals
