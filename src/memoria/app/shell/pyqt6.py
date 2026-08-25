"""PyQt6 桌面壳（Package 发布；Win32 hidden chrome）。"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from pathlib import Path

from memoria import __version__
from memoria.app.shell.pyqt6_hidden_chrome import (
    create_main_window,
    finalize_frameless_chrome,
    install_titlebar_drag_handles,
    register_web_view_hwnd,
    schedule_first_paint_refresh,
)
from memoria.app.shell.pyqt6_host import PyQt6Host
from memoria.app.shell.static_server_thread import StaticServerThread
from memoria.presentation.api.ui import UIAPI
from memoria.storage.ui_settings import resolve_last_kb_path
from memoria.presentation.paths import UI_APP_INDEX


def _startup_kb_path() -> str | None:
    return resolve_last_kb_path()


def _configure_qtwebengine_env() -> None:
    """须在 import PyQt6.QtWebEngine* 之前调用。"""
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    # WebGL（3D 知识图谱）必需；不用 --disable-gpu-driver-bug-workarounds：
    # 它在有 bug 的驱动上强制 GPU 加速合成路径，易致 WebEngine 首帧合成挂起
    # （发布态首次打开点击无响应，最小化还原才恢复）。
    extras = "--enable-webgl --ignore-gpu-blocklist"
    # 修复 Qt WebEngine 在 Win11 上"画面冻结但 JS 正常、最小化/还原才恢复"：
    # CalculateNativeWinOcclusion 会把被误判为遮挡的窗口当作后台页，暂停渲染
    # 且不自动恢复（窗口移动/遮挡状态变化后最易触发，与 diag3-5 日志完全吻合）；
    # --disable-backgrounding-occluded-windows 一并禁止被遮挡页面的后台化降级。
    extras += " --disable-features=CalculateNativeWinOcclusion"
    extras += " --disable-backgrounding-occluded-windows"
    if os.environ.get("MEMORIA_SOFTWARE_COMPOSITING", "0").lower() in (
        "1",
        "true",
        "yes",
    ):
        # 软件合成兜底：GPU 合成器故障的机器保证可用（3D 图性能会下降）
        extras += " --disable-gpu-compositing --disable-gpu-rasterization"
    if extras not in flags:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{flags} {extras}".strip()
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        qt6 = Path(sys._MEIPASS) / "PyQt6" / "Qt6"
        for sub in ("bin", "libexec"):
            process = qt6 / sub / "QtWebEngineProcess.exe"
            if process.is_file():
                os.environ.setdefault("QTWEBENGINEPROCESS_PATH", str(process))
                break


def _frameless_enabled() -> bool:
    return os.environ.get("MEMORIA_FRAMELESS", "1").lower() not in ("0", "false", "no")


# 前端探针：页面加载后注入，维护 window.__m0diag 事件计数与焦点/可见性状态，
# 由 Python 侧 runJavaScript 主动查询（PyQt6 无 console 信号，故不走 console.log）。
# 并承担合成器冻结自愈检测：requestAnimationFrame 由合成器驱动，冻结时回调停止；
# 可见状态下 rAF 停滞 >1.2s 判定合成冻结，通过 document.title 通知 Qt（titleChanged
# 信号）触发整窗 HWND 翻转自愈（等效最小化→还原的合成器重置）。
_DIAG_PROBE_JS = r"""
(function () {
  if (window.__m0diagReady) { return; }
  window.__m0diagReady = true;
  window.__m0diag = {
    down: 0, up: 0, focus: 0, blur: 0, focusNow: document.hasFocus(),
    vis: document.visibilityState, ready: document.readyState,
    bridge: !!window.MemoriaBridge, last: ''
  };
  document.addEventListener('pointerdown', function (e) {
    var d = window.__m0diag; d.down++; d.last = 'tag=' + (e.target && e.target.tagName) +
      ' x=' + Math.round(e.clientX) + ' y=' + Math.round(e.clientY) + ' focus=' + document.hasFocus();
  }, true);
  document.addEventListener('pointerup', function () { window.__m0diag.up++; }, true);
  window.addEventListener('focus', function () { var d = window.__m0diag; d.focus++; d.focusNow = true; }, true);
  window.addEventListener('blur', function () { var d = window.__m0diag; d.blur++; d.focusNow = false; }, true);
  document.addEventListener('visibilitychange', function () {
    window.__m0diag.vis = document.visibilityState;
  }, true);
  // 合成冻结自愈：rAF 由合成器驱动，冻结时回调停止；可见且停滞>1.2s 判冻结
  (function () {
    var last = Date.now();
    window.__m0rafTick = function () { last = Date.now(); requestAnimationFrame(window.__m0rafTick); };
    requestAnimationFrame(window.__m0rafTick);
    setInterval(function () {
      if (document.visibilityState !== 'visible') { return; }
      var now = Date.now();
      if (now - last > 1200 && document.title.indexOf('__m0frozen__') !== 0) {
        var t0 = document.title;
        document.title = '__m0frozen__' + now;
        setTimeout(function () { document.title = t0; }, 600);
      }
    }, 400);
  })();
})();
"""


def _require_pyqt6():
    try:
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QIcon
        from PyQt6.QtWebChannel import QWebChannel
        from PyQt6.QtWebEngineCore import (
            QWebEnginePage,
            QWebEngineProfile,
            QWebEngineSettings,
        )
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWidgets import QApplication
    except ImportError as e:
        raise SystemExit(
            "PyQt6 壳需要安装 desktop 依赖：pip install memoria[desktop]\n"
            f"原始错误: {e}"
        ) from e
    return (
        QApplication,
        QIcon,
        QUrl,
        QWebChannel,
        QWebEnginePage,
        QWebEngineProfile,
        QWebEngineSettings,
        QWebEngineView,
    )


def run() -> None:
    if not UI_APP_INDEX.is_file():
        raise FileNotFoundError(f"UI 入口不存在: {UI_APP_INDEX}")

    _configure_qtwebengine_env()
    from memoria.app.shell.app_icon import (
        apply_app_window_icons,
        configure_process_app_identity,
        reapply_app_window_icons,
        resolve_app_icon_path,
    )

    configure_process_app_identity()
    (
        QApplication,
        QIcon,
        QUrl,
        QWebChannel,
        QWebEnginePage,
        QWebEngineProfile,
        QWebEngineSettings,
        QWebEngineView,
    ) = _require_pyqt6()
    from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
    from memoria.app.shell.api_rpc import UIAPIRpc
    from memoria.app.shell.shell_log import shell_log, shell_log_banner, shell_log_enabled

    class _DiagEventFilter(QObject):
        """发布态诊断：记录 Qt 层鼠标点击 / 窗口激活 / 焦点事件（仅 shell 日志启用时输出）。"""

        def __init__(self, parent: QObject | None = None) -> None:
            super().__init__(parent)
            self._enabled = shell_log_enabled()

        def eventFilter(self, watched, event) -> bool:  # noqa: ANN001
            if not self._enabled:
                return False
            try:
                t = event.type()
                if t == QEvent.Type.MouseButtonPress:
                    pos = getattr(event, "position", None)
                    shell_log(
                        "diag_mouse_press",
                        target=type(watched).__name__,
                        x=round(pos.x()) if pos is not None else None,
                        y=round(pos.y()) if pos is not None else None,
                    )
                    # 点击到达 Qt 层后，立即查询前端探针计数：
                    # 若 __m0diag.down 未增长，说明点击未到达页面 DOM（事件路由/合成问题）
                    try:
                        view.page().runJavaScript(
                            "JSON.stringify(window.__m0diag || null)",
                            lambda r: shell_log("frontend_probe", state=str(r)),
                        )
                    except Exception:  # noqa: BLE001
                        pass
                elif t == QEvent.Type.WindowActivate:
                    shell_log("diag_window_activate", target=type(watched).__name__)
                elif t == QEvent.Type.WindowDeactivate:
                    shell_log("diag_window_deactivate", target=type(watched).__name__)
                elif t == QEvent.Type.ActivationChange:
                    shell_log("diag_activation_change", target=type(watched).__name__)
                elif t == QEvent.Type.FocusIn:
                    shell_log("diag_focus_in", target=type(watched).__name__)
                elif t == QEvent.Type.FocusOut:
                    shell_log("diag_focus_out", target=type(watched).__name__)
                elif t == QEvent.Type.Resize:
                    size = getattr(event, "size", None)
                    shell_log(
                        "diag_resize",
                        target=type(watched).__name__,
                        w=size.width() if size is not None else None,
                        h=size.height() if size is not None else None,
                    )
            except Exception:  # noqa: BLE001
                pass
            return False

    shell_log_banner()

    frameless = _frameless_enabled()
    app = QApplication(sys.argv)
    app.setApplicationName("Memoria")

    icon_path = resolve_app_icon_path()
    app_icon = QIcon(str(icon_path)) if icon_path is not None else None

    server = StaticServerThread()
    url = server.start()

    window = create_main_window(frameless=frameless)
    window.setWindowTitle(f"Memoria v{__version__}")
    if app_icon is not None and icon_path is not None:
        apply_app_window_icons(app, window, icon_path, app_icon)
    window.resize(1280, 860)
    window.setMinimumSize(900, 600)

    host = PyQt6Host(window, frameless=frameless)
    startup_kb = _startup_kb_path()
    api = UIAPI(host=host, kb_path=startup_kb)

    profile = QWebEngineProfile.defaultProfile()
    settings = profile.settings()
    settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
    settings.setAttribute(
        QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True
    )
    settings.setAttribute(
        QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
    )
    settings.setAttribute(
        QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
    )

    page = QWebEnginePage(profile)
    view = QWebEngineView()
    view.setPage(page)
    # 禁用 Qt 默认右键菜单（B08），让前端 contextmenu 事件自行处理
    from PyQt6.QtCore import Qt

    view.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
    from PyQt6.QtWidgets import QSizePolicy

    view.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
    )
    window.setStyleSheet("QMainWindow { background-color: #1e1e1e; }")
    view.setStyleSheet("background-color: #1e1e1e;")
    window.setCentralWidget(view)

    channel = QWebChannel()
    page.setWebChannel(channel)
    rpc = UIAPIRpc(api)
    rpc.setParent(window)
    channel.registerObject("bridge", rpc)
    window._memoria_api_rpc = rpc  # 防止 Python GC 回收 bridge

    # ── 发布态诊断（MEMORIA_SHELL_LOG=1 时输出）──
    # Qt 层事件过滤：点击/激活/焦点/尺寸
    diag_filter = _DiagEventFilter(app)
    app.installEventFilter(diag_filter)
    window._memoria_diag_filter = diag_filter  # noqa: SLF001 防止 GC
    # 注：PyQt6 的 QWebEnginePage 无 javaScriptConsoleMessage 信号（仅静态方法），
    # 前端探针状态改经 window.__m0diag + runJavaScript 主动查询（见事件过滤与首帧刷新）。
    page.loadStarted.connect(lambda: shell_log("load_started"))
    page.renderProcessTerminated.connect(
        lambda status, code: shell_log(
            "render_terminated", status=int(status), code=int(code)
        )
    )

    view.load(QUrl(url))

    def _flip_hwnd_recomposite() -> None:
        """整窗 HWND 隐藏→显示，强制 DWM 重建窗口表面并让 Chromium 重新合成。

        诊断日志（diag2）证实：widget 级 view.setVisible 翻转已执行（前端收到
        blur/focus），但用户仍需手动最小化→还原——widget 可见性不重建窗口表面；
        最小化→还原的本质是 HWND 从桌面移除再回归，DWM 必须重建表面并重新开始
        合成提交。故在页面加载完成后对顶层 HWND 做一次 SW_HIDE→SW_SHOW。
        """
        try:
            hwnd = int(window.winId())
            user32 = ctypes.windll.user32
            shell_log("hwnd_flip_hide", hwnd=hwnd)
            user32.ShowWindow(hwnd, 0)  # SW_HIDE

            def _show() -> None:
                user32.ShowWindow(hwnd, 5)  # SW_SHOW
                user32.SetForegroundWindow(hwnd)
                shell_log("hwnd_flip_show", hwnd=hwnd)
                schedule_first_paint_refresh(window)

            QTimer.singleShot(60, _show)
        except Exception:  # noqa: BLE001
            pass

    def _on_page_loaded(ok: bool) -> None:
        shell_log("page_loaded", ok=ok)
        if ok:
            view.page().runJavaScript(
                "window.MemoriaWindowChrome?.syncToolbarDragExclusion?.()"
            )
            # 注入前端交互/焦点探针
            view.page().runJavaScript(_DIAG_PROBE_JS)
            # 首帧合成器重置（见 _flip_hwnd_recomposite 注释：需重建整窗 DWM 表面）
            QTimer.singleShot(150, _flip_hwnd_recomposite)
        # 页面就绪后补一轮首帧刷新（重置 show 后那轮尚未完成的多拍链）
        schedule_first_paint_refresh(window)

    # 合成冻结自愈（前端探针经 document.title 上报 __m0frozen__）
    _last_heal = [0.0]  # time.monotonic 时间戳（防抖）

    def _heal_synthesis() -> None:
        now = time.monotonic()
        if now - _last_heal[0] < 5.0:
            shell_log("synthesis_heal_skipped", reason="cooldown")
            return
        _last_heal[0] = now
        shell_log("synthesis_heal_start")
        _flip_hwnd_recomposite()

    def _on_page_title_changed(title: str) -> None:
        t = str(title)
        if t.startswith("__m0frozen__"):
            shell_log("synthesis_frozen_detected", title=t[:80])
            _heal_synthesis()

    page.loadFinished.connect(_on_page_loaded)
    page.titleChanged.connect(_on_page_title_changed)
    window.show()
    window.raise_()
    window.activateWindow()
    # 首帧合成强化：show 后立即多拍强制重绘（不等 loadFinished，兜底加载失败场景）
    schedule_first_paint_refresh(window)

    if frameless:
        install_titlebar_drag_handles(window)
        QTimer.singleShot(0, lambda: finalize_frameless_chrome(window, app))
        QTimer.singleShot(50, lambda: register_web_view_hwnd(window))
        if icon_path is not None:
            QTimer.singleShot(0, lambda: reapply_app_window_icons(app, window))
            QTimer.singleShot(150, lambda: reapply_app_window_icons(app, window))

    sys.exit(app.exec())


def main() -> None:
    run()


if __name__ == "__main__":
    main()
