"""PyInstaller runtime hook：frozen 包内应用身份设置（任务栏分组/图标）。"""

from __future__ import annotations

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


_configure_windows_app_identity()
