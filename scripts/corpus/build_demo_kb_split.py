#!/usr/bin/env python
"""Build a split demo KB (one Markdown file per section) from the corpus pilot.

Why split: a single 126k Markdown file plus 50 KPs made the dev app lag and the
multilevel graph collapse into one focus node. Splitting by source section gives
small files, section-level clusters, and a much smaller editor payload.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "artifacts/corpus/pilot"
SRC = PILOT / "source/chapter.txt"
SECTIONS = PILOT / "source/sections.json"
KPS = PILOT / "annotations/kps.single.jsonl"
EDGES = PILOT / "annotations/edges.single.jsonl"
SHOWCASE = ROOT / "docs/example/showcase"
OUT = ROOT / "artifacts/demo-kb/corpus-pilot-split"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    chapter = SRC.read_text(encoding="utf-8")
    sections = json.loads(SECTIONS.read_text(encoding="utf-8"))["sections"]
    kps = read_jsonl(KPS)
    edges = read_jsonl(EDGES)
    by_section: dict[str, list[dict]] = {}
    for kp in kps:
        by_section.setdefault(kp.get("section_key") or "ch1-intro", []).append(kp)
    id_sec = {kp["id"]: (kp.get("section_key") or "ch1-intro") for kp in kps}

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SHOWCASE, OUT)
    for p in list(OUT.glob("*.md")):
        p.unlink()
    sidecars = OUT / ".memoria/sidecars"
    if sidecars.exists():
        shutil.rmtree(sidecars)
    sidecars.mkdir(parents=True, exist_ok=True)
    for d in (OUT / ".memoria/cache",):
        if d.exists():
            shutil.rmtree(d)
    for n in ("pending.json", "kp_targets.json"):
        p = OUT / ".memoria" / n
        if p.exists():
            p.unlink()

    def snippet(text: str) -> str:
        text = (text or "").strip()
        return text if len(text) <= 80 else text[:80]

    files = []
    total_kps = 0
    total_links = 0
    for sec in sections:
        page_id = sec["page_id"]
        start, end = int(sec["start"]), int(sec["end"])
        text = chapter[start:end]
        if not text.strip():
            continue
        fn = f"{page_id}.md"
        fp = OUT / fn
        fp.write_text(text, encoding="utf-8")
        local_offsets = [0]
        for line in text.splitlines():
            local_offsets.append(local_offsets[-1] + len(line) + 1)

        def local_line(global_off: int) -> int:
            loc = max(0, int(global_off) - start)
            return max(1, bisect.bisect_right(local_offsets, loc))

        rows = []
        for kp in by_section.get(page_id, []):
            ev = (kp.get("evidence") or [{}])[0]
            g0, g1 = int(ev.get("start") or 0), int(ev.get("end") or 0)
            quote = ev.get("quote") or kp.get("name") or ""
            rows.append({
                "id": kp["id"],
                "name": kp.get("name") or kp["id"],
                "aliases": [x for x in [kp.get("name_zh")] if x],
                "tags": [kp.get("concept_type") or "concept"],
                "range": {
                    "start": {"snippet": snippet(quote), "line_hint": local_line(g0)},
                    "end": {"snippet": snippet(quote), "line_hint": local_line(max(g0, g1 - 1))},
                },
            })
        # hub first per file
        degree = {r["id"]: 0 for r in rows}
        for e in edges:
            if e.get("source") in degree:
                degree[e["source"]] += 1
            if e.get("target") in degree:
                degree[e["target"]] += 1
        rows.sort(key=lambda r: (-degree.get(r["id"], 0), r["id"]))
        links = []
        for e in edges:
            src, tgt = e.get("source"), e.get("target")
            if src not in id_sec or tgt not in id_sec or id_sec[src] != page_id:
                continue
            src_kp = next((k for k in by_section.get(page_id, []) if k["id"] == src), None)
            if not src_kp:
                continue
            ev = (src_kp.get("evidence") or [{}])[0]
            line = local_line(int(ev.get("start") or 0))
            links.append({
                "anchor_text": next((k.get("name") or tgt for k in by_section.get(id_sec[tgt], []) if k["id"] == tgt), tgt),
                "targets": [tgt],
                "edge_type": "reference" if e.get("type") == "contain" else (e.get("type") or "reference"),
                "instances": [{"line": line}],
                "source_id": src,
            })
        sidecar = {"schema_version": 1, "file": fn, "knowledge_points": rows, "links": links}
        sc = sidecars / f"{page_id}.memoria.yaml"
        sc.write_text(yaml.safe_dump(sidecar, allow_unicode=True, sort_keys=False, width=1000000), encoding="utf-8")
        total_kps += len(rows)
        total_links += len(links)
        files.append({
            "path": fn,
            "md_mtime": fp.stat().st_mtime,
            "md_size": fp.stat().st_size,
            "md_sha256": sha(fp.read_bytes()),
            "sidecar_mtime": sc.stat().st_mtime,
            "sidecar_sha256": sha(sc.read_bytes()),
        })

    manifest = {"schema_version": 1, "updated_at": datetime.now(timezone.utc).isoformat(), "files": files}
    (OUT / ".memoria/manifest.yaml").write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False, width=1000000), encoding="utf-8")
    (OUT / ".memoria/pending.json").write_text("{}\n", encoding="utf-8")
    (OUT / ".memoria/kp_targets.json").write_text("{}\n", encoding="utf-8")
    (OUT / "README.md").write_text(
        "# Corpus pilot demo KB (split by section)\n\n"
        "Tier-A source: OpenStax Introduction to Business, Chapter 1 (CC BY 4.0).\n"
        "One Markdown file per source section; section-level clusters in the graph.\n"
        "KPs/links are machine candidate drafts, not gold labels.\n",
        encoding="utf-8",
    )
    print(json.dumps({"kb": str(OUT), "files": len(files), "kps": total_kps, "links": total_links}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

