"""从侧车 edges[] 与 KP 索引收集图谱数据（M2 GraphEngine 输入）。"""

from __future__ import annotations

import os

from memoria.graph.edge_derivation import (
    build_target_kp_resolver,
    dedupe_graph_edges,
    derive_file_graph_edges,
)
from memoria.services.kp_index import build_kp_index, entry_to_dict
from memoria.storage.markdown import strip_frontmatter
from memoria.storage.scanner import collect_md_files
from memoria.storage.sidecar import load_sidecar_for_md


def _build_kp_meta(kb_path: str) -> dict[str, dict]:
    meta: dict[str, dict] = {}
    for rel in collect_md_files(kb_path):
        full = os.path.join(kb_path, rel)
        sidecar = load_sidecar_for_md(full, kb_path) or {}
        for kp in sidecar.get("knowledge_points") or []:
            if not isinstance(kp, dict):
                continue
            kid = (kp.get("id") or "").strip()
            if not kid:
                continue
            meta[kid] = {
                "name": (kp.get("name") or kid).strip(),
                "description": (kp.get("description") or "").strip(),
            }
    return meta


def _read_body(kb_path: str, rel: str) -> str:
    full = os.path.join(kb_path, rel)
    with open(full, "r", encoding="utf-8") as f:
        raw = f.read()
    body, _ = strip_frontmatter(raw)
    return body


def collect_graph_data(kb_path: str) -> dict:
    """返回 { status, nodes[], edges[] }。

    边仅由两类来源构建（不读侧车 edges[]、不扫描正文 wikilink）：
    - range 几何包含 → contain
    - sidecar links[]（含 instances，行落在 KP range 内）→ reference / extend
    """
    index = build_kp_index(kb_path)
    kp_meta = _build_kp_meta(kb_path)
    nodes: list[dict] = []
    seen_node: set[str] = set()
    for kp_id, group in index["by_id"].items():
        if kp_id in seen_node:
            continue
        seen_node.add(kp_id)
        preferred = next((e for e in group if e.range_ok), group[0])
        meta = kp_meta.get(kp_id, {})
        nodes.append(
            {
                "id": kp_id,
                "name": meta.get("name") or preferred.name or kp_id,
                "label": meta.get("name") or preferred.name or kp_id,
                "description": meta.get("description") or "",
                "file": preferred.file,
                **entry_to_dict(preferred),
            }
        )

    resolve_target_kp = build_target_kp_resolver(kb_path)
    all_edges: list[dict] = []
    for rel in collect_md_files(kb_path):
        rel_norm = rel.replace("\\", "/")
        full = os.path.join(kb_path, rel)
        sidecar = load_sidecar_for_md(full, kb_path) or {}
        body = _read_body(kb_path, rel)
        contain, link_edges, sidecar_edges = derive_file_graph_edges(
            rel_norm, body, sidecar, resolve_target_kp=resolve_target_kp
        )
        for e in contain + link_edges + sidecar_edges:
            e.setdefault("file", rel_norm)
        all_edges.extend(contain + link_edges + sidecar_edges)

    return {"status": "ok", "nodes": nodes, "edges": dedupe_graph_edges(all_edges)}
