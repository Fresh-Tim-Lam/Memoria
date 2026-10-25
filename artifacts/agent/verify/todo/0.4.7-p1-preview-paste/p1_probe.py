"""task-137 P1 定性：预览区折叠光标多行 Ctrl+V 是否丢行（先定性，不修）。

方法（严格对照）：
  · 真机 pywebview+WebView2，隔离 KB + 专用 cursor-test.md；
  · 同一套"真实鼠标点击定位 + 后端剪贴板写入"；
  · 两种按键注入方式各跑 N 次：① OS 级 SendInput（keybd_event，最接近用户）② CDP Input.dispatchKeyEvent；
  · 每次记录：paste 事件计数 / beforeinput.inputType / 粘贴前后行数 / 3 行是否各自成行 / 光标位置；
  · 对照组：源码区同样 10 次（预期 3/3 行，验证注入本身可靠）。

判据（Lead 要求，二选一）：
  OS 注入 ≥3/10 丢 ⇒ 产品缺陷；OS 注入 0/10 丢而 CDP 有丢 ⇒ 测量不稳（根因=CDP 按键注入不可靠）。
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
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t137"
CDP_PORT = 9601
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
TOOLS = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-93-responsive"
LAUNCH = TOOLS / "launch_ctl.py"
PROBE = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-112-d4b" / "probe112.mjs"
N = 10

user32 = ctypes.windll.user32
u32 = ctypes.WinDLL("user32", use_last_error=True)
u32.GetForegroundWindow.restype = wintypes.HWND
u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]


def fg_title() -> str:
    h = u32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    u32.GetWindowTextW(h, buf, 256)
    return buf.value


def os_ctrl_v():
    # keybd_event 即 SendInput 同族（OS 级注入，发给前台窗口）
    KEYEVENTF_KEYUP = 0x0002
    VK_CONTROL, VK_V = 0x11, 0x56
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_V, 0, 0, 0)
    user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def up(url):
    try:
        urllib.request.urlopen(url, timeout=2)
        return True
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
    try:
        ack.unlink()
    except OSError:
        pass
    payload = dict(payload)
    payload["_seq"] = time.time_ns()
    (WORK / "cmd.json").write_text(json.dumps(payload), encoding="utf-8")
    for _ in range(60):
        if ack.is_file():
            try:
                return json.loads(ack.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                pass
        time.sleep(0.1)
    return {"ok": False}


def click(x, y):
    probe([
        {"action": "mouse", "type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1},
        {"action": "mouse", "type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1},
    ])


LISTENERS = """(() => {
  window.__P1 = { paste: 0, beforeinput: [], keydownV: 0 };
  document.addEventListener('paste', function () { window.__P1.paste++; }, true);
  document.addEventListener('beforeinput', function (e) { window.__P1.beforeinput.push(e.inputType); }, true);
  document.addEventListener('keydown', function (e) { if (e.key === 'v' || e.key === 'V') window.__P1.keydownV++; }, true);
  return true;
})()"""


def open_doc():
    ev("(() => { window.__OPEN = 'pending'; window.MemoriaApp.openFile('cursor-test.md').then(function (r) { window.__OPEN = (r && r.status) || 'done'; }, function (e) { window.__OPEN = 'err:' + e; }); return 'started'; })()")
    for _ in range(120):
        if ev("window.__OPEN") not in ("pending", None):
            break
        time.sleep(0.2)
    time.sleep(0.9)


def set_mode(view: str):
    ev(f"(() => {{ document.querySelector('.-view-btn[data-view=\"{view}\"]')?.click(); return true; }})()")
    time.sleep(0.9)
    ev("(() => { const EH = window.MemoriaEditHandler; if (EH && !EH.editMode) EH.toggleEditMode(); return !!(EH && EH.editMode); })()")
    time.sleep(0.4)


def point_source():
    return ev("""(() => {
      const lines = [...document.querySelectorAll('#editor-pane .-line')];
      for (const ln of lines) {
        const c = ln.querySelector('.-line-content'); const t = c && (c.textContent || '');
        if (ln.dataset.line !== '1' && t && t.length >= 8 && t.length <= 40) {
          const tn = c.firstChild;
          if (!tn || tn.nodeType !== 3) continue;
          const rr = document.createRange();
          rr.setStart(tn, tn.nodeValue.length); rr.setEnd(tn, tn.nodeValue.length);
          const r = rr.getBoundingClientRect();
          return { line: +ln.dataset.line, x: Math.round(r.right - 1), y: Math.round(r.top + r.height / 2) };
        }
      }
      return null;
    })()""")


def point_preview():
    return ev("""(() => {
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


def read_after(markers, label):
    return ev("""(() => {
      const body = (window.state && window.state.doc && window.state.doc.body) || '';
      const lines = body.split(String.fromCharCode(10));
      const found = %s.map(function (m) { return lines.some(function (l) { return l.indexOf(m) >= 0; }); });
      const hitLines = lines.filter(function (l) { return l.indexOf('%s') >= 0; });
      const sel = window.getSelection();
      const r = sel && sel.rangeCount ? sel.getRangeAt(0) : null;
      let caretLine = null, caretOff = null, caretBlock = null;
      if (r) {
        const node = r.startContainer;
        const el = node && (node.nodeType === 3 ? node.parentElement : node);
        if (el && el.closest) {
          const ln = el.closest('[data-line]'); caretLine = ln ? +ln.dataset.line : null;
          const blk = el.closest('.-src-block'); caretBlock = blk ? (blk.textContent || '').slice(0, 60) : null;
        }
        caretOff = r.startOffset;
      }
      return { found: found, hitLineCount: hitLines.length, hitLines: hitLines.slice(0, 5),
               bodyLineCount: lines.length, caretLine: caretLine, caretOff: caretOff,
               caretBlock: caretBlock, collapsed: r ? r.isCollapsed : null,
               paste: window.__P1.paste, beforeinput: window.__P1.beforeinput.slice(-6), keydownV: window.__P1.keydownV };
    })()""" % (json.dumps(markers), label))


def set_clip(text):
    ev(f"(() => {{ const a = window.pywebview && window.pywebview.api; return a && a.clipboard_set_text ? a.clipboard_set_text({json.dumps(text)}) : 'no-api'; }})()")


def trial(mode: str, inject: str, trial_i: int) -> dict:
    open_doc()
    set_mode(mode)
    ctl({"op": "foreground"})
    time.sleep(0.5)
    title = fg_title()
    pt = point_source() if mode == "source" else point_preview()
    if not pt:
        return {"ok": False, "reason": "no-point"}
    prefix = "P1SRC" if mode == "source" else "P1PREV"
    text = f"{prefix}_ONE t{trial_i}a\n{prefix}_TWO t{trial_i}b\n{prefix}_THREE t{trial_i}c"
    markers = [f"{prefix}_ONE t{trial_i}a", f"{prefix}_TWO t{trial_i}b", f"{prefix}_THREE t{trial_i}c"]
    set_clip(text)
    time.sleep(0.25)
    ev("(() => { window.__P1 = { paste: 0, beforeinput: [], keydownV: 0 }; return true; })()")
    click(pt["x"], pt["y"])
    time.sleep(0.25)
    pre = ev("(() => ({ collapsed: window.getSelection().isCollapsed, focus: document.hasFocus() }))()")
    if inject == "os":
        os_ctrl_v()
    else:
        probe([{"action": "key", "key": "v", "code": "KeyV", "vk": 86, "modifiers": 2}])
    time.sleep(1.3)
    after = read_after(markers, f"{prefix}_")
    ok3 = all(after["found"]) and after["hitLineCount"] >= 3
    return {"ok": True, "mode": mode, "inject": inject, "trial": trial_i, "fgTitle": title,
            "preClick": pre, "point": pt, "after": after, "threeLines": ok3}


def main() -> int:
    os.makedirs(WORK, exist_ok=True)
    kb = WORK / "kb"
    if kb.exists():
        shutil.rmtree(kb)
    shutil.copytree(REPO / "tests" / "probe-kb", kb)
    (kb / "cursor-test.md").write_text(
        "# Cursor test\n\nALPHA one two three\n\nBETA four five six\n\nGAMMA seven eight nine\n", encoding="utf-8")
    cfg = WORK / "cfg"
    if cfg.exists():
        shutil.rmtree(cfg)
    os.makedirs(cfg, exist_ok=True)
    for f in ("cmd.json", "ack.json", "probe-cmd.json"):
        try:
            (WORK / f).unlink()
        except OSError:
            pass
    env = dict(os.environ)
    env.update({"T93_WORK": str(WORK), "T93_CDP_PORT": str(CDP_PORT), "MEMORIA_CONFIG_DIR": str(cfg),
                "MEMORIA_KB": str(kb), "MEMORIA_FRAMELESS": "0", "PYTHONIOENCODING": "utf-8"})
    env.pop("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", None)
    out = (WORK / "app.out.log").open("w", encoding="utf-8")
    err = (WORK / "app.err.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([PY, str(LAUNCH)], cwd=str(REPO), env=env, stdout=out, stderr=err)
    res = {"trials": [], "summary": {}}
    try:
        for _ in range(160):
            if up(f"http://127.0.0.1:{CDP_PORT}/json/version"):
                break
            time.sleep(0.5)
        time.sleep(6)
        ctl({"op": "foreground"})
        time.sleep(1.0)
        ev(LISTENERS)
        plan = ([("source", "os")] * N) + ([("preview", "os")] * N) + ([("preview", "cdp")] * N)
        for i, (mode, inject) in enumerate(plan):
            try:
                r = trial(mode, inject, i)
            except Exception as e:  # noqa: BLE001
                r = {"ok": False, "reason": str(e), "mode": mode, "inject": inject, "trial": i}
            res["trials"].append(r)
            print(f"[{i+1}/{len(plan)}] {mode}/{inject} threeLines={r.get('threeLines')} "
                  f"hit={((r.get('after') or {}).get('hitLineCount'))} paste={((r.get('after') or {}).get('paste'))} "
                  f"beforeinput={((r.get('after') or {}).get('beforeinput'))}", flush=True)

        def stat(mode, inject):
            ts = [t for t in res["trials"] if t.get("mode") == mode and t.get("inject") == inject and t.get("ok")]
            good = [t for t in ts if t.get("threeLines")]
            return {"runs": len(ts), "threeLines": len(good), "lost": len(ts) - len(good),
                    "pasteFired": sum(1 for t in ts if (t.get("after") or {}).get("paste", 0) > 0)}

        res["summary"] = {"source_os": stat("source", "os"), "preview_os": stat("preview", "os"),
                          "preview_cdp": stat("preview", "cdp"), "N": N}
        (HERE / "p1-verify.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(res["summary"], ensure_ascii=False, indent=1))
        # 判据
        po = res["summary"]["preview_os"]
        if po["lost"] >= 3:
            verdict = "PRODUCT_DEFECT"
        elif po["lost"] == 0:
            verdict = "MEASUREMENT_UNSTABLE"
        else:
            verdict = "INCONCLUSIVE"
        res["verdict"] = verdict
        print("VERDICT:", verdict)
        return 0
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close(); err.close()


if __name__ == "__main__":
    raise SystemExit(main())
