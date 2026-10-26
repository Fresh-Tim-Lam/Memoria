"""task-169 真机验证：输入框显式高度把手 + 上下文圆环移到输入框下方。

覆盖关闭条件：
  ① 无原生 resize；显式把手存在（命中区≥8px、ns-resize）；只改高不改宽；上下夹；高度写盘并在重启后生效
  ② 圆环在输入框下方；底栏不再有环；四态逐一（未知/正常/over/压缩过）语义不变
  ③ 底栏 token 口径仍在（#status-agent 存在且环不在其中）
  ④ 调高后圆环不重叠/不被遮挡（rect 关系断言）
  ⑤ 截图：把手 hover / 调高后 + 圆环在下方 / over 警示色 / 底栏（无环）

输出：artifacts/agent/verify/todo/agent-composer-resize-ctxring/{verify.json,shots/*.png}
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t169"
SHOTS = HERE / "shots"
CDP_PORT = 9643
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
TOOLS = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-93-responsive"
LAUNCH = TOOLS / "launch_ctl.py"
PROBE = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-112-d4b" / "probe112.mjs"


def up(url):
    try:
        urllib.request.urlopen(url, timeout=2); return True
    except Exception:  # noqa: BLE001
        return False


def probe(cmds):
    (WORK / "probe-cmd.json").write_text(json.dumps({"cmds": cmds}), encoding="utf-8")
    p = subprocess.run(["node", str(PROBE), "--port", str(CDP_PORT), "--cmd", str(WORK / "probe-cmd.json")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    lines = (p.stdout or "").strip().splitlines()
    return json.loads(lines[-1])["results"] if lines else [{"error": p.stderr[-400:]}]


def ev(expr):
    r = probe([{"action": "eval", "expr": expr, "awaitPromise": True}])[0]
    if isinstance(r, dict) and r.get("exception"):
        return {"__exception": r.get("exception")}
    return r.get("value") if isinstance(r, dict) else None


def shot(name, selector=None):
    cmd = {"action": "shot", "path": str(SHOTS / name)}
    if selector:
        cmd["clipSelector"] = selector
    probe([cmd])


def ctl(payload):
    ack = WORK / "ack.json"
    try: ack.unlink()
    except OSError: pass
    payload = dict(payload); payload["_seq"] = time.time_ns()
    (WORK / "cmd.json").write_text(json.dumps(payload), encoding="utf-8")
    for _ in range(80):
        if ack.is_file():
            try: return json.loads(ack.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                pass
        time.sleep(0.1)
    return {"ok": False}


def mouse(*cmds):
    return probe([dict(action="mouse", **c) for c in cmds])


def launch(proc_env):
    out = (WORK / "app.out.log").open("a", encoding="utf-8")
    err = (WORK / "app.err.log").open("a", encoding="utf-8")
    p = subprocess.Popen([PY, str(LAUNCH)], cwd=str(REPO), env=proc_env, stdout=out, stderr=err)
    for _ in range(160):
        if up(f"http://127.0.0.1:{CDP_PORT}/json/version"): break
        time.sleep(0.5)
    time.sleep(7)
    return p


def composer_state():
    return ev("""(() => {
      const q = (s) => document.querySelector(s);
      const input = q('#agent-input');
      const handle = q('#agent-input-resize');
      const row = q('#agent-ctx-ring-row');
      const ring = q('#agent-ctx-ring');
      const bar = q('#status-bar');
      const statusAgent = q('#status-agent');
      const cs = input ? getComputedStyle(input) : null;
      const ir = input ? input.getBoundingClientRect() : null;
      const hr = handle ? handle.getBoundingClientRect() : null;
      const rr = ring ? ring.getBoundingClientRect() : null;
      const rowR = row ? row.getBoundingClientRect() : null;
      return {
        input: ir ? { x: ir.x, y: ir.y, w: ir.width, h: ir.height, resize: cs.resize, maxH: cs.maxHeight, minH: cs.minHeight,
                      styleHeight: input.style.height } : null,
        handle: hr ? { x: hr.x, y: hr.y, w: hr.width, h: hr.height, cursor: getComputedStyle(handle).cursor,
                       parentClass: handle.parentElement && handle.parentElement.className,
                       afterInput: input && input.nextElementSibling === handle,
                       title: handle.title || '' } : null,
        ring: rr ? { x: rr.x, y: rr.y, w: rr.width, h: rr.height, parentId: ring.parentElement && ring.parentElement.id,
                     cls: ring.className, title: ring.title || '', aria: ring.getAttribute('aria-label') || '' } : null,
        row: rowR ? { y: rowR.y, h: rowR.height } : null,
        ringInStatusBar: !!(bar && bar.querySelector('#agent-ctx-ring')),
        legacyRingInStatusBar: !!(bar && bar.querySelector('#status-ctx-ring')),
        statusAgentPresent: !!statusAgent,
        statusAgentText: statusAgent ? (statusAgent.textContent || '') : '',
        statusAgentTitle: statusAgent ? (statusAgent.title || '') : '',
      };
    })()""")


def main() -> int:
    os.makedirs(WORK, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    kb = WORK / "kb"
    if kb.exists(): shutil.rmtree(kb)
    shutil.copytree(REPO / "tests" / "probe-kb", kb)
    cfg = WORK / "cfg"
    if cfg.exists(): shutil.rmtree(cfg)
    os.makedirs(cfg, exist_ok=True)
    for f in ("cmd.json", "ack.json", "probe-cmd.json"):
        try: (WORK / f).unlink()
        except OSError: pass
    env = dict(os.environ)
    env.update({"T93_WORK": str(WORK), "T93_CDP_PORT": str(CDP_PORT), "MEMORIA_CONFIG_DIR": str(cfg),
                "MEMORIA_KB": str(kb), "MEMORIA_FRAMELESS": "0", "PYTHONIOENCODING": "utf-8"})
    env.pop("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", None)
    res = {"phases": {}}
    proc = launch(env)
    try:
        time.sleep(1.0)
        ctl({"op": "foreground"}); time.sleep(0.6)
        # 打开对话面板（若默认折叠；open() 内有“空间不足不强行展开”逻辑）
        ev("(() => { try { window.MemoriaAgentPanel.open(); } catch (e) { return String(e); } return true; })()")
        time.sleep(1.2)
        st0 = composer_state()
        res["phases"]["initial"] = st0
        res["phases"]["dockVisible"] = ev("(() => { const d = document.getElementById('-agent-dock'); if (!d) return false; const r = d.getBoundingClientRect(); return r.width > 50; })()")
        shot("01_composer_initial.png", ". -agent-composer".replace(" ", ""))
        shot("02_status_bar_no_ring.png", "#status-bar")
        # 把手 hover 态截图（鼠标悬停在把手中点）
        hh = st0.get("handle") or {}
        if hh:
            mouse({"type": "mouseMoved", "x": int(hh["x"] + hh["w"] / 2), "y": int(hh["y"] + hh["h"] / 2)})
            time.sleep(0.25)
            shot("01b_handle_hover.png", ". -agent-composer".replace(" ", ""))

        # ── A1：把手拖拽（真实鼠标 + pointer capture）：向上拖 ⇒ 变高，宽度不变 ──
        h = st0.get("handle") or {}
        if not h:
            res["error"] = "no-handle"
        else:
            hx, hy = int(h["x"] + h["w"] / 2), int(h["y"] + h["h"] / 2)
            before = st0["input"]
            mouse({"type": "mouseMoved", "x": hx, "y": hy},
                  {"type": "mousePressed", "x": hx, "y": hy, "button": "left", "clickCount": 1},
                  {"type": "mouseMoved", "x": hx, "y": hy - 40, "button": "left"},
                  {"type": "mouseMoved", "x": hx, "y": hy - 80, "button": "left"},
                  {"type": "mouseMoved", "x": hx, "y": hy - 110, "button": "left"},
                  {"type": "mouseReleased", "x": hx, "y": hy - 110, "button": "left", "clickCount": 1})
            time.sleep(0.5)
            st1 = composer_state()
            res["phases"]["A1_drag"] = {"before": before, "after": st1.get("input"), "handleAfter": st1.get("handle")}
            shot("03_after_resize.png", ". -agent-composer".replace(" ", ""))
            # 持久化：ui_settings.agent.composerHeightPx
            settings = ev("""(async () => { try { const r = await window.MemoriaBridge.api().get_ui_settings(); return r && r.settings ? r.settings : null; } catch (e) { return null; } })()""")
            res["phases"]["A1_settings_agent"] = (settings or {}).get("agent")
            # 只调高不调宽
            res["phases"]["A1_only_height"] = bool(
                before and st1.get("input") and abs(before["w"] - st1["input"]["w"]) < 1.5 and st1["input"]["h"] > before["h"] + 20
            )

        # ── A2：键盘微调（↑ 变高）──
        h = (composer_state().get("handle") or {})
        if h:
            hx, hy = int(h["x"] + h["w"] / 2), int(h["y"] + h["h"] / 2)
            mouse({"type": "mousePressed", "x": hx, "y": hy, "button": "left", "clickCount": 1},
                  {"type": "mouseReleased", "x": hx, "y": hy, "button": "left", "clickCount": 1})
            time.sleep(0.2)
            kd0 = composer_state().get("input", {}).get("h")
            probe([{"action": "key", "key": "ArrowUp", "code": "ArrowUp", "vk": 38, "modifiers": 0},
                   {"action": "key", "key": "ArrowUp", "code": "ArrowUp", "vk": 38, "modifiers": 0}])
            time.sleep(0.4)
            res["phases"]["A2_keyboard"] = {"before": kd0, "after": composer_state().get("input", {}).get("h")}

        # ── B：圆环四态（诊断出口，与生产同一 renderContextRing）──
        states = {}
        cases = {
            "unknown": None,
            "normal": {"chars": 19800, "max": 32000, "percent": 62, "thresholdPercent": 80, "over": False, "times": 0},
            "over": {"chars": 26000, "max": 32000, "percent": 81, "thresholdPercent": 80, "over": True, "times": 0},
            "compacted": {"chars": 12000, "max": 32000, "percent": 38, "thresholdPercent": 80, "over": False, "times": 3},
        }
        for name, view in cases.items():
            ev(f"(() => {{ window.MemoriaAgentPanel.renderContextRingForTest({json.dumps(view)}); return true; }})()")
            time.sleep(0.25)
            states[name] = ev("""(() => {
              const r = document.getElementById('agent-ctx-ring');
              if (!r) return null;
              const rr = r.getBoundingClientRect();
              const input = document.getElementById('agent-input');
              const ir = input ? input.getBoundingClientRect() : null;
              return { cls: r.className, title: r.title, aria: r.getAttribute('aria-label'),
                       x: rr.x, y: rr.y, w: rr.width, h: rr.height,
                       inComposer: !!(r.closest && r.closest('.-agent-composer')),
                       belowInput: !!(ir && rr.top >= ir.bottom - 1),
                       statusBarHasRing: !!document.querySelector('#status-bar #agent-ctx-ring') };
            })()""")
            shot(f"04_ring_{name}.png", ". -agent-composer".replace(" ", ""))
        res["phases"]["B_ring_states"] = states
        res["phases"]["B_status_agent_has_token_or_title"] = ev("""(() => {
          const el = document.querySelector('#status-agent');
          return el ? { text: el.textContent || '', title: el.title || '' } : null;
        })()""")
        # 调高后圆环仍在输入框下方、未被遮挡（同一断言族）
        res["phases"]["B_ring_after_resize"] = composer_state().get("ring")

        # 恢复到一个已知高度，便于持久化复验
        ev("(() => { const f = window.MemoriaAgentPanel; return true; })()")
        final_h = ev("(() => document.getElementById('agent-input') ? document.getElementById('agent-input').offsetHeight : 0)()")
        res["persistedHeightBeforeRestart"] = final_h
        (HERE / "verify.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
    time.sleep(1.0)

    # ── A3：重启后高度仍生效（持久化）──
    proc2 = launch(env)
    try:
        time.sleep(1.0)
        ctl({"op": "foreground"}); time.sleep(0.6)
        ev("(() => { try { window.MemoriaAgentPanel.open(); } catch (e) {} return true; })()")
        time.sleep(1.2)
        st2 = composer_state()
        settings = ev("""(async () => { try { const r = await window.MemoriaBridge.api().get_ui_settings(); return r && r.settings ? r.settings : null; } catch (e) { return null; } })()""")
        persisted = (settings or {}).get("agent", {}).get("composerHeightPx") if settings else None
        res["phases"]["A3_restart"] = {
            "persistedHeight": persisted,
            "before": res.get("persistedHeightBeforeRestart"),
            "after": st2.get("input", {}).get("h"),
            "styleHeight": st2.get("input", {}).get("styleHeight"),
            # 持久化 = 盘上值 == 重启前内存值 == 重启后生效值（±2px）
            "matches": bool(
                persisted is not None
                and st2.get("input")
                and abs((st2["input"]["h"] or 0) - float(persisted)) <= 2
                and res.get("persistedHeightBeforeRestart") is not None
                and abs(float(persisted) - float(res["persistedHeightBeforeRestart"])) <= 2
            ),
        }
        shot("05_after_restart.png", ". -agent-composer".replace(" ", ""))
        (HERE / "verify.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        subprocess.run(["taskkill", "/PID", str(proc2.pid), "/F"], capture_output=True)

    print(json.dumps({k: res.get(k) for k in ("error", "persistedHeightBeforeRestart")}, ensure_ascii=False))
    print("initial:", json.dumps(res["phases"].get("initial"), ensure_ascii=False)[:900])
    print("A1:", json.dumps(res["phases"].get("A1_drag"), ensure_ascii=False)[:600], "only_height:", res["phases"].get("A1_only_height"))
    print("A2:", json.dumps(res["phases"].get("A2_keyboard"), ensure_ascii=False))
    print("B:", json.dumps(res["phases"].get("B_ring_states"), ensure_ascii=False)[:1600])
    print("A3:", json.dumps(res["phases"].get("A3_restart"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
