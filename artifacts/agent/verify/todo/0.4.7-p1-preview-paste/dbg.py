"""调试：确认点击点落点/视图模式/elementFromPoint（不产生结论）。"""
from __future__ import annotations
import json, os, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t137_dbg"
CDP_PORT = 9603
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
TOOLS = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-93-responsive"
PROBE = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-112-d4b" / "probe112.mjs"


def up(u):
    try:
        urllib.request.urlopen(u, timeout=2); return True
    except Exception:  # noqa: BLE001
        return False


def probe(cmds):
    (WORK / "probe-cmd.json").write_text(json.dumps({"cmds": cmds}), encoding="utf-8")
    p = subprocess.run(["node", str(PROBE), "--port", str(CDP_PORT), "--cmd", str(WORK / "probe-cmd.json")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    lines = (p.stdout or "").strip().splitlines()
    return json.loads(lines[-1])["results"] if lines else [{"error": p.stderr[-400:]}]


def ev(e):
    r = probe([{"action": "eval", "expr": e}])[0]
    return r.get("value") if isinstance(r, dict) else None


def main():
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
    proc = subprocess.Popen([PY, str(TOOLS / "launch_ctl.py")], cwd=str(REPO), env=env, stdout=out, stderr=err)
    try:
        for _ in range(160):
            if up(f"http://127.0.0.1:{CDP_PORT}/json/version"): break
            time.sleep(0.5)
        time.sleep(6)
        ev("(() => { window.__OPEN = 'pending'; window.MemoriaApp.openFile('cursor-test.md').then(function (r) { window.__OPEN = (r && r.status) || 'done'; }, function (e) { window.__OPEN = 'err:' + e; }); return 'started'; })()")
        for _ in range(120):
            if ev("window.__OPEN") not in ("pending", None): break
            time.sleep(0.2)
        time.sleep(1.0)
        print("A view/size:", json.dumps(ev("(() => ({ mode: window.state && window.state.viewMode, w: innerWidth, h: innerHeight, hasEditor: !!document.getElementById('editor-pane'), editorVis: document.getElementById('editor-pane') ? getComputedStyle(document.getElementById('editor-pane')).display : null }))()"), ensure_ascii=False))
        ev("(() => { document.querySelector('.-view-btn[data-view=\"source\"]')?.click(); return true; })()")
        time.sleep(1.0)
        print("B view:", json.dumps(ev("(() => ({ mode: window.state && window.state.viewMode, btns: [...document.querySelectorAll('[data-view]')].map(b => b.getAttribute('data-view') + ':' + (b.className||'')) }))()"), ensure_ascii=False))
        print("C lines:", json.dumps(ev("""(() => {
          const lines = [...document.querySelectorAll('#editor-pane .-line')];
          return lines.slice(0, 8).map(ln => { const c = ln.querySelector('.-line-content'); const r = c ? c.getBoundingClientRect() : null;
            return { line: ln.dataset.line, text: (c && c.textContent || '').slice(0, 20), rect: r ? { l: r.left, t: r.top, w: r.width, h: r.height } : null }; });
        })()"""), ensure_ascii=False)[:1200])
        print("D elementAt:", json.dumps(ev("(() => { const el = document.elementFromPoint(910, 145); return el ? { tag: el.tagName, cls: String(el.className), id: el.id } : null; })()"), ensure_ascii=False))
        print("E editMode:", ev("!!(window.MemoriaEditHandler && window.MemoriaEditHandler.editMode)"))
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close(); err.close()


if __name__ == "__main__":
    main()
