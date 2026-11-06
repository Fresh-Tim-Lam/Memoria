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
        "idle_motion_initial_focus_and_release_each_at_least_30_frames",
        "semantics_edge_dash_selection_group_and_dblclick",
        "view_snapshot_restores_positions_camera_selection",
    ):
        assert required in names


def test_app_wires_click_focus_and_dblclick_jump() -> None:
    app = (APP / "js/app.js").read_text(encoding="utf-8")
    assert "setFocusFrame" in app, "点击节点未接 Nav setFocusFrame"
    assert "multilevelFocusNode(node_id)" in app
    assert 'renderer.on("nodeDblClick"' in app, "双击跳编辑器入口缺失"
    assert "openGraphEditorJumpPreview" in app, "双击未先走小窗预览"
    assert "showLinkPanel(" in app
    assert "jumpToTarget(" in app
    assert "setBackgroundGhost" in app, "进入子图未保留父层 A 的背景幽灵"
    renderer = (APP / "js/graph-multilevel/renderer-adapter.js").read_text(encoding="utf-8")
    assert "setBackgroundGhost" in renderer
    assert "clearBackgroundGhost" in renderer


def test_legend_distinguishes_kp_group_collapsed_and_edge_dash() -> None:
    app = (APP / "js/app.js").read_text(encoding="utf-8")
    assert "ml-swatch--kp" in app and "ml-swatch--group" in app and "ml-swatch--collapsed" in app
    assert "legendGroup" in app and "legendCollapsed" in app
    css = (APP / "css/app.css").read_text(encoding="utf-8")
    assert ".ml-line--reference" in css and "dashed" in css
    assert ".ml-line--structural" in css and "solid" in css
    assert ".ml-swatch--group" in css and "clip-path" in css


def test_drilldown_and_back_controls() -> None:
    app = (APP / "js/app.js").read_text(encoding="utf-8")
    for token in (
        "enterMultilevelGroup",
        "backMultilevelView",
        "goToMultilevelDepth",
        "captureViewState",
        "restoreViewState",
        "graph-multilevel-crumb",
        "graph-multilevel-crumbs",
    ):
        assert token in app, f"缺少下钻/返回实现：{token}"
    # task-391 rev17（人的裁决）：drillbar 不再有「← 返回」按钮；返回唯一入口 = 节点 A（幽灵）。
    assert "graph-multilevel-back" not in app, "drillbar 仍生成返回按钮（应只有节点 A 作为返回入口）"
    assert "backMultilevelView" in app, "backMultilevelView 必须保留（节点 A / 面包屑使用）"
    assert 'aria-label="${esc(T("toolbar.back.title"))}"' not in app, "返回按钮可访问名称仍残留"
    css = (APP / "css/app.css").read_text(encoding="utf-8")
    assert ".graph-multilevel-back" not in css, "返回按钮 CSS 仍残留"
    assert ".graph-multilevel-crumb:focus-visible" in css
    assert ":focus-visible" in css
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
    # task-387：KP/group 形状、关联边虚线、选中/组/背景语义
    assert "EDGE_DASH" in src and "drawHexagon" in src and "drawGroupBadge" in src
    assert "selectNode(" in src and "clearSelection(" in src and "selectGroup(" in src
    assert 'reference: [5, 4]' in src and 'semantic: [2, 3]' in src
    assert "truncateLabel" in src
    # 不把 group 写成 VM cluster kind
    assert "kind: \"cluster\"" not in src[src.find("function normalizeGroups"): src.find("function normalizeGroups") + 1200]


def test_course_demo_h_a_routing_and_label_avoidance() -> None:
    app = (APP / "js/app.js").read_text(encoding="utf-8")
    for token in (
        "hOverview",
        "hChapterFocus",
        "multilevelHierarchyPresentation",
        "multilevelLayoutOverviewClusters",
        "drillRootCourse",
    ):
        assert token in app, f"缺少课程 H/A 分流/层级实现：{token}"
    src = (APP / "js/graph-multilevel/renderer-adapter.js").read_text(encoding="utf-8")
    assert "topN: 5" in src and "maxLabels: 14" in src
    assert "groupLabelCount" in src and "_groupLabelBoxes" in src
    assert "truncateTextWidth" in src
