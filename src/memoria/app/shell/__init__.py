"""桌面壳选择与启动。"""

from __future__ import annotations

from memoria.app.runtime import resolve_shell_kind as _resolve_shell_kind


def resolve_shell_kind() -> str:
    return _resolve_shell_kind()


def launch_shell() -> None:
    kind = resolve_shell_kind()
    if kind == "pyqt6":
        from memoria.app.shell.pyqt6 import run

        run()
        return
    if kind in ("pywebview", "webview", ""):
        from memoria.app.shell.pywebview import run

        run()
        return
    raise ValueError(f"未知 MEMORIA_SHELL={kind!r}，可选: pywebview | pyqt6")


def main() -> None:
    launch_shell()


__all__ = ["launch_shell", "main", "resolve_shell_kind"]
