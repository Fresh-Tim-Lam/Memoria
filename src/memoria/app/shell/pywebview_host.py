"""pywebview 窗口宿主（开发默认）。"""

from __future__ import annotations

import sys

import webview

from memoria.app.window_win32 import apply_bounds, maximize_to_work_area, read_bounds


class PyWebViewHost:
    kind = "pywebview"

    def __init__(self, *, frameless: bool = False) -> None:
        self.frameless = frameless
        self._maximized = False
        self._saved_bounds: tuple[int, int, int, int] | None = None

    @property
    def maximized(self) -> bool:
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

    def minimize(self) -> None:
        window = self._window()
        if window is None:
            raise RuntimeError("窗口不可用")
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
        if self._maximized:
            raise RuntimeError("已最大化")
        window = self._window()
        if window is None:
            raise RuntimeError("窗口不可用")
        px, py = int(x), int(y)
        if sys.platform == "win32" and self.frameless:
            bounds = read_bounds(window)
            if bounds:
                _, _, w, h = bounds
                apply_bounds(window, px, py, w, h)
            else:
                window.move(px, py)
        else:
            window.move(px, py)

    def toggle_maximize(self) -> bool:
        window = self._window()
        if window is None:
            raise RuntimeError("窗口不可用")

        if sys.platform == "win32" and self.frameless:
            if self._maximized:
                if self._saved_bounds:
                    x, y, w, h = self._saved_bounds
                    apply_bounds(window, x, y, w, h)
                else:
                    window.restore()
                self._maximized = False
            else:
                bounds = read_bounds(window)
                if bounds:
                    self._saved_bounds = bounds
                window.restore()
                if not maximize_to_work_area(window):
                    window.maximize()
                self._maximized = True
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
            w, h = 1280, 860
        px = int(float(screen_x) - ratio * w)
        py = int(float(screen_y) - titlebar_y)

        if sys.platform == "win32" and self.frameless:
            apply_bounds(window, px, py, w, h)
        else:
            window.restore()
            window.move(px, py)
            window.resize(w, h)
        self._maximized = False
        return px, py, w, h

    def start_move(self) -> None:
        _ = self
