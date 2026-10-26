"""task-180：版本更新机制后端单测（不联网；用注入 opener/假 response 证明纪律）。"""

from __future__ import annotations

import hashlib
import io
import json
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

import pytest

from memoria.services import update as upd


def _release(tag: str = "v0.4.10", *, lite_bytes: int = 350, full_bytes: int = 1180) -> dict:
    return {
        "tag_name": tag,
        "published_at": "2026-10-26T00:00:00Z",
        "body": "修复若干问题\n- update mechanism",
        "html_url": f"https://github.com/Fresh-Tim-Lam/Memoria/releases/tag/{tag}",
        "assets": [
            {
                "name": f"Memoria-{tag}-win64.zip",
                "size": full_bytes,
                "browser_download_url": f"https://github.com/Fresh-Tim-Lam/Memoria/releases/download/{tag}/full.zip",
                "digest": "sha256:" + "a" * 64,
            },
            {
                "name": f"Memoria-{tag}-win64-lite.zip",
                "size": lite_bytes,
                "browser_download_url": f"https://github.com/Fresh-Tim-Lam/Memoria/releases/download/{tag}/lite.zip",
            },
        ],
    }


def _zip_bytes(tmp_path: Path, *, version: str = "0.4.10", tamper: bool = False) -> bytes:
    """构造包含 release-manifest.json 的最小发布 zip。"""
    files = {
        "VERSION": version.encode(),
        "Memoria.exe": b"exe-bytes",
        "README.txt": b"readme",
    }
    manifest = {
        "schema": "memoria-release-manifest/v1",
        "format_version": 1,
        "version": version,
        "built_at": "2026-10-26T00:00:00Z",
        "asset": {"name": f"Memoria-v{version}-win64-lite.zip", "bytes": 0},
        "layout": {"required": [], "optional": [], "forbidden": []},
        "files": [
            {
                "path": name,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            }
            for name, data in files.items()
        ],
    }
    write_files = dict(files)
    if tamper:
        write_files["Memoria.exe"] = b"exe-TAMPERED"  # 清单仍按原内容算 ⇒ 校验必须红
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in write_files.items():
            zf.writestr(name, data)
        zf.writestr("release-manifest.json", json.dumps(manifest, ensure_ascii=False))
    return out.getvalue()


class _FakeResponse:
    def __init__(self, data: bytes, *, chunk_delay: float = 0.0, content_length: bool = True):
        self._data = data
        self._pos = 0
        self._delay = chunk_delay
        self.headers = {"Content-Length": str(len(data))} if content_length else {}

    def read(self, n: int = -1) -> bytes:
        if self._delay:
            time.sleep(self._delay)
        if self._pos >= len(self._data):
            return b""
        end = len(self._data) if n < 0 else min(self._pos + n, len(self._data))
        chunk = self._data[self._pos : end]
        self._pos = end
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# ── ① 检查更新 ─────────────────────────────────────────────────────────────


def test_outbound_disabled_makes_zero_requests(monkeypatch, tmp_path):
    monkeypatch.setattr(upd, "_outbound_enabled", lambda: False)
    calls: list[str] = []

    def fake_get(url):
        calls.append(url)
        return _release()

    res = upd.check_for_update(http_get=fake_get, state_file=tmp_path / "update-state.json")
    assert res["status"] == "offline"
    assert res["update_available"] is False
    assert calls == [], "出网关闭时必须一个请求都没发（不是'没处理响应'）"


def test_parse_release_assets_and_version_compare():
    parsed = upd.parse_release(_release(), current_version="0.4.9")
    assert parsed["latest_version"] == "0.4.10"
    assert parsed["update_available"] is True
    kinds = {a["kind"]: a for a in parsed["assets"]}
    assert kinds["lite"]["recommended"] is True
    assert kinds["full"]["requires_explicit_choice"] is True
    assert kinds["full"]["sha256"] == "a" * 64
    assert upd.is_newer("v0.4.10", "0.4.9")
    assert not upd.is_newer("0.4.9", "0.4.9")


def test_manual_check_then_auto_uses_cache(monkeypatch, tmp_path):
    # 钉住 current_version：本用例的语义是"存在更新版本"，不能随仓库版本 bump 而反转。
    # （0.4.9 → 0.4.10 bump 时该用例曾因"最新版=当前版"而红：测试不应耦合仓库版本号。）

    monkeypatch.setattr(upd, "_outbound_enabled", lambda: True)
    state = tmp_path / "update-state.json"
    calls = []

    def first(url):
        calls.append(url)
        return _release()

    res = upd.check_for_update(
        manual=True, http_get=first, state_file=state, current_version="0.4.9"
    )
    assert res["status"] == "ok" and res["cached"] is False
    assert res["update_available"] is True and len(calls) == 1

    def must_not_call(url):
        raise AssertionError("24h 内自动检查不应再请求")

    cached = upd.check_for_update(
        manual=False, http_get=must_not_call, state_file=state, current_version="0.4.9"
    )
    assert cached["status"] == "ok" and cached["cached"] is True
    assert cached["latest_version"] == "0.4.10"


def test_network_error_is_fail_open(monkeypatch, tmp_path):
    monkeypatch.setattr(upd, "_outbound_enabled", lambda: True)

    def boom(url):
        raise TimeoutError("network down")

    res = upd.check_for_update(manual=True, http_get=boom, state_file=tmp_path / "s.json")
    assert res["status"] == "error"
    assert res["update_available"] is False
    assert res["code"] == "network_error"


def test_http_request_carries_only_ua_and_accept(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        captured["headers"] = dict(req.header_items())
        return _FakeResponse(b'{"tag_name":"v0"}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    upd._http_json("https://api.github.com/repos/x/y/releases/latest")
    headers = {k.lower(): v for k, v in captured["headers"].items()}
    assert "user-agent" in headers
    assert headers["user-agent"].startswith("Memoria/")
    assert set(headers) <= {"user-agent", "accept"}


# ── ② 下载 + 校验 ──────────────────────────────────────────────────────────


def test_verify_package_manifest_ok_and_tamper(tmp_path):
    good = tmp_path / "good.zip"
    good.write_bytes(_zip_bytes(tmp_path))
    ok = upd.verify_downloaded_package(good, expected_version="0.4.10")
    assert ok["ok"] is True
    assert ok["mode"] == "manifest"
    assert "不含数字签名" in ok["verified_label"]

    bad = tmp_path / "bad.zip"
    bad.write_bytes(_zip_bytes(tmp_path, tamper=True))
    fail = upd.verify_downloaded_package(bad, expected_version="0.4.10")
    assert fail["ok"] is False
    assert fail["mode"] == "failed"
    assert fail["failures"]


def test_verify_size_mismatch_rejected(tmp_path):
    pkg = tmp_path / "p.zip"
    pkg.write_bytes(_zip_bytes(tmp_path))
    res = upd.verify_downloaded_package(pkg, expected_bytes=pkg.stat().st_size + 1)
    assert res["ok"] is False
    assert any("大小不符" in f for f in res["failures"])


def test_download_lite_success_and_cleanup(monkeypatch, tmp_path):
    monkeypatch.setattr(upd, "_outbound_enabled", lambda: True)
    state = tmp_path / "update-state.json"
    release = _release(lite_bytes=len(_zip_bytes(tmp_path)))
    upd._save_state({"release": release}, state)
    payload = _zip_bytes(tmp_path)

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        return _FakeResponse(payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    out_dir = tmp_path / "Downloads"
    res = upd.start_update_download(
        "Memoria-v0.4.10-win64-lite.zip", state_file=state, download_dir=out_dir
    )
    assert res["status"] == "ok", res
    job_id = res["job_id"]
    deadline = time.time() + 10
    st = None
    while time.time() < deadline:
        st = upd.get_update_download_status(job_id)
        if st["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.05)
    assert st is not None and st["status"] == "done", st
    target = Path(st["path"])
    assert target.is_file()
    assert target.read_bytes() == payload
    assert st["verification"]["mode"] == "manifest"
    assert not list(out_dir.glob("*.part"))


def test_download_disabled_makes_zero_requests(monkeypatch, tmp_path):
    monkeypatch.setattr(upd, "_outbound_enabled", lambda: False)
    called = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: called.append(1))
    res = upd.start_update_download("Memoria-v0.4.10-win64-lite.zip", download_dir=tmp_path)
    assert res["status"] == "disabled"
    assert called == []


def test_download_cancel_removes_partial(monkeypatch, tmp_path):
    monkeypatch.setattr(upd, "_outbound_enabled", lambda: True)
    state = tmp_path / "update-state.json"
    payload = _zip_bytes(tmp_path)
    release = _release(lite_bytes=len(payload))
    upd._save_state({"release": release}, state)
    big = payload * 2000  # 足够大，保证轮询期间能取消

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        return _FakeResponse(big, chunk_delay=0.02)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    out_dir = tmp_path / "Downloads"
    res = upd.start_update_download(
        "Memoria-v0.4.10-win64-lite.zip", state_file=state, download_dir=out_dir
    )
    assert res["status"] == "ok"
    job_id = res["job_id"]
    time.sleep(0.08)
    cancel_res = upd.cancel_update_download(job_id)
    assert cancel_res["status"] == "ok"
    deadline = time.time() + 10
    st = None
    while time.time() < deadline:
        st = upd.get_update_download_status(job_id)
        if st["status"] in ("cancelled", "failed", "done"):
            break
        time.sleep(0.03)
    assert st is not None and st["status"] == "cancelled", st
    assert not list(out_dir.glob("*.part"))


def test_verify_zip_without_manifest_is_explicitly_unverified(tmp_path):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("Memoria.exe", b"exe")
        zf.writestr("VERSION", b"0.4.10")
    p = tmp_path / "no-manifest.zip"
    p.write_bytes(out.getvalue())
    res = upd.verify_downloaded_package(p, expected_version="0.4.10")
    assert res["ok"] is True
    assert res["mode"] == "zip-only"
    assert res["verified_label"] == ""
