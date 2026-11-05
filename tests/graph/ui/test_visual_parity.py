"""task-367 / S3-ADDENDUM-3 视觉回归：离线机检（pytest 包装 Node 套件 + 静态常量）。"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "src/memoria/ui/static/app"
RENDERER = APP / "js/graph-multilevel/renderer-adapter.js"
MOUNT = APP / "js/graph-multilevel/mount.js"
APP_JS = APP / "js/app.js"
CSS = APP / "css/app.css"
NODE_TEST = Path(__file__).resolve().parent / "renderer_visual.test.js"
ADDENDUM = ROOT / "docs/design/multilevel-graph/S3-ADDENDUM-3.md"


def test_visual_node_suite() -> None:
    proc = subprocess.run(
        ["node", str(NODE_TEST)],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    assert proc.returncode == 0, f"visual 套件失败：\n{proc.stdout[-3000:]}\n{proc.stderr[-3000:]}"
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["suite"] == "renderer_visual"
    assert payload["failed"] == 0
    names = {r["name"] for r in payload["results"]}
    for required in (
        "old_kgviz_visual_constants",
        "continuous_degree_radius_range_and_monotonic",
        "hover_target_radius_bonus",
        "galaxy_gradient_endpoints",
        "renderer_applies_degree_colors_labels_and_edges",
        "hover_and_target_fill_colors",
    ):
        assert required in names, f"缺视觉用例：{required}"


def test_renderer_visual_constants_match_addendum() -> None:
    src = RENDERER.read_text(encoding="utf-8")
    for token in (
        'bg: "#0a0d13"', 'node: "#c9d1d9"', 'nodeHover: "#f0f6fc"',
        'nodeTarget: "#79c0ff"', 'nodeDim: "#3d4350"', 'nodeInvalid: "#3a4152"',
        'label: "#adbac7"', 'labelInvalid: "#6e7681"',
        '"10px system-ui, sans-serif"', "rgba(13,17,23,0.92)",
        "KP_BASE_RADIUS = 6", "SIZE_RATIO_MIN = 0.75", "SIZE_RATIO_MAX = 1.65",
        "HOVER_EXTRA_RADIUS = 3", "TARGET_EXTRA_RADIUS = 2",
        'contain: "#3fb950"', 'reference: "#58a6ff"', 'extend: "#d29922"', 'semantic: "#e06c75"',
        "drawStar(", "radiusForDegree(", "setPresentation(",
    ):
        assert token in src, f"Renderer 缺视觉常量/函数：{token}"
    # 不得回退固定 8px
    assert "KP_RADIUS = 8" not in src
    assert "return KP_RADIUS" not in src


def test_presentation_wiring_not_in_vm() -> None:
    """degree 只能经 Presentation 元数据进 Renderer；VM 白名单无 degree。"""
    app = APP_JS.read_text(encoding="utf-8")
    mount = MOUNT.read_text(encoding="utf-8")
    assert "presentation: state.graphMultilevel.presentation" in app
    assert "setPresentation?.(state.graphMultilevel.presentation)" in app
    assert "setPresentation(" in mount
    renderer = RENDERER.read_text(encoding="utf-8")
    assert "degrees" in renderer
    assert '.get("data_edge_ids")' not in renderer
    assert "['data_edge_ids']" not in renderer
    # 旧 KGviz/3D 文件未被本任务修改（只在写域内动新 renderer/mount/app/CSS/tests）
    for p in (APP / "js/graph-view-2d.js", APP / "js/graph-view-3d.js", APP / "js/graph-theme.js"):
        assert p.is_file()


def test_chrome_downgraded_to_hint_bar_style() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert "background: #161b22" in css
    assert "background: #0a0d13" in css
    assert "font: 10px system-ui, sans-serif" in css
    assert "rgba(13, 17, 23, 0.55)" in css
    # 不再是大卡片（旧 toolbar/legend 的 8px 圆角 + surface 卡片被替换）
    assert "border-radius: 8px" not in css[css.find(".-graph-multilevel-host"):]
    assert ".graph-multilevel-toolbar" in css and ".graph-multilevel-legend" in css
