#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 配套开发者工具：验证的调用面语义移植自 deepseek-harness packages/llm/*（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""agent LLM 冒烟工具：读配置 → 发一句 prompt → 打印流式回答与用量。

用法：
    python scripts/agent_llm_smoke.py --mock            # 离线：本地假 SSE 端点（127.0.0.1 随机端口）
    python scripts/agent_llm_smoke.py "用一句话解释贝叶斯定理"

配置来源与库内一致：环境变量 `MEMORIA_AGENT_BASE_URL` / `MEMORIA_AGENT_API_KEY` /
`MEMORIA_AGENT_MODEL` / `MEMORIA_AGENT_TIMEOUT_S`，回退到本地 `config/agent.json`。
密钥只用于请求头，**绝不打印**（只打印掩码）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SRC = str(ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from memoria.services.agent.llm import (  # noqa: E402
    AgentConfig,
    AgentLlmError,
    FinishEvent,
    FinishReason,
    LlmRequest,
    Message,
    ReasoningDelta,
    RetryPolicy,
    Role,
    TextDelta,
    UsageEvent,
    UsageMeter,
    create_provider,
    iter_with_retry,
    load_config,
    mask_secret,
)

DEFAULT_PROMPT = "用一句话说明 Memoria 是什么。"
MOCK_ANSWER = "Memoria 是一个本地知识图谱 IDE：Markdown 笔记、知识点、双链与图谱都在本机运行。"
MOCK_REASONING = "先给出一句概括，不必展开。"
#: 每片文本之间的停顿，让「流式」在终端里可见。
MOCK_CHUNK_DELAY_S = 0.05


def _chunks(text: str, size: int = 8) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def _mock_sse_payloads(model: str, prompt_tokens: int) -> list[str]:
    """构造一段 OpenAI 兼容的 SSE 载荷（推理 → 正文 → 用量 → [DONE]）。"""
    payloads: list[str] = []
    for piece in _chunks(MOCK_REASONING, 12):
        payloads.append(
            json.dumps(
                {"choices": [{"index": 0, "delta": {"reasoning_content": piece}, "finish_reason": None}]},
                ensure_ascii=False,
            )
        )
    for piece in _chunks(MOCK_ANSWER):
        payloads.append(
            json.dumps(
                {"choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]},
                ensure_ascii=False,
            )
        )
    payloads.append(
        json.dumps(
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            ensure_ascii=False,
        )
    )
    completion = len(_chunks(MOCK_REASONING, 12)) + len(_chunks(MOCK_ANSWER))
    payloads.append(
        json.dumps(
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion,
                    "total_tokens": prompt_tokens + completion,
                },
            },
            ensure_ascii=False,
        )
    )
    payloads.append("[DONE]")
    return payloads


class _MockHandler(BaseHTTPRequestHandler):
    """最小假端点：对任何 POST 都回一段流式 SSE（用于离线冒烟）。"""

    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: object) -> None:  # 静音默认访问日志
        return

    def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler 约定
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            body = {}
        model = str(body.get("model") or "mock-model")
        prompt_tokens = max(1, len(json.dumps(body, ensure_ascii=False)) // 4)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        for payload in _mock_sse_payloads(model, prompt_tokens):
            self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
            self.wfile.flush()
            time.sleep(MOCK_CHUNK_DELAY_S)


class MockServer:
    """本地假 SSE 服务（127.0.0.1 随机端口），仅冒烟用。"""

    def __init__(self) -> None:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _MockHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="agent-llm-mock", daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/v1"

    def __enter__(self) -> MockServer:
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def _build_config(args: argparse.Namespace) -> AgentConfig:
    base = load_config()
    return AgentConfig(
        base_url=args.base_url or base.base_url,
        api_key=base.api_key,
        model=args.model or base.model,
        timeout_s=args.timeout or base.timeout_s,
        source=base.source,
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="agent LLM 冒烟工具（dsh 移植 M1）")
    parser.add_argument("prompt", nargs="?", default=DEFAULT_PROMPT, help="发送给模型的单句 prompt")
    parser.add_argument("--mock", action="store_true", help="离线：本地假 SSE 端点（不访问外网）")
    parser.add_argument("--model", default="", help="覆盖模型名")
    parser.add_argument("--base-url", default="", help="覆盖端点基址（形如 https://host/v1）")
    parser.add_argument("--timeout", type=float, default=0.0, help="覆盖超时秒数")
    parser.add_argument("--max-tokens", type=int, default=2048, help="输出上限（推理型模型会先把配额花在思考上，默认给足 2048）")
    parser.add_argument("--no-retry", action="store_true", help="关闭重试（单次尝试）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    config = _build_config(args)
    if args.mock:
        with MockServer() as server:
            config = AgentConfig(
                base_url=server.base_url,
                api_key="",
                model=args.model or "mock-model",
                timeout_s=args.timeout or 15.0,
                source="mock",
            )
            return _run(config, args)
    print(f"[config] base_url={config.base_url or '（未配置）'} model={config.model} timeout={config.timeout_s}s")
    print(f"[config] api_key={mask_secret(config.api_key) or '（未配置，按无认证发送）'} source={config.source}")
    return _run(config, args)


def _run(config: AgentConfig, args: argparse.Namespace) -> int:
    if args.mock:
        print(f"[mock] 本地假端点：{config.base_url}")
    request = LlmRequest(
        model=config.model,
        messages=(Message(role=Role.USER, content=args.prompt),),
        temperature=0.2,
        max_tokens=args.max_tokens,
        timeout_s=config.timeout_s,
    )
    provider = create_provider(config=config)
    policy = None if args.no_retry else RetryPolicy()
    meter = UsageMeter()
    finish: FinishEvent | None = None
    print(f"[ask] {args.prompt}")
    print("[answer] ", end="", flush=True)
    reasoning_open = False  # 推理增量按流拼接：不要给每个增量换行加前缀，否则中文会被拆成"一字一行"
    try:
        stream = iter_with_retry(lambda: provider.stream(request), policy=policy)
        for event in stream:
            if isinstance(event, TextDelta):
                print(event.text, end="", flush=True)
            elif isinstance(event, ReasoningDelta):
                if not reasoning_open:
                    print("[reasoning] ", file=sys.stderr, end="", flush=True)
                    reasoning_open = True
                print(event.text, file=sys.stderr, end="", flush=True)
            elif isinstance(event, UsageEvent):
                meter.add(event.usage)
            elif isinstance(event, FinishEvent):
                finish = event
    except AgentLlmError as exc:
        print(f"\n[error] {exc!r}", file=sys.stderr)
        return 1
    if reasoning_open:
        print(file=sys.stderr)
    print()
    if finish is None:
        print("[error] 流未给出终止事件", file=sys.stderr)
        return 1
    snapshot = meter.to_dict()
    print(
        f"[usage] 本次 prompt={meter.last.prompt_tokens if meter.last else 0}"
        f" completion={meter.last.completion_tokens if meter.last else 0}"
        f" total={meter.last.total if meter.last else 0}"
        f" estimated={'yes' if (meter.last and meter.last.estimated) else 'no'}"
    )
    print(
        f"[usage] 累计 calls={snapshot['calls']} total={snapshot['total_tokens']}"
        f" estimated_calls={snapshot['estimated_calls']}"
    )
    print(f"[finish] reason={finish.reason.value} tool_calls={len(finish.tool_calls)}")
    if finish.reason is FinishReason.MAX_TOKENS:
        print(
            f"[warn] 输出被 max-tokens 截断（本次 {args.max_tokens}）：推理型模型的思考也吃这个配额，"
            f"正文可能一个字都没轮到 —— 用 --max-tokens 调大（如 4096）再试",
            file=sys.stderr,
        )
    if finish.failure is not None:
        print(f"[error] 流内失败：{finish.failure!r}", file=sys.stderr)
        return 1
    return 0 if finish.reason is not FinishReason.ERROR else 1


if __name__ == "__main__":
    if os.environ.get("MEMORIA_AGENT_DEBUG"):
        import logging

        logging.basicConfig(level=logging.DEBUG)
    raise SystemExit(main())
