"""KP 元数据更新与删除。"""

from __future__ import annotations

from memoria.services.document import DocumentService


def _write_demo_kb(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    md = kb / "demo.md"
    md.write_text(
        "## Alpha\n\nAlpha body.\n\n## Beta\n\nBeta body.\n",
        encoding="utf-8",
    )
    sidecar_dir = kb / ".memoria" / "sidecars"
    sidecar_dir.mkdir(parents=True)
    (sidecar_dir / "demo.memoria.yaml").write_text(
        """schema_version: 1
file: demo.md
knowledge_points:
- id: alpha
  name: Alpha
  range:
    start: {snippet: '## Alpha', line_hint: 1}
    end: {snippet: Alpha body., line_hint: 3}
- id: beta
  name: Beta
  range:
    start: {snippet: '## Beta', line_hint: 5}
    end: {snippet: Beta body., line_hint: 7}
links:
- anchor_text: Alpha link
  targets: [alpha]
  source_id: alpha
""",
        encoding="utf-8",
    )
    return kb


def test_update_kp_name_and_tags(tmp_path):
    kb = _write_demo_kb(tmp_path)
    svc = DocumentService(kb_path=str(kb))

    res = svc.update_kp("demo.md", "alpha", name="Alpha Renamed", tags=["rl", "demo"])
    assert res["status"] == "ok"
    kp = next(k for k in res["knowledge_points"] if k["id"] == "alpha")
    assert kp["name"] == "Alpha Renamed"
    assert kp["tags"] == ["rl", "demo"]

    res2 = svc.update_kp("demo.md", "alpha", tags=["rl"])
    kp2 = next(k for k in res2["knowledge_points"] if k["id"] == "alpha")
    assert kp2["tags"] == ["rl"]
    assert kp2["name"] == "Alpha Renamed"


def test_update_kp_persists_tag_candidates(tmp_path):
    kb = _write_demo_kb(tmp_path)
    svc = DocumentService(kb_path=str(kb))
    res = svc.update_kp(
        "demo.md",
        "alpha",
        tags=["rl"],
        tag_candidates=[
            {"tag": "policy", "source": "system", "score": 14.0},
            {"tag": "manual", "source": "user"},
        ],
    )
    assert res["status"] == "ok"
    kp = next(k for k in res["knowledge_points"] if k["id"] == "alpha")
    assert kp["tags"] == ["rl"]
    assert len(kp["tag_candidates"]) == 2
    assert kp["tag_candidates"][0]["tag"] == "policy"

    res2 = svc.load_document("demo.md")
    kp2 = next(k for k in res2["knowledge_points"] if k["id"] == "alpha")
    assert kp2["tag_candidates"][1]["tag"] == "manual"


def test_delete_kp_clears_link_source_id(tmp_path):
    kb = _write_demo_kb(tmp_path)
    svc = DocumentService(kb_path=str(kb))

    res = svc.delete_kp("demo.md", "alpha")
    assert res["status"] == "ok"
    ids = [k["id"] for k in res["knowledge_points"]]
    assert "alpha" not in ids
    link = res["sidecar"]["links"][0]
    assert "source_id" not in link or not link.get("source_id")
