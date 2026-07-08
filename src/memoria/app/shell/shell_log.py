"""PyQt6 壳诊断日志（MEMORIA_SHELL_LOG=1 启用）。"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_ENABLED: bool | None = None
_LOG_PATH: Path | None = None


def shell_log_enabled() -> bool:
    global _ENABLED  # noqa: PLW0603
    if _ENABLED is None:
        _ENABLED = os.environ.get("MEMORIA_SHELL_LOG", "0").lower() not in (
            "0",
            "false",
            "no",
            "",
        )
    return _ENABLED


def _log_path() -> Path | None:
    global _LOG_PATH  # noqa: PLW0603
    if _LOG_PATH is not None:
        return _LOG_PATH
    raw = os.environ.get("MEMORIA_SHELL_LOG_FILE", "").strip()
    if not raw:
        _LOG_PATH = None
        return None
    _LOG_PATH = Path(raw).expanduser()
    return _LOG_PATH


def _fmt_kwargs(fields: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in fields.items():
        if value is None:
            continue
        text = repr(value)
        if len(text) > 160:
            text = text[:157] + "..."
        parts.append(f"{key}={text}")
    return " ".join(parts)


def shell_log(event: str, **fields: Any) -> None:
    if not shell_log_enabled():
        return
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    extra = _fmt_kwargs(fields)
    line = f"[memoria.shell] {ts} {event}"
    if extra:
        line = f"{line} {extra}"
    print(line, file=sys.stderr, flush=True)
    path = _log_path()
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def shell_log_banner() -> None:
    if not shell_log_enabled():
        return
    shell_log(
        "log_enabled",
        shell=os.environ.get("MEMORIA_SHELL", "pywebview"),
        frameless=os.environ.get("MEMORIA_FRAMELESS", "1"),
        log_file=str(_log_path()) if _log_path() else None,
        platform=sys.platform,
    )


def format_qt_window_state(state: Any) -> str:
    """PyQt6 WindowState 不可直接 int()，转成可读标签。"""
    try:
        from PyQt6.QtCore import Qt

        parts: list[str] = []
        if state & Qt.WindowState.WindowMinimized:
            parts.append("min")
        if state & Qt.WindowState.WindowMaximized:
            parts.append("max")
        if state & Qt.WindowState.WindowFullScreen:
            parts.append("full")
        return "|".join(parts) if parts else "normal"
    except Exception:  # noqa: BLE001
        return repr(state)


def shell_log_window(window: Any, event: str, **fields: Any) -> None:
    """附带窗口/视图/拖拽条快照。"""
    if not shell_log_enabled():
        return
    snap: dict[str, Any] = dict(fields)
    try:
        geo = window.geometry()
        snap["geo"] = (geo.x(), geo.y(), geo.width(), geo.height())
        snap["win"] = (window.width(), window.height())
        snap["qt_max"] = window.isMaximized()
        snap["qt_min"] = window.isMinimized()
    except Exception as exc:  # noqa: BLE001
        snap["win_err"] = str(exc)
    view = window.centralWidget()
    if view is not None:
        try:
            snap["view"] = (view.width(), view.height(), view.isVisible())
        except Exception as exc:  # noqa: BLE001
            snap["view_err"] = str(exc)
    left = getattr(window, "_drag_handle_left", None)
    spacer = getattr(window, "_drag_handle_spacer", None)
    if left is not None:
        g = left.geometry()
        snap["drag_left"] = (left.isVisible(), g.x(), g.y(), g.width(), g.height())
    if spacer is not None:
        g = spacer.geometry()
        snap["drag_spacer"] = (spacer.isVisible(), g.x(), g.y(), g.width(), g.height())
    if sys.platform == "win32":
        try:
            handle = window.windowHandle()
            hwnd = int(handle.winId()) if handle is not None else int(window.winId())
            if hwnd:
                import ctypes

                user32 = ctypes.windll.user32
                snap["hwnd"] = hwnd
                snap["is_zoomed"] = bool(user32.IsZoomed(hwnd))
                snap["is_iconic"] = bool(user32.IsIconic(hwnd))
        except Exception as exc:  # noqa: BLE001
            snap["win32_err"] = str(exc)
    shell_log(event, **snap)
