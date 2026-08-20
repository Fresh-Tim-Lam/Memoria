"""PyQt6 窗口壳：Win32 hidden chrome（DWM 动画）+ 非 Windows 回退 Frameless。"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from memoria.app.shell.shell_log import (
    format_qt_window_state,
    shell_log,
    shell_log_window,
)

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QApplication, QMainWindow

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    WM_NCCALCSIZE = 0x0083
    WM_NCHITTEST = 0x0084
    WM_SIZE = 0x0005
    WM_MOVE = 0x0003
    WM_WINDOWPOSCHANGED = 0x0047

    SIZE_RESTORED = 0
    SIZE_MINIMIZED = 1
    SIZE_MAXIMIZED = 2

    GA_ROOT = 2
    MONITOR_DEFAULTTONEAREST = 2

    SW_MAXIMIZE = 3
    SW_RESTORE = 9
    SW_SHOWNORMAL = 1
    SW_SHOWMAXIMIZED = 3

    WM_SYSCOMMAND = 0x0112
    SC_MOVE = 0xF010
    HTCAPTION = 2

    HTLEFT = 10
    HTRIGHT = 11
    HTTOP = 12
    HTTOPLEFT = 13
    HTTOPRIGHT = 14
    HTBOTTOM = 15
    HTBOTTOMLEFT = 16
    HTBOTTOMRIGHT = 17
    HTTRANSPARENT = -1

    SWP_FRAMECHANGED = 0x0020
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SWP_SHOWWINDOW = 0x0040

    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    DWMWA_WINDOW_CORNER_PREFERENCE = 33
    DWMWCP_DONOTROUND = 1
    DWMWCP_ROUND = 2

    WM_ENTERSIZEMOVE = 0x0231
    WM_EXITSIZEMOVE = 0x0232
    WM_SIZING = 0x0214

    BORDER = 8
    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi

    class _RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", _RECT),
            ("rcWork", _RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    class _NCCALCSIZE_PARAMS(ctypes.Structure):
        _fields_ = [
            ("rgrc", _RECT * 3),
            ("lppos", ctypes.c_void_p),
        ]

    class _WINDOWPOS(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("hwndInsertAfter", wintypes.HWND),
            ("x", ctypes.c_int),
            ("y", ctypes.c_int),
            ("cx", ctypes.c_int),
            ("cy", ctypes.c_int),
            ("flags", wintypes.UINT),
        ]

    class _WINDOWPLACEMENT(ctypes.Structure):
        _fields_ = [
            ("length", wintypes.UINT),
            ("flags", wintypes.UINT),
            ("showCmd", wintypes.UINT),
            ("ptMinPosition", wintypes.POINT),
            ("ptMaxPosition", wintypes.POINT),
            ("rcNormalPosition", _RECT),
        ]

    def _msg_address(message) -> int:  # type: ignore[no-untyped-def]
        if hasattr(message, "__int__"):
            return int(message.__int__())
        return int(message)

    def _monitor_work_rect(hwnd: int) -> _RECT | None:
        monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
            return mi.rcWork
        return None

    def _apply_nc_calc(params: _NCCALCSIZE_PARAMS, hwnd: int) -> None:
        """最大化时用显示器工作区，否则扩展客户区覆盖标题栏。"""
        if user32.IsZoomed(hwnd):
            work = _monitor_work_rect(hwnd)
            if work is not None:
                params.rgrc[0] = work
                return
        params.rgrc[0] = params.rgrc[1]

    def _apply_nc_calc_rect(rect: _RECT, hwnd: int) -> None:
        if user32.IsZoomed(hwnd):
            work = _monitor_work_rect(hwnd)
            if work is not None:
                rect.left = work.left
                rect.top = work.top
                rect.right = work.right
                rect.bottom = work.bottom
                return
        return


def _bounds_sane(
    window: QMainWindow, bounds: tuple[int, int, int, int]
) -> bool:
    """过滤动画中间帧/负坐标等不可信矩形，避免污染 saved bounds。"""
    _x, y, w, h = bounds
    min_w = max(window.minimumWidth(), 400)
    min_h = max(window.minimumHeight(), 200)
    if w < min_w or h < min_h:
        return False
    if y < -48:
        return False
    try:
        from PyQt6.QtGui import QGuiApplication

        screen = window.screen() or QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            if w > avail.width() + 48 or h > avail.height() + 48:
                return False
    except Exception:  # noqa: BLE001
        pass
    return True


def read_normal_bounds(window: QMainWindow) -> tuple[int, int, int, int] | None:
    """保存最大化前的窗口矩形（Qt geometry；不可信时回退已存 bounds）。"""
    if window.isMaximized():
        if sys.platform != "win32":
            geo = window.normalGeometry()
            bounds = geo.x(), geo.y(), geo.width(), geo.height()
            store_normal_bounds(window, bounds)
            return bounds
        hwnd = _resolve_hwnd(window)
        if not hwnd:
            return get_normal_bounds(window)
        wp = _WINDOWPLACEMENT()
        wp.length = ctypes.sizeof(_WINDOWPLACEMENT)
        if not user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
            return get_normal_bounds(window)
        r = wp.rcNormalPosition
        w = int(r.right - r.left)
        h = int(r.bottom - r.top)
        if w <= 0 or h <= 0:
            return get_normal_bounds(window)
        bounds = int(r.left), int(r.top), w, h
        if _bounds_sane(window, bounds):
            store_normal_bounds(window, bounds)
            return bounds
        return get_normal_bounds(window)

    geo = window.geometry()
    bounds = geo.x(), geo.y(), geo.width(), geo.height()
    if _bounds_sane(window, bounds):
        store_normal_bounds(window, bounds)
        return bounds
    return get_normal_bounds(window)


def set_restore_target(
    window: QMainWindow, bounds: tuple[int, int, int, int] | None
) -> None:
    """还原/任务栏恢复的唯一可信尺寸（最大化前或用户拖动后更新）。"""
    if not bounds or not _bounds_sane(window, bounds):
        return
    window._memoria_restore_target = bounds  # noqa: SLF001
    window._memoria_normal_bounds = bounds  # noqa: SLF001


def store_normal_bounds(
    window: QMainWindow, bounds: tuple[int, int, int, int] | None
) -> None:
    set_restore_target(window, bounds)


def get_normal_bounds(window: QMainWindow) -> tuple[int, int, int, int] | None:
    target = getattr(window, "_memoria_restore_target", None)
    if target:
        return target
    stored = getattr(window, "_memoria_normal_bounds", None)
    if stored:
        return stored
    if window.isMaximized() or window.isMinimized():
        if sys.platform != "win32":
            return None
        hwnd = _resolve_hwnd(window)
        if not hwnd:
            return None
        wp = _WINDOWPLACEMENT()
        wp.length = ctypes.sizeof(_WINDOWPLACEMENT)
        if not user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
            return None
        r = wp.rcNormalPosition
        w = int(r.right - r.left)
        h = int(r.bottom - r.top)
        if w <= 0 or h <= 0:
            return None
        return int(r.left), int(r.top), w, h
    geo = window.geometry()
    return geo.x(), geo.y(), geo.width(), geo.height()


def _restore_active(window: QMainWindow) -> bool:
    return bool(getattr(window, "_memoria_restore_active", False))


def _geometry_needs_fix(
    window: QMainWindow, bounds: tuple[int, int, int, int]
) -> bool:
    if window.isMaximized() or window.isMinimized():
        return False
    _x, _y, w, h = bounds
    cur_w, cur_h = window.width(), window.height()
    min_h = max(window.minimumHeight(), 200)
    min_w = max(window.minimumWidth(), 400)
    if cur_h < min_h or cur_w < min_w:
        return True
    tol = 24
    return abs(cur_w - w) > tol or abs(cur_h - h) > tol


def _collapsed_height(window: QMainWindow) -> bool:
    return window.height() < max(window.minimumHeight(), 200)


def _win32_set_normal_placement(
    hwnd: int, bounds: tuple[int, int, int, int]
) -> None:
    x, y, w, h = bounds
    wp = _WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(_WINDOWPLACEMENT)
    if not user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
        return
    wp.rcNormalPosition.left = x
    wp.rcNormalPosition.top = y
    wp.rcNormalPosition.right = x + w
    wp.rcNormalPosition.bottom = y + h
    wp.showCmd = SW_SHOWNORMAL
    user32.SetWindowPlacement(hwnd, ctypes.byref(wp))
    user32.ShowWindow(hwnd, SW_SHOWNORMAL)


def _win32_apply_bounds(
    window: QMainWindow, bounds: tuple[int, int, int, int]
) -> bool:
    from PyQt6.QtWidgets import QApplication

    x, y, w, h = bounds
    hwnd = _resolve_hwnd(window)
    if not hwnd:
        return False
    _win32_set_normal_placement(hwnd, bounds)
    user32.SetWindowPos(
        hwnd, None, x, y, w, h, SWP_SHOWWINDOW | SWP_FRAMECHANGED
    )
    _refresh_nonclient_frame(hwnd)
    QApplication.processEvents()
    return True


def apply_normal_bounds(
    window: QMainWindow, bounds: tuple[int, int, int, int]
) -> None:
    if not _bounds_sane(window, bounds):
        shell_log_window(window, "apply_normal_bounds_skipped", bounds=bounds)
        return
    from PyQt6.QtWidgets import QApplication

    x, y, w, h = bounds
    collapsed = _collapsed_height(window)
    window._memoria_restore_active = True  # noqa: SLF001
    try:
        if window.isMaximized():
            window.showNormal()
            QApplication.processEvents()
        if sys.platform == "win32":
            _win32_apply_bounds(window, bounds)
        # setGeometry 在 DWM 条带动画期间会与 hidden chrome 帧边距冲突
        if not collapsed and not _collapsed_height(window):
            geo = window.geometry()
            if abs(geo.width() - w) > 8 or abs(geo.height() - h) > 8:
                window.setGeometry(x, y, w, h)
                QApplication.processEvents()
        elif sys.platform == "win32":
            _win32_apply_bounds(window, bounds)
        layout_titlebar_drag_handles(window)
        shell_log_window(
            window,
            "apply_normal_bounds",
            bounds=bounds,
            target=get_normal_bounds(window),
            cur=(window.width(), window.height()),
            collapsed=collapsed,
        )
    finally:
        window._memoria_restore_active = False


def schedule_force_iconic_restore(
    window: QMainWindow, *, delay_ms: int = 200
) -> None:
    from PyQt6.QtCore import QTimer

    timer = getattr(window, "_memoria_iconic_timer", None)
    if timer is None:
        timer = QTimer(window)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: _run_force_iconic_restore(window))
        window._memoria_iconic_timer = timer  # noqa: SLF001
    timer.start(delay_ms)


def _schedule_post_iconic_web_sync(window: QMainWindow) -> None:
    """任务栏从最小化恢复：几何校正 + 多拍 finalize（防快速 min↔restore 取消单次 timer）。"""
    window._memoria_iconic_attempt = 0  # noqa: SLF001
    window._memoria_was_minimized = False  # noqa: SLF001
    schedule_force_iconic_restore(window, delay_ms=_ICONIC_RESTORE_INITIAL_MS)
    schedule_finalize_burst(window, reason="restore_from_min", commit_bounds=True)


def _run_force_iconic_restore(window: QMainWindow) -> None:
    if window.isMinimized():
        attempt = getattr(window, "_memoria_iconic_attempt", 0)
        if attempt < 8:
            window._memoria_iconic_attempt = attempt + 1  # noqa: SLF001
            shell_log_window(
                window,
                "force_iconic_restore_wait",
                attempt=attempt,
            )
            schedule_force_iconic_restore(window, delay_ms=60)
        else:
            schedule_finalize_burst(window, reason="iconic_restore_timeout")
        return
    if window.isMaximized():
        schedule_finalize_window_layout(window, delay_ms=0, reason="restore_while_max")
        return
    bounds = get_normal_bounds(window)
    if not bounds or not _bounds_sane(window, bounds):
        shell_log_window(
            window, "force_iconic_restore_skipped", bounds=bounds
        )
        schedule_finalize_burst(window, reason="iconic_restore_skipped")
        return
    attempt = getattr(window, "_memoria_iconic_attempt", 0)
    window._memoria_iconic_attempt = attempt + 1  # noqa: SLF001
    shell_log_window(
        window,
        "force_iconic_restore",
        attempt=attempt,
        bounds=bounds,
        cur=(window.width(), window.height()),
    )
    apply_normal_bounds(window, bounds)
    if (
        _collapsed_height(window) or _geometry_needs_fix(window, bounds)
    ) and attempt < 4:
        schedule_force_iconic_restore(window, delay_ms=120)
        return
    window._memoria_iconic_attempt = 0  # noqa: SLF001
    window._memoria_restore_active = False  # noqa: SLF001
    finalize_window_layout(window, reason="iconic_restore", commit_bounds=True)


def force_iconic_restore(window: QMainWindow) -> None:
    window._memoria_iconic_attempt = 0  # noqa: SLF001
    _run_force_iconic_restore(window)


_STABILIZE_MAX_ATTEMPTS = 6
_STABILIZE_RETRY_MS = 60
_INTERACTION_FINALIZE_MS = 80
_ICONIC_RESTORE_INITIAL_MS = 80
_FINALIZE_BURST_DELAYS_MS = (0, 120, 280)


def _stabilize_normal_geometry(window: QMainWindow) -> None:
    """最大化还原等：尺寸不对则强制写入，不被动等待 DWM。"""
    if window.isMinimized():
        return
    if window.isMaximized():
        attempt = getattr(window, "_memoria_stabilize_attempt", 0)
        if attempt < _STABILIZE_MAX_ATTEMPTS:
            window._memoria_stabilize_attempt = attempt + 1  # noqa: SLF001
            from PyQt6.QtCore import QTimer

            shell_log_window(
                window,
                "stabilize_wait_restore",
                attempt=attempt,
            )
            QTimer.singleShot(
                _STABILIZE_RETRY_MS, lambda w=window: _stabilize_normal_geometry(w)
            )
            return
        window._memoria_restore_active = False  # noqa: SLF001
        schedule_finalize_window_layout(window, delay_ms=0, reason="stabilize_gave_up")
        return
    bounds = get_normal_bounds(window)
    if not bounds or not _bounds_sane(window, bounds):
        shell_log_window(
            window, "stabilize_skipped", reason="bad_bounds", bounds=bounds
        )
        window._memoria_restore_active = False  # noqa: SLF001
        finalize_window_layout(window, reason="stabilize_skipped")
        return

    attempt = getattr(window, "_memoria_stabilize_attempt", 0)
    window._memoria_stabilize_attempt = attempt + 1  # noqa: SLF001

    if _collapsed_height(window):
        schedule_force_iconic_restore(window, delay_ms=80)
        return

    if _geometry_needs_fix(window, bounds):
        shell_log_window(
            window,
            "stabilize_apply",
            attempt=attempt,
            bounds=bounds,
            cur=(window.width(), window.height()),
        )
        apply_normal_bounds(window, bounds)
        if _geometry_needs_fix(window, bounds) and attempt < _STABILIZE_MAX_ATTEMPTS:
            from PyQt6.QtCore import QTimer

            QTimer.singleShot(
                _STABILIZE_RETRY_MS, lambda w=window: _stabilize_normal_geometry(w)
            )
            return

    shell_log_window(
        window,
        "stabilize_done",
        attempt=attempt,
        bounds=bounds,
        cur=(window.width(), window.height()),
    )
    window._memoria_restore_active = False  # noqa: SLF001
    finalize_window_layout(window, reason="stabilize_done", commit_bounds=True)


def _schedule_post_restore_web_sync(window: QMainWindow) -> None:
    """最大化 → 还原：几何校正 + 多拍 finalize。"""
    schedule_stabilize_normal_geometry(window, initial_delay_ms=_INTERACTION_FINALIZE_MS)
    schedule_finalize_burst(window, reason="restore_from_max", commit_bounds=True)


def schedule_stabilize_normal_geometry(
    window: QMainWindow, *, initial_delay_ms: int = 120
) -> None:
    from PyQt6.QtCore import QTimer

    window._memoria_stabilize_attempt = 0  # noqa: SLF001
    timer = getattr(window, "_memoria_stabilize_timer", None)
    if timer is None:
        timer = QTimer(window)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: _stabilize_normal_geometry(window))
        window._memoria_stabilize_timer = timer  # noqa: SLF001
    timer.start(initial_delay_ms)


def ensure_normal_geometry(window: QMainWindow) -> bool:
    """兼容旧调用：单次尝试校正。"""
    bounds = get_normal_bounds(window)
    if not bounds or not _geometry_needs_fix(window, bounds):
        return False
    apply_normal_bounds(window, bounds)
    return True


def schedule_ensure_normal_geometry(
    window: QMainWindow, *, delays_ms: tuple[int, ...] = (120,)
) -> None:
    _ = delays_ms
    schedule_stabilize_normal_geometry(window)


def begin_system_move(window: QMainWindow) -> bool:
    """启动系统拖动；原生 mousePress 上下文优先 startSystemMove。"""
    handle = window.windowHandle()
    if handle is not None and handle.startSystemMove():
        shell_log("begin_system_move", via="startSystemMove", ok=True)
        return True
    if sys.platform == "win32":
        hwnd = _resolve_hwnd(window)
        if hwnd:
            user32.ReleaseCapture()
            user32.SendMessageW(hwnd, WM_SYSCOMMAND, SC_MOVE | HTCAPTION, 0)
            shell_log("begin_system_move", via="SendMessage", hwnd=hwnd, ok=True)
            return True
    shell_log("begin_system_move", ok=False)
    return False


def _window_is_maximized(window: QMainWindow) -> bool:
    if window.isMaximized():
        return True
    if sys.platform == "win32":
        hwnd = _resolve_hwnd(window)
        return bool(hwnd and user32.IsZoomed(hwnd))
    return False


def win32_is_maximized(window: QMainWindow) -> bool:
    return window.isMaximized()


def win32_maximize(window: QMainWindow) -> None:
    shell_log_window(window, "win32_maximize")
    window.showMaximized()


def win32_restore(window: QMainWindow, bounds: tuple[int, int, int, int] | None) -> None:
    """SetWindowPlacement 原子还原，并在动画结束后校正尺寸。"""
    shell_log_window(window, "win32_restore_before", bounds=bounds)
    if bounds:
        set_restore_target(window, bounds)
    window._memoria_restore_active = True  # noqa: SLF001
    if sys.platform == "win32" and bounds:
        hwnd = _resolve_hwnd(window)
        if hwnd:
            wp = _WINDOWPLACEMENT()
            wp.length = ctypes.sizeof(_WINDOWPLACEMENT)
            if user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
                x, y, w, h = bounds
                wp.rcNormalPosition.left = x
                wp.rcNormalPosition.top = y
                wp.rcNormalPosition.right = x + w
                wp.rcNormalPosition.bottom = y + h
                wp.showCmd = SW_RESTORE
                user32.SetWindowPlacement(hwnd, ctypes.byref(wp))
            window.raise_()
            window.activateWindow()
            layout_titlebar_drag_handles(window)
            _schedule_post_restore_web_sync(window)
            shell_log_window(
                window, "win32_restore_after", bounds=bounds, via="SetWindowPlacement"
            )
            return
    window.showNormal()
    window.raise_()
    window.activateWindow()
    layout_titlebar_drag_handles(window)
    if bounds:
        _schedule_post_restore_web_sync(window)
    shell_log_window(window, "win32_restore_after", bounds=bounds, via="showNormal")


def commit_user_bounds(window: QMainWindow) -> None:
    """用户拖动/缩放结束后更新 restore target（不在还原动画中调用）。"""
    if _restore_active(window) or window.isMaximized() or window.isMinimized():
        return
    geo = window.geometry()
    bounds = geo.x(), geo.y(), geo.width(), geo.height()
    if _bounds_sane(window, bounds):
        set_restore_target(window, bounds)


def _cancel_pending_finalize(window: QMainWindow) -> None:
    """最小化等：取消去抖 timer，并使已排队的 burst 代次失效。"""
    _cancel_finalize_timer(window)
    window._memoria_finalize_burst_id = (  # noqa: SLF001
        getattr(window, "_memoria_finalize_burst_id", 0) + 1
    )
    window._memoria_was_minimized = True  # noqa: SLF001


def _bump_finalize_burst(window: QMainWindow) -> int:
    burst_id = getattr(window, "_memoria_finalize_burst_id", 0) + 1
    window._memoria_finalize_burst_id = burst_id  # noqa: SLF001
    return burst_id


def schedule_finalize_burst(
    window: QMainWindow,
    *,
    reason: str = "",
    commit_bounds: bool = False,
) -> None:
    """状态切换后连拍 finalize（0/120/280ms），避免快速 min↔restore 吃掉单次 timer。"""
    from PyQt6.QtCore import QTimer

    burst_id = _bump_finalize_burst(window)
    shell_log_window(window, "finalize_burst_scheduled", burst=burst_id, reason=reason)
    for delay_ms in _FINALIZE_BURST_DELAYS_MS:
        QTimer.singleShot(
            int(delay_ms),
            lambda w=window, bid=burst_id, d=delay_ms, r=reason, cb=commit_bounds: _run_finalize_burst_tick(  # noqa: ARG005
                w, bid, d, r, cb
            ),
        )


def _run_finalize_burst_tick(
    window: QMainWindow,
    burst_id: int,
    delay_ms: int,
    reason: str,
    commit_bounds: bool,
) -> None:
    if getattr(window, "_memoria_finalize_burst_id", 0) != burst_id:
        return
    if window.isMinimized():
        shell_log_window(
            window,
            "finalize_burst_skipped",
            burst=burst_id,
            delay=delay_ms,
            reason="still_minimized",
        )
        return
    finalize_window_layout(
        window,
        reason=f"{reason}@{delay_ms}ms",
        commit_bounds=commit_bounds and delay_ms == 0,
    )


def _cancel_finalize_timer(window: QMainWindow) -> None:
    timer = getattr(window, "_memoria_finalize_timer", None)
    if timer is not None:
        timer.stop()


def finalize_window_layout(
    window: QMainWindow, *, reason: str = "", commit_bounds: bool = False
) -> None:
    """窗口交互结束后的统一重渲染：WebEngine 几何 + 页面 resize。"""
    if window.isMinimized():
        shell_log_window(window, "finalize_layout_skipped", reason=reason)
        return
    ensure_web_view_geometry(window)
    refresh_window_chrome(window)
    refresh_web_content(window)
    if commit_bounds:
        commit_user_bounds(window)
    shell_log_window(
        window,
        "finalize_layout",
        reason=reason,
        size=(window.width(), window.height()),
    )


def schedule_finalize_window_layout(
    window: QMainWindow,
    *,
    delay_ms: int = _INTERACTION_FINALIZE_MS,
    reason: str = "",
    commit_bounds: bool = False,
) -> None:
    """去抖：拖拽/缩放退出或窗口状态变化结束后触发一次 finalize。"""
    window._memoria_finalize_reason = reason  # noqa: SLF001
    if commit_bounds:
        window._memoria_finalize_commit_bounds = True  # noqa: SLF001
    from PyQt6.QtCore import QTimer

    timer = getattr(window, "_memoria_finalize_timer", None)
    if timer is None:
        timer = QTimer(window)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda w=window: _run_scheduled_finalize(w))
        window._memoria_finalize_timer = timer  # noqa: SLF001
    timer.start(max(0, int(delay_ms)))


def _run_scheduled_finalize(window: QMainWindow) -> None:
    reason = getattr(window, "_memoria_finalize_reason", "")
    commit = bool(getattr(window, "_memoria_finalize_commit_bounds", False))
    window._memoria_finalize_commit_bounds = False  # noqa: SLF001
    finalize_window_layout(window, reason=reason, commit_bounds=commit)


def schedule_refresh_web_content(window: QMainWindow, *, delay_ms: int = 0) -> None:
    """兼容旧调用：转交到统一的 finalize 去抖。"""
    schedule_finalize_window_layout(
        window, delay_ms=delay_ms, reason="legacy_refresh"
    )


def sync_web_content_after_state_change(window: QMainWindow) -> None:
    """最大化/还原/任务栏恢复：几何校正后统一走 finalize。"""
    shell_log_window(window, "sync_web_scheduled")
    if window.isMinimized():
        return
    if _restore_active(window):
        schedule_finalize_burst(window, reason="restore_active", commit_bounds=True)
        return
    if _collapsed_height(window):
        _schedule_post_iconic_web_sync(window)
        return
    bounds = get_normal_bounds(window)
    if bounds and _geometry_needs_fix(window, bounds):
        schedule_stabilize_normal_geometry(
            window, initial_delay_ms=_INTERACTION_FINALIZE_MS
        )
        schedule_finalize_burst(window, reason="geometry_fix")
        return
    if window.isMaximized():
        schedule_finalize_burst(window, reason="maximized")
        return
    schedule_finalize_burst(window, reason="state_change", commit_bounds=True)


def create_main_window(*, frameless: bool) -> QMainWindow:
    """创建主窗口。Windows 用 hidden chrome（保留 DWM）；其它平台用 Frameless。"""
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtWidgets import QMainWindow

    class MemoriaMainWindow(QMainWindow):
        def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
            super().resizeEvent(event)
            if self.isMinimized():
                return
            if _size_move_active(self):
                # 缩放由 WM_SIZING → sync_web_view_live 驱动；此处再调会与左/上边拖拽抢尺寸。
                return
            ensure_web_view_geometry(self)
            schedule_drag_handles_layout(self)
            schedule_refresh_window_chrome(self)

        def moveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
            super().moveEvent(event)
            if self.isMinimized() or self.isMaximized() or _restore_active(self):
                return
            from PyQt6.QtCore import QTimer

            timer = getattr(self, "_memoria_commit_bounds_timer", None)
            if timer is None:
                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(lambda: commit_user_bounds(self))
                self._memoria_commit_bounds_timer = timer  # noqa: SLF001
            timer.start(250)

        def changeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
            super().changeEvent(event)
            if event.type() == QEvent.Type.WindowStateChange:
                old = event.oldState()
                new = self.windowState()
                max_mask = Qt.WindowState.WindowMaximized
                min_mask = Qt.WindowState.WindowMinimized
                if (old & max_mask) != (new & max_mask) or (old & min_mask) != (
                    new & min_mask
                ):
                    layout_titlebar_drag_handles(self)
                    unminimize = (old & min_mask) and not (new & min_mask)
                    minimize = (new & min_mask) and not (old & min_mask)
                    if minimize:
                        _cancel_pending_finalize(self)
                        shell_log_window(
                            self,
                            "changeEvent_windowState",
                            old=format_qt_window_state(old),
                            new=format_qt_window_state(new),
                            note="minimized",
                        )
                    elif unminimize:
                        shell_log_window(
                            self,
                            "changeEvent_windowState",
                            old=format_qt_window_state(old),
                            new=format_qt_window_state(new),
                            note="iconic_deferred",
                        )
                        _schedule_post_iconic_web_sync(self)
                    else:
                        sync_web_content_after_state_change(self)
                        shell_log_window(
                            self,
                            "changeEvent_windowState",
                            old=format_qt_window_state(old),
                            new=format_qt_window_state(new),
                        )

    window = MemoriaMainWindow()
    window._memoria_frameless = frameless  # noqa: SLF001
    if not frameless:
        return window

    if sys.platform == "win32":
        window.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
    else:
        window.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
        )
    return window


def prepare_frameless_window(window: QMainWindow) -> None:
    _ = window


def _resolve_hwnd(window: QMainWindow) -> int:
    from PyQt6.QtWidgets import QApplication

    QApplication.processEvents()
    handle = window.windowHandle()
    if handle is not None:
        wid = int(handle.winId())
        if wid:
            return wid
    return int(window.winId())


def _refresh_nonclient_frame(hwnd: int) -> None:
    if sys.platform != "win32" or not hwnd:
        return
    user32.SetWindowPos(
        hwnd,
        None,
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
    )


def _apply_dwm_attrs(hwnd: int) -> None:
    if sys.platform != "win32" or not hwnd:
        return
    dark = ctypes.c_int(1)
    dwmapi.DwmSetWindowAttribute(
        hwnd,
        DWMWA_USE_IMMERSIVE_DARK_MODE,
        ctypes.byref(dark),
        ctypes.sizeof(dark),
    )
    corner = ctypes.c_int(DWMWCP_ROUND)
    dwmapi.DwmSetWindowAttribute(
        hwnd,
        DWMWA_WINDOW_CORNER_PREFERENCE,
        ctypes.byref(corner),
        ctypes.sizeof(corner),
    )


def refresh_window_chrome(window: QMainWindow) -> None:
    """重刷 DWM 圆角 + 非客户区（resize / 还原后 client 区与帧对齐）。"""
    if sys.platform != "win32":
        return
    hwnd = _resolve_hwnd(window)
    if not hwnd:
        return
    _apply_dwm_attrs(hwnd)
    _refresh_nonclient_frame(hwnd)


def schedule_refresh_window_chrome(
    window: QMainWindow, *, delay_ms: int = 80
) -> None:
    if _size_move_active(window):
        return
    from PyQt6.QtCore import QTimer

    timer = getattr(window, "_memoria_chrome_refresh_timer", None)
    if timer is None:
        timer = QTimer(window)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: refresh_window_chrome(window))
        window._memoria_chrome_refresh_timer = timer  # noqa: SLF001
    timer.start(delay_ms)


def _size_move_active(window: QMainWindow) -> bool:
    return bool(getattr(window, "_memoria_size_move_active", False))


def _set_size_move_active(window: QMainWindow, active: bool) -> None:
    window._memoria_size_move_active = active  # noqa: SLF001


def _cancel_deferred_resize_chrome(window: QMainWindow) -> None:
    for attr in ("_memoria_chrome_refresh_timer", "_memoria_drag_layout_timer"):
        timer = getattr(window, attr, None)
        if timer is not None:
            timer.stop()


def _frame_insets(hwnd: int) -> tuple[int, int]:
    wr = wintypes.RECT()
    cr = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(wr))
    user32.GetClientRect(hwnd, ctypes.byref(cr))
    inset_x = (wr.right - wr.left) - (cr.right - cr.left)
    inset_y = (wr.bottom - wr.top) - (cr.bottom - cr.top)
    return max(0, inset_x), max(0, inset_y)


def _proposed_client_size(hwnd: int, lparam: int) -> tuple[int, int]:
    """WM_SIZING 的 proposed 外框矩形，比 GetClientRect 更早一帧。"""
    rect = _RECT.from_address(lparam)
    prop_w = rect.right - rect.left
    prop_h = rect.bottom - rect.top
    inset_x, inset_y = _frame_insets(hwnd)
    return max(1, prop_w - inset_x), max(1, prop_h - inset_y)


def _client_size(
    window: QMainWindow, *, hwnd: int = 0, sizing_lparam: int = 0
) -> tuple[int, int]:
    if sys.platform == "win32" and hwnd and sizing_lparam:
        return _proposed_client_size(hwnd, sizing_lparam)
    if sys.platform == "win32" and hwnd:
        rect = wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(rect))
        return rect.right - rect.left, rect.bottom - rect.top
    return window.width(), window.height()


def ensure_web_view_geometry(window: QMainWindow) -> None:
    """WebEngine 铺满客户区，避免缩放/拖动后右侧露黑边。"""
    if window.isMinimized() or _restore_active(window):
        return
    view = window.centralWidget()
    if view is None:
        return
    w, h = window.width(), window.height()
    if w <= 0 or h <= 0:
        return
    geo = view.geometry()
    if geo.x() != 0 or geo.y() != 0 or geo.width() != w or geo.height() != h:
        view.setGeometry(0, 0, w, h)


def _border_hit_test(hwnd: int, lparam: int) -> int | None:
    x = lparam & 0xFFFF
    y = (lparam >> 16) & 0xFFFF
    if x >= 0x8000:
        x -= 0x10000
    if y >= 0x8000:
        y -= 0x10000
    pt = wintypes.POINT(x, y)
    user32.ScreenToClient(hwnd, ctypes.byref(pt))
    cx, cy = pt.x, pt.y

    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return None

    on_left = cx < BORDER
    on_right = cx >= w - BORDER
    on_top = cy < BORDER
    on_bottom = cy >= h - BORDER

    if on_top and on_left:
        return HTTOPLEFT
    if on_top and on_right:
        return HTTOPRIGHT
    if on_bottom and on_left:
        return HTBOTTOMLEFT
    if on_bottom and on_right:
        return HTBOTTOMRIGHT
    if on_left:
        return HTLEFT
    if on_right:
        return HTRIGHT
    if on_top:
        return HTTOP
    if on_bottom:
        return HTBOTTOM
    return None


def register_web_view_hwnd(window: QMainWindow) -> None:
    """记录 WebEngine 子 HWND，供边缘 WM_NCHITTEST 转发。"""
    view = window.centralWidget()
    if view is None:
        return
    try:
        wid = int(view.winId())
        if wid:
            window._memoria_web_hwnd = wid  # noqa: SLF001
    except Exception:  # noqa: BLE001
        pass


def apply_hidden_chrome(
    window: QMainWindow, app: QApplication, *, hwnd: int = 0
) -> None:
    """安装 Win32 hidden chrome 过滤器（QAbstractNativeEventFilter，兼容 WebEngine）。"""
    if sys.platform != "win32":
        return
    if not getattr(window, "_memoria_frameless", False):
        return
    if getattr(window, "_hidden_chrome_filter", None) is not None:
        return

    from PyQt6.QtCore import QAbstractNativeEventFilter

    class HiddenChromeFilter(QAbstractNativeEventFilter):
        _SIZE_NAMES = {SIZE_RESTORED: "RESTORED", SIZE_MINIMIZED: "MINIMIZED", SIZE_MAXIMIZED: "MAXIMIZED"}

        def __init__(self, target: QMainWindow, initial_hwnd: int = 0) -> None:
            super().__init__()
            self._window = target
            self._hwnd = initial_hwnd
            self._await_iconic_restore = False

        def _hwnd_or_resolve(self) -> int:
            if not self._hwnd or not user32.IsWindow(self._hwnd):
                self._hwnd = _resolve_hwnd(self._window)
            return self._hwnd

        def _matches_root(self, msg_hwnd: int) -> bool:
            return msg_hwnd == self._hwnd_or_resolve()

        def _matches_nchittest(self, msg_hwnd: int) -> bool:
            if self._matches_root(msg_hwnd):
                return True
            web = getattr(self._window, "_memoria_web_hwnd", 0)
            return bool(web and msg_hwnd == web)

        def nativeEventFilter(self, eventType, message):  # type: ignore[no-untyped-def]
            if eventType != b"windows_generic_MSG":
                return False, 0
            try:
                msg = wintypes.MSG.from_address(_msg_address(message))

                if msg.message == WM_NCHITTEST:
                    if not self._matches_nchittest(msg.hWnd):
                        return False, 0
                    root = self._hwnd_or_resolve()
                    hit = _border_hit_test(root, msg.lParam)
                    if hit is None:
                        return False, 0
                    # WebEngine 子 HWND 若直接返回 HTLEFT 等，Win32 只会缩放子窗口；
                    # 客户区内容变大但外框不动。透传给顶层后再由 root 返回命中码。
                    if msg.hWnd != root:
                        return True, HTTRANSPARENT
                    return True, hit

                if not self._matches_root(msg.hWnd):
                    return False, 0

                if msg.message == WM_NCCALCSIZE:
                    if msg.wParam:
                        params = _NCCALCSIZE_PARAMS.from_address(msg.lParam)
                        _apply_nc_calc(params, msg.hWnd)
                    else:
                        rect = _RECT.from_address(msg.lParam)
                        _apply_nc_calc_rect(rect, msg.hWnd)
                    return True, 0

                if msg.message == WM_SIZE:
                    wp = int(msg.wParam)
                    name = self._SIZE_NAMES.get(wp, f"UNKNOWN_{wp}")
                    if wp == SIZE_MINIMIZED:
                        self._await_iconic_restore = True
                        _cancel_pending_finalize(self._window)
                        iconic = getattr(self._window, "_memoria_iconic_timer", None)
                        if iconic is not None:
                            iconic.stop()
                        shell_log_window(self._window, "wm_size", kind=name)
                    elif wp == SIZE_RESTORED and (
                        self._await_iconic_restore
                        or getattr(self._window, "_memoria_was_minimized", False)
                    ):
                        self._await_iconic_restore = False
                        self._window._memoria_was_minimized = False  # noqa: SLF001
                        shell_log_window(
                            self._window, "wm_size", kind=name, iconic_restore=True
                        )
                        from PyQt6.QtCore import QTimer

                        QTimer.singleShot(
                            0,
                            lambda: _schedule_post_iconic_web_sync(self._window),
                        )
                    elif wp == SIZE_RESTORED and _size_move_active(self._window):
                        sync_web_view_live(self._window, hwnd=msg.hWnd)
                    elif wp == SIZE_RESTORED and not self._window.isMaximized():
                        schedule_finalize_burst(
                            self._window, reason="size_restored"
                        )
                    elif wp == SIZE_MAXIMIZED:
                        shell_log_window(self._window, "wm_size", kind=name)
                        from PyQt6.QtCore import QTimer

                        QTimer.singleShot(
                            0,
                            lambda: schedule_finalize_burst(
                                self._window, reason="maximized"
                            ),
                        )

                if msg.message == WM_ENTERSIZEMOVE:
                    shell_log("wm_entersizemove", hwnd=msg.hWnd)
                    _set_size_move_active(self._window, True)
                    _cancel_deferred_resize_chrome(self._window)
                    _cancel_live_resize_js_timer(self._window)
                    self._window._memoria_live_wh = None  # noqa: SLF001
                    self._window._memoria_view_wh = None  # noqa: SLF001

                if msg.message == WM_MOVE and _size_move_active(self._window):
                    sync_web_view_live(self._window, hwnd=msg.hWnd)

                if msg.message == WM_SIZING:
                    sync_web_view_live(
                        self._window, hwnd=msg.hWnd, sizing_lparam=msg.lParam
                    )

                if msg.message == WM_EXITSIZEMOVE:
                    shell_log("wm_exitsizemove", hwnd=msg.hWnd)
                    _set_size_move_active(self._window, False)
                    _cancel_live_resize_js_timer(self._window)
                    self._window._memoria_live_wh = None  # noqa: SLF001
                    self._window._memoria_view_wh = None  # noqa: SLF001
                    schedule_finalize_window_layout(
                        self._window,
                        delay_ms=0,
                        reason="exit_size_move",
                        commit_bounds=True,
                    )

            except Exception:
                pass
            return False, 0

    filt = HiddenChromeFilter(window, initial_hwnd=hwnd)
    app.installNativeEventFilter(filt)
    window._hidden_chrome_filter = filt  # noqa: SLF001
    shell_log("hidden_chrome_installed", hwnd=hwnd)


def finalize_frameless_chrome(window: QMainWindow, app: QApplication) -> None:
    """show 后：hidden chrome + DWM + 强制刷新非客户区。"""
    if not getattr(window, "_memoria_frameless", False):
        return

    if sys.platform != "win32":
        return

    hwnd = _resolve_hwnd(window)
    apply_hidden_chrome(window, app, hwnd=hwnd)
    register_web_view_hwnd(window)
    if hwnd:
        _apply_dwm_attrs(hwnd)
        _refresh_nonclient_frame(hwnd)
        from memoria.app.shell.app_icon import reapply_app_window_icons

        reapply_app_window_icons(app, window)
        from PyQt6.QtCore import QTimer

        QTimer.singleShot(100, lambda: refresh_window_chrome(window))
        QTimer.singleShot(100, lambda: reapply_app_window_icons(app, window))


_LIVE_RESIZE_JS = "window.dispatchEvent(new Event('resize'));"
_LIVE_RESIZE_JS_INTERVAL_MS = 16


def _web_page(view) -> object | None:
    if view is None:
        return None
    page_attr = getattr(view, "page", None)
    if page_attr is None:
        return None
    return page_attr() if callable(page_attr) else page_attr


def _dispatch_live_resize_js(window: QMainWindow) -> None:
    page = _web_page(window.centralWidget())
    if page is not None:
        page.runJavaScript(_LIVE_RESIZE_JS)


def _notify_live_resize_if_changed(
    window: QMainWindow, w: int, h: int
) -> None:
    """尺寸变化时通知页面 reflow。"""
    if not _size_move_active(window):
        return
    last = getattr(window, "_memoria_live_wh", None)
    if last == (w, h):
        return
    window._memoria_live_wh = (w, h)  # noqa: SLF001
    _dispatch_live_resize_js(window)


def _cancel_live_resize_js_timer(window: QMainWindow) -> None:
    timer = getattr(window, "_memoria_live_resize_js_timer", None)
    if timer is not None:
        timer.stop()


def _defer_live_resize_notify(window: QMainWindow, w: int, h: int) -> None:
    """WM_SIZING 内合并 resize 通知，避免每帧 runJavaScript 拖慢 Win32 模态缩放。"""
    window._memoria_pending_live_wh = (w, h)  # noqa: SLF001
    from PyQt6.QtCore import QTimer

    timer = getattr(window, "_memoria_live_resize_js_timer", None)
    if timer is None:
        timer = QTimer(window)
        timer.setSingleShot(True)

        def _fire() -> None:
            wh = getattr(window, "_memoria_pending_live_wh", None)
            if wh is not None:
                _notify_live_resize_if_changed(window, wh[0], wh[1])

        timer.timeout.connect(_fire)
        window._memoria_live_resize_js_timer = timer  # noqa: SLF001
    timer.start(_LIVE_RESIZE_JS_INTERVAL_MS)


def sync_web_view_live(
    window: QMainWindow, *, hwnd: int = 0, sizing_lparam: int = 0
) -> None:
    """拖拽缩放时即时调整 WebEngine 尺寸（无 DWM / drag handle / 日志）。"""
    if window.isMinimized() or _restore_active(window):
        return
    view = window.centralWidget()
    if view is None:
        return
    w, h = _client_size(window, hwnd=hwnd, sizing_lparam=sizing_lparam)
    if w <= 0 or h <= 0:
        return
    last_view = getattr(window, "_memoria_view_wh", None)
    size_changed = last_view != (w, h)
    if size_changed:
        window._memoria_view_wh = (w, h)  # noqa: SLF001
        view.setGeometry(0, 0, w, h)
        view.update()
    if sizing_lparam:
        _defer_live_resize_notify(window, w, h)
    elif size_changed:
        _notify_live_resize_if_changed(window, w, h)


def schedule_live_web_resize_notify(
    window: QMainWindow, *, delay_ms: int = 16
) -> None:
    """兼容旧调用；缩放路径已改为尺寸变化即通知。"""
    if not _size_move_active(window):
        return
    w, h = _client_size(window)
    if delay_ms <= 0:
        _notify_live_resize_if_changed(window, w, h)
        return
    _notify_live_resize_if_changed(window, w, h)


def schedule_drag_handles_layout(window: QMainWindow, *, delay_ms: int = 16) -> None:
    if _size_move_active(window):
        return
    from PyQt6.QtCore import QTimer

    timer = getattr(window, "_memoria_drag_layout_timer", None)
    if timer is None:
        timer = QTimer(window)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: layout_titlebar_drag_handles(window))
        window._memoria_drag_layout_timer = timer  # noqa: SLF001
    if delay_ms <= 0:
        layout_titlebar_drag_handles(window)
        return
    remaining = timer.remainingTime()
    if remaining < 0 or delay_ms > remaining:
        timer.start(delay_ms)


def refresh_web_content(window: QMainWindow) -> None:
    """状态变化后轻量同步 WebEngine（不用 hide/show，避免任务栏恢复白屏）。"""
    if window.isMinimized():
        shell_log_window(window, "refresh_web_skipped", reason="minimized")
        return
    view = window.centralWidget()
    if view is None:
        shell_log_window(window, "refresh_web_skipped", reason="no_view")
        return

    w, h = window.width(), window.height()
    if w <= 0 or h <= 0:
        shell_log_window(window, "refresh_web_skipped", reason="bad_size", w=w, h=h)
        return

    geo = view.geometry()
    resized = geo.width() != w or geo.height() != h
    ensure_web_view_geometry(window)
    view.updateGeometry()
    if hasattr(view, "update"):
        view.update()
    layout_titlebar_drag_handles(window)
    _dispatch_live_resize_js(window)
    shell_log_window(window, "refresh_web_done", resized=resized)


def install_titlebar_drag_handles(window: QMainWindow) -> None:
    """PyQt6 顶栏拖动由 JS + QWebChannel.startMove 处理，不再叠加原生透明层（会挡住 kb 路径点击）。"""
    window._memoria_toolbar_no_drag_from = 0  # noqa: SLF001
    left = getattr(window, "_drag_handle_left", None)
    spacer = getattr(window, "_drag_handle_spacer", None)
    if left is not None:
        left.hide()
        left.deleteLater()
        window._drag_handle_left = None  # noqa: SLF001
    if spacer is not None:
        spacer.hide()
        spacer.deleteLater()
        window._drag_handle_spacer = None  # noqa: SLF001


def set_toolbar_drag_exclusion(window: QMainWindow, left_x: int) -> None:
    window._memoria_toolbar_no_drag_from = max(0, int(left_x))  # noqa: SLF001


def layout_titlebar_drag_handles(window: QMainWindow) -> None:
    """兼容旧调用点；原生拖拽条已移除。"""
    return


# ── 首帧合成强化 ──────────────────────────────────────────────
# 现象：发布态（PyQt6 / WebEngine）首次打开窗口可见但内容冻结、点击无响应；
# 最小化→还原（触发 refresh_web_content + refresh_window_chrome 强制 DWM 重合成）
# 后才正常。页面其实早已加载完，问题在于 Chromium 合成器未把首帧提交到窗口表面，
# 且 show 后没有任何强制重绘动作。对策：show / loadFinished 后多拍强制重绘，
# 与还原路径完全对齐（同样的 refresh_web_content + refresh_window_chrome 调用）。

# 每拍之后的间隔（ms）：共 1+len 拍，覆盖冷启动时 GPU 合成器就绪前的窗口期。
_FIRST_PAINT_DELAYS_MS = (100, 200, 500, 1000, 1500)


def schedule_first_paint_refresh(window: QMainWindow) -> None:
    """调度多拍首帧强制重绘；重复调用会重置节奏（show 与 loadFinished 双触发去重）。"""
    from PyQt6.QtCore import QTimer

    timer = getattr(window, "_memoria_first_paint_timer", None)
    if timer is None:
        timer = QTimer(window)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: _first_paint_refresh_tick(window))
        window._memoria_first_paint_timer = timer  # noqa: SLF001
    window._memoria_first_paint_shot = 0  # noqa: SLF001
    timer.start(0)
    shell_log_window(window, "first_paint_scheduled")


def _first_paint_refresh_tick(window: QMainWindow) -> None:
    if window.isMinimized():
        shell_log_window(window, "first_paint_skipped", reason="minimized")
        return
    shot = getattr(window, "_memoria_first_paint_shot", 0)
    window._memoria_first_paint_shot = shot + 1  # noqa: SLF001
    refresh_web_content(window)
    refresh_window_chrome(window)
    # 诊断：每拍查询前端激活/可见性/探针状态，对比"最小化还原后正常"的差异
    view = window.centralWidget()
    if view is not None and hasattr(view, "page"):
        try:
            view.page().runJavaScript(
                "JSON.stringify({focus: document.hasFocus(), vis: document.visibilityState,"
                " ready: document.readyState, diag: window.__m0diag || null})",
                lambda r, s=shot: shell_log_window(
                    window, "first_paint_frontend", shot=s, state=str(r)
                ),
            )
        except Exception:  # noqa: BLE001
            pass
    # 最后一拍：主动激活窗口与 view 焦点（对齐"最小化还原后恢复交互"的激活机制）
    if shot == len(_FIRST_PAINT_DELAYS_MS):
        window.raise_()
        window.activateWindow()
        if view is not None:
            try:
                view.setFocus()
            except Exception:  # noqa: BLE001
                pass
        shell_log_window(window, "first_paint_focus_applied")
    shell_log_window(window, "first_paint_refresh", shot=shot)
    timer = getattr(window, "_memoria_first_paint_timer", None)
    if timer is not None and shot < len(_FIRST_PAINT_DELAYS_MS):
        timer.start(_FIRST_PAINT_DELAYS_MS[shot])
