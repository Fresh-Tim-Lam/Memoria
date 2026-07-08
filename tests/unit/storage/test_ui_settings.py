"""UI 设置磁盘持久化测试。"""

from __future__ import annotations

import json

from memoria.storage import ui_settings


def test_save_and_load_ui_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_settings, "_settings_dir", lambda: tmp_path)
    assert ui_settings.load_ui_settings() == {}

    merged = ui_settings.save_ui_settings(
        {
            "graph": {"labelMaxLen": 12, "repulsion": 6000},
            "sidebarSplit": {"files": 0.6, "graph2d": 0.8},
        }
    )
    assert merged["graph"]["labelMaxLen"] == 12
    assert merged["sidebarSplit"]["graph2d"] == 0.8

    again = ui_settings.save_ui_settings({"graph": {"linkDistance": 120}})
    assert again["graph"]["labelMaxLen"] == 12
    assert again["graph"]["linkDistance"] == 120

    loaded = ui_settings.load_ui_settings()
    assert loaded == again
    raw = json.loads((tmp_path / "ui-settings.json").read_text(encoding="utf-8"))
    assert raw["graph"]["linkDistance"] == 120


def test_remember_and_resolve_last_kb_path(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_settings, "_settings_dir", lambda: tmp_path)
    kb = tmp_path / "my-kb"
    kb.mkdir()

    assert ui_settings.resolve_last_kb_path() is None
    ui_settings.remember_last_kb_path(str(kb))
    assert ui_settings.resolve_last_kb_path() == str(kb.resolve())

    ui_settings.remember_last_kb_path(None)
    assert ui_settings.resolve_last_kb_path() is None
    assert ui_settings.load_ui_settings()["last_kb_path"] == ""


def test_settings_dir_defaults_to_install_root(tmp_path, monkeypatch):
    fake_root = tmp_path / "Package"
    fake_root.mkdir()
    monkeypatch.setattr(
        "memoria.app.runtime.install_root",
        lambda: fake_root,
    )
    monkeypatch.delenv("MEMORIA_CONFIG_DIR", raising=False)
    assert ui_settings.settings_path() == fake_root / "config" / "ui-settings.json"


def test_migrate_legacy_home_settings(tmp_path, monkeypatch):
    fake_root = tmp_path / "Package"
    fake_root.mkdir()
    legacy_dir = tmp_path / "legacy_home" / ".memoria"
    legacy_dir.mkdir(parents=True)
    legacy_dir.joinpath("ui-settings.json").write_text(
        '{"last_kb_path": "D:/kb"}', encoding="utf-8"
    )
    monkeypatch.setattr(
        "memoria.app.runtime.install_root",
        lambda: fake_root,
    )
    monkeypatch.setattr(ui_settings, "_legacy_settings_path", lambda: legacy_dir / "ui-settings.json")
    monkeypatch.delenv("MEMORIA_CONFIG_DIR", raising=False)

    loaded = ui_settings.load_ui_settings()
    assert loaded["last_kb_path"] == "D:/kb"
    assert (fake_root / "config" / "ui-settings.json").is_file()


def test_resolve_last_kb_path_missing_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_settings, "_settings_dir", lambda: tmp_path)
    ui_settings.remember_last_kb_path(str(tmp_path / "gone"))
    assert ui_settings.resolve_last_kb_path() is None
