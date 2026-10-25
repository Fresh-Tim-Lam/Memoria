"""task-93 只读盘点：真机两档视口测量（1256×774 / 1600×900），记录三栏几何与溢出。

不修改任何源码；窗口用 pywebview `window.resize()` 改**真实 OS 窗口**（harness `launch_ctl.py`
的本地控制口），不是 CDP 视口模拟 ⇒ CSS 断点 / ResizeObserver / WebView2 重排都走真实路径。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t93"
CDP_PORT = int(os.environ.get("T93_CDP_PORT", "9579"))
PY = str(REPO / ".venv" / "Scripts" / "python.exe")


def http_json(url: str):
    with urllib.request.urlopen(url, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def wait_cdp(timeout_s: float = 150.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            return http_json(f"http://127.0.0.1:{CDP_PORT}/json/version")
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    raise RuntimeError("CDP 未就绪")


def node_eval(expr: str) -> dict:
    script = f"""
const list = await (await fetch('http://127.0.0.1:{CDP_PORT}/json/list')).json();
const t = list.find(x => x.type === 'page' && String(x.url).startsWith('http://127.0.0.1'));
if (!t) {{ console.log(JSON.stringify({{error:'no target'}})); process.exit(0); }}
const ws = new WebSocket(t.webSocketDebuggerUrl);
await new Promise((res, rej) => {{ ws.onopen = res; ws.onerror = () => rej(new Error('ws')); }});
let id = 0; const pending = new Map();
ws.onmessage = (ev) => {{
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {{ const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }}
}};
const send = (method, params = {{}}) => new Promise((resolve, reject) => {{ const i = ++id; pending.set(i, {{resolve, reject}}); ws.send(JSON.stringify({{id: i, method, params}})); }});
await send('Runtime.enable');
const r = await send('Runtime.evaluate', {{ expression: {json.dumps(expr)}, awaitPromise: true, returnByValue: true, userGesture: true }});
console.log(JSON.stringify(r && r.result ? r.result.value : {{error: 'no result'}}));
process.exit(0);
"""
    p = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    out = (p.stdout or "").strip().splitlines()
    return json.loads(out[-1]) if out else {"error": (p.stderr or "")[-600:]}


def find_our_apps() -> list[int]:
    cmd = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        "Where-Object { $_.CommandLine -like '*0.4.7-task-93-responsive*launch_ctl.py*' } | "
        "Select-Object -ExpandProperty ProcessId"
    )
    p = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return [int(x) for x in re.findall(r"\d+", p.stdout or "")]


def kill_ours() -> None:
    for pid in find_our_apps():
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    time.sleep(1.0)


def resize_to(inner_w: int, inner_h: int) -> dict:
    cmd = WORK / "cmd.json"
    ack = WORK / "ack.json"
    if ack.exists():
        ack.unlink()
    cmd.write_text(json.dumps({"w": inner_w, "h": inner_h}), encoding="utf-8")
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            if ack.is_file() and json.loads(ack.read_text(encoding="utf-8")).get("ok"):
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.2)
    time.sleep(1.2)  # 等 CSS transition(0.18s) + ResizeObserver 落定
    return node_eval("(() => ({ innerW: window.innerWidth, innerH: window.innerHeight }))()")


GEOM = """(() => {
  const g = (sel) => { const e = document.querySelector(sel); if (!e) return null; const r = e.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height), x: Math.round(r.left) }; };
  const content = document.querySelector('#content');
  const dock = document.querySelector('#-agent-dock');
  const sidebar = document.querySelector('#-sidebar');
  return {
    innerW: window.innerWidth, innerH: window.innerHeight,
    main: g('#main'), sidebar: g('#-sidebar'), content: g('#content'), dock: g('#-agent-dock'),
    sidebarCollapsed: !!(sidebar && sidebar.classList.contains('-sidebar--collapsed')),
    dockCollapsed: !!(dock && dock.classList.contains('-agent-dock--collapsed')),
    dockAutoHidden: !!(dock && dock.classList.contains('-agent-dock--auto-hidden')),
    contentScrollW: content ? content.scrollWidth : null,
    docScrollW: document.documentElement.scrollWidth,
    viewMode: (window.MemoriaApp && window.MemoriaApp.state && window.MemoriaApp.state.viewMode) || '',
    overflowX: document.documentElement.scrollWidth > window.innerWidth + 1,
  };
})()"""


def main() -> int:
    kill_ours()
    env = dict(os.environ)
    env.update(
        {
            "T93_WORK": str(WORK),
            "T93_CDP_PORT": str(CDP_PORT),
            "MEMORIA_CONFIG_DIR": str(WORK / "cfg"),
            "MEMORIA_KB": str(WORK / "kb"),
            "MEMORIA_FRAMELESS": "0",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    env.pop("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", None)
    os.makedirs(WORK, exist_ok=True)
    if (WORK / "kb").exists():
        shutil.rmtree(WORK / "kb")
    os.makedirs(WORK / "cfg", exist_ok=True)
    shutil.copytree(REPO / "tests" / "probe-kb", WORK / "kb")
    (WORK / "cfg" / "agent.json").write_text('{"enabled": false}', encoding="utf-8")

    out = (WORK / "app.out.log").open("w", encoding="utf-8")
    err = (WORK / "app.err.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([PY, str(HERE / "launch_ctl.py")], cwd=str(REPO), env=env, stdout=out, stderr=err)
    print("app pid", proc.pid)
    try:
        wait_cdp()
        time.sleep(6)
        results = []
        for target in ((1256, 774), (1600, 900)):
            got = resize_to(*target)
            iw, ih = int(got.get("innerW", 0)), int(got.get("innerH", 0))
            # 若 pywebview resize 设的是 outer/略有偏差 ⇒ 按差值迭一次
            if abs(iw - target[0]) > 4 or abs(ih - target[1]) > 4:
                got = resize_to(target[0] + (target[0] - iw), target[1] + (target[1] - ih))
            geom = node_eval(GEOM)
            geom["target"] = {"w": target[0], "h": target[1]}
            results.append(geom)
            print(json.dumps(geom, ensure_ascii=False))
        (HERE / "measure.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close()
        err.close()
        kill_ours()
        webviews = (
            "Get-CimInstance Win32_Process -Filter \"Name='msedgewebview2.exe'\" | "
            f"Where-Object {{ $_.CommandLine -like '*--remote-debugging-port={CDP_PORT}*' }} | Select-Object -ExpandProperty ProcessId"
        )
        p = subprocess.run(["powershell", "-NoProfile", "-Command", webviews], capture_output=True, text=True, encoding="utf-8", errors="replace")
        for pid in re.findall(r"\d+", p.stdout or ""):
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
