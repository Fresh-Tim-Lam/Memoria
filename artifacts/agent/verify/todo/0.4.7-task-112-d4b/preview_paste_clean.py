"""最小干净实验：预览区**多行粘贴**是否保留换行（fresh app，无前置阶段污染）。

真机 pywebview+WebView2；KB 临时副本 + 专用 cursor-test.md；真实鼠标点击定位 + 后端剪贴板 + 真实 Ctrl+V。
只回答一个问题：多行粘贴后 body 是否出现 3 行，光标在哪。
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
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t112_prev"
CDP_PORT = 9597
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
TOOLS = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-93-responsive"
LAUNCH = TOOLS / "launch_ctl.py"
PROBE = HERE / "probe112.mjs"
TEXT = "PREVX_ONE aaa\nPREVX_TWO bbb\nPREVX_THREE ccc"


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
    return json.loads(lines[-1])["results"] if lines else [{"error": p.stderr[-300:]}]


def ev(expr):
    r = probe([{"action": "eval", "expr": expr}])[0]
    return r.get("value") if isinstance(r, dict) else None


def evx(expr):
    """返回完整 eval 结果（含 exception），用于诊断。"""
    return probe([{"action": "eval", "expr": expr}])[0]


def main() -> int:
    os.makedirs(WORK, exist_ok=True)
    kb = WORK / "kb"
    if kb.exists():
        shutil.rmtree(kb)
    shutil.copytree(REPO / "tests" / "probe-kb", kb)
    (kb / "cursor-test.md").write_text("# Cursor test\n\nALPHA one two three\n\nBETA four five six\n\nGAMMA seven eight nine\n", encoding="utf-8")
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
    try:
        for _ in range(160):
            if up(f"http://127.0.0.1:{CDP_PORT}/json/version"):
                break
            time.sleep(0.5)
        time.sleep(6)
        # 前台（真实 Ctrl+V）
        ack = WORK / "ack.json"
        (WORK / "cmd.json").write_text(json.dumps({"op": "foreground", "_seq": time.time_ns()}), encoding="utf-8")
        time.sleep(0.6)
        ev("(() => { window.__OPEN = 'pending'; window.MemoriaApp.openFile('cursor-test.md').then(function (r) { window.__OPEN = (r && r.status) || 'done'; }, function (e) { window.__OPEN = 'err:' + e; }); return 'started'; })()")
        for _ in range(100):
            if ev("window.__OPEN") not in ("pending", None):
                break
            time.sleep(0.2)
        time.sleep(1.2)
        ev("(() => { document.querySelector('.-view-btn[data-view=\"preview\"]')?.click(); return true; })()")
        time.sleep(1.2)
        ev("(() => { const EH = window.MemoriaEditHandler; if (EH && !EH.editMode) EH.toggleEditMode(); return !!(EH && EH.editMode); })()")
        time.sleep(0.5)
        pt = ev("""(() => {
          const ps = [...document.querySelectorAll('#preview .-src-block')].filter(function (b) { return b.tagName === 'P'; });
          for (const p of ps) {
            const t = (p.textContent || '').trim();
            if (t.length > 8 && t.length < 60) {
              const tn = document.createTreeWalker(p, NodeFilter.SHOW_TEXT, null).nextNode();
              if (!tn) continue;
              const rr = document.createRange();
              rr.setStart(tn, (tn.nodeValue || '').length); rr.collapse(true);
              const r = rr.getBoundingClientRect();
              return { x: Math.round(r.right - 1), y: Math.round(r.top + r.height / 2), text: t };
            }
          }
          return null;
        })()""")
        readback = ev(f"(() => {{ const a = window.pywebview && window.pywebview.api; return a.clipboard_set_text({json.dumps(TEXT)}).then(function (r) {{ return a.clipboard_get_text(); }}); }})()")
        time.sleep(0.4)
        if pt:
            probe([{"action": "mouse", "type": "mousePressed", "x": pt["x"], "y": pt["y"], "button": "left", "clickCount": 1},
                   {"action": "mouse", "type": "mouseReleased", "x": pt["x"], "y": pt["y"], "button": "left", "clickCount": 1}])
            time.sleep(0.3)
            probe([{"action": "key", "key": "v", "code": "KeyV", "vk": 86, "modifiers": 2}])
            time.sleep(1.5)
        after_raw = evx("""(() => {
          const sel = window.getSelection();
          const r = sel && sel.rangeCount ? sel.getRangeAt(0) : null;
          const node = r ? r.startContainer : null;
          const el = node && (node.nodeType === 3 ? node.parentElement : node);
          const block = el && el.closest ? el.closest('.-src-block') : null;
          const body = (window.state && window.state.doc && window.state.doc.body) || '';
          const caret = (function () {
            if (!r) return null;
            const rr = document.createRange();
            try {
              if (r.startContainer.nodeType === 3 && r.startOffset > 0) { rr.setStart(r.startContainer, r.startOffset - 1); rr.setEnd(r.startContainer, r.startOffset); }
              else if (r.startContainer.nodeType === 3) { rr.setStart(r.startContainer, 0); rr.setEnd(r.startContainer, 1); }
              else return null;
              const b = rr.getBoundingClientRect();
              return { left: b.left, right: b.right, top: b.top, bottom: b.bottom };
            } catch (e) { return null; }
          })();
          return {
            collapsed: r ? r.isCollapsed : null, caret: caret,
            blockText: block ? (block.textContent || '').slice(0, 200) : null,
            bodyHasAll: ['PREVX_ONE aaa', 'PREVX_TWO bbb', 'PREVX_THREE ccc'].every(function (s) { return body.indexOf(s) >= 0; }),
            bodyLines: body.split(String.fromCharCode(10)).filter(function (l) { return l.indexOf('PREVX_') >= 0; }),
            lineCount: body.split(String.fromCharCode(10)).length,
          };
        })()""")
        res = {"clickPoint": pt, "clipboardReadback": readback, "after": after_raw, "text": TEXT}
        SHOTS = HERE / "shots"
        SHOTS.mkdir(parents=True, exist_ok=True)
        probe([{"action": "shot", "path": str(SHOTS / "preview_multiline_paste_collapsed_caret.png")}])
        res["shot"] = str(SHOTS / "preview_multiline_paste_collapsed_caret.png")
        (HERE / "preview-paste-clean.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(res, ensure_ascii=False, indent=1)[:2000])
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close(); err.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
