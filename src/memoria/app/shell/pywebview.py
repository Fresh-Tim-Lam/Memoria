"""pywebview 桌面壳（开发默认）。"""

from __future__ import annotations

import os

import webview

from memoria.app.shell.pywebview_host import PyWebViewHost
from memoria.presentation.api.m0 import M0API
from memoria.presentation.paths import UI_M0_INDEX
from memoria.presentation.static_server import create_app
from memoria.storage.ui_settings import resolve_last_kb_path


def _startup_kb_path() -> str | None:
    return resolve_last_kb_path()


def _frameless_enabled() -> bool:
    return os.environ.get("MEMORIA_FRAMELESS", "1").lower() not in ("0", "false", "no")


def _debug_enabled() -> bool:
    return os.environ.get("MEMORIA_DEBUG", "1").lower() not in ("0", "false", "no")


def run() -> None:
    frameless = _frameless_enabled()
    host = PyWebViewHost(frameless=frameless)
    startup_kb = _startup_kb_path()
    api = M0API(host=host, kb_path=startup_kb)

    if not UI_M0_INDEX.is_file():
        raise FileNotFoundError(f"UI 入口不存在: {UI_M0_INDEX}")

    webview.create_window(
        title="Memoria M1",
        url=create_app(),
        js_api=api,
        width=1280,
        height=860,
        min_size=(900, 600),
        frameless=frameless,
        easy_drag=False,
    )

    webview.start(debug=_debug_enabled())


def main() -> None:
    run()


if __name__ == "__main__":
    main()
