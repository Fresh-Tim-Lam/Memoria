"""知识库目录扫描。"""

from __future__ import annotations

import os

from memoria.storage.constants import SKIP_DIR_NAMES


def collect_md_files(kb_root: str) -> list[str]:
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(kb_root):
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIR_NAMES and not d.startswith(".")
        ]
        for name in filenames:
            if name.endswith(".md"):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, kb_root).replace("\\", "/")
                out.append(rel)
    return sorted(out)
