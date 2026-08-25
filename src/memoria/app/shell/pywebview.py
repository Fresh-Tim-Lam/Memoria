"""pywebview 桌面壳（开发默认）。"""

from __future__ import annotations

import os
import sys
import time

import webview

from memoria import __version__
from memoria.app.shell.pywebview_host import PyWebViewHost
from memoria.presentation.api.ui import UIAPI
from memoria.presentation.paths import UI_APP_INDEX
from memoria.presentation.static_server import create_app
from memoria.storage.ui_settings import resolve_last_kb_path


def _startup_kb_path() -> str | None:
    return resolve_last_kb_path()


def _frameless_enabled() -> bool:
    val = os.environ.get("MEMORIA_FRAMELESS", "").strip().lower()
    if val in ("0", "false", "no"):
        return False
    if val in ("1", "true", "yes"):
        return True
    # 默认无边框（保留自定义标题栏 UI，与开发态一致）；需要系统原生标题栏时
    # 可 MEMORIA_FRAMELESS=0。换壳核心收益：WebView2 新内核，冻结问题根治
    return True


def _debug_enabled() -> bool:
    val = os.environ.get("MEMORIA_DEBUG", "").strip().lower()
    if val in ("1", "true", "yes"):
        return True
    if val in ("0", "false", "no"):
        return False
    # 发布态关闭 pywebview 调试（右键菜单/DevTools）；开发态默认开启
    from memoria.app.runtime import resolve_mode

    return resolve_mode() == "dev"


def _apply_frameless_native(window) -> None:
    """无边框窗口补齐原生窗口行为（同 Electron“隐藏标题栏”方案）：
    任务栏最小化/还原、最小化/还原渐变动画、最大化、Aero Snap、系统菜单。

    关键点：
    1. 保留 WS_CAPTION：DWM 视窗口为“标准窗口”，最小化/还原时播放
       原生渐变动画（去掉 WS_CAPTION 后 DWM 不播动画，这是此前无动画的根因）；
    2. 保留 DWM 边框渲染（不设 DWMNCRP_DISABLED）+ DWMWA_WINDOW_CORNER_PREFERENCE
       = ROUND：Win11 圆角、边框、阴影由系统渲染，外观接近原生；
    3. WM_NCCALCSIZE → 0：客户区 = 完整窗口，消除标题栏预留的空白带；
    4. 标题栏拖动：前端检测拖拽 → RPC → PostMessage → WndProc（UI 线程）
       发起 ReleaseCapture + SendMessage(WM_NCLBUTTONDOWN, HTCAPTION)，原生拖动；
    5. WinForms 层：FormBorderStyle.None 默认 MinimizeBox=False，WndProc 会吞掉
       任务栏发出的 SC_MINIMIZE/SC_MAXIMIZE，必须显式放行。"""
    import ctypes
    import time
    from ctypes import wintypes

    from memoria.app.window_win32 import (
        enable_rounded_corners,
        subclass_nccalcsize,
    )

    user32 = ctypes.windll.user32
    GWL_STYLE = -16
    WS_POPUP = 0x80000000
    WS_CAPTION = 0x00C00000
    WS_SYSMENU = 0x00080000
    WS_THICKFRAME = 0x00040000
    WS_MINIMIZEBOX = 0x00020000
    WS_MAXIMIZEBOX = 0x00010000
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SWP_FRAMECHANGED = 0x0020

    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_uint,
    ]

    try:
        # pywebview 的 start(func) 在独立线程运行，与窗口创建并发；
        # 轮询等待 native（BrowserForm）就绪（最多约 7.5 秒）
        native = None
        for _ in range(30):
            native = window.native
            if native is not None:
                break
            time.sleep(0.25)
        if native is None:
            print("[shell] apply_frameless_native: native not ready", flush=True)
            return

        hwnd = native.Handle.ToInt64()
        steps: list[str] = []
        steps.append(f"hwnd=0x{hwnd:x}")

        # 1) WinForms 放行最小化/最大化（否则 WndProc 吞掉任务栏命令）
        try:
            native.MinimizeBox = True
            native.MaximizeBox = True
            steps.append("minmaxbox=1")
        except Exception as exc:  # noqa: BLE001
            steps.append(f"minmaxbox=ERR:{exc}")

        # 2) 先安装 WndProc 子类（NCCALCSIZE→0 + 原生标题栏拖动），
        #    再改样式并触发 FRAMECHANGED，保证重新计算非客户区时子类已生效
        try:
            nc_ok = subclass_nccalcsize(window)
            steps.append(f"nccalc={nc_ok}")
        except Exception as exc:  # noqa: BLE001
            nc_ok = False
            steps.append(f"nccalc=ERR:{exc}")

        # 3) Win32 样式：标准窗口（含 WS_CAPTION）+ 边缘 resize + Aero Snap。
        #    清掉 WS_POPUP 让窗口成为标准覆盖窗口，DWM 才按常规窗口播放动画。
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        style_new = style
        style_new &= ~WS_POPUP
        style_new |= (
            WS_CAPTION | WS_SYSMENU | WS_THICKFRAME
            | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
        )
        user32.SetWindowLongW(hwnd, GWL_STYLE, style_new)
        user32.SetWindowPos(
            hwnd, 0, 0, 0, 0, 0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )
        steps.append(f"style=0x{style_new:08x} popup={(style & WS_POPUP) != 0}->{(style_new & WS_POPUP) != 0}")

        # 4) 保留 DWM 边框渲染（圆角/阴影/边框），显式请求 Win11 圆角。
        #    标题栏视觉由 WM_NCCALCSIZE→0 消除，不设 DWMNCRP_DISABLED
        corners_ok = enable_rounded_corners(window)
        steps.append(f"corners={corners_ok}")

        print(
            f"[shell] apply_frameless_native: hwnd=0x{hwnd:x} style=0x{style_new:08x} "
            f"corners={corners_ok} nccalc={nc_ok}",
            flush=True,
        )
        # 文件副作用：确认执行路径（windowed 下 stdout 不可靠）
        try:
            with open(
                os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "frameless-ok.txt"),
                "w",
                encoding="utf-8",
            ) as f:
                f.write(" ".join(steps) + "\n")
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        print(f"[shell] apply_frameless_native failed: {exc}", flush=True)


def run() -> None:
    frameless = _frameless_enabled()
    host = PyWebViewHost(frameless=frameless)
    startup_kb = _startup_kb_path()
    api = UIAPI(host=host, kb_path=startup_kb)
    if not UI_APP_INDEX.is_file():
        raise FileNotFoundError(f"UI 入口不存在: {UI_APP_INDEX}")

    window = webview.create_window(
        title=f"Memoria v{__version__}",
        url=create_app(),
        js_api=api,
        width=1280,
        height=860,
        min_size=(900, 600),
        frameless=frameless,
        easy_drag=False,
    )

    if frameless:
        # 窗口创建并显示后补原生样式（HWND / native 就绪后再执行）
        webview.start(lambda: _apply_frameless_native(window), debug=_debug_enabled())
    else:
        webview.start(debug=_debug_enabled())


def main() -> None:
    run()


if __name__ == "__main__":
    main()
