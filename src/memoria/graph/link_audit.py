"""图谱建边自查：对比正文 wikilink、sidecar links[] 与推导边。"""

from __future__ import annotations

import os

from memoria.services.check_report import normalize_check_severity
from memoria.graph.edge_derivation import (
    KpRange,
    build_target_kp_resolver,
    derive_file_graph_edges,
    kp_ranges_from_resolved,
    line_in_any_kp,
    minimal_kps_for_line,
    sources_for_link_instance,
)
from memoria.services.kp_resolver import resolve_knowledge_points
from memoria.services.link_resolver import scan_wikilinks
from memoria.storage.markdown import strip_frontmatter
from memoria.storage.scanner import collect_md_files
from memoria.storage.sidecar import load_sidecar_for_md

ISSUE_MISSING_SIDECAR = "missing_sidecar_link"
ISSUE_NO_INSTANCES = "no_instances"
ISSUE_INSTANCE_OUTSIDE_KP = "instance_outside_kp"
ISSUE_UNRESOLVED_TARGET = "unresolved_graph_target"
ISSUE_PARTIAL_TARGETS = "partial_targets"
ISSUE_VIRTUAL_LINK = "virtual_link"


def _line_from_offset(body: str, start: int) -> int:
    return (body[:start].count("\n") + 1) if body else 1


def _normalize_targets(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        s = raw.strip()
        return [s] if s else []
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if isinstance(t, str) and str(t).strip()]
    return []


def _instance_lines(link: dict) -> list[int]:
    out: list[int] = []
    for inst in link.get("instances") or []:
        if isinstance(inst, dict) and inst.get("line") is not None:
            out.append(int(inst["line"]))
    return out


def _find_sidecar_link(sidecar: dict, anchor: str) -> dict | None:
    anchor = (anchor or "").strip()
    if not anchor:
        return None
    for link in sidecar.get("links") or []:
        if isinstance(link, dict) and str(link.get("anchor_text") or "").strip() == anchor:
            return link
    return None


def _resolve_targets_for_graph(
    raw_targets: list[str], resolve_target_kp
) -> tuple[list[str], list[str]]:
    resolved: list[str] = []
    unresolved: list[str] = []
    seen: set[str] = set()
    for raw in raw_targets:
        kp_id = resolve_target_kp(raw)
        if kp_id and kp_id not in seen:
            seen.add(kp_id)
            resolved.append(kp_id)
        elif not kp_id:
            unresolved.append(raw)
    return resolved, unresolved


def _derived_outgoing_by_source(link_edges: list[dict]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for e in link_edges:
        src = (e.get("source_id") or "").strip()
        if not src:
            continue
        for tid in _normalize_targets(e.get("targets")):
            out.setdefault(src, set()).add(tid)
    return out


def audit_file_graph_links(
    rel_path: str,
    body: str,
    sidecar: dict | None,
    *,
    resolve_target_kp,
) -> dict:
    """单文件图谱链接自查。"""
    sidecar = sidecar or {}
    kps = resolve_knowledge_points(body, sidecar)
    ranges = kp_ranges_from_resolved(kps)
    _, link_edges = derive_file_graph_edges(
        rel_path, body, sidecar, resolve_target_kp=resolve_target_kp
    )
    derived_by_source = _derived_outgoing_by_source(link_edges)

    issues: list[dict] = []
    kp_stats: dict[str, dict] = {}

    def bump_kp(kp_id: str, *, wikilink: bool = False, configured: bool = False, edge: bool = False):
        st = kp_stats.setdefault(
            kp_id,
            {
                "kp_id": kp_id,
                "wikilink_count": 0,
                "configured_link_count": 0,
                "derived_edge_count": 0,
            },
        )
        if wikilink:
            st["wikilink_count"] += 1
        if configured:
            st["configured_link_count"] += 1
        if edge:
            st["derived_edge_count"] += 1

    for kp_id, targets in derived_by_source.items():
        kp_stats.setdefault(
            kp_id,
            {
                "kp_id": kp_id,
                "wikilink_count": 0,
                "configured_link_count": 0,
                "derived_edge_count": 0,
            },
        )["derived_edge_count"] = len(targets)

    configured_anchors: set[str] = set()
    for link in sidecar.get("links") or []:
        if not isinstance(link, dict):
            continue
        anchor = str(link.get("anchor_text") or "").strip()
        if not anchor:
            continue
        configured_anchors.add(anchor)
        raw_targets = _normalize_targets(link.get("targets"))
        inst_lines = _instance_lines(link)

        if not raw_targets:
            issues.append(
                {
                    "code": ISSUE_VIRTUAL_LINK,
                    "severity": "info",
                    "file": rel_path,
                    "anchor_text": anchor,
                    "message": f"链接「{anchor}」未绑定目标，不参与图谱建边",
                }
            )
            continue

        resolved, unresolved = _resolve_targets_for_graph(raw_targets, resolve_target_kp)

        if not inst_lines:
            issues.append(
                {
                    "code": ISSUE_NO_INSTANCES,
                    "severity": "warning",
                    "file": rel_path,
                    "anchor_text": anchor,
                    "targets": raw_targets,
                    "message": f"链接「{anchor}」已配置跳转目标但无 instances，图谱不建边",
                }
            )
            continue

        for line in inst_lines:
            sources = sources_for_link_instance(line, ranges, link)
            if not sources:
                issues.append(
                    {
                        "code": ISSUE_INSTANCE_OUTSIDE_KP,
                        "severity": "warning",
                        "file": rel_path,
                        "anchor_text": anchor,
                        "line": line,
                        "message": f"链接「{anchor}」L{line} 不在任何 KP range 内，图谱不建边",
                    }
                )
                continue
            for src in sources:
                bump_kp(src, configured=True)
            if not resolved:
                issues.append(
                    {
                        "code": ISSUE_UNRESOLVED_TARGET,
                        "severity": "warning",
                        "file": rel_path,
                        "anchor_text": anchor,
                        "line": line,
                        "targets": raw_targets,
                        "message": (
                            f"链接「{anchor}」L{line} 的 targets 均无法解析为 KP id"
                            f"（{', '.join(raw_targets)}）"
                        ),
                    }
                )
            elif unresolved:
                issues.append(
                    {
                        "code": ISSUE_PARTIAL_TARGETS,
                        "severity": "info",
                        "file": rel_path,
                        "anchor_text": anchor,
                        "line": line,
                        "resolved": resolved,
                        "unresolved": unresolved,
                        "message": (
                            f"链接「{anchor}」部分 target 未入图谱："
                            f"{', '.join(unresolved)}"
                        ),
                    }
                )

    for wl in scan_wikilinks(body or ""):
        line = _line_from_offset(body, wl["start"])
        anchor = (wl.get("target_id") or "").strip()
        if not anchor:
            continue
        if not line_in_any_kp(line, ranges):
            continue
        sources = minimal_kps_for_line(line, ranges)

        for src in sources:
            bump_kp(src, wikilink=True)

        entry = _find_sidecar_link(sidecar, anchor)
        if not entry:
            for src in sources:
                issues.append(
                    {
                        "code": ISSUE_MISSING_SIDECAR,
                        "severity": "warning",
                        "file": rel_path,
                        "kp_id": src,
                        "anchor_text": anchor,
                        "line": line,
                        "message": (
                            f"KP「{src}」内正文 [[{anchor}]]（L{line}）"
                            f"未配置 sidecar links[]，图谱不建边"
                        ),
                    }
                )
            continue

        inst_lines = _instance_lines(entry)
        if line not in inst_lines:
            for src in sources:
                issues.append(
                    {
                        "code": ISSUE_MISSING_SIDECAR,
                        "severity": "warning",
                        "file": rel_path,
                        "kp_id": src,
                        "anchor_text": anchor,
                        "line": line,
                        "message": (
                            f"KP「{src}」内 [[{anchor}]]（L{line}）"
                            f"无对应 instances 行，图谱不建边"
                        ),
                    }
                )

    warn_count = sum(
        1 for i in issues if normalize_check_severity(i.get("severity")) == "warning"
    )
    kp_summaries = []
    for st in kp_stats.values():
        gap = st["wikilink_count"] - st["derived_edge_count"]
        if st["wikilink_count"] > 0 and gap > 0:
            st = {**st, "edge_gap": gap}
        kp_summaries.append(st)

    return {
        "file": rel_path,
        "ok": warn_count == 0,
        "summary": {
            "issue_count": len(issues),
            "warn_count": warn_count,
            "kp_count": len(kp_summaries),
        },
        "issues": issues,
        "kp_summaries": sorted(kp_summaries, key=lambda x: x["kp_id"]),
    }


def audit_kb_graph_links(kb_path: str) -> dict:
    """全库图谱链接自查。"""
    resolve_target_kp = build_target_kp_resolver(kb_path)
    files_report: list[dict] = []
    total_warn = 0
    total_issues = 0

    for rel in collect_md_files(kb_path):
        rel_norm = rel.replace("\\", "/")
        full = os.path.join(kb_path, rel)
        sidecar = load_sidecar_for_md(full, kb_path)
        if not sidecar:
            continue
        with open(full, "r", encoding="utf-8") as f:
            raw = f.read()
        body, _ = strip_frontmatter(raw)
        report = audit_file_graph_links(
            rel_norm, body, sidecar, resolve_target_kp=resolve_target_kp
        )
        if report["issues"]:
            files_report.append(report)
        total_issues += report["summary"]["issue_count"]
        total_warn += report["summary"]["warn_count"]

    return {
        "status": "ok",
        "ok": total_warn == 0,
        "summary": {
            "files_checked": len(list(collect_md_files(kb_path))),
            "files_with_issues": len(files_report),
            "issue_count": total_issues,
            "warn_count": total_warn,
        },
        "files": files_report,
    }
