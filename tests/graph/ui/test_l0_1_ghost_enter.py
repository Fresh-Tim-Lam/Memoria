# -*- coding: utf-8 -*-
"""L0_1 折叠容器 → 子图 backgroundGhost 回归（task-391 rev12，真机 CDP）。

动机（Lead 真机复核发现的回归）：父视图把 container 组折叠成簇节点后，成员是 hidden、
不在 `captureViewState().positions` 里；`enterMultigroup` 旧逻辑只用成员质心算幽灵位置
⇒ `backgroundGhost=null`，进入子图后画布只剩子图 KP，没有 A/跨层线/可拖簇节点。

本测试跑真实应用页面（项目标准 harness + 真实 Edge + CDP 受信任输入）：
  1) 父视图断言只有折叠簇节点、无成员 node-001；
  2) 真实点击簇节点进入子图；
  3) 断言 child view `getPositions()` 同时有 `node-001` 与 `ghost:A`；
  4) 拖 KP → ghost 位移 &gt; 0；拖 ghost → KP 位移 &gt; 0；全程单画布。

依赖：node + msedge（无则 skip，不阻塞 `pytest tests/graph`）。
证据：`artifacts/agent/verify/graph/l0-1-ghost-realapp.json`。
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SURFACE = ROOT / "scripts" / "benchmark" / "surface"
DEMO_KB = HERE / "fixtures" / "demo-kb-l0x"
SCENARIO = HERE / "l0_1_ghost_enter.test.mjs"
EVIDENCE_OUT = ROOT / "artifacts" / "agent" / "verify" / "graph" / "l0-1-ghost-realapp.json"
EVIDENCE_SHOT = ROOT / "artifacts" / "agent" / "verify" / "graph" / "l0-1-drillbar-no-back.png"
EVIDENCE_SHOT_DEMO = ROOT / "artifacts" / "agent" / "verify" / "graph" / "l0-x-clusters-demo.png"
EVIDENCE_SHOT_CHILD = ROOT / "artifacts" / "agent" / "verify" / "graph" / "l0-1-child-bg-ghosts.png"
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
    spec = importlib.util.spec_from_file_location("memoria_run_probe_l01", str(SURFACE / "run_probe.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(_find_edge() is None, reason="无 msedge，跳过 L0_1 真机回归")
@pytest.mark.skipif(os.environ.get("MEMORIA_SKIP_L0_1_REALAPP") == "1", reason="显式跳过 L0_1 真机回归")
def test_l0_1_enter_group_keeps_background_ghost() -> None:
    assert DEMO_KB.is_dir(), f"缺少 demo KB：{DEMO_KB}"
    tag = "l0_1_probe_%d" % os.getpid()
    work_kb = ROOT / "artifacts" / "_l0_1_probe_kb_" / tag
    cfg_dir = ROOT / "artifacts" / "_l0_1_probe_config_" / tag
    raw_out = ROOT / "artifacts" / "_l0_1_probe_" / (tag + ".json")
    shutil.rmtree(work_kb, ignore_errors=True)
    shutil.rmtree(cfg_dir, ignore_errors=True)
    work_kb.parent.mkdir(parents=True, exist_ok=True)
    cfg_dir.mkdir(parents=True, exist_ok=True)
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(DEMO_KB, work_kb)
    os.environ["MEMORIA_CONFIG_DIR"] = str(cfg_dir)
    port = _free_port()
    bottle = None
    try:
        rp = _load_run_probe()
        harness = rp.load_harness(work_kb, port)
        import bottle as bottle_mod  # noqa: PLC0415  (延迟导入：无 bottle 时由门禁环境保证)
        bottle = bottle_mod
        threading.Thread(
            target=bottle.run,
            kwargs=dict(app=harness.app, host="127.0.0.1", port=port, quiet=True),
            daemon=True,
        ).start()
        assert rp.wait_port(port), "harness 未在 20s 内就绪"
        raw_shot = raw_out.with_suffix(".png")
        raw_shot_parent = raw_out.with_name(raw_out.stem + "-demo.png")
        raw_shot_child = raw_out.with_name(raw_out.stem + "-child-bg.png")
        cmd = [
            "node", str(SCENARIO), "--url", "http://127.0.0.1:%d/" % port,
            "--out", str(raw_out), "--shot", str(raw_shot),
            "--shot-parent", str(raw_shot_parent),
            "--shot-child-bg", str(raw_shot_child),
        ]
        cp = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=240)
        assert raw_out.is_file(), f"探针未产出 JSON。stdout={cp.stdout[-2000:]}\nstderr={cp.stderr[-3000:]}"
        payload = json.loads(raw_out.read_text(encoding="utf-8"))
        EVIDENCE_OUT.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(raw_out, EVIDENCE_OUT)
        if raw_shot.is_file():
            shutil.copyfile(raw_shot, EVIDENCE_SHOT)
        if raw_shot_parent.is_file():
            shutil.copyfile(raw_shot_parent, EVIDENCE_SHOT_DEMO)
        if raw_shot_child.is_file():
            shutil.copyfile(raw_shot_child, EVIDENCE_SHOT_CHILD)
        assert payload.get("verdict") == "PASS", (
            "L0_1 demo/子图回归失败：\n%s" % json.dumps(payload, ensure_ascii=False, indent=2)[-4000:]
        )
        checks = payload.get("checks") or {}
        for key in (
            "demoFourClusters",
            "demoClusterLabelsClean",
            "demoKp002Visible",
            "demoHubKpsVisible",
            "demoPresentationLinks",
            "expandAllSingleL01",
            "childBackgroundGhosts",
            "childBackgroundNoLabels",
            "childBackgroundWhiteGlow",
            "backClearsBackground",
            "parentOnlyCollapsedCluster",
            "childHasNode001AndGhost",
            "ghostConnectorDrawn",
            "drillbarOnlyCrumbsNoBack",
            "textNotSelectable",
            "dragKpMovedGhost",
            "dragGhostMovedKp",
            "singleCanvas",
        ):
            assert checks.get(key) is True, f"L0_1 幽灵回归 check 失败：{key}"
    finally:
        shutil.rmtree(work_kb, ignore_errors=True)
        shutil.rmtree(cfg_dir, ignore_errors=True)
        shutil.rmtree(raw_out.parent, ignore_errors=True)
