"""task-133 真机验证编排器：种子 → 桩端点 → **真实 Memoria 应用** → CDP 驱动 → 证据判定。

只写 `artifacts/agent/verify/todo/0.4.7-task-91-realmachine/`、独立 KB 与独立配置目录：
- 用户真实配置：`MEMORIA_CONFIG_DIR` 指向独立临时目录，**不读不写用户 config**；
- 用户知识库：用 `tests/probe-kb` 的临时副本，**不碰 `docs/example/AAA_Vocab`**；
- 用户正在运行的 `Package\\Memoria.exe`：**只读不动**；清理只杀本次自己启动的 pid（身份校验后）。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t133"
CDP_PORT = int(os.environ.get("T133_CDP_PORT", "9577"))
STUB_PORT = int(os.environ.get("T133_STUB_PORT", "9599"))
PY = str(REPO / ".venv" / "Scripts" / "python.exe")


def log(msg: str) -> None:
    print("[t133] " + msg, flush=True)


def http_json(url: str, timeout: float = 3.0):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wait_cdp(timeout_s: float = 90.0) -> dict:
    deadline = time.time() + timeout_s
    last = ""
    while time.time() < deadline:
        try:
            return http_json(f"http://127.0.0.1:{CDP_PORT}/json/version")
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
            time.sleep(0.5)
    raise RuntimeError(f"CDP 未在 {timeout_s}s 内就绪：{last}")


def _ps(cmd: str) -> str:
    proc = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (proc.stdout or "") + (proc.stderr or "")


def find_our_app_pids() -> list[int]:
    """找出「命令行里带本 harness 的 launch_app.py」的 python 进程（不碰用户 Package\\Memoria.exe）。"""
    out = _ps(
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        "Where-Object { $_.CommandLine -like '*0.4.7-task-91-realmachine*launch_app.py*' } | "
        "Select-Object -ExpandProperty ProcessId"
    )
    return [int(x) for x in re.findall(r"\d+", out)]


def kill_our_app() -> list[str]:
    killed: list[str] = []
    for pid in find_our_app_pids():
        # 二次身份校验：命令行必须含本 harness 路径，绝不 /T（绝不杀进程树）
        out = _ps(f"(Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\").CommandLine")
        if "0.4.7-task-91-realmachine" not in out or "launch_app.py" not in out:
            killed.append(f"skip {pid}（身份校验未过）")
            continue
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        killed.append(f"killed {pid}")
    time.sleep(1.5)
    # 清理本次遗留的 WebView2 子进程：按**本次唯一 CDP 端口**精确匹配（绝不按端口反查父进程）
    out = _ps(
        "Get-CimInstance Win32_Process -Filter \"Name='msedgewebview2.exe'\" | "
        f"Where-Object {{ $_.CommandLine -like '*--remote-debugging-port={CDP_PORT}*' }} | "
        "ForEach-Object { \"$($_.ProcessId)|$($_.ExecutablePath)|$($_.CommandLine)\" }"
    )
    for line in [x for x in out.splitlines() if x.strip()]:
        parts = line.split("|", 2)
        if len(parts) < 3:
            continue
        pid_s, exe, cmd = parts
        if "Package\\Memoria.exe" in cmd or (exe and exe.lower().endswith("package\\memoria.exe")):
            continue  # 用户应用：绝不碰
        try:
            subprocess.run(["taskkill", "/PID", pid_s.strip(), "/F"], capture_output=True)
            killed.append(f"orphan-webview {pid_s.strip()}")
        except Exception:  # noqa: BLE001
            pass
    return killed


def parse_session(kb: str, sid: str) -> dict:
    path = Path(kb) / ".memoria" / "agent" / "sessions" / f"{sid}.jsonl"
    events = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    compactions = [
        {
            "seq": e.get("seq"),
            "shadowed": len((e.get("data") or {}).get("shadowed") or []),
            "summary_chars": len(str((e.get("data") or {}).get("summary") or "")),
            "model": (e.get("data") or {}).get("model"),
        }
        for e in events
        if e.get("type") == "compaction"
    ]
    users = [e for e in events if e.get("type") == "user/message"]
    loops = [e for e in events if e.get("type") == "loop/end"]
    return {
        "path": str(path),
        "event_count": len(events),
        "compactions": compactions,
        "user_messages": len(users),
        "loop_end": len(loops),
        "last_type": events[-1].get("type") if events else None,
        "total_lines": len(events),
    }


def pct_from_text(text: str) -> int | None:
    m = re.search(r"压缩预算\s*(\d+)%", text or "")
    return int(m.group(1)) if m else None


def times_from_text(text: str) -> int | None:
    m = re.search(r"已压缩\s*(\d+)\s*次", text or "")
    return int(m.group(1)) if m else None


def main() -> int:
    for stale in find_our_app_pids():
        log(f"清理上次遗留实例 pid={stale}")
    kill_our_app()

    env = dict(os.environ)
    env.update(
        {
            "T133_WORK": str(WORK),
            "T133_CDP_PORT": str(CDP_PORT),
            "T133_STUB_PORT": str(STUB_PORT),
            "MEMORIA_CONFIG_DIR": str(WORK / "cfg"),
            "MEMORIA_KB": str(WORK / "kb"),
            "MEMORIA_FRAMELESS": "0",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    env.pop("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", None)

    # ① 种子
    seed = subprocess.run([PY, str(HERE / "seed.py")], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    log("seed: " + (seed.stdout or "").strip())
    if seed.returncode != 0:
        log("seed 失败：" + (seed.stderr or "")[-1500:])
        return 1

    # ② 桩端点（进程内线程）
    # 注意：桩模块在 **import 时**读 T133_WORK 决定日志路径 ⇒ 必须先把 env 写进本进程
    os.environ.update(env)
    sys.path.insert(0, str(HERE))
    from stub_llm import serve_forever  # noqa: E402

    server = serve_forever(STUB_PORT)
    log(f"stub LLM on 127.0.0.1:{STUB_PORT}")

    # ③ 启动真实应用
    out_log = (WORK / "app.out.log").open("w", encoding="utf-8")
    err_log = (WORK / "app.err.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [PY, str(HERE / "launch_app.py")],
        cwd=str(REPO),
        env=env,
        stdout=out_log,
        stderr=err_log,
    )
    log(f"app pid={proc.pid}")
    result: dict = {"app_pid": proc.pid, "cdp_port": CDP_PORT, "stub_port": STUB_PORT}
    try:
        version = wait_cdp(120)
        result["cdp"] = {"Browser": version.get("Browser"), "Protocol-Version": version.get("Protocol-Version")}
        log("CDP ready: " + str(version.get("Browser")))

        # ④ 驱动
        drive = subprocess.run(
            ["node", str(HERE / "drive.mjs"), "--port", str(CDP_PORT), "--out", str(HERE)],
            cwd=str(HERE),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        result["driver"] = {"rc": drive.returncode, "stdout": (drive.stdout or "").strip()[-2000:], "stderr": (drive.stderr or "").strip()[-3000:]}
        log("driver rc=" + str(drive.returncode))
        if drive.returncode != 0:
            log("driver stderr: " + (drive.stderr or "")[-2000:])
    finally:
        killed = kill_our_app()
        result["cleanup"] = killed
        out_log.close()
        err_log.close()
        server.shutdown()

    # ⑤ 证据判定
    seed_info = json.loads((WORK / "seed.json").read_text(encoding="utf-8"))
    session = parse_session(seed_info["kb"], seed_info["session_id"])
    stub_log = WORK / "stub-requests.jsonl"
    stub_requests = []
    if stub_log.is_file():
        stub_requests = [json.loads(x) for x in stub_log.read_text(encoding="utf-8").splitlines() if x.strip()]

    dom = {}
    for name in ("pre", "post", "reload"):
        path = HERE / f"dom-{name}.json"
        dom[name] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    pre_txt = (dom.get("pre") or {}).get("statusText", "")
    post_txt = (dom.get("post") or {}).get("statusText", "")
    reload_txt = (dom.get("reload") or {}).get("statusText", "")
    driver_file = HERE / "driver-result.json"
    driver_result = json.loads(driver_file.read_text(encoding="utf-8")) if driver_file.is_file() else {}
    checks = {
        "1_real_compaction_event": bool(session["compactions"]),
        "2a_pre_screenshot": (HERE / "pre.png").is_file() and (HERE / "pre.png").stat().st_size > 5000,
        "2b_post_screenshot": (HERE / "post.png").is_file() and (HERE / "post.png").stat().st_size > 5000,
        "2c_reload_screenshot": (HERE / "reload.png").is_file() and (HERE / "reload.png").stat().st_size > 5000,
        "2d_element_clips": all(
            (HERE / name).is_file() and (HERE / name).stat().st_size > 3000
            for name in ("status-pre.png", "status-post.png", "status-reload.png", "system-row-reload.png")
        ),
        "3a_percent_dropped": (
            pct_from_text(pre_txt) is not None
            and pct_from_text(post_txt) is not None
            and pct_from_text(post_txt) < pct_from_text(pre_txt)
        ),
        "3b_times_plus_one": (
            times_from_text(post_txt) is not None
            and times_from_text(post_txt) == (times_from_text(pre_txt) or 0) + 1
        ),
        "4_reload_system_row_kept": (dom.get("reload") or {}).get("systemRows", 0) >= 1
        and "已压缩" in " ".join((dom.get("reload") or {}).get("systemTexts") or []),
        "5_stub_saw_compaction_call": any(r.get("kind") == "compaction" for r in stub_requests),
        "6_gpu_is_real": bool((driver_result.get("gpu") or {}).get("webgl")),
    }
    result.update(
        {
            "seed": seed_info,
            "session": session,
            "stub_requests": stub_requests,
            "dom": dom,
            "percent": {"pre": pct_from_text(pre_txt), "post": pct_from_text(post_txt), "reload": pct_from_text(reload_txt)},
            "times": {"pre": times_from_text(pre_txt), "post": times_from_text(post_txt), "reload": times_from_text(reload_txt)},
            "checks": checks,
            "pass": all(checks.values()),
        }
    )
    (HERE / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 70)
    print("compaction events:", json.dumps(session["compactions"], ensure_ascii=False))
    print("percent pre/post/reload:", result["percent"])
    print("times   pre/post/reload:", result["times"])
    print("systemRows reload:", (dom.get("reload") or {}).get("systemRows"), (dom.get("reload") or {}).get("systemTexts"))
    print("checks:", json.dumps(checks, ensure_ascii=False))
    print("PASS" if result["pass"] else "FAIL")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
