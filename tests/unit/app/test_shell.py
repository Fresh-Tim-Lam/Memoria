"""桌面壳 WindowHost 与 M0API 窗口委托。"""

from __future__ import annotations

import sys

from memoria.app.shell import resolve_shell_kind
from memoria.presentation.api.m0 import M0API


class _FakeHost:
    kind = "fake"
    frameless = True

    def __init__(self) -> None:
        self.maximized = False
        self.calls: list[tuple] = []

    def pick_directory(self) -> str | None:
        self.calls.append(("pick_directory",))
        return "/tmp/kb"

    def minimize(self) -> None:
        self.calls.append(("minimize",))

    def close(self) -> None:
        self.calls.append(("close",))

    def resize(self, width: int, height: int, anchor: str) -> None:
        self.calls.append(("resize", width, height, anchor))

    def move_to(self, x: int, y: int) -> None:
        self.calls.append(("move_to", x, y))

    def toggle_maximize(self) -> bool:
        self.calls.append(("toggle_maximize",))
        self.maximized = not self.maximized
        return self.maximized

    def restore_from_drag(
        self, screen_x: float, screen_y: float, ratio_x: float
    ) -> tuple[int, int, int, int]:
        self.calls.append(("restore_from_drag", screen_x, screen_y, ratio_x))
        self.maximized = False
        return 10, 20, 800, 600


def test_resolve_shell_kind_default(monkeypatch):
    monkeypatch.delenv("MEMORIA_SHELL", raising=False)
    assert resolve_shell_kind() == "pywebview"


def test_resolve_shell_kind_pyqt6(monkeypatch):
    monkeypatch.setenv("MEMORIA_SHELL", "pyqt6")
    assert resolve_shell_kind() == "pyqt6"


def test_resolve_shell_kind_frozen_defaults_pyqt6(monkeypatch):
    monkeypatch.delenv("MEMORIA_SHELL", raising=False)
    monkeypatch.setattr("memoria.app.runtime.sys.frozen", True, raising=False)
    monkeypatch.setattr(
        "memoria.app.runtime.sys._MEIPASS",
        "C:/fake/_MEIPASS",
        raising=False,
    )
    assert resolve_shell_kind() == "pyqt6"


def test_runtime_mode_and_examples(tmp_path, monkeypatch):
    from memoria.app import runtime as rt

    monkeypatch.setattr(rt, "is_frozen", lambda: False)
    monkeypatch.setattr(rt, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(rt, "install_root", lambda: tmp_path)
    monkeypatch.setattr(
        rt,
        "resources_dir",
        lambda: tmp_path / "resources",
    )
    monkeypatch.delenv("MEMORIA_MODE", raising=False)
    assert rt.resolve_mode() == "dev"

    examples = tmp_path / "examples"
    examples.mkdir()
    assert rt.default_examples_dir() == examples

    rel = tmp_path / "resources" / "examples"
    rel.mkdir(parents=True)
    assert rt.default_examples_dir() == rel


def test_m0api_window_ops_delegate_to_host(tmp_path):
    host = _FakeHost()
    host.pick_directory = lambda: str(tmp_path)  # type: ignore[method-assign]
    api = M0API(host=host)

    chrome = api.get_window_chrome()
    assert chrome["status"] == "ok"
    assert chrome["frameless"] is True
    assert chrome["shell"] == "fake"

    assert api.window_minimize() == {"status": "ok"}
    res = api.window_toggle_maximize()
    assert res == {"status": "ok", "maximized": True}
    assert api.window_resize_to(1000, 700, "se") == {"status": "ok"}
    assert ("resize", 1000, 700, "se") in host.calls

    path = api.select_directory()
    assert path == str(tmp_path)


def test_m0api_without_host_returns_window_error():
    api = M0API(host=None)
    assert api.get_window_chrome()["frameless"] is False
    assert api.window_minimize()["status"] == "error"


def test_shell_log_disabled_by_default(monkeypatch):
    monkeypatch.delenv("MEMORIA_SHELL_LOG", raising=False)
    from memoria.app.shell import shell_log as sl

    sl._ENABLED = None  # noqa: SLF001
    assert sl.shell_log_enabled() is False


def test_shell_log_enabled_with_env(monkeypatch):
    monkeypatch.setenv("MEMORIA_SHELL_LOG", "1")
    from memoria.app.shell import shell_log as sl

    sl._ENABLED = None  # noqa: SLF001
    assert sl.shell_log_enabled() is True


def test_format_qt_window_state():
    from PyQt6.QtCore import Qt

    from memoria.app.shell.shell_log import format_qt_window_state

    assert format_qt_window_state(Qt.WindowState.WindowNoState) == "normal"
    assert "max" in format_qt_window_state(Qt.WindowState.WindowMaximized)


def test_geometry_needs_fix_detects_collapsed_height():
    from memoria.app.shell.pyqt6_hidden_chrome import _geometry_needs_fix

    class _Win:
        minimumHeight = lambda self: 600  # noqa: ARG005
        minimumWidth = lambda self: 900  # noqa: ARG005
        width = lambda self: 1280  # noqa: ARG005
        height = lambda self: 28  # noqa: ARG005
        isMaximized = lambda self: False  # noqa: ARG005
        isMinimized = lambda self: False  # noqa: ARG005

    assert _geometry_needs_fix(_Win(), (373, 113, 1296, 899)) is True


def test_geometry_needs_fix_ok_when_matching():
    from memoria.app.shell.pyqt6_hidden_chrome import _geometry_needs_fix

    class _Win:
        minimumHeight = lambda self: 600  # noqa: ARG005
        minimumWidth = lambda self: 900  # noqa: ARG005
        width = lambda self: 1296  # noqa: ARG005
        height = lambda self: 899  # noqa: ARG005
        isMaximized = lambda self: False  # noqa: ARG005
        isMinimized = lambda self: False  # noqa: ARG005

    assert _geometry_needs_fix(_Win(), (373, 113, 1296, 899)) is False


def test_bounds_sane_rejects_animation_strip():
    from memoria.app.shell.pyqt6_hidden_chrome import _bounds_sane

    class _Win:
        minimumHeight = lambda self: 600  # noqa: ARG005
        minimumWidth = lambda self: 900  # noqa: ARG005
        screen = lambda self: None  # noqa: ARG005

    assert _bounds_sane(_Win(), (320, 918, 1280, 28)) is False
    assert _bounds_sane(_Win(), (312, 55, 1296, 899)) is True


def test_ui_static_root_frozen(monkeypatch, tmp_path):
    import importlib

    static = tmp_path / "memoria" / "ui" / "static" / "m0"
    static.mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    import memoria.presentation.paths as paths

    importlib.reload(paths)
    assert paths.UI_STATIC_ROOT == tmp_path / "memoria" / "ui" / "static"
    importlib.reload(paths)


def test_size_move_defers_chrome_refresh():
    from memoria.app.shell.pyqt6_hidden_chrome import (
        _notify_live_resize_if_changed,
        _set_size_move_active,
        _size_move_active,
        schedule_refresh_window_chrome,
    )

    class _Win:
        _memoria_size_move_active = False
        _memoria_chrome_refresh_timer = None
        _memoria_live_wh = None

    win = _Win()
    assert _size_move_active(win) is False
    _set_size_move_active(win, True)
    assert _size_move_active(win) is True
    schedule_refresh_window_chrome(win)
    assert win._memoria_chrome_refresh_timer is None

    class _Page:
        calls = 0

        def runJavaScript(self, _script: str) -> None:
            self.calls += 1

    class _View:
        page = lambda self: _Page()  # noqa: E731

    class _Win2:
        _memoria_size_move_active = True
        _memoria_live_wh = None

        def centralWidget(self):
            return _View()

    w2 = _Win2()
    _notify_live_resize_if_changed(w2, 100, 200)
    _notify_live_resize_if_changed(w2, 100, 200)
    _notify_live_resize_if_changed(w2, 101, 200)
    assert w2._memoria_live_wh == (101, 200)


def test_refresh_web_content_dispatches_resize_js(monkeypatch):
    from memoria.app.shell.pyqt6_hidden_chrome import refresh_web_content

    monkeypatch.setattr(
        "memoria.app.shell.pyqt6_hidden_chrome.shell_log_window",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "memoria.app.shell.pyqt6_hidden_chrome.ensure_web_view_geometry",
        lambda _w: None,
    )

    class _Page:
        scripts: list[str] = []

        def runJavaScript(self, script: str) -> None:
            self.scripts.append(script)

    page = _Page()

    class _Geo:
        def width(self):
            return 800

        def height(self):
            return 600

    class _View:
        def updateGeometry(self) -> None:
            pass

        def update(self) -> None:
            pass

        def geometry(self):
            return _Geo()

        page = lambda self: page  # noqa: E731

    class _Win:
        def isMinimized(self):
            return False

        def width(self):
            return 1280

        def height(self):
            return 860

        def centralWidget(self):
            return _View()

    refresh_web_content(_Win())
    assert any("resize" in s for s in page.scripts)


def test_schedule_post_iconic_web_sync(monkeypatch):
    from memoria.app.shell.pyqt6_hidden_chrome import _schedule_post_iconic_web_sync

    iconic: list[int] = []
    bursts: list[str] = []

    monkeypatch.setattr(
        "memoria.app.shell.pyqt6_hidden_chrome.schedule_force_iconic_restore",
        lambda _w, *, delay_ms=200: iconic.append(delay_ms),
    )
    monkeypatch.setattr(
        "memoria.app.shell.pyqt6_hidden_chrome.schedule_finalize_burst",
        lambda _w, *, reason="", commit_bounds=False: bursts.append(reason),
    )

    class _Win:
        _memoria_iconic_attempt = 99

    win = _Win()
    _schedule_post_iconic_web_sync(win)
    assert win._memoria_iconic_attempt == 0
    assert getattr(win, "_memoria_was_minimized") is False
    assert iconic == [80]
    assert bursts == ["restore_from_min"]


def test_force_iconic_restore_retries_while_minimized(monkeypatch):
    from memoria.app.shell.pyqt6_hidden_chrome import _run_force_iconic_restore

    scheduled: list[int] = []

    monkeypatch.setattr(
        "memoria.app.shell.pyqt6_hidden_chrome.schedule_force_iconic_restore",
        lambda _w, *, delay_ms=200: scheduled.append(delay_ms),
    )
    monkeypatch.setattr(
        "memoria.app.shell.pyqt6_hidden_chrome.shell_log_window",
        lambda *args, **kwargs: None,
    )

    class _Win:
        _memoria_iconic_attempt = 0

        def isMinimized(self):
            return True

        def isMaximized(self):
            return False

    win = _Win()
    _run_force_iconic_restore(win)
    assert win._memoria_iconic_attempt == 1
    assert scheduled == [60]


def test_sync_web_during_restore_schedules_burst(monkeypatch):
    from memoria.app.shell.pyqt6_hidden_chrome import sync_web_content_after_state_change

    monkeypatch.setattr(
        "memoria.app.shell.pyqt6_hidden_chrome.shell_log_window",
        lambda *args, **kwargs: None,
    )
    bursts: list[str] = []

    monkeypatch.setattr(
        "memoria.app.shell.pyqt6_hidden_chrome.schedule_finalize_burst",
        lambda _w, *, reason="", commit_bounds=False: bursts.append(reason),
    )

    class _Win:
        _memoria_restore_active = True

        def isMinimized(self):
            return False

        def isMaximized(self):
            return False

    sync_web_content_after_state_change(_Win())
    assert bursts == ["restore_active"]


def test_finalize_window_layout_dispatches_resize(monkeypatch):
    from memoria.app.shell.pyqt6_hidden_chrome import finalize_window_layout

    monkeypatch.setattr(
        "memoria.app.shell.pyqt6_hidden_chrome.shell_log_window",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "memoria.app.shell.pyqt6_hidden_chrome.ensure_web_view_geometry",
        lambda _w: None,
    )
    monkeypatch.setattr(
        "memoria.app.shell.pyqt6_hidden_chrome.refresh_window_chrome",
        lambda _w: None,
    )

    class _Page:
        scripts: list[str] = []

        def runJavaScript(self, script: str) -> None:
            self.scripts.append(script)

    page = _Page()

    class _Geo:
        def width(self):
            return 800

        def height(self):
            return 600

    class _View:
        def updateGeometry(self) -> None:
            pass

        def update(self) -> None:
            pass

        def geometry(self):
            return _Geo()

        page = lambda self: page  # noqa: E731

    class _Win:
        def isMinimized(self):
            return False

        def width(self):
            return 1280

        def height(self):
            return 860

        def centralWidget(self):
            return _View()

    finalize_window_layout(_Win(), reason="exit_size_move")
    assert any("resize" in s for s in page.scripts)
