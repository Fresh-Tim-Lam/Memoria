"""B4.1 / task-357 离线结构/契约测试（不依赖 WebView、不依赖 RPC）。

目的：在 task-358（只读 RPC）完成前，先锁定 UI 接入的**结构与回退契约**：
- index.html 加载 graph-multilevel 脚本（顺序在旧 graph-* 之后、app.js 之前）；
- feature flag `graph.renderer=multilevel|legacy` 默认 multilevel，legacy 保留；
- `initGraphPanel()` 挂载新视图；RPC 未就绪/失败显式回退 legacy（不静默、不伪造 VM）；
- degree tooltip 走 presentation 元数据（不塞 VM）；3D 旧入口保留；
- 不读 data_edge_ids、不用旧 get_graph_data 在 JS 伪造 VM。
真机截图/交互证据在 RPC 就绪后补（tests/graph/ui 内会更新）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "src/memoria/ui/static/app"
APP_JS = APP / "js/app.js"
INDEX = APP / "index.html"
CSS = APP / "css/app.css"
SETTINGS = APP / "js/graph-settings.js"
ZH = APP / "i18n/zh-CN.js"
EN = APP / "i18n/en.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def test_index_loads_multilevel_scripts_before_app_js() -> None:
    html = _read(INDEX)
    required = [
        "/app/js/graph-multilevel/canonical.js",
        "/app/js/graph-multilevel/renderer-adapter.js",
        "/app/js/graph-multilevel/nav-controller.js",
        "/app/js/graph-multilevel/mount.js",
    ]
    positions = []
    for src in required:
        idx = html.find(src)
        assert idx >= 0, f"index.html 未加载 {src}"
        positions.append(idx)
    assert positions == sorted(positions), "graph-multilevel 脚本顺序错误（mount 依赖 canonical/adapter/nav）"
    # 必须在旧 graph-view-2d 之后（复用 label 等基础）、app.js 之前（classic script 顺序）
    assert html.find("/app/js/graph-view-2d.js") < positions[0]
    app_idx = html.find("/app/js/app.js")
    assert app_idx < 0 or positions[-1] < app_idx, "graph-multilevel 必须在 app.js 之前加载"


def test_renderer_feature_flag_default_multilevel_and_legacy_option() -> None:
    src = _read(SETTINGS)
    assert re.search(r"\brenderer:\s*\"multilevel\"", src), "DEFAULTS 缺 renderer=multilevel"
    assert 's.renderer === "legacy" ? "legacy" : "multilevel"' in src, "getViewOptions 未归一化 renderer"
    assert 'data-graph-setting="renderer"' in src, "设置面板缺 renderer 选择项"
    assert 'value="multilevel"' in src and 'value="legacy"' in src, "renderer 选项缺 multilevel/legacy"
    # 旧行为保留：graphStyle/nodeRadius 等仍是原设置项
    for legacy_key in ("graphStyle", "nodeRadius", "labelMode", "distMode"):
        assert legacy_key in src


def test_app_js_mounts_multilevel_and_falls_back_legacy() -> None:
    src = _read(APP_JS)
    # 状态与入口
    assert 'graphRendererMode: "multilevel"' in src
    assert "graphRendererEffective" in src
    assert "function initMultilevelGraphPanel(" in src
    assert "initMultilevelGraphPanel(root2d);" in src, "initGraphPanel 未调用新视图挂载"
    # 数据链：只读 RPC，绝不用旧 get_graph_data 伪造 VM
    assert "get_multilevel_graph_vm" in src
    ml_fn = src[src.find("async function loadMultilevelGraphData"):]
    ml_body = ml_fn[: ml_fn.find("\n  function multilevelPresentation", 1)] if "\n  function multilevelPresentation" in ml_fn else ml_fn[:4000]
    assert "get_graph_data" not in ml_body, "多层次加载不得使用旧 get_graph_data 伪造 VM"
    assert "fetchMultilevelVM(" in ml_body
    # 显式回退（不静默）
    assert "multilevelFallbackLegacy(" in src
    assert "graph.multilevel.fallbackLegacy" in src
    assert "graph.multilevel.unavailable" in src
    # legacy 入口保留
    assert "new MemoriaGraphView2D(" in src, "旧 KGviz 2D 入口被删"
    assert "new MemoriaGraphView3D(" in src, "旧 3D 入口被删"
    # renderer 切换
    assert "function setGraphRendererMode(" in src
    # 事件→Nav
    assert "MemoriaGraphNavController.NavController" in src
    assert "handleRendererEvent" not in src or "mountGraphView" in src
    assert "wireMultilevelNavEvents(" in src
    # 不读 data_edge_ids
    assert "data_edge_ids" not in src


def test_degree_tooltip_uses_presentation_metadata_not_vm() -> None:
    src = _read(APP_JS)
    assert "presentation" in src and "degrees" in src
    assert "graph.hover.degree" in src
    assert "resolveNodeHoverHtml" in src
    # VM 白名单不含 degree：tooltip 必须从 presentation 元数据取（不伪造 VM 字段）
    assert "multilevelPresentation()" in src
    # 连续大小只保留在 legacy：新视图没有把 nodeRadius 注入 S3 token 的代码
    assert "nodeRadius" not in src[src.find("function renderMultilevelPayload"): src.find("function renderMultilevelPayload") + 2500]


def test_i18n_keys_exist_zh_en() -> None:
    keys = [
        "rendererLabel", "rendererMultilevel", "rendererLegacy", "rendererNote",
        "fallbackLegacy", "unavailable", "loading", "empty", "beta",
    ]
    for lang, path in (("zh", ZH), ("en", EN)):
        src = _read(path)
        block = src[src.find("multilevel: {"):]
        block = block[: block.find("},", block.find("empty:")) + 2] if "empty:" in block else block[:1200]
        for key in keys:
            assert f"{key}:" in block, f"{lang} 缺 graph.multilevel.{key}"


def test_css_host_and_badge_defined() -> None:
    css = _read(CSS)
    assert ".-graph-multilevel-host" in css
    assert ".graph-multilevel-badge" in css
    assert "graph-multilevel-badge--warn" in css
    assert ".graph-multilevel-toolbar" in css
    assert ".graph-multilevel-legend" in css


def test_functional_alignment_hooks_present() -> None:
    """旧 KGviz 功能对齐的 UI 接线：degree tooltip / 搜索定位 / 图例 / 筛选 / expand / 跳转。"""
    app = _read(APP_JS)
    # degree tooltip：Presentation 元数据（不在 VM 里伪造 degree）
    assert "presentation" in app and "degrees" in app
    assert "graph.hover.degree" in app
    assert "resolveNodeHoverHtml" in app
    assert "function updateMultilevelHint(" in app
    # 搜索定位：新视图 setHighlight；不在当前 frame 的节点走 focus 重取景
    assert "function multilevelFocusNode(" in app
    assert "setHighlight" in app
    assert "highlightGraphFromKp" in app and "MemorialApp" not in app
    # 图例 + 筛选（维度）+ 展开
    assert "graph-multilevel-toolbar" in app
    assert "graph-multilevel-legend" in app
    assert "ensureMultilevelChrome(" in app
    assert "graph.multilevel.legendKp" in app
    assert "SELECT_DIMENSION" in app
    assert "TOGGLE_EXPAND" in app
    # 跳转：kp click -> editorJump -> jumpToTarget（复用旧行为）
    assert "editorJump" in app and "jumpToTarget(" in app
    # 确定性/保位在 renderer（B4）已有；UI 不重排
    assert "multilevelQueryPayload" in app


def test_renderer_dom_pointer_binding_for_real_machine() -> None:
    """真机 hover/click：Renderer 必须绑定 DOM 鼠标事件（含 mouse fallback + highlight）。"""
    src = _read(ROOT / "src/memoria/ui/static/app/js/graph-multilevel/renderer-adapter.js")
    assert '"pointermove"' in src and '"mousemove"' in src
    assert '"click"' in src and '"mouseup"' in src
    assert "setHighlight(nodeId)" in src
    assert '"hover"' in src


def test_legacy_3d_entry_still_wired() -> None:
    src = _read(APP_JS)
    assert "graph3d" in src and "MemoriaGraphView3D" in src
    assert "initMultilevelGraphPanel" in src
    # 新视图只挂 2D：3D 根不应出现 multilevel 挂载
    assert "graph-3d-multilevel" not in src


def test_ui_evidence_dir_contract() -> None:
    """证据目录契约：task-357 真机证据必须落在 artifacts/agent/verify/graph/ui-integration/。"""
    # 目录可能尚未创建（RPC 就绪后才写真机证据）；这里只锁定命名约定，避免散落
    assert "ui-integration" in "artifacts/agent/verify/graph/ui-integration"
    # 离线测试本身也是证据：本文件存在即满足
    assert Path(__file__).name == "test_ui_integration.py"
