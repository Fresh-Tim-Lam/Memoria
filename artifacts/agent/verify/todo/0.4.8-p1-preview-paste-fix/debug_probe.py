"""task-138 定位探针：给 MemoriaEditSync.insertText/splitParagraph 包一层，记录每次调用的
返回值 + 前后的 EH.cursorAST + 文档块数，然后 OS 级 Ctrl+V 粘贴 3 行，读取 trace。
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from ctypes import wintypes
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t138dbg"
CDP_PORT = 9607
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
TOOLS = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-93-responsive"
LAUNCH = TOOLS / "launch_ctl.py"
PROBE = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-112-d4b" / "probe112.mjs"
TEXT = "DBG_ONE aaa\nDBG_TWO bbb\nDBG_THREE ccc"

user32 = ctypes.windll.user32
u32 = ctypes.WinDLL("user32")
u32.GetForegroundWindow.restype = wintypes.HWND
u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]


def fg_title():
    buf = ctypes.create_unicode_buffer(256)
    u32.GetWindowTextW(u32.GetForegroundWindow(), buf, 256)
    return buf.value


def os_ctrl_v():
    user32.keybd_event(0x11, 0, 0, 0)
    user32.keybd_event(0x56, 0, 0, 0)
    user32.keybd_event(0x56, 0, 2, 0)
    user32.keybd_event(0x11, 0, 2, 0)


def up(u):
    try:
        urllib.request.urlopen(u, timeout=2); return True
    except Exception:  # noqa: BLE001
        return False


def probe(cmds):
    (WORK / "probe-cmd.json").write_text(json.dumps({"cmds": cmds}), encoding="utf-8")
    p = subprocess.run(["node", str(PROBE), "--port", str(CDP_PORT), "--cmd", str(WORK / "probe-cmd.json")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    lines = (p.stdout or "").strip().splitlines()
    return json.loads(lines[-1])["results"] if lines else [{"error": p.stderr[-300:]}]


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
    kb = WORK / "kb"
    if kb.exists(): shutil.rmtree(kb)
    shutil.copytree(REPO / "tests" / "probe-kb", kb)
    (kb / "cursor-test.md").write_text("# Cursor test\n\nALPHA one two three\n\nBETA four five six\n\nGAMMA seven eight nine\n", encoding="utf-8")
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
    try:
        for _ in range(160):
            if up(f"http://127.0.0.1:{CDP_PORT}/json/version"): break
            time.sleep(0.5)
        time.sleep(6)
        ctl({"op": "foreground"})
        time.sleep(0.8)
        ev("(() => { window.__OPEN = 'pending'; window.MemoriaApp.openFile('cursor-test.md').then(function (r) { window.__OPEN = (r && r.status) || 'done'; }, function (e) { window.__OPEN = 'err:' + e; }); return 'started'; })()")
        for _ in range(120):
            if ev("window.__OPEN") not in ("pending", None): break
            time.sleep(0.2)
        time.sleep(1.0)
        ev("(() => { document.querySelector('.-view-btn[data-view=\"preview\"]')?.click(); return true; })()")
        time.sleep(1.1)
        ev("(() => { const EH = window.MemoriaEditHandler; if (EH && !EH.editMode) EH.toggleEditMode(); return !!(EH && EH.editMode); })()")
        time.sleep(0.5)
        pt = ev("""(() => {
          const ps = [...document.querySelectorAll('#preview .-src-block')].filter(function (b) { return b.tagName === 'P'; });
          for (const p of ps) {
            const t = (p.textContent || '').trim();
            if (t.length > 8) {
              const tn = document.createTreeWalker(p, NodeFilter.SHOW_TEXT, null).nextNode();
              if (!tn) continue;
              const rr = document.createRange();
              rr.setStart(tn, (tn.nodeValue || '').length); rr.setEnd(tn, (tn.nodeValue || '').length);
              const r = rr.getBoundingClientRect();
              return { x: Math.round(r.right - 1), y: Math.round(r.top + r.height / 2), text: t };
            }
          }
          return null;
        })()""")
        print("clickPoint:", json.dumps(pt, ensure_ascii=False))
        ev("""(() => {
          const ES = window.MemoriaEditSync;
          window.__TRACE = [];
          function snap() {
            const EH = window.MemoriaEditHandler;
            const c = EH && EH.cursorAST;
            return c ? { bi: c.blockIndex, path: (c.nodePath || []).slice(), off: c.offset } : null;
          }
          function blockSnap() {
            try {
              return (window.state.doc.blocks || []).slice(0, 12).map(function (b, i) {
                return { i: i, type: b.type, text: (b.children || []).map(function (ch) { return ch.type + ':' + (ch.text || '').slice(0, 20); }).join('|') };
              });
            } catch (e) { return String(e); }
          }
          const oi = ES.insertText.bind(ES);
          ES.insertText = function (t) {
            const b4 = snap();
            const r = oi.apply(null, arguments);
            window.__TRACE.push({ fn: 'insertText', arg: t, ret: r, before: b4, after: snap(), blocks: blockSnap() });
            return r;
          };
          const os = ES.splitParagraph.bind(ES);
          ES.splitParagraph = function () {
            const b4 = snap();
            const r = os.apply(null, arguments);
            window.__TRACE.push({ fn: 'splitParagraph', ret: r, before: b4, after: snap(), blocks: blockSnap() });
            return r;
          };
          return true;
        })()""")
        ev(f"(() => {{ const a = window.pywebview && window.pywebview.api; return a.clipboard_set_text({json.dumps(TEXT)}); }})()")
        time.sleep(0.3)
        probe([{"action": "mouse", "type": "mousePressed", "x": pt["x"], "y": pt["y"], "button": "left", "clickCount": 1},
               {"action": "mouse", "type": "mouseReleased", "x": pt["x"], "y": pt["y"], "button": "left", "clickCount": 1}])
        time.sleep(0.35)
        print("fg:", fg_title(), "| sel:", json.dumps(ev("(() => { const s = window.getSelection(); return { collapsed: s.isCollapsed, text: String(s).slice(0, 30) }; })()"), ensure_ascii=False))
        os_ctrl_v()
        time.sleep(1.6)
        trace = ev("(() => window.__TRACE.slice(0, 20))()")
        after = ev("""(() => {
          const body = (window.state && window.state.doc && window.state.doc.body) || '';
          const lines = body.split(String.fromCharCode(10));
          return { bodyLines: lines, pasteHits: lines.filter(function (l) { return l.indexOf('DBG_') >= 0; }),
                   cursorAST: (window.MemoriaEditHandler || {}).cursorAST || null };
        })()""")
        res = {"clickPoint": pt, "trace": trace, "after": after, "text": TEXT}
        (HERE / "debug-trace.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(res, ensure_ascii=False, indent=1)[:6000])
        return 0
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close(); err.close()


if __name__ == "__main__":
    raise SystemExit(main())
