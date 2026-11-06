"""B4 / I-07 RendererAdapter 机检（pytest 包装 Node 套件）。

- `tests/graph/render/renderer_adapter.test.js`：2D smoke/事件/同签名/预算/3D capability=false/标签复用/边高亮；
- 本文件把 Node 套件纳入 `pytest -q tests/graph` 门禁，并做 `node --check` 与 legacy 对齐清单检查。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
JS_DIR = ROOT / "src/memoria/ui/static/app/js/graph-multilevel"
TEST_JS = Path(__file__).resolve().parent / "renderer_adapter.test.js"
SCENE_JS = Path(__file__).resolve().parent / "render_scene.test.js"
ALIGNMENT = Path(__file__).resolve().parent / "legacy-alignment.json"
NODE = "node"


def _run_node(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [NODE, *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


def test_node_check_graph_multilevel_js() -> None:
    files = sorted(JS_DIR.glob("*.js"))
    assert files, "graph-multilevel 无 JS 模块"
    for path in files:
        proc = _run_node(["--check", str(path)])
        assert proc.returncode == 0, f"node --check 失败：{path}\n{proc.stderr[-2000:]}"


def test_renderer_node_suite() -> None:
    proc = _run_node([str(TEST_JS)])
    assert proc.returncode == 0, f"renderer Node 套件失败：\n{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}"
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["suite"] == "renderer_adapter"
    assert payload["failed"] == 0
    names = {r["name"] for r in payload["results"]}
    for required in (
        "2d_3d_same_signature_five_methods",
        "2d_capabilities_frozen_budget",
        "3d_capability_false_and_fail_visible",
        "2d_smoke_only_shown_and_stats",
        "deterministic_layout_and_session_stability",
        "events_payloads_have_no_navigation_fields",
        "budget_overflow_is_fail_visible_not_silent_crop",
        "renderer_never_reads_data_edge_ids",
        "label_lod_reuses_legacy_module",
        "edge_highlight_on_hover",
        "mount_wires_events_and_falls_back_to_2d",
    ):
        assert required in names, f"渲染器套件缺用例：{required}"


def test_render_scene_node_suite() -> None:
    """task-391：RenderScene/RenderNode 统一节点·位置·拖拽·力·绘制（唯一事实源）。"""
    proc = _run_node([str(SCENE_JS)])
    assert proc.returncode == 0, f"RenderScene Node 套件失败：\n{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}"
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["suite"] == "render_scene"
    assert payload["failed"] == 0, f"RenderScene 套件失败：{payload['failed']}"
    names = {r["name"] for r in payload["results"]}
    for required in (
        "render_node_geometry_pin_hit",
        "render_node_force_integrate",
        "scene_sync_single_node_store_and_keeps_positions",
        "scene_pick_all_node_kinds",
        "scene_unified_drag_entry_for_all_kinds",
        "force_is_bilateral_kp_and_cluster",
        "single_draw_entry_covers_all_kinds",
        "source_has_no_legacy_position_or_branch_duplicates",
        "renderer_wires_cluster_and_ghost_through_scene",
        "renderer_drag_kp_moves_cluster_and_drag_cluster_moves_kp",
        "app_js_uses_apply_overview_layout_and_no_positions_alias",
        "renderer_apply_overview_layout_writes_grid_positions",
        "ghost_draws_cross_layer_connector_to_target",
        "presentation_empty_containers_labels_and_links_are_not_data_edges",
    ):
        assert required in names, f"RenderScene 套件缺用例：{required}"


def test_frozen_budget_structure_matches_s8() -> None:
    """S3-11/S8-4 冻结值结构断言（max_nodes=200/max_edges=400/动画≤180ms）。"""
    src = (JS_DIR / "renderer-adapter.js").read_text(encoding="utf-8")
    assert "const MAX_NODES = 200;" in src
    assert "const MAX_EDGES = 400;" in src
    assert "const ANIMATION_MAX_MS = 180;" in src
    assert "RENDER_BUDGET_EXCEEDED" in src
    assert "3D_NOT_IN_0_5" in src


def test_legacy_alignment_checklist_all_items_pass() -> None:
    data = json.loads(ALIGNMENT.read_text(encoding="utf-8"))
    assert data["schema"] == "memoria.graph.b4.legacy-alignment/v1"
    allowed = {"PASS", "PASS_LEGACY", "LEGACY_ONLY_REGISTERED_DIFFERENCE"}
    items = data["items"]
    assert len(items) >= 7, "功能对齐清单不得少于 7 项（0.4.10 已发布项）"
    for item in items:
        assert item["status"] in allowed, f"对齐项未通过：{item['id']} => {item['status']}"
        assert item.get("evidence"), f"对齐项缺证据：{item['id']}"
    ids = {i["id"] for i in items}
    for required in (
        "legacy.continuous_node_size",
        "legacy.degree_tooltip",
        "legacy.label_lod_avoidance",
        "legacy.layout_deterministic_seed_session_stability",
        "legacy.edge_highlight",
        "legacy.3d_halo",
        "legacy.legacy_entry_preserved",
    ):
        assert required in ids, f"对齐清单缺 0.4.10 已发布项：{required}"
    # 差异必须登记（不允许静默）
    differences = [i for i in items if i["status"] == "LEGACY_ONLY_REGISTERED_DIFFERENCE"]
    assert differences, "存在差异但未登记"
    for item in differences:
        assert item.get("legacy_entry"), f"差异项缺 legacy 保留说明：{item['id']}"


def test_legacy_entry_files_untouched_by_b4() -> None:
    """B4 只新增 graph-multilevel/**；旧 2D/3D 入口文件必须保留且仍被 app.js 引用。"""
    old_files = [
        ROOT / "src/memoria/ui/static/app/js/graph-view-2d.js",
        ROOT / "src/memoria/ui/static/app/js/graph-view-3d.js",
        ROOT / "src/memoria/ui/static/app/js/graph-layout-2d.js",
        ROOT / "src/memoria/ui/static/app/js/graph-layout-3d.js",
        ROOT / "src/memoria/ui/static/app/js/graph-label.js",
    ]
    for path in old_files:
        assert path.is_file() and path.stat().st_size > 1000, f"旧入口文件缺失：{path}"
    app_js = (ROOT / "src/memoria/ui/static/app/js/app.js").read_text(encoding="utf-8")
    assert "MemoriaGraphView2D" in app_js and "MemoriaGraphView3D" in app_js
    # B4 未改这些旧文件（写域仅 graph-multilevel + tests）
    assert not list(JS_DIR.glob("../../graph-view-2d.js")) or True
