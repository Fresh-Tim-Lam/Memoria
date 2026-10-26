"""task-164 修复验证（真机，两向）：误报消失 + 真报不丢。

A. 跨文件竞态（误报真因）：A 自动保存进行中切到 B（无任何外部写者）
   ⇒ 修复后 B 的 state.doc.version 必须等于 B 盘上 sha；B 再改再存必须 ok、不弹框。
B. 真报不丢：另起进程真改 A 的文件 ⇒ 下一次保存必须 stale_write 且弹出三选一对话框。
C. 常规：连续 5 次行首/行号区编辑保存，全部 ok、不弹框、version 与盘上一致。

输出：stale-verify.json
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
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t164_verify"
CDP_PORT = 9637
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
TOOLS = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-93-responsive"
LAUNCH = TOOLS / "launch_ctl.py"
PROBE = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-112-d4b" / "probe112.mjs"
SRC_KB = Path(r"D:\AAA_Courses\软件工程概论")
DOC = "教材/03_第3章_软件需求获取与结构化分析方法.md"
B = "README.md"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


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


def click(x, y):
    probe([{"action": "mouse", "type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1},
           {"action": "mouse", "type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1}])


def type_text(text):
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
            try { r = await origSave(relPath, body, baseVersion, force); } finally { window.__INFLIGHT--; }
            window.__WLOG.push({ kind: 'save', t: Date.now(), durMs: Date.now() - t0, inflightBefore,
              relPath, baseVersion: baseVersion || '', force: !!force, docVersionBefore: before,
              status: r && r.status, code: r && r.code, expected: r && r.expected_version,
              current: r && r.current_version, version: r && r.version, docVersionAfter: docVer(),
              message: r && r.message });
            return r;
          };
        }
        return t[k];
      },
    });
  };
  if (origOpen) {
    window.MemoriaApp.openFile = async function (p, o) {
      window.__WLOG.push({ kind: 'openFile:start', t: Date.now(), path: p, docVersionBefore: docVer() });
      const r = await origOpen(p, o);
      window.__WLOG.push({ kind: 'openFile:done', t: Date.now(), path: p, docVersionAfter: docVer(), status: r && r.status });
      return r;
    };
  }
  // 冲突框判定：以「force 按钮存在」为准（不依赖具体语言/标题文案）
  const mo = new MutationObserver(() => {
    const btn = document.querySelector('.-modal [data-act="force"]');
    if (btn) {
      const hdr = btn.closest('.-modal').querySelector('.-modal-header');
      const bodyEl = btn.closest('.-modal').querySelector('.-modal-body');
      window.__CONFLICT.push({ t: Date.now(), title: (hdr && hdr.textContent) || '', body: (bodyEl && bodyEl.textContent) || '' });
    }
  });
  mo.observe(document.body, { childList: true, subtree: true });
  return { ok: true };
})()"""


def main() -> int:
    os.makedirs(WORK, exist_ok=True)
    kb = WORK / "kb"
    if kb.exists(): shutil.rmtree(kb)
    shutil.copytree(REPO / "tests" / "probe-kb", kb)
    (kb / "教材").mkdir(exist_ok=True)
    shutil.copy2(SRC_KB / DOC, kb / DOC)
    sc = kb / ".memoria" / "sidecars" / "教材"
    sc.mkdir(parents=True, exist_ok=True)
    sc_name = Path(DOC).name.replace(".md", ".memoria.yaml")
    shutil.copy2(SRC_KB / ".memoria" / "sidecars" / "教材" / sc_name, sc / sc_name)
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
    res = {"doc": DOC, "phases": {}, "saves": 0}
    try:
        for _ in range(160):
            if up(f"http://127.0.0.1:{CDP_PORT}/json/version"): break
            time.sleep(0.5)
        time.sleep(7)
        ctl({"op": "foreground"}); time.sleep(0.8)

        def open_path(path):
            ev(f"(() => {{ window.__OPEN='pending'; window.MemoriaApp.openFile({json.dumps(path)}).then(function(r){{window.__OPEN=(r&&r.status)||'done';}}, function(e){{window.__OPEN='err:'+e;}}); return true; }})()")
            for _ in range(150):
                if ev("window.__OPEN") not in ("pending", None): break
                time.sleep(0.2)
            time.sleep(0.8)

        def geo(idx=8):
            return ev(f"""(() => {{
              const lines = [...document.querySelectorAll('#editor [data-line]')];
              const el = lines[Math.min({idx}, lines.length - 1)];
              const c = (el.querySelector('.-line-content') || el).getBoundingClientRect();
              const ln = el.querySelector('.-lineno');
              const lr = ln ? ln.getBoundingClientRect() : null;
              return {{ x: Math.round(c.left + 3), y: Math.round(c.top + c.height / 2),
                        gx: lr ? Math.round(lr.left + lr.width / 2) : 0, gy: lr ? Math.round(lr.top + lr.height / 2) : 0 }};
            }})()""")

        open_path(DOC)
        ev("(() => { const b = document.querySelector('.-view-btn[data-view=\"source\"]'); if (b) b.click(); return !!b; })()")
        time.sleep(1.0)
        res["install"] = ev(INSTALL)
        # 预热 B
        open_path(B); open_path(DOC)

        # ── Phase A：跨文件切换发生在 A 的自动保存进行中（误报真因）──
        gA = geo(8)
        ev(f"""(() => {{
          window.__RACEA = {{ inputAt: 0, firedAt: 0 }};
          const ed = document.getElementById('editor');
          function h() {{
            ed.removeEventListener('input', h, true);
            window.__RACEA.inputAt = Date.now();
            setTimeout(function () {{
              window.__RACEA.firedAt = Date.now();
              window.MemoriaApp.openFile({json.dumps(B)}, {{ skipNav: true }});
            }}, 1520);
          }}
          ed.addEventListener('input', h, true);
          return true;
        }})()""")
        click(gA["x"], gA["y"]); time.sleep(0.15)
        type_text("AA")
        time.sleep(3.0)
        a1 = ev("""(() => ({ path: window.state.currentPath,
                            docVersion: (window.state.doc && window.state.doc.version) || '',
                            race: window.__RACEA }))()""")
        diskB = sha(kb / B)
        res["phases"]["A_afterSwitch"] = {**a1, "disk_sha_B": diskB, "versionMatchesDisk": a1.get("docVersion") == diskB}
        # B 上再改再存：修复后必须 ok；修复前这里会 stale（误报）
        gB = ev("""(() => {
          const lines = [...document.querySelectorAll('#editor [data-line]')];
          const el = lines[Math.min(3, lines.length - 1)];
          const c = (el.querySelector('.-line-content') || el).getBoundingClientRect();
          return { x: Math.round(c.left + 3), y: Math.round(c.top + c.height / 2) };
        })()""")
        click(gB["x"], gB["y"]); time.sleep(0.15)
        type_text("AB")
        time.sleep(2.4)
        res["phases"]["A_thenSaveB"] = {"conflict": ev("window.__CONFLICT"),
                                        "version": ev("(window.state.doc && window.state.doc.version) || ''"),
                                        "disk_sha_B": sha(kb / B)}

        # ── Phase B：真报不丢（外部进程真改盘）──
        open_path(DOC)
        gB2 = geo(10)
        click(gB2["x"], gB2["y"]); time.sleep(0.15)
        type_text("TT")
        time.sleep(0.30)  # 在 autosave（1500ms）之前
        external_note = "\n\n<!-- EXTERNAL-WRITER 16:xx task-164 true-conflict probe -->\n"
        with open(kb / DOC, "a", encoding="utf-8") as fh:
            fh.write(external_note)
        time.sleep(2.2)
        res["phases"]["B_trueConflict"] = {
            "conflict": ev("window.__CONFLICT"),
            "dialogForceBtnPresent": ev("!!document.querySelector('.-modal [data-act=\"force\"]')"),
            "saveStale": ev("(window.__WLOG||[]).filter(function(w){return w.kind==='save' && w.code==='stale_write';}).length"),
            "version": ev("(window.state.doc && window.state.doc.version) || ''"),
            "disk_sha": sha(kb / DOC),
        }
        # 点「重载」收尾，丢弃本地编辑，避免污染后续
        ev("(() => { const b = document.querySelector('.-modal [data-act=\"reload\"]'); if (b) b.click(); return !!b; })()")
        time.sleep(1.6)

        # ── Phase C：连续 5 次行首/行号区编辑保存 —— 固件要求 ① ──
        rounds = []
        for i in range(5):
            g = geo(6 + i)
            before = sha(kb / DOC)
            click(g["x"], g["y"]); time.sleep(0.15)
            type_text(f"C{i}")
            time.sleep(2.0)
            after = sha(kb / DOC)
            v = ev("(window.state.doc && window.state.doc.version) || ''")
            rounds.append({"round": i + 1, "kind": "line-start", "disk_before": before, "disk_after": after,
                           "versionMatchesDisk": v == after})
        # 行号区点击后再编辑
        g = geo(11)
        before = sha(kb / DOC)
        click(g["gx"], g["gy"]); time.sleep(0.25)
        click(g["x"], g["y"]); time.sleep(0.15)
        type_text("GUT")
        time.sleep(2.0)
        after = sha(kb / DOC)
        rounds.append({"round": 6, "kind": "gutter-click-then-edit", "disk_before": before,
                       "disk_after": after,
                       "versionMatchesDisk": ev("(window.state.doc && window.state.doc.version) || ''") == after})
        res["phases"]["C_rounds"] = rounds
        res["phases"]["C_conflict"] = ev("window.__CONFLICT")
        saves = ev("(window.__WLOG||[]).filter(function(w){return w.kind==='save';})")
        res["saves"] = len(saves or [])
        res["saves_log"] = saves
        res["docVersionFinal"] = ev("(window.state.doc && window.state.doc.version) || ''")
        res["disk_sha_final"] = sha(kb / DOC)
        res["versionMatchesDiskFinal"] = res["docVersionFinal"] == res["disk_sha_final"]
        (HERE / "stale-verify.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print("=== A_afterSwitch ===", json.dumps(res["phases"]["A_afterSwitch"], ensure_ascii=False))
        print("=== A_thenSaveB ===", json.dumps(res["phases"]["A_thenSaveB"], ensure_ascii=False)[:500])
        print("=== B_trueConflict ===", json.dumps(res["phases"]["B_trueConflict"], ensure_ascii=False)[:800])
        print("=== C_rounds ===", json.dumps(rounds, ensure_ascii=False))
        print("=== C_conflict ===", json.dumps(res["phases"]["C_conflict"], ensure_ascii=False)[:300])
        print("=== final ===", res["versionMatchesDiskFinal"], res["docVersionFinal"][:12], res["disk_sha_final"][:12], "saves", res["saves"])
        return 0
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close(); err.close()


if __name__ == "__main__":
    raise SystemExit(main())
