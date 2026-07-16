"""链接匹配文本搜索（M2 · 搜索引擎对接层）。

当前实现：精确匹配 + 可选空白模糊；后续搜索引擎可替换 ``scan_link_text_matches`` /
``suggest_link_anchor_texts`` 内部逻辑而不改 API 契约。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field

from memoria.services.link_md import _ok_plain_prefix, _ok_plain_suffix
from memoria.services.link_resolver import scan_wikilinks, wikilink_label


def line_at_offset(body: str, offset: int) -> int:
    return body[:offset].count("\n") + 1


def section_for_line(lines: list[str], line_num: int) -> str:
    if not lines or line_num < 1:
        return ""
    idx = min(line_num - 1, len(lines) - 1)
    for i in range(idx, -1, -1):
        row = lines[i].strip()
        if row.startswith("#"):
            return row.lstrip("#").strip()
    return ""


# ---------------------------------------------------------------------------
# 选项
# ---------------------------------------------------------------------------


@dataclass
class LinkTextSearchOptions:
    """与搜索引擎共用的匹配选项（前端 checkbox 对应字段）。"""

    fuzzy_whitespace: bool = False
    fuzzy_suggest: bool = True
    case_insensitive: bool = False
    route_anchor: str | None = None

    @classmethod
    def from_dict(cls, raw: dict | None) -> LinkTextSearchOptions:
        raw = raw or {}
        route = (raw.get("route_anchor") or "").strip() or None
        return cls(
            fuzzy_whitespace=bool(
                raw.get("fuzzy_whitespace", raw.get("fuzzy", False))
            ),
            fuzzy_suggest=bool(raw.get("fuzzy_suggest", True)),
            case_insensitive=bool(raw.get("case_insensitive", False)),
            route_anchor=route,
        )

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_SEARCH_OPTIONS = LinkTextSearchOptions()


def compact_text(text: str, *, case_insensitive: bool = False) -> str:
    """去掉全部空白，用于空白模糊比较。

    同时做 Unicode NFKC 规范化，使全角/半角字符（如 （）vs ()、Ａ vs A）
    能正确匹配。这样"完整性 （integrity）"和"完整性 (integrity)"被视为相等。
    """
    s = unicodedata.normalize("NFKC", (text or "").strip())
    s = re.sub(r"\s+", "", s)
    return s.lower() if case_insensitive else s


def normalize_query(text: str, options: LinkTextSearchOptions) -> str:
    t = (text or "").strip()
    if options.case_insensitive:
        t = t.lower()
    return t


# ---------------------------------------------------------------------------
# 精确匹配（自 link_instances 迁入）
# ---------------------------------------------------------------------------


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


def _link_label(link: dict) -> str:
    return wikilink_label(link["target_id"], link.get("display"))


def _route_sidecar_keys(
    link_entry: dict | None,
    options: LinkTextSearchOptions,
) -> set[str]:
    """侧车中已确立的跳转键（不含用户正在输入的新匹配文本）。"""
    keys: set[str] = set()
    for raw in ((link_entry or {}).get("anchor_text"), options.route_anchor):
        k = str(raw or "").strip()
        if k:
            keys.add(k)
    return keys


def _route_identity_keys(
    search_anchor: str,
    link_entry: dict | None,
    options: LinkTextSearchOptions,
) -> set[str]:
    keys = set(_route_sidecar_keys(link_entry, options))
    sa = (search_anchor or "").strip()
    if sa:
        keys.add(sa)
    return keys


def _wikilink_belongs_to_route_for(
    link: dict,
    search_anchor: str,
    route: str,
    *,
    options: LinkTextSearchOptions,
) -> bool:
    """wikilink 是否属于指定 route 键（应展开而非剔除）。"""
    tid = link["target_id"]
    label = _link_label(link)
    sa = (search_anchor or "").strip()
    route = (route or "").strip()

    def _matches_key(key: str) -> bool:
        if not key:
            return False
        if _strict_anchor_equal(tid, key, case_insensitive=options.case_insensitive):
            return True
        return _strict_anchor_equal(label, key, case_insensitive=options.case_insensitive)

    if sa and _matches_key(sa):
        return True
    if route and _matches_key(route):
        return True

    for key in (tid, label):
        if not key or not route:
            continue
        ck = compact_text(key, case_insensitive=options.case_insensitive)
        cr = compact_text(route, case_insensitive=options.case_insensitive)
        cs = compact_text(sa, case_insensitive=options.case_insensitive) if sa else cr
        if ck and (cr.startswith(ck) or (sa and cs.startswith(ck))):
            return True

    if not route or not sa or route == sa:
        return False

    extends = sa.startswith(route) or (
        options.fuzzy_whitespace
        and compact_text(sa, case_insensitive=options.case_insensitive).startswith(
            compact_text(route, case_insensitive=options.case_insensitive)
        )
    )
    if not extends:
        return False

    for key in (tid, label):
        if not key:
            continue
        ck = compact_text(key, case_insensitive=options.case_insensitive)
        cr = compact_text(route, case_insensitive=options.case_insensitive)
        cs = compact_text(sa, case_insensitive=options.case_insensitive)
        if cr and ck and (cr.startswith(ck) or cs.startswith(ck)):
            return True
    return False


def _wikilink_belongs_to_route(
    link: dict,
    search_anchor: str,
    *,
    link_entry: dict | None,
    options: LinkTextSearchOptions,
) -> bool:
    """wikilink 是否属于当前配置的跳转（应展开而非剔除）。"""
    keys = _route_identity_keys(search_anchor, link_entry, options)
    if not keys:
        return False
    return any(
        _wikilink_belongs_to_route_for(link, search_anchor, route, options=options)
        for route in keys
    )


def build_search_view(
    text: str,
    search_anchor: str,
    *,
    options: LinkTextSearchOptions,
    link_entry: dict | None = None,
) -> tuple[str, list[int]]:
    """构造匹配用视图：当前跳转的 [[…]] 展开为可见文本，其它 [[…]] 整段移除。

    返回 (view, view_to_orig)，view_to_orig[i] 为 view[i] 在原文中的下标。
    """
    body = text or ""
    search_anchor = (search_anchor or "").strip()
    if not body:
        return "", []

    links = scan_wikilinks(body)
    if not links:
        return body, list(range(len(body)))

    view_chars: list[str] = []
    view_to_orig: list[int] = []
    cursor = 0
    for link in links:
        for i in range(cursor, link["start"]):
            view_chars.append(body[i])
            view_to_orig.append(i)
        if _wikilink_belongs_to_route(
            link, search_anchor, link_entry=link_entry, options=options
        ):
            vis_start, _ = _visible_text_abs_span(link)
            label = _link_label(link) or link["target_id"]
            for j, ch in enumerate(label):
                view_chars.append(ch)
                view_to_orig.append(vis_start + j)
        cursor = link["end"]

    for i in range(cursor, len(body)):
        view_chars.append(body[i])
        view_to_orig.append(i)

    return "".join(view_chars), view_to_orig


def _strict_anchor_equal(a: str, b: str, *, case_insensitive: bool = False) -> bool:
    if not a or not b:
        return False
    if case_insensitive:
        return a.lower() == b.lower()
    return a == b


def _visible_text_abs_span(link: dict) -> tuple[int, int]:
    """wikilink 在正文中的可见文本 [start, end)。"""
    label = _link_label(link) or link["target_id"]
    inner = link["raw"]
    rel = inner.find(label)
    if rel < 0:
        rel = 2
    start = link["start"] + rel
    return start, start + len(label)


def _orig_replace_bounds(
    row: str,
    view_to_orig: list[int],
    view_start: int,
    view_end: int,
    search_anchor: str,
    *,
    link_entry: dict | None,
    options: LinkTextSearchOptions,
) -> tuple[int, int]:
    """视图匹配 [view_start, view_end) 在原文中应替换的 [lo, hi)（可含当前跳转的 [[]]）。"""
    if view_end <= view_start or not view_to_orig:
        pos = _view_index_to_orig(view_to_orig, view_start)
        return pos, pos
    orig_indices = view_to_orig[view_start:view_end]
    lo = min(orig_indices)
    hi = max(orig_indices) + 1
    for link in scan_wikilinks(row):
        if not _wikilink_belongs_to_route(
            link, search_anchor, link_entry=link_entry, options=options
        ):
            continue
        vis_start, vis_end = _visible_text_abs_span(link)
        if any(vis_start <= o < vis_end for o in orig_indices):
            lo = min(lo, link["start"])
    return lo, hi


def _view_index_to_orig(view_to_orig: list[int], view_index: int) -> int:
    if not view_to_orig:
        return view_index
    if view_index < 0:
        return 0
    if view_index >= len(view_to_orig):
        return view_to_orig[-1]
    return view_to_orig[view_index]


def _map_view_span_to_orig(
    view_to_orig: list[int], start: int, end: int
) -> tuple[int, int]:
    if end <= start:
        pos = _view_index_to_orig(view_to_orig, start)
        return pos, pos
    orig_start = _view_index_to_orig(view_to_orig, start)
    orig_end = _view_index_to_orig(view_to_orig, end - 1) + 1
    return orig_start, orig_end


def _find_plain_in_view(
    view: str,
    anchor: str,
    view_to_orig: list[int],
    *,
    occurrence: int = 0,
) -> int:
    """在搜索视图中找 plain 出现，返回原文中的起始下标。"""
    pos = 0
    found = 0
    while pos <= len(view):
        hit = view.find(anchor, pos)
        if hit < 0:
            return -1
        if _ok_plain_prefix(view, hit, anchor=anchor) and _ok_plain_suffix(
            view, hit + len(anchor), anchor=anchor
        ):
            if found == occurrence:
                return _view_index_to_orig(view_to_orig, hit)
            found += 1
        pos = hit + 1
    return -1


def _anchors_equal(a: str, b: str, options: LinkTextSearchOptions) -> bool:
    # NFKC normalize both sides so full-width/half-width variants match.
    na = unicodedata.normalize("NFKC", a)
    nb = unicodedata.normalize("NFKC", b)
    if options.case_insensitive:
        if na.lower() == nb.lower():
            return True
    elif na == nb:
        return True
    if options.fuzzy_whitespace:
        return compact_text(a, case_insensitive=options.case_insensitive) == compact_text(
            b, case_insensitive=options.case_insensitive
        )
    return False


def _snippet_for_line(
    lines: list[str],
    line_num: int,
    highlight: str,
    *,
    ctx: int = 48,
    replace_start: int | None = None,
) -> str:
    if line_num < 1 or line_num > len(lines):
        return ""
    row = lines[line_num - 1]
    pos = row.find(highlight) if highlight else -1
    if pos < 0 and replace_start is not None and replace_start >= 0:
        pos = replace_start
    if pos < 0:
        pos = 0
    start = max(0, pos - ctx)
    end = min(len(row), pos + max(len(highlight or ""), 1) + ctx)
    return row[start:end]


def _match_from_view_span(
    row: str,
    view: str,
    view_to_orig: list[int],
    view_start: int,
    view_end: int,
    search_anchor: str,
    *,
    link_entry: dict | None,
    options: LinkTextSearchOptions,
) -> dict:
    matched = view[view_start:view_end]
    replace_start, replace_end = _orig_replace_bounds(
        row,
        view_to_orig,
        view_start,
        view_end,
        search_anchor,
        link_entry=link_entry,
        options=options,
    )
    return {
        "col": replace_start,
        "matched_text": matched,
        "replace_start": replace_start,
        "replace_end": replace_end,
    }


def _naive_substring_lines(
    lines: list[str],
    anchor: str,
    skip_lines: set[int],
    *,
    options: LinkTextSearchOptions,
    link_entry: dict | None = None,
) -> list[dict]:
    anchor = (anchor or "").strip()
    if not anchor:
        return []
    out: list[dict] = []
    ca = compact_text(anchor, case_insensitive=options.case_insensitive)
    for i, row in enumerate(lines):
        ln = i + 1
        if ln in skip_lines:
            continue
        view, v2o = build_search_view(
            row, anchor, options=options, link_entry=link_entry
        )
        if _find_plain_in_view(view, anchor, v2o, occurrence=0) >= 0:
            continue
        if options.fuzzy_whitespace and ca:
            fuzzy = find_fuzzy_whitespace_spans_in_line(
                row,
                anchor,
                options=options,
                search_anchor=anchor,
                link_entry=link_entry,
            )
            if fuzzy:
                continue
        pos = view.find(anchor)
        if pos < 0 and not (
            options.fuzzy_whitespace
            and ca
            and ca in compact_text(view, case_insensitive=options.case_insensitive)
        ):
            continue
        if pos < 0:
            pos = 0
        span = _match_from_view_span(
            row,
            view,
            v2o,
            pos,
            pos + len(anchor),
            anchor,
            link_entry=link_entry,
            options=options,
        )
        out.append(
            {
                "line": ln,
                "col": span["col"],
                "matched_text": span["matched_text"],
                "replace_start": span["replace_start"],
                "replace_end": span["replace_end"],
                "wrapped": False,
                "is_substring": True,
                "excluded": False,
                "attached": False,
                "fuzzy": False,
                "section": section_for_line(lines, ln),
                "snippet": _snippet_for_line(
                    lines, ln, span["matched_text"], replace_start=span["replace_start"]
                ),
            }
        )
    return out


def find_fuzzy_whitespace_spans_in_line(
    row: str,
    anchor: str,
    *,
    options: LinkTextSearchOptions | None = None,
    search_anchor: str | None = None,
    link_entry: dict | None = None,
) -> list[tuple[int, int, str, int, int]]:
    """在行内找空白模糊等价 span；返回 (col, view_end, matched, replace_start, replace_end)。"""
    options = options or DEFAULT_SEARCH_OPTIONS
    anchor = (anchor or "").strip()
    if not anchor:
        return []
    ca = compact_text(anchor, case_insensitive=options.case_insensitive)
    if not ca:
        return []

    sa = (search_anchor if search_anchor is not None else anchor).strip()
    view, v2o = build_search_view(row, sa, options=options, link_entry=link_entry)

    out: list[tuple[int, int, str, int, int]] = []
    n = len(view)
    seen: set[tuple[int, int]] = set()

    for start in range(n):
        if view[start].isspace():
            continue
        ci = 0
        j = start
        while j < n and ci < len(ca):
            ch = view[j]
            if ch.isspace():
                j += 1
                continue
            ac = ca[ci]
            rc = ch.lower() if options.case_insensitive else ch
            if rc != ac:
                break
            ci += 1
            j += 1
        if ci != len(ca):
            continue
        if not _ok_plain_prefix(view, start, anchor=sa):
            continue
        if not _ok_plain_suffix(view, j, anchor=sa):
            continue
        span = _match_from_view_span(
            row,
            view,
            v2o,
            start,
            j,
            sa,
            link_entry=link_entry,
            options=options,
        )
        key = (span["replace_start"], span["replace_end"])
        if key in seen:
            continue
        seen.add(key)
        out.append(
            (
                span["col"],
                j,
                span["matched_text"],
                span["replace_start"],
                span["replace_end"],
            )
        )
    return out


def _match_span_bounds(m: dict) -> tuple[int, int, int]:
    rs = int(m.get("replace_start") if m.get("replace_start") is not None else m.get("col") or 0)
    mt = str(m.get("matched_text") or "")
    re = int(m.get("replace_end") if m.get("replace_end") is not None else rs + len(mt))
    return int(m["line"]), rs, re


def _match_quality(m: dict) -> int:
    return (
        (8 if m.get("wrapped") else 0)
        + (4 if m.get("attached") else 0)
        + (2 if not m.get("is_substring") else 0)
        + (1 if not m.get("fuzzy") else 0)
    )


def _dedupe_overlapping_matches(matches: list[dict]) -> list[dict]:
    """同行、同文本且区域重叠的匹配只保留质量最高的一条（优先已包裹）。"""
    out: list[dict] = []
    for m in matches:
        ln, rs, re = _match_span_bounds(m)
        mt = str(m.get("matched_text") or "")
        merged = False
        for i, prev in enumerate(out):
            pln, prs, pre = _match_span_bounds(prev)
            if pln != ln or str(prev.get("matched_text") or "") != mt:
                continue
            if rs < pre and prs < re:
                if _match_quality(m) > _match_quality(prev):
                    out[i] = m
                merged = True
                break
            if rs == prs and re == pre:
                merged = True
                break
        if not merged:
            out.append(m)
    return sorted(out, key=lambda m: (m["line"], m.get("replace_start") or 0))


def _exact_scan(
    body: str,
    anchor: str,
    lines: list[str],
    *,
    link_entry: dict | None,
    options: LinkTextSearchOptions,
) -> list[dict]:
    excluded = (link_entry or {}).get("excluded") or []
    inst_lines = _instance_lines((link_entry or {}).get("instances"))
    by_key: dict[tuple[int, int], dict] = {}

    def _add_match(m: dict) -> None:
        rs = int(m.get("replace_start") if m.get("replace_start") is not None else m.get("col") or 0)
        key = (int(m["line"]), rs)
        prev = by_key.get(key)
        if prev:
            if prev.get("wrapped") and not m.get("wrapped"):
                return
            if not prev.get("wrapped") and m.get("wrapped"):
                by_key[key] = m
                return
            if prev.get("matched_text") == m.get("matched_text"):
                return
        by_key[key] = m

    for link in scan_wikilinks(body):
        tid = link["target_id"]
        label = _link_label(link)
        if not _wikilink_belongs_to_route(
            link, anchor, link_entry=link_entry, options=options
        ):
            continue
        if not (
            _anchors_equal(tid, anchor, options)
            or _anchors_equal(label, anchor, options)
        ):
            continue
        ln = line_at_offset(body, link["start"])
        line_start = body.rfind("\n", 0, link["start"]) + 1 if link["start"] > 0 else 0
        row_rs = link["start"] - line_start
        row_re = link["end"] - line_start
        vis_start, _ = _visible_text_abs_span(link)
        matched = wikilink_label(tid, link.get("display")) or tid
        _add_match(
            {
                "line": ln,
                "col": vis_start - line_start,
                "matched_text": matched,
                "replace_start": row_rs,
                "replace_end": row_re,
                "wrapped": True,
                "is_substring": False,
                "excluded": _is_excluded(ln, excluded),
                "attached": ln in inst_lines if inst_lines else True,
                "fuzzy": False,
                "section": section_for_line(lines, ln),
                "snippet": _snippet_for_line(
                    lines, ln, matched, replace_start=row_rs
                ),
            }
        )

    search_body, search_v2o = build_search_view(
        body, anchor, options=options, link_entry=link_entry
    )
    occ = 0
    while True:
        pos = _find_plain_in_view(search_body, anchor, search_v2o, occurrence=occ)
        if pos < 0:
            break
        ln = line_at_offset(body, pos)
        if 0 < ln <= len(lines):
            row = lines[ln - 1]
            view, v2o = build_search_view(
                row, anchor, options=options, link_entry=link_entry
            )
            view_hit = -1
            for vi, oi in enumerate(v2o):
                if oi == pos:
                    view_hit = vi
                    break
            if view_hit < 0:
                view_hit = view.find(anchor)
            if view_hit >= 0:
                span = _match_from_view_span(
                    row,
                    view,
                    v2o,
                    view_hit,
                    view_hit + len(anchor),
                    anchor,
                    link_entry=link_entry,
                    options=options,
                )
                _add_match(
                    {
                        "line": ln,
                        "col": span["col"],
                        "matched_text": span["matched_text"],
                        "replace_start": span["replace_start"],
                        "replace_end": span["replace_end"],
                        "wrapped": False,
                        "is_substring": False,
                        "excluded": _is_excluded(ln, excluded),
                        "attached": ln in inst_lines if inst_lines else False,
                        "fuzzy": False,
                        "section": section_for_line(lines, ln),
                        "snippet": _snippet_for_line(
                            lines,
                            ln,
                            span["matched_text"],
                            replace_start=span["replace_start"],
                        ),
                    }
                )
        occ += 1

    occupied_lines = {m["line"] for m in by_key.values()}
    for sub in _naive_substring_lines(
        lines, anchor, occupied_lines, options=options, link_entry=link_entry
    ):
        _add_match(sub)

    return _dedupe_overlapping_matches(
        sorted(by_key.values(), key=lambda m: (m["line"], m.get("replace_start") or 0))
    )


def _fuzzy_whitespace_scan(
    body: str,
    anchor: str,
    lines: list[str],
    *,
    link_entry: dict | None,
    options: LinkTextSearchOptions,
    existing: dict[int, dict],
) -> list[dict]:
    excluded = (link_entry or {}).get("excluded") or []
    inst_lines = _instance_lines((link_entry or {}).get("instances"))
    extra: dict[int, dict] = {}

    for i, row in enumerate(lines):
        ln = i + 1
        if ln in existing:
            continue
        for col, _v_end, matched, rs, re in find_fuzzy_whitespace_spans_in_line(
            row,
            anchor,
            options=options,
            search_anchor=anchor,
            link_entry=link_entry,
        ):
            extra[ln] = {
                "line": ln,
                "col": col,
                "matched_text": matched,
                "replace_start": rs,
                "replace_end": re,
                "wrapped": False,
                "is_substring": False,
                "excluded": _is_excluded(ln, excluded),
                "attached": ln in inst_lines if inst_lines else False,
                "fuzzy": True,
                "section": section_for_line(lines, ln),
                "snippet": _snippet_for_line(
                    lines, ln, matched, replace_start=rs
                ),
            }
            break

    return [extra[k] for k in sorted(extra)]


def _spans_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def annotate_match_conflicts(
    matches: list[dict],
    body: str,
    sidecar_links: list | None,
    *,
    anchor_text: str,
    link_entry: dict | None,
    options: LinkTextSearchOptions,
) -> list[dict]:
    """若匹配区域与其它跳转入口的 [[…]] 重叠，标记为不可挂接。"""
    current = _route_sidecar_keys(link_entry, options)
    others: list[str] = []
    for link in sidecar_links or []:
        if not isinstance(link, dict):
            continue
        oa = str(link.get("anchor_text") or "").strip()
        if oa and oa not in current:
            others.append(oa)

    if not others:
        return matches

    lines = (body or "").split("\n")
    for m in matches:
        if m.get("is_substring") or m.get("excluded"):
            continue
        ln = int(m["line"])
        if ln < 1 or ln > len(lines):
            continue
        row = lines[ln - 1]
        rs = int(m.get("replace_start") if m.get("replace_start") is not None else m.get("col") or 0)
        matched = str(m.get("matched_text") or "")
        re = int(m.get("replace_end") if m.get("replace_end") is not None else rs + len(matched))

        for wl in scan_wikilinks(row):
            ws, we = wl["start"], wl["end"]
            if not _spans_overlap(rs, re, ws, we):
                continue
            tid = wl["target_id"]
            label = _link_label(wl)
            for oa in others:
                if _strict_anchor_equal(tid, oa, case_insensitive=options.case_insensitive) or _strict_anchor_equal(
                    label, oa, case_insensitive=options.case_insensitive
                ):
                    m["blocked"] = True
                    m["block_reason"] = f"与跳转「{oa}」占用区域重叠"
                    break
            if m.get("blocked"):
                break
    return matches


def scan_link_text_matches(
    body: str,
    anchor_text: str,
    lines: list[str] | None = None,
    *,
    link_entry: dict | None = None,
    search_options: dict | LinkTextSearchOptions | None = None,
    sidecar_links: list | None = None,
) -> list[dict]:
    """扫描正文中 anchor 的全部出现；``search_options`` 控制模糊规则。"""
    anchor = (anchor_text or "").strip()
    if not anchor or not body:
        return []

    options = (
        search_options
        if isinstance(search_options, LinkTextSearchOptions)
        else LinkTextSearchOptions.from_dict(search_options)
    )
    lines = lines if lines is not None else body.split("\n")

    exact = _exact_scan(body, anchor, lines, link_entry=link_entry, options=options)
    by_span = {
        (int(m["line"]), int(m.get("replace_start") if m.get("replace_start") is not None else m.get("col") or 0)): m
        for m in exact
    }
    out = list(exact)

    if options.fuzzy_whitespace:
        existing_by_line = {m["line"]: m for m in exact}
        for m in _fuzzy_whitespace_scan(
            body, anchor, lines, link_entry=link_entry, options=options, existing=existing_by_line
        ):
            key = (int(m["line"]), int(m.get("replace_start") if m.get("replace_start") is not None else m.get("col") or 0))
            if key not in by_span:
                by_span[key] = m
                out.append(m)

    out.sort(key=lambda m: (m["line"], m.get("replace_start") or 0))
    if sidecar_links:
        annotate_match_conflicts(
            out,
            body,
            sidecar_links,
            anchor_text=anchor,
            link_entry=link_entry,
            options=options,
        )
    return out


# ---------------------------------------------------------------------------
# 匹配文本推荐（搜索引擎占位）
# ---------------------------------------------------------------------------


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def _subsequence_score(query: str, candidate: str) -> float:
    if not query or not candidate:
        return 0.0
    qi = ci = 0
    while qi < len(query) and ci < len(candidate):
        if query[qi] == candidate[ci]:
            qi += 1
        ci += 1
    if qi == len(query):
        return 0.88
    return 0.0


def score_anchor_suggestion(
    query: str,
    candidate: str,
    *,
    options: LinkTextSearchOptions,
) -> float:
    q = normalize_query(query, options)
    c = normalize_query(candidate, options)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    if c.startswith(q):
        return 0.96
    cq = compact_text(q, case_insensitive=options.case_insensitive)
    cc = compact_text(c, case_insensitive=options.case_insensitive)
    if cq == cc:
        return 0.94
    if cc.startswith(cq):
        return 0.92
    sub = _subsequence_score(cq, cc)
    if sub:
        return sub
    if options.fuzzy_suggest and cq and cc and q[0] == c[0]:
        han_q = [ch for ch in query if "\u4e00" <= ch <= "\u9fff"]
        han_c = [ch for ch in candidate if "\u4e00" <= ch <= "\u9fff"]
        if han_q and han_c and han_q[0] == han_c[0]:
            base = 0.72
            lat_q = re.sub(r"[\s\u4e00-\u9fff]", "", query.lower())
            lat_c = re.sub(r"[\s\u4e00-\u9fff]", "", candidate.lower())
            if lat_q and lat_c:
                dist = _levenshtein(lat_q, lat_c)
                max_len = max(len(lat_q), len(lat_c), 1)
                lr = 1.0 - dist / max_len
                if lr >= 0.5:
                    return min(0.98, base + lr * 0.2)
            return base
    if options.fuzzy_suggest:
        dist = _levenshtein(cq, cc)
        max_len = max(len(cq), len(cc), 1)
        ratio = 1.0 - dist / max_len
        if ratio >= 0.55:
            return ratio * 0.85
    return 0.0


def collect_anchor_candidates(
    body: str,
    lines: list[str],
    sidecar_links: list | None,
) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []

    def add(text: str, source: str) -> None:
        t = (text or "").strip()
        if not t or len(t) > 120 or t in seen:
            return
        seen.add(t)
        out.append({"text": t, "source": source})

    for link in sidecar_links or []:
        if isinstance(link, dict):
            add(str(link.get("anchor_text") or ""), "sidecar")

    for wl in scan_wikilinks(body or ""):
        add(wikilink_label(wl["target_id"], wl.get("display")), "wikilink")
        add(wl["target_id"], "wikilink")

    for row in lines:
        s = row.strip()
        if s.startswith("#"):
            add(s.lstrip("#").strip(), "heading")

    return out


def suggest_link_anchor_texts(
    body: str,
    query: str,
    sidecar_links: list | None = None,
    *,
    lines: list[str] | None = None,
    search_options: dict | LinkTextSearchOptions | None = None,
    limit: int = 12,
) -> list[dict]:
    """根据用户输入推荐 canonical 匹配文本（选中后应替换输入框内容）。"""
    query = (query or "").strip()
    if not query:
        return []

    options = (
        search_options
        if isinstance(search_options, LinkTextSearchOptions)
        else LinkTextSearchOptions.from_dict(search_options)
    )
    lines = lines if lines is not None else (body or "").split("\n")
    candidates = collect_anchor_candidates(body, lines, sidecar_links)

    scored: list[dict] = []
    for item in candidates:
        text = item["text"]
        score = score_anchor_suggestion(query, text, options=options)
        if score <= 0:
            continue
        scored.append(
            {
                "text": text,
                "source": item["source"],
                "score": round(score, 3),
            }
        )

    scored.sort(key=lambda x: (-x["score"], x["text"]))
    return scored[: max(1, int(limit))]


def line_matched_spans(
    matches: list[dict], line_numbers: list[int]
) -> dict[int, tuple[int, str] | tuple[int, str, int]]:
    """从扫描结果提取行 → (col, matched_text) 或 (replace_start, matched_text, replace_end)。"""
    wanted = set(int(x) for x in line_numbers)
    out: dict[int, tuple[int, str] | tuple[int, str, int]] = {}
    for m in matches:
        ln = int(m["line"])
        if ln not in wanted:
            continue
        matched = str(m.get("matched_text") or "").strip()
        if not matched:
            continue
        rs = m.get("replace_start")
        re = m.get("replace_end")
        if rs is not None and re is not None:
            out[ln] = (int(rs), matched, int(re))
        else:
            out[ln] = (int(m.get("col") or 0), matched)
    return out


def resolve_canonical_anchor(
    anchor_text: str,
    matches: list[dict],
    selected_lines: list[int],
) -> str:
    """采用所选行正文 canonical 文本作为 anchor（优先于用户搜索词）。"""
    wanted = set(int(x) for x in selected_lines)
    texts: list[str] = []
    for m in matches:
        ln = int(m["line"])
        if ln not in wanted:
            continue
        t = str(m.get("matched_text") or "").strip()
        if t:
            texts.append(t)
    if not texts:
        return (anchor_text or "").strip()
    if len(wanted) == 1:
        return texts[0]
    if len(set(texts)) == 1:
        return texts[0]
    return (anchor_text or "").strip()
