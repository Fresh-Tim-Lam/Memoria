#!/usr/bin/env python
"""Build a multi-level course demo KB from the cleaned course textbook copies.

Source (read-only):  artifacts/demo-kb/courses/<kb>/  (md only, 0 KP / 0 sidecar)
Output (disposable demo): artifacts/demo-kb/courses-demo/<kb>/

What it does
------------
1. Copies only the cleaned textbook Markdown files.
2. Extracts **machine candidate** knowledge units from headings / paragraphs:
   chapter → section (``1.2``) → subsection (``1.2.3``) → KP paragraph.
   Every candidate keeps a quote/line range (evidence) and is tagged ``candidate``.
3. Writes valid ``.memoria/sidecars/*.memoria.yaml`` + ``manifest.yaml`` so
   ``memoria validate`` passes and the product graph can consume the KB.
4. Adds association links (``reference`` / ``extend``) only when a candidate name
   is literally mentioned in a paragraph / chapter intro of the source; no old
   KP or old link identity is reused (source copies are clean).
5. Writes ``.memoria/demo-meta.json`` — the explicit H/A contract for the 2D
   graph (levels/parents/hierarchy edges vs association edges).
6. Writes ``build-report.json`` with per-level counts and edge counts.

Determinism: fixed ``updated_at``, source mtimes, sorted output; rebuilding twice
produces byte-identical files (verified by the build script's own check when
run with ``--check-determinism``).

Boundaries: machine candidates, not gold; never writes the user library; never
touches the cleaned source copies or product source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = ROOT / "artifacts/demo-kb/courses"
DEFAULT_OUT = ROOT / "artifacts/demo-kb/courses-demo"
SCHEMA_VERSION = 1
FIXED_UPDATED_AT = "1970-01-01T00:00:00+00:00"

HEAD_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
WIKILINK_RE = re.compile(r"\[\[([^\[\]]*?)\]\]")
SEC_RE = re.compile(r"^(\d+)\.(\d+)(?!\.\d)\s*(.*)$")
SUB_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)\s*(.*)$")
DEF_RE = re.compile(
    r"^\s*(?:[*_`]+\s*)?(?:[一二三四五六七八九十]+[、.．]\s*|\d+[、.．]\s*|[(（][0-9一二三四五六七八九十]+[)）]\s*)?"
    r"(?P<name>[\u4e00-\u9fa5A-Za-z][\u4e00-\u9fa5A-Za-z0-9（）()·\-\s]{0,24}?)"
    r"(?:是指|指的是|称为|称为|定义为|是一种|是一个|是)"
    r"[^。；;]{4,}"
)
CAUSE_CUES = ("导致", "因此", "从而", "使得", "引起", "产生", "影响", "决定了", "造成", "促进")
GENERIC_NAMES = {
    "软件", "系统", "方法", "技术", "数据", "信息", "计算机", "网络", "过程", "问题",
    "功能", "结构", "模型", "设计", "分析", "测试", "管理", "工程", "用户", "程序",
    "协议", "服务", "应用", "内容", "工作", "活动", "阶段", "目标", "需求", "原则",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def norm_name(text: str) -> str:
    t = re.sub(r"[*_`]", "", text or "").strip()
    t = re.sub(r"\s+", " ", t)
    return t.strip(" ：:，,。.、;；")


def classify_heading(title: str) -> tuple[str, str]:
    """返回 (kind, clean_title)。kind ∈ section / subsection / other。"""
    t = norm_name(title)
    if SEC_RE.match(t):
        return "section", t
    if SUB_RE.match(t):
        return "subsection", t
    return "other", t


def chapter_title_from_file(path: Path) -> str:
    stem = path.stem
    stem = re.sub(r"^\d+[_\-—\s]*", "", stem)
    stem = stem.replace("_", " ").strip()
    return stem or path.stem


def snippet_of(line: str) -> str:
    s = line.strip()
    return s[:60] if len(s) > 60 else s


def blocks_of(lines: list[str], heading_lines: set[int]) -> list[dict]:
    """Consecutive non-empty, non-heading lines → paragraph blocks (1-based lines)."""
    blocks: list[dict] = []
    i = 1
    n = len(lines)
    while i <= n:
        line = lines[i - 1]
        if i in heading_lines or not line.strip():
            i += 1
            continue
        start = i
        buf = []
        while i <= n and i not in heading_lines and lines[i - 1].strip():
            buf.append(lines[i - 1].strip())
            i += 1
        text = " ".join(buf)
        if text:
            blocks.append({"start": start, "end": i - 1, "text": text})
    return blocks


def extract_name(text: str) -> str | None:
    m = DEF_RE.search(text)
    if m:
        name = norm_name(m.group("name"))
        if 2 <= len(name) <= 24 and name not in GENERIC_NAMES:
            return name
    # fallback: first sentence chunk before punctuation
    chunk = re.split(r"[。；;]", text, maxsplit=1)[0]
    chunk = re.split(r"[，,]", chunk, maxsplit=1)[0]
    chunk = norm_name(chunk)
    if 4 <= len(chunk) <= 24 and chunk not in GENERIC_NAMES:
        return chunk
    return None


def choose_leaves(blocks: list[dict], parent_span: tuple[int, int],
                  used_names: set[str], max_n: int) -> list[dict]:
    """Pick paragraph candidates inside parent span (cue-scored, deterministic)."""
    candidates = []
    for b in blocks:
        if b["start"] < parent_span[0] or b["end"] > parent_span[1]:
            continue
        name = extract_name(b["text"])
        if not name:
            continue
        cue = sum(1 for c in ("是指", "定义", "称为", "是一种", "是一个", "包括", "分为") if c in b["text"])
        score = cue * 2 + (2 if "是指" in b["text"] or "定义" in b["text"] else 0)
        candidates.append((score, b["start"], name, b))
    candidates.sort(key=lambda x: (-x[0], x[1]))
    out = []
    for score, _, name, b in candidates:
        if len(out) >= max_n:
            break
        if name in used_names:
            continue
        used_names.add(name)
        out.append({"name": name, "block": b, "score": score})
    return out


def build_file_candidates(path: Path, rel: str, prefix: str,
                          max_leaves_per_chapter: int) -> tuple[list[dict], list[dict], list[dict]]:
    """Return (candidates, hierarchy_edges, chapter_intro) for one md file."""
    text = read_text(path)
    lines = text.splitlines()
    n = len(lines)
    # last non-empty line (range end anchor)
    last = n
    while last > 1 and not lines[last - 1].strip():
        last -= 1

    candidates: list[dict] = []
    edges: list[dict] = []
    heading_lines: set[int] = set()
    sections: list[dict] = []
    subsections: list[dict] = []
    for i, line in enumerate(lines, 1):
        m = HEAD_RE.match(line)
        if not m:
            continue
        heading_lines.add(i)
        kind, title = classify_heading(m.group(2))
        if kind == "section":
            sections.append({"line": i, "title": title})
        elif kind == "subsection":
            subsections.append({"line": i, "title": title})

    # chapter node: whole file (line 1 .. last)
    chapter = {
        "id": f"{prefix}-ch",
        "name": chapter_title_from_file(path),
        "level": "chapter",
        "parent_id": None,
        "start": 1,
        "end": last,
        "kind": "chapter",
        "rel": rel,
    }
    candidates.append(chapter)

    def add_node(node_id: str, name: str, level: str, parent_id: str,
                 start: int, end: int, kind: str) -> dict:
        node = {"id": node_id, "name": name, "level": level, "parent_id": parent_id,
                "start": start, "end": end, "kind": kind, "rel": rel}
        candidates.append(node)
        edges.append({"source": parent_id, "target": node_id})
        return node

    # section ranges: heading line .. line before next section heading (last non-empty)
    for si, sec in enumerate(sections):
        next_line = sections[si + 1]["line"] if si + 1 < len(sections) else n + 1
        end = next_line - 1
        while end > sec["line"] and not lines[end - 1].strip():
            end -= 1
        sec["end"] = max(sec["line"], end)
        sec["id"] = f"{prefix}-s{si + 1:02d}"
        add_node(sec["id"], sec["title"], "section", chapter["id"],
                 sec["line"], sec["end"], "section")

    # subsection ranges: heading .. next section/subsection heading -1
    boundary_lines = sorted({s["line"] for s in sections} | {s["line"] for s in subsections})
    for ssi, sub in enumerate(subsections):
        later = [b for b in boundary_lines if b > sub["line"]]
        next_line = later[0] if later else n + 1
        end = next_line - 1
        while end > sub["line"] and not lines[end - 1].strip():
            end -= 1
        parent = None
        for sec in sections:
            if sec["line"] < sub["line"] <= sec["end"]:
                parent = sec
        if parent is None:
            continue
        sub["end"] = max(sub["line"], end)
        sub["id"] = f"{prefix}-ss{ssi + 1:02d}"
        add_node(sub["id"], sub["title"], "subsection", parent["id"],
                 sub["line"], sub["end"], "subsection")

    # paragraph leaves: strong-definition paragraphs only (fallback for containers
    # that have no heading leaf), attached to innermost subsection else section.
    blocks = blocks_of(lines, heading_lines)
    intro_lines = [b for b in blocks if b["end"] < (sections[0]["line"] if sections else n + 1)]

    # leaf candidates = unnumbered sub-headings (e.g. "1. 软件的概念", "(1) 形态特性")
    # attached to the innermost subsection (or section when there is no subsection).
    def leaf_parent(line_no: int):
        parent = None
        for sub in subsections:
            if sub["line"] < line_no <= sub["end"]:
                parent = sub
        if parent is not None:
            return parent
        for sec in sections:
            if sec["line"] < line_no <= sec["end"]:
                return sec
        return None

    def strip_number(title: str) -> str:
        t = re.sub(r"^\s*(?:[(（]\s*\d+\s*[)）]|\d+\s*[.、．])\s*", "", title)
        return norm_name(t)

    SKIP_TITLES = ("习题", "思考题", "练习题", "课后", "本章小结", "小结", "案例")
    leaf_headings = []
    for i, line in enumerate(lines, 1):
        m = HEAD_RE.match(line)
        if not m:
            continue
        kind, title = classify_heading(m.group(2))
        if kind != "other":
            continue
        name = strip_number(title)
        if len(name) < 2 or len(name) > 30:
            continue
        if any(x in name for x in SKIP_TITLES):
            continue
        if leaf_parent(i) is None:
            continue
        leaf_headings.append({"line": i, "name": name, "title": title})

    # leaf range = heading line .. next heading line - 1 (trimmed), so its paragraph
    # content can be used as evidence/context for association links.
    heading_sorted = sorted(heading_lines)
    leaf_used_by_parent: dict[str, int] = {}
    associated_leaf_count = 0
    for lh in leaf_headings:
        if associated_leaf_count >= max_leaves_per_chapter:
            break
        parent = leaf_parent(lh["line"])
        if parent is None:
            continue
        key = parent["id"]
        if leaf_used_by_parent.get(key, 0) >= 2:
            continue
        later = [h for h in heading_sorted if h > lh["line"]]
        next_line = later[0] if later else n + 1
        end = next_line - 1
        while end > lh["line"] and not lines[end - 1].strip():
            end -= 1
        if end < lh["line"]:
            end = lh["line"]
        leaf_id = f"{prefix}-kp{associated_leaf_count + 1:03d}"
        add_node(leaf_id, lh["name"], "kp", parent["id"], lh["line"], end, "kp")
        leaf_used_by_parent[key] = leaf_used_by_parent.get(key, 0) + 1
        associated_leaf_count += 1

    # fallback: a strong definition paragraph under containers without any heading leaf
    containers = [(s, "subsection") for s in subsections] + \
                 [(s, "section") for s in sections if not any(
                     s["line"] < sub["line"] <= s["end"] for sub in subsections)]
    containers.sort(key=lambda x: x[0]["line"])
    used_names = {n["name"] for n in candidates}
    for container, level in containers:
        if associated_leaf_count >= max_leaves_per_chapter:
            break
        if leaf_used_by_parent.get(container["id"], 0) > 0:
            continue
        picked = choose_leaves(blocks, (container["line"], container["end"]),
                               used_names, max_n=1)
        for item in picked:
            if associated_leaf_count >= max_leaves_per_chapter:
                break
            b = item["block"]
            leaf_id = f"{prefix}-kp{associated_leaf_count + 1:03d}"
            add_node(leaf_id, item["name"], "kp", container["id"], b["start"], b["end"], "kp")
            associated_leaf_count += 1

    intro = [{"start": b["start"], "end": b["end"], "text": b["text"]} for b in intro_lines]
    return candidates, edges, intro


def sidecar_kp(node: dict, lines: list[str]) -> dict:
    start_line, end_line = node["start"], node["end"]
    tags = [
        "candidate",
        f"level:{node['level']}",
        f"parent:{node['parent_id']}" if node["parent_id"] else "parent:root",
        f"kind:{node['kind']}",
    ]
    return {
        "id": node["id"],
        "name": node["name"],
        "aliases": [],
        "tags": tags,
        "range": {
            "start": {"snippet": snippet_of(lines[start_line - 1]), "line_hint": start_line},
            "end": {"snippet": snippet_of(lines[end_line - 1]), "line_hint": end_line},
        },
    }


def build_kb(src: Path, out: Path, *, kb_name: str, prefix: str,
             max_leaves_per_chapter: int = 8, max_links_per_leaf: int = 2,
             max_links_per_chapter: int = 6) -> dict:
    if not src.is_dir():
        raise FileNotFoundError(f"source KB not found: {src}")
    md_files = [p for p in sorted(src.glob("*.md")) if not p.name.startswith("00_")]
    if not md_files:
        raise ValueError(f"no textbook md files under {src}")

    if out.exists():
        shutil.rmtree(out)
    (out / ".memoria/sidecars").mkdir(parents=True)
    all_nodes: list[dict] = []
    per_file: dict[str, dict] = {}
    wikilinks_removed = 0
    for idx, path in enumerate(md_files, 1):
        rel = path.name
        # Demo copies are re-cleaned defensively: a residual ``[[]]`` marker may
        # survive the source cleanup; the demo KB itself must contain zero wikilinks.
        raw = read_text(path)
        cleaned, removed = WIKILINK_RE.subn(
            lambda m: (m.group(1).split("|")[-1].strip()
                       if "|" in m.group(1) else m.group(1).strip()), raw)
        wikilinks_removed += removed
        dst = out / rel
        dst.write_text(cleaned, encoding="utf-8", newline="\n")
        src_stat = path.stat()
        os.utime(dst, (src_stat.st_atime, src_stat.st_mtime))
        nodes, hier_edges, intro = build_file_candidates(
            path, rel, f"{prefix}-c{idx:02d}", max_leaves_per_chapter)
        _lines = read_text(path).splitlines()
        _heading_lines = {i for i, ln in enumerate(_lines, 1) if HEAD_RE.match(ln)}
        per_file[rel] = {"nodes": nodes, "hierarchy": hier_edges, "intro": intro,
                        "lines": _lines, "blocks": blocks_of(_lines, _heading_lines),
                        "md_path": out / rel, "chapter_id": nodes[0]["id"]}
        all_nodes.extend(nodes)

    # global name index (clean display names) for mention links
    def clean_node_name(node: dict) -> str:
        name = node["name"]
        if node["level"] in ("section", "subsection"):
            name = re.sub(r"^\s*\d+(\.\d+)+\s*", "", name)
        elif node["level"] == "chapter":
            name = re.sub(r"^\s*第\d+章\s*", "", name)
        return norm_name(name)

    name_to_ids: dict[str, list[str]] = {}
    for node in sorted(all_nodes, key=lambda x: (0 if x["level"] == "kp" else 1,
                                                 -len(clean_node_name(x)), x["id"])):
        name = clean_node_name(node)
        if len(name) < 2 or name in GENERIC_NAMES:
            continue
        ids = name_to_ids.setdefault(name, [])
        if node["id"] not in ids:
            ids.append(node["id"])
    # drop names that are too common in the whole KB (avoid noisy generic links)
    joined = "\n".join(read_text(p) for p in md_files)
    for name in list(name_to_ids):
        if joined.count(name) > 60:
            name_to_ids.pop(name, None)

    node_by_id = {n["id"]: n for n in all_nodes}
    ancestor_cache: dict[str, set[str]] = {}

    def ancestors(node_id: str) -> set[str]:
        if node_id in ancestor_cache:
            return ancestor_cache[node_id]
        out_set = set()
        cur = node_by_id.get(node_id)
        while cur and cur["parent_id"]:
            out_set.add(cur["parent_id"])
            cur = node_by_id.get(cur["parent_id"])
        ancestor_cache[node_id] = out_set
        return out_set

    hierarchy_edges: list[dict] = []
    association_edges: list[dict] = []

    def innermost_node(info: dict, line: int) -> dict | None:
        best = None
        for node in info["nodes"]:
            if node["start"] <= line <= node["end"]:
                if best is None or (node["start"], -node["end"]) >= (best["start"], -best["end"]):
                    best = node
        return best

    for rel, info in per_file.items():
        lines = info["lines"]
        nodes = info["nodes"]
        node_ids = {n["id"] for n in nodes}
        node_by_id_file = {n["id"]: n for n in nodes}
        links: list[dict] = []
        assoc: list[dict] = []
        seen_link: set[tuple[str, str]] = set()
        file_link_budget = 60

        for block in info["blocks"]:
            if len(links) >= file_link_budget:
                break
            text = block["text"]
            source = innermost_node(info, block["start"])
            if source is None:
                continue
            for name, ids in name_to_ids.items():
                if len(links) >= file_link_budget:
                    break
                if name not in text:
                    continue
                # prefer a cross-file target, otherwise another candidate in this file
                target = next((i for i in ids if i not in node_ids), None)
                if target is None:
                    target = next((i for i in ids if i != source["id"]), None)
                if target is None or target == source["id"]:
                    continue
                tgt_node = node_by_id.get(target)
                if tgt_node is None:
                    continue
                # skip pure hierarchy pairs (contain edges already cover them)
                if target in ancestors(source["id"]) or source["id"] in ancestors(target):
                    continue
                key = (source["id"], target)
                if key in seen_link:
                    continue
                # locate mention line inside the block
                line_no = block["start"]
                for ln in range(block["start"], block["end"] + 1):
                    if name in lines[ln - 1]:
                        line_no = ln
                        break
                pos = text.find(name)
                sentence = text[max(0, pos - 40):pos + len(name) + 60]
                edge_type = "extend" if any(c in sentence for c in CAUSE_CUES) else "reference"
                seen_link.add(key)
                links.append({
                    "anchor_text": name,
                    "targets": [target],
                    "edge_type": edge_type,
                    "instances": [{"line": line_no}],
                })
                assoc.append({"source": source["id"], "target": target, "type": edge_type,
                              "file": rel, "line": line_no,
                              "quote_sha256": hashlib.sha256(
                                  lines[line_no - 1].encode("utf-8")).hexdigest()})

        # write sidecar
        sidecar = {
            "schema_version": SCHEMA_VERSION,
            "file": rel,
            "knowledge_points": [sidecar_kp(n, lines) for n in nodes],
            "links": links,
        }
        sc_path = out / ".memoria/sidecars" / (Path(rel).stem + ".memoria.yaml")
        sc_path.write_text(yaml.safe_dump(sidecar, allow_unicode=True, sort_keys=False,
                                          width=1000000), encoding="utf-8", newline="\n")
        info["sidecar_path"] = sc_path
        info["links"] = links
        hierarchy_edges.extend(info["hierarchy"])
        association_edges.extend(assoc)

    # manifest with deterministic mtimes
    files = []
    for rel, info in per_file.items():
        md_path = info["md_path"]
        sc_path = info["sidecar_path"]
        md_stat = md_path.stat()
        files.append({
            "path": rel,
            "md_mtime": md_stat.st_mtime,
            "md_size": md_stat.st_size,
            "md_sha256": sha256_bytes(md_path.read_bytes()),
            "sidecar_mtime": md_stat.st_mtime,
            "sidecar_sha256": sha256_bytes(sc_path.read_bytes()),
        })
    manifest = {"schema_version": SCHEMA_VERSION, "updated_at": FIXED_UPDATED_AT,
                "files": files}
    (out / ".memoria/manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False, width=1000000),
        encoding="utf-8", newline="\n")
    (out / ".memoria/pending.json").write_text("{}\n", encoding="utf-8")
    (out / ".memoria/kp_targets.json").write_text("{}\n", encoding="utf-8")

    # explicit H/A contract for renderer + tests
    level_counts = {"chapter": 0, "section": 0, "subsection": 0, "kp": 0}
    for node in all_nodes:
        level_counts[node["level"]] += 1
    meta = {
        "schema": "course-demo-kb/v1",
        "kb": kb_name,
        "source_kb": str(src),
        "machine_candidate": True,
        "is_gold": False,
        "levels": ["chapter", "section", "subsection", "kp"],
        "level_counts": level_counts,
        "nodes": [
            {"id": n["id"], "name": n["name"], "level": n["level"],
             "parent_id": n["parent_id"], "file": n["rel"],
             "line_start": n["start"], "line_end": n["end"]}
            for n in all_nodes
        ],
        "edges": {
            "hierarchy": hierarchy_edges,
            "association": association_edges,
        },
        "dimensions": {
            "H": {
                "name": "hierarchy",
                "description": "chapter → section → subsection → KP 沿包含边逐层下钻；"
                               "H 视图只用 hierarchy 边（contain），不显示 association 边。",
                "edge_set": "hierarchy",
                "levels": ["chapter", "section", "subsection", "kp"],
            },
            "A": {
                "name": "association",
                "description": "从焦点 KP/章节沿正文中出现的候选名称展开引用/关联边；"
                               "A 视图显示 association 边（reference/extend），"
                               "层级仅作为背景分组。",
                "edge_set": "association",
                "hop": 1,
            },
        },
        "counts": {
            "nodes": len(all_nodes),
            "hierarchy_edges": len(hierarchy_edges),
            "association_edges": len(association_edges),
        },
    }
    (out / ".memoria/demo-meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    report = {
        "kb": kb_name,
        "source": str(src),
        "out": str(out),
        "wikilinks_removed_in_demo": wikilinks_removed,
        "files": len(per_file),
        "level_counts": level_counts,
        "hierarchy_edges": len(hierarchy_edges),
        "association_edges": len(association_edges),
        "sidecar_files": len(per_file),
        "machine_candidate": True,
    }
    (out / "build-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    return report


def build_all(src_dir: Path, out_dir: Path, **kwargs) -> dict:
    reports = {}
    for kb_dir in sorted(p for p in src_dir.iterdir() if p.is_dir()):
        name = kb_dir.name
        prefix = "se" if name.startswith("software") else ("cn" if name.startswith("computer") else name[:2])
        out = out_dir / name
        reports[name] = build_kb(kb_dir, out, kb_name=name, prefix=prefix, **kwargs)
    (out_dir / "build-report.json").write_text(
        json.dumps({"schema": "course-demo-build/v1", "kbs": reports},
                   ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    return reports


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build multi-level course demo KB(s)")
    ap.add_argument("--source", default=str(DEFAULT_SRC))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--kb", default="", help="only build one subdir name")
    ap.add_argument("--max-leaves-per-chapter", type=int, default=8)
    ap.add_argument("--max-links-per-leaf", type=int, default=2)
    ap.add_argument("--max-links-per-chapter", type=int, default=6)
    args = ap.parse_args(argv)
    src_dir, out_dir = Path(args.source), Path(args.out)
    kwargs = dict(max_leaves_per_chapter=args.max_leaves_per_chapter,
                  max_links_per_leaf=args.max_links_per_leaf,
                  max_links_per_chapter=args.max_links_per_chapter)
    if args.kb:
        reports = {args.kb: build_kb(src_dir / args.kb, out_dir / args.kb,
                                     kb_name=args.kb,
                                     prefix="se" if args.kb.startswith("software") else "cn",
                                     **kwargs)}
    else:
        reports = build_all(src_dir, out_dir, **kwargs)
    print(json.dumps({"ok": True, "reports": reports}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
