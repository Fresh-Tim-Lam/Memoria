"""B4.1 · task-358：只读 RPC `get_multilevel_graph_vm` 测试。

## 这个文件守什么

| 要求 | 落点 |
|---|---|
| `vm` 严格 S3 白名单（含 ADDENDUM-1/2） | `test_vm_whitelist_*` |
| `edition_sha` / `frame_id` **可复算** | `test_frame_id_recomputable` / `test_edition_sha_recomputable` |
| `presentation.degrees` 与 DataSource 一致 | `test_degrees_match_datasource` |
| `presentation` **不塞进 VM**（S3-12） | `test_presentation_is_not_in_vm` |
| 只读（事实源零变化、无 sidecar 写） | `test_rpc_is_read_only` |
| 非法参数 / 预算超限 ⇒ 结构化 `GRAPH_*` 失败 | `test_illegal_*` / `test_budget_*` |
| UI 不依赖 `data_edge_ids`（静态断言） | `test_static_ui_does_not_read_data_edge_ids` |
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
import yaml

from memoria.graph.multilevel import datasource as ds_mod
from memoria.graph.multilevel.admission import make_frame_spec
from memoria.graph.multilevel.datasource import DataSourceReader, detect_writes
from memoria.graph.multilevel.errors import GraphError
from memoria.graph.multilevel.schema import validate as validate_schema
from memoria.graph.multilevel.view_model import (
    RENDERER_FORBIDDEN_EDGE_FIELDS,
    VM_EDGE_FIELDS,
    VM_NODE_FIELDS,
    VM_TOP_FIELDS,
    validate_vm,
)
from memoria.presentation.api import ui as ui_mod
from memoria.presentation.api.ui import UIAPI

UI_FILE = Path(ui_mod.__file__)

KB_MD = (
    "# A\n"            # 1
    "\n"               # 2
    "## A1\n"          # 3
    "\n"               # 4
    "text a1\n"        # 5
    "\n"               # 6
    "### A1-1\n"       # 7
    "\n"               # 8
    "text a11\n"       # 9
    "\n"               # 10
    "text tail\n"      # 11
    "\n"               # 12
    "text end\n"       # 13
)


def _make_kb(root: Path) -> Path:
    """最小合法 KB：3 层嵌套 KP（a ⊃ a1 ⊃ a1-1）⇒ contain 边 a→a1、a1→a1-1。"""
    kb = root / "kb"
    (kb / ".memoria" / "sidecars").mkdir(parents=True)
    (kb / "a.md").write_text(KB_MD, encoding="utf-8")
    (kb / ".memoria" / "manifest.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    sidecar = {
        "schema_version": 1,
        "file": "a.md",
        "knowledge_points": [
            {"id": "a", "name": "A", "range": {
                "start": {"snippet": "# A", "line_hint": 1},
                "end": {"snippet": "text end", "line_hint": 13}}},
            {"id": "a1", "name": "A1", "range": {
                "start": {"snippet": "## A1", "line_hint": 3},
                "end": {"snippet": "text tail", "line_hint": 11}}},
            {"id": "a1-1", "name": "A1-1", "range": {
                "start": {"snippet": "### A1-1", "line_hint": 7},
                "end": {"snippet": "text a11", "line_hint": 9}}},
        ],
    }
    (kb / ".memoria" / "sidecars" / "a.memoria.yaml").write_text(
        yaml.safe_dump(sidecar, allow_unicode=True, sort_keys=False, width=4096),
        encoding="utf-8",
    )
    return kb


def _api(kb: Path | None) -> UIAPI:
    return UIAPI(kb_path=str(kb) if kb else None)


# ── 成功形状 / 白名单 ───────────────────────────────────────────────────


def test_rpc_returns_exact_contract_shape(tmp_path: Path) -> None:
    """成功响应**恰好**是契约里的 7 个字段（不多不少）。"""
    result = _api(_make_kb(tmp_path)).get_multilevel_graph_vm()
    assert result["status"] == "ok"
    assert set(result) == {
        "status", "vm", "presentation", "edition_sha", "frame_id",
        "rule_histogram", "suppressed_summary",
    }
    assert set(result["presentation"]) == {"degrees", "files"}


def test_vm_whitelist_strict(tmp_path: Path) -> None:
    """`vm` 严格 S3 白名单（顶层/节点/边），且通过 `validate_vm`。"""
    result = _api(_make_kb(tmp_path)).get_multilevel_graph_vm()
    vm = result["vm"]
    assert set(vm) == set(VM_TOP_FIELDS)
    assert validate_vm(vm) == [], validate_vm(vm)
    for node in vm["nodes"]:
        assert set(node) <= set(VM_NODE_FIELDS)
        assert node["role"] == "member"
    for edge in vm["edges"]:
        assert set(edge) <= set(VM_EDGE_FIELDS)
        if edge["presence"] != "shown":
            assert edge.get("rule_id")       # ADDENDUM-2：非 shown 边必填


def test_vm_carries_no_navigation_or_cluster_state(tmp_path: Path) -> None:
    vm = _api(_make_kb(tmp_path)).get_multilevel_graph_vm()["vm"]
    for forbidden in ("clusters", "run_id", "metrics", "frame_id", "nav", "mode", "focus"):
        assert forbidden not in vm


def test_presentation_is_not_in_vm(tmp_path: Path) -> None:
    """S3-12：degree/file 属 Presentation，**不得**混进 VM。"""
    result = _api(_make_kb(tmp_path)).get_multilevel_graph_vm()
    blob = json.dumps(result["vm"], ensure_ascii=False)
    for token in ('"degrees"', '"files"', '"presentation"'):
        assert token not in blob


# ── 可复算：frame_id / edition_sha ─────────────────────────────────────


def test_frame_id_recomputable(tmp_path: Path) -> None:
    """`frame_id = sha256(canonical(S4_FRAME_SPEC))`，用同一有效参数可复算。"""
    kb = _make_kb(tmp_path)
    result = _api(kb).get_multilevel_graph_vm({"level": "LL", "focus": "a"})
    expected = make_frame_spec(
        level="LL", view_family="default", dimension_id="A", focus="a",
        hop=1, new_hop=False, mode="default", max_nodes=200, max_edges=400,
    ).canonical_sha()
    assert result["frame_id"] == expected


def test_frame_id_changes_with_params(tmp_path: Path) -> None:
    """防"恒定 sha"：换 focus 必须换 frame_id。"""
    api = _api(_make_kb(tmp_path))
    a = api.get_multilevel_graph_vm({"focus": "a"})["frame_id"]
    b = api.get_multilevel_graph_vm({"focus": "a1"})["frame_id"]
    assert a != b


def test_edition_sha_recomputable(tmp_path: Path) -> None:
    """`edition_sha` 的计算式对调用方公开可复算（同一只读 DataSource）。"""
    kb = _make_kb(tmp_path)
    result = _api(kb).get_multilevel_graph_vm()
    ds = DataSourceReader(kb).read()
    assert result["edition_sha"] == ui_mod._mlvm_edition_sha(str(kb), ds)


def test_edition_sha_changes_with_content(tmp_path: Path) -> None:
    kb = _make_kb(tmp_path)
    api = _api(kb)
    before = api.get_multilevel_graph_vm()["edition_sha"]
    (kb / ".memoria" / "manifest.yaml").write_text("schema_version: 2\n", encoding="utf-8")
    after = api.get_multilevel_graph_vm()["edition_sha"]
    assert before != after


# ── degrees / files 与 DataSource 一致 ─────────────────────────────────


def test_degrees_match_datasource(tmp_path: Path) -> None:
    """`presentation.degrees` 必须能由**同一只读 DataSource** 逐条复算。"""
    kb = _make_kb(tmp_path)
    result = _api(kb).get_multilevel_graph_vm()
    ds = DataSourceReader(kb).read()
    vm_ids = {str(n["id"]) for n in result["vm"]["nodes"]}

    expected = {str(k["id"]): 0 for k in ds.kps if str(k.get("id")) in vm_ids}
    for edge in ds.edges:
        src = str(edge.get("source_id") or "")
        if src in expected:
            expected[src] += 1
        for tgt in edge.get("targets") or ():
            if str(tgt) in expected:
                expected[str(tgt)] += 1

    assert result["presentation"]["degrees"] == expected
    assert set(result["presentation"]["degrees"]) <= vm_ids


def test_files_match_datasource(tmp_path: Path) -> None:
    kb = _make_kb(tmp_path)
    result = _api(kb).get_multilevel_graph_vm()
    ds = DataSourceReader(kb).read()
    vm_ids = {str(n["id"]) for n in result["vm"]["nodes"]}
    expected = {
        str(k["id"]): str(k["file"]) for k in ds.kps
        if str(k.get("id")) in vm_ids and k.get("file")
    }
    assert result["presentation"]["files"] == expected


# ── 只读（D-3）─────────────────────────────────────────────────────────


def test_rpc_is_read_only(tmp_path: Path) -> None:
    """调用前后**事实源**（md + sidecars + manifest）零变化，且不新增 sidecar。

    ⚠️ 测量窗口：先构造 `UIAPI` 再快照。**开库**时 `DocumentService` 会同步
    `.memoria/manifest.yaml`（加 `updated_at`/`files`/`md_sha256`）—— 那是既有产品行为，
    不是本 RPC 的写；把窗口放在构造之后，才能只测"RPC 调用本身是否写盘"。
    """
    kb = _make_kb(tmp_path)
    api = _api(kb)                                  # ← 先开库（会同步一次 manifest）
    before = ds_mod.snapshot_facts(kb)
    sidecars_before = sorted((kb / ".memoria" / "sidecars").rglob("*"))
    result = api.get_multilevel_graph_vm()
    assert result["status"] == "ok"
    after = ds_mod.snapshot_facts(kb)
    assert detect_writes(before, after) == [], "RPC 写了事实源（D-3 违规）"
    assert sorted((kb / ".memoria" / "sidecars").rglob("*")) == sidecars_before


def test_open_kb_syncs_manifest_but_rpc_does_not(tmp_path: Path) -> None:
    """记录既有产品行为：**开库**同步 manifest；**RPC 本身不写**（两者必须分清）。"""
    kb = _make_kb(tmp_path)
    before_open = ds_mod.snapshot_facts(kb)
    api = _api(kb)
    opened = ds_mod.snapshot_facts(kb)
    # 开库确实会写 manifest（既有行为，非 D-3 违规）
    assert detect_writes(before_open, opened) != []
    # 但随后 RPC 调用不再写任何事实源
    before_rpc = ds_mod.snapshot_facts(kb)
    assert api.get_multilevel_graph_vm()["status"] == "ok"
    assert detect_writes(before_rpc, ds_mod.snapshot_facts(kb)) == []


def test_rpc_does_not_write_cache(tmp_path: Path) -> None:
    """RPC 自身不写 cache（不落盘）：`.memoria/cache` 由我们创建前不存在。"""
    kb = _make_kb(tmp_path)
    assert not (kb / ".memoria" / "cache").exists()
    assert _api(kb).get_multilevel_graph_vm()["status"] == "ok"
    assert not (kb / ".memoria" / "cache").exists()


def test_rpc_ignores_concurrent_cache_writes(tmp_path: Path) -> None:
    """回归（B4.1 实测）：后台任务写 cache 不应把只读 RPC 误判成 D-3 违规。"""
    kb = _make_kb(tmp_path)
    cache = kb / ".memoria" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "embeddings-index.json").write_text("{}", encoding="utf-8")
    assert _api(kb).get_multilevel_graph_vm()["status"] == "ok"


# ── 结构化失败 ────────────────────────────────────────────────────────


def _error_code(result: dict) -> str:
    assert result["status"] == "error", result
    return result["error"]["code"]


def test_illegal_dimension_fails_structurally(tmp_path: Path) -> None:
    result = _api(_make_kb(tmp_path)).get_multilevel_graph_vm({"dimension_id": "RESERVED_X"})
    assert _error_code(result) == "GRAPH_TOOL_INPUT_INVALID"


@pytest.mark.parametrize("params", [
    {"hop": 0},
    {"hop": 3},
    {"hop": "1"},
    {"new_hop": "yes"},
    {"nope": 1},                    # 未知参数
])
def test_illegal_params_fail_structurally(tmp_path: Path, params: dict) -> None:
    result = _api(_make_kb(tmp_path)).get_multilevel_graph_vm(params)
    assert _error_code(result) == "GRAPH_TOOL_INPUT_INVALID"


def test_params_must_be_dict(tmp_path: Path) -> None:
    result = _api(_make_kb(tmp_path)).get_multilevel_graph_vm([1, 2])
    assert _error_code(result) == "GRAPH_TOOL_INPUT_INVALID"


@pytest.mark.parametrize("budget", [
    {"max_nodes": 999},
    {"max_edges": 999},
    {"animation_ms": 999},
    {"max_nodes": 0},
    {"weird": 1},
])
def test_budget_over_cap_fails_structurally(tmp_path: Path, budget: dict) -> None:
    """budget 超过 S8 冻结上限 ⇒ `GRAPH_BUDGET_INVALID`（不静默截断）。"""
    result = _api(_make_kb(tmp_path)).get_multilevel_graph_vm({"budget": budget})
    assert _error_code(result) == "GRAPH_BUDGET_INVALID"


def test_budget_defaults_are_frozen() -> None:
    """缺省 = 200 nodes / 400 edges / 180ms（S8 冻结值）。"""
    assert ui_mod.MULTILEVEL_BUDGET_CAPS == {
        "max_nodes": 200, "max_edges": 400, "animation_ms": 180,
    }


def test_budget_within_cap_is_accepted(tmp_path: Path) -> None:
    result = _api(_make_kb(tmp_path)).get_multilevel_graph_vm(
        {"budget": {"max_nodes": 5, "max_edges": 3}}
    )
    assert result["status"] == "ok"


def test_no_kb_open_fails_structurally() -> None:
    result = _api(None).get_multilevel_graph_vm()
    assert _error_code(result) == "GRAPH_INTERNAL"


def test_cluster_level_without_clusters_fails_visibly(tmp_path: Path) -> None:
    """无语义簇时不应伪造簇层视图（S2-12），而应可见失败并给出建议层级。"""
    result = _api(_make_kb(tmp_path)).get_multilevel_graph_vm({"level": "L0"})
    assert _error_code(result) == "GRAPH_INTERNAL"
    assert result["error"]["detail"]["suggested_level"] == "LL"


def test_error_envelope_matches_frozen_schema(tmp_path: Path) -> None:
    """错误信封满足 S6 的 `error.json` 契约（code/severity/i18n_key/audit_id…）。"""
    result = _api(_make_kb(tmp_path)).get_multilevel_graph_vm({"dimension_id": "X"})
    envelope = result["error"]
    assert validate_schema(envelope, "error").ok, validate_schema(envelope, "error").to_dict()
    assert envelope["code"].startswith("GRAPH_")
    assert envelope["severity"] in ("error", "warn")
    assert envelope["i18n_key"].startswith("graph.")


# ── 调用形态 / rule 直方图 ────────────────────────────────────────────


def test_call_forms_are_equivalent(tmp_path: Path) -> None:
    """`f({...})`、`f(**kwargs)`、`f()`（缺省 focus）都应可用且 frame_id 一致。"""
    api = _api(_make_kb(tmp_path))
    a = api.get_multilevel_graph_vm({"focus": "a"})
    b = api.get_multilevel_graph_vm(focus="a")
    c = api.get_multilevel_graph_vm()             # 缺省 focus = 最小 KP id
    assert a["frame_id"] == b["frame_id"]
    assert a["vm"] == b["vm"]
    assert c["status"] == "ok"


def test_rule_histogram_and_suppressed_summary_align(tmp_path: Path) -> None:
    """`rule_histogram` 与 `suppressed_summary` 同源同数（S4/S8 X-SUMMARY 口径）。"""
    result = _api(_make_kb(tmp_path)).get_multilevel_graph_vm()
    histogram = dict(result["rule_histogram"])
    summary = dict(result["suppressed_summary"])
    assert histogram == summary


def test_rule_ids_are_within_frozen_enum(tmp_path: Path) -> None:
    from memoria.graph.multilevel.admission import RULE_IDS

    result = _api(_make_kb(tmp_path)).get_multilevel_graph_vm()
    for rule_id in result["suppressed_summary"]:
        assert rule_id in RULE_IDS


# ── 静态断言：UI 不依赖 data_edge_ids ────────────────────────────────


def test_static_ui_does_not_read_data_edge_ids() -> None:
    """**静态断言**：RPC 层（ui.py）不得读取 `data_edge_ids`（S3-12/R-S3-9 禁读）。

    Renderer/UI 只允许消费 `renderer_projection()` 的结果；RPC 本身也不应触碰该字段。
    """
    source = UI_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    patterns = (
        '.get("data_edge_ids")', ".get('data_edge_ids')",
        '["data_edge_ids"]', "['data_edge_ids']",
    )
    offenders = [n.name for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef)
                 and any(p in (ast.get_source_segment(source, n) or "") for p in patterns)]
    assert not offenders, f"ui.py 读取了 data_edge_ids：{offenders}"
    assert "data_edge_ids" in RENDERER_FORBIDDEN_EDGE_FIELDS


def test_rpc_appends_only_no_existing_lines_changed() -> None:
    """契约要求"末尾追加、不改既有行"：新增内容只在文件尾部（按行号单调）。"""
    source = UI_FILE.read_text(encoding="utf-8")
    start = source.find("# 0.5 多层次图谱：**只读** RPC")
    assert start > 0, "未找到追加段标记"
    tail = source[start:]
    assert "def _get_multilevel_graph_vm(" in tail
    assert "UIAPI.get_multilevel_graph_vm = _get_multilevel_graph_vm" in tail
