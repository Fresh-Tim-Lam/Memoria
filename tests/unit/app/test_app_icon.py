"""应用图标路径与 Windows AppUserModelID。"""

from __future__ import annotations

from pathlib import Path


def test_resolve_app_icon_prefers_resources_dir(tmp_path, monkeypatch):
    from memoria.app import runtime
    from memoria.app.shell import app_icon
    from memoria.presentation import paths

    root = tmp_path / "repo"
    icons = root / "resources" / "icons"
    icons.mkdir(parents=True)
    ico = icons / "Memoria.ico"
    ico.write_bytes(b"fake")

    monkeypatch.setattr(runtime, "resources_dir", lambda: root / "resources")
    monkeypatch.setattr(runtime, "install_root", lambda: tmp_path / "install")
    monkeypatch.setattr(runtime, "repo_root", lambda: root)
    monkeypatch.setattr(
        paths,
        "UI_APP_ICON",
        root / "missing" / "Memoria.ico",
    )

    assert app_icon.resolve_app_icon_path() == ico


def test_resolve_app_icon_falls_back_to_static(tmp_path, monkeypatch):
    from memoria.app import runtime
    from memoria.app.shell import app_icon
    from memoria.presentation import paths

    root = tmp_path / "repo"
    static = root / "src" / "memoria" / "ui" / "static" / "icons"
    static.mkdir(parents=True)
    bundled = static / "Memoria.ico"
    bundled.write_bytes(b"bundled")

    monkeypatch.setattr(runtime, "resources_dir", lambda: root / "resources")
    monkeypatch.setattr(runtime, "install_root", lambda: tmp_path / "install")
    monkeypatch.setattr(runtime, "repo_root", lambda: root)
    monkeypatch.setattr(paths, "UI_APP_ICON", bundled)

    assert app_icon.resolve_app_icon_path() == bundled


def test_configure_process_app_identity_noop_on_non_windows(monkeypatch):
    from memoria.app.shell import app_icon

    monkeypatch.setattr(app_icon.sys, "platform", "linux")
    app_icon.configure_process_app_identity()
