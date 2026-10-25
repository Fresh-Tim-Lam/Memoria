"""task-144 功能核验：② 文档区保底宽度设置 / ④ 圆环 / ⑥ 恢复抑制 + 启动加载态。

真机 pywebview 启动 → 断言 + 截图（artifacts/.../shots/）。
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
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t144v"
CDP_PORT = 9615
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
TOOLS = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-93-responsive"
LAUNCH = TOOLS / "launch_ctl.py"
PROBE = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-112-d4b" / "probe112.mjs"
SHOTS = HERE / "shots"


def up(url):
    try:
        urllib.request.urlopen(url, timeout=2); return True
    except Exception:  # noqa: BLE001
        return False


def probe(cmds):
    (WORK / "probe-cmd.json").write_text(json.dumps({"cmds": cmds}), encoding="utf-8")
    p = subprocess.run(["node", str(PROBE), "--port", str(CDP_PORT), "--cmd", str(WORK / "probe-cmd.json")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    lines = (p.stdout or "").strip().splitlines()
    return json.loads(lines[-1])["results"] if lines else [{"error": p.stderr[-400:]}]


def ev(expr):
    r = probe([{"action": "eval", "expr": expr}])[0]
    return r.get("value") if isinstance(r, dict) else None


def ctl(payload):
    ack = WORK / "ack.json"
    try: ack.unlink()
    except OSError: pass
    payload = dict(payload); payload["_seq"] = time.time_ns()
    (WORK / "cmd.json").write_text(json.dumps(payload), encoding="utf-8")
    for _ in range(60):
        if ack.is_file():
            try: return json.loads(ack.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                pass
        time.sleep(0.1)
    return {"ok": False}


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
    out = (WORK / "app.out.log").open("w", encoding="utf-8")
    err = (WORK / "app.err.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([PY, str(LAUNCH)], cwd=str(REPO), env=env, stdout=out, stderr=err)
    res = {"checks": {}}
    try:
        for _ in range(160):
            if up(f"http://127.0.0.1:{CDP_PORT}/json/version"): break
            time.sleep(0.5)
        time.sleep(6)
        ctl({"op": "foreground"})
        time.sleep(0.8)
        ev("(() => { window.__OPEN = 'pending'; window.MemoriaApp.openFile('README.md').then(function (r) { window.__OPEN = (r && r.status) || 'done'; }, function (e) { window.__OPEN = 'err:' + e; }); return 'started'; })()")
        for _ in range(150):
            if ev("window.__OPEN") not in ("pending", None): break
            time.sleep(0.2)
        time.sleep(1.2)

        # ④ 圆环存在 + 未知态
        ring = ev("""(() => {
          const el = document.getElementById('status-ctx-ring');
          if (!el) return { exists: false };
          return { exists: true, inStatusBar: !!el.closest('#status-bar'),
                   unknown: el.classList.contains('-ctx-ring--unknown'),
                   hasSvg: !!el.querySelector('svg circle'),
                   title: el.title || '', aria: el.getAttribute('aria-label') || '',
                   statusAgentText: (document.getElementById('status-agent') || {}).textContent || '' };
        })()""")
        res["ring_unknown"] = ring
        res["checks"]["ring_exists_in_status_bar"] = bool(ring and ring.get("exists") and ring.get("inStatusBar") and ring.get("hasSvg"))
        res["checks"]["ring_unknown_state_has_title"] = bool(ring and ring.get("unknown") and ring.get("title"))
        res["checks"]["ring_no_long_text_in_status_agent"] = not any(k in (ring or {}).get("statusAgentText", "") for k in ("压缩预算", "Compact budget"))

        # ② 设置字段 + 落盘 + 夹紧 + agent-panel 读取
        settings = ev("""(() => {
          const DS = window.MemoriaDisplaySettings;
          if (!DS) return { error: 'no-display-settings' };
          const html = DS.renderSettingsBody();
          const before = DS.getContentMinPx();
          DS.save({ contentMinPx: 480 });
          const after480 = { get: DS.getContentMinPx(), local: JSON.parse(localStorage.getItem('-display-settings') || '{}').contentMinPx };
          const agent = window.MemoriaAgentPanel && typeof window.MemoriaAgentPanel.getContentMinPx === 'function'
            ? window.MemoriaAgentPanel.getContentMinPx() : null;
          DS.save({ contentMinPx: 9999 });
          const clampedHigh = DS.getContentMinPx();
          DS.save({ contentMinPx: 100 });
          const clampedLow = DS.getContentMinPx();
          DS.save({ contentMinPx: 360 });
          const restored = DS.getContentMinPx();
          return { hasField: html.indexOf('data-display-setting="contentMinPx"') >= 0,
                   hasRange320560: html.indexOf('min="320"') >= 0 && html.indexOf('max="560"') >= 0,
                   hasNote: html.indexOf('文档区保底宽度') >= 0 || html.indexOf('Minimum document width') >= 0,
                   before: before, after480: after480, agentGet: agent,
                   clampedHigh: clampedHigh, clampedLow: clampedLow, restored: restored,
                   range: DS.CONTENT_MIN_RANGE };
        })()""")
        res["settings"] = settings
        res["checks"]["settings_field_present"] = bool(settings.get("hasField") and settings.get("hasRange320560") and settings.get("hasNote"))
        res["checks"]["settings_default_360"] = settings.get("before") == 360
        res["checks"]["settings_save_480_persists"] = bool(settings.get("after480", {}).get("get") == 480 and settings.get("after480", {}).get("local") == 480)
        res["checks"]["settings_agent_panel_reads_value"] = settings.get("agentGet") == 480
        res["checks"]["settings_clamp_range"] = settings.get("clampedHigh") == 560 and settings.get("clampedLow") == 320
        res["checks"]["settings_restore_360"] = settings.get("restored") == 360

        # ① 过渡仍在 + contain 生效；点击后宽度确实在动画（>1 个不同宽度）
        anim = ev("""(() => new Promise(function (resolve) {
          const dock = document.getElementById('-agent-dock');
          const sb = document.getElementById('-sidebar');
          const csD = dock ? getComputedStyle(dock) : null;
          const csS = sb ? getComputedStyle(sb) : null;
          const base = {
            dockTransition: csD ? csD.transitionDuration + ' ' + csD.transitionProperty : null,
            sidebarContain: csS ? csS.contain : null,
            dockContain: csD ? csD.contain : null,
          };
          const btn = document.getElementById('btn-toggle-sidebar');
          if (!btn) return resolve(Object.assign(base, { click: false }));
          const widths = [];
          const t0 = performance.now();
          btn.click();
          (function loop() {
            widths.push(sb ? Math.round(sb.getBoundingClientRect().width) : null);
            if (performance.now() - t0 < 300) requestAnimationFrame(loop);
            else resolve(Object.assign(base, { click: true, distinct: Array.from(new Set(widths)).length,
                                               widths: Array.from(new Set(widths)).sort(function (a, b) { return a - b; }) }));
          })();
        }))()""")
        res["anim"] = anim
        res["checks"]["toggle_still_animates"] = bool(anim and anim.get("distinct", 0) >= 2)
        res["checks"]["sidebar_contain_layout"] = bool(anim and "layout" in str(anim.get("sidebarContain")))
        res["checks"]["dock_contain_layout"] = bool(anim and "layout" in str(anim.get("dockContain")))
        # 恢复抑制：focus 事件加 -no-transition，240ms 后移除；正常过渡不被永久关掉
        noTrans = ev("""(() => new Promise(function (resolve) {
          const root = document.documentElement;
          window.dispatchEvent(new Event('focus'));
          const during = root.classList.contains('-no-transition');
          setTimeout(function () {
            resolve({ during: during, after: root.classList.contains('-no-transition') });
          }, 320);
        }))()""")
        res["noTrans"] = noTrans
        res["checks"]["restore_suppresses_transition_temporarily"] = bool(noTrans and noTrans.get("during") and not noTrans.get("after"))
        # 启动加载态已在就绪后移除
        res["checks"]["booting_class_removed_when_ready"] = ev("!document.documentElement.classList.contains('-booting')")
        # 截图（状态栏圆环 + 设置页）
        probe([{"action": "shot", "path": str(SHOTS / "statusbar_ring.png")}])
        ev("""(() => {
          const DS = window.MemoriaDisplaySettings;
          const html = DS.renderSettingsBody();
          let host = document.getElementById('__t144_settings_preview');
          if (!host) {
            host = document.createElement('div');
            host.id = '__t144_settings_preview';
            host.style.cssText = 'position:fixed;right:16px;top:56px;width:420px;max-height:70vh;overflow:auto;z-index:99999;background:var(--bg-secondary);border:1px solid var(--border);border-radius:8px;padding:12px;box-shadow:0 8px 24px rgba(0,0,0,.35)';
            document.body.appendChild(host);
          }
          host.innerHTML = html;
          return true;
        })()""")
        time.sleep(0.4)
        probe([{"action": "shot", "path": str(SHOTS / "settings_content_min_width.png")}])
        res["pass"] = all(res["checks"].values())
        (HERE / "verify-144.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(res["checks"], ensure_ascii=False, indent=1))
        print("PASS" if res["pass"] else "FAIL", "| settings:", json.dumps(settings, ensure_ascii=False)[:400])
        return 0 if res["pass"] else 1
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close(); err.close()


if __name__ == "__main__":
    raise SystemExit(main())
