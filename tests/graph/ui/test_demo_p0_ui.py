"""task-380 P0 UI 机检：Node demo 用例 + app/nav 点击 focus 接线。"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "src/memoria/ui/static/app"
NODE_TEST = Path(__file__).resolve().parent / "renderer_demo_p0.test.js"


def test_demo_renderer_node_suite() -> None:
    proc = subprocess.run(
        ["node", str(NODE_TEST)], cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120,
    )
    assert proc.returncode == 0, f"demo P0 套件失败：\n{proc.stdout[-3000:]}\n{proc.stderr[-3000:]}"
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["suite"] == "renderer_demo_p0"
    assert payload["failed"] == 0
    assert payload["hub"] == "kp-022"
    assert payload["shown"] >= 2
    names = {r["name"] for r in payload["results"]}
    for required in (
        "demo_fixture_has_focus_and_groups",
        "focus_centered_layout_not_vertical_collapse",
        "presentation_groups_collapse_expand_without_vm_change",
        "focus_switch_recenters_and_relayouts",
        "deferred_first_render_waits_for_layout_not_800_fallback",
        "resize_recomputes_layout_and_canvas_px",
        "force_layout_is_not_radial_ring_and_deterministic",
        "labels_use_presentation_names_and_truncate",
        "node_drag_pins_position_without_relayout",
        "blank_pan_moves_camera_only",
        "wheel_zoom_about_pointer_and_fit_reset",
        "rAF_force_animation_no_teleport_and_focus_transition",
        "animation_is_deterministic_two_runs",
        "pointermove_follows_without_4px_dead_zone",
        "drag_hold_keeps_neighbors_moving_no_rebuild",
    ):
        assert required in names


def test_app_wires_click_focus_and_dblclick_jump() -> None:
    app = (APP / "js/app.js").read_text(encoding="utf-8")
    assert "setFocusFrame" in app, "点击节点未接 Nav setFocusFrame"
    assert "multilevelFocusNode(node_id)" in app
    assert 'renderer.on("nodeDblClick"' in app, "双击跳编辑器入口缺失"
    assert "jumpToTarget(" in app
    assert "setFocusNode?.(focusId)" in app, "Renderer 未拿到 focus（布局不居中）"
    assert 'graph.multilevel' in app


def test_nav_set_focus_frame_contract() -> None:
    nav = (APP / "js/graph-multilevel/nav-controller.js").read_text(encoding="utf-8")
    assert "setFocusFrame(focus)" in nav
    assert 'event: "SET_FOCUS_FRAME"' in nav
    # 不改变 S5 的 FOCUS_NODE 语义：该方法独立，FOCUS_NODE 仍不改 frame
    assert "_on_FOCUS_NODE" in nav


def test_renderer_presentation_groups_are_not_vm_fields() -> None:
    src = (APP / "js/graph-multilevel/renderer-adapter.js").read_text(encoding="utf-8")
    assert "normalizeGroups(" in src
    assert "presentation_only" in src
    assert "getGroups()" in src
    assert "toggleGroup(" in src
    # 首帧不得用 800 回退尺寸；CSS 用实测 px；尺寸变化重排
    assert "|| 800" not in src and "|| 600" not in src
    assert "CONTAINER_NOT_LAID_OUT" in src
    assert "ResizeObserver" in src
    assert 'style.width = `${' in src
    assert "_onContainerResize" in src
    # task-381：力导向 + 指针拖拽/平移/缩放 + names 标签
    assert "computeForceLayout" in src and "runForceLayout" in src
    assert "FORCE" in src and "pinFocusCenter" in src
    assert "pointerdown" in src and "wheel" in src
    assert "setPointerCapture" in src or "pointerId" in src
    assert "presentation.names" in src or "this._presentation && this._presentation.names" in src
    assert "truncateLabel" in src
    # 不把 group 写成 VM cluster kind
    assert "kind: \"cluster\"" not in src[src.find("function normalizeGroups"): src.find("function normalizeGroups") + 1200]
