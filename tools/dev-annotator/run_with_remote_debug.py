"""Dev launcher: enable WebView2 remote debugging without touching product code.

Also injects the dev-only annotation board once the page is ready, so the board
survives reloads/restarts. Set MEMORIA_NO_ANNOTATOR=1 to disable.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import webview  # noqa: E402

WEBVIEW_PORT = int(os.environ.get("MEMORIA_CDP_PORT", "9222"))
webview.settings.data["REMOTE_DEBUGGING_PORT"] = WEBVIEW_PORT


def _auto_inject_annotator() -> None:
    if os.environ.get("MEMORIA_NO_ANNOTATOR") == "1":
        return
    try:
        import requests
        import websocket
    except Exception:
        return
    js_path = Path(__file__).with_name("annotator.js")
    if not js_path.is_file():
        return
    js = js_path.read_text(encoding="utf-8")
    url = f"http://127.0.0.1:{WEBVIEW_PORT}/json"
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
                pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
            if pages:
                ws = websocket.create_connection(pages[0]["webSocketDebuggerUrl"], timeout=5)
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
                return
        except Exception:
            pass
        time.sleep(0.5)


if __name__ == "__main__":
    os.environ.setdefault("MEMORIA_MODE", "dev")
    os.environ.setdefault("MEMORIA_SHELL", "pywebview")
    os.environ.setdefault("MEMORIA_DEBUG", "1")
    threading.Thread(target=_auto_inject_annotator, daemon=True).start()
    from memoria.app.desktop import main

    main()
