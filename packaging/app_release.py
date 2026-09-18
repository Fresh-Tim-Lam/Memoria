"""PyInstaller 入口：默认 pywebview 发布壳（WebView2）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("MEMORIA_SHELL", "pywebview")
os.environ.setdefault("MEMORIA_MODE", "release")

_root = Path(__file__).resolve().parents[1]
_src = _root / "src"
if _src.is_dir() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from memoria.app.desktop import main


def _crash_log_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "crash.log")


def _dump_crash_log() -> None:
    """windowed 模式 stderr 不可见，异常写入 exe 同目录 crash.log 便于定位。"""
    import traceback

    try:
        with open(_crash_log_path(), "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
    except Exception:
        pass


def _show_fatal_dialog() -> None:
    """启动失败时给一个可读弹窗——windowed 模式双击运行看不到任何输出，
    裸栈等于“闪一下就没了”。仅发布态需要；开发态控制台已可见。"""
    import ctypes
    import traceback

    lines = ["Memoria 启动失败，无法继续运行。", "", f"错误详情：{_crash_log_path()}"]
    if "Python.Runtime.Loader.Initialize" in traceback.format_exc():
        lines += [
            "",
            "原因：Windows 把随包 .NET 运行时标记为“来自网络”并阻止加载。",
            "处理：在解压目录用 PowerShell 执行一次",
            "      Get-ChildItem -Recurse | Unblock-File",
            "然后重新运行 Memoria.exe。",
        ]
    try:
        ctypes.windll.user32.MessageBoxW(
            0,
            "\n".join(lines),
            "Memoria — 启动失败",
            0x10 | 0x10000 | 0x40000,  # ICONERROR | SETFOREGROUND | TOPMOST
        )
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        _dump_crash_log()
        _show_fatal_dialog()
        raise
