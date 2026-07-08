"""path_cascade 路径级联。"""

from __future__ import annotations

import shutil
from pathlib import Path

from memoria.storage.manifest import audit_manifest_diff, load_manifest
from memoria.storage.path_cascade import (
    apply_path_move,
    detect_path_moves,
    reconcile_path_cascade,
)
from memoria.storage.pending import load_pending, save_pending
from memoria.storage.sidecar import load_sidecar_for_md, save_sidecar_for_md


def _kb(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    mod = kb / "模块1"
    mod.mkdir()
    md = mod / "a.md"
    md.write_text("# A\n\nbody\n", encoding="utf-8")
    save_sidecar_for_md(
        md,
        kb,
        {"schema_version": 1, "file": "模块1/a.md", "knowledge_points": []},
    )
    audit_manifest_diff(str(kb))
    return kb, md


def test_detect_move_by_hash(tmp_path):
    kb, md = _kb(tmp_path)
    new_dir = kb / "模块10"
    new_dir.mkdir()
    md.replace(new_dir / "a.md")
    moves = detect_path_moves(str(kb))
    assert len(moves) == 1
    assert moves[0]["from"] == "模块1/a.md"
    assert moves[0]["to"] == "模块10/a.md"


def test_apply_move_updates_sidecar_and_manifest(tmp_path):
    kb, md = _kb(tmp_path)
    new_dir = kb / "模块10"
    new_dir.mkdir()
    md.replace(new_dir / "a.md")

    result = reconcile_path_cascade(str(kb), apply=True)
    assert result["applied_count"] == 1

    sc = load_sidecar_for_md(kb / "模块10/a.md", kb)
    assert sc["file"] == "模块10/a.md"
    manifest = load_manifest(str(kb))
    assert "模块10/a.md" in manifest["files_by_path"]
    assert "模块1/a.md" not in manifest["files_by_path"]


def test_apply_move_updates_pending(tmp_path):
    kb, md = _kb(tmp_path)
    save_pending(
        str(kb),
        {
            "schema_version": 1,
            "items": [
                {
                    "pending_id": "abc",
                    "file": "模块1/a.md",
                    "kind": "heading",
                    "name": "T",
                    "status": "pending",
                }
            ],
        },
    )
    new_dir = kb / "模块10"
    new_dir.mkdir()
    md.replace(new_dir / "a.md")
    apply_path_move(str(kb), "模块1/a.md", "模块10/a.md")
    pending = load_pending(str(kb))
    assert pending["items"][0]["file"] == "模块10/a.md"


def test_dry_run_does_not_write(tmp_path):
    kb, md = _kb(tmp_path)
    from memoria.storage.sidecar import sidecar_path_for

    old_sc_path = Path(sidecar_path_for(kb / "模块1/a.md", kb))
    new_dir = kb / "模块10"
    new_dir.mkdir()
    md.replace(new_dir / "a.md")
    result = reconcile_path_cascade(str(kb), apply=False)
    assert result["dry_run"] is True
    assert old_sc_path.is_file()
    assert load_sidecar_for_md(kb / "模块10/a.md", kb) is None
