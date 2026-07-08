"""M3 KP id 重命名测试。"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from memoria.services.document import DocumentService
from memoria.services.kp_index import build_kp_index
from memoria.services.kp_rename import (
    migrate_sidecar_kp_refs,
    replace_link_id_in_markdown,
    rename_kp_in_kb,
)
from memoria.storage.sidecar import load_sidecar_for_md

FIXTURE_KB = Path(__file__).resolve().parents[2] / "fixtures" / "m3_rename_kb"


@pytest.fixture
def rename_kb(tmp_path: Path) -> Path:
    """Copy fixture so rename tests do not mutate the source tree."""
    dest = tmp_path / "m3_rename_kb"
    shutil.copytree(FIXTURE_KB, dest)
    return dest


@pytest.fixture
def svc(rename_kb: Path) -> DocumentService:
    s = DocumentService()
    s.set_kb_path(str(rename_kb))
    return s


def test_replace_link_id_preserves_display_text():
    body = "见 [[old-id|显示文字]] 与 [[old-id]] 和 [[old-id#extend|锚]]"
    new_body, n = replace_link_id_in_markdown(body, "old-id", "new-id")
    assert n == 3
    assert "[[new-id|显示文字]]" in new_body
    assert "[[new-id|old-id]]" in new_body
    assert "[[new-id#extend|锚]]" in new_body
    assert "[[old-id" not in new_body


def test_migrate_sidecar_refs():
    sidecar = {
        "knowledge_points": [{"id": "old"}],
        "edges": [{"source_id": "x", "targets": ["old"]}],
        "links": [
            {
                "source_id": "old",
                "targets": ["old"],
                "target_edges": {"old": {"edge_type": "reference"}},
                "pool": ["old"],
            }
        ],
    }
    n = migrate_sidecar_kp_refs(sidecar, "old", "new")
    assert n >= 5
    assert sidecar["knowledge_points"][0]["id"] == "new"
    assert sidecar["edges"][0]["targets"] == ["new"]
    assert sidecar["links"][0]["source_id"] == "new"
    assert sidecar["links"][0]["targets"] == ["new"]
    assert "new" in sidecar["links"][0]["target_edges"]


def test_rename_kp_in_kb(rename_kb: Path, svc: DocumentService):
    res = rename_kp_in_kb(str(rename_kb), "rename-kp", "renamed-kp")
    assert res["status"] == "ok"
    assert res["changed"] is True
    assert "alpha.md" in res["sidecar_files"]
    assert "beta.md" in res["sidecar_files"]
    assert res["md_replacements"] >= 2

    index = build_kp_index(str(rename_kb))
    assert "rename-kp" not in index["by_id"]
    assert "renamed-kp" in index["by_id"]

    alpha = (rename_kb / "alpha.md").read_text(encoding="utf-8")
    assert "[[renamed-kp|rename-me]]" in alpha

    beta = (rename_kb / "beta.md").read_text(encoding="utf-8")
    assert "[[renamed-kp|旧显示名]]" in beta

    beta_sc = load_sidecar_for_md(rename_kb / "beta.md", rename_kb)
    assert beta_sc["links"][0]["targets"] == ["renamed-kp"]
    assert beta_sc["edges"][0]["targets"] == ["renamed-kp"]

    report = svc.validate_kb()
    assert report["errors"] == 0


def test_rename_rejects_duplicate(rename_kb: Path, svc: DocumentService):
    res = svc.rename_kp_id("rename-kp", "beta-local")
    assert res["status"] == "error"
    assert "已存在" in res.get("message", "")
