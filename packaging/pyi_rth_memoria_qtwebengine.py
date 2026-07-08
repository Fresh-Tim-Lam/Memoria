"""PyInstaller runtime hook：Qt WebEngine 在 frozen 包内可启动渲染/GPU 进程。"""

from __future__ import annotations

import os
import sys


def _configure_windows_app_identity() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Memoria.Desktop.1"
        )
    except Exception:
        pass


def _configure_qtwebengine() -> None:
    if not getattr(sys, "frozen", False) or not hasattr(sys, "_MEIPASS"):
        return
    meipass = sys._MEIPASS
    candidates = [
        os.path.join(meipass, "lib", "PyQt6", "Qt6", "bin", "QtWebEngineProcess.exe"),
        os.path.join(meipass, "PyQt6", "Qt6", "bin", "QtWebEngineProcess.exe"),
        os.path.join(meipass, "PyQt6", "Qt6", "libexec", "QtWebEngineProcess.exe"),
    ]
    for process in candidates:
        if os.path.isfile(process):
            os.environ.setdefault("QTWEBENGINEPROCESS_PATH", process)
            break
    os.environ.setdefault(
        "QTWEBENGINE_CHROMIUM_FLAGS",
        "--enable-webgl --ignore-gpu-blocklist --disable-gpu-driver-bug-workarounds",
    )


_configure_windows_app_identity()
_configure_qtwebengine()
