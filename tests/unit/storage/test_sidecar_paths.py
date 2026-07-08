from pathlib import Path

from memoria.storage.sidecar import (
    legacy_sidecar_path_for,
    resolve_sidecar_path,
    sidecar_path_for,
)


def test_sidecar_mirror_path():
    kb = Path("D:/kb")
    md = kb / "notes" / "rl.md"
    sc = sidecar_path_for(md, kb)
    assert sc.replace("\\", "/") == "D:/kb/.memoria/sidecars/notes/rl.memoria.yaml"


def test_legacy_fallback(tmp_path):
    kb = tmp_path
    md = kb / "foo.md"
    md.write_text("# hi", encoding="utf-8")
    legacy = Path(legacy_sidecar_path_for(md))
    legacy.write_text("schema_version: 1\nfile: foo.md\n", encoding="utf-8")
    assert Path(resolve_sidecar_path(md, kb)) == legacy
