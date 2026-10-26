# -*- coding: utf-8 -*-
"""task-180 夹具：生成 lite/full 两个**带 release-manifest.json 的合法 zip**（mock 发布用）。

不签名；只生成结构/完整性清单（与 task-181 `services.verify.manifest` 同格式）。
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parent / "payload"
VERSION = "0.4.10"


def _build_zip(name: str, *, filler_bytes: int) -> bytes:
    files: dict[str, bytes] = {
        "VERSION": VERSION.encode(),
        "Memoria.exe": b"MZ-mock-exe-" + b"x" * 1024,
        "README.txt": b"Mock release for task-180 real-app verification.\n",
        "manifest.json": json.dumps({"name": "Memoria", "version": VERSION}).encode(),
        "lib/memoria/_mock.py": b"# mock\n",
        "resources/app.js": b"// mock\n",
        "config/ui-settings.json": b"{}\n",
    }
    if filler_bytes:
        files["hf/model.bin"] = os.urandom(filler_bytes)
    manifest = {
        "schema": "memoria-release-manifest/v1",
        "format_version": 1,
        "version": VERSION,
        "built_at": "2026-10-26T00:00:00Z",
        "asset": {"name": name, "bytes": 0},
        "layout": {"required": ["Memoria.exe", "VERSION", "manifest.json"], "optional": [], "forbidden": []},
        "files": [
            {"path": p, "sha256": hashlib.sha256(d).hexdigest(), "bytes": len(d)}
            for p, d in files.items()
        ],
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p, d in files.items():
            zf.writestr(p, d)
        zf.writestr("release-manifest.json", json.dumps(manifest, ensure_ascii=False))
    return out.getvalue()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    lite = _build_zip("Memoria-v0.4.10-win64-lite.zip", filler_bytes=0)
    full = _build_zip("Memoria-v0.4.10-win64.zip", filler_bytes=8 * 1024 * 1024)
    (OUT / "Memoria-v0.4.10-win64-lite.zip").write_bytes(lite)
    (OUT / "Memoria-v0.4.10-win64.zip").write_bytes(full)
    print(f"lite={len(lite)} bytes, full={len(full)} bytes -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
