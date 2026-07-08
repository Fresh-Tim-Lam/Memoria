"""链接文本实例：扫描、挂接、剔除（M2）。"""

from __future__ import annotations

from memoria.services.link_md import (
    find_plain_text,
    format_wikilink,
    remove_wikilink_on_line,
    wikilink_replacement_text,
)
from memoria.services.link_resolver import scan_wikilinks, wikilink_label
from memoria.services.link_text_search import scan_link_text_matches as _scan_link_text_matches


def scan_link_text_matches(
    body: str,
    anchor_text: str,
    lines: list[str] | None = None,
    *,
    link_entry: dict | None = None,
    search_options: dict | None = None,
    sidecar_links: list | None = None,
) -> list[dict]:
    """扫描正文匹配；规则见 ``link_text_search``（搜索引擎对接层）。"""
    return _scan_link_text_matches(
        body,
        anchor_text,
        lines,
        link_entry=link_entry,
        search_options=search_options,
        sidecar_links=sidecar_links,
    )


def line_at_offset(body: str, offset: int) -> int:
    return body[:offset].count("\n") + 1


def section_for_line(lines: list[str], line_num: int) -> str:
    """向上找最近 ## / ### 标题作为章节名。"""
    if not lines or line_num < 1:
        return ""
    idx = min(line_num - 1, len(lines) - 1)
    for i in range(idx, -1, -1):
        row = lines[i].strip()
        if row.startswith("#"):
            return row.lstrip("#").strip()
    return ""


def _link_label(link: dict) -> str:
    return wikilink_label(link["target_id"], link.get("display"))


def _is_excluded(line: int, excluded: list) -> bool:
    for ex in excluded or []:
        if not isinstance(ex, dict):
            continue
        if int(ex.get("line") or 0) == line:
            return True
    return False


def _instance_lines(instances: list) -> set[int]:
    out: set[int] = set()
    for inst in instances or []:
        if isinstance(inst, dict) and inst.get("line"):
            out.add(int(inst["line"]))
    return out


def wrap_plain_on_lines(
    body: str,
    anchor: str,
    line_numbers: list[int],
    *,
    line_spans: dict[int, tuple[int, str]] | None = None,
) -> tuple[str, int]:
    """按行号包裹 plain 匹配（自下而上）；``line_spans`` 为模糊匹配时的 (col, matched_text)。"""
    anchor = anchor.strip()
    if not anchor:
        return body, 0
    lines_set = set(int(x) for x in line_numbers)
    count = 0
    body_lines = body.split("\n")
    spans = line_spans or {}
    for ln in sorted(lines_set, reverse=True):
        if ln < 1 or ln > len(body_lines):
            continue
        idx = ln - 1
        row = body_lines[idx]
        new_row = row
        if ln in spans:
            spec = spans[ln]
            if len(spec) == 3:
                pos, _matched, replace_end = spec
                new_row = row[:pos] + format_wikilink(anchor) + row[replace_end:]
            else:
                pos, matched = spec
                if pos < 0 or not matched or row[pos : pos + len(matched)] != matched:
                    pos = find_plain_text_in_line(row, matched)
                    if pos < 0:
                        pos = find_plain_text_in_line(row, anchor)
                        matched = anchor
                if pos >= 0:
                    new_row = row[:pos] + format_wikilink(anchor) + row[pos + len(matched) :]
        else:
            pos = find_plain_text_in_line(row, anchor)
            if pos >= 0:
                new_row = row[:pos] + format_wikilink(anchor) + row[pos + len(anchor) :]
        if new_row != row:
            body_lines[idx] = new_row
            count += 1
    return "\n".join(body_lines), count


def migrate_link_instances(body: str, link: dict, lines: list[str]) -> dict:
    """无 instances 时从正文扫描初始化；有 instances 时按正文 [[anchor]] 校正行号。"""
    anchor = str(link.get("anchor_text") or "").strip()
    if not anchor:
        return link
    matches = scan_link_text_matches(body, anchor, lines, link_entry=link)
    wrapped_lines = sorted(
        m["line"] for m in matches if m.get("wrapped") and not m.get("excluded")
    )
    if not link.get("instances"):
        instances = []
        for m in matches:
            if m.get("excluded"):
                continue
            if m.get("wrapped") or m.get("attached"):
                instances.append({"line": m["line"], "wrapped": m.get("wrapped", False)})
        if not instances:
            for m in matches:
                if not m.get("is_substring") and not m.get("excluded"):
                    instances.append({"line": m["line"], "wrapped": m.get("wrapped", False)})
        out = dict(link)
        out["instances"] = instances
        return out
    if wrapped_lines:
        inst_lines = _instance_lines(link.get("instances"))
        if inst_lines != set(wrapped_lines):
            out = dict(link)
            out["instances"] = [{"line": ln, "wrapped": True} for ln in wrapped_lines]
            return out
    return link


def sync_instances_from_selection(
    link: dict,
    selected_lines: list[int],
    matches: list[dict],
) -> dict:
    selected = set(int(x) for x in selected_lines)
    instances = []
    for m in matches:
        ln = int(m["line"])
        if ln in selected:
            instances.append({"line": ln, "wrapped": bool(m.get("wrapped"))})
    out = dict(link)
    out["instances"] = instances
    return out


def find_plain_text_in_line(row: str, text: str) -> int:
    """单行内找 plain 匹配（复用 find_plain_text 规则）。"""
    pos = find_plain_text(row, text, occurrence=0)
    return pos


def unwrap_lines(body: str, anchor: str, line_numbers: list[int]) -> tuple[str, int]:
    anchor = anchor.strip()
    count = 0
    for ln in sorted(set(int(x) for x in line_numbers), reverse=True):
        new_body, ok = remove_wikilink_on_line(body, anchor, ln)
        if ok:
            body = new_body
            count += 1
    return body, count


def add_excluded_lines(link: dict, line_numbers: list[int]) -> dict:
    excluded = list(link.get("excluded") or [])
    existing = {int(x.get("line") or 0) for x in excluded if isinstance(x, dict)}
    for ln in line_numbers:
        ln = int(ln)
        if ln and ln not in existing:
            excluded.append({"line": ln})
    out = dict(link)
    out["excluded"] = excluded
    return out


def remove_excluded_line(link: dict, line_number: int) -> dict:
    ln = int(line_number)
    excluded = [
        x
        for x in (link.get("excluded") or [])
        if not (isinstance(x, dict) and int(x.get("line") or 0) == ln)
    ]
    out = dict(link)
    out["excluded"] = excluded
    return out


def preview_filter_wikilinks(body: str, sidecar_links: list, lines: list[str]) -> str:
    """预览：非 instances 行上的 [[anchor]] 还原为 plain（不改源文件）。"""
    if not body or not sidecar_links:
        return body
    to_unwrap: list[tuple[int, int, str]] = []
    for link in sidecar_links:
        if not isinstance(link, dict):
            continue
        anchor = str(link.get("anchor_text") or "").strip()
        if not anchor:
            continue
        inst = link.get("instances")
        if not inst:
            continue
        inst_lines = _instance_lines(inst)
        excluded = link.get("excluded") or []
        for wl in scan_wikilinks(body):
            if wl["target_id"] != anchor and _link_label(wl) != anchor:
                continue
            ln = line_at_offset(body, wl["start"])
            if ln in inst_lines and not _is_excluded(ln, excluded):
                continue
            repl = wikilink_replacement_text(
                wl["target_id"], display=wl.get("display") or anchor
            )
            to_unwrap.append((wl["start"], wl["end"], repl))
    for start, end, repl in sorted(to_unwrap, key=lambda x: x[0], reverse=True):
        body = body[:start] + repl + body[end:]
    return body


def build_preview_body(body: str, sidecar_links: list, lines: list[str]) -> str:
    """预览正文：过滤非实例 wikilink + 注入实例 plain。"""
    out = preview_filter_wikilinks(body, sidecar_links or [], lines)
    for link in sidecar_links or []:
        if isinstance(link, dict):
            out = inject_sidecar_plain_on_lines(out, link, lines)
    return out


def inject_sidecar_plain_on_lines(
    body: str, link: dict, lines: list[str] | None = None
) -> str:
    """仅对 instances 中未包裹的行注入 [[anchor]]（预览用）。"""
    anchor = str(link.get("anchor_text") or "").strip()
    targets = link.get("targets") or []
    if not anchor or not targets or not body:
        return body
    lines = lines if lines is not None else body.split("\n")
    inst = link.get("instances")
    if not inst:
        return body
    inst_lines = _instance_lines(inst)
    excluded = link.get("excluded") or []
    out_lines = body.split("\n")
    for inst_row in inst:
        if not isinstance(inst_row, dict):
            continue
        ln = int(inst_row.get("line") or 0)
        if not ln or ln > len(out_lines) or inst_row.get("wrapped"):
            continue
        if ln not in inst_lines or _is_excluded(ln, excluded):
            continue
        row = out_lines[ln - 1]
        pos = find_plain_text_in_line(row, anchor)
        if pos < 0:
            continue
        wrapped = format_wikilink(anchor)
        out_lines[ln - 1] = row[:pos] + wrapped + row[pos + len(anchor) :]
    return "\n".join(out_lines)


def audit_link_consistency(
    body: str,
    sidecar_links: list,
    lines: list[str] | None = None,
    *,
    resolved_targets: set[str] | frozenset[str] | None = None,
) -> dict:
    """检查 sidecar 链接、正文 [[]] 与预览挂接是否一致。"""
    lines = lines if lines is not None else (body or "").split("\n")
    results: list[dict] = []

    for link in sidecar_links or []:
        if not isinstance(link, dict):
            continue
        anchor = str(link.get("anchor_text") or "").strip()
        targets = link.get("targets") or []
        if not anchor:
            continue

        matches = scan_link_text_matches(body, anchor, lines, link_entry=link)
        inst_lines = _instance_lines(link.get("instances"))
        excluded = link.get("excluded") or []
        wrapped_lines = {m["line"] for m in matches if m.get("wrapped")}

        preview_attached = 0
        issues: list[str] = []
        active_inst = [ln for ln in inst_lines if not _is_excluded(ln, excluded)]

        if active_inst:
            for ln in active_inst:
                on_line = next((m for m in matches if m["line"] == ln), None)
                if on_line and on_line.get("wrapped"):
                    preview_attached += 1
                elif on_line and not on_line.get("is_substring"):
                    preview_attached += 1
                else:
                    issues.append(f"L{ln} 实例在正文中未找到「{anchor}」")
        else:
            preview_attached = len(
                [
                    m
                    for m in matches
                    if m.get("wrapped") and not m.get("excluded")
                ]
            )
            if not preview_attached and targets:
                issues.append("未记录 instances，正文无 [[…]] 入口")

        targets_resolved = True
        if resolved_targets is not None and targets:
            targets_resolved = any(
                str(t).strip() in resolved_targets for t in targets
            )
            if not targets_resolved:
                issues.append("跳转目标均无法解析")

        if not targets:
            issues.append("未配置跳转目标")

        status = "ok"
        if targets and preview_attached == 0:
            status = "missing_body"
            if not any("未找到" in x for x in issues):
                issues.append("正文无已挂接的跳转入口")
        elif issues and preview_attached > 0:
            status = "partial"
        elif issues:
            status = "stale_instance" if active_inst else "missing_body"

        results.append(
            {
                "anchor_text": anchor,
                "status": status,
                "issues": issues,
                "instance_lines": sorted(active_inst),
                "body_wrapped_count": len(wrapped_lines),
                "preview_attached_count": preview_attached,
                "targets_resolved": targets_resolved,
                "scan_match_count": len(
                    [m for m in matches if not m.get("is_substring")]
                ),
                "suggested_lines": [
                    m["line"]
                    for m in matches
                    if not m.get("is_substring") and not m.get("excluded")
                ],
            }
        )

    issue_count = sum(1 for r in results if r["status"] != "ok")
    unresolved = sum(1 for r in results if not r.get("targets_resolved"))
    return {
        "ok": issue_count == 0,
        "summary": {
            "total": len(results),
            "issue_count": issue_count,
            "unresolved_count": unresolved,
        },
        "links": results,
    }


def is_line_attached(link: dict | None, line: int, body: str, lines: list[str]) -> bool:
    """预览/跳转：该行是否挂接入跳转入口。"""
    if not link:
        return False
    anchor = str(link.get("anchor_text") or "").strip()
    if not anchor:
        return False
    if _is_excluded(line, link.get("excluded") or []):
        return False
    inst_lines = _instance_lines(link.get("instances"))
    if inst_lines:
        return line in inst_lines
    # legacy：任一 [[anchor]] 或 plain（由预览 inject 处理）
    for m in scan_link_text_matches(body, anchor, lines, link_entry=link):
        if m["line"] == line and not m.get("excluded"):
            return m.get("wrapped") or True
    return False
