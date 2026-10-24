# -*- coding: utf-8 -*-
"""task-75 复现：真机 WebView2 启动早期调 openFile 的返回值/生效性。

流程：复制语料 → 与 boot 探针同一套 env 启动真机应用（CDP 端口暴露）→
scenarios/openfile-race.mjs attach 并在三个时机调 openFile → 汇总 JSON/MD。

用法：
  .venv\\Scripts\\python.exe scripts/benchmark/surface/run_openfile_race.py --runs 3 --label t75
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LAUNCHER = REPO / "scripts" / "benchmark" / "surface" / "_boot_launch.py"
DRIVER = REPO / "scripts" / "benchmark" / "surface" / "scenarios" / "openfile-race.mjs"
VERIFY = REPO / "artifacts" / "agent" / "verify"
TEMP = Path(os.environ.get("TEMP", "C:/Windows/Temp")) / "memoria_openfile_race"
SRC_KB = REPO / "artifacts" / "baseline-kb" / "数字通信原理"


def wait_cdp(port: int, timeout=90.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=0.5) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def port_free(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=0.3):
            return False
    except Exception:
        return True


def run_once(idx: int, args) -> dict:
    port = args.port + idx
    run_dir = TEMP / f"run_{args.label}_{idx}"
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    kb = run_dir / "kb"
    shutil.copytree(SRC_KB, kb)
    cfg = run_dir / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    out_json = VERIFY / f"openfile-race-{args.label}-r{idx}.json"

    env = os.environ.copy()
    env.update({
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "MEMORIA_MODE": "dev",
        "MEMORIA_DEBUG": "0",
        "MEMORIA_KB": str(kb),
        "MEMORIA_CONFIG_DIR": str(cfg),
        "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS": f"--remote-debugging-port={port}",
    })
    for k in ("MEMORIA_UI_SETTINGS", "MEMORIA_NO_KB", "MEMORIA_SHELL", "MEMORIA_FRAMELESS", "MEMORIA_THEME"):
        env.pop(k, None)

    if not port_free(port):
        return {"index": idx, "ok": False, "error": f"port {port} occupied"}
    stdout = open(run_dir / "app.out", "wb")
    stderr = open(run_dir / "app.err", "wb")
    proc = subprocess.Popen(
        [sys.executable, str(LAUNCHER), "--probe-port", str(port)],
        cwd=str(REPO), env=env, stdout=stdout, stderr=stderr,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    result = {"index": idx, "ok": False, "port": port, "runDir": str(run_dir)}
    try:
        if not wait_cdp(port):
            result["error"] = "CDP 端口未就绪"
            return result
        result["cdpReadyMs"] = None
        cp = subprocess.run(
            ["node", str(DRIVER), "--port", str(port), "--out", str(out_json)],
            cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=args.timeout,
        )
        result["driverExit"] = cp.returncode
        result["driverStdoutTail"] = (cp.stdout or "")[-1500:]
        if cp.returncode != 0:
            result["driverStderrTail"] = (cp.stderr or "")[-4000:]
        if out_json.is_file():
            race = json.loads(out_json.read_text("utf-8"))
            result["race"] = race
            result["ok"] = bool(race.get("ok"))
    except subprocess.TimeoutExpired:
        result["error"] = f"driver timeout {args.timeout}s"
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        stdout.close()
        stderr.close()
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-CimInstance Win32_Process -Filter \"Name='msedgewebview2.exe'\" | "
             f"Where-Object {{ $_.CommandLine -like '*remote-debugging-port={port}*' }} | "
             f"ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}"],
            capture_output=True,
        )
        for _ in range(40):
            if port_free(port):
                break
            time.sleep(0.25)
    return result


def build_md(campaign: dict) -> str:
    L = ["# task-75 复现：启动早期 openFile 返回值/生效性（真机 WebView2）", ""]
    L.append("- 生成：%s" % campaign["generatedAt"])
    L.append("- 语料：`%s` 副本；每轮独立进程/空配置/CDP 端口" % SRC_KB)
    L.append("- 探针：`scripts/benchmark/surface/scenarios/openfile-race.mjs`（attach 到**最早**出现的页面目标后立即调用）")
    L.append("")
    for run in campaign["runs"]:
        L.append("## run#%d（port=%d, ok=%s）" % (run["index"], run["port"], run["ok"]))
        race = run.get("race") or {}
        att = race.get("attach") or {}
        L.append("")
        L.append("- attach：目标出现 %s ms，连上 %s ms；`openFile` 可见 %s ms" % (
            att.get("foundAtMs"), att.get("connectedAtMs"), att.get("openFileVisibleAtMs")))
        fv = att.get("stateAtFirstVisible") or {}
        L.append("- 最早快照：files=%s kbPath=%s currentPath=%s bootPending=%s" % (
            fv.get("files"), fv.get("kbPath"), fv.get("currentPath"), fv.get("bootPending")))
        cb = att.get("caughtBootPending")
        L.append("- 命中「自动打开进行中」：%s" % (json.dumps(cb, ensure_ascii=False) if cb else "（窗口太窄未命中）"))
        L.append("")
        L.append("| 时机 | 调用时刻(ms) | 返回值(原文) | currentPath 前 | currentPath 后(立即) | 立即生效 | 1.8s 后生效 |")
        L.append("|---|---|---|---|---|---|---|")
        for c in race.get("calls") or []:
            L.append("| %s | %s | `%s` | %s | %s | %s | %s |" % (
                c.get("tag"), c.get("tCallMs"), c.get("returnValue"),
                (c.get("before") or {}).get("currentPath"),
                (c.get("immediately") or {}).get("currentPath"),
                c.get("pathChangedImmediately"), c.get("pathChangedSettled")))
        L.append("")
        logs = []
        for c in race.get("calls") or []:
            for lg in (c.get("logsAtCall") or [])[-4:]:
                logs.append("  - [%s] %s: %s" % (lg.get("t"), lg.get("lvl"), lg.get("text")))
        if logs:
            L.append("- 调用前后应用日志（节选）：")
            L.extend(logs)
        if race.get("error"):
            L.append("- **错误**：%s" % race["error"])
        L.append("")
    L.append("## 判定口径")
    L.append("- 「静默失真」定义：返回值不明确（undefined/空字符串）**且** currentPath 未变 **且** 无任何日志/状态提示。")
    L.append("- 明确失败可接受：返回 `failed`/`aborted`/`THROW:` 字符串，且 `setStatus` 已给出可见提示。")
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="task-75 openFile 启动期竞态复现")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--label", default="t75")
    ap.add_argument("--port", type=int, default=9691)
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()
    VERIFY.mkdir(parents=True, exist_ok=True)
    runs = [run_once(i, args) for i in range(args.runs)]
    campaign = {
        "schema": "openfile-race-campaign/v1",
        "label": args.label,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "kbSource": str(SRC_KB),
        "runs": runs,
    }
    out_json = VERIFY / f"openfile-race-{args.label}.json"
    out_md = VERIFY / f"openfile-race-{args.label}.md"
    out_json.write_text(json.dumps(campaign, ensure_ascii=False, indent=2), "utf-8")
    out_md.write_text(build_md(campaign), "utf-8")
    ok = sum(1 for r in runs if r.get("ok"))
    print("[race] %d/%d 轮成功；产物：%s / %s" % (ok, len(runs), out_md, out_json))
    for r in runs:
        if not r.get("ok"):
            print("  run#%d 失败：%s" % (r["index"], r.get("error") or r.get("driverStderrTail", "")[-500:]))
    return 0 if ok == len(runs) else 1


if __name__ == "__main__":
    sys.exit(main())
