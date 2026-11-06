# -*- coding: utf-8 -*-
"""链接小窗 pin 状态回归（task-391 rev14，真机 CDP）。

Lead 真机复现：`prefs.pinned=true` 被恢复 ⇒ 用户“没开 pin”却点画布不关闭。
本测试预置 `ui-settings.linkPanel.pinned=true`，跑真实应用页面断言：
  1) 新面板仍为 `pinned=false`；2) 未 pin 点面板外关闭；3) 点 pin 后不关闭；
  4) 回读持久化不含 pinned=true。

依赖：node + msedge（无则 skip）。证据：`artifacts/agent/verify/graph/link-panel-pin-realapp.json`。
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import socket
import subprocess
import threading
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SURFACE = ROOT / "scripts" / "benchmark" / "surface"
DEMO_KB = ROOT / "docs" / "example" / "empty"
SCENARIO = HERE / "link_panel_pin.test.mjs"
EVIDENCE_OUT = ROOT / "artifacts" / "agent" / "verify" / "graph" / "link-panel-pin-realapp.json"
EDGE_CANDIDATES = [
    os.environ.get("MEMORIA_EDGE"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _find_edge() -> str | None:
    for p in EDGE_CANDIDATES:
        if p and Path(p).is_file():
            return p
    return None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _load_run_probe():
    spec = importlib.util.spec_from_file_location("memoria_run_probe_lp", str(SURFACE / "run_probe.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(_find_edge() is None, reason="无 msedge，跳过链接小窗真机回归")
@pytest.mark.skipif(os.environ.get("MEMORIA_SKIP_LINK_PANEL_REALAPP") == "1", reason="显式跳过链接小窗真机回归")
def test_link_panel_new_panel_is_unpinned_and_closes_on_outside() -> None:
    assert DEMO_KB.is_dir(), f"缺少 demo KB：{DEMO_KB}"
    tag = "link_panel_probe_%d" % os.getpid()
    work_kb = ROOT / "artifacts" / "_link_panel_probe_kb_" / tag
    cfg_dir = ROOT / "artifacts" / "_link_panel_probe_config_" / tag
    raw_out = ROOT / "artifacts" / "_link_panel_probe_" / (tag + ".json")
    shutil.rmtree(work_kb, ignore_errors=True)
    shutil.rmtree(cfg_dir, ignore_errors=True)
    work_kb.parent.mkdir(parents=True, exist_ok=True)
    cfg_dir.mkdir(parents=True, exist_ok=True)
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(DEMO_KB, work_kb)
    # 模拟历史持久化：pinned=true 落在 ui-settings.linkPanel
    (cfg_dir / "ui-settings.json").write_text(
        json.dumps({
            "linkPanel": {"pinned": True, "x": 60, "y": 80, "w": 360, "h": 280, "mode": "preview"},
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.environ["MEMORIA_CONFIG_DIR"] = str(cfg_dir)
    port = _free_port()
    try:
        rp = _load_run_probe()
        harness = rp.load_harness(work_kb, port)
        import bottle as bottle_mod  # noqa: PLC0415

        threading.Thread(
            target=bottle_mod.run,
            kwargs=dict(app=harness.app, host="127.0.0.1", port=port, quiet=True),
            daemon=True,
        ).start()
        assert rp.wait_port(port), "harness 未在 20s 内就绪"
        cmd = ["node", str(SCENARIO), "--url", "http://127.0.0.1:%d/" % port, "--out", str(raw_out)]
        cp = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=240)
        assert raw_out.is_file(), f"探针未产出 JSON。stdout={cp.stdout[-2000:]}\nstderr={cp.stderr[-3000:]}"
        payload = json.loads(raw_out.read_text(encoding="utf-8"))
        EVIDENCE_OUT.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(raw_out, EVIDENCE_OUT)
        assert payload.get("verdict") == "PASS", (
            "链接小窗 pin 回归失败：\n%s" % json.dumps(payload, ensure_ascii=False, indent=2)[-4000:]
        )
        checks = payload.get("checks") or {}
        for key in (
            "prefsSeededPinnedTrue",
            "defaultUnpinnedWithPrefsPinned",
            "outsideClosesUnpinned",
            "pinToggleWorks",
            "pinnedSurvivesOutside",
            "persistOmitsPinned",
        ):
            assert checks.get(key) is True, f"链接小窗 pin check 失败：{key}"
    finally:
        shutil.rmtree(work_kb, ignore_errors=True)
        shutil.rmtree(cfg_dir, ignore_errors=True)
        shutil.rmtree(raw_out.parent, ignore_errors=True)
