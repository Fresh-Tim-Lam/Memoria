"""delete_link_route 单元测试。"""

from __future__ import annotations

from memoria.services.document import DocumentService


def test_delete_link_route_removes_sidecar_and_unwraps(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    md = kb / "demo.md"
    md.write_text(
        "见 [[按顺序点]] 与 [[按顺序点]] 两处。\n",
        encoding="utf-8",
    )
    sidecar_dir = kb / ".memoria" / "sidecars"
    sidecar_dir.mkdir(parents=True)
    (sidecar_dir / "demo.memoria.yaml").write_text(
        """schema_version: 1
file: demo.md
knowledge_points: []
links:
- anchor_text: 按顺序点
  targets: [rl]
  instances:
  - line: 1
    wrapped: true
""",
        encoding="utf-8",
    )

    svc = DocumentService(kb_path=str(kb))
    res = svc.delete_link_route("demo.md", "按顺序点")
    assert res["status"] == "ok"
    body = res["document"]["body"]
    assert "[[" not in body
    assert "按顺序点" in body
    links = res["document"]["sidecar"]["links"]
    assert not links
