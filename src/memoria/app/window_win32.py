"""Windows 无边框窗口：工作区最大化（不遮挡任务栏）。

无边框窗口的“原生窗口行为”（拖拽 / 动画 / 圆角 / Aero Snap）实现要点：
- 保留 WS_CAPTION 等标准窗口样式 + DWM 边框渲染：DWM 视窗口为标准窗口，
  最小化/还原/最大化播放原生渐变动画，边框/圆角/阴影由 DWM 渲染；
- WM_NCCALCSIZE→0：客户区 = 完整窗口，消除标题栏空白带（视觉无边框）；
- DWMWA_WINDOW_CORNER_PREFERENCE=ROUND：Win11 系统圆角；
- 标题栏拖动：前端检测拖拽动作 → RPC → PostMessage → WndProc（UI 线程）
  执行 ReleaseCapture + SendMessage(WM_NCLBUTTONDOWN, HTCAPTION)，进入
  系统原生标题栏拖动（鼠标捕获、Aero Snap、最大化时下拉还原）。
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
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


class _POINT(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
    ]


class _MINMAXINFO(ctypes.Structure):
    _fields_ = [
        ("ptReserved", _POINT),
        ("ptMaxSize", _POINT),
        ("ptMaxPosition", _POINT),
        ("ptMinTrackSize", _POINT),
        ("ptMaxTrackSize", _POINT),
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


class _NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [
        ("rgrc", _RECT * 3),
        ("lppos", ctypes.c_void_p),
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


def native_hwnd(window) -> int | None:
    """从 pywebview window.native（WinForms BrowserForm）取 HWND。"""
    native = getattr(window, "native", None)
    if native is None:
        return None
    handle = getattr(native, "Handle", None)
    if handle is None:
        return None
    return int(handle.ToInt64())


class _WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.UINT),
        ("flags", wintypes.UINT),
        ("showCmd", wintypes.UINT),
        ("ptMinPosition", wintypes.LONG * 2),
        ("ptMaxPosition", wintypes.LONG * 2),
        ("rcNormalPosition", wintypes.LONG * 4),
    ]


def is_maximized(window) -> bool | None:
    """读取窗口真实最大化状态（含 Aero Snap 等系统操作）。"""
    hwnd = native_hwnd(window)
    if hwnd is None:
        return None
    user32 = ctypes.windll.user32
    wp = _WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(_WINDOWPLACEMENT)
    if not user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
        return None
    return wp.showCmd == 3  # SW_MAXIMIZE


def send_syscommand(window, command: int) -> bool:
    """WM_SYSCOMMAND：走系统命令路径（触发 DWM 原生动画）。"""
    hwnd = native_hwnd(window)
    if hwnd is None:
        return False
    user32 = ctypes.windll.user32
    user32.SendMessageW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    ]
    user32.SendMessageW(hwnd, 0x0112, command, 0)  # WM_SYSCOMMAND
    return True


def start_system_drag(window) -> bool:
    """系统级窗口拖动：ReleaseCapture + WM_NCLBUTTONDOWN(HTCAPTION)。
    无边框窗口获得原生拖动体验（平滑、Aero Snap 生效）。"""
    hwnd = native_hwnd(window)
    if hwnd is None:
        return False
    user32 = ctypes.windll.user32
    user32.ReleaseCapture()
    user32.SendMessageW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    ]
    user32.SendMessageW(hwnd, 0x00A1, 0x0002, 0)  # WM_NCLBUTTONDOWN, HTCAPTION
    return True


def enable_rounded_corners(window) -> bool:
    """DWMWA_WINDOW_CORNER_PREFERENCE(33)=DWMWCP_ROUND(2)：Win11 圆角。
    配合保留的 DWM 边框渲染（不设 DWMNCRP_DISABLED），窗口显示系统
    圆角 + 边框 + 阴影，标题栏区域由 WM_NCCALCSIZE→0 消除。"""
    hwnd = native_hwnd(window)
    if hwnd is None:
        return False
    dwmapi = ctypes.windll.dwmapi
    dwmapi.DwmSetWindowAttribute.argtypes = [
        wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
    ]
    value = ctypes.c_int(2)  # DWMWCP_ROUND
    return dwmapi.DwmSetWindowAttribute(
        hwnd, 33, ctypes.byref(value), ctypes.sizeof(ctypes.c_int)
    ) == 0


def show_window_state(window, cmd: int) -> bool:
    """ShowWindow 直接走系统窗口状态机（触发 DWM 原生渐变动画），
    绕过 WinForms 对 WM_SYSCOMMAND 的拦截。
    cmd: SW_MINIMIZE=6 / SW_MAXIMIZE=3 / SW_RESTORE=9。"""
    hwnd = native_hwnd(window)
    if hwnd is None:
        return False
    return bool(ctypes.windll.user32.ShowWindow(hwnd, cmd))


def move_window(window, x: int, y: int) -> bool:
    """仅移动窗口位置（保持大小 / Z 序 / 激活状态）——前端 JS 拖动用。"""
    hwnd = native_hwnd(window)
    if hwnd is None:
        return False
    user32 = ctypes.windll.user32
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_uint,
    ]
    # SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
    return bool(user32.SetWindowPos(hwnd, None, int(x), int(y), 0, 0, 0x0001 | 0x0004 | 0x0010))


def dpi_scale(window) -> float:
    """物理像素 / DIP 缩放比（前端 screenX/screenY 是 DIP，SetWindowPos 需物理像素）。"""
    hwnd = native_hwnd(window)
    if hwnd is None:
        return 1.0
    try:
        return ctypes.windll.user32.GetDpiForWindow(hwnd) / 96.0
    except Exception:  # noqa: BLE001
        return 1.0


def normal_bounds(window) -> tuple[int, int, int, int] | None:
    """最大化前的常规窗口矩形（rcNormalPosition，物理像素屏幕坐标）。"""
    hwnd = native_hwnd(window)
    if hwnd is None:
        return None
    user32 = ctypes.windll.user32
    wp = _WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(_WINDOWPLACEMENT)
    if not user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
        return None
    r = wp.rcNormalPosition
    return int(r[0]), int(r[1]), int(r[2] - r[0]), int(r[3] - r[1])


_WM_NCCALCSIZE = 0x0083
_WM_NCLBUTTONDOWN = 0x00A1
_WM_GETMINMAXINFO = 0x0024
_WM_WINDOWPOSCHANGING = 0x0046
_HTCAPTION = 2
_GWLP_WNDPROC = -4
_WNDPROC_CALLBACKS: dict[int, tuple[int, object]] = {}
# WM_APP 起始自定义消息：前端 JS 检测到标题栏拖拽动作后，由 RPC 处理器
# PostMessage 到窗口，WndProc（UI 线程）据此启动原生标题栏拖动
_WM_APP_BEGIN_DRAG = 0x8001

_DIAG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(sys.executable)), "window-diag.txt"
)


def _diag_write(line: str) -> None:
    try:
        with open(_DIAG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:  # noqa: BLE001
        pass


def begin_caption_drag(window) -> bool:
    """请求启动原生标题栏拖动：PostMessage 给窗口（线程安全，可后台线程调用）。
    WndProc 在 UI 线程收到 _WM_APP_BEGIN_DRAG 后执行 ReleaseCapture +
    SendMessage(WM_NCLBUTTONDOWN, HTCAPTION)，进入系统标题栏拖动循环
    （鼠标捕获、Aero Snap、最大化时下拉还原全部由 Windows 原生处理）。
    之所以 PostMessage 转发：ReleaseCapture / 拖动循环必须由 UI 线程发起，
    直接在任何后台线程调用会立即退出拖动。"""
    hwnd = native_hwnd(window)
    if hwnd is None:
        return False
    user32 = ctypes.windll.user32
    user32.PostMessageW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    ]
    return bool(user32.PostMessageW(hwnd, _WM_APP_BEGIN_DRAG, 0, 0))


def subclass_nccalcsize(window) -> bool:
    """子类化窗口 WndProc（UI 线程）——Electron/原生无边框窗口标准方案：
    - WM_NCCALCSIZE(wParam=TRUE)：非最大化返回 0（客户区 = 窗口矩形，消除
      标题栏空白带，视觉无边框）；最大化时把客户区（rgrc[0]）四周内缩 frame
      （frame = 边框+补白 ≈8px），恰好抵消系统最大化矩形的外扩量；
    - WM_GETMINMAXINFO：最大化矩形 = 工作区四周外扩 frame。系统最大化本来就
      这么干（把窗口溢出到工作区外 1 个边框宽，为保留圆角/阴影，原生窗口
      靠客户区偏移抵消）。配合上面 NCCALCSIZE 的内缩，客户区恰好 = 工作区：
      内容铺满、无缝隙、边框画在屏幕外被裁剪（不越界）；
    - WM_WINDOWPOSCHANGING：兜底——最大化时若窗口矩形被 WinForms/系统钳制
      为工作区（未外扩），修正为工作区 ± frame；
    - _WM_APP_BEGIN_DRAG：ReleaseCapture + SendMessage(WM_NCLBUTTONDOWN,
      HTCAPTION)，启动系统原生标题栏拖动（带 Aero Snap、最大化下拉还原）。
    其余消息全部透传给原 WndProc（WinForms 不受影响）。"""
    hwnd = native_hwnd(window)
    if hwnd is None:
        return False
    if hwnd in _WNDPROC_CALLBACKS:
        return True
    user32 = ctypes.windll.user32
    WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    )
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    user32.CallWindowProcW.restype = ctypes.c_ssize_t
    user32.CallWindowProcW.argtypes = [
        ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    ]
    user32.ReleaseCapture.argtypes = []
    user32.ReleaseCapture.restype = wintypes.BOOL
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.SendMessageW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    ]
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [
        wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO),
    ]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.IsZoomed.restype = wintypes.BOOL
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    old_proc = user32.GetWindowLongPtrW(hwnd, _GWLP_WNDPROC)
    _drag_first = {"done": False}
    _mmi_first = {"done": False}

    def _frame() -> int:
        """系统边框宽：SM_CXSIZEFRAME + SM_CXPADDEDBORDER（Win11 ≈8px @100%，
        随 DPI 缩放）。最大化矩形外扩 / 客户区内缩都用它，两者相消后
        客户区恰好 = 工作区。"""
        return user32.GetSystemMetrics(32) + user32.GetSystemMetrics(92)

    @WNDPROC
    def _frameless_proc(hwnd_, msg, wparam, lparam):
        if msg == _WM_NCCALCSIZE and wparam:
            # 非最大化：客户区 = 窗口矩形（无边框视觉）；最大化：客户区
            # 内缩 frame，抵消系统最大化矩形的外扩 → 客户区 = 工作区
            try:
                if user32.IsZoomed(hwnd_):
                    params = ctypes.cast(lparam, ctypes.POINTER(_NCCALCSIZE_PARAMS)).contents
                    f = _frame()
                    params.rgrc[0].left += f
                    params.rgrc[0].top += f
                    params.rgrc[0].right -= f
                    params.rgrc[0].bottom -= f
            except Exception:  # noqa: BLE001
                pass
            return 0
        if msg == _WM_GETMINMAXINFO and lparam:
            # 先透传原 WndProc（WinForms 会设置 ptMinTrackSize），再覆盖最大化矩形
            result = user32.CallWindowProcW(old_proc, hwnd_, msg, wparam, lparam)
            try:
                mmi = ctypes.cast(lparam, ctypes.POINTER(_MINMAXINFO)).contents
                monitor = user32.MonitorFromWindow(hwnd_, 2)  # MONITOR_DEFAULTTONEAREST
                mi = _MONITORINFO()
                mi.cbSize = ctypes.sizeof(_MONITORINFO)
                if user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
                    work = mi.rcWork
                    f = _frame()
                    # 系统最大化本来就外扩 1 个边框宽（为保留圆角/阴影）；
                    # 我们显式指定 = 工作区外扩 frame，NCCALCSIZE 再把客户区
                    # 内缩回 frame → 客户区恰好 = 工作区（无缝隙、不越界）
                    if not _mmi_first["done"]:
                        _mmi_first["done"] = True
                        _diag_write(
                            f"{time.strftime('%H:%M:%S')} minmaxinfo default max=("
                            f"{mmi.ptMaxPosition.x},{mmi.ptMaxPosition.y},"
                            f"{mmi.ptMaxSize.x},{mmi.ptMaxSize.y}) "
                            f"work=({work.left},{work.top},"
                            f"{work.right - work.left},{work.bottom - work.top}) "
                            f"frame={f}"
                        )
                    mmi.ptMaxPosition.x = work.left - f
                    mmi.ptMaxPosition.y = work.top - f
                    mmi.ptMaxSize.x = (work.right - work.left) + 2 * f
                    mmi.ptMaxSize.y = (work.bottom - work.top) + 2 * f
            except Exception:  # noqa: BLE001
                pass
            return result
        if msg == _WM_WINDOWPOSCHANGING and lparam:
            # 兜底：最大化时若窗口矩形被钳制为工作区（未外扩 frame，说明
            # MINMAXINFO 被 WinForms/系统覆盖），修正为工作区 ± frame。
            # 仅修正"被钳制"情形，动画中间帧/还原/拖动/分屏不干预。
            result = user32.CallWindowProcW(old_proc, hwnd_, msg, wparam, lparam)
            try:
                if user32.IsZoomed(hwnd_):
                    wpos = ctypes.cast(lparam, ctypes.POINTER(_WINDOWPOS)).contents
                    monitor = user32.MonitorFromWindow(hwnd_, 2)
                    mi = _MONITORINFO()
                    mi.cbSize = ctypes.sizeof(_MONITORINFO)
                    if user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
                        work = mi.rcWork
                        f = _frame()
                        exp_x = work.left - f
                        exp_y = work.top - f
                        exp_cx = (work.right - work.left) + 2 * f
                        exp_cy = (work.bottom - work.top) + 2 * f
                        if (
                            wpos.x == work.left
                            and wpos.y == work.top
                            and wpos.cx == work.right - work.left
                            and wpos.cy == work.bottom - work.top
                        ):
                            wpos.x = exp_x
                            wpos.y = exp_y
                            wpos.cx = exp_cx
                            wpos.cy = exp_cy
            except Exception:  # noqa: BLE001
                pass
            return result
        if msg == _WM_APP_BEGIN_DRAG:
            # 必须在 UI 线程执行：释放捕获 + 模拟标题栏按下，进入原生拖动循环
            user32.ReleaseCapture()
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            lpt = (pt.y << 16) | (pt.x & 0xFFFF)
            if not _drag_first["done"]:
                _drag_first["done"] = True
                _diag_write(
                    f"{time.strftime('%H:%M:%S')} caption drag start x={pt.x} y={pt.y}"
                )
            user32.SendMessageW(hwnd_, _WM_NCLBUTTONDOWN, _HTCAPTION, lpt)
            return 0
        return user32.CallWindowProcW(old_proc, hwnd_, msg, wparam, lparam)

    user32.SetWindowLongPtrW(hwnd, _GWLP_WNDPROC, ctypes.cast(_frameless_proc, ctypes.c_void_p).value)
    _WNDPROC_CALLBACKS[hwnd] = (old_proc, _frameless_proc)  # 保持引用，防 GC
    return True
