"""作者流程（semantic contain）的端到端钉子：curation overlay + collector 合并（M8a）。

来源：人（2026-11-02）「文本上的 contain 不一定真实具有 contain 的语义」→ 批准方案 B（
`dec-20261102-3b8e6eb6`）→ 批准作者流程 D1+D2+D3 copy-only（`dec-20261102-2dcefd31`）。

钉住：
1. `curate_contain` 写一份 curation overlay，collector 合并后输出 `contain_kind=semantic` +
   `derived_by=author` + `assertion_source`（值一致），`generator_version` 移除，其余边不变；
2. 缺证据 / 锚点 stale / 重复 curation 一律拒绝（不写）；
3. 孤儿 overlay 不造边、只产 warning（不静默）；
4. 撤销后回到 structural；
5. agent 工具面不得出现 `curate_contain`（agent 只能提议，落库仅人确认）。
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
FROZEN = (
    _ROOT
    / "artifacts"
    / "agent"
    / "verify"
    / "debate"
    / "kg-retrieval"
    / "round2"
    / "frozen"
    / "数字通信原理"
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture()
def kb(tmp_path) -> Path:
    if not FROZEN.is_dir():
        pytest.skip("frozen 语料不在本机（gitignored artifacts）")
    dest = tmp_path / "kb"
    shutil.copytree(FROZEN, dest)
    return dest


def _graph(kb: Path) -> dict:
    from memoria.graph.collector import collect_graph_data

    return collect_graph_data(str(kb))


def _pick_contain(kb: Path) -> tuple[dict, dict]:
    """返回 (边, 锚点)；锚点取该边源文档首个非空行。"""
    graph = _graph(kb)
    edge = next(e for e in graph["edges"] if e.get("type") == "contain")
    rel = edge["file"]
    lines = (kb / rel).read_text(encoding="utf-8").splitlines()
    line_no = next(i for i, line in enumerate(lines, 1) if line.strip())
    anchor = {
        "file": rel,
        "line_start": line_no,
        "line_end": line_no,
        "quote_sha256": _sha(lines[line_no - 1]),
    }
    return edge, anchor


def _service(kb: Path):
    from memoria.services.document import DocumentService

    return DocumentService(kb_path=str(kb))


def _find(graph: dict, source_id: str, target_id: str) -> dict:
    return next(
        e
        for e in graph["edges"]
        if e.get("type") == "contain"
        and (e.get("source_id") or "").strip() == source_id
        and target_id in (e.get("targets") or [])
    )


def _edge_map(graph: dict) -> dict[str, dict]:
    return {
        f"{e.get('type')}|{e.get('source_id')}|{(e.get('targets') or [''])[0]}": e
        for e in graph["edges"]
    }


def test_curate_merges_semantic_and_keeps_other_edges(kb: Path) -> None:
    edge, anchor = _pick_contain(kb)
    source_id, target_id = edge["source_id"], edge["targets"][0]
    baseline = _edge_map(_graph(kb))
    result = _service(kb).curate_contain(edge["file"], source_id, target_id, anchor, confirmed_by="human:test")
    assert result["status"] == "ok", result

    graph = _graph(kb)
    merged = _find(graph, source_id, target_id)
    assert merged["contain_kind"] == "semantic"
    assert merged["derived_by"] == "author"
    assert merged["assertion_source"] == anchor
    assert "generator_version" not in merged
    # 几何/基础字段保持派生值
    assert merged["origin"] == "range" and merged["derived"] is True
    assert len(graph["edges"]) == 62 and len(graph["nodes"]) == 357

    changed = {key for key, value in _edge_map(graph).items() if baseline.get(key) != value}
    assert changed == {f"contain|{source_id}|{target_id}"}, f"其它边不应变化：{changed}"

    # canonical schema 校验
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((_ROOT / "docs/design/kg-edge-provenance.schema.json").read_text(encoding="utf-8"))
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(merged)) == []


def test_reject_missing_evidence_and_stale_anchor(kb: Path) -> None:
    edge, anchor = _pick_contain(kb)
    svc = _service(kb)
    source_id, target_id = edge["source_id"], edge["targets"][0]
    assert svc.curate_contain(edge["file"], source_id, target_id, {}, confirmed_by="human:test")["status"] == "error"
    stale = dict(anchor)
    stale["quote_sha256"] = "0" * 64
    result = svc.curate_contain(edge["file"], source_id, target_id, stale, confirmed_by="human:test")
    assert result["status"] == "error"
    assert "quote_sha256" in result["message"]
    # 必须由人确认
    assert svc.curate_contain(edge["file"], source_id, target_id, anchor, confirmed_by="  ")["status"] == "error"


def test_duplicate_curation_rejected(kb: Path) -> None:
    edge, anchor = _pick_contain(kb)
    svc = _service(kb)
    source_id, target_id = edge["source_id"], edge["targets"][0]
    assert svc.curate_contain(edge["file"], source_id, target_id, anchor, confirmed_by="human:test")["status"] == "ok"
    second = svc.curate_contain(edge["file"], source_id, target_id, anchor, confirmed_by="human:test")
    assert second["status"] == "error"
    assert "已有" in second["message"]


def test_orphan_overlay_warns_without_creating_edge(kb: Path) -> None:
    from memoria.storage.sidecar import load_sidecar_for_md, save_sidecar_for_md

    edge, anchor = _pick_contain(kb)
    rel = edge["file"]
    # 一条在几何上不成立的 canonical id：source 与一个不存在的 target
    overlay = {
        "type": "contain",
        "source_id": edge["source_id"],
        "targets": ["kp-does-not-exist"],
        "relevance": 0.9,
        "contain_kind": "semantic",
        "derived_by": "author",
        "assertion_source": anchor,
        "curated_by": "agent:test",
        "curated_at": "2026-11-02T14:15:00+08:00",
    }
    full = kb / rel
    sidecar = load_sidecar_for_md(str(full), str(kb))
    sidecar.setdefault("edges", []).append(overlay)
    save_sidecar_for_md(str(full), str(kb), sidecar)

    graph = _graph(kb)
    assert len(graph["edges"]) == 62, "孤儿 overlay 不得造边"
    warnings = graph.get("warnings") or []
    assert any(item.get("code") == "contain_overlay_orphan" for item in warnings), warnings


def test_remove_curation_restores_structural(kb: Path) -> None:
    edge, anchor = _pick_contain(kb)
    svc = _service(kb)
    source_id, target_id = edge["source_id"], edge["targets"][0]
    if not any(
        e.get("contain_kind") == "semantic" for e in _graph(kb)["edges"]
    ):
        assert svc.curate_contain(edge["file"], source_id, target_id, anchor, confirmed_by="human:test")["status"] == "ok"
    removed = svc.remove_contain_curation(edge["file"], source_id, target_id, confirmed_by="human:test")
    assert removed["status"] == "ok"
    restored = _find(_graph(kb), source_id, target_id)
    assert restored["contain_kind"] == "structural"
    assert "assertion_source" not in restored
    assert restored.get("derived_by") == "system_range"


def test_agent_curation_goes_through_plan_op_not_a_new_tool() -> None:
    """v0.3（dec-20261102-5f71d1da）：agent 可确认 semantic，但入口是 propose_write 的
    `curate_contain` **op**（带证据/审计/撤销），不是另立一个只会写库的工具。"""
    plan_py = (_ROOT / "src/memoria/services/agent/plan.py").read_text(encoding="utf-8")
    apply_py = (_ROOT / "src/memoria/services/agent/apply.py").read_text(encoding="utf-8")
    assert 'OP_CURATE_CONTAIN = "curate_contain"' in plan_py
    assert '"curate_contain": _call_curate_contain' in apply_py


def test_ui_entry_wired() -> None:
    """UI 入口静态接线：人确认按钮 + RPC + i18n + 后端方法（防止只做后端没入口）。"""
    app = (_ROOT / "src/memoria/ui/static/app/js/app.js").read_text(encoding="utf-8")
    assert "-edge-btn-curate" in app
    assert 'call("curate_contain"' in app
    assert 'call("remove_contain_curation"' in app
    assert "buildContainAnchor" in app
    # 必须是应用内弹窗，不得弹浏览器原生 confirm（本轮人明确要求）
    assert "function showConfirm(title, message, okLabel, opts = {})" in app
    assert "const ok = await showConfirm(" in app
    assert 'window.confirm(T("cfg.edge.curateConfirm"' not in app
    zh = (_ROOT / "src/memoria/ui/static/app/i18n/zh-CN.js").read_text(encoding="utf-8")
    en = (_ROOT / "src/memoria/ui/static/app/i18n/en.js").read_text(encoding="utf-8")
    assert 'curateBtn: "确认为整体-部分"' in zh
    assert 'curateBtn: "Confirm whole-part"' in en
    ui_py = (_ROOT / "src/memoria/presentation/api/ui.py").read_text(encoding="utf-8")
    assert "def curate_contain(" in ui_py
    assert "def remove_contain_curation(" in ui_py
