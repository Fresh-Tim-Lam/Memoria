"""Windows 无边框窗口：工作区最大化（不遮挡任务栏）。"""

from __future__ import annotations

import ctypes
from ctypes import wintypes


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def _hwnd(window) -> int | None:
    native = getattr(window, "native", None)
    if native is None:
        return None
    handle = getattr(native, "Handle", None)
    if handle is None:
        return None
    return int(handle.ToInt32())


def read_bounds(window) -> tuple[int, int, int, int] | None:
    native = getattr(window, "native", None)
    if native is None:
        return None
    loc = native.Location
    size = native.Size
    return int(loc.X), int(loc.Y), int(size.Width), int(size.Height)


def apply_bounds(window, x: int, y: int, w: int, h: int) -> bool:
    hwnd = _hwnd(window)
    if hwnd is None:
        return False
    ctypes.windll.user32.SetWindowPos(hwnd, None, x, y, w, h, 0x0040)
    return True


def maximize_to_work_area(window) -> bool:
    hwnd = _hwnd(window)
    if hwnd is None:
        return False
    user32 = ctypes.windll.user32
    monitor = user32.MonitorFromWindow(hwnd, 2)
    mi = _MONITORINFO()
    mi.cbSize = ctypes.sizeof(_MONITORINFO)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
        return False
    work = mi.rcWork
    w = work.right - work.left
    h = work.bottom - work.top
    user32.SetWindowPos(hwnd, None, work.left, work.top, w, h, 0x0040)
    return True
