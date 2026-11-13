"""一键自动更新的准备层（不实际替换目录）。

helper 的真实文件操作在独立 PowerShell 中；本测试只钉住：
- 开发态不冒充支持；
- 未完成的 job 不被接受；
- result 读取不抛异常；
- no_window_kwargs 允许组合 detached flags。
"""

from __future__ import annotations

import json
import subprocess

import pytest

from memoria.services import update_auto
from memoria.util import proc


def test_auto_update_unsupported_in_dev() -> None:
    assert update_auto.auto_update_supported()["ok"] is False
    assert update_auto.auto_update_supported()["code"] == "unsupported_dev"


def test_prepare_auto_update_rejects_unknown_job(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(update_auto, "auto_update_supported", lambda: {"ok": True, "app_dir": "."})
    result = update_auto.prepare_auto_update("does-not-exist")
    assert result["status"] == "error"
    assert result["code"] == "unknown_job"


def test_get_auto_update_result_none_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(update_auto, "_auto_result_path", lambda: tmp_path / "missing.json")
    assert update_auto.get_auto_update_result() is None


def test_get_auto_update_result_reads_json(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    path = tmp_path / "update-result.json"
    payload = {"status": "success", "to_version": "0.4.15"}
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(update_auto, "_auto_result_path", lambda: path)
    assert update_auto.get_auto_update_result() == payload


def test_no_window_kwargs_can_add_detached_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(proc, "_is_windows", lambda: True)
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", proc.CREATE_NO_WINDOW, raising=False)
    flags = proc.no_window_kwargs(extra_flags=0x00000008 | 0x00000200)
    assert flags["creationflags"] & proc.CREATE_NO_WINDOW
    assert flags["creationflags"] & 0x00000008
    assert flags["creationflags"] & 0x00000200
