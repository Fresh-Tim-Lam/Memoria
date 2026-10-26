#!/usr/bin/env python
"""task-180 真机验证用本地 mock GitHub Releases 服务（只读、只记请求元数据）。

用法：
    python mock_update_server.py --port-file <tmp>/port.txt --log <tmp>/requests.jsonl \
        --payload-dir <fixture> [--chunk-delay 0.05]

端点：
    GET /latest              -> releases/latest JSON（资产 URL 指向本服务）
    GET /asset/<name>.zip    -> 按 64KB chunk 输出（可节流，用来测进度/取消）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ASSETS = [
    "Memoria-v0.4.10-win64-lite.zip",
    "Memoria-v0.4.10-win64.zip",
]
CHUNK = 64 * 1024


class Handler(BaseHTTPRequestHandler):
    server_version = "MemoriaMockUpdate/1.0"
    payload_dir: Path
    log_path: Path
    chunk_delay: float = 0.0
    base_url: str = ""
    _lock = threading.Lock()

    def log_message(self, fmt, *args):  # noqa: A003 - silence default stderr
        pass

    def _record(self, method: str) -> None:
        entry = {
            "ts": time.time(),
            "method": method,
            "path": self.path,
            "header_names": sorted(k.lower() for k in self.headers.keys()),
            "user_agent": self.headers.get("User-Agent", ""),
            "has_cookie": bool(self.headers.get("Cookie")),
            "has_auth": bool(self.headers.get("Authorization")),
        }
        try:
            with self._lock:
                with self.log_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001
            pass

    def do_GET(self):  # noqa: N802
        self._record("GET")
        if self.path == "/latest":
            self._send_latest()
            return
        if self.path.startswith("/asset/"):
            name = self.path[len("/asset/") :]
            path = self.payload_dir / name
            if not path.is_file():
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(path.stat().st_size))
            self.end_headers()
            with path.open("rb") as fh:
                while True:
                    chunk = fh.read(CHUNK)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
                    if self.chunk_delay:
                        time.sleep(self.chunk_delay)
            return
        self.send_error(404)

    def _send_latest(self):
        assets = []
        for name in ASSETS:
            path = self.payload_dir / name
            if not path.is_file():
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assets.append(
                {
                    "name": name,
                    "size": path.stat().st_size,
                    "browser_download_url": f"{self.base_url}/asset/{name}",
                    "digest": f"sha256:{digest}",
                }
            )
        payload = {
            "tag_name": "v0.4.10",
            "name": "v0.4.10",
            "published_at": "2026-10-26T00:00:00Z",
            "body": "## 更新说明（mock）\n\n- 版本更新机制真机验证\n- 修复若干问题",
            "html_url": f"{self.base_url}/release/v0.4.10",
            "assets": assets,
        }
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port-file", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--payload-dir", required=True)
    ap.add_argument("--chunk-delay", type=float, default=0.0)
    args = ap.parse_args()
    payload_dir = Path(args.payload_dir).resolve()
    log_path = Path(args.log).resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    Handler.payload_dir = payload_dir
    Handler.log_path = log_path
    Handler.chunk_delay = args.chunk_delay
    Handler.base_url = f"http://127.0.0.1:{port}"
    Path(args.port_file).write_text(str(port), encoding="utf-8")
    print(f"[mock] listening 127.0.0.1:{port} payload={payload_dir}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
