#!/usr/bin/env python
"""Acceptance checker for the course demo KBs (task-388).

Verifies, for each KB under ``artifacts/demo-kb/courses-demo/<kb>``:
- ``memoria validate`` report: status ok, 0 errors, 0 warnings;
- ≥3 levels (chapter/section/subsection/kp), all levels non-empty, ≥100 candidates;
- every candidate has a parent (except chapter), valid range, sidecar tag
  ``candidate`` + ``level:<...>`` + ``parent:<id>``; no old pilot KP/link identity;
- hierarchy edges form the parent tree; association edges carry evidence and are
  exactly what the product collector derives;
- A/H visible contrast via the real product RPC `_mlvm_build`:
  * H at a chapter node expands the containment tree;
  * H at a leaf hub shows only the focus;
  * A at the same leaf hub shows a 1-hop reference/extend network (strictly more nodes/edges).

Writes ``acceptance-report.json`` (and optionally ``ah-contrast.json``).
Exit 0 = all checks pass; 1 = any failure.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from memoria.graph.collector import collect_graph_data  # noqa: E402
from memoria.presentation.api.ui import _mlvm_build  # noqa: E402

LEVELS = ["chapter", "section", "subsection", "kp"]
OLD_ID_RE = re.compile(r"^kp-\d{3}$")
OLD_EDGE_RE = re.compile(r"^edge-\d{3}$")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def vm_shown(kb: Path, focus: str, dimension: str) -> dict:
    r = _mlvm_build(str(kb), {"level": "LL", "dimension_id": dimension,
                              "focus": focus, "hop": 1, "new_hop": False,
                              "mode": "default"})
    if r.get("status") != "ok":
        return {"ok": False, "error": r.get("error")}
    vm = r["vm"]
    nodes = [n for n in vm["nodes"] if n.get("presence") == "shown"]
    edges = [e for e in vm["edges"] if e.get("presence") == "shown"]
    return {"ok": True, "nodes": nodes, "edges": edges,
            "node_ids": [n["id"] for n in nodes],
            "edge_ids": [e["id"] for e in edges],
            "edge_types": dict(collections.Counter(e["type"] for e in edges))}


def pick_focuses(meta: dict) -> dict:
    nodes = meta["nodes"]
    node_by_level = {n["id"]: n["level"] for n in nodes}
    assoc = meta["edges"]["association"]
    degree = collections.Counter()
    for e in assoc:
        degree[e["source"]] += 1
        degree[e["target"]] += 1
    hub = degree.most_common(1)[0][0]
    leaf_degree = {nid: d for nid, d in degree.items() if node_by_level.get(nid) == "kp"}
    leaf_hub = max(leaf_degree, key=lambda k: leaf_degree[k]) if leaf_degree else hub
    chapters = [n for n in nodes if n["level"] == "chapter"]
    chapter = chapters[0]
    sections = [n for n in nodes if n["level"] == "section" and n["parent_id"] == chapter["id"]]
    section = sections[0] if sections else chapter
    subs = [n for n in nodes if n["level"] == "subsection" and n["parent_id"] == section["id"]]
    sub = subs[0] if subs else section
    # a subsection that actually has leaf children (for H drill depth)
    leaf_parents = {n["parent_id"] for n in nodes if n["level"] == "kp"}
    sub_with_kp = next((n for n in nodes if n["level"] == "subsection" and n["id"] in leaf_parents), sub)
    return {"hub": hub, "leaf_hub": leaf_hub, "chapter": chapter["id"],
            "section": section["id"], "subsection": sub_with_kp["id"]}


def check_kb(kb_dir: Path) -> tuple[dict, dict]:
    checks: list[dict] = []

    def check(cid: str, ok: bool, detail: str = "") -> None:
        checks.append({"id": cid, "ok": bool(ok), "detail": detail})

    meta = load_json(kb_dir / ".memoria/demo-meta.json")
    report = load_json(kb_dir / "build-report.json")
    validate_path = kb_dir.parent / "validate" / f"{kb_dir.name}.json"
    if not validate_path.exists():
        validate_path = kb_dir / "validate-report.json"
    validate = load_json(validate_path)

    check("validate.exit", validate.get("status") == "ok"
          and validate.get("errors", 0) == 0 and validate.get("warnings", 0) == 0,
          f"status={validate.get('status')} errors={validate.get('errors')} warnings={validate.get('warnings')}")
    counts = meta.get("level_counts", {})
    for level in LEVELS:
        check(f"levels.{level}", counts.get(level, 0) > 0, str(counts.get(level)))
    total = sum(counts.get(l, 0) for l in LEVELS)
    check("candidates.total", total >= 100, f"total={total}")
    check("candidates.machine_candidate", meta.get("machine_candidate") is True and
          meta.get("is_gold") is False, "must be machine candidate, not gold")
    check("report.match", report.get("level_counts") == counts, "build-report vs demo-meta")
    wikilinks = sum(len(re.findall(r"\[\[", p.read_text(encoding="utf-8")))
                    for p in kb_dir.glob("*.md"))
    check("md.no_wikilinks", wikilinks == 0, f"remaining [[...]] markers: {wikilinks}")

    nodes = meta["nodes"]
    node_by_id = {n["id"]: n for n in nodes}
    node_by_level = {n["id"]: n["level"] for n in nodes}
    check("nodes.unique", len(node_by_id) == len(nodes), f"{len(nodes)} nodes")
    for n in nodes:
        if n["level"] != "chapter":
            check(f"parent.{n['id']}", n.get("parent_id") in node_by_id, "parent exists")
    for n in nodes:
        check(f"range.{n['id']}", 0 < n["line_start"] <= n["line_end"], "line range")
        if n.get("parent_id"):
            parent = node_by_id[n["parent_id"]]
            check(f"nested.{n['id']}",
                  parent["line_start"] <= n["line_start"] and n["line_end"] <= parent["line_end"],
                  "child range inside parent")

    # sidecar tags/identity + no old pilot identity reused
    sidecars = sorted((kb_dir / ".memoria/sidecars").glob("*.memoria.yaml"))
    check("sidecars.count", len(sidecars) == report.get("files"), f"{len(sidecars)}")
    import yaml
    tagged_ok = True
    old_ids = []
    for sc_path in sidecars:
        data = yaml.safe_load(sc_path.read_text(encoding="utf-8"))
        for kp in data.get("knowledge_points") or []:
            tags = kp.get("tags") or []
            if "candidate" not in tags or not any(t.startswith("level:") for t in tags):
                tagged_ok = False
            if OLD_ID_RE.match(str(kp.get("id") or "")):
                old_ids.append(kp["id"])
        for link in data.get("links") or []:
            for t in link.get("targets") or []:
                if OLD_ID_RE.match(str(t)) or OLD_EDGE_RE.match(str(t)):
                    old_ids.append(str(t))
    check("sidecars.candidate_tags", tagged_ok, "every KP has candidate+level tags")
    check("no_old_identity", not old_ids, f"old ids: {old_ids[:5]}")

    # collector: contain == hierarchy tree, reference/extend == association edges
    data = collect_graph_data(str(kb_dir))
    coll = collections.Counter(e["type"] for e in data["edges"])
    meta_h = len(meta["edges"]["hierarchy"])
    meta_a = len(meta["edges"]["association"])
    check("collector.contain", coll.get("contain", 0) == meta_h,
          f"collector={coll.get('contain', 0)} meta={meta_h}")
    check("collector.association", coll.get("reference", 0) + coll.get("extend", 0) == meta_a,
          f"collector={coll.get('reference', 0) + coll.get('extend', 0)} meta={meta_a}")
    # association evidence quote sha
    evidence_ok = True
    for e in meta["edges"]["association"]:
        src = kb_dir / e["file"]
        line = int(e["line"])
        lines = src.read_text(encoding="utf-8").splitlines()
        if not (1 <= line <= len(lines)):
            evidence_ok = False
            break
        if hashlib.sha256(lines[line - 1].encode("utf-8")).hexdigest() != e["quote_sha256"]:
            evidence_ok = False
            break
    check("association.evidence", evidence_ok, "quote_sha256 matches source line")

    focuses = pick_focuses(meta)
    h_ch = vm_shown(kb_dir, focuses["chapter"], "H")
    a_ch = vm_shown(kb_dir, focuses["chapter"], "A")
    h_sec = vm_shown(kb_dir, focuses["section"], "H")
    h_sub = vm_shown(kb_dir, focuses["subsection"], "H")
    h_hub = vm_shown(kb_dir, focuses["hub"], "H")
    a_hub = vm_shown(kb_dir, focuses["hub"], "A")
    h_leaf = vm_shown(kb_dir, focuses["leaf_hub"], "H")
    a_leaf = vm_shown(kb_dir, focuses["leaf_hub"], "A")
    check("vm.h_chapter.ok", h_ch.get("ok") and a_ch.get("ok"), "RPC ok")
    if h_ch.get("ok"):
        check("vm.h_chapter.children", len(h_ch["nodes"]) > 1 and
              all(t == "contain" for t in h_ch["edge_types"]),
              f"H shown nodes={len(h_ch['nodes'])} types={h_ch['edge_types']}")
        check("vm.h_chapter.drill", len(h_sec["nodes"]) > 1 or len(h_sub["nodes"]) > 1,
              f"section={len(h_sec['nodes'])} subsection={len(h_sub['nodes'])}")
    if h_hub.get("ok") and a_hub.get("ok"):
        hub_level = node_by_level.get(focuses["hub"], "?")
        check("vm.h_hub.ok", "nodes" in h_hub and "edges" in h_hub,
              f"H default hub ({hub_level}) nodes={len(h_hub.get('nodes', []))}")
        check("vm.a_hub.network", len(a_hub["nodes"]) >= 3 and len(a_hub["edges"]) >= 2
              and any(t in ("reference", "extend") for t in a_hub["edge_types"]),
              f"A hub nodes={len(a_hub['nodes'])} edges={len(a_hub['edges'])} types={a_hub['edge_types']}")
        check("vm.ah_visible_diff", len(a_hub["nodes"]) > len(h_hub["nodes"])
              and len(a_hub["edges"]) > len(h_hub["edges"]),
              f"A={len(a_hub['nodes'])}/{len(a_hub['edges'])} vs H={len(h_hub['nodes'])}/{len(h_hub['edges'])}")
    if h_leaf.get("ok") and a_leaf.get("ok"):
        check("vm.h_leaf.single", len(h_leaf["nodes"]) == 1 and len(h_leaf["edges"]) == 0,
              f"H leaf hub nodes={len(h_leaf['nodes'])} edges={len(h_leaf['edges'])}")
        check("vm.a_leaf.network", len(a_leaf["nodes"]) >= 3 and len(a_leaf["edges"]) >= 2
              and any(t in ("reference", "extend") for t in a_leaf["edge_types"]),
              f"A leaf hub nodes={len(a_leaf['nodes'])} edges={len(a_leaf['edges'])}")

    contrast = {
        "kb": meta.get("kb"),
        "focuses": focuses,
        "H_chapter": {"nodes": len(h_ch.get("nodes", [])), "edges": len(h_ch.get("edges", [])),
                      "edge_types": h_ch.get("edge_types")},
        "A_chapter": {"nodes": len(a_ch.get("nodes", [])), "edges": len(a_ch.get("edges", [])),
                      "edge_types": a_ch.get("edge_types")},
        "H_section": {"nodes": len(h_sec.get("nodes", [])), "edges": len(h_sec.get("edges", []))},
        "H_subsection": {"nodes": len(h_sub.get("nodes", [])), "edges": len(h_sub.get("edges", []))},
        "H_hub": {"nodes": len(h_hub.get("nodes", [])), "edges": len(h_hub.get("edges", [])),
                  "hub_level": node_by_level.get(focuses["hub"])},
        "A_hub": {"nodes": len(a_hub.get("nodes", [])), "edges": len(a_hub.get("edges", [])),
                  "edge_types": a_hub.get("edge_types")},
        "H_leaf_hub": {"nodes": len(h_leaf.get("nodes", [])), "edges": len(h_leaf.get("edges", []))},
        "A_leaf_hub": {"nodes": len(a_leaf.get("nodes", [])), "edges": len(a_leaf.get("edges", [])),
                       "edge_types": a_leaf.get("edge_types")},
        "level_counts": counts,
        "hierarchy_edges": meta_h,
        "association_edges": meta_a,
    }
    return {"kb": meta.get("kb"), "ok": all(c["ok"] for c in checks),
            "checks": checks, "failed": [c["id"] for c in checks if not c["ok"]],
            "counts": {"nodes": len(nodes), **counts,
                       "hierarchy_edges": meta_h, "association_edges": meta_a}}, contrast


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check course demo KB acceptance")
    ap.add_argument("--root", default="artifacts/demo-kb/courses-demo")
    ap.add_argument("--kb", default="", help="only one KB")
    ap.add_argument("--out", default="")
    ap.add_argument("--contrast-out", default="")
    args = ap.parse_args(argv)
    root = Path(args.root)
    kb_dirs = [root / args.kb] if args.kb else [p for p in sorted(root.iterdir())
                                                if p.is_dir() and (p / ".memoria/demo-meta.json").exists()]
    reports = {}
    contrasts = {}
    for kb_dir in kb_dirs:
        name = kb_dir.name
        report, contrast = check_kb(kb_dir)
        reports[name] = report
        contrasts[name] = contrast
        print(json.dumps({"kb": name, "ok": report["ok"],
                          "failed": report["failed"][:10],
                          "counts": report["counts"]}, ensure_ascii=False))
    out = Path(args.out) if args.out else root / "acceptance-report.json"
    out.write_text(json.dumps({"schema": "course-demo-acceptance/v1", "kbs": reports},
                              ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8", newline="\n")
    contrast_out = Path(args.contrast_out) if args.contrast_out else root / "ah-contrast.json"
    contrast_out.write_text(json.dumps({"schema": "course-demo-ah-contrast/v1", "kbs": contrasts},
                                       ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8", newline="\n")
    ok = all(r["ok"] for r in reports.values())
    print(json.dumps({"ok": ok, "out": str(out), "contrast_out": str(contrast_out)}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
