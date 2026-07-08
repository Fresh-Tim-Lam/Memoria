"""知识库构建：从正文 wikilink 同步 sidecar links[]，并输出图谱产物。"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from memoria.graph.collector import collect_graph_data
from memoria.graph.edge_derivation import (
    build_target_kp_resolver,
    kp_ranges_from_resolved,
    line_in_any_kp,
    minimal_kps_for_line,
    sources_for_link_instance,
)
from memoria.graph.edge_types import EDGE_EXTEND, EDGE_REFERENCE, is_wikilink_edge_type_fragment, normalize_link_edge_type
from memoria.graph.link_audit import audit_kb_graph_links
from memoria.services.kp_resolver import resolve_knowledge_points
from memoria.services.link_md import strip_known_wikilink_edge_hints
from memoria.services.link_resolver import scan_wikilinks
from memoria.services.link_text_search import scan_link_text_matches
from memoria.storage.constants import MEMORIA_DIR, SIDECAR_SCHEMA_VERSION
from memoria.storage.markdown import compose_markdown, strip_frontmatter
from memoria.storage.scanner import collect_md_files
from memoria.storage.sidecar import load_sidecar_for_md, save_sidecar_for_md
from memoria.storage.sidecar_validate import validate_sidecar


def _line_from_offset(body: str, start: int) -> int:
    return (body[:start].count("\n") + 1) if body else 1


def _instance_lines(link: dict) -> list[int]:
    out: list[int] = []
    for inst in link.get("instances") or []:
        if isinstance(inst, dict) and inst.get("line") is not None:
            out.append(int(inst["line"]))
    return out


def _has_instance(link: dict, line: int) -> bool:
    return line in _instance_lines(link)


def _add_instance(link: dict, line: int) -> bool:
    if _has_instance(link, line):
        return False
    link.setdefault("instances", []).append({"line": line, "wrapped": True})
    return True


def _wikilink_anchor(wl: dict) -> str:
    return (wl.get("target_id") or "").strip()


def _find_link_index(links: list, anchor: str, line: int) -> int | None:
    hit_idx: int | None = None
    for i, ln in enumerate(links):
        if not isinstance(ln, dict):
            continue
        if str(ln.get("anchor_text") or "").strip() != anchor:
            continue
        if _has_instance(ln, line):
            return i
        if hit_idx is None:
            hit_idx = i
    return hit_idx


def _apply_wikilink_edge_hint(entry: dict, wl: dict) -> bool:
    """遗留 ``[[id#prerequisite]]`` 等 → ``links[].edge_type``（reference / extend）。"""
    hint = (wl.get("edge_hint") or "").strip()
    if not hint or not is_wikilink_edge_type_fragment(hint):
        return False
    hinted = normalize_link_edge_type(hint)
    current = normalize_link_edge_type(entry.get("edge_type"))
    if hinted == EDGE_EXTEND:
        if current == EDGE_EXTEND:
            return False
        entry["edge_type"] = EDGE_EXTEND
        return True
    if current == EDGE_EXTEND:
        return False
    if current == EDGE_REFERENCE and entry.get("edge_type"):
        return False
    entry["edge_type"] = EDGE_REFERENCE
    return True


def _sync_configured_link_instances(
    body: str,
    lines: list[str],
    sidecar: dict,
    ranges,
) -> dict:
    """为已配置 links[] 补全 KP 范围内的 instances（含父层与子层空隙区）。"""
    links = sidecar.get("links") or []
    instances_added = 0
    skipped_outside_kp = 0
    changed = False

    for link in links:
        if not isinstance(link, dict):
            continue
        anchor = str(link.get("anchor_text") or "").strip()
        if not anchor:
            continue
        idx = next(
            (i for i, ln in enumerate(links) if ln is link),
            None,
        )
        if idx is None:
            continue
        entry = dict(link)
        entry_changed = False

        matches = scan_link_text_matches(
            body,
            anchor,
            lines,
            link_entry=entry,
            sidecar_links=links,
        )
        for m in matches:
            if m.get("is_substring") or m.get("blocked") or m.get("excluded"):
                continue
            line = int(m["line"])
            if not line_in_any_kp(line, ranges):
                skipped_outside_kp += 1
                continue
            if not (m.get("wrapped") or entry.get("targets")):
                continue
            if _add_instance(entry, line):
                instances_added += 1
                entry_changed = True

        sources_seen = {
            sid
            for inst in entry.get("instances") or []
            if isinstance(inst, dict) and inst.get("line") is not None
            for sid in sources_for_link_instance(int(inst["line"]), ranges, entry)
        }
        if len(sources_seen) == 1:
            only = next(iter(sources_seen))
            if entry.get("source_id") != only:
                entry["source_id"] = only
                entry_changed = True

        if entry_changed:
            links[idx] = entry
            changed = True

    return {
        "changed": changed,
        "instances_added": instances_added,
        "skipped_outside_kp": skipped_outside_kp,
    }


def sync_file_sidecar_links(
    rel_path: str,
    body: str,
    sidecar: dict,
    *,
    resolve_target_kp,
) -> dict:
    """按图谱规则，将 KP range 内 wikilink 同步到 sidecar links[]。"""
    kps = resolve_knowledge_points(body, sidecar)
    ranges = kp_ranges_from_resolved(kps)
    if not ranges:
        return {
            "file": rel_path,
            "changed": False,
            "links_created": 0,
            "instances_added": 0,
            "targets_set": 0,
            "skipped_unresolved": 0,
            "skipped_outside_kp": 0,
        }

    links = sidecar.setdefault("links", [])
    links_created = 0
    instances_added = 0
    targets_set = 0
    skipped_unresolved = 0
    skipped_outside_kp = 0
    changed = False

    for wl in scan_wikilinks(body or ""):
        line = _line_from_offset(body, wl["start"])
        if not line_in_any_kp(line, ranges):
            skipped_outside_kp += 1
            continue

        sources = minimal_kps_for_line(line, ranges)

        anchor = _wikilink_anchor(wl)
        if not anchor:
            continue

        graph_kp = resolve_target_kp(anchor)
        idx = _find_link_index(links, anchor, line)

        if idx is None:
            entry: dict = {
                "anchor_text": anchor,
                "occurrence": 0,
                "targets": [graph_kp] if graph_kp else [],
                "edge_type": normalize_link_edge_type(None),
                "instances": [],
            }
            if len(sources) == 1:
                entry["source_id"] = sources[0]
            links.append(entry)
            idx = len(links) - 1
            links_created += 1
            changed = True
        else:
            entry = dict(links[idx])

        if _add_instance(entry, line):
            instances_added += 1
            changed = True

        existing_targets = [
            str(t).strip()
            for t in (entry.get("targets") or [])
            if isinstance(t, str) and str(t).strip()
        ]
        if graph_kp:
            if not existing_targets:
                entry["targets"] = [graph_kp]
                targets_set += 1
                changed = True
            elif graph_kp not in existing_targets:
                entry["targets"] = existing_targets + [graph_kp]
                targets_set += 1
                changed = True
        elif not existing_targets:
            skipped_unresolved += 1

        if _apply_wikilink_edge_hint(entry, wl):
            changed = True
        elif not entry.get("edge_type"):
            entry["edge_type"] = normalize_link_edge_type(None)
            changed = True

        links[idx] = entry

    cfg = _sync_configured_link_instances(
        body,
        body.splitlines(),
        sidecar,
        ranges,
    )
    if cfg["changed"]:
        changed = True
    instances_added += cfg["instances_added"]
    skipped_outside_kp += cfg["skipped_outside_kp"]

    return {
        "file": rel_path,
        "changed": changed,
        "links_created": links_created,
        "instances_added": instances_added,
        "targets_set": targets_set,
        "skipped_unresolved": skipped_unresolved,
        "skipped_outside_kp": skipped_outside_kp,
    }


def _build_dir(kb_path: str) -> Path:
    return Path(kb_path) / MEMORIA_DIR / "build"


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_knowledge_base(kb_path: str) -> dict:
    """全库构建：同步 links[] → 校验 → 图谱 → 自查 → 写入 .memoria/build/。"""
    kb_path = str(kb_path)
    if not os.path.isdir(kb_path):
        return {"status": "error", "message": f"知识库路径不存在: {kb_path}"}

    resolve_target_kp = build_target_kp_resolver(kb_path)
    file_reports: list[dict] = []
    totals = {
        "files_scanned": 0,
        "files_updated": 0,
        "links_created": 0,
        "instances_added": 0,
        "targets_set": 0,
        "skipped_unresolved": 0,
        "validation_errors": 0,
    }

    for rel in collect_md_files(kb_path):
        rel_norm = rel.replace("\\", "/")
        full = os.path.join(kb_path, rel)
        with open(full, "r", encoding="utf-8") as f:
            raw = f.read()
        body, fm = strip_frontmatter(raw)
        lines = body.splitlines()

        sidecar = load_sidecar_for_md(full, kb_path)
        if not sidecar:
            sidecar = {
                "schema_version": SIDECAR_SCHEMA_VERSION,
                "file": rel_norm,
                "knowledge_points": [],
                "links": [],
            }

        totals["files_scanned"] += 1
        sync = sync_file_sidecar_links(
            rel_norm, body, sidecar, resolve_target_kp=resolve_target_kp
        )

        body_stripped, hints_stripped = strip_known_wikilink_edge_hints(body)
        if hints_stripped:
            raw = compose_markdown(body_stripped, fm)
            with open(full, "w", encoding="utf-8") as f:
                f.write(raw)
            body = body_stripped
            lines = body.splitlines()
            sync = {**sync, "hints_stripped": hints_stripped, "body_cleaned": True}

        if sync["changed"]:
            sidecar["schema_version"] = SIDECAR_SCHEMA_VERSION
            sidecar["file"] = rel_norm
            validation = validate_sidecar(sidecar, rel_norm, lines)
            if not validation["ok"]:
                totals["validation_errors"] += 1
                file_reports.append(
                    {**sync, "saved": False, "validation": validation}
                )
                continue
            save_sidecar_for_md(full, kb_path, sidecar)
            totals["files_updated"] += 1

        totals["links_created"] += sync["links_created"]
        totals["instances_added"] += sync["instances_added"]
        totals["targets_set"] += sync["targets_set"]
        totals["skipped_unresolved"] += sync["skipped_unresolved"]

        if sync["changed"]:
            file_reports.append({**sync, "saved": True})

    graph_data = collect_graph_data(kb_path)
    graph_audit = audit_kb_graph_links(kb_path)

    built_at = datetime.now(timezone.utc).isoformat()
    warn_count = (graph_audit.get("summary") or {}).get("warn_count", 0)
    report = {
        "built_at": built_at,
        "kb_path": kb_path,
        "totals": totals,
        "graph": {
            "nodes": len(graph_data.get("nodes") or []),
            "edges": len(graph_data.get("edges") or []),
        },
        "audit": graph_audit.get("summary") or {},
        "files": file_reports,
    }

    out_dir = _build_dir(kb_path)
    _write_json(out_dir / "graph.json", graph_data)
    _write_json(out_dir / "graph_audit.json", graph_audit)
    _write_json(out_dir / "report.json", report)

    lexical_records = 0
    try:
        from memoria.services.lexical_index import rebuild_lexical_index

        lex = rebuild_lexical_index(kb_path)
        lexical_records = int(lex.get("record_count") or 0)
    except OSError:
        lexical_records = 0

    ok = totals["validation_errors"] == 0 and warn_count == 0
    return {
        "status": "ok" if totals["validation_errors"] == 0 else "partial",
        "ok": ok,
        "built_at": built_at,
        "totals": totals,
        "graph": report["graph"],
        "audit": graph_audit.get("summary") or {},
        "warn_count": warn_count,
        "build_dir": str(out_dir),
        "files": file_reports,
        "graph_data": graph_data,
        "graph_audit": graph_audit,
        "lexical_records": lexical_records,
        "message": _build_summary_message(totals, report["graph"], warn_count),
    }


def _build_summary_message(totals: dict, graph: dict, warn_count: int) -> str:
    parts = [
        f"更新 {totals['files_updated']} 文件",
        f"+{totals['links_created']} 链接",
        f"+{totals['instances_added']} 实例",
        f"{graph.get('edges', 0)} 边",
    ]
    if warn_count:
        parts.append(f"{warn_count} 处待人工配置")
    if totals["validation_errors"]:
        parts.append(f"{totals['validation_errors']} 文件校验失败")
    return " · ".join(parts)
