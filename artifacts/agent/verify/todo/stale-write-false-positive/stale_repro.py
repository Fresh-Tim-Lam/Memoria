"""task-164 定位探针：真机复现「无外部写者时 stale_write 误报」。

做法（不改 src）：
  · 真机 pywebview + 临时 KB（复制 tests/probe-kb，自己生成 80 行测试文档）
  · 运行时把 MemoriaBridge.api() 换成 Proxy：记录每次 save_document 的
    (rel_path, base_version, force) 与返回（status/code/expected_version/current_version/version），
    并记录 load_document 返回的 version、openFile 调用、state.doc.version 前后值
  · 用 CDP 真实键盘在**行首**敲字，等 1.9s 自动保存；重复 ≥6 轮，另加行号区点击
  · 每轮后从磁盘直接算 sha256，与请求 base_version / 响应 version 并列落表
输出：stale-repro.json（逐轮表 + 事件日志 + 对话框是否出现）
"""

from __future__ import annotations

import hashlib
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
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t164"
CDP_PORT = 9631
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
TOOLS = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-93-responsive"
LAUNCH = TOOLS / "launch_ctl.py"
PROBE = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-112-d4b" / "probe112.mjs"
DOC = "教材/test-doc.md"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


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


def ev(expr, await_promise=True):
    r = probe([{"action": "eval", "expr": expr, "awaitPromise": await_promise}])[0]
    if isinstance(r, dict) and r.get("exception"):
        return {"__exception": r.get("exception")}
    return r.get("value") if isinstance(r, dict) else None


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


def click(x: int, y: int):
    probe([{"action": "mouse", "type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1},
           {"action": "mouse", "type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1}])


def type_text(text: str):
    """CDP 逐字符 keyDown/char/keyUp（与真人键盘同一输入路径）。"""
    cmds = []
    for ch in text:
        code = "Key" + ch.upper() if ch.isalpha() else ("Digit" + ch if ch.isdigit() else ch)
        vk = ord(ch.upper()) if ch.isalpha() else (ord(ch) if ch.isdigit() else 0)
        cmds.append({"action": "key", "key": ch, "code": code, "vk": vk, "text": ch, "modifiers": 0})
    probe(cmds)


INSTALL = """(() => {
  window.__WLOG = [];
  window.__CONFLICT = [];
  window.__INFLIGHT = 0;
  const realApi = window.MemoriaBridge.api();
  if (!realApi || !realApi.save_document) return { error: 'no-api' };
  const origSave = realApi.save_document.bind(realApi);
  const origLoad = realApi.load_document.bind(realApi);
  const origOpen = window.MemoriaApp.openFile ? window.MemoriaApp.openFile.bind(window.MemoriaApp) : null;
  const docVer = () => (window.state && window.state.doc && window.state.doc.version) || "";
  window.MemoriaBridge.api = function () {
    return new Proxy(realApi, {
      get(t, k) {
        if (k === 'save_document') {
          return async function (relPath, body, baseVersion, force) {
            const before = docVer();
            const inflightBefore = window.__INFLIGHT;
            const t0 = Date.now();
            window.__INFLIGHT++;
            let r;
            try {
              r = await origSave(relPath, body, baseVersion, force);
            } finally {
              window.__INFLIGHT--;
            }
            window.__WLOG.push({ kind: 'save', t: Date.now(), durMs: Date.now() - t0,
              inflightBefore: inflightBefore, relPath: relPath, baseVersion: baseVersion || '',
              force: !!force, docVersionBefore: before, status: r && r.status, code: r && r.code,
              expected_version: r && r.expected_version, current_version: r && r.current_version,
              version: r && r.version, bodyLen: (body || '').length, bodyTail: JSON.stringify((body || '').slice(-3)),
              docVersionAfter: docVer(), message: r && r.message });
            return r;
          };
        }
        if (k === 'load_document') {
          return async function (relPath) {
            const r = await origLoad(relPath);
            window.__WLOG.push({ kind: 'load', t: Date.now(), relPath: relPath,
              status: r && r.status, version: r && r.version, docVersionAfter: docVer() });
            return r;
          };
        }
        return t[k];
      },
    });
  };
  if (origOpen) {
    window.MemoriaApp.openFile = async function (p, o) {
      const before = docVer();
      window.__WLOG.push({ kind: 'openFile:start', t: Date.now(), path: p, docVersionBefore: before });
      const r = await origOpen(p, o);
      window.__WLOG.push({ kind: 'openFile:done', t: Date.now(), path: p, docVersionAfter: docVer(), status: r && r.status });
      return r;
    };
  }
  // 冲突对话框观察（DOM 变更）
  const mo = new MutationObserver(() => {
    const modal = document.querySelector('.-modal .-modal-header');
    if (modal && /File changed|文件已/.test(modal.textContent || '')) {
      const body = document.querySelector('.-modal .-modal-body');
      window.__CONFLICT.push({ t: Date.now(), title: modal.textContent, body: (body && body.textContent) || '' });
    }
  });
  mo.observe(document.body, { childList: true, subtree: true });
  // 捕获 [SYNC] 日志
  window.__SYNCLOG = [];
  const origLog = console.log.bind(console);
  console.log = function (...a) {
    try { if (a[0] === '[SYNC]') window.__SYNCLOG.push(a.map(String).join(' ').slice(0, 400)); } catch (_) {}
    return origLog.apply(console, a);
  };
  return { ok: true };
})()"""


def main() -> int:
    global DOC
    os.makedirs(WORK, exist_ok=True)
    kb = WORK / "kb"
    if kb.exists(): shutil.rmtree(kb)
    shutil.copytree(REPO / "tests" / "probe-kb", kb)
    (kb / "教材").mkdir(exist_ok=True)
    REAL = os.environ.get("STALE_REAL") == "1"
    if REAL:
        # 用【人报障的真实文件】（只读复制，绝不改用户 KB）：100KB 教材章节 + 19 个 KP 的 sidecar
        src = Path(r"D:\AAA_Courses\软件工程概论")
        DOC = "教材/03_第3章_软件需求获取与结构化分析方法.md"
        shutil.copy2(src / DOC, kb / DOC)
        sc_dir = kb / ".memoria" / "sidecars" / "教材"
        sc_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            src / ".memoria" / "sidecars" / "教材" / "03_第3章_软件需求获取与结构化分析方法.memoria.yaml",
            sc_dir / "03_第3章_软件需求获取与结构化分析方法.memoria.yaml",
        )
        BIG = DOC
    else:
        lines = ["# stale write 复现文档", ""]
        for i in range(1, 81):
            lines.append(f"第 {i:02d} 行：内容内容内容 content-{i}")
        (kb / DOC).write_text("\n".join(lines) + "\n", encoding="utf-8")
        BIG = "教材/big-doc.md"
        big_lines = ["# 大文档（模拟用户教材章节）", ""]
        for i in range(2000):
            big_lines.append(f"第 {i:04d} 行：正文正文正文正文正文正文 content-{i} 关键词{i % 37}")
        (kb / BIG).parent.mkdir(parents=True, exist_ok=True)
        (kb / BIG).write_text("\n".join(big_lines) + "\n", encoding="utf-8")
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
    res = {"doc": DOC, "rounds": [], "disk_sha_initial": sha(kb / DOC)}
    try:
        for _ in range(160):
            if up(f"http://127.0.0.1:{CDP_PORT}/json/version"): break
            time.sleep(0.5)
        time.sleep(7)
        ctl({"op": "foreground"})
        time.sleep(0.8)
        ev(f"(() => {{ window.__OPEN='pending'; window.MemoriaApp.openFile({json.dumps(DOC)}).then(function(r){{window.__OPEN=(r&&r.status)||'done';}}, function(e){{window.__OPEN='err:'+e;}}); return true; }})()")
        for _ in range(150):
            if ev("window.__OPEN") not in ("pending", None):
                break
            time.sleep(0.2)
        time.sleep(1.2)
        ev("(() => { const b = document.querySelector('.-view-btn[data-view=\"source\"]'); if (b) b.click(); return !!b; })()")
        time.sleep(1.2)
        inst = ev(INSTALL)
        res["install"] = inst
        # 定位源码编辑器：行内容起始点 / 行号点
        geo = ev("""(() => {
          const lines = [...document.querySelectorAll('#editor [data-line]')];
          if (!lines.length) return { error: 'no-lines', editor: !!(document.getElementById('editor')) };
          const pick = (idx) => {
            const el = lines[Math.min(idx, lines.length - 1)];
            const content = el.querySelector('.-line-content') || el;
            const ln = el.querySelector('.-lineno');
            const cr = content.getBoundingClientRect();
            const lr = ln ? ln.getBoundingClientRect() : null;
            return { line: el.dataset.line, content: { x: Math.round(cr.left + 3), y: Math.round(cr.top + cr.height / 2) },
                     gutter: lr ? { x: Math.round(lr.left + lr.width / 2), y: Math.round(lr.top + lr.height / 2) } : null };
          };
          return { count: lines.length, first: pick(4), second: pick(5), third: pick(6) };
        })()""")
        res["geometry"] = geo
        if not geo or geo.get("error"):
            res["error"] = "editor-not-ready"
        else:
            rounds = []
            # 6 轮：行首编辑（第 4..9 行），每轮 3 字符 + 等自动保存
            for i in range(6):
                before = sha(kb / DOC)
                pt = geo["first"] if i % 2 == 0 else geo["second"]
                click(pt["content"]["x"], pt["content"]["y"])
                time.sleep(0.15)
                type_text(f"Z{i}")
                time.sleep(1.9)
                rounds.append({"round": i + 1, "kind": "line-start-edit", "line": pt["line"],
                               "disk_before": before, "disk_after": sha(kb / DOC)})
            # 行号区点击 + 编辑
            g = geo["third"]["gutter"]
            before = sha(kb / DOC)
            click(g["x"], g["y"])
            time.sleep(0.25)
            click(geo["third"]["content"]["x"], geo["third"]["content"]["y"])
            time.sleep(0.15)
            type_text("GUT")
            time.sleep(1.9)
            rounds.append({"round": 7, "kind": "gutter-click-then-edit", "line": geo["third"]["line"],
                           "disk_before": before, "disk_after": sha(kb / DOC)})
            res["rounds"] = rounds
            # ── Phase B：连续打字（不等 1.9s）⇒ 自动保存可能与上一个保存重叠（候选 b）──
            click(geo["first"]["content"]["x"], geo["first"]["content"]["y"])
            time.sleep(0.15)
            b_before = sha(kb / DOC)
            for i in range(12):
                type_text("Q" + str(i % 10))
                time.sleep(0.12)
            time.sleep(2.2)
            res["phaseB"] = {"kind": "continuous-typing", "disk_before": b_before,
                             "disk_after": sha(kb / DOC)}
            # ── Phase C：直接并发两次 save_document（同一 base_version）⇒ 证明后端在并发下的行为（候选 b 机制）──
            res["phaseC"] = ev("""(async () => {
              const api = window.MemoriaBridge.api();
              const st = window.state;
              const path = st.currentPath;
              const v0 = (st.doc && st.doc.version) || '';
              const body = (st.doc && st.doc.body) || '';
              const a = api.save_document(path, body + '\\nCONC-A', v0, false);
              const b = api.save_document(path, body + '\\nCONC-B', v0, false);
              const ra = await a; const rb = await b;
              return { v0: v0,
                       a: { status: ra.status, code: ra.code, expected: ra.expected_version, current: ra.current_version, version: ra.version },
                       b: { status: rb.status, code: rb.code, expected: rb.expected_version, current: rb.current_version, version: rb.version } };
            })()""")
            time.sleep(0.4)
            ev(f"(() => {{ window.__OPEN='pending'; window.MemoriaApp.openFile({json.dumps(DOC)}).then(function(r){{window.__OPEN=(r&&r.status)||'done';}}); return true; }})()")
            for _ in range(80):
                if ev("window.__OPEN") not in ("pending", None):
                    break
                time.sleep(0.2)
            time.sleep(0.8)
            # ── Phase D：自然跨文件竞态 —— 编辑 A 后恰好在自动保存开始时切到 B（无任何外部写者）──
            # 目标：验证「旧文件 save 的响应把 version 写进新文件的 state.doc」是否导致 B 下一次保存误报
            B = "README.md"
            def open_sync(path):
                ev(f"(() => {{ window.__OPEN='pending'; window.MemoriaApp.openFile({json.dumps(path)}).then(function(r){{window.__OPEN=(r&&r.status)||'done';}}, function(e){{window.__OPEN='err:'+e;}}); return true; }})()")
                for _ in range(100):
                    if ev("window.__OPEN") not in ("pending", None):
                        break
                    time.sleep(0.2)
                time.sleep(0.6)
            # 预热 B（让后端/前端缓存热），再回 A
            open_sync(B)
            open_sync(DOC)
            geo2 = ev("""(() => {
              const lines = [...document.querySelectorAll('#editor [data-line]')];
              const el = lines[Math.min(9, lines.length - 1)];
              const c = (el.querySelector('.-line-content') || el).getBoundingClientRect();
              return { x: Math.round(c.left + 3), y: Math.round(c.top + c.height / 2) };
            })()""")
            click(geo2["x"], geo2["y"]); time.sleep(0.15)
            type_text("R1")
            # 自动保存 = 停止编辑 1500ms 后；在 1500ms 边界立刻切到 B（模拟用户"刚停手就切文件"）
            time.sleep(1.50)
            open_sync(B)
            time.sleep(1.0)
            d1 = ev("""(() => ({ path: window.state.currentPath,
                                docVersion: (window.state.doc && window.state.doc.version) || '' }))()""")
            diskB = sha(kb / B)
            # 在 B 上编辑 → 等待自动保存；若 state.doc.version 被 A 的保存污染 ⇒ 应弹 stale 假冲突
            geoB = ev("""(() => {
              const lines = [...document.querySelectorAll('#editor [data-line]')];
              const el = lines[Math.min(3, lines.length - 1)];
              const c = (el.querySelector('.-line-content') || el).getBoundingClientRect();
              return { x: Math.round(c.left + 3), y: Math.round(c.top + c.height / 2) };
            })()""")
            click(geoB["x"], geoB["y"]); time.sleep(0.15)
            type_text("RB")
            time.sleep(2.2)
            res["phaseD"] = {"kind": "cross-file-save-race",
                             "afterSwitch": d1, "disk_sha_B": diskB,
                             "versionMatchesDisk": d1.get("docVersion") == diskB,
                             "conflictAfterEditB": ev("window.__CONFLICT"),
                             "currentPath": ev("window.state.currentPath")}
            # 恢复 A（避免后续步骤被污染）
            open_sync(DOC)
            # ── Phase D2：页面内精确计时 —— 在"自动保存进行中"切到已预热的 B（无任何外部写者）──
            #   input 后 1520ms 触发 openFile(B)：autosave 在 1500ms 启动（实测 dur 60–90ms），
            #   ⇒ save 尚未返回时 state.doc 已被 B 的 load 替换，save 响应随后把 A 的 version 写进 B。
            geoD2 = ev("""(() => {
              const lines = [...document.querySelectorAll('#editor [data-line]')];
              const el = lines[Math.min(12, lines.length - 1)];
              const c = (el.querySelector('.-line-content') || el).getBoundingClientRect();
              return { x: Math.round(c.left + 3), y: Math.round(c.top + c.height / 2) };
            })()""")
            ev(f"""(() => {{
              window.__RACED2 = {{ inputAt: 0, firedAt: 0 }};
              const ed = document.getElementById('editor');
              function h() {{
                ed.removeEventListener('input', h, true);
                window.__RACED2.inputAt = Date.now();
                setTimeout(function () {{
                  window.__RACED2.firedAt = Date.now();
                  window.MemoriaApp.openFile({json.dumps(B)}, {{ skipNav: true }});
                }}, 1520);
              }}
              ed.addEventListener('input', h, true);
              return true;
            }})()""")
            click(geoD2["x"], geoD2["y"]); time.sleep(0.15)
            type_text("D2")
            time.sleep(3.0)
            d2 = ev("""(() => ({ path: window.state.currentPath,
                                docVersion: (window.state.doc && window.state.doc.version) || '',
                                race: window.__RACED2 }))()""")
            diskB2 = sha(kb / B)
            # 在 B 上编辑 ⇒ 若 B 的 state.doc.version 被 A 的 save 响应污染，这里必弹 stale 假冲突
            geoB2 = ev("""(() => {
              const lines = [...document.querySelectorAll('#editor [data-line]')];
              const el = lines[Math.min(3, lines.length - 1)];
              const c = (el.querySelector('.-line-content') || el).getBoundingClientRect();
              return { x: Math.round(c.left + 3), y: Math.round(c.top + c.height / 2) };
            })()""")
            click(geoB2["x"], geoB2["y"]); time.sleep(0.15)
            type_text("RB2")
            time.sleep(2.4)
            res["phaseD2"] = {"kind": "switch-during-save", "afterSwitch": d2, "disk_sha_B": diskB2,
                              "versionMatchesDisk": d2.get("docVersion") == diskB2,
                              "conflictAfterEditB": ev("window.__CONFLICT"),
                              "currentPath": ev("window.state.currentPath")}
            open_sync(DOC)
            # ── Phase F：同一文件在"自动保存进行中"被 reload（大文档 ⇒ load 比 save 慢）──
            # 目的：验证 load/save 响应乱序时，旧 load 的 version 会不会把 state.doc.version 写回旧值
            def open_big():
                ev(f"(() => {{ window.__OPEN='pending'; window.MemoriaApp.openFile({json.dumps(BIG)}).then(function(r){{window.__OPEN=(r&&r.status)||'done';}}, function(e){{window.__OPEN='err:'+e;}}); return true; }})()")
                for _ in range(200):
                    if ev("window.__OPEN") not in ("pending", None):
                        break
                    time.sleep(0.2)
                time.sleep(0.5)
            open_big()
            geoF = ev("""(() => {
              const lines = [...document.querySelectorAll('#editor [data-line]')];
              const el = lines[Math.min(20, lines.length - 1)];
              const c = (el.querySelector('.-line-content') || el).getBoundingClientRect();
              return { x: Math.round(c.left + 3), y: Math.round(c.top + c.height / 2) };
            })()""")
            click(geoF["x"], geoF["y"]); time.sleep(0.15)
            res["phaseF"] = {"kind": "same-file-reload-during-save", "doc": BIG}
            # 精确安排：在「本行第一次 input」后 1490ms（autosave=1500ms，早 10ms）触发同文件 reload
            ev(f"""(() => {{
              window.__RACEF = {{ firedAt: 0, inputAt: 0, path: {json.dumps(BIG)} }};
              const ed = document.getElementById('editor');
              function h() {{
                ed.removeEventListener('input', h, true);
                window.__RACEF.inputAt = Date.now();
                setTimeout(function () {{
                  window.__RACEF.firedAt = Date.now();
                  window.MemoriaApp.openFile({json.dumps(BIG)}, {{ skipNav: true }});
                }}, 1490);
              }}
              ed.addEventListener('input', h, true);
              return true;
            }})()""")
            type_text("F1")
            time.sleep(3.5)
            f1 = ev("""(() => ({ path: window.state.currentPath,
                                docVersion: (window.state.doc && window.state.doc.version) || '',
                                bodyLen: ((window.state.doc && window.state.doc.body) || '').length }))()""")
            res["phaseF"]["afterReload"] = f1
            res["phaseF"]["disk_sha"] = sha(kb / BIG)
            res["phaseF"]["versionMatchesDisk"] = f1.get("docVersion") == sha(kb / BIG)
            # 在（可能已污染的）state 上继续编辑 → 若 version 旧 ⇒ 应弹出 stale 假冲突
            click(geoF["x"], geoF["y"]); time.sleep(0.15)
            type_text("F2")
            time.sleep(2.2)
            res["phaseF"]["conflictAfterEdit"] = ev("window.__CONFLICT")
            res["phaseF"]["versionAfterSave"] = ev("(window.state.doc && window.state.doc.version) || ''")
            # ── Phase G：复刻用户行为（映射日志显示 16:31 是【预览区】click→beforeinput）
            open_sync(DOC)
            ev("(() => { const b = document.querySelector('.-view-btn[data-view=\"preview\"]'); if (b) b.click(); return !!b; })()")
            time.sleep(1.5)
            gdom = ev("""(() => {
              const pv = document.getElementById('preview');
              if (!pv) return { error: 'no-preview' };
              const blocks = [...pv.querySelectorAll('[contenteditable="true"]')];
              const any = [...pv.querySelectorAll('p, li, h1, h2, h3, .-line')].slice(0, 5).map((e) => ({ tag: e.tagName, ce: e.isContentEditable }));
              return { count: blocks.length, sample: any, editMode: !!(window.MemoriaEditHandler && window.MemoriaEditHandler.editMode) };
            })()""")
            res["phaseG"] = {"kind": "preview-edit", "dom": gdom}
            target = ev("""(() => {
              const pv = document.getElementById('preview');
              const cand = (pv && pv.querySelector('[contenteditable="true"]')) || (pv && pv.querySelector('p')) || pv;
              if (!cand) return null;
              cand.scrollIntoView({ block: 'center' });
              const r = cand.getBoundingClientRect();
              return { x: Math.round(r.left + 12), y: Math.round(r.top + 8), tag: cand.tagName,
                       ce: cand.isContentEditable, text: (cand.textContent || '').slice(0, 40) };
            })()""")
            res["phaseG"]["target"] = target
            if target:
                click(target["x"], target["y"]); time.sleep(0.2)
                type_text("PV")
                time.sleep(2.2)
                res["phaseG"]["disk_after"] = sha(kb / DOC)
                res["phaseG"]["docVersion"] = ev("(window.state.doc && window.state.doc.version) || ''")
                res["phaseG"]["conflict"] = ev("window.__CONFLICT")
                res["phaseG"]["bodyLen"] = ev("((window.state.doc && window.state.doc.body) || '').length")
                res["phaseG"]["versionMatchesDisk"] = res["phaseG"]["docVersion"] == res["phaseG"]["disk_after"]
            # 回源码模式，避免后续步骤受测
            ev("(() => { const b = document.querySelector('.-view-btn[data-view=\"source\"]'); if (b) b.click(); return !!b; })()")
            time.sleep(1.2)
        res["wlog"] = ev("window.__WLOG")
        res["conflict"] = ev("window.__CONFLICT")
        res["synclog"] = ev("window.__SYNCLOG.slice(-40)")
        res["docVersionFinal"] = ev("(window.state && window.state.doc && window.state.doc.version) || ''")
        res["disk_sha_final"] = sha(kb / DOC)
        res["dialog_dom"] = ev("(() => { const m = document.querySelector('.-modal .-modal-header'); return m ? m.textContent : null; })()")
        (HERE / "stale-repro.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k: res[k] for k in ("install", "geometry", "error", "docVersionFinal", "disk_sha_final", "dialog_dom") if k in res},
                         ensure_ascii=False, indent=1)[:2000])
        print("rounds:", json.dumps(res.get("rounds"), ensure_ascii=False)[:1500])
        print("wlog-save:", json.dumps([w for w in (res.get("wlog") or []) if w.get("kind") == "save"], ensure_ascii=False)[:3000])
        print("conflict:", json.dumps(res.get("conflict"), ensure_ascii=False)[:800])
        return 0
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close(); err.close()


if __name__ == "__main__":
    raise SystemExit(main())
