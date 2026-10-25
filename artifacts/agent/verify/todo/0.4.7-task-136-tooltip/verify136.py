"""task-136 真机验证：左栏开关三态 tooltip（自动折叠 / 用户折叠 / 展开）+ 视觉弱强调对比。

真机：真实 pywebview+WebView2 窗口；原生 title tooltip 用 OS 级截图（bundled Pillow）取证。
隔离：独立 MEMORIA_CONFIG_DIR / KB（tests/probe-kb 副本）；不碰用户 app / 配置 / docs/example。
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
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t136"
CDP_PORT = int(os.environ.get("T136_CDP_PORT", "9581"))
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
LAUNCH = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-93-responsive" / "launch_ctl.py"
PROBE = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-93-responsive" / "probe.mjs"
BUNDLED_PY = Path(r"D:\deepseek-harness\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe")
SHOTS = HERE / "shots"

EXPECT = {
    "auto": "空间不足，已自动收起；点击展开（空间不足时会收起对话栏）",
    "user": "展开文件树",
    "expanded": "收起侧栏",
}


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
    wcmd = (
        "Get-CimInstance Win32_Process -Filter \"Name='msedgewebview2.exe'\" | "
        f"Where-Object {{ $_.CommandLine -like '*--remote-debugging-port={CDP_PORT}*' }} | Select-Object -ExpandProperty ProcessId"
    )
    p = subprocess.run(["powershell", "-NoProfile", "-Command", wcmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
    for pid in re.findall(r"\d+", p.stdout or ""):
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    time.sleep(0.8)


def probe(cmds: list[dict]) -> list[dict]:
    cmd_file = WORK / "probe-cmd.json"
    cmd_file.write_text(json.dumps({"cmds": cmds}, ensure_ascii=False), encoding="utf-8")
    p = subprocess.run(
        ["node", str(PROBE), "--port", str(CDP_PORT), "--cmd", str(cmd_file)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
    )
    lines = (p.stdout or "").strip().splitlines()
    if not lines:
        raise RuntimeError("probe 无输出：" + (p.stderr or "")[-600:])
    data = json.loads(lines[-1])
    if not data.get("ok"):
        raise RuntimeError("probe 失败：" + json.dumps(data, ensure_ascii=False)[:400])
    return data["results"]


def ev(expr: str):
    return probe([{"action": "eval", "expr": expr}])[0].get("value")


def ctl(payload: dict) -> dict:
    ack = WORK / "ack.json"
    try:
        ack.unlink()
    except OSError:
        pass
    payload = dict(payload)
    payload["_seq"] = time.time_ns()  # 控制口会跳过"与上一条完全相同"的命令 ⇒ 必须带唯一序号
    (WORK / "cmd.json").write_text(json.dumps(payload), encoding="utf-8")
    deadline = time.time() + 8
    while time.time() < deadline:
        try:
            if ack.is_file():
                data = json.loads(ack.read_text(encoding="utf-8"))
                if data.get("req") == payload:
                    return data
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.1)
    return {"ok": False, "err": "ack timeout"}


def resize(inner_w: int, inner_h: int) -> dict:
    """真实 OS 窗口 resize（pywebview），迭代收敛到 inner 目标。"""
    tw, th = inner_w, inner_h
    got = None
    for _ in range(5):
        ctl({"op": "resize", "w": tw, "h": th})
        time.sleep(0.35)
        got = ev("(() => ({ innerW: window.innerWidth, innerH: window.innerHeight }))()")
        dw = int(got.get("innerW", inner_w)) - inner_w
        dh = int(got.get("innerH", inner_h)) - inner_h
        if abs(dw) <= 2 and abs(dh) <= 2:
            got["ok"] = True
            return got
        tw -= dw
        th -= dh
    return got or {"ok": False}


SNAP = """(() => {
  const b = document.querySelector('#btn-toggle-sidebar');
  const r = b.getBoundingClientRect();
  const cs = getComputedStyle(b);
  const rs = window.MemoriaApp.getResponsiveState();
  return {
    title: b.title,
    ariaLabel: b.getAttribute('aria-label'),
    ariaPressed: b.getAttribute('aria-pressed'),
    className: b.className,
    color: cs.color,
    rect: { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) },
    autoCollapsed: rs.sidebarAutoCollapsed,
    userCollapsed: rs.sidebarUserCollapsed,
    sidebarCollapsedClass: document.querySelector('#-sidebar').classList.contains('-sidebar--collapsed'),
  };
})()"""


def snap() -> dict:
    return ev(SNAP)


def hover(rect: dict) -> None:
    x = rect["x"] + rect["w"] // 2
    y = rect["y"] + rect["h"] // 2
    probe([{"action": "mouse", "type": "mouseMoved", "x": x, "y": y, "button": "none"}])
    time.sleep(1.4)  # 原生 tooltip 约 0.5~1s 出现


def os_shot(name: str, rect: dict) -> dict:
    # 顺序关键：先置顶+激活（会作废已弹出的 tooltip），再把**真实 OS 光标**移到按钮上
    # （CDP 合成 mouseMoved 不触发原生 title tooltip），等 tooltip 出现后抓屏。
    fg = ctl({"op": "foreground"})
    if not fg.get("ok"):
        return {"ok": False, "err": fg}
    win = fg["rect"]
    origin = ctl({"op": "clientorigin"})
    if not origin.get("ok"):
        return {"ok": False, "err": origin}
    sx = origin["x"] + rect["x"] + rect["w"] // 2
    sy = origin["y"] + rect["y"] + rect["h"] // 2
    ctl({"op": "hover", "x": sx, "y": sy})
    time.sleep(1.6)  # 原生 tooltip 约 0.5~1s 出现
    tips = ctl({"op": "tooltips", "needles": [EXPECT["auto"], EXPECT["user"], EXPECT["expanded"]]})
    SHOTS.mkdir(parents=True, exist_ok=True)
    out = SHOTS / name
    p = subprocess.run(
        [str(BUNDLED_PY), str(HERE / "grab.py"), str(win["x"]), str(win["y"]), str(win["w"]), str(win["h"]), str(out)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    ok = out.is_file() and out.stat().st_size > 1000
    # 再裁一张按钮附近的小图（自动折叠 vs 用户折叠的弱强调对比证据）
    crop = SHOTS / name.replace(".png", "_button_crop.png")
    pad = 14
    cx = origin["x"] - win["x"] + rect["x"] - pad
    cy = origin["y"] - win["y"] + rect["y"] - pad
    cw = rect["w"] + pad * 2
    ch = rect["h"] + pad * 2
    subprocess.run(
        [str(BUNDLED_PY), str(HERE / "crop.py"), str(out), str(crop), str(cx), str(cy), str(cw), str(ch)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    return {
        "ok": ok,
        "path": str(out),
        "crop": str(crop) if crop.is_file() else None,
        "rect": win,
        "fg": fg,
        "origin": origin,
        "cursor": [sx, sy],
        "tooltipHits": tips.get("hits") if tips.get("ok") else None,
        "stdout": (p.stdout or "").strip()[-200:],
        "stderr": (p.stderr or "").strip()[-200:],
    }


def page_shot(name: str) -> dict:
    SHOTS.mkdir(parents=True, exist_ok=True)
    out = SHOTS / name
    probe([{"action": "shot", "path": str(out), "clipSelector": "#btn-toggle-sidebar"}])
    return {"ok": out.is_file(), "path": str(out)}


def click(sel: str) -> None:
    ev(f"(() => {{ const b = document.querySelector({json.dumps(sel)}); if (b) b.click(); return !!b; }})()")
    time.sleep(0.7)


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
    if (WORK / "cfg").exists():
        shutil.rmtree(WORK / "cfg")
    os.makedirs(WORK / "cfg", exist_ok=True)
    shutil.copytree(REPO / "tests" / "probe-kb", WORK / "kb")
    (WORK / "cfg" / "agent.json").write_text('{"enabled": false}', encoding="utf-8")
    for f in ("cmd.json", "ack.json", "probe-cmd.json"):
        try:
            (WORK / f).unlink()
        except OSError:
            pass

    out = (WORK / "app.out.log").open("w", encoding="utf-8")
    err = (WORK / "app.err.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([PY, str(LAUNCH)], cwd=str(REPO), env=env, stdout=out, stderr=err)
    print("app pid", proc.pid)
    result: dict = {"states": {}, "shots": {}, "checks": {}}
    try:
        wait_cdp()
        time.sleep(6)

        # ── A. 自动折叠态（1256×774 触发响应式） ─────────────────
        resize(1256, 774)
        time.sleep(0.9)
        a = snap()
        result["states"]["auto_1256"] = a
        hover(a["rect"])
        result["shots"]["auto_1256_tooltip"] = os_shot("auto_1256_tooltip.png", a["rect"])
        result["shots"]["auto_1256_button"] = page_shot("auto_1256_button.png")
        # 移开鼠标，避免 tooltip 干扰后续截图
        probe([{"action": "mouse", "type": "mouseMoved", "x": 700, "y": 400, "button": "none"}])
        time.sleep(0.4)

        # ── C. 展开态（1600×900，无联动） ────────────────────────
        resize(1600, 900)
        time.sleep(0.9)
        c = snap()
        result["states"]["expanded_1600"] = c
        hover(c["rect"])
        result["shots"]["expanded_1600_tooltip"] = os_shot("expanded_1600_tooltip.png", c["rect"])
        result["shots"]["expanded_1600_button"] = page_shot("expanded_1600_button.png")
        probe([{"action": "mouse", "type": "mouseMoved", "x": 700, "y": 400, "button": "none"}])
        time.sleep(0.4)

        # ── B. 用户折叠态（1600 下点按钮主动折叠） ───────────────
        click("#btn-toggle-sidebar")
        b = snap()
        result["states"]["user_1600"] = b
        hover(b["rect"])
        result["shots"]["user_1600_tooltip"] = os_shot("user_1600_tooltip.png", b["rect"])
        result["shots"]["user_1600_button"] = page_shot("user_1600_button.png")
        ctl({"op": "normal"})  # 取消临时置顶，恢复普通窗口

        # ── 判定 ──────────────────────────────────────────────
        # 说明：本机 WebView2 在 OS 截图里**不渲染原生 title tooltip**（用顶栏既有的
        # "后退 (Alt+←)" 按钮做对照也拍不到 tooltip，见 tooltip_probe.py）。
        # 因此 tooltip 的"可见性"用 DOM 的 title/aria-label 三态实测断言；按钮弱强调用
        # 真机截图裁剪对比。原生 tooltip 窗口文本扫描仅作信息项，不纳入 pass。
        checks = {
            "auto_title_exact": a["title"] == EXPECT["auto"],
            "auto_title_mentions_dock_tradeoff": "会收起对话栏" in a["title"],
            "auto_class_present": "-sidebar-auto-collapsed" in a["className"],
            "auto_color_is_theme": a["color"] not in ("", None),
            "auto_aria_equals_title": a["ariaLabel"] == a["title"],
            "user_title_exact": b["title"] == EXPECT["user"],
            "user_class_absent": "-sidebar-auto-collapsed" not in b["className"],
            "expanded_title_exact": c["title"] == EXPECT["expanded"],
            "expanded_class_absent": "-sidebar-auto-collapsed" not in c["className"],
            "auto_vs_user_color_differs": a["color"] != b["color"],
            "auto_shot_ok": bool(result["shots"]["auto_1256_tooltip"].get("ok")),
            "user_shot_ok": bool(result["shots"]["user_1600_tooltip"].get("ok")),
            "expanded_shot_ok": bool(result["shots"]["expanded_1600_tooltip"].get("ok")),
            "auto_button_crop_ok": bool(result["shots"]["auto_1256_tooltip"].get("crop")),
            "user_button_crop_ok": bool(result["shots"]["user_1600_tooltip"].get("crop")),
            "expanded_button_crop_ok": bool(result["shots"]["expanded_1600_tooltip"].get("crop")),
            "auto_state_is_auto_collapsed": bool(a["autoCollapsed"] and not a["userCollapsed"]),
            "user_state_is_user_collapsed": bool(b["userCollapsed"] and not b["autoCollapsed"]),
            "native_tooltip_captured_in_this_env": bool(
                result["shots"]["auto_1256_tooltip"].get("tooltipHits")
                or result["shots"]["user_1600_tooltip"].get("tooltipHits")
            ),
        }
        result["checks"] = checks
        # 原生 tooltip 截图在本 harness 环境不可得（环境限制，非实现失败）⇒ 信息项
        required = [k for k in checks if k not in ("native_tooltip_captured_in_this_env",)]
        result["pass"] = all(checks[k] for k in required)
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close()
        err.close()
        kill_ours()
    (HERE / "verify.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result["checks"].get(k) for k in result["checks"]}, ensure_ascii=False, indent=1))
    if not result.get("pass"):
        print("STATES:", json.dumps(result["states"], ensure_ascii=False)[:1200])
        print("SHOTS:", json.dumps(result["shots"], ensure_ascii=False)[:800])
    print("PASS" if result.get("pass") else "FAIL")
    return 0 if result.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
