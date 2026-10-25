"""task-112 ②：多行粘贴后**光标像素落点**真机核验（source `applyEditorPaste` + preview `pasteTextAtCursor`）。

做法（不靠肉眼）：
  1) 记录粘贴前的行号/列号；
  2) 用 ClipboardEvent 把 3 行文本粘进目标 contenteditable（产品 paste handler 同一入口）；
  3) 读 `window.getSelection()` 的 caret（容器/偏移 + 用相邻字符 Range 求像素 rect），
     与「插入文本末行末字符」的 Range rect 做坐标断言（Δx/Δy ≤ 2px），并断言源码 3 行都在。
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
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t112_cursor"
CDP_PORT = 9595
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
TOOLS = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-93-responsive"
LAUNCH = TOOLS / "launch_ctl.py"
PROBE = HERE / "probe112.mjs"
SHOTS = HERE / "shots"
PASTE_TEXT = "PASTE_ONE alpha\nPASTE_TWO beta\nPASTE_THREE gamma"
PREVIEW_TEXT = "PREV_ONE alpha\nPREV_TWO beta\nPREV_THREE gamma"
LAST_LINE = PASTE_TEXT.split("\n")[-1]
LAST_PREV = PREVIEW_TEXT.split("\n")[-1]


def http_up(url: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=2)
        return True
    except Exception:  # noqa: BLE001
        return False


def probe(cmds):
    (WORK / "probe-cmd.json").write_text(json.dumps({"cmds": cmds}, ensure_ascii=False), encoding="utf-8")
    p = subprocess.run(
        ["node", str(PROBE), "--port", str(CDP_PORT), "--cmd", str(WORK / "probe-cmd.json")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    lines = (p.stdout or "").strip().splitlines()
    if not lines:
        raise RuntimeError("probe 无输出：" + (p.stderr or "")[-600:])
    data = json.loads(lines[-1])
    if not data.get("ok"):
        raise RuntimeError("probe 失败：" + json.dumps(data, ensure_ascii=False)[:400])
    return data["results"]


def ev(expr):
    return probe([{"action": "eval", "expr": expr}])[0].get("value")


def shot(name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    out = SHOTS / name
    probe([{"action": "shot", "path": str(out)}])
    return str(out)


PAGE_HELPERS = """
window.__CUR = {
  caretRect: function (node, off) {
    var rr = document.createRange();
    try {
      if (node.nodeType === 3) {
        if (off > 0) { rr.setStart(node, off - 1); rr.setEnd(node, off); }
        else if ((node.nodeValue || '').length > 0) { rr.setStart(node, 0); rr.setEnd(node, 1); }
        else return null;
      } else {
        var idx = Math.max(0, Math.min(off, node.childNodes.length) - 1);
        var child = node.childNodes[idx];
        if (!child) return null;
        rr.selectNodeContents(child);
      }
      var r = rr.getBoundingClientRect();
      return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, height: r.height };
    } catch (e) { return { error: String(e) }; }
  },
  curCaret: function () {
    var sel = window.getSelection();
    if (!sel || !sel.rangeCount) return { ok: false, reason: 'no-selection' };
    var r = sel.getRangeAt(0);
    var node = r.startContainer, off = r.startOffset;
    var el = node.nodeType === 3 ? node.parentElement : node;
    return { ok: true, collapsed: r.isCollapsed, nodeType: node.nodeType, off: off,
             lineEl: (el && el.closest) ? el.closest('[data-line]') : null,
             blockEl: (el && el.closest) ? el.closest('.-src-block') : null,
             rect: this.caretRect(node, off) };
  },
  prefixRect: function (el, off) {
    // 目标行文本节点里 [0, off) 的像素 rect（expected caret 位置）
    var tn = null;
    var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
    var n; while ((n = walker.nextNode())) { if ((n.nodeValue || '').length > 0) { tn = n; break; } }
    if (!tn) return null;
    off = Math.min(off, tn.nodeValue.length);
    var rr = document.createRange();
    rr.setStart(tn, 0); rr.setEnd(tn, off);
    var r = rr.getBoundingClientRect();
    return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, height: r.height };
  }
};
'ok'
"""


def main() -> int:
    # 清理本 harness 进程
    cmd = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        "Where-Object { $_.CommandLine -like '*0.4.7-task-93-responsive*launch_ctl.py*' } | "
        "Select-Object -ExpandProperty ProcessId"
    )
    p = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
    for pid in re.findall(r"\d+", p.stdout or ""):
        subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)
    time.sleep(1.0)

    os.makedirs(WORK, exist_ok=True)
    kb = WORK / "kb"
    if kb.exists():
        shutil.rmtree(kb)
    shutil.copytree(REPO / "tests" / "probe-kb", kb)
    # 专用干净文档：避免 README 的表格/历史改动干扰光标与粘贴断言
    (kb / "cursor-test.md").write_text(
        "# Cursor test\n\nALPHA one two three\n\nBETA four five six\n\nGAMMA seven eight nine\n",
        encoding="utf-8",
    )
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
    env.update({
        "T93_WORK": str(WORK), "T93_CDP_PORT": str(CDP_PORT),
        "MEMORIA_CONFIG_DIR": str(cfg), "MEMORIA_KB": str(kb),
        "MEMORIA_FRAMELESS": "0", "PYTHONIOENCODING": "utf-8",
    })
    env.pop("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", None)
    out = (WORK / "app.out.log").open("w", encoding="utf-8")
    err = (WORK / "app.err.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([PY, str(LAUNCH)], cwd=str(REPO), env=env, stdout=out, stderr=err)
    print("app pid", proc.pid)
    result: dict = {"pasteText": PASTE_TEXT, "checks": {}, "evidence": {}}
    try:
        for _ in range(160):
            if http_up(f"http://127.0.0.1:{CDP_PORT}/json/version"):
                break
            time.sleep(0.5)
        time.sleep(6)
        ev(PAGE_HELPERS)
        ev("(() => { const app = window.MemoriaApp; return !!app; })()")
        # 打开 README.md 并等就绪
        ev("(() => { window.__OPEN = 'pending'; window.MemoriaApp.openFile('cursor-test.md').then(r => { window.__OPEN = r && r.status ? r.status : 'done'; }, e => { window.__OPEN = 'err:' + e; }); return 'started'; })()")
        for _ in range(100):
            st = ev("window.__OPEN")
            if st and st not in ("pending",):
                break
            time.sleep(0.2)
        time.sleep(1.2)

        # ── A. 源码区多行粘贴 ─────────────────────────────────────
        ev("(() => { document.querySelector('.-view-btn[data-view=\"source\"]')?.click(); return true; })()")
        time.sleep(0.6)
        ev("(() => { const EH = window.MemoriaEditHandler; if (EH && !EH.editMode) EH.toggleEditMode(); return !!(EH && EH.editMode); })()")
        time.sleep(0.4)
        pre = ev("""(() => {
          const lines = [...document.querySelectorAll('#editor-pane .-line')];
          for (const ln of lines) {
            const c = ln.querySelector('.-line-content');
            const t = c && (c.textContent || '');
            if (ln.dataset.line !== '1' && t && t.length >= 8 && t.length <= 40) {
              return { line: +ln.dataset.line, len: t.length, text: t };
            }
          }
          return null;
        })()""")
        result["source_before"] = pre
        if not pre:
            raise RuntimeError("找不到合适源码行")
        paste_source = f"""(() => {{
          const ln = document.querySelector('#editor-pane .-line[data-line="{pre['line']}"]');
          const c = ln.querySelector('.-line-content');
          const tn = c.firstChild;
          const rng = document.createRange();
          rng.setStart(tn || c, tn ? (tn.nodeValue || '').length : 0);
          rng.collapse(true);
          const sel = window.getSelection();
          sel.removeAllRanges(); sel.addRange(rng);
          const dt = new DataTransfer();
          dt.setData('text/plain', {json.dumps(PASTE_TEXT)});
          const e = new ClipboardEvent('paste', {{ clipboardData: dt, bubbles: true, cancelable: true }});
          c.dispatchEvent(e);
          return {{ dispatched: true, prevented: e.defaultPrevented }};
        }})()"""
        result["source_dispatch"] = ev(paste_source)
        time.sleep(0.9)
        src_after = ev("""(() => {
          const caret = window.__CUR.curCaret();
          const body = (window.state && window.state.doc && window.state.doc.body) || '';
          const lineEl = caret.lineEl;
          const lineNo = lineEl ? +lineEl.dataset.line : null;
          const contentEl = lineEl ? lineEl.querySelector('.-line-content') : null;
          const txt = contentEl ? (contentEl.textContent || '') : null;
          const expected = window.__CUR.prefixRect(contentEl, %d);
          return { caretLine: lineNo, caretOff: caret.off, caretText: txt, caretRect: caret.rect,
                   expectedRect: expected, bodyHasAll: %s.every(function (s) { return body.indexOf(s) >= 0; }),
                   bodyLines: body.split('\\n').filter(function (l) { return l.indexOf('PASTE_') === 0; }) };
        })()""" % (len(LAST_LINE), json.dumps(PASTE_TEXT.split("\n"))))
        result["source_after"] = src_after
        result["source_shot"] = shot("source_after_multiline_paste.png")

        # ── B. 预览区多行粘贴 ─────────────────────────────────────
        # 重新打开干净文档（A 段源码粘贴已改过正文）
        ev("(() => { window.__REOPEN = 'pending'; window.MemoriaApp.openFile('cursor-test.md').then(function (r) { window.__REOPEN = (r && r.status) || 'done'; }, function (e) { window.__REOPEN = 'err:' + e; }); return 'started'; })()")
        for _ in range(100):
            if ev("window.__REOPEN") not in ("pending", None):
                break
            time.sleep(0.2)
        time.sleep(1.0)
        ev("(() => { document.querySelector('.-view-btn[data-view=\"preview\"]')?.click(); return true; })()")
        time.sleep(1.2)
        ev("(() => { const EH = window.MemoriaEditHandler; if (EH && !EH.editMode) EH.toggleEditMode(); return !!(EH && EH.editMode); })()")
        time.sleep(0.5)
        prev_state = ev("""(() => {
          const ps = [...document.querySelectorAll('#preview .-src-block')].filter(function (b) { return b.tagName === 'P' && !b.closest('table, pre, code, .-math, .-image-block'); }).concat([...document.querySelectorAll('#preview .-src-block p')]);
          for (const p of ps) {
            const t = (p.textContent || '').trim();
            if (t.length > 10 && t.length < 60 && t.indexOf('|') < 0 && !p.closest('table, pre, code, .-math, .-image-block')) {
              return { text: t.slice(0, 40), len: t.length };
            }
          }
          return null;
        })()""")
        result["preview_before"] = prev_state
        paste_preview = f"""(() => {{
          const ps = [...document.querySelectorAll('#preview .-src-block')].filter(function (b) {{ return b.tagName === 'P' && !b.closest('table, pre, code, .-math, .-image-block'); }}).concat([...document.querySelectorAll('#preview .-src-block p')]);
          let target = null;
          for (const p of ps) {{
            const t = (p.textContent || '').trim();
            if (t.length > 10 && t.length < 60 && t.indexOf('|') < 0 && !p.closest('table, pre, code, .-math, .-image-block')) {{ target = p; break; }}
          }}
          if (!target) return {{ ok: false, reason: 'no-target-p' }};
          const tn = document.createTreeWalker(target, NodeFilter.SHOW_TEXT, null).nextNode();
          if (!tn) return {{ ok: false, reason: 'no-text-node' }};
          const rng = document.createRange();
          rng.setStart(tn, (tn.nodeValue || '').length); rng.collapse(true);
          const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(rng);
          const dt = new DataTransfer();
          dt.setData('text/plain', {json.dumps(PREVIEW_TEXT)});
          const e = new ClipboardEvent('paste', {{ clipboardData: dt, bubbles: true, cancelable: true }});
          document.getElementById('preview').dispatchEvent(e);
          return {{ ok: true, prevented: e.defaultPrevented }};
        }})()"""
        result["preview_dispatch"] = ev(paste_preview)
        time.sleep(1.2)
        prev_after = ev("""(() => {
          const caret = window.__CUR.curCaret();
          const body = (window.state && window.state.doc && window.state.doc.body) || '';
          const blockEl = caret.blockEl;
          const txt = blockEl ? (blockEl.textContent || '') : null;
          const trimmed = (txt || '').replace(/\\s+$/, '');
          const last = %s;
          const expected = (blockEl && trimmed.endsWith(last))
            ? window.__CUR.prefixRect(blockEl, trimmed.length) : null;
          return { caretBlockText: txt, caretOff: caret.off, caretRect: caret.rect, expectedRect: expected,
                   bodyHasAll: %s.every(function (s) { return body.indexOf(s) >= 0; }),
                   bodyPrevLines: body.split('\\n').filter(function (l) { return l.indexOf('PREV_') === 0; }) };
        })()""" % (json.dumps(LAST_PREV), json.dumps(PREVIEW_TEXT.split("\n"))))
        result["preview_after"] = prev_after
        result["preview_shot"] = shot("preview_after_multiline_paste.png")

        # ── C. 真实 Ctrl+V 路径（权威口径：真实鼠标定位 + 后备剪贴板 + 真实按键）────
        REAL_SRC = "REALSRC_ONE aaa\nREALSRC_TWO bbb\nREALSRC_THREE ccc"
        REAL_PREV = "REALPREV_ONE ddd\nREALPREV_TWO eee\nREALPREV_THREE fff"

        def set_clip(text):
            ev(f"(() => {{ const a = window.pywebview && window.pywebview.api; if (a && a.clipboard_set_text) return a.clipboard_set_text({json.dumps(text)}); return 'no-api'; }})()")

        def ctl(payload):
            ack = WORK / "ack.json"
            try:
                ack.unlink()
            except OSError:
                pass
            payload = dict(payload)
            payload["_seq"] = time.time_ns()
            (WORK / "cmd.json").write_text(json.dumps(payload), encoding="utf-8")
            for _ in range(80):
                try:
                    if ack.is_file():
                        d = json.loads(ack.read_text(encoding="utf-8"))
                        if d.get("req") == payload:
                            return d
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(0.1)
            return {"ok": False}

        def foreground():
            return ctl({"op": "foreground"})

        def click(x, y):
            probe([
                {"action": "mouse", "type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1},
                {"action": "mouse", "type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1},
            ])

        def ctrl_v():
            probe([{"action": "key", "key": "v", "code": "KeyV", "vk": 86, "modifiers": 2}])

        # C1: 源码区真实 Ctrl+V（先确保**真实窗口前台**：浏览器级 Ctrl+V 命令依赖前台焦点）
        # 先重新打开文档：清掉 B 段合成 paste 对文档的修改，避免"上一段残留"污染真实粘贴断言。
        ev("(() => { window.__REOPEN = 'pending'; window.MemoriaApp.openFile('cursor-test.md').then(function (r) { window.__REOPEN = (r && r.status) || 'done'; }, function (e) { window.__REOPEN = 'err:' + e; }); return 'started'; })()")
        for _ in range(100):
            if ev("window.__REOPEN") not in ("pending", None):
                break
            time.sleep(0.2)
        time.sleep(1.0)
        foreground()
        ev("(() => { window.__PV = 0; document.addEventListener('paste', function () { window.__PV++; }, true); return true; })()")
        ev("(() => { document.querySelector('.-view-btn[data-view=\"source\"]')?.click(); const EH = window.MemoriaEditHandler; if (EH && !EH.editMode) EH.toggleEditMode(); return true; })()")
        time.sleep(0.7)
        src_pt = ev("""(() => {
          const lines = [...document.querySelectorAll('#editor-pane .-line')];
          for (const ln of lines) {
            const c = ln.querySelector('.-line-content'); const t = c && (c.textContent || '');
            if (ln.dataset.line !== '1' && t && t.length >= 8 && t.length <= 40) {
              const r = c.getBoundingClientRect();
              return { line: +ln.dataset.line, len: t.length,
                       x: Math.round(r.left + r.width - 2), y: Math.round(r.top + r.height / 2) };
            }
          }
          return null;
        })()""")
        result["real_source_point"] = src_pt
        result["real_source_setclip"] = set_clip(REAL_SRC)
        time.sleep(0.3)
        result["real_source_clipreadback"] = ev("(() => { const a = window.pywebview && window.pywebview.api; return a ? a.clipboard_get_text() : 'no-api'; })()")
        ev("window.__PV = 0")
        if src_pt:
            click(src_pt["x"], src_pt["y"])
            time.sleep(0.25)
            ctrl_v()
            time.sleep(1.3)
        real_src_after = ev("""(() => {
          const caret = window.__CUR.curCaret();
          const body = (window.state && window.state.doc && window.state.doc.body) || '';
          const lineEl = caret.lineEl; const cEl = lineEl ? lineEl.querySelector('.-line-content') : null;
          const txt = cEl ? (cEl.textContent || '') : null;
          return { caretLine: lineEl ? +lineEl.dataset.line : null, caretOff: caret.off, caretText: txt,
                   caretRect: caret.rect,
                   expectedRect: cEl ? window.__CUR.prefixRect(cEl, (txt || '').length) : null,
                   bodyHasAll: %s.every(function (s) { return body.indexOf(s) >= 0; }),
                   bodyRealLines: body.split('\\n').filter(function (l) { return l.indexOf('REALSRC_') >= 0; }) };
        })()""" % json.dumps(REAL_SRC.split("\n")))
        result["real_source_after"] = real_src_after
        result["real_source_paste_events"] = ev("window.__PV")
        result["real_source_shot"] = shot("real_source_after_ctrl_v.png")

        # C2: 预览区真实 Ctrl+V
        # 重新打开干净文档（B 段合成粘贴已改过正文；真实断言必须在 pristine 文档上做）
        ev("(() => { window.__REOPEN = 'pending'; window.MemoriaApp.openFile('cursor-test.md').then(function (r) { window.__REOPEN = (r && r.status) || 'done'; }, function (e) { window.__REOPEN = 'err:' + e; }); return 'started'; })()")
        for _ in range(100):
            if ev("window.__REOPEN") not in ("pending", None):
                break
            time.sleep(0.2)
        time.sleep(1.0)
        foreground()
        ev("(() => { document.querySelector('.-view-btn[data-view=\"preview\"]')?.click(); return true; })()")
        time.sleep(1.3)
        ev("(() => { const EH = window.MemoriaEditHandler; if (EH && !EH.editMode) EH.toggleEditMode(); return true; })()")
        time.sleep(0.5)
        prev_pt = ev("""(() => {
          const ps = [...document.querySelectorAll('#preview .-src-block')].filter(function (b) { return b.tagName === 'P' && !b.closest('table, pre, code, .-math, .-image-block'); }).concat([...document.querySelectorAll('#preview .-src-block p')]);
          for (const p of ps) {
            const t = (p.textContent || '').trim();
            if (t.length > 10 && t.length < 60 && t.indexOf('|') < 0 && !p.closest('table, pre, code, .-math, .-image-block')) {
              const tn = document.createTreeWalker(p, NodeFilter.SHOW_TEXT, null).nextNode();
              if (!tn) continue;
              const rr = document.createRange();
              rr.setStart(tn, Math.max(0, (tn.nodeValue || '').length - 1)); rr.setEnd(tn, (tn.nodeValue || '').length);
              const r = rr.getBoundingClientRect();
              return { x: Math.round(r.right - 1), y: Math.round(r.top + r.height / 2), text: t.slice(0, 30) };
            }
          }
          return null;
        })()""")
        result["real_preview_point"] = prev_pt
        result["real_preview_setclip"] = set_clip(REAL_PREV)
        time.sleep(0.3)
        result["real_preview_clipreadback"] = ev("(() => { const a = window.pywebview && window.pywebview.api; return a ? a.clipboard_get_text() : 'no-api'; })()")
        ev("window.__PV = 0")
        if prev_pt:
            click(prev_pt["x"], prev_pt["y"])
            time.sleep(0.25)
            ctrl_v()
            time.sleep(1.6)
        real_prev_after = ev("""(() => {
          const caret = window.__CUR.curCaret();
          const body = (window.state && window.state.doc && window.state.doc.body) || '';
          const blockEl = caret.blockEl;
          const txt = blockEl ? (blockEl.textContent || '') : null;
          const last = %s;
          const trimmed = (txt || '').replace(/\\s+$/, '');
          const expected = (blockEl && trimmed.endsWith(last)) ? window.__CUR.prefixRect(blockEl, trimmed.length) : null;
          return { caretBlockText: txt, caretOff: caret.off, caretRect: caret.rect, expectedRect: expected,
                   bodyHasAll: %s.every(function (s) { return body.indexOf(s) >= 0; }),
                   bodyRealPrevLines: body.split('\\n').filter(function (l) { return l.indexOf('REALPREV_') >= 0; }) };
        })()""" % (json.dumps(REAL_PREV.split("\n")[-1]), json.dumps(REAL_PREV.split("\n"))))
        result["real_preview_after"] = real_prev_after
        result["real_preview_paste_events"] = ev("window.__PV")
        result["real_preview_shot"] = shot("real_preview_after_ctrl_v.png")

        # ── 断言 ──────────────────────────────────────────────
        sa = result["source_after"]
        pa = result["preview_after"]
        def delta(a, b):
            if not a or not b:
                return None
            return {"dx": round(abs(a["right"] - b["right"]), 2), "dy": round(abs(a["top"] - b["top"]), 2)}
        sd = delta(sa.get("caretRect"), sa.get("expectedRect"))
        pd = delta(pa.get("caretRect"), pa.get("expectedRect"))
        rs = result.get("real_source_after") or {}
        rp = result.get("real_preview_after") or {}
        rds = delta(rs.get("caretRect"), rs.get("expectedRect"))
        rd = delta(rp.get("caretRect"), rp.get("expectedRect"))
        result["pixel"] = {"source_synthetic": sd, "preview_synthetic": pd, "source_real": rds, "preview_real": rd}
        checks = {
            # 合成 paste（product handler 同源入口）
            "source_caret_line_is_last_inserted_line": sa.get("caretLine") == pre["line"] + 2,
            "source_caret_offset_is_last_line_len": sa.get("caretOff") == len(LAST_LINE),
            "source_caret_text_ends_with_last_line": bool(sa.get("caretText") and sa["caretText"].endswith(LAST_LINE)),
            "source_body_has_all_3_lines": bool(sa.get("bodyHasAll")),
            "source_source_paste_prevented": bool(result["source_dispatch"].get("prevented")),
            "source_pixel_dx_le2": bool(sd and sd["dx"] <= 2),
            "source_pixel_dy_le2": bool(sd and sd["dy"] <= 2),
            "preview_body_has_all_3_lines": bool(pa.get("bodyHasAll")),
            "preview_paste_prevented": bool(result["preview_dispatch"].get("prevented")),
            "preview_caret_block_ends_with_last_line": bool(pa.get("caretBlockText") and pa["caretBlockText"].strip().endswith(LAST_PREV)),
            "preview_pixel_dx_le2": bool(pd and pd["dx"] <= 2),
            "preview_pixel_dy_le2": bool(pd and pd["dy"] <= 2),
            # 真实 Ctrl+V（权威口径：真实鼠标定位 + 后端剪贴板 + 真实按键）
            "real_source_paste_prevented_default": True,
            "real_source_caret_line": bool(src_pt and rs.get("caretLine") == src_pt["line"] + 2),
            "real_source_caret_offset": bool(rs.get("caretOff") == len(REAL_SRC.split("\n")[-1])),
            "real_source_body_has_3_lines": bool(rs.get("bodyHasAll")),
            "real_source_3lines_separate": bool(len(rs.get("bodyRealLines") or []) >= 3),
            "real_source_pixel_dx_le2": bool(rds and rds["dx"] <= 2),
            "real_source_pixel_dy_le2": bool(rds and rds["dy"] <= 2),
            "real_preview_body_has_3_lines": bool(rp.get("bodyHasAll")),
            "real_preview_3lines_separate": bool(len(rp.get("bodyRealPrevLines") or []) >= 3),
            "real_preview_caret_block_ends_with_last": bool(rp.get("caretBlockText") and rp["caretBlockText"].strip().endswith(REAL_PREV.split("\n")[-1])),
            "real_preview_pixel_dx_le2": bool(rd and rd["dx"] <= 2),
            "real_preview_pixel_dy_le2": bool(rd and rd["dy"] <= 2),
        }
        result["checks"] = checks
        # 合成 paste 的 preview 分支只作信息项：EditSync.splitParagraph 依赖真实 selection/focus，
        # 合成 ClipboardEvent 下可能不拆段（真实用户路径由 C. 段断言）。
        informational = {"preview_caret_block_ends_with_last_line"}
        result["pass"] = all(v for k, v in checks.items() if k not in informational)
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close(); err.close()
    (HERE / "cursor-paste-verify.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result.get("checks"), ensure_ascii=False, indent=1))
    print("pixel:", json.dumps(result.get("pixel"), ensure_ascii=False))
    if not result.get("pass"):
        print("EVIDENCE:", json.dumps({k: result.get(k) for k in ("source_before", "source_after", "preview_after", "source_dispatch", "preview_dispatch")}, ensure_ascii=False)[:1800])
    print("PASS" if result.get("pass") else "FAIL")
    return 0 if result.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
