"""agent 全权接管 semantic contain 的端到端钉子（v0.3：`propose_write` 的 curate_contain op）。

来源：人（2026-11-02）「新设计范式是 agent 全权接管知识组织设计，因为人的判断力不足，所以要做
agent 的能力」→ 决策 `dec-20261102-5f71d1da`（取代“仅人确认”）。

钉住：
1. plan 校验 + 编译：`curate_contain` op 编译出 `curate_contain` 原语，**校验期不落盘**；
2. apply：agent 写入 curation overlay，collect 输出 `contain_kind=semantic` +
   `curated_by=agent:plan` + `curated_at` + assertion_source，且其余边不变；
3. 证据 stale / 目标不是派生 contain 边 ⇒ 拒（不落盘）；
4. 提示词里 agent 能看到这个 op（否则模型不知道能用）。
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
SESSION = "session-test-agent-curate"


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


def _pick(kb: Path) -> tuple[dict, dict]:
    graph = _graph(kb)
    edge = next(e for e in graph["edges"] if e.get("type") == "contain")
    rel = edge["file"]
    lines = (kb / rel).read_text(encoding="utf-8").splitlines()
    line_no = next(i for i, line in enumerate(lines, 1) if line.strip())
    ev = {
        "file": rel,
        "line_start": line_no,
        "line_end": line_no,
        "quote_sha256": hashlib.sha256(lines[line_no - 1].encode("utf-8")).hexdigest(),
    }
    return edge, ev


def _plan(rel: str, source_id: str, target_id: str, ev: dict) -> dict:
    return {
        "v": 1,
        "txid": "20261102T141500Z-01",
        "intent": "agent 确认一条 contain 为整体-部分",
        "ops": [
            {
                "op": "curate_contain",
                "op_id": "c1",
                "file": rel,
                "source_id": source_id,
                "target_id": target_id,
                "assertion_source": ev,
            }
        ],
    }


def _find(graph: dict, source_id: str, target_id: str) -> dict:
    return next(
        e
        for e in graph["edges"]
        if e.get("type") == "contain"
        and e.get("source_id") == source_id
        and target_id in (e.get("targets") or [])
    )


def test_validate_and_compile_without_writing(kb: Path) -> None:
    from memoria.services.agent.apply import compile_plan
    from memoria.services.agent.plan import validate_plan

    edge, ev = _pick(kb)
    plan = _plan(edge["file"], edge["source_id"], edge["targets"][0], ev)
    checked = validate_plan(str(kb), plan)
    assert checked["status"] == "ok", checked["errors"]
    compiled = compile_plan(str(kb), plan)
    assert compiled["status"] == "ok", compiled.get("errors")
    prim = [c for c in compiled["calls"] if c.get("primitive") == "curate_contain"]
    assert prim and prim[0]["args"]["source_id"] == edge["source_id"]
    # 校验/编译不落盘
    assert _find(_graph(kb), edge["source_id"], edge["targets"][0])["contain_kind"] == "structural"


def test_apply_writes_audited_semantic_edge(kb: Path) -> None:
    from memoria.services.agent.apply import apply_plan

    edge, ev = _pick(kb)
    source_id, target_id = edge["source_id"], edge["targets"][0]
    baseline = {
        f"{e.get('type')}|{e.get('source_id')}|{(e.get('targets') or [''])[0]}": e
        for e in _graph(kb)["edges"]
    }
    result = apply_plan(str(kb), _plan(edge["file"], source_id, target_id, ev),
                        origin="human", session_id=SESSION)
    assert result["status"] == "ok", result
    graph = _graph(kb)
    merged = _find(graph, source_id, target_id)
    assert merged["contain_kind"] == "semantic"
    assert merged["derived_by"] == "author"
    assert merged["assertion_source"] == ev
    assert merged["curated_by"] == "agent:plan"
    assert merged["curated_at"]
    assert len(graph["edges"]) == 62 and len(graph["nodes"]) == 357
    changed = {
        key
        for key, value in {
            f"{e.get('type')}|{e.get('source_id')}|{(e.get('targets') or [''])[0]}": e
            for e in graph["edges"]
        }.items()
        if baseline.get(key) != value
    }
    assert changed == {f"contain|{source_id}|{target_id}"}
    # canonical schema 校验（semantic 必须带审计身份）
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((_ROOT / "docs/design/kg-edge-provenance.schema.json").read_text(encoding="utf-8"))
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(merged)) == []


def test_stale_evidence_rejected(kb: Path) -> None:
    from memoria.services.agent.apply import apply_plan
    from memoria.services.agent.plan import validate_plan

    edge, ev = _pick(kb)
    stale = dict(ev)
    stale["quote_sha256"] = "0" * 64
    plan = _plan(edge["file"], edge["source_id"], edge["targets"][0], stale)
    checked = validate_plan(str(kb), plan)
    assert checked["status"] != "ok"
    assert any(err.get("code") == "stale_evidence" for err in checked["errors"])
    applied = apply_plan(str(kb), plan, origin="human", session_id=SESSION)
    assert applied["status"] != "ok"
    assert _find(_graph(kb), edge["source_id"], edge["targets"][0])["contain_kind"] == "structural"


def test_non_derived_pair_rejected(kb: Path) -> None:
    from memoria.services.agent.apply import apply_plan

    edge, ev = _pick(kb)
    graph = _graph(kb)
    # 取一个不构成几何包含关系的 target（同一文件里排除现有 contain 的目标）
    rel = edge["file"]
    existing = {
        (e["source_id"], e["targets"][0])
        for e in graph["edges"]
        if e.get("type") == "contain" and e.get("source_id") == edge["source_id"]
    }
    candidates = [n["id"] for n in graph["nodes"] if n["id"] != edge["source_id"]]
    target = next((tid for tid in candidates if (edge["source_id"], tid) not in existing), None)
    if target is None:
        pytest.skip("没有可用的非包含 pair")
    result = apply_plan(str(kb), _plan(rel, edge["source_id"], target, ev),
                        origin="human", session_id=SESSION)
    assert result["status"] != "ok", "目标不是派生 contain 边时必须拒"
    assert _find(_graph(kb), edge["source_id"], edge["targets"][0])["contain_kind"] == "structural"


def test_agent_prompt_and_op_registered() -> None:
    plan_py = (_ROOT / "src/memoria/services/agent/plan.py").read_text(encoding="utf-8")
    apply_py = (_ROOT / "src/memoria/services/agent/apply.py").read_text(encoding="utf-8")
    kb_py = (_ROOT / "src/memoria/services/agent/tools/kb.py").read_text(encoding="utf-8")
    assert 'OP_CURATE_CONTAIN = "curate_contain"' in plan_py
    assert "_validate_curate_contain" in plan_py
    assert '"curate_contain": _call_curate_contain' in apply_py
    assert "⑱ `curate_contain`" in kb_py
