"""应用图标：路径解析 + Windows 任务栏 / Alt+Tab 集成。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication, QMainWindow

APP_USER_MODEL_ID = "Memoria.Desktop.1"


def configure_process_app_identity() -> None:
    """须在 QApplication 创建之前调用（Windows 任务栏图标分组）。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID
        )
    except Exception:
        pass


def resolve_app_icon_path() -> Path | None:
    from memoria.app.runtime import install_root, repo_root, resources_dir
    from memoria.presentation.paths import UI_APP_ICON

    static_png = UI_APP_ICON.with_suffix(".png")
    for candidate in (
        resources_dir() / "icons" / "Memoria.ico",
        install_root() / "resources" / "icons" / "Memoria.ico",
        repo_root() / "resources" / "icons" / "Memoria.ico",
        UI_APP_ICON,
        resources_dir() / "icons" / "Memoria.png",
        static_png,
    ):
        if candidate.is_file():
            return candidate
    return None


def _native_icon_path(icon_path: Path) -> Path:
    if icon_path.suffix.lower() == ".ico":
        return icon_path
    sibling = icon_path.with_suffix(".ico")
    if sibling.is_file():
        return sibling
    return icon_path


def apply_native_window_icons(hwnd: int, icon_path: Path) -> None:
    """Win32 WM_SETICON：hidden chrome 下 Qt setWindowIcon 有时不生效。"""
    if sys.platform != "win32" or not hwnd:
        return

    import ctypes

    user32 = ctypes.windll.user32
    WM_SETICON = 0x0080
    ICON_SMALL = 0
    ICON_BIG = 1
    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x0010

    path = str(_native_icon_path(icon_path).resolve())
    for size, slot in ((16, ICON_SMALL), (32, ICON_BIG)):
        hicon = user32.LoadImageW(
            None,
            path,
            IMAGE_ICON,
            size,
            size,
            LR_LOADFROMFILE,
        )
        if hicon:
            user32.SendMessageW(hwnd, WM_SETICON, slot, hicon)


def apply_app_window_icons(
    app: QApplication,
    window: QMainWindow,
    icon_path: Path,
    icon: QIcon,
) -> None:
    app.setWindowIcon(icon)
    window.setWindowIcon(icon)
    window._memoria_app_icon_path = icon_path  # noqa: SLF001

    if sys.platform != "win32":
        return

    from memoria.app.shell.pyqt6_hidden_chrome import _resolve_hwnd

    hwnd = _resolve_hwnd(window)
    if hwnd:
        apply_native_window_icons(hwnd, icon_path)


def reapply_app_window_icons(app: QApplication, window: QMainWindow) -> None:
    icon_path = getattr(window, "_memoria_app_icon_path", None)
    if icon_path is None:
        icon_path = resolve_app_icon_path()
    if icon_path is None:
        return

    from PyQt6.QtGui import QIcon

    icon = QIcon(str(icon_path))
    if icon.isNull():
        return
    apply_app_window_icons(app, window, icon_path, icon)
