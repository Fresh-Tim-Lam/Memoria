#!/usr/bin/env python3
"""为独立样例库 example-boonie/ 生成侧车 YAML。"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from memoria.range.constants import SNIPPET_MAX_LEN
from memoria.storage.markdown import strip_frontmatter

ROOT = Path(__file__).resolve().parents[1]
KB_ROOT = ROOT / "example-boonie"
SIDECAR_DIR = KB_ROOT / ".memoria" / "sidecars"

# rel_path (相对 KB 根) -> (kp_id, name, start_heading, end_snippet_substr)
KP_SPECS: dict[str, list[tuple[str, str, str, str]]] = {
    "dog-xiong-ridge.md": [
        ("gou-xiong-ling", "狗熊岭", "## 狗熊岭", "也是[[熊大]]、[[熊二]]的家园。"),
        ("big-forest", "大森林", "## 大森林", "常发生在这片森林。"),
        ("forest-ranger", "护林员", "### 护林员", "保护[[大森林]]。"),
    ],
    "guang-tou-qiang.md": [
        ("guang-tou-qiang", "光头强", "## 光头强", "也在危难时互相帮助。"),
        ("inventions", "光头强的发明", "## 光头强的发明", "或因操作失误而失败。"),
        ("fei-die", "飞碟", "### 飞碟", "最终引发[[飞碟坠落事件]]。"),
    ],
    "bear-brothers.md": [
        ("xiong-da", "熊大", "## 熊大", "可是很聪明的」。"),
        ("xiong-er", "熊二", "## 熊二", "软化[[光头强]]。"),
        ("protect-forest", "保护森林", "## 保护森林", "应对偷猎者或灾害。"),
    ],
    "inventions-and-events.md": [
        ("super-felling", "超级伐木机", "## 超级伐木机", "因过载自毁。"),
        ("shrink-ray", "缩小射线", "## 缩小射线", "才恢复原状。"),
        ("ufo-crash", "飞碟坠落事件", "## 飞碟坠落事件", "飞碟彻底报废。"),
        ("qiang-xiong-rivalry", "强熊对立", "## 强熊对立", "喜剧与温情的来源。"),
    ],
    "minor-characters.md": [
        ("big-monkey-er-gou", "大马猴和二狗", "## 大马猴和二狗", "最终变成笑料。"),
        ("fei-bo", "肥波", "## 肥波", "误以为它是间谍。"),
    ],
}

TARGET_MAP = {
    "狗熊岭": ["gou-xiong-ling"],
    "大森林": ["big-forest"],
    "光头强": ["guang-tou-qiang"],
    "熊大": ["xiong-da"],
    "熊二": ["xiong-er"],
    "熊兄弟": ["xiong-da", "xiong-er"],
    "超级伐木机": ["super-felling"],
    "缩小射线": ["shrink-ray"],
    "飞碟坠落事件": ["ufo-crash"],
    "飞碟": ["fei-die"],
    "强熊对立": ["qiang-xiong-rivalry"],
    "保护森林": ["protect-forest"],
    "大马猴和二狗": ["big-monkey-er-gou"],
    "肥波": ["fei-bo"],
    "李老板": [],
}


def find_line(lines: list[str], needle: str, *, from_line: int = 1) -> int:
    for i in range(from_line - 1, len(lines)):
        if needle in lines[i]:
            return i + 1
    raise ValueError(f"not found: {needle!r} in {lines}")


def snippet_at(lines: list[str], line_no: int) -> str:
    return lines[line_no - 1].strip()[:SNIPPET_MAX_LEN]


def _resolve_targets(anchor: str, raw: str) -> list[str]:
    if anchor in TARGET_MAP:
        t = TARGET_MAP[anchor]
        return t if t else []
    if raw in TARGET_MAP:
        t = TARGET_MAP[raw]
        return t if t else []
    return []


def _source_kp_for_line(line_no: int, kps: list[dict]) -> str | None:
    for kp in kps:
        s = kp["range"]["start"]["line_hint"]
        e = kp["range"]["end"]["line_hint"]
        if s <= line_no <= e:
            return kp["id"]
    return kps[0]["id"] if kps else None


def scan_links(body: str, kps: list[dict]) -> list[dict]:
    lines = body.splitlines()
    links: list[dict] = []
    for line_no, line in enumerate(lines, 1):
        for m in re.finditer(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]", line):
            anchor = (m.group(2) or m.group(1)).strip()
            raw = m.group(1).strip()
            targets = _resolve_targets(anchor, raw)
            if not targets:
                continue
            source = _source_kp_for_line(line_no, kps)
            if not source:
                continue
            links.append(
                {
                    "anchor_text": anchor,
                    "occurrence": 0,
                    "targets": targets,
                    "edge_type": "reference",
                    "instances": [{"line": line_no, "wrapped": True}],
                    "source_id": source,
                }
            )
    seen: set[tuple] = set()
    out: list[dict] = []
    for lk in links:
        key = (lk["anchor_text"], lk["source_id"], tuple(lk["targets"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(lk)
    return out


def build_sidecar(rel: str, specs: list[tuple]) -> dict:
    md_path = KB_ROOT / rel
    raw = md_path.read_text(encoding="utf-8")
    body, _ = strip_frontmatter(raw)
    lines = body.splitlines()
    kps: list[dict] = []
    prev_end = 0
    for kp_id, name, start_heading, end_needle in specs:
        start_line = find_line(lines, start_heading, from_line=max(1, prev_end))
        end_line = find_line(lines, end_needle, from_line=start_line)
        kps.append(
            {
                "id": kp_id,
                "name": name,
                "range": {
                    "start": {"snippet": snippet_at(lines, start_line), "line_hint": start_line},
                    "end": {"snippet": snippet_at(lines, end_line), "line_hint": end_line},
                },
            }
        )
        prev_end = end_line
    return {
        "schema_version": 1,
        "file": rel,
        "knowledge_points": kps,
        "links": scan_links(body, kps),
    }


def main() -> None:
    SIDECAR_DIR.mkdir(parents=True, exist_ok=True)
    for rel, specs in KP_SPECS.items():
        data = build_sidecar(rel, specs)
        out = SIDECAR_DIR / f"{Path(rel).stem}.memoria.yaml"
        out.write_text(
            yaml.dump(data, allow_unicode=True, sort_keys=False, width=88),
            encoding="utf-8",
        )
        print("wrote", out.relative_to(ROOT))
    empty = {
        "schema_version": 1,
        "file": "_nothing-here.md",
        "knowledge_points": [],
        "links": [],
    }
    p = SIDECAR_DIR / "_nothing-here.memoria.yaml"
    p.write_text(yaml.dump(empty, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print("wrote", p.relative_to(ROOT))


if __name__ == "__main__":
    main()
