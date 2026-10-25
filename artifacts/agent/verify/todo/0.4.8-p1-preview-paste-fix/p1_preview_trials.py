"""task-137 P1：**每次全新 app** 的预览区折叠光标多行粘贴试验（消除"app 卡住"干扰）。

每 trial：新 app → 打开 cursor-test.md → preview+edit → 后端写剪贴板（唯一 marker）→
真实鼠标点击段落末尾 → OS 级 Ctrl+V（keybd_event）→ 读 body 行数/光标 → OS 截图（查权限弹窗）→ 关 app。
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
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t137b"
CDP_PORT = 9605
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
PIL_PY = r"D:\deepseek-harness\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
TOOLS = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-93-responsive"
LAUNCH = TOOLS / "launch_ctl.py"
PROBE = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-112-d4b" / "probe112.mjs"
GRAB = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-136-tooltip" / "grab.py"
SHOTS = HERE / "shots"
N = 10

user32 = ctypes.windll.user32
u32 = ctypes.WinDLL("user32")
u32.GetForegroundWindow.restype = wintypes.HWND
u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]


def fg_title() -> str:
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


def evx(expr):
    return probe([{"action": "eval", "expr": expr}])[0]


def ev(expr):
    r = evx(expr)
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


def os_shot(name: str) -> str | None:
    """OS 级截图（Pillow）：直接按窗口标题找 Memoria 窗口 rect，避免依赖 ctl windows 格式。"""
    try:
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def cb(hwnd, _lparam):
            buf = ctypes.create_unicode_buffer(256)
            u32.GetWindowTextW(hwnd, buf, 256)
            if "Memoria" in buf.value and u32.IsWindowVisible(hwnd):
                r = wintypes.RECT()
                u32.GetWindowRect(hwnd, ctypes.byref(r))
                if r.right - r.left > 200:
                    found.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
                    return False
            return True

        u32.EnumWindows(cb, 0)
        if not found:
            return None
        x, y, w, h = found[0]
        SHOTS.mkdir(parents=True, exist_ok=True)
        out = SHOTS / name
        subprocess.run([PIL_PY, str(GRAB), str(x), str(y), str(w), str(h), str(out)],
                       capture_output=True, timeout=30)
        return str(out) if out.is_file() else None
    except Exception:  # noqa: BLE001
        return None


def trial(i: int, inject: str) -> dict:
    kb = WORK / f"kb{i}"
    if kb.exists(): shutil.rmtree(kb)
    shutil.copytree(REPO / "tests" / "probe-kb", kb)
    (kb / "cursor-test.md").write_text(
        "# Cursor test\n\nALPHA one two three\n\nBETA four five six\n\nGAMMA seven eight nine\n", encoding="utf-8")
    cfg = WORK / f"cfg{i}"
    if cfg.exists(): shutil.rmtree(cfg)
    os.makedirs(cfg, exist_ok=True)
    for f in ("cmd.json", "ack.json", "probe-cmd.json"):
        try: (WORK / f).unlink()
        except OSError: pass
    env = dict(os.environ)
    env.update({"T93_WORK": str(WORK), "T93_CDP_PORT": str(CDP_PORT), "MEMORIA_CONFIG_DIR": str(cfg),
                "MEMORIA_KB": str(kb), "MEMORIA_FRAMELESS": "0", "PYTHONIOENCODING": "utf-8"})
    env.pop("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", None)
    out = (WORK / f"app{i}.out.log").open("w", encoding="utf-8")
    err = (WORK / f"app{i}.err.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([PY, str(LAUNCH)], cwd=str(REPO), env=env, stdout=out, stderr=err)
    res = {"trial": i, "inject": inject}
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
        ev("""(() => {
          window.__P1 = { paste: 0, beforeinput: [], keydownV: 0 };
          document.addEventListener('paste', function () { window.__P1.paste++; }, true);
          document.addEventListener('beforeinput', function (e) { window.__P1.beforeinput.push(e.inputType); }, true);
          document.addEventListener('keydown', function (e) { if (e.key === 'v' || e.key === 'V') window.__P1.keydownV++; }, true);
          return true;
        })()""")
        pt = ev("""(() => {
          const ps = [...document.querySelectorAll('#preview .-src-block')].filter(function (b) { return b.tagName === 'P'; });
          for (const p of ps) {
            const t = (p.textContent || '').trim();
            if (t.length > 8 && t.length < 60) {
              const tn = document.createTreeWalker(p, NodeFilter.SHOW_TEXT, null).nextNode();
              if (!tn) continue;
              const rr = document.createRange();
              rr.setStart(tn, (tn.nodeValue || '').length); rr.setEnd(tn, (tn.nodeValue || '').length);
              const r = rr.getBoundingClientRect();
              return { x: Math.round(r.right - 1), y: Math.round(r.top + r.height / 2), text: t.slice(0, 30) };
            }
          }
          return null;
        })()""")
        res["point"] = pt
        prefix = "P1PV"
        text = f"{prefix}_ONE x{i}a\n{prefix}_TWO x{i}b\n{prefix}_THREE x{i}c"
        markers = [f"{prefix}_ONE x{i}a", f"{prefix}_TWO x{i}b", f"{prefix}_THREE x{i}c"]
        ev(f"(() => {{ const a = window.pywebview && window.pywebview.api; return a.clipboard_set_text({json.dumps(text)}); }})()")
        time.sleep(0.25)
        if pt:
            probe([{"action": "mouse", "type": "mousePressed", "x": pt["x"], "y": pt["y"], "button": "left", "clickCount": 1},
                   {"action": "mouse", "type": "mouseReleased", "x": pt["x"], "y": pt["y"], "button": "left", "clickCount": 1}])
            time.sleep(0.3)
            res["fgTitle"] = fg_title()
            if inject == "os":
                os_ctrl_v()
            else:
                probe([{"action": "key", "key": "v", "code": "KeyV", "vk": 86, "modifiers": 2}])
            time.sleep(1.5)
        res["shot"] = os_shot(f"p1_trial_{inject}_{i}.png")
        raw = evx("""(() => {
          const body = (window.state && window.state.doc && window.state.doc.body) || '';
          const lines = body.split(String.fromCharCode(10));
          const markers = %s;
          const found = markers.map(function (m) { return lines.some(function (l) { return l.indexOf(m) >= 0; }); });
          const hitLines = lines.filter(function (l) { return l.indexOf('%s') >= 0; });
          const sel = window.getSelection();
          const r = sel && sel.rangeCount ? sel.getRangeAt(0) : null;
          // ── task-138 光标像素断言：caret 的位置 vs 末行文本末端 rect ──
          let caretRect = null, expectedRect = null, caretBlockText = null, caretBlockIsLast = null;
          if (r) {
            const node = r.startContainer;
            const rr = document.createRange();
            try {
              if (node && node.nodeType === 3 && r.startOffset > 0) { rr.setStart(node, r.startOffset - 1); rr.setEnd(node, r.startOffset); }
              else if (node && node.nodeType === 3 && (node.nodeValue || '').length > 0) { rr.setStart(node, 0); rr.setEnd(node, 1); }
              if (rr.startContainer && rr.startContainer.nodeType === 3) {
                const b = rr.getBoundingClientRect();
                caretRect = { right: b.right, top: b.top, bottom: b.bottom, left: b.left };
              }
            } catch (e) { /* caretRect 留给断言判失败 */ }
            const el = node && (node.nodeType === 3 ? node.parentElement : node);
            const blk = el && el.closest ? el.closest('.-src-block') : null;
            if (blk) {
              caretBlockText = (blk.textContent || '').slice(-80);
              const last = markers[markers.length - 1];
              caretBlockIsLast = !!(caretBlockText && caretBlockText.indexOf(last) >= 0);
              const walker = document.createTreeWalker(blk, NodeFilter.SHOW_TEXT, null);
              let tn = null, n;
              while ((n = walker.nextNode())) { if ((n.nodeValue || '').length > 0) tn = n; }
              if (tn) {
                const er = document.createRange();
                er.setStart(tn, 0); er.setEnd(tn, (tn.nodeValue || '').length);
                const eb = er.getBoundingClientRect();
                expectedRect = { right: eb.right, top: eb.top, bottom: eb.bottom, left: eb.left };
              }
            }
          }
          return { found: found, hitLineCount: hitLines.length, hitLines: hitLines.slice(0, 4),
                   bodyLineCount: lines.length, collapsed: r ? r.isCollapsed : null,
                   caretRect: caretRect, expectedRect: expectedRect,
                   caretBlockText: caretBlockText, caretBlockIsLast: caretBlockIsLast,
                   paste: window.__P1.paste, beforeinput: window.__P1.beforeinput.slice(-6), keydownV: window.__P1.keydownV,
                   ready: document.readyState, focus: document.hasFocus() };
        })()""" % (json.dumps(markers), "P1PV_"))
        res["after"] = raw.get("value")
        res["evalException"] = raw.get("exception")
        a = res["after"] or {}
        res["threeLines"] = bool(a.get("found") and all(a["found"]) and a.get("hitLineCount", 0) >= 3)
        cr, er = a.get("caretRect"), a.get("expectedRect")
        res["caretPixelDelta"] = ({"dx": round(abs(cr["right"] - er["right"]), 2),
                                   "dy": round(abs(cr["top"] - er["top"]), 2)}
                                  if cr and er else None)
        d = res["caretPixelDelta"]
        res["caretAtLastLineEnd"] = bool(d and d["dx"] <= 2 and d["dy"] <= 2 and a.get("caretBlockIsLast"))
        return res
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close(); err.close()


def main() -> int:
    os.makedirs(WORK, exist_ok=True)
    res = {"trials": [], "inject": sys.argv[1] if len(sys.argv) > 1 else "os", "N": N}
    inject = res["inject"]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else N
    res["N"] = n
    for i in range(n):
        try:
            r = trial(i, inject)
        except Exception as e:  # noqa: BLE001
            r = {"trial": i, "inject": inject, "error": str(e)}
        res["trials"].append(r)
        print(f"[{i+1}/{n}] {inject} threeLines={r.get('threeLines')} hit={((r.get('after') or {}).get('hitLineCount'))} "
              f"paste={((r.get('after') or {}).get('paste'))} bi={((r.get('after') or {}).get('beforeinput'))} "
              f"pixel={r.get('caretPixelDelta')} caretEnd={r.get('caretAtLastLineEnd')} "
              f"exc={str(r.get('evalException'))[:60]}", flush=True)
        (HERE / f"p1-trials-{inject}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    runs = [t for t in res["trials"] if t.get("after") is not None]
    lost = [t for t in runs if not t.get("threeLines")]
    pixel_ok = [t for t in runs if t.get("caretAtLastLineEnd")]
    res["summary"] = {"runs": len(runs), "threeLines": len(runs) - len(lost), "lost": len(lost),
                      "caretPixelOk": len(pixel_ok),
                      "caretPixelDeltas": [t.get("caretPixelDelta") for t in runs]}
    (HERE / f"p1-trials-{inject}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(res["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
