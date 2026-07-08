"""Markdown 维基链接读写（M1.5 链接编辑器）。"""

from __future__ import annotations

from memoria.services.link_resolver import scan_wikilinks
from memoria.graph.edge_types import is_wikilink_edge_type_fragment


def format_wikilink(
    anchor: str,
    *,
    display: str | None = None,
    edge_hint: str | None = None,
) -> str:
    """格式化维基链接；``edge_hint`` 已废弃，类型仅存 sidecar，不写入正文。"""
    _ = edge_hint
    anchor = (anchor or "").strip()
    if not anchor:
        raise ValueError("anchor 不能为空")
    disp = (display or "").strip()
    inner = anchor
    if disp and disp != anchor:
        inner += f"|{disp}"
    return f"[[{inner}]]"


def strip_known_wikilink_edge_hints(body: str) -> tuple[str, int]:
    """移除正文中已注册边类型 fragment（``#prerequisite`` 等），保留非类型锚点。"""
    if not body:
        return body, 0
    count = 0
    parts: list[str] = []
    last = 0
    for link in scan_wikilinks(body):
        parts.append(body[last : link["start"]])
        hint = (link.get("edge_hint") or "").strip()
        if hint and is_wikilink_edge_type_fragment(hint):
            parts.append(
                format_wikilink(
                    link["target_id"],
                    display=link.get("display"),
                )
            )
            count += 1
        else:
            parts.append(link["raw"])
        last = link["end"]
    parts.append(body[last:])
    return "".join(parts), count


def wikilink_replacement_text(
    anchor: str,
    display: str | None = None,
    edge_hint: str | None = None,
) -> str:
    """移除 [[]] 后保留的文本：优先 display，否则 anchor。"""
    disp = (display or "").strip()
    if disp:
        return disp
    return (anchor or "").strip()


def _wikilink_matches_anchor(link: dict, anchor: str) -> bool:
    from memoria.services.link_resolver import wikilink_label

    anchor = (anchor or "").strip()
    if not anchor:
        return False
    if link["target_id"] == anchor:
        return True
    return wikilink_label(link["target_id"], link.get("display")) == anchor


def remove_wikilink_on_line(
    body: str,
    anchor: str,
    line_number: int,
) -> tuple[str, bool]:
    """移除指定行上的 [[anchor]]，保留显示文字。"""
    anchor = (anchor or "").strip()
    ln = int(line_number)
    if not anchor or ln < 1:
        return body, False
    for link in scan_wikilinks(body):
        if not _wikilink_matches_anchor(link, anchor):
            continue
        if body[: link["start"]].count("\n") + 1 != ln:
            continue
        repl = wikilink_replacement_text(
            link["target_id"],
            display=link.get("display") or anchor,
            edge_hint=link.get("edge_hint"),
        )
        return body[: link["start"]] + repl + body[link["end"] :], True
    return body, False


def remove_wikilink(
    body: str,
    anchor: str,
    *,
    display: str | None = None,
    edge_hint: str | None = None,
    occurrence: int = 0,
) -> tuple[str, bool]:
    anchor = (anchor or "").strip()
    if not anchor:
        return body, False
    found = scan_wikilinks(body)
    idx = 0
    for link in found:
        if not _wikilink_matches_anchor(link, anchor):
            continue
        if display is not None and (link.get("display") or None) != (display or None):
            continue
        if idx != occurrence:
            idx += 1
            continue
        repl = wikilink_replacement_text(
            anchor, display=link.get("display") or display, edge_hint=edge_hint
        )
        return body[: link["start"]] + repl + body[link["end"] :], True
    return body, False


def update_wikilink(
    body: str,
    old_anchor: str,
    *,
    new_anchor: str | None = None,
    display: str | None = None,
    edge_hint: str | None = None,
    old_display: str | None = None,
    old_edge_hint: str | None = None,
    occurrence: int = 0,
) -> tuple[str, bool]:
    old_anchor = (old_anchor or "").strip()
    if not old_anchor:
        return body, False
    found = scan_wikilinks(body)
    idx = 0
    for link in found:
        if link["target_id"] != old_anchor:
            continue
        if old_display is not None and (link.get("display") or None) != (old_display or None):
            continue
        if idx != occurrence:
            idx += 1
            continue
        anchor = (new_anchor or old_anchor).strip()
        disp = display if display is not None else link.get("display")
        new_raw = format_wikilink(anchor, display=disp)
        return body[: link["start"]] + new_raw + body[link["end"] :], True
    return body, False


def _is_plain_boundary(ch: str) -> bool:
    if not ch:
        return True
    if ch.isspace():
        return True
    if ch in "，。、；：！？（）【】《》""''[]()…—·":
        return True
    return False


# 匹配后允许紧跟的句内连接字（「查看二者在…」）；「击」等不算
_PLAIN_OK_AFTER = set("在与和的了或为以及而")


def _is_cjk_char(ch: str) -> bool:
    if not ch:
        return False
    o = ord(ch)
    return (
        0x4E00 <= o <= 0x9FFF
        or 0x3400 <= o <= 0x4DBF
        or 0xF900 <= o <= 0xFAFF
    )


def _is_cjk_only_anchor(anchor: str, *, min_len: int = 3) -> bool:
    """纯中文锚点（≥ min_len 字）。"""
    text = (anchor or "").strip()
    if len(text) < min_len:
        return False
    return all(_is_cjk_char(ch) for ch in text)


def _is_latin_token_anchor(anchor: str, *, min_len: int = 2) -> bool:
    """纯 ASCII 缩写/术语（如 SVD、PCA），可与中文词根连写：SVD技巧。"""
    text = (anchor or "").strip()
    if len(text) < min_len:
        return False
    return all(ch.isascii() and (ch.isalnum() or ch in "+-_./") for ch in text)


# 锚点后若紧跟这些字，视为词内续写不可挂接（如 按顺序点|击）
_FORBIDDEN_CJK_CONTINUATION = frozenset("击")


def _ok_plain_prefix(body: str, start: int, *, anchor: str | None = None) -> bool:
    if start <= 0:
        return True
    if not anchor or not _is_latin_token_anchor(anchor):
        return True
    ch = body[start - 1]
    if _is_plain_boundary(ch):
        return True
    if _is_cjk_char(ch):
        return True
    return False


def _ok_plain_suffix(body: str, end: int, *, anchor: str | None = None) -> bool:
    if end >= len(body):
        return True
    ch = body[end]
    if _is_plain_boundary(ch):
        return True
    if anchor and _is_cjk_only_anchor(anchor) and _is_cjk_char(ch):
        return ch not in _FORBIDDEN_CJK_CONTINUATION
    if anchor and _is_latin_token_anchor(anchor) and _is_cjk_char(ch):
        return True
    return ch in _PLAIN_OK_AFTER


def _wikilink_spans(body: str) -> list[tuple[int, int]]:
    return [(w["start"], w["end"]) for w in scan_wikilinks(body)]


def _overlaps_wikilink(pos: int, length: int, spans: list[tuple[int, int]]) -> bool:
    end = pos + length
    return any(pos < e and end > s for s, e in spans)


def find_plain_text(
    body: str, text: str, *, occurrence: int = 0
) -> int:
    """第 occurrence 次出现在 [[]] 外的 plain 文本位置，未找到返回 -1。"""
    text = (text or "").strip()
    if not text:
        return -1
    spans = _wikilink_spans(body)
    start = 0
    found = 0
    while start <= len(body):
        pos = body.find(text, start)
        if pos < 0:
            return -1
        if not _overlaps_wikilink(pos, len(text), spans) and _ok_plain_prefix(
            body, pos, anchor=text
        ) and _ok_plain_suffix(body, pos + len(text), anchor=text):
            if found == occurrence:
                return pos
            found += 1
        start = pos + 1
    return -1


def wrap_plain_text(
    body: str,
    text: str,
    anchor: str,
    *,
    display: str | None = None,
    edge_hint: str | None = None,
    occurrence: int = 0,
) -> tuple[str, bool]:
    text = (text or "").strip()
    anchor = (anchor or "").strip()
    if not text or not anchor:
        return body, False
    pos = find_plain_text(body, text, occurrence=occurrence)
    if pos < 0:
        return body, False
    disp = (display or "").strip()
    disp_for_fmt = disp if disp and disp != anchor else None
    new_raw = format_wikilink(anchor, display=disp_for_fmt)
    return body[:pos] + new_raw + body[pos + len(text) :], True
