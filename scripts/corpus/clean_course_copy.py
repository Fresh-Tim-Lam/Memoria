#!/usr/bin/env python
"""Clean copied course textbooks: remove Memoria wikilink markup only.

The originals are never touched. In the cleaned copies every ``[[...]]`` token is
replaced by its visible label:
  ``[[slug|label]]``        -> ``label``
  ``[[\\h:#fff:#000|text]]`` -> ``text``
  ``[[slug]]``              -> ``slug``
This removes old KP links/highlight markup so a new demo KB starts from plain
textbook content.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COPIES = ROOT / "artifacts/demo-kb/courses"
LINK = re.compile(r"\[\[([^\[\]]*?)\]\]")


def clean_text(text: str) -> tuple[str, int]:
    count = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        inner = match.group(1)
        parts = inner.split("|")
        return parts[-1].strip() if len(parts) > 1 else parts[0].strip()

    return LINK.sub(repl, text), count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="only report, do not write")
    args = parser.parse_args()
    report = {}
    for kb in sorted(p for p in COPIES.iterdir() if p.is_dir()):
        total = 0
        files = 0
        for path in sorted(kb.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            cleaned, n = clean_text(text)
            if n:
                total += n
                files += 1
                if not args.check:
                    path.write_text(cleaned, encoding="utf-8", newline="\n")
        report[kb.name] = {"files_changed": files, "links_removed": total}
        print(json.dumps({kb.name: report[kb.name]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
