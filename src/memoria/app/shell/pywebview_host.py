"""pywebview 窗口宿主（开发默认）。"""

from __future__ import annotations

import sys

import webview

from memoria.app.window_win32 import (
    begin_caption_drag,
    dpi_scale,
    is_maximized,
    move_window,
    normal_bounds,
    show_window_state,
    start_system_drag,
)


class PyWebViewHost:
    kind = "pywebview"

    def __init__(self, *, frameless: bool = False) -> None:
        self.frameless = frameless
        self._maximized = False
        self._saved_bounds: tuple[int, int, int, int] | None = None

    @property
    def maximized(self) -> bool:
        # 读取真实窗口状态（用户可能通过 Aero Snap / 系统命令最大化）
        if sys.platform == "win32":
            window = self._window()
            if window is not None:
                cur = is_maximized(window)
                if cur is not None:
                    self._maximized = cur
        return self._maximized

    def _window(self):
        return webview.windows[0] if webview.windows else None

    def pick_directory(self) -> str | None:
        window = self._window()
        if window is None:
            return None
        result = window.create_file_dialog(webview.FileDialog.FOLDER)
        if result:
            return result[0]
        return None

    def pick_import_files(self) -> list[str]:
        window = self._window()
        if window is None:
            return []
        result = window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=True,
            file_types=("Text Files (*.txt;*.md)", "All Files (*.*)"),
        )
        return list(result) if result else []

    def minimize(self) -> None:
        window = self._window()
        if window is None:
            raise RuntimeError("窗口不可用")
        if sys.platform == "win32":
            # ShowWindow(SW_MINIMIZE)：直接走系统状态机，触发 DWM 原生
            # 最小化动画（窗口向下渐变飞向任务栏），绕过 WinForms 拦截
            if not show_window_state(window, 6):  # SW_MINIMIZE
                raise RuntimeError("窗口不可用")
            return
        window.minimize()

    def close(self) -> None:
        window = self._window()
        if window is None:
            raise RuntimeError("窗口不可用")
        window.destroy()

    def resize(self, width: int, height: int, anchor: str) -> None:
        if self._maximized:
            raise RuntimeError("已最大化，无法调整大小")
        window = self._window()
        if window is None:
            raise RuntimeError("窗口不可用")
        from webview.window import FixPoint

        anchors = {
            "n": FixPoint.SOUTH | FixPoint.WEST | FixPoint.EAST,
            "s": FixPoint.NORTH | FixPoint.WEST | FixPoint.EAST,
            "e": FixPoint.NORTH | FixPoint.SOUTH | FixPoint.WEST,
            "w": FixPoint.NORTH | FixPoint.SOUTH | FixPoint.EAST,
            "nw": FixPoint.SOUTH | FixPoint.EAST,
            "ne": FixPoint.SOUTH | FixPoint.WEST,
            "sw": FixPoint.NORTH | FixPoint.EAST,
            "se": FixPoint.NORTH | FixPoint.WEST,
        }
        fix = anchors.get(str(anchor or "se"), FixPoint.NORTH | FixPoint.WEST)
        window.resize(int(width), int(height), fix)

    def move_to(self, x: int, y: int) -> None:
        # 实时读取真实最大化状态（Aero Snap / 原生拖动还原后缓存可能过期）
        if self.maximized:
            raise RuntimeError("已最大化")
        window = self._window()
        if window is None:
            raise RuntimeError("窗口不可用")
        if sys.platform == "win32" and self.frameless:
            # 前端 screenX/screenY 为 DIP，SetWindowPos 需物理像素
            scale = dpi_scale(window)
            px = int(int(x) * scale)
            py = int(int(y) * scale)
            if not move_window(window, px, py):
                raise RuntimeError("窗口不可用")
        else:
            window.move(int(x), int(y))

    def toggle_maximize(self) -> bool:
        window = self._window()
        if window is None:
            raise RuntimeError("窗口不可用")

        if sys.platform == "win32":
            # ShowWindow(SW_MAXIMIZE / SW_RESTORE)：直接走系统状态机，
            # 触发 DWM 原生最大化/还原动画 + 自动避开任务栏；状态实时读取
            cur = bool(is_maximized(window))
            cmd = 3 if not cur else 9  # SW_MAXIMIZE / SW_RESTORE
            if not show_window_state(window, cmd):
                raise RuntimeError("窗口不可用")
            self._maximized = not cur
            return self._maximized

        if self._maximized:
            window.restore()
            self._maximized = False
        else:
            window.maximize()
            self._maximized = True
        return self._maximized

    def restore_from_drag(
        self, screen_x: float, screen_y: float, ratio_x: float
    ) -> tuple[int, int, int, int]:
        if not self._maximized:
            if self._saved_bounds:
                x, y, w, h = self._saved_bounds
                return x, y, w, h
            return 0, 0, 1280, 860

        window = self._window()
        if window is None:
            raise RuntimeError("窗口不可用")

        ratio = max(0.0, min(1.0, float(ratio_x)))
        titlebar_y = 17
        if self._saved_bounds:
            _, _, w, h = self._saved_bounds
        else:
            nb = normal_bounds(window) if sys.platform == "win32" else None
            w, h = (nb[2], nb[3]) if nb else (1280, 860)
        scale = dpi_scale(window) if sys.platform == "win32" else 1.0
        px = int(float(screen_x) * scale - ratio * w)
        py = int(float(screen_y) * scale - titlebar_y)

        if sys.platform == "win32" and self.frameless:
            # 先还原（触发还原动画）再定位到鼠标，否则最大化状态下 SetWindowPos 无效
            show_window_state(window, 9)  # SW_RESTORE
            move_window(window, px, py)
        else:
            window.restore()
            window.move(px, py)
            window.resize(w, h)
        self._maximized = False
        # JS 端用 DIP 计算（e.screenX 为 DIP），统一返回 DIP 数值
        return int(px / scale), int(py / scale), int(w / scale), int(h / scale)

    def start_move(self) -> None:
        """系统级窗口拖动（ReleaseCapture + WM_NCLBUTTONDOWN HTCAPTION）：
        无边框窗口获得原生拖动体验，Aero Snap 生效。"""
        window = self._window()
        if window is None:
            return
        if sys.platform != "win32":
            return
        start_system_drag(window)

    def begin_drag(self) -> None:
        """前端检测到标题栏拖拽动作后调用：PostMessage 给窗口，由 WndProc
        （UI 线程）发起原生标题栏拖动（ReleaseCapture + WM_NCLBUTTONDOWN
        HTCAPTION），鼠标捕获 / Aero Snap / 最大化下拉还原全部原生处理。"""
        window = self._window()
        if window is None:
            return
        if sys.platform != "win32":
            return
        begin_caption_drag(window)
