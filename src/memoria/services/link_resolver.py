"""链接目标解析（M1）。"""

from __future__ import annotations

import re

from memoria.services.kp_index import build_kp_index, entry_to_dict

_WIKILINK_RE = re.compile(
    r"\[\[([^\]|#\]]+)(?:#([^\]|#]+))?(?:\|([^\]]+))?\]\]"
)


def parse_wikilink(raw: str) -> dict | None:
    m = _WIKILINK_RE.fullmatch(raw.strip())
    if not m:
        return None
    return {
        "target_id": m.group(1).strip(),
        "edge_hint": (m.group(2) or "").strip() or None,
        "display": (m.group(3) or "").strip() or None,
    }


def scan_wikilinks(body: str) -> list[dict]:
    found: list[dict] = []
    for m in _WIKILINK_RE.finditer(body or ""):
        found.append(
            {
                "raw": m.group(0),
                "target_id": m.group(1).strip(),
                "edge_hint": (m.group(2) or "").strip() or None,
                "display": (m.group(3) or "").strip() or None,
                "start": m.start(),
                "end": m.end(),
            }
        )
    return found


def resolve_link_target(kb_path: str, target_id: str) -> dict:
    """按 KP id 或文件 stem 解析跳转目标。"""
    target_id = (target_id or "").strip()
    if not target_id:
        return {"status": "error", "message": "空链接目标", "candidates": []}

    index = build_kp_index(kb_path)
    by_id = index["by_id"]
    file_stems: dict[str, str] = index["file_stems"]

    if target_id in by_id:
        candidates = [entry_to_dict(e) for e in by_id[target_id]]
        if len(candidates) == 1:
            return {"status": "ok", "candidates": candidates, "match": "kp_id"}
        return {"status": "ambiguous", "candidates": candidates, "match": "kp_id"}

    if target_id in file_stems:
        rel = file_stems[target_id]
        file_entries = [e for e in index["entries"] if e.file == rel]
        preferred = next((e for e in file_entries if e.kp_id == target_id), None)
        if preferred:
            return {
                "status": "ok",
                "candidates": [entry_to_dict(preferred)],
                "match": "file_stem",
            }
        if file_entries:
            first = file_entries[0]
            return {
                "status": "ok",
                "candidates": [
                    {
                        "file": rel,
                        "kp_id": first.kp_id,
                        "name": first.name,
                        "range_ok": first.range_ok,
                        "start_line": first.start_line,
                        "end_line": first.end_line,
                    }
                ],
                "match": "file_stem",
            }
        return {
            "status": "ok",
            "candidates": [
                {
                    "file": rel,
                    "kp_id": None,
                    "name": target_id,
                    "range_ok": False,
                    "start_line": None,
                    "end_line": None,
                }
            ],
            "match": "file_stem",
        }

    return {
        "status": "not_found",
        "message": f"未找到知识点或文件: {target_id}",
        "candidates": [],
    }


def wikilink_label(target_id: str, display: str | None = None) -> str:
    """用户可见的链接标签：有 | 显示文字时用显示文字，否则用目标键。"""
    d = (display or "").strip()
    return d if d else (target_id or "").strip()


def _pick_canonical_anchor(anchors: set[str], label: str) -> str:
    """同标签多写法时，优先短虚拟 id（如 nav-*）。"""
    anchors = {a.strip() for a in anchors if a and a.strip()}
    if not anchors:
        return label
    nav = sorted(a for a in anchors if a.startswith("nav-"))
    if nav:
        return nav[0]
    ascii_ids = sorted(
        a for a in anchors if a != label and not any("\u4e00" <= c <= "\u9fff" for c in a)
    )
    if ascii_ids:
        return ascii_ids[0]
    return sorted(anchors, key=len)[0]


def build_link_overrides(sidecar: dict | None, body: str | None = None) -> dict[str, list[str]]:
    """侧车 links[] + 正文同标签别名 → 维基链接 target id → targets。"""
    raw: dict[str, list[str]] = {}
    for link in (sidecar or {}).get("links") or []:
        if not isinstance(link, dict):
            continue
        anchor = str(link.get("anchor_text") or "").strip()
        targets = link.get("targets") or []
        if not anchor or not isinstance(targets, list):
            continue
        cleaned = [str(t).strip() for t in targets if str(t).strip()]
        if cleaned:
            raw[anchor] = cleaned

    if not body:
        return raw

    label_to_anchors: dict[str, set[str]] = {}
    for w in scan_wikilinks(body):
        tid = w["target_id"]
        label = wikilink_label(tid, w.get("display"))
        label_to_anchors.setdefault(label, set()).add(tid)
        if tid in raw:
            label_to_anchors.setdefault(label, set()).add(tid)

    overrides = dict(raw)
    for label, anchors in label_to_anchors.items():
        merged: list[str] = []
        seen: set[str] = set()
        for a in sorted(anchors):
            for t in raw.get(a, []):
                if t not in seen:
                    seen.add(t)
                    merged.append(t)
        if label in raw:
            for t in raw[label]:
                if t not in seen:
                    seen.add(t)
                    merged.append(t)
        if not merged:
            continue
        for a in anchors:
            overrides[a] = merged
        if label not in anchors:
            overrides[label] = merged
    return overrides


def collect_link_alias_anchors(
    body: str,
    anchor_text: str,
    display_text: str | None = None,
) -> tuple[str, set[str]]:
    """正文内同显示标签的所有目标键 + 规范 anchor。"""
    label = wikilink_label(anchor_text, display_text)
    anchors: set[str] = set()
    for w in scan_wikilinks(body or ""):
        if wikilink_label(w["target_id"], w.get("display")) == label:
            anchors.add(w["target_id"])
    anchors.add((anchor_text or "").strip())
    if display_text and display_text.strip():
        anchors.add(display_text.strip())
    canonical = _pick_canonical_anchor(anchors, label)
    return canonical, anchors


def resolve_link_targets(kb_path: str, target_ids: list[str]) -> dict:
    """解析多个链接目标（多目标链接选择）。"""
    candidates: list[dict] = []
    for tid in target_ids:
        tid = (tid or "").strip()
        if not tid:
            continue
        res = resolve_link_target(kb_path, tid)
        if res.get("status") == "ok" and res.get("candidates"):
            c = dict(res["candidates"][0])
            c["requested_id"] = tid
            candidates.append(c)
        elif res.get("status") == "ambiguous":
            for c in res.get("candidates") or []:
                item = dict(c)
                item["requested_id"] = tid
                candidates.append(item)
    if not candidates:
        return {
            "status": "not_found",
            "message": "多目标链接均无法解析",
            "candidates": [],
        }
    if len(candidates) == 1:
        return {"status": "ok", "candidates": candidates}
    return {"status": "multi", "candidates": candidates}


def build_target_lookup(kb_path: str) -> dict:
    """供前端标记链接是否可解析。"""
    index = build_kp_index(kb_path)
    kp_ids = sorted(index["by_id"].keys())
    file_stems = sorted(index["file_stems"].keys())
    return {
        "kp_ids": kp_ids,
        "file_stems": file_stems,
        "resolved_targets": sorted(set(kp_ids) | set(file_stems)),
    }


def build_target_lookup_from(kp_ids: set[str] | None, file_stems: dict[str, str] | None) -> dict:
    """G5：由全库轻量快照构造（读路径零构建，见 kp_index.kp_targets_snapshot）。"""
    ids = sorted(kp_ids or ())
    stems = sorted((file_stems or {}).keys())
    return {
        "kp_ids": ids,
        "file_stems": stems,
        "resolved_targets": sorted(set(ids) | set(stems)),
    }
