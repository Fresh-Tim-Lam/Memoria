"""从标题提议 bootstrap 示例侧车（开发用）。"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from memoria.services.heading_proposals import propose_ranges_from_headings
from memoria.storage.constants import SIDECAR_SCHEMA_VERSION
from memoria.storage.markdown import strip_frontmatter


def _slug(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", s)
    return s.strip("-")[:40] or "kp"


def build_sidecar_from_headings(rel_path: str, body: str, fm: dict | None) -> dict:
    proposals = propose_ranges_from_headings(body)
    kps = []
    used: set[str] = set()
    for p in proposals:
        pid = _slug(p["name"])
        base = pid
        n = 2
        while pid in used:
            pid = f"{base}-{n}"
            n += 1
        used.add(pid)
        kps.append({
            "id": pid,
            "name": p["name"],
            "range": p["range"],
        })
    return {
        "schema_version": SIDECAR_SCHEMA_VERSION,
        "file": rel_path.replace("\\", "/"),
        "description": (fm or {}).get("description", ""),
        "knowledge_points": kps,
    }


def write_example_sidecars(examples_dir: Path, *, force: bool = False) -> list[str]:
    written: list[str] = []
    out_dir = examples_dir / ".memoria" / "sidecars"
    out_dir.mkdir(parents=True, exist_ok=True)
    for md in sorted(examples_dir.glob("*.md")):
        rel = md.name
        target = out_dir / f"{md.stem}.memoria.yaml"
        if target.is_file() and not force:
            continue
        raw = md.read_text(encoding="utf-8")
        body, fm = strip_frontmatter(raw)
        data = build_sidecar_from_headings(rel, body, fm)
        if not data["knowledge_points"]:
            continue
        with open(target, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
        written.append(str(target))
    return written


if __name__ == "__main__":
    import sys

    root = Path(__file__).resolve().parents[1]
    force = "--force" in sys.argv
    for p in write_example_sidecars(root / "examples", force=force):
        print("wrote", p)
