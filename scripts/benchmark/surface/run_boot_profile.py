# -*- coding: utf-8 -*-
"""冷启动时间线测量入口（task-69 测量阶段）。

一条命令 = 起 N 次**真机** Memoria（隔离配置 + 独立 KB 副本 + 独立 CDP 端口），
每次同时采三路证据并合成**分阶段 ms 表**：

  ① 子进程侧（`_boot_launch.py` → JSONL）：进程入口/导入/壳/服务 + 每个 UIAPI RPC 的
     **服务端净执行时间** + 图谱/完整性等重活的内层 span；
  ② 浏览器侧（`_boot_probe.mjs` → JSON）：CDP 目标出现/attach/导航/桥就绪/每个 RPC 的
     **页面往返时间**/状态与 DOM 里程碑/长任务/`PerformanceObserver` paint；
  ③ **注入式重载**（document_start 打点）：把前端阶段拆到毫秒级，并用产品自带的
     `_lastSwitch`（openFile 的 stash/load/editor/render/settle/tail + 异步 paint）
     把"自动打开首个文件"内部再拆一层。

产物：
  · `artifacts/agent/verify/boot-timeline-<label>.json` —— 原始证据 + 每轮 phases + P50/max
  · `artifacts/agent/verify/boot-timeline-<label>.md`   —— 人读分阶段表 + 可延后估算

用法：
  .venv\\Scripts\\python.exe scripts/benchmark/surface/run_boot_profile.py --runs 3
  .venv\\Scripts\\python.exe scripts/benchmark/surface/run_boot_profile.py --runs 1 --label smoke --no-reload
  .venv\\Scripts\\python.exe scripts/benchmark/surface/run_boot_profile.py --runs 3 --extra-open   # 另测稳态 openFile

纪律（与 surface/README.md 一致）：
  · 冻结 KB **只读**：默认从 `artifacts/baseline-kb/数字通信原理` 拷一份到 %TEMP% 工作副本，
    测量只碰副本；
  · 配置隔离：每轮新建**空** `MEMORIA_CONFIG_DIR`（不继承开发机 ui-settings）；
  · 清理只走 `safe-kill.psm1` 口径：只杀**自己启动且命令行含本次端口**的 PID，绝不 `/T`，
    绝不碰 `Package\\Memoria.exe`；
  · 端口固定 9660–9665（避开其它 agent 的 95xx/96xx），被占即**拒绝测量**（不杀占用者）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
RESULTS_DIR = REPO_ROOT / "artifacts" / "agent" / "verify"
LAUNCHER = HERE / "_boot_launch.py"
PROBE = HERE / "_boot_probe.mjs"
SAFE_KILL = HERE / "safe-kill.psm1"
DEFAULT_KB = REPO_ROOT / "artifacts" / "baseline-kb" / "数字通信原理"
TEMP_ROOT = Path(os.environ.get("TEMP", ".")) / "memoria_boot_probe"


def _utf8_stdio() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def log(msg: str) -> None:
    print("[boot-profile] " + msg, flush=True)


def port_free(port: int) -> bool:
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def port_owner(port: int) -> str:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        pid = (out.stdout or "").strip().splitlines()
        pid = pid[-1].strip() if pid else ""
        if not pid.isdigit():
            return "<unknown>"
        out2 = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').Name"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        return f"pid={pid} name={(out2.stdout or '').strip()}"
    except Exception:
        return "<unknown>"


def safe_kill_pid(pid: int, port: int) -> dict:
    """走 safe-kill.psm1：校验身份（命令行含端口）后才杀，绝不 /T。"""
    cmd = (
        f"Import-Module '{SAFE_KILL}' -Force; "
        f"$r = Stop-MeasurementProcess -ProcessId {pid} -ExpectedPort {port} -Quiet; "
        f"$r | ConvertTo-Json -Compress"
    )
    try:
        cp = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=60)
        txt = (cp.stdout or "").strip()
        try:
            return json.loads(txt.splitlines()[-1]) if txt else {}
        except Exception:
            return {"raw": txt[-400:]}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def cleanup_webview2(port: int) -> list[int]:
    """按**调试端口**精确清理本次实例遗留的 WebView2（只杀 msedgewebview2，不带 /T）。"""
    marker = f"remote-debugging-port={port}"
    cmd = (
        f"Import-Module '{SAFE_KILL}' -Force; "
        f"$k = Stop-OrphanWebView2 -Marker '{marker}' -Quiet; "
        f"@($k) | ConvertTo-Json -Compress"
    )
    try:
        cp = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=60)
        txt = (cp.stdout or "").strip()
        if not txt:
            return []
        v = json.loads(txt.splitlines()[-1])
        return [int(x) for x in (v if isinstance(v, list) else [v]) if str(x).isdigit()]
    except Exception:
        return []


def machine_context() -> dict:
    ctx: dict = {
        "platform": sys.platform,
        "python": sys.version,
        "cpuCount": os.cpu_count(),
        "cwd": os.getcwd(),
    }
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty LoadPercentage"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        v = (out.stdout or "").strip()
        if v.isdigit():
            ctx["cpuLoadPercentAtStart"] = int(v)
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_OperatingSystem | Select-Object -ExpandProperty FreePhysicalMemory"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        v = (out.stdout or "").strip()
        if v.isdigit():
            ctx["freePhysicalMemoryKB"] = int(v)
    except Exception:
        pass
    try:
        ctx["gitHead"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                                                 text=True, encoding="utf-8").strip()
        ctx["gitDirty"] = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO_ROOT,
                                                       text=True, encoding="utf-8").strip())
    except Exception:
        pass
    # 并发测量识别（本机可能同时有其它 agent 的真机/无头测量在跑；数字必须在口工里注明）
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|node|Memoria' } | "
             "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        procs = json.loads((out.stdout or "[]").strip() or "[]")
        if isinstance(procs, dict):
            procs = [procs]
        patterns = ("run_selection.py", "selection-driver.mjs", "run_boot_profile.py",
                    "run_fidelity", "run_lazy_gate", "p5perf", "run_interaction.py")
        others = []
        for p in procs:
            cmd = str(p.get("CommandLine") or "")
            if any(k in cmd for k in patterns) and "run_boot_profile.py" not in cmd:
                others.append({"pid": p.get("ProcessId"), "name": p.get("Name"),
                               "cmd": cmd[:200]})
        ctx["concurrentMeasurements"] = others
        ctx["memoriaExeProcesses"] = sum(1 for p in procs if p.get("Name") == "Memoria.exe")
        ctx["webview2Processes"] = sum(1 for p in procs if p.get("Name") == "msedgewebview2.exe")
    except Exception as exc:  # noqa: BLE001
        ctx["concurrentProbeError"] = str(exc)
    return ctx


# ── JSONL / importtime 解析 ─────────────────────────────────────────────

def parse_jsonl(path: Path) -> dict:
    recs = []
    if path.is_file():
        for line in path.read_text("utf-8", "replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except Exception:
                continue
    t0 = next((r for r in recs if r.get("kind") == "proc_start"), None)
    spans = []
    cur: dict[str, dict] = {}
    for r in recs:
        k = r.get("kind")
        name = r.get("name") or ""
        if k == "span_start":
            cur.setdefault(name, []).append(r)
        elif k == "span":
            starts = cur.get(name) or []
            s = starts.pop(0) if starts else None
            spans.append({
                "name": name,
                "startT": (s or {}).get("t"),
                "startWall": (s or {}).get("wall"),
                "endT": r.get("t"),
                "ms": r.get("ms"),
                "ok": r.get("ok"),
                "thread": r.get("thread"),
                "result": r.get("result"),
                "error": r.get("error"),
            })
    marks = [
        {"kind": r.get("kind"), "name": r.get("name"), "t": r.get("t"), "wall": r.get("wall"),
         "ms": r.get("ms"), "count": r.get("count"), "imports_ms": r.get("imports_ms"),
         "address": (r.get("result") or {}).get("address") if isinstance(r.get("result"), dict) else None}
        for r in recs if r.get("kind") in ("launcher_ready", "before_desktop_main", "import", "wrap_done", "proc_start", "proc_exit", "desktop_crash")
    ]
    http = [r for r in recs if str(r.get("kind", "")).startswith("http_req")]
    return {
        "path": str(path),
        "t0WallEpoch": (t0 or {}).get("t0_wall_epoch"),
        "pid": (t0 or {}).get("pid"),
        "env": (t0 or {}).get("env"),
        "python": (t0 or {}).get("python"),
        "records": len(recs),
        "marks": marks,
        "spans": spans,
        "http": http,
    }


_IMPORTTIME_RE = re.compile(r"^import time:\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(.+)$")


def parse_importtime(stderr_path: Path) -> dict:
    rows = []
    if not stderr_path.is_file():
        return {"rows": [], "top": []}
    for line in stderr_path.read_text("utf-8", "replace").splitlines():
        m = _IMPORTTIME_RE.match(line.strip())
        if not m:
            continue
        self_us, cum_us, mod = int(m.group(1)), int(m.group(2)), m.group(3).strip()
        rows.append({"selfMs": round(self_us / 1000.0, 1), "cumMs": round(cum_us / 1000.0, 1), "module": mod})
    top = sorted(rows, key=lambda r: r["cumMs"], reverse=True)[:25]
    return {"rows": len(rows), "top": top}


# ── 单轮 ────────────────────────────────────────────────────────────────

def run_once(idx: int, args, kb_work: Path) -> dict:
    port = args.port + idx
    run_dir = TEMP_ROOT / f"run_{args.label}_{idx}"
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    cfg = run_dir / "config"
    cfg.mkdir(parents=True, exist_ok=True)  # 空配置目录 = 首次启动默认值（隔离 ambient）
    jsonl = run_dir / "boot-events.jsonl"
    stdout = run_dir / "app.out"
    stderr = run_dir / "app.err"
    probe_out = run_dir / "probe.json"

    if not port_free(port):
        return {"index": idx, "ok": False, "error": f"port {port} occupied by {port_owner(port)}",
                "port": port, "runDir": str(run_dir)}

    env = os.environ.copy()
    env.update({
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "MEMORIA_MODE": "dev",
        "MEMORIA_DEBUG": "0",
        "MEMORIA_KB": str(kb_work),
        "MEMORIA_CONFIG_DIR": str(cfg),
        "BOOT_PROBE_JSONL": str(jsonl),
        "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS": f"--remote-debugging-port={port}",
    })
    # 不继承会让窗口状态漂移的变量（父 shell 可能设过）
    for k in ("MEMORIA_UI_SETTINGS", "MEMORIA_NO_KB", "MEMORIA_SHELL", "MEMORIA_FRAMELESS", "MEMORIA_THEME"):
        env.pop(k, None)

    cmd = [sys.executable, "-X", "importtime", str(LAUNCHER), "--probe-port", str(port)]
    log(f"run#{idx} port={port} launch: {' '.join(cmd)}")
    t_launch_epoch = int(time.time() * 1000)
    with open(stdout, "wb") as fo, open(stderr, "wb") as fe:
        proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT), env=env, stdout=fo, stderr=fe,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    started = time.time()
    node_cp = None
    node_err = None
    try:
        node_cmd = ["node", str(PROBE), "--port", str(port), "--out", str(probe_out),
                    "--launch-epoch", str(t_launch_epoch),
                    "--boot-timeout", str(args.boot_timeout),
                    "--reload-timeout", str(args.reload_timeout)]
        if args.no_reload:
            node_cmd.append("--no-reload")
        if args.extra_open:
            node_cmd += ["--extra-open", args.extra_open]
        if args.extra_open_view:
            node_cmd += ["--extra-open-view", args.extra_open_view]
        log(f"run#{idx} probe: {' '.join(node_cmd)}")
        node_cp = subprocess.run(node_cmd, cwd=str(REPO_ROOT), capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=args.probe_timeout)
        node_err = (node_cp.stderr or "")[-4000:]
        if node_cp.returncode != 0:
            log(f"run#{idx} probe exit={node_cp.returncode}")
    except subprocess.TimeoutExpired:
        node_err = f"probe timeout after {args.probe_timeout}s"
        log(f"run#{idx} {node_err}")
    finally:
        killed = safe_kill_pid(proc.pid, port)
        time.sleep(args.settle)
        orphans = cleanup_webview2(port)
        if killed.get("Killed") is False and killed.get("Reason") not in ("not-running", None):
            log(f"run#{idx} WARN safe-kill: {killed}")
        if orphans:
            log(f"run#{idx} cleaned orphan webview2: {orphans}")
        for _ in range(30):
            if port_free(port):
                break
            time.sleep(0.3)

    backend = parse_jsonl(jsonl)
    imports = parse_importtime(stderr)
    probe = None
    if probe_out.is_file():
        try:
            probe = json.loads(probe_out.read_text("utf-8"))
        except Exception as exc:  # noqa: BLE001
            probe = {"parseError": str(exc)}
    try:
        app_out = stdout.read_text("utf-8", "replace")[-8000:]
        app_err = stderr.read_text("utf-8", "replace")[-12000:]
    except Exception:
        app_out = app_err = ""
    wall = time.time() - started

    result = {
        "index": idx,
        "ok": bool(probe and probe.get("ok")),
        "port": port,
        "runDir": str(run_dir),
        "kbWorkCopy": str(kb_work),
        "configDir": str(cfg),
        "launchEpoch": t_launch_epoch,
        "wallSeconds": round(wall, 2),
        "nodeStderrTail": node_err,
        "backend": backend,
        "importtime": imports,
        "probe": probe,
        "appStdoutTail": app_out,
        "appStderrTail": app_err[-6000:],
    }
    result["phases"] = compute_phases(result)
    return result


# ── 阶段合成 ────────────────────────────────────────────────────────────

def _ms(a, b):
    if a is None or b is None:
        return None
    try:
        return round(float(b) - float(a), 1)
    except Exception:
        return None


def _find_span(spans, name):
    cand = [s for s in spans if s.get("name") == name]
    return cand[0] if cand else None


def _find_spans(spans, prefix):
    return [s for s in spans if str(s.get("name", "")).startswith(prefix)]


def compute_phases(run: dict) -> dict:
    """把三路证据合成一条以「父进程 Popen 时刻」为 0 的时间轴（ms）。"""
    launch = run.get("launchEpoch")
    backend = run.get("backend") or {}
    probe = run.get("probe") or {}
    spans = backend.get("spans") or []
    phases: dict = {}

    t0 = backend.get("t0WallEpoch")
    phases["A0_launch_to_child_entry"] = _ms(launch, t0)

    first = probe.get("firstBoot") or {}
    raw = first.get("raw") or {}
    nav = raw.get("nav") or {}
    time_origin = raw.get("timeOrigin")
    if time_origin:
        phases["A1_launch_to_page_nav_start"] = _ms(launch, time_origin)
        if nav:
            phases["A2_page_nav_to_dom_interactive"] = _ms(time_origin, time_origin + (nav.get("domInteractive") or 0))
            phases["A3_page_nav_to_dcl"] = _ms(time_origin, time_origin + (nav.get("domContentLoadedEventEnd") or 0))
            phases["A4_page_nav_to_load_end"] = _ms(time_origin, time_origin + (nav.get("loadEventEnd") or 0))
            phases["A4b_page_response_end"] = nav.get("responseEnd")

    # 后端壳阶段（子进程侧）
    cw = _find_span(spans, "webview.create_window")
    if cw:
        phases["B1_create_window_ms"] = cw.get("ms")
    ss = _find_span(spans, "webview.bottle.start_server")
    if ss:
        phases["B2_http_server_start_ms"] = ss.get("ms")
        if t0 and ss.get("startWall"):
            phases["B3_launch_to_http_server_ready"] = _ms(launch, ss.get("startWall"))
            phases["B3_launch_to_http_server_ready"] = round(
                phases["B3_launch_to_http_server_ready"], 1) if phases["B3_launch_to_http_server_ready"] else None
    launcher_ready = next((m for m in backend.get("marks") or [] if m.get("kind") == "launcher_ready"), None)
    if launcher_ready and launcher_ready.get("t") is not None:
        phases["B0_launch_to_launcher_ready"] = round(
            (_ms(launch, t0) or 0) + float(launcher_ready["t"]), 1)

    # 前端里程碑（注入式重载里是精确的 epoch；首次导航里是 node 轮询）
    inst = probe.get("instrumented") or {}
    dump = inst.get("dump") or {}
    inst_marks = dump.get("marks") or []
    origin = dump.get("timeOrigin")

    def mark_epoch(name):
        for m in inst_marks:
            if m.get("name") == name and origin is not None:
                return origin + m.get("t", 0)
        return None

    if dump:
        for key, name in (
            ("C1_page_nav_to_document_start", "document_start"),
            ("C2_page_nav_to_dcl", "readyState:interactive"),
            ("C3_page_nav_to_load", "readyState:complete"),
            ("C4_page_nav_to_bridge_ready", "bridge_ready"),
            ("C5_page_nav_to_api_hooked", "api_hooked"),
            ("C6_page_nav_to_app_defined", "memoriaapp_defined"),
            ("C7_page_nav_to_kbPath", "state:kbPath"),
            ("C8_page_nav_to_files", "state:files"),
            ("C9_page_nav_to_graphData", "state:graphData"),
            ("C10_page_nav_to_validateReport", "state:kbValidateReport"),
            ("C11_page_nav_to_currentPath", "state:currentPath"),
            ("C12_page_nav_to_previewBlocks", "dom:preview-blocks"),
            ("C13_page_nav_to_editorLines", "dom:editor-lines"),
            ("C14_page_nav_to_fileTree", "dom:file-tree-items"),
        ):
            e = mark_epoch(name)
            if e is not None and origin is not None:
                phases[key] = _ms(origin, e)

        # 相对 launch 的绝对位置（重载轮）
        if origin:
            phases["D1_launch_to_page_nav_start_reload"] = _ms(launch, origin)
            e_prev = mark_epoch("dom:preview-blocks")
            if e_prev:
                phases["D2_launch_to_first_doc_visible"] = _ms(launch, e_prev)

        # 产品自带 openFile 分段（相对 openFile 起点）
        ls = dump.get("lastSwitch") or {}
        if ls.get("phases"):
            phases["E0_openFile_total_ms"] = ls.get("ms")
            for k, v in sorted(ls["phases"].items(), key=lambda kv: kv[1]):
                phases[f"E1_open_{k}_abs"] = v
            # 相邻差 = 每段自身耗时
            order = sorted(ls["phases"].items(), key=lambda kv: kv[1])
            prev = None
            for k, v in order:
                if prev is not None:
                    phases[f"E2_open_{k}_delta"] = round(v - prev, 1)
                prev = v
        if ls.get("async"):
            for k, v in ls["async"].items():
                phases[f"E3_open_async_{k}"] = v

        # 页面侧 RPC 往返（每方法）
        rpc = dump.get("rpc") or []
        for r in rpc:
            fn = str(r.get("fn") or "")
            if r.get("ms") is None:
                continue
            phases[f"R_{fn}_ms"] = r.get("ms")
            if origin is not None and r.get("t") is not None:
                phases[f"R_{fn}_start_rel_page"] = r.get("t")
            if fn == "suggest_group_labels" and r.get("arg0len") is not None:
                phases["F0_suggest_group_labels_groupCount"] = r.get("arg0len")
        # 关键派生：图谱渲染（graphData 写入 → validate_kb 开始）与全库校验成本
        gd = mark_epoch("state:graphData")
        rpc_validate = next((r for r in rpc if r.get("fn") == "validate_kb"), None)
        if gd is not None and rpc_validate is not None and origin is not None:
            phases["F1_graph_data_render_ms"] = _ms(gd, origin + rpc_validate.get("t", 0))
        rpc_graph = next((r for r in rpc if r.get("fn") == "get_graph_data"), None)
        if rpc_graph is not None and rpc_graph.get("ms") is not None:
            phases["F2_get_graph_data_rpc_ms"] = rpc_graph.get("ms")
        vr = mark_epoch("state:kbValidateReport")
        if vr is not None and rpc_validate is not None and origin is not None:
            phases["F3_validate_window_ms"] = _ms(origin + rpc_validate.get("t", 0), vr)
        cur = mark_epoch("state:currentPath")
        if vr is not None and cur is not None:
            phases["F4_validate_done_to_open_start_ms"] = _ms(vr, cur)

        # 长任务：open 之前的 JS 主线程阻塞总量（真机"卡住"证据）
        lts = [t for t in (dump.get("longtasks") or []) if (t.get("start") or 0) < (mark_epoch("state:currentPath") or 0) - (origin or 0)]
        if lts:
            phases["G1_longtask_count_before_open"] = len(lts)
            phases["G2_longtask_total_ms_before_open"] = round(sum(t.get("dur") or 0 for t in lts), 1)
            phases["G3_longtask_max_ms"] = round(max((t.get("dur") or 0) for t in lts), 1)

        # 总账（重载轮）
        if mark_epoch("dom:preview-blocks") is not None and launch:
            phases["Z_total_launch_to_first_doc_reload"] = _ms(launch, mark_epoch("dom:preview-blocks"))

    # 首次导航（真实用户路径）里程碑：node 侧 100ms 轮询（精度有限）
    for k, label in (
        ("kbPath", "N1_first_launch_to_kbPath"),
        ("files", "N2_first_launch_to_files"),
        ("graphNodes", "N3_first_launch_to_graphData"),
        ("validateReport", "N4_first_launch_to_validateReport"),
        ("currentPath", "N5_first_launch_to_currentPath"),
        ("previewBlocks", "N6_first_launch_to_previewBlocks"),
        ("editorLines", "N7_first_launch_to_editorLines"),
    ):
        v = (first.get("milestones") or {}).get(k)
        if v is not None:
            phases[label] = v
    if first.get("lastSwitch") and not (dump.get("lastSwitch")):
        phases["E0_openFile_total_ms"] = first["lastSwitch"].get("ms")
        for k, v in (first["lastSwitch"].get("phases") or {}).items():
            phases[f"E1_open_{k}_abs"] = v

    # 额外的稳态 openFile（--extra-open）：与 boot 期首开分开记
    ex = probe.get("extraOpen") or {}
    ls_ex = ex.get("lastSwitch") or {}
    if ls_ex.get("ms") is not None:
        phases["O1_extra_open_ms"] = ls_ex.get("ms")
        order = sorted((ls_ex.get("phases") or {}).items(), key=lambda kv: kv[1])
        prev = None
        for k, v in order:
            phases[f"O2_extra_open_{k}_abs"] = v
            if prev is not None:
                phases[f"O3_extra_open_{k}_delta"] = round(v - prev, 1)
            prev = v
        for k, v in (ls_ex.get("async") or {}).items():
            phases[f"O4_extra_open_async_{k}"] = v
    return phases


# ── 聚合与报告 ──────────────────────────────────────────────────────────

KEY_GROUPS = [
    ("A. 进程/壳（启动到页面开始加载）", [
        "A0_launch_to_child_entry", "B0_launch_to_launcher_ready", "B1_create_window_ms",
        "B2_http_server_start_ms", "B3_launch_to_http_server_ready", "A1_launch_to_page_nav_start",
    ]),
    ("B. 页面加载（HTML + 50 个 JS/CSS）", [
        "A2_page_nav_to_dom_interactive", "A3_page_nav_to_dcl", "A4_page_nav_to_load_end",
        "C1_page_nav_to_document_start", "C3_page_nav_to_load", "C14_page_nav_to_fileTree",
    ]),
    ("C. 桥/状态：开库到自动打开（阻塞首文档的部分）", [
        "C4_page_nav_to_bridge_ready", "C5_page_nav_to_api_hooked", "C7_page_nav_to_kbPath",
        "C8_page_nav_to_files", "C9_page_nav_to_graphData", "C10_page_nav_to_validateReport",
        "C11_page_nav_to_currentPath", "F1_graph_data_render_ms", "F2_get_graph_data_rpc_ms",
        "F3_validate_window_ms", "F4_validate_done_to_open_start_ms",
    ]),
    ("D. 打开首个文件内部（产品 _lastSwitch 分段）", [
        "E0_openFile_total_ms", "E2_open_stash_delta", "E2_open_load_delta", "E2_open_editor_delta",
        "E2_open_viewIn_delta", "E2_open_render_delta", "E2_open_settle_delta", "E2_open_tail_delta",
        "E3_open_async_paint", "E3_open_async_mathjax", "E3_open_async_frame1",
        "C12_page_nav_to_previewBlocks", "C13_page_nav_to_editorLines",
    ]),
    ("E. 总账", [
        "D2_launch_to_first_doc_visible", "Z_total_launch_to_first_doc_reload",
        "N5_first_launch_to_currentPath", "N6_first_launch_to_previewBlocks",
    ]),
    ("F. 稳态 openFile（--extra-open，与 boot 期首开区分）", [
        "O1_extra_open_ms", "O3_extra_open_stash_delta", "O3_extra_open_load_delta",
        "O3_extra_open_editor_delta", "O3_extra_open_viewIn_delta", "O3_extra_open_render_delta",
        "O3_extra_open_settle_delta", "O3_extra_open_tail_delta",
        "O4_extra_open_async_paint", "O4_extra_open_async_mathjax",
    ]),
]


def aggregate(runs: list[dict]) -> dict:
    keys: dict[str, list[float]] = {}
    for r in runs:
        for k, v in (r.get("phases") or {}).items():
            if isinstance(v, (int, float)):
                keys.setdefault(k, []).append(float(v))
    agg = {}
    for k, vals in keys.items():
        agg[k] = {
            "n": len(vals),
            "p50": round(statistics.median(vals), 1),
            "min": round(min(vals), 1),
            "max": round(max(vals), 1),
            "spread": round(max(vals) - min(vals), 1),
            "values": [round(v, 1) for v in vals],
        }
    return agg


def _fmt_row(name: str, a: dict | None) -> str:
    if not a:
        return f"| `{name}` | — | — | — | — | — |"
    return f"| `{name}` | {a['n']} | **{a['p50']}** | {a['min']} | {a['max']} | {a['spread']} |"


def write_markdown(label: str, campaign: dict) -> str:
    agg = campaign["aggregate"]
    lines: list[str] = []
    lines.append(f"# 冷启动分阶段时间线（boot profile · {label}）")
    lines.append("")
    lines.append("> 由 `scripts/benchmark/surface/run_boot_profile.py` 生成。**真机 WebView2 + 真实窗口**；"
                 "每轮独立进程、独立空配置目录、独立 CDP 端口。")
    lines.append("")
    mc = campaign["machine"]
    lines.append("## 口径")
    lines.append("")
    lines.append(f"- 机器：{mc.get('cpuCount')} 逻辑核，起测 CPU 负载 {mc.get('cpuLoadPercentAtStart', '?')}%，"
                 f"空闲内存 {mc.get('freePhysicalMemoryKB', '?')} KB")
    conc = mc.get("concurrentMeasurements") or []
    lines.append(f"- 并发：起测时检测到 **{len(conc)} 个其它测量进程**"
                 f"（{'; '.join((x.get('name') or '?') + ':' + str(x.get('cmd', ''))[:80] for x in conc) or '无'}）；"
                 f"用户 Memoria.exe 实例 {mc.get('memoriaExeProcesses', '?')} 个，"
                 f"WebView2 进程 {mc.get('webview2Processes', '?')} 个")
    lines.append(f"- 构建身份：git `{str(mc.get('gitHead'))[:12]}` dirty={mc.get('gitDirty')}；"
                 f"python {str(mc.get('python', '')).split()[0] if mc.get('python') else '?'}")
    lines.append(f"- KB：`{campaign['kbWorkCopy']}`（{campaign['kbStats']['mdFiles']} 个 md / "
                 f"{campaign['kbStats']['mdBytes']} bytes；从 {campaign['kbSource']} 复制，**冻结语料只读**）")
    lines.append(f"- 轮数：{len(campaign['runs'])}；端口：{campaign['ports']}")
    lines.append("- 计时零点 = 父进程 `Popen` 返回时刻；浏览器侧 epoch = `performance.timeOrigin + startTime`。")
    lines.append("- `first*` 前缀 = **首次导航**（真实用户路径，node 侧 100ms 轮询，精度 ±100ms）。")
    lines.append("- 其余阶段 = **注入式重载**（`Page.addScriptToEvaluateOnNewDocument` 在 document_start 打点，"
                 "毫秒级；资产已从 OS 缓存读，比首次导航略快）。")
    lines.append("")

    lines.append("## 分阶段 ms 表（P50 / min / max / spread）")
    lines.append("")
    total_runs = len(campaign["runs"])
    lines.append(f"（n = 该阶段在 {total_runs} 轮中取到值的次数）")
    lines.append("")
    unused = set(agg.keys())
    for title, names in KEY_GROUPS:
        lines.append(f"### {title}")
        lines.append("")
        lines.append("| 阶段 | n | P50 | min | max | spread |")
        lines.append("|---|---|---|---|---|---|")
        for n in names:
            if n in agg:
                lines.append(_fmt_row(n, agg[n]))
                unused.discard(n)
        lines.append("")
    if unused:
        lines.append("### 其它读数（未归组，供参考）")
        lines.append("")
        lines.append("| 阶段 | n | P50 | min | max | spread |")
        lines.append("|---|---|---|---|---|---|")
        for n in sorted(unused):
            if n.startswith(("R_", "E1_", "C2_", "C6_", "N1_", "N2_", "N3_", "N4_", "N7_", "A4b_", "D1_", "G")):
                lines.append(_fmt_row(n, agg[n]))
        lines.append("")

    # 逐轮结果
    lines.append("## 逐轮（一致性）")
    lines.append("")
    lines.append("| 轮 | ok | wall(s) | 首次→currentPath | 首次→previewBlocks | 重载→首文档可见 | openFile 总 | async.paint |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in campaign["runs"]:
        ph = r.get("phases") or {}
        lines.append("| {i} | {ok} | {w} | {a} | {b} | {c} | {d} | {e} |".format(
            i=r["index"], ok="✅" if r.get("ok") else "❌", w=r.get("wallSeconds"),
            a=ph.get("N5_first_launch_to_currentPath", "—"),
            b=ph.get("N6_first_launch_to_previewBlocks", "—"),
            c=ph.get("D2_launch_to_first_doc_visible", "—"),
            d=ph.get("E0_openFile_total_ms", "—"),
            e=ph.get("E3_open_async_paint", "—"),
        ))
    lines.append("")
    if any((r.get("probe") or {}).get("extraOpen") for r in campaign["runs"]):
        lines.append("### 稳态 openFile 明细（`--extra-open`）")
        lines.append("")
        lines.append("| 轮 | 文档 | 行数 | viewMode | openFile ms | load | editor | render | settle | tail | async.paint |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in campaign["runs"]:
            ex = (r.get("probe") or {}).get("extraOpen") or {}
            if not ex:
                continue
            ph = r.get("phases") or {}
            rt = ex.get("runtime") or {}
            lines.append("| {i} | `{p}` | {n} | {v} | {ms} | {load} | {ed} | {rd} | {st} | {tl} | {pt} |".format(
                i=r["index"], p=ex.get("path"), n=rt.get("docLines", "—"), v=rt.get("viewMode", "—"),
                ms=ph.get("O1_extra_open_ms", "—"),
                load=ph.get("O3_extra_open_load_delta", "—"),
                ed=ph.get("O3_extra_open_editor_delta", "—"),
                rd=ph.get("O3_extra_open_render_delta", "—"),
                st=ph.get("O3_extra_open_settle_delta", "—"),
                tl=ph.get("O3_extra_open_tail_delta", "—"),
                pt=ph.get("O4_extra_open_async_paint", "—"),
            ))
        lines.append("")

    # RPC 表
    lines.append("## 页面侧 RPC 往返（注入轮，P50）")
    lines.append("")
    lines.append("| RPC | n | P50 ms |")
    lines.append("|---|---|---|")
    rpc_keys = sorted((k for k in agg if k.startswith("R_") and k.endswith("_ms")))
    for k in rpc_keys:
        lines.append(f"| `{k[2:-3]}` | {agg[k]['n']} | {agg[k]['p50']} |")
    lines.append("")

    # 后端 span 表
    lines.append("## 后端服务端净执行（子进程 span，P50）")
    lines.append("")
    lines.append("| span | n | P50 ms | max ms |")
    lines.append("|---|---|---|---|")
    for k, a in sorted(campaign.get("backendSpans", {}).items(), key=lambda kv: -kv[1]["p50"]):
        lines.append(f"| `{k}` | {a['n']} | {a['p50']} | {a['max']} |")
    lines.append("")

    # 可延后估算
    lines.append("## 哪些阶段可以延后（用实测时间戳估算收益）")
    lines.append("")
    def g(k):
        return (agg.get(k) or {}).get("p50")
    rows = []
    v_validate = g("F3_validate_window_ms") or g("R_validate_kb_ms")
    v_graph_rpc = g("F2_get_graph_data_rpc_ms")
    v_graph_render = g("F1_graph_data_render_ms")
    v_labels_rpc = g("R_suggest_group_labels_ms")
    v_open = g("E0_openFile_total_ms")
    v_paint = g("E3_open_async_paint")
    v_link = g("R_get_link_targets_ms")
    v_files = g("R_list_files_ms")
    for name, ms_, can, counted in (
        ("全库校验 `validate_kb`（完整性+manifest+path+图谱审计，全部文件）", v_validate, True, True),
        ("图谱数据 `get_graph_data`（全库解析 + graph audit）", v_graph_rpc, True, True),
        ("图谱分组命名 `suggest_group_labels`（**诊断项**：F1 窗口内的主体）", v_labels_rpc, True, False),
        ("图谱分组标签窗口（graphData 写入 → 校验开始；F1 已含 suggest）", v_graph_render, True, True),
        ("`get_link_targets`（wikilink 目标索引）", v_link, True, True),
        ("`list_files`（文件树数据）", v_files, False, False),
        ("openFile 总耗时（必须：用户要看到文件）", v_open, False, False),
        ("预览 paint（必须：用户要看到内容）", v_paint, False, False),
    ):
        if ms_ is None:
            continue
        rows.append((name, round(ms_, 1), "可延后" if can else "必须", round(ms_, 1) if can else 0, counted))
    lines.append("| 阶段 | P50 ms | 判定 | 延后收益（该阶段直接省掉） | 计入合计 |")
    lines.append("|---|---|---|---|---|")
    for name, ms_, verdict, gain, counted in rows:
        lines.append(f"| {name} | {ms_} | {verdict} | {gain} ms | {'是' if counted else '否（避免重复计）'} |")
    lines.append("")
    blocking = sum(x[3] for x in rows if x[2] == "可延后" and x[4])
    lines.append(f"**可延后项 P50 合计 ≈ {round(blocking, 1)} ms**（前提：它们都在 openFile 之前被 await，"
                 f"实测顺序见 app.js `initKb()`；延后不改变一致性语义时才有此收益）。")
    lines.append("")

    # 结论
    lines.append("## 结论（由数据直接读出）")
    lines.append("")
    top = []
    for k, a in agg.items():
        if k.startswith(("F3_", "F1_", "F2_", "E0_", "E3_open_async_paint", "A4_page_nav_to_load_end",
                         "B0_launch_to_launcher_ready", "A1_launch_to_page_nav_start")):
            top.append((k, a["p50"]))
    top.sort(key=lambda kv: -kv[1])
    lines.append("P50 从大到小的主要耗时段：")
    lines.append("")
    for k, v in top[:10]:
        lines.append(f"- `{k}` = **{v} ms**")
    lines.append("")
    if campaign.get("notes"):
        lines.append("### 测量说明/限制")
        lines.append("")
        for n in campaign["notes"]:
            lines.append(f"- {n}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--label", default="")
    ap.add_argument("--port", type=int, default=9661, help="基底端口（每轮 +idx；建议 9660–9665）")
    ap.add_argument("--kb", default=str(DEFAULT_KB), help="KB 源（只读；会复制到 %%TEMP%% 工作副本）")
    ap.add_argument("--kb-work", default="", help="复用已有工作副本（默认每次新建）")
    ap.add_argument("--no-reload", action="store_true", help="不做注入式重载（只量首次导航）")
    ap.add_argument("--extra-open", default="", help="重载完成后额外 openFile 该相对路径（稳态开文档）")
    ap.add_argument("--extra-open-view", default="", choices=["", "source", "preview", "split"],
                    help="额外 openFile 前先切到该视图（测「恢复到预览视图」的体感成本）")
    ap.add_argument("--boot-timeout", type=int, default=120000)
    ap.add_argument("--reload-timeout", type=int, default=120000)
    ap.add_argument("--probe-timeout", type=int, default=420)
    ap.add_argument("--settle", type=float, default=2.0)
    ap.add_argument("--keep-temp", action="store_true")
    args = ap.parse_args()
    _utf8_stdio()

    label = args.label or time.strftime("boot-%Y%m%d-%H%M%S")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # KB 工作副本（冻结语料只读 → 用副本）
    kb_src = Path(args.kb).resolve()
    if not (kb_src / ".memoria").is_dir() and not any(kb_src.glob("*.md")):
        log(f"KB 源不存在或不是知识库：{kb_src}")
        return 2
    if args.kb_work:
        kb_work = Path(args.kb_work).resolve()
    else:
        kb_work = TEMP_ROOT / "kb"
        if kb_work.exists():
            shutil.rmtree(kb_work, ignore_errors=True)
        log(f"copy KB {kb_src} -> {kb_work}")
        shutil.copytree(kb_src, kb_work)
    md_files = list(kb_work.rglob("*.md"))
    kb_stats = {"mdFiles": len(md_files), "mdBytes": sum(p.stat().st_size for p in md_files)}

    machine = machine_context()
    machine["kbSource"] = str(kb_src)
    log(f"machine: {machine.get('cpuCount')} cores, load={machine.get('cpuLoadPercentAtStart')}%, "
        f"git={str(machine.get('gitHead'))[:12]} dirty={machine.get('gitDirty')}")
    log(f"kb: {kb_stats}")

    runs: list[dict] = []
    for i in range(args.runs):
        try:
            r = run_once(i, args, kb_work)
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            r = {"index": i, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
        runs.append(r)
        log(f"run#{i} ok={r.get('ok')} err={r.get('error') or ''} wall={r.get('wallSeconds')}s")
        # 轮间冷却：让上轮 WebView2/磁盘缓存状态落地（同时避免连续测量互相干扰）
        if i + 1 < args.runs:
            time.sleep(3.0)

    agg = aggregate(runs)
    backend_spans: dict[str, list[float]] = {}
    for r in runs:
        for s in ((r.get("backend") or {}).get("spans") or []):
            name = s.get("name") or ""
            if name.startswith(("UIAPI.", "DocumentService.", "graph.", "storage.", "services.", "webview.")):
                if isinstance(s.get("ms"), (int, float)):
                    backend_spans.setdefault(name, []).append(float(s["ms"]))
    backend_agg = {
        k: {"n": len(v), "p50": round(statistics.median(v), 1), "max": round(max(v), 1)}
        for k, v in backend_spans.items()
    }

    notes = [
        "首次导航的桥/状态里程碑由 node 侧每 100ms 轮询得到（±100ms），用于给「真实用户路径」定位；"
        "毫秒级拆分取自同一进程内的注入式重载。",
        "注入式重载时 50 个 JS 已从 OS 文件缓存读，load_end 等数值偏低；**瓶颈归属**（哪段在等什么）不受影响。",
        "本轮为**开发态源码启动**（python 直接跑），不含 PyInstaller 冻结包的自解压时间 ⇒ 用户实测的"
        "13–23s 里若含冻结启动成本，本表之外还有一段（见 machine 字段与结论的说明）。",
        "配置目录每轮为空 ⇒ 相当于「首次打开该 KB」；lastPath 恢复分支未覆盖（如需请用 --extra-open 或后续补测）。",
    ]
    if args.extra_open:
        notes.append(f"额外测量了稳态 openFile(`{args.extra_open}`)（见 runs[*].probe.extraOpen）。")

    campaign = {
        "schema": "memoria-boot-timeline/v1",
        "label": label,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "kbSource": str(kb_src),
        "kbWorkCopy": str(kb_work),
        "kbStats": kb_stats,
        "ports": [args.port + i for i in range(args.runs)],
        "machine": machine,
        "runs": runs,
        "aggregate": agg,
        "backendSpans": backend_agg,
        "notes": notes,
    }

    out_json = RESULTS_DIR / f"boot-timeline-{label}.json"
    out_md = RESULTS_DIR / f"boot-timeline-{label}.md"
    out_json.write_text(json.dumps(campaign, ensure_ascii=False, indent=2, default=str), "utf-8")
    out_md.write_text(write_markdown(label, campaign), "utf-8")
    log(f"wrote {out_json}")
    log(f"wrote {out_md}")

    if not args.keep_temp:
        for i in range(args.runs):
            shutil.rmtree(TEMP_ROOT / f"run_{label}_{i}", ignore_errors=True)

    ok_runs = sum(1 for r in runs if r.get("ok"))
    log(f"done: {ok_runs}/{len(runs)} runs ok")
    return 0 if ok_runs == len(runs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
