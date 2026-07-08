"""save_link_route 边类型持久化测试。"""

from __future__ import annotations

from pathlib import Path

from memoria.services.document import DocumentService
from memoria.storage.sidecar import load_sidecar_for_md


def test_save_link_route_persists_edge_type_when_anchor_equals_target(tmp_path: Path):
    kb = tmp_path / "kb"
    kb.mkdir()
    md = kb / "a.md"
    md.write_text("# Demo\n\nsee [[mdp]] here.\n", encoding="utf-8")
    sidecar_dir = kb / ".memoria" / "sidecars"
    sidecar_dir.mkdir(parents=True)
    (sidecar_dir / "a.memoria.yaml").write_text(
        "schema_version: 1\nfile: a.md\nknowledge_points: []\nlinks: []\n",
        encoding="utf-8",
    )

    svc = DocumentService(kb_path=str(kb))
    res = svc.save_link_route(
        "a.md",
        "mdp",
        ["mdp"],
        edge_type="extend",
        target_edges={"mdp": {"edge_type": "extend", "relevance": 0.55}},
        update_markdown=False,
    )
    assert res["status"] == "ok"

    sidecar = load_sidecar_for_md(md, kb)
    link = sidecar["links"][0]
    assert link["anchor_text"] == "mdp"
    assert link["targets"] == ["mdp"]
    assert link["edge_type"] == "extend"
    assert link["target_edges"]["mdp"]["edge_type"] == "extend"
    assert link["target_edges"]["mdp"]["relevance"] == 0.55
