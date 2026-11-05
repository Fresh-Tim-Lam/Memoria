#!/usr/bin/env python
"""Build a disposable demo KB from the Tier-A corpus pilot.

The demo KB is written under artifacts/ and is never used as a user library.
It turns the machine KP/edge candidates into a Memoria KB (Markdown + sidecar)
so the graph and editor can be inspected in dev mode.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "artifacts/corpus/pilot"
SRC = PILOT / "source/chapter.txt"
KPS = PILOT / "annotations/kps.single.jsonl"
EDGES = PILOT / "annotations/edges.single.jsonl"
SHOWCASE = ROOT / "docs/example/showcase"
OUT = ROOT / "artifacts/demo-kb/corpus-pilot"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    chapter = SRC.read_text(encoding="utf-8")
    kps = read_jsonl(KPS)
    edges = read_jsonl(EDGES)
    lines = chapter.splitlines()
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line) + 1)

    def line_of(offset: int) -> int:
        # 1-based line index
        import bisect
        return max(1, bisect.bisect_right(offsets, offset))

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SHOWCASE, OUT)
    # remove showcase content, keep .memoria skeleton
    for p in list(OUT.glob("*.md")):
        p.unlink()
    sidecars = OUT / ".memoria/sidecars"
    if sidecars.exists():
        shutil.rmtree(sidecars)
    sidecars.mkdir(parents=True, exist_ok=True)
    cache = OUT / ".memoria/cache"
    if cache.exists():
        shutil.rmtree(cache)
    for name in ("pending.json", "kp_targets.json"):
        p = OUT / ".memoria" / name
        if p.exists():
            p.unlink()

    md = chapter
    md_path = OUT / "chapter1.md"
    md_path.write_text(md, encoding="utf-8")

    def snippet(text: str) -> str:
        # Must be an exact substring of the Markdown; never collapse whitespace.
        text = (text or "").strip()
        return text if len(text) <= 80 else text[:80]

    kp_rows = []
    id_to_kp = {}
    for kp in kps:
        ev = (kp.get("evidence") or [{}])[0]
        start = int(ev.get("start") or 0)
        end = int(ev.get("end") or start)
        quote = ev.get("quote") or kp.get("name") or ""
        row = {
            "id": kp["id"],
            "name": kp.get("name") or kp["id"],
            "aliases": [x for x in [kp.get("name_zh")] if x],
            "tags": [kp.get("concept_type") or "concept"],
            "range": {
                "start": {"snippet": snippet(quote), "line_hint": line_of(start)},
                "end": {"snippet": snippet(quote), "line_hint": line_of(max(start, end - 1))},
            },
        }
        kp_rows.append(row)
        id_to_kp[kp["id"]] = kp

    links = []
    for e in edges:
        src = e.get("source")
        tgt = e.get("target")
        if src not in id_to_kp or tgt not in id_to_kp:
            continue
        src_ev = (id_to_kp[src].get("evidence") or [{}])[0]
        line = line_of(int(src_ev.get("start") or 0))
        links.append({
            "anchor_text": id_to_kp[tgt].get("name") or tgt,
            "targets": [tgt],
            "edge_type": "reference" if (e.get("type") == "contain") else (e.get("type") or "reference"),
            "instances": [{"line": line}],
            "source_id": src,
        })

    # Put a connected hub first so the graph's initial focus shows a neighborhood
    # instead of an isolated node (dev demo only; ids/links unchanged).
    degree = {row["id"]: 0 for row in kp_rows}
    for link in links:
        degree[link["source_id"]] = degree.get(link["source_id"], 0) + 1
        for tgt in link.get("targets", []):
            degree[tgt] = degree.get(tgt, 0) + 1
    ordered_kp_rows = sorted(kp_rows, key=lambda r: (-degree.get(r["id"], 0), r["id"]))
    sidecar = {
        "schema_version": 1,
        "file": "chapter1.md",
        "knowledge_points": ordered_kp_rows,
        "links": links,
    }
    sidecar_path = sidecars / "chapter1.memoria.yaml"
    sidecar_text = yaml.safe_dump(sidecar, allow_unicode=True, sort_keys=False)
    sidecar_path.write_text(sidecar_text, encoding="utf-8")

    now = datetime.now(timezone.utc).isoformat()
    md_bytes = md_path.read_bytes()
    sc_bytes = sidecar_path.read_bytes()
    manifest = {
        "schema_version": 1,
        "updated_at": now,
        "files": [{
            "path": "chapter1.md",
            "md_mtime": md_path.stat().st_mtime,
            "md_size": len(md_bytes),
            "md_sha256": sha256_bytes(md_bytes),
            "sidecar_mtime": sidecar_path.stat().st_mtime,
            "sidecar_sha256": sha256_bytes(sc_bytes),
        }],
    }
    (OUT / ".memoria/manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (OUT / ".memoria/pending.json").write_text("{}\n", encoding="utf-8")
    (OUT / ".memoria/kp_targets.json").write_text("{}\n", encoding="utf-8")
    (OUT / "README.md").write_text(
        "# Corpus pilot demo KB\n\n"
        "Tier-A source: OpenStax Introduction to Business, Chapter 1 (CC BY 4.0).\n"
        "This is a disposable demo KB under artifacts/; do not treat it as a user library.\n"
        "KPs/links are machine candidate drafts, not gold labels.\n",
        encoding="utf-8",
    )
    print(json.dumps({"kb": str(OUT), "kps": len(kp_rows), "links": len(links), "md_bytes": len(md_bytes), "sidecar_bytes": len(sc_bytes)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


