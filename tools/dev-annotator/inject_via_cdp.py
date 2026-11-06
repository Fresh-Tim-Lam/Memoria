"""Inject the dev-only annotation board into the Memoria WebView2 page via CDP."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests
import websocket

ROOT = Path(__file__).resolve().parents[2]
JS = (Path(__file__).with_name("annotator.js")).read_text(encoding="utf-8")


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9222
    url = f"http://127.0.0.1:{port}/json"
    last = None
    for _ in range(40):
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
                print(json.dumps({"target": target.get("url"), "title": target.get("title")}, ensure_ascii=False))
                ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=5)
                expr = "(() => { " + JS + " })()"
                ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": expr, "awaitPromise": False}}))
                reply = json.loads(ws.recv())
                print(json.dumps({"cdp": reply}, ensure_ascii=False)[:500])
                ws.close()
                return 0 if "result" in reply else 1
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(0.5)
    print(f"CDP inject failed: {last}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
