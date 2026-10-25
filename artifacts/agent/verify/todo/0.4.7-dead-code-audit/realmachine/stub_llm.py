"""task-134 真机验证 · 本地 OpenAI 兼容 SSE 桩（只替代模型服务；附件/工具/RPC 全是真实代码）。

额外记录 `has_resource_note`：请求体任一消息是否包含资源提示段
（"用户拖入了以下资料文件"）—— 作为「发送时资源提示真的注入到请求」的旁证。
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WORK = Path(os.environ.get("T134_WORK", "."))
LOG = WORK / "stub-requests.jsonl"

ANSWER_TEXT = "真机验证回答：已收到（task-134 资源附件验证）。"
RESOURCE_NOTE_MARK = "用户拖入了以下资料文件"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8", "replace"))
        except Exception:
            body = {}
        messages = body.get("messages") or []
        joined = "\n".join(str(m.get("content") or "") for m in messages)
        record = {
            "kind": "compaction" if "压缩引擎" in joined else "answer",
            "messages": len(messages),
            "has_resource_note": RESOURCE_NOTE_MARK in joined,
            "last_user_head": str(((messages[-1] or {}).get("content") or ""))[:120] if messages else "",
        }
        try:
            with LOG.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

        text = ANSWER_TEXT
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        for i in range(0, len(text), 24):
            frame = {"choices": [{"index": 0, "delta": {"content": text[i : i + 24]}}]}
            self.wfile.write(("data: " + json.dumps(frame, ensure_ascii=False) + "\n\n").encode("utf-8"))
            self.wfile.flush()
        stop = {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
        self.wfile.write(("data: " + json.dumps(stop, ensure_ascii=False) + "\n\n").encode("utf-8"))
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        self.close_connection = True


def serve_forever(port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    port = int(os.environ.get("T134_STUB_PORT", "9599"))
    serve_forever(port)
    print(f"stub listening on 127.0.0.1:{port}", flush=True)
    threading.Event().wait()
