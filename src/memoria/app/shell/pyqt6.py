"""PyQt6 桌面壳（Package 发布；Win32 hidden chrome）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from memoria.app.shell.pyqt6_hidden_chrome import (
    create_main_window,
    finalize_frameless_chrome,
    install_titlebar_drag_handles,
    register_web_view_hwnd,
)
from memoria.app.shell.pyqt6_host import PyQt6Host
from memoria.app.shell.static_server_thread import StaticServerThread
from memoria.presentation.api.m0 import M0API
from memoria.storage.ui_settings import resolve_last_kb_path
from memoria.presentation.paths import UI_M0_INDEX


def _startup_kb_path() -> str | None:
    return resolve_last_kb_path()


def _configure_qtwebengine_env() -> None:
    """须在 import PyQt6.QtWebEngine* 之前调用。"""
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    extras = "--enable-webgl --ignore-gpu-blocklist --disable-gpu-driver-bug-workarounds"
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
    if not UI_M0_INDEX.is_file():
        raise FileNotFoundError(f"UI 入口不存在: {UI_M0_INDEX}")

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
    from PyQt6.QtCore import QTimer
    from memoria.app.shell.api_rpc import M0APIRpc
    from memoria.app.shell.shell_log import shell_log_banner

    shell_log_banner()

    frameless = _frameless_enabled()
    app = QApplication(sys.argv)
    app.setApplicationName("Memoria")

    icon_path = resolve_app_icon_path()
    app_icon = QIcon(str(icon_path)) if icon_path is not None else None

    server = StaticServerThread()
    url = server.start()

    window = create_main_window(frameless=frameless)
    window.setWindowTitle("Memoria M1")
    if app_icon is not None and icon_path is not None:
        apply_app_window_icons(app, window, icon_path, app_icon)
    window.resize(1280, 860)
    window.setMinimumSize(900, 600)

    host = PyQt6Host(window, frameless=frameless)
    startup_kb = _startup_kb_path()
    api = M0API(host=host, kb_path=startup_kb)

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
    rpc = M0APIRpc(api)
    rpc.setParent(window)
    channel.registerObject("bridge", rpc)
    window._memoria_api_rpc = rpc  # 防止 Python GC 回收 bridge

    view.load(QUrl(url))

    def _on_page_loaded(ok: bool) -> None:
        if ok:
            view.page().runJavaScript(
                "window.MemoriaWindowChrome?.syncToolbarDragExclusion?.()"
            )

    page.loadFinished.connect(_on_page_loaded)
    window.show()

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
