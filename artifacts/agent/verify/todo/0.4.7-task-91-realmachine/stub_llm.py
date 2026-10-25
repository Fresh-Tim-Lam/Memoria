"""task-133 本地 OpenAI 兼容桩端点（SSE）：让**真实应用的压缩管线**真的跑过一次摘要调用。

为什么用桩而不是用户真实密钥：
- 真机验证要证明的是「压缩真的会被观测到」——压缩管线（`ask._compact_if_needed` →
  `compaction.summarize_span` → 落 `compaction` 事件 → `_replay/ build_history` → UI 投影）全是真实代码；
  只有**模型服务**换成桩，避免消耗用户真实密钥/额度（这是仓库既有惯例：task-11/交互验收都用桩端点）。
- 桩按请求内容分流：末条消息含「压缩引擎」（= `COMPACTION_INSTRUCTION`）⇒ 返回 checkpoint 摘要；
  其余 ⇒ 返回普通最终答案（无工具调用）。

每个请求同时追加一行到 `<work>/stub-requests.jsonl`，作为「压缩调用确实发生」的旁证。
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WORK = Path(os.environ.get("T133_WORK", "."))
LOG = WORK / "stub-requests.jsonl"

SUMMARY_TEXT = (
    "## 用户的原始诉求与意图演变\n- 真机验证：把上下文推过压缩阈值后继续对话。\n"
    "## 关键概念\n- 字符预算 / 压缩阈值 / checkpoint\n"
    "## 文件与内容\n- (none)\n"
    "## 错误与修法\n- (none)\n"
    "## 待办\n- (none)\n"
    "## 当前进展\n- 桩端点替代真实模型返回本 checkpoint\n"
    "## 下一步\n- 继续回答新问题\n"
    "## 关键上下文\n- 这是 task-133 真机验证专用摘要，内容可作压缩后回放证据。\n"
)
ANSWER_TEXT = "真机验证回答：已按当前（压缩后的）上下文继续。"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: object) -> None:  # 静默默认访问日志
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8", "replace"))
        except Exception:
            body = {}
        messages = body.get("messages") or []
        is_compaction = any("压缩引擎" in str(m.get("content") or "") for m in messages)
        record = {
            "kind": "compaction" if is_compaction else "answer",
            "messages": len(messages),
            "model": body.get("model"),
            "stream": body.get("stream"),
            "last_role": (messages[-1] or {}).get("role") if messages else None,
            "last_content_head": str(((messages[-1] or {}).get("content") or ""))[:60],
        }
        try:
            with LOG.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

        text = SUMMARY_TEXT if is_compaction else ANSWER_TEXT
        chunks = [text[i : i + 24] for i in range(0, len(text), 24)] or [""]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        for piece in chunks:
            frame = {"choices": [{"index": 0, "delta": {"content": piece}}]}
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
    port = int(os.environ.get("T133_STUB_PORT", "9599"))
    serve_forever(port)
    print(f"stub listening on 127.0.0.1:{port}", flush=True)
    threading.Event().wait()
