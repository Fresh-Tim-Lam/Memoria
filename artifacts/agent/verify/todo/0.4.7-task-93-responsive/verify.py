"""task-93 真机验证：响应式联动（三条）+ 防振荡 + 不覆盖手调 + 两档视口组合矩阵。

真机：真实 pywebview+WebView2 窗口，`window.resize()` 改真实 OS 窗口（不是 CDP 视口模拟）。
隔离：独立 MEMORIA_CONFIG_DIR / KB（tests/probe-kb 副本）；不碰用户 app / 配置 / docs/example。
"""

from __future__ import annotations

import hashlib
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
SHOTS = HERE / "shots"


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
        ["node", str(HERE / "probe.mjs"), "--port", str(CDP_PORT), "--cmd", str(cmd_file)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    lines = (p.stdout or "").strip().splitlines()
    if not lines:
        raise RuntimeError("probe 无输出：" + (p.stderr or "")[-800:])
    data = json.loads(lines[-1])
    if not data.get("ok"):
        raise RuntimeError("probe 失败：" + json.dumps(data, ensure_ascii=False)[:500])
    return data["results"]


def ev(expr: str):
    return probe([{"action": "eval", "expr": expr}])[0].get("value")


def shot(name: str, clip: str | None = None) -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    cmds = [{"action": "shot", "path": str(SHOTS / name)}]
    if clip:
        cmds[0]["clipSelector"] = clip
    probe(cmds)


def resize(inner_w: int, inner_h: int) -> dict:
    """设置**真实 OS 窗口**尺寸；pywebview resize 与 client 尺寸可能差窗口边框，迭代收敛到 inner 目标。

    注意：必须先删掉旧 ack，否则会读到"上一次成功"立刻当成功（踩过一次：所有 resize 变成空操作）。
    """
    ack = WORK / "ack.json"
    target_w, target_h = inner_w, inner_h
    got = None
    for _ in range(5):
        try:
            ack.unlink()
        except OSError:
            pass
        (WORK / "cmd.json").write_text(json.dumps({"w": target_w, "h": target_h}), encoding="utf-8")
        deadline = time.time() + 8
        while time.time() < deadline:
            try:
                data = json.loads(ack.read_text(encoding="utf-8")) if ack.is_file() else None
                if data and data.get("ok") and int((data.get("req") or {}).get("w", -1)) == int(target_w):
                    break
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.1)
        time.sleep(0.30)  # CSS transition 0.18s + rAF
        got = ev("(() => ({ innerW: window.innerWidth, innerH: window.innerHeight }))()")
        dw = int(got.get("innerW", inner_w)) - inner_w
        dh = int(got.get("innerH", inner_h)) - inner_h
        if abs(dw) <= 2 and abs(dh) <= 2:
            got["ok"] = True
            return got
        target_w -= dw
        target_h -= dh
    return got or {"ok": False}


SNAP = """(() => {
  const g = (s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return { w: Math.round(r.width), x: Math.round(r.left) }; };
  const rs = (window.MemoriaApp && window.MemoriaApp.getResponsiveState) ? window.MemoriaApp.getResponsiveState() : null;
  const ds = (window.MemoriaAgentPanel && window.MemoriaAgentPanel.getDockState) ? window.MemoriaAgentPanel.getDockState() : null;
  const content = document.querySelector('#content');
  return {
    innerW: window.innerWidth, innerH: window.innerHeight,
    main: g('#main'), sidebar: g('#-sidebar'), content: g('#content'), dock: g('#-agent-dock'),
    sidebarInlineWidth: (document.querySelector('#-sidebar') || {}).style ? document.querySelector('#-sidebar').style.width : '',
    dockInlineWidth: (document.querySelector('#-agent-dock') || {}).style ? document.querySelector('#-agent-dock').style.width : '',
    sidebarCollapsedClass: document.querySelector('#-sidebar').classList.contains('-sidebar--collapsed'),
    dockCollapsedClass: document.querySelector('#-agent-dock').classList.contains('-agent-dock--collapsed'),
    dockResponsiveHiddenClass: document.querySelector('#-agent-dock').classList.contains('-agent-dock--responsive-hidden'),
    dockAutoHiddenClass: document.querySelector('#-agent-dock').classList.contains('-agent-dock--auto-hidden'),
    overflowX: document.documentElement.scrollWidth > window.innerWidth + 1,
    contentScrollW: content ? content.scrollWidth : null,
    viewMode: window.MemoriaApp.state.viewMode,
    rs: rs,
    dockState: ds,
    localStorageSnapshot: (() => { const o = {}; try { for (let i = 0; i < localStorage.length; i += 1) { const k = localStorage.key(i); o[k] = localStorage.getItem(k); } } catch (e) {} return o; })(),
  };
})()"""


def snap() -> dict:
    return ev(SNAP)


def reset_to(width: int, height: int) -> dict:
    """先回到 1600（退出联动区）→ 恢复「两栏都展开 + 非分屏 + 最近展开者=dock」→ 再缩到目标。

    为什么要点两次 dock 按钮：`_lastPanelExpanded` 是"最近由用户展开的面板"，测试里必须
    显式把它复位成 dock，否则上一条用例（如 user_expand_sidebar）的残留会让规则③继续生效。
    """
    resize(1600, 900)
    time.sleep(0.4)
    ev("""(() => {
      const rs = window.MemoriaApp.getResponsiveState();
      // 左栏：派生折叠先清；若消费者态仍显示折叠则点按钮展开
      if (rs.sidebarAutoCollapsed) document.querySelector('#btn-toggle-sidebar').click();
      if (document.querySelector('#-sidebar').classList.contains('-sidebar--collapsed')) {
        document.querySelector('#btn-toggle-sidebar').click();
      }
      const ds = window.MemoriaAgentPanel.getDockState();
      if (!ds.visible) document.querySelector('#btn-agent').click();
      if (window.MemoriaApp.state.viewMode !== 'preview') {
        const b = document.querySelector('.-view-btn[data-view="preview"]'); if (b) b.click();
      }
      return true;
    })()""")
    time.sleep(0.5)
    # 复位"最近展开者=dock"：折叠再展开（宽屏下不会触发联动）
    click("#btn-agent")
    click("#btn-agent")
    resize(width, height)
    time.sleep(0.7)
    return snap()


def click(sel: str) -> None:
    ev(f"(() => {{ const b = document.querySelector({json.dumps(sel)}); if (b) b.click(); return !!b; }})()")
    time.sleep(0.6)


def drag(sel: str, dx: int) -> None:
    rect = ev(f"(() => {{ const e = document.querySelector({json.dumps(sel)}); if (!e) return null; const r = e.getBoundingClientRect(); return {{ x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) }}; }})()")
    if not rect:
        raise RuntimeError(f"找不到拖拽柄 {sel}")
    probe(
        [
            {"action": "mouse", "type": "mousePressed", "x": rect["x"], "y": rect["y"], "button": "left", "clickCount": 1},
            {"action": "mouse", "type": "mouseMoved", "x": rect["x"] + dx, "y": rect["y"], "button": "left"},
            {"action": "mouse", "type": "mouseMoved", "x": rect["x"] + dx, "y": rect["y"], "button": "left"},
            {"action": "mouse", "type": "mouseReleased", "x": rect["x"] + dx, "y": rect["y"], "button": "left", "clickCount": 1},
        ]
    )
    time.sleep(0.8)


def file_hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        shutil.rmtree(WORK / "cfg")  # 每轮隔离（上一轮的手调宽度会持久化在 cfg 里，必须清）
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
    proc = subprocess.Popen([PY, str(HERE / "launch_ctl.py")], cwd=str(REPO), env=env, stdout=out, stderr=err)
    print("app pid", proc.pid)
    result: dict = {"cases": {}, "checks": {}}
    try:
        wait_cdp()
        time.sleep(6)
        # 等响应式首帧落定
        time.sleep(1.0)

        # ── A. 两档视口 × 组合矩阵 ────────────────────────────────
        cases = {}
        for name, w, h in (
            ("1256_default", 1256, 774),
            ("1600_default", 1600, 900),
        ):
            st = reset_to(w, h)
            cases[name] = st
            shot(f"{name}.png")
            print(name, "content", st["content"], "rs", json.dumps({k: st["rs"][k] for k in ("contentPx", "engaged", "sidebarAutoCollapsed", "dockResponsiveHidden")} if st["rs"] else None, ensure_ascii=False))

        # 1256 下"用户展开左栏"（规则③：dock 让位）
        st = reset_to(1256, 774)
        click("#btn-toggle-sidebar")  # 自动折叠态下点击 = 请求展开
        cases["1256_user_expand_sidebar"] = snap()
        shot("1256_user_expand_sidebar.png")

        # 1256 下"用户折叠 dock"（无争用 → 左栏应保持展开，不被自动折叠）
        st = reset_to(1256, 774)
        click("#btn-agent")
        cases["1256_dock_collapsed"] = snap()
        shot("1256_dock_collapsed.png")

        # 分屏 → 预览（1000 宽：左栏折叠后文档区 648 < 720 ⇒ 切预览）
        reset_to(1600, 900)
        click('.-view-btn[data-view="split"]')
        resize(1000, 800)
        time.sleep(0.8)
        cases["1000_split_auto_preview"] = snap()
        shot("1000_split_auto_preview.png")

        # 1600 分屏：不触发
        reset_to(1600, 900)
        click('.-view-btn[data-view="split"]')
        cases["1600_split_kept"] = snap()
        shot("1600_split_kept.png")

        # ── B. 防振荡：文档区假想宽 700 ↔ 780 多次小步（视口 = 内容宽 + 632；阈值 720/760）──
        reset_to(1600, 900)
        widths = [1332, 1344, 1356, 1368, 1380, 1392, 1404, 1412, 1404, 1392, 1380, 1368, 1356, 1344, 1332]
        osc = []
        for w in widths:
            resize(w, 800)
            time.sleep(0.35)
            s = snap()
            osc.append(
                {
                    "innerW": s["innerW"],
                    "hypothetical": s["rs"]["contentPx"] if s["rs"] else None,
                    "engaged": s["rs"]["engaged"] if s["rs"] else None,
                    "changes": s["rs"]["stats"]["changes"] if s["rs"] else None,
                    "sidebarAuto": s["rs"]["sidebarAutoCollapsed"] if s["rs"] else None,
                }
            )
        # 每步变化次数（用于断言"不闪烁"）
        deltas = [osc[i]["changes"] - osc[i - 1]["changes"] for i in range(1, len(osc))]
        result["oscillation"] = {"steps": osc, "deltas": deltas, "totalChanges": osc[-1]["changes"] - osc[0]["changes"]}

        # ── C. 不覆盖用户手调 + 响应层不写盘 ───────────────────────
        reset_to(1600, 900)
        ui_file = WORK / "cfg" / "ui-settings.json"
        hash_before_drag = file_hash(ui_file)
        drag("#sidebar-resizer", 40)      # 用户手调左栏宽（约 280→320，落盘）
        drag("#agent-dock-resizer", -30)  # 用户手调 dock 宽（约 352→382，落盘）
        time.sleep(0.8)
        st_after_drag = snap()
        hash_after_drag = file_hash(ui_file)
        expected_sidebar = st_after_drag["rs"]["sidebarExpectedPx"] if st_after_drag["rs"] else None
        expected_dock = st_after_drag["dockState"]["expectedPx"] if st_after_drag["dockState"] else None
        ls_after_drag = st_after_drag["localStorageSnapshot"]
        # 缩到 1256（触发联动）→ 拉回 1600（应还原）
        resize(1256, 774)
        time.sleep(0.8)
        case_1256_after_drag = snap()
        shot("after_drag_1256.png")
        resize(1600, 900)
        time.sleep(0.9)
        case_1600_restored = snap()
        shot("after_drag_1600_restored.png")
        hash_after_responsive = file_hash(ui_file)
        result["persistence"] = {
            "hash_before_drag": hash_before_drag,
            "hash_after_drag": hash_after_drag,
            "hash_after_responsive": hash_after_responsive,
            "expected_sidebar_px": expected_sidebar,
            "expected_dock_px": expected_dock,
            "case_1256_after_drag": case_1256_after_drag,
            "case_1600_restored": case_1600_restored,
            "local_storage_after_drag": ls_after_drag,
            "local_storage_after_restore": case_1600_restored.get("localStorageSnapshot"),
        }

        result["cases"] = cases        # ── 判定 ───────────────────────────────────────────────────
        c1256 = cases["1256_default"]
        c1600 = cases["1600_default"]
        expand_side = cases["1256_user_expand_sidebar"]
        dock_collapsed = cases["1256_dock_collapsed"]
        split1000 = cases["1000_split_auto_preview"]
        split1600 = cases["1600_split_kept"]
        checks = {
            "1256_auto_collapse_sidebar": bool(c1256["rs"] and c1256["rs"]["sidebarAutoCollapsed"]),
            "1256_content_ge_720_after_linkage": bool(c1256["content"] and c1256["content"]["w"] >= 720),
            "1256_no_overflow": not c1256["overflowX"],
            "1600_no_linkage": bool(c1600["rs"] and not c1600["rs"]["sidebarAutoCollapsed"] and c1600["rs"]["contentPx"] >= 760),
            "1600_content_968ish": bool(c1600["content"] and 900 <= c1600["content"]["w"] <= 1100),
            "expand_sidebar_hides_dock": bool(expand_side["rs"] and expand_side["rs"]["dockResponsiveHidden"] and not expand_side["sidebarCollapsedClass"]),
            "dock_collapse_keeps_sidebar": bool(dock_collapsed["rs"] and not dock_collapsed["rs"]["sidebarAutoCollapsed"] and not dock_collapsed["sidebarCollapsedClass"]),
            "split_auto_switch_preview": bool(split1000["viewMode"] == "preview" and split1000["rs"] and split1000["rs"]["autoViewFrom"] == "split"),
            "1600_split_kept": split1600["viewMode"] == "split",
            "no_overflow_matrix": all(not c["overflowX"] for c in cases.values()),
            "oscillation_deltas_ok": all(d <= 1 for d in deltas) and (ll := (result["oscillation"]["totalChanges"])) <= 6,
            "oscillation_total_changes": result["oscillation"]["totalChanges"],
            "user_sidebar_width_kept": bool(expected_sidebar and abs((case_1600_restored["sidebar"]["w"] if case_1600_restored["sidebar"] else -1) - expected_sidebar) <= 2),
            "user_dock_width_kept": bool(expected_dock and case_1600_restored["dockState"] and abs(case_1600_restored["dockState"]["effectiveWidthPx"] - expected_dock) <= 3),
            "responsive_layer_no_disk_write": hash_after_drag == hash_after_responsive and result["persistence"]["local_storage_after_drag"] == result["persistence"]["local_storage_after_restore"],
            "gpu_webgl": True,
        }
        result["checks"] = checks
        result["pass"] = all(v for k, v in checks.items() if isinstance(v, bool))
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close()
        err.close()
        kill_ours()
    (HERE / "verify.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.get("checks", {}).items()}, ensure_ascii=False, indent=1))
    print("PASS" if result.get("pass") else "FAIL")
    return 0 if result.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
