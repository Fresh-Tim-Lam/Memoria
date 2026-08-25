"""桌面应用启动入口（按 MEMORIA_SHELL 选择壳）。"""

from __future__ import annotations

import sys

from memoria.app.shell import launch_shell


class _SafeStream:
    """UTF-8 容错输出流：frozen/windowed 下 stdout/stderr 编码为 cp1252
    且不可 reconfigure，print 中文会 UnicodeEncodeError 导致启动崩溃；
    此流固定 UTF-8 + 写失败静默丢弃，永不出错。"""

    def __init__(self, real=None):
        self._real = real

    def write(self, s):
        if s is None:
            return 0
        if self._real is not None:
            try:
                self._real.write(s)
            except Exception:
                pass
        return len(s)

    def flush(self):
        if self._real is not None:
            try:
                self._real.flush()
            except Exception:
                pass

    def reconfigure(self, **kwargs):  # noqa: ARG002
        pass

    def isatty(self):
        return False

    def writable(self):
        return True

    @property
    def encoding(self):
        return "utf-8"


def _force_utf8_stdio() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        try:
            if stream is not None:
                stream.reconfigure(encoding="utf-8", errors="replace")
                continue
        except Exception:
            pass
        # windowed 模式 stdout/stderr 不可 reconfigure：替换为容错流
        try:
            setattr(sys, name, _SafeStream(stream))
        except Exception:
            pass


def _set_dpi_awareness() -> None:
    """创建任何窗口前强制抬升进程 DPI 感知为 PerMonitorV2。

    打包态 exe 的清单缺 dpiAwareness 声明 → 进程以 DPI 不感知启动，
    WinForms/IFileDialog 等系统对话框按 96dpi 逻辑尺寸绘制后被系统
    虚拟放大，高缩放（150%/200%）下文件夹选择对话框会占满整个屏幕。
    开发态由 WebView2 初始化时抬升，故表现正常。此处统一在启动最早
    处设置，覆盖开发态与打包态；若已由清单/WebView2 设置则调用失败，
    无害忽略。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
        user32.SetProcessDpiAwarenessContext.argtypes = [wintypes.HANDLE]

        # PER_MONITOR_AWARE_V2 = -4（Win10 1703+）
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
        # 回退：PROCESS_PER_MONITOR_DPI_AWARE = 2（Win8.1+）
        shcore = ctypes.windll.shcore
        shcore.SetProcessDpiAwareness.restype = wintypes.HRESULT
        shcore.SetProcessDpiAwareness.argtypes = [ctypes.c_int]
        if shcore.SetProcessDpiAwareness(2) == 0:
            return
        # 最终回退：SetProcessDPIAware()（Vista+）
        user32.SetProcessDPIAware()
    except Exception:  # noqa: BLE001  DPI 设置失败不影响启动
        pass


def main() -> None:
    _set_dpi_awareness()
    _force_utf8_stdio()
    launch_shell()


if __name__ == "__main__":
    main()
