"""atomic_yaml 备份与原子写。"""

from __future__ import annotations

from pathlib import Path

import yaml

from memoria.storage.atomic_yaml import (
    atomic_write_yaml,
    backup_path,
    restore_from_backup,
    write_backup,
)
from memoria.storage.sidecar import load_sidecar, save_sidecar


def test_atomic_write_creates_bak_on_overwrite(tmp_path):
    path = tmp_path / "a.memoria.yaml"
    path.write_text("schema_version: 1\n", encoding="utf-8")
    atomic_write_yaml(path, {"schema_version": 1, "file": "a.md"})
    bak = backup_path(path)
    assert bak.is_file()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["file"] == "a.md"
    old = yaml.safe_load(bak.read_text(encoding="utf-8"))
    assert old == {"schema_version": 1}


def test_save_sidecar_uses_backup(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    md = kb / "note.md"
    md.write_text("# n\n", encoding="utf-8")
    from memoria.storage.sidecar import save_sidecar_for_md, sidecar_path_for

    save_sidecar_for_md(md, kb, {"schema_version": 1, "file": "note.md", "knowledge_points": []})
    save_sidecar_for_md(
        md,
        kb,
        {"schema_version": 1, "file": "note.md", "knowledge_points": [{"id": "kp1", "name": "kp1"}]},
    )
    sc_path = Path(sidecar_path_for(md, kb))
    bak = backup_path(sc_path)
    assert bak.is_file()
    restored = load_sidecar(sc_path)
    assert len(restored["knowledge_points"]) == 1


def test_restore_from_backup(tmp_path):
    path = tmp_path / "x.yaml"
    write_backup(path)  # no-op if missing
    path.write_text("a: 1\n", encoding="utf-8")
    write_backup(path)
    path.write_text("a: 2\n", encoding="utf-8")
    assert restore_from_backup(path)
    assert yaml.safe_load(path.read_text()) == {"a": 1}
