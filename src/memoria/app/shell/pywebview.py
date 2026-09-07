"""pywebview 桌面壳（开发默认）。"""

from __future__ import annotations

import os
import sys
import threading
import time

import webview

from memoria import __version__
from memoria.app.runtime import resolve_startup_kb_path
from memoria.app.shell.pywebview_host import PyWebViewHost
from memoria.presentation.api.ui import UIAPI
from memoria.presentation.paths import UI_APP_INDEX
from memoria.presentation.static_server import create_app


def _startup_kb_path() -> str | None:
    return resolve_startup_kb_path()


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
            _diag("apply_frameless native-not-ready")
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

        # 文件诊断：记录无边框改造执行的完整步骤（追加，勿覆盖 run 早期日志）
        _diag("apply_frameless " + " ".join(steps))
    except Exception as exc:  # noqa: BLE001
        _diag(f"apply_frameless failed: {exc}")


def _own_top_level_windows():
    """枚举本进程全部顶层窗口句柄（不依赖 pywebview window.native）。"""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    my_pid = int(kernel32.GetCurrentProcessId())

    handles: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lp):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == my_pid:
            handles.append(int(hwnd))
        return True

    user32.EnumWindows(_cb, 0)
    return handles


def _win_texts(hwnd: int) -> tuple[str, str]:
    """返回顶层窗口 (类名, 标题)，失败时 ('?', '')。"""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    title = ctypes.create_unicode_buffer(256)
    cls = ctypes.create_unicode_buffer(128)
    try:
        user32.GetWindowTextW(hwnd, title, 256)
        user32.GetClassNameW(hwnd, cls, 128)
    except Exception:  # noqa: BLE001
        return "?", ""
    return cls.value or "?", title.value or ""


def _own_main_windows() -> list[int]:
    """本进程中应用主窗口句柄：WindowsForms10 类 + 标题含 Memoria。

    只认 pywebview BrowserForm 主窗口；GDI+ Hook Window、.NET-Broadcast
    EventWindow、IME/MSCTF 等系统辅助窗口一律排除 —— 它们正常应保持
    隐藏，强制 Show 会把它们弹出成多余窗口。
    """
    out: list[int] = []
    for h in _own_top_level_windows():
        cls, title = _win_texts(h)
        if cls.startswith("WindowsForms10") and "Memoria" in title:
            out.append(h)
    return out


def _force_window_show(_native=None) -> bool:
    """兜底显示：只针对应用主窗口，绝不碰系统辅助窗口。

    native 可用则直接用其句柄（BrowserForm）；否则按
    WindowsForms10 + 标题含 Memoria 匹配主窗口。任一不可见主窗口
    Show(SW_SHOW)+置前即视为执行了 Show。
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]

    targets: list[int] = []
    if _native is not None:
        try:
            targets.append(int(_native.Handle.ToInt64()))
        except Exception:  # noqa: BLE001
            targets = []
    if not targets:
        targets = _own_main_windows()

    shown_any = False
    for hwnd in targets:
        h = ctypes.c_void_p(hwnd)
        try:
            if not user32.IsWindowVisible(h):
                user32.ShowWindow(h, 5)  # SW_SHOW
                user32.SetForegroundWindow(h)
                shown_any = True
        except Exception:  # noqa: BLE001
            continue
    return shown_any


def _diag_path() -> str:
    """诊断文件路径：发布态为 exe 同目录 frameless-ok.txt（windowed 下 stdout 不可靠）。"""
    return os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "frameless-ok.txt")


def _diag_clear() -> None:
    """清空旧诊断，保证本次运行从头记录。"""
    try:
        if os.path.exists(_diag_path()):
            os.remove(_diag_path())
    except Exception:  # noqa: BLE001
        pass


def _write_diag(line: str) -> None:
    """追加一行诊断到文件（仅落盘，供发布态排查；永不抛错）。"""
    try:
        with open(_diag_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:  # noqa: BLE001
        pass


def _diag(line: str) -> None:
    """统一诊断出口：发布态落盘；开发态同时打印到控制台。"""
    _write_diag(line)
    if _debug_enabled():
        try:
            print(f"[shell] {line}", flush=True)
        except Exception:  # noqa: BLE001
            pass


def _ensure_window_visible(window) -> None:
    """启动后即时兜底（一次）：尽量 Show 本进程窗口并落诊断。"""
    native = None
    for _ in range(40):
        native = window.native
        if native is not None:
            break
        time.sleep(0.25)
    _diag(f"ensure_visible native_ok={native is not None}")
    shown = _force_window_show(native)
    _diag(f"ensure_visible executed_show={shown}")


def _watch_window_visible(window) -> None:
    """守护线程兜底（修复打包态"后台进程无窗口"）。

    注意：不要在这里调 window.show() —— pywebview 的 show() 被 @_shown_call
    包装，内部会 events.shown.wait(20)；一旦窗口因故障从未 shown，show() 会
    阻塞 20 秒，使兜底轮询失效。这里只走纯 Win32（EnumWindows + ShowWindow），
    不依赖 shown 事件，且只针对应用主窗口（WindowsForms10 + Memoria 标题），
    绝不 Show GDI+/Broadcast/IME 等系统辅助窗口。每 0.5s 轮询：主窗口出现且
    不可见 → 强制 Show+置前并结束；主窗口可见（正常态）→ 立即结束；40s 仍
    无主窗口 → 落结论行（说明 create_window 阶段就失败，需看 run 早期诊断）。
    """
    import time as _t

    _diag("watch start")
    for i in range(80):
        _t.sleep(0.5)
        if not _own_main_windows():
            continue  # 主窗口尚未创建，继续等
        # 存在不可见主窗口 → 已执行 Show（_force_window_show 返回 True）
        if _force_window_show(None):
            _diag(f"watch forced_shown=1 t={(i + 1) // 2}s")
            return
        # 主窗口已可见 → 正常，无需兜底
        _diag(f"watch main_visible t={(i + 1) // 2}s")
        return
    _diag("watch no-main-window t=40s")


def _own_window_info() -> list[str]:
    """自进程顶层窗口摘要：[hwnd:class:visible:title]（不依赖 window.native）。"""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]

    out: list[str] = []
    for h in _own_top_level_windows():
        try:
            cls, title = _win_texts(h)
            vis = int(user32.IsWindowVisible(ctypes.c_void_p(h)))
            out.append(f"0x{h:x}:{cls}:vis={vis}:{title}")
        except Exception:  # noqa: BLE001
            continue
    return out


def _post_launch_log(stage: str) -> None:
    """阶段日志：开发态打印，发布态落盘 frameless-ok.txt。"""
    try:
        _diag(f"post_launch:{stage} own={_own_window_info()}")
    except Exception as exc:  # noqa: BLE001
        _diag(f"post_launch:{stage} log-err {exc}")


def _start_dev_window_monitor(window) -> None:
    """开发态窗口显示链路监视器：每秒打印 native/gui/shown 事件与自进程窗口状态。

    定位 pywebview 窗口"创建但不可见"：shown 事件是否触发、native/gui 是否就绪、
    顶层窗口是否带 WS_VISIBLE。打包态不打印（走 frameless-ok.txt 文件诊断）。
    """
    if not _debug_enabled():
        return

    def _run() -> None:
        for i in range(45):
            try:
                native_ok = window.native is not None
                gui_ok = getattr(window, "gui", None) is not None
                shown_evt = "?"
                try:
                    shown_evt = bool(window.events.shown.is_set())
                except Exception:  # noqa: BLE001
                    pass
                wins = _own_window_info()
                print(
                    f"[shell] mon t={i}s native={int(native_ok)} gui={int(gui_ok)} "
                    f"shown_evt={shown_evt} own={wins}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[shell] mon err {exc}", flush=True)
            time.sleep(1)

    threading.Thread(target=_run, daemon=True).start()


def _disable_browser_accelerator_keys(window) -> None:
    """关闭 WebView2 浏览器级加速键（Ctrl+= / Ctrl+- / Ctrl+0 等）。

    pywebview 将 AreBrowserAcceleratorKeysEnabled 直接绑定 debug 标志：
    开发态 debug=True → WebView2 自身拦截 Ctrl+= 等按键做页面缩放，
    keydown 不再派发到页面，应用缩放快捷键因此失效。关闭后按键事件
    交还给页面（app.js 自行处理 Ctrl+= 缩放快捷键）；打包态 debug=False
    本就关闭，此函数无副作用。
    """
    native = None
    for _ in range(30):
        native = window.native
        if native is not None:
            break
        time.sleep(0.25)
    if native is None:
        return

    # WebView2 控件在 pywebview 各版本的暴露位置不同（native.webview /
    # native.browser.webview）；pythonnet 跨线程代理可能不暴露 Python 侧
    # 附加属性，统一多级兼容解析。找不到则静默跳过（页面自行处理缩放键）。
    webview2 = None
    for _getter in (
        lambda n: n.webview,
        lambda n: n.browser.webview,
        lambda n: getattr(n, "CoreWebView2", None),
    ):
        try:
            webview2 = _getter(native)
            if webview2 is not None:
                break
        except Exception:  # noqa: BLE001
            continue
    if webview2 is None:
        return

    try:
        # CoreWebView2 只能在 UI 线程访问；pywebview 的 start(func) 中 func
        # 运行在非 UI 线程，直接读取会抛 InvalidCastException，须 Invoke 调度。
        # 注意不能在 UI 线程 sleep 轮询：CoreWebView2 初始化回调也要在 UI 线程
        # 派发，阻塞 UI 会形成死锁导致窗口白屏。改用初始化完成事件驱动。
        from System import Action  # pythonnet

        def _on_initialized(sender, args):
            try:
                core = webview2.CoreWebView2
                if core is not None:
                    core.Settings.AreBrowserAcceleratorKeysEnabled = False
            except Exception:  # noqa: BLE001
                pass

        def _try_set() -> None:
            core = None
            try:
                core = webview2.CoreWebView2
            except Exception:  # noqa: BLE001
                return
            if core is not None:
                try:
                    core.Settings.AreBrowserAcceleratorKeysEnabled = False
                except Exception:  # noqa: BLE001
                    pass
            else:
                # 初始化未完成：挂事件，就绪时回调（幂等，不阻塞 UI）
                try:
                    webview2.CoreWebView2InitializationCompleted += _on_initialized
                except Exception:  # noqa: BLE001
                    pass

        if native.InvokeRequired:
            native.Invoke(Action(_try_set))
        else:
            _try_set()
    except Exception as exc:  # noqa: BLE001
        print(f"[shell] disable_browser_accelerator_keys failed: {exc}", flush=True)


def run() -> None:
    frameless = _frameless_enabled()
    # 本次运行诊断从头记录（发布态落地 Package/frameless-ok.txt）
    _diag_clear()
    _diag(
        f"run enter frameless={frameless} frozen={getattr(sys, 'frozen', False)} "
        f"webview={webview.__file__}"
    )
    host = PyWebViewHost(frameless=frameless)
    startup_kb = _startup_kb_path()
    api = UIAPI(host=host, kb_path=startup_kb)
    if not UI_APP_INDEX.is_file():
        _diag(f"run ui-index-missing {UI_APP_INDEX}")
        raise FileNotFoundError(f"UI 入口不存在: {UI_APP_INDEX}")
    _diag(f"run ui-ready kb={startup_kb}")

    window = webview.create_window(
        title=f"Memoria v{__version__}",
        url=create_app(),
        js_api=api,
        width=1280,
        height=860,
        min_size=(900, 600),
        frameless=frameless,
        easy_drag=False,
        # pywebview 默认 text_select=False 会注入 body{-webkit-user-select:none}，
        # Chromium 下该样式会阻止 <input type=range> 拖拽（滑块 input 事件不触发），
        # 设置面板的字号/缩放滑块因此无响应；应用 CSS 已自行管理 user-select 策略
        text_select=True,
    )
    _diag(
        f"run created_window native={window.native is not None} "
        f"gui={getattr(window, 'gui', None) is not None}"
    )

    def _post_launch(window_):
        _post_launch_log("enter")
        _disable_browser_accelerator_keys(window_)
        _post_launch_log("after_disable_keys")
        if frameless:
            # 窗口创建并显示后补原生样式（HWND / native 就绪后再执行）
            _apply_frameless_native(window_)
            _post_launch_log("after_frameless")
        # 兜底：确保主窗口可见并置前（打包态偶发"后台进程无窗口"）
        _ensure_window_visible(window_)
        _post_launch_log("after_ensure_visible")

    _start_dev_window_monitor(window)
    # 守护线程：native 就绪晚时仍能强制显示窗口（打包态排查/修复用）。
    # 注意该线程与 _post_launch 均不依赖 shown 事件，避免故障态下阻塞。
    _diag("run start watch-thread")
    threading.Thread(target=_watch_window_visible, args=(window,), daemon=True).start()

    _diag("run webview.start begin")
    webview.start(lambda: _post_launch(window), debug=_debug_enabled())


def main() -> None:
    run()


if __name__ == "__main__":
    main()
