"""B6 / S7：5 个只读工具（task-353）；冻结依据 S7-agent-v1 + S7a。

覆盖：工具面/只读边界、ViewResponse 字段与 edges 只含 shown、edition/幂等/审计、
预算/截断、expand 不改 nav、resolve_ref excerpt 上限/stale、错误码、G-G7。
"""
from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from memoria.graph.multilevel.audit import AuditError  # noqa: E402
from memoria.graph.multilevel.datasource import snapshot_kb  # noqa: E402
from memoria.graph.multilevel.g6 import G6Store, G7Store  # noqa: E402
from memoria.services.agent.tools.graph import (  # noqa: E402
    GraphToolset,
    TOOL_NAMES,
    WRITE_TOOL_NAMES,
    make_graph_tools,
)


def test_build_kb_tools_wires_graph_tools_read_only(kb: Path):
    """B6.1（task-356）：agent 工具面实际返回五把 graph 工具，且均 read_only。"""
    from memoria.services.agent.tools.kb import KB_TOOL_NAMES, build_kb_tools

    built = tuple(tool.name for tool in build_kb_tools(str(kb)))
    assert built == KB_TOOL_NAMES
    tools = {tool.name: tool for tool in build_kb_tools(str(kb))}
    for name in TOOL_NAMES:
        assert name in tools, name
        assert tools[name].read_only is True, name
    assert "graph_path" not in tools
    assert not (set(tools) & set(WRITE_TOOL_NAMES))

KB_FIXTURE = REPO / "tests" / "graph" / "fixtures" / "kb-mini"


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    dst = tmp_path / "kb"
    shutil.copytree(KB_FIXTURE, dst)
    return dst


@pytest.fixture()
def toolset(kb: Path) -> GraphToolset:
    return GraphToolset(kb)


def _call(toolset: GraphToolset, name: str, args: dict) -> tuple[dict, object]:
    tools = {t.name: t for t in toolset.tools()}
    out = tools[name].handler(args)
    return json.loads(out.text), out


def _audit_lines(kb: Path) -> list[dict]:
    path = kb / ".memoria" / "agent" / "audit" / "graph" / "audit.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# ── 工具面 / 只读边界 ────────────────────────────────────────────────


def test_tool_surface_is_five_read_only_tools(toolset: GraphToolset):
    tools = {t.name: t for t in toolset.tools()}
    assert tuple(sorted(tools)) == tuple(sorted(TOOL_NAMES))
    assert len(tools) == 5
    assert "graph_path" not in tools  # S7-3：v1 无 path
    for name, tool in tools.items():
        assert tool.read_only is True, name
        props = tool.parameters["properties"]
        assert "kb_id" in props, name
        assert "expected_edition" in props, name


def test_no_write_tool_names_or_write_calls():
    source = (REPO / "src" / "memoria" / "services" / "agent" / "tools" / "graph.py").read_text(
        encoding="utf-8")
    for forbidden in ("save_sidecar", "atomic_write_yaml", "graph-groups", "delete_sidecar"):
        assert forbidden not in source
    tools = {t.name for t in make_graph_tools(KB_FIXTURE)}
    assert tools == set(TOOL_NAMES)
    assert not (tools & set(WRITE_TOOL_NAMES))
    # 注册的 Tool 名只允许 5 个只读名（S7-3）；写工具不得有实现方法
    for name in WRITE_TOOL_NAMES:
        assert f"def {name}(" not in source


def test_read_only_does_not_touch_fact_source(kb: Path, toolset: GraphToolset):
    before = snapshot_kb(kb)
    _call(toolset, "graph_focus", {"kb_id": "kb-mini", "focus": "ch1-sampling"})
    _call(toolset, "graph_summary", {"kb_id": "kb-mini"})
    after = snapshot_kb(kb)
    # 唯一允许的变化：append-only 审计（cache 未被本测试触发）
    changed = {k for k in before if before[k] != after.get(k)}
    added = set(after) - set(before)
    assert all(k.startswith(".memoria/agent/audit/graph/") for k in changed)
    assert all(k.startswith(".memoria/agent/audit/graph/") for k in added)


# ── focus / ViewResponse ────────────────────────────────────────────


def test_focus_response_fields_and_edges_only_shown(toolset: GraphToolset):
    payload, out = _call(toolset, "graph_focus",
                        {"kb_id": "kb-mini", "focus": "ch1-sampling"})
    assert out.error is False
    for key in ("kb_id", "level_id", "view_family_id", "dimension_id", "data_state",
                "nodes", "edges", "clusters", "suppressed_count", "unknown_count",
                "suppressed_summary", "rule_histogram", "truncated", "edition_sha",
                "audit_id"):
        assert key in payload, key
    assert payload["edition_sha"] == toolset.edition_sha
    assert payload["edges"] and all(e["presence"] == "shown" for e in payload["edges"])
    assert payload["suppressed_count"] >= 0
    assert set(payload["suppressed_summary"]) == set(payload["rule_histogram"])
    assert payload["truncated"] is False


def test_focus_budget_truncates_visibly(toolset: GraphToolset):
    payload, out = _call(toolset, "graph_focus",
                        {"kb_id": "kb-mini", "focus": "ch1-sampling", "max_tokens": 600})
    assert out.error is False
    assert payload["truncated"] is True
    assert payload["omitted"]["nodes"] + payload["omitted"]["edges"] > 0


def test_focus_budget_too_small_returns_code(toolset: GraphToolset):
    payload, out = _call(toolset, "graph_focus",
                        {"kb_id": "kb-mini", "focus": "ch1-sampling", "max_tokens": 1})
    assert out.error is True
    assert out.code == "GRAPH_TOOL_BUDGET_EXCEEDED"
    assert payload["code"] == "GRAPH_TOOL_BUDGET_EXCEEDED"


def test_focus_unknown_focus_is_input_invalid(toolset: GraphToolset):
    payload, out = _call(toolset, "graph_focus",
                        {"kb_id": "kb-mini", "focus": "not-a-kp"})
    assert out.error is True
    assert out.code == "GRAPH_TOOL_INPUT_INVALID"


def test_focus_rejects_unsupported_dimension(toolset: GraphToolset):
    payload, out = _call(toolset, "graph_focus",
                        {"kb_id": "kb-mini", "focus": "ch1-sampling", "dimension": "A"})
    assert out.error is True
    assert out.code == "GRAPH_TOOL_INPUT_INVALID"


# ── edition / 幂等 / 审计 ────────────────────────────────────────────


def test_expected_edition_mismatch_is_stale(toolset: GraphToolset):
    payload, out = _call(toolset, "graph_summary",
                        {"kb_id": "kb-mini", "expected_edition": "0" * 64})
    assert out.error is True
    assert out.code == "GRAPH_ANCHOR_STALE"
    assert payload["detail"]["legacy_code"] == "GRAPH_EDITION_STALE"


def test_idempotent_same_args_same_payload_and_audit_each_call(kb: Path, toolset: GraphToolset):
    args = {"kb_id": "kb-mini", "focus": "ch1-lowpass"}
    first, _ = _call(toolset, "graph_focus", args)
    second, _ = _call(toolset, "graph_focus", args)
    a = {k: v for k, v in first.items() if k != "audit_id"}
    b = {k: v for k, v in second.items() if k != "audit_id"}
    assert a == b
    records = [r for r in _audit_lines(kb) if r["ref"] == "graph_focus"]
    assert len(records) == 2  # append-only：每次调用都审计
    for record in records:
        assert record["kind"] == "graph_tool_call"
        assert record["detail"]["write_attempts"] == 0
        assert record["detail"]["read_only"] is True
        assert "excerpt" not in json.dumps(record["detail"])


def test_audit_failure_is_visible(kb: Path, toolset: GraphToolset, monkeypatch):
    def boom(**kwargs):
        raise AuditError("disk full")

    monkeypatch.setattr(toolset._audit, "append", boom)
    payload, out = _call(toolset, "graph_summary", {"kb_id": "kb-mini"})
    assert out.error is True
    assert out.code == "GRAPH_TOOL_AUDIT_FAILED"


# ── explain / expand / summary ──────────────────────────────────────


def test_explain_semantic_edge(toolset: GraphToolset):
    focus, _ = _call(toolset, "graph_focus",
                    {"kb_id": "kb-mini", "focus": "ch1-sampling", "max_tokens": 4000})
    semantic = next(e for e in focus["edges"] if "ch1-lowpass" in e["id"])
    payload, out = _call(toolset, "graph_explain_edge",
                        {"kb_id": "kb-mini", "edge_id": semantic["id"]})
    assert out.error is False
    assert payload["relation_class"] == "semantic"
    assert payload["claim_type"] == "graph_relation"
    assert payload["presence"] == "shown"
    assert payload["source_refs"]  # 引用完整（S8-6）
    # 受控解释：从 target 视角看这条边被抑制（S7-2/S7-11：suppressed 可解释）
    suppressed = [f for f in payload["alternate_frames"] if f["presence"] == "suppressed"]
    assert suppressed and suppressed[0]["rule_id"]
    # 审计/响应都不得带正文
    assert "正文" not in json.dumps(payload, ensure_ascii=False)


def test_explain_unknown_edge_is_input_invalid(toolset: GraphToolset):
    payload, out = _call(toolset, "graph_explain_edge",
                        {"kb_id": "kb-mini", "edge_id": "contain|a|b"})
    assert out.error is True
    assert out.code == "GRAPH_TOOL_INPUT_INVALID"


def test_expand_cluster_is_read_only_and_nav_unchanged(toolset: GraphToolset):
    summary, _ = _call(toolset, "graph_summary", {"kb_id": "kb-mini"})
    multi = [c for c in summary["clusters"] if c["member_count"] >= 2]
    assert multi, "fixture 应有 ≥2 成员的簇"
    cluster = multi[0]
    first, out = _call(toolset, "graph_expand_cluster",
                      {"kb_id": "kb-mini", "cluster_id": cluster["cluster_id"]})
    second, _ = _call(toolset, "graph_expand_cluster",
                      {"kb_id": "kb-mini", "cluster_id": cluster["cluster_id"]})
    assert out.error is False
    assert first["nav_unchanged"] is True
    assert first["members"] == second["members"]
    assert {k: v for k, v in first.items() if k != "audit_id"} == {
        k: v for k, v in second.items() if k != "audit_id"}


def test_summary_shape(toolset: GraphToolset):
    payload, out = _call(toolset, "graph_summary", {"kb_id": "kb-mini"})
    assert out.error is False
    assert payload["data_state"] in {"ok", "empty_nosemantic"}
    assert payload["clusters"] and all(
        {"cluster_id", "run_id", "cluster_key", "label", "member_count", "coverage"}
        <= set(c) for c in payload["clusters"])
    assert {"kps", "edges", "semantic_edges", "clusters", "suppressed", "unknown"} <= set(
        payload["counts"])


# ── resolve_ref ─────────────────────────────────────────────────────


def test_resolve_ref_by_kp_and_file(toolset: GraphToolset):
    by_kp, out = _call(toolset, "graph_resolve_ref",
                      {"kb_id": "kb-mini", "kp_id": "ch1-lowpass"})
    assert out.error is False
    assert by_kp["resolved"] is True
    assert by_kp["detail"]["anchor_verified"] is True
    assert 0 < len(by_kp["source_excerpt"]) <= 500
    by_file, out2 = _call(toolset, "graph_resolve_ref",
                         {"kb_id": "kb-mini", "file": "docs/ch01-sampling.md", "line": 5})
    assert out2.error is False
    assert by_file["resolved"] is True
    assert len(by_file["source_excerpt"]) <= 500


def test_resolve_ref_unknown_kp_is_stale_not_fabricated(toolset: GraphToolset):
    payload, out = _call(toolset, "graph_resolve_ref",
                        {"kb_id": "kb-mini", "kp_id": "kpi-does-not-exist"})
    assert out.error is False  # 可见的 resolved=false，不静默、不编造
    assert payload["resolved"] is False
    assert payload["code"] == "GRAPH_ANCHOR_STALE"
    assert "source_excerpt" not in payload


def test_resolve_ref_rejects_path_traversal(toolset: GraphToolset):
    payload, out = _call(toolset, "graph_resolve_ref",
                        {"kb_id": "kb-mini", "file": "../outside.md", "line": 1})
    assert out.error is True
    assert out.code == "GRAPH_TOOL_INPUT_INVALID"


def test_resolve_ref_stale_when_range_broken(toolset: GraphToolset, kb: Path):
    sidecar = kb / ".memoria" / "sidecars" / "docs" / "ch01-sampling.memoria.yaml"
    text = sidecar.read_text(encoding="utf-8")
    text = text.replace("snippet: '## 1.1 低通抽样定理'", "snippet: '### 不存在的标题'")
    sidecar.write_text(text, encoding="utf-8")
    payload, out = _call(toolset, "graph_resolve_ref",
                        {"kb_id": "kb-mini", "kp_id": "ch1-lowpass"})
    assert out.error is False
    assert payload["resolved"] is False
    assert payload["code"] == "GRAPH_ANCHOR_STALE"


# ── G7 / G-G7 ───────────────────────────────────────────────────────


def test_g7_envelope_passes_g_g7(kb: Path, toolset: GraphToolset):
    focus, _ = _call(toolset, "graph_focus", {"kb_id": "kb-mini", "focus": "ch1-sampling"})
    summary, _ = _call(toolset, "graph_summary", {"kb_id": "kb-mini"})
    envelope = toolset.g7_envelope(run_ids=[summary["run_id"]], frame_ids=[focus["frame_id"]])
    assert envelope["write_attempts"] == 0
    assert envelope["read_only_ratio"] == 1.0
    assert envelope["reference_completeness"] > 0
    assert "excerpt" not in json.dumps(envelope)
    g6_doc = {
        "g6_version": 1,
        "data_source_sha": toolset.edition_sha,
        "run_ids": [summary["run_id"]],
        "registry_sha": "b" * 64,
        "vm_sha": "c" * 64,
        "frame_ids": [focus["frame_id"]],
        "frame_sha": "d" * 64,
        "nav_sha": "e" * 64,
        "rule_histogram": {"hop.budget": 1},
        "node_count": len(focus["nodes"]),
        "edge_count": len(focus["edges"]),
        "subset_ok": True,
        "determinism_sha": "f" * 64,
        "closure_violations": 0,
        "behind_violations": 0,
        "history_signed": False,
    }
    g6 = G6Store(kb / ".memoria")
    written = g6.write(copy.deepcopy(g6_doc))
    g6.update_baseline(written["snapshot_id"], decision_id="dec-b6-test")
    g7 = G7Store(kb / ".memoria")
    report = g7.assert_g_g7(envelope, g6=g6)
    assert report["ok"] is True
    assert report["g_g7"] == {"write_attempts": 0, "read_only_ratio": 1.0}
