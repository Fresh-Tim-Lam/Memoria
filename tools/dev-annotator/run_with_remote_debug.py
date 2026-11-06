"""Dev launcher: enable WebView2 remote debugging without touching product code.

Also injects the dev-only annotation board once the page is ready, so the board
survives reloads/restarts. Set MEMORIA_NO_ANNOTATOR=1 to disable.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import webview  # noqa: E402


def _pick_port() -> int:
    """Prefer an explicit port; otherwise take a fresh free port.

    A fixed 9222/9223-style port is the usual reason the board attaches to a stale
    WebView2 target or fails to attach at all.
    """
    raw = os.environ.get("MEMORIA_CDP_PORT", "").strip()
    if raw:
        return int(raw)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])
    finally:
        s.close()


WEBVIEW_PORT = _pick_port()
webview.settings.data["REMOTE_DEBUGGING_PORT"] = WEBVIEW_PORT
PORT_PATH = ROOT / "artifacts" / "dev-cdp-port.txt"
LOG_PATH = ROOT / "artifacts" / "dev-annotator-inject.log"


def _log(message: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + message + "\n")
    except Exception:
        pass


def _auto_inject_annotator() -> None:
    if os.environ.get("MEMORIA_NO_ANNOTATOR") == "1":
        _log("disabled by MEMORIA_NO_ANNOTATOR=1")
        return
    try:
        import requests
        import websocket
    except Exception as exc:
        _log(f"missing dependency: {exc!r}")
        return
    js_path = Path(__file__).with_name("annotator.js")
    if not js_path.is_file():
        _log("annotator.js missing")
        return
    js = js_path.read_text(encoding="utf-8")
    url = f"http://127.0.0.1:{WEBVIEW_PORT}/json"
    last_error = ""
    _log(f"waiting for CDP port {WEBVIEW_PORT}")
    for _ in range(160):
        try:
            targets = requests.get(url, timeout=1).json()
            pages = [
                t for t in targets
                if t.get("type") == "page"
                and t.get("webSocketDebuggerUrl")
                and not str(t.get("url", "")).startswith("devtools://")
                and "127.0.0.1" in str(t.get("url", ""))
            ]
            if not pages:
                time.sleep(0.5)
                continue
            if pages:
                target = pages[0]
                ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=5)
                expr = "(() => { " + js + " })()"
                ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": expr, "awaitPromise": False}}))
                ws.recv()
                # 让批注板在未来 reload 后仍在：注册到 new-document
                src = (
                    "(() => { const run = () => { " + js + " };"
                    " if (document.readyState === 'loading')"
                    " document.addEventListener('DOMContentLoaded', run, { once: true });"
                    " else run(); })()"
                )
                ws.send(json.dumps({"id": 2, "method": "Page.enable", "params": {}}))
                ws.recv()
                ws.send(json.dumps({"id": 3, "method": "Page.addScriptToEvaluateOnNewDocument", "params": {"source": src}}))
                ws.recv()
                ws.close()
                _log(f"injected into {target.get('url')}")
                return
        except Exception as exc:
            last_error = repr(exc)
        time.sleep(0.5)
    _log(f"injection failed after retries: {last_error}")


def _watch_webview_board() -> None:
    """Last-resort in-process watchdog: re-inject the board via pywebview JS.

    This does not depend on CDP, a free port, DevTools targets or a reload hook.
    It keeps polling the live pywebview window so the board comes back even if the
    page rewrites its DOM or the user reloads the app.
    """
    if os.environ.get("MEMORIA_NO_ANNOTATOR") == "1":
        return
    js_path = Path(__file__).with_name("annotator.js")
    if not js_path.is_file():
        return
    js = js_path.read_text(encoding="utf-8")
    expr = "(() => { " + js + " })()"
    probe = "(() => !!document.getElementById('__memoria_annotator_host__'))()"
    ensure = "(() => { window.__MEMORIA_ANNOTATOR__?.ensureMounted?.(); return true; })()"
    _log("webview watchdog started")
    while True:
        try:
            for win in list(getattr(webview, "windows", []) or []):
                try:
                    present = win.evaluate_js(probe)
                    if not present:
                        win.evaluate_js(expr)
                        _log("injected via pywebview watchdog")
                    else:
                        win.evaluate_js(ensure)
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(1.5)


if __name__ == "__main__":
    os.environ.setdefault("MEMORIA_MODE", "dev")
    os.environ.setdefault("MEMORIA_SHELL", "pywebview")
    os.environ.setdefault("MEMORIA_DEBUG", "1")
    try:
        PORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        PORT_PATH.write_text(str(WEBVIEW_PORT), encoding="utf-8")
    except Exception:
        pass
    _log(f"launch KB={os.environ.get('MEMORIA_KB', '')} CDP={WEBVIEW_PORT}")
    threading.Thread(target=_auto_inject_annotator, daemon=True).start()
    threading.Thread(target=_watch_webview_board, daemon=True).start()
    from memoria.app.desktop import main

    main()
