#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 配套命令行工具：调用面语义移植自 deepseek-harness packages/core/agent-loop（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""知识库问答 CLI（dsh 移植 M1 第二块）。

用法：
    python scripts/agent_ask.py --mock --kb <知识库路径> "这个知识库大概有什么内容？"
    python scripts/agent_ask.py --kb <知识库路径> "多层感知机讲了什么？"

`--mock` 使用**内置脚本化假 provider**（不联网）：第一步发一个 `search_kb` 工具
调用，第二步用工具结果（带 `文件:行号` 锚点）产出最终答案，从而让整条竖切
（提问 → 检索 → 工具回填 → 回答 → 会话落盘）离线可验证。

真实模式读 `MEMORIA_AGENT_BASE_URL` / `MEMORIA_AGENT_API_KEY` / `MEMORIA_AGENT_MODEL`
（回退 `config/agent.json`）；密钥只打印掩码。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
_SRC = str(ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from memoria.services.agent.ask import ask  # noqa: E402
from memoria.services.agent.llm import (  # noqa: E402
    FinishEvent,
    FinishReason,
    LlmRequest,
    Role,
    TextDelta,
    ToolCall,
    Usage,
    UsageEvent,
    create_provider,
    load_config,
    mask_secret,
)
from memoria.services.agent.prompt import load_instructions, prompt_debug_info  # noqa: E402

MOCK_MODEL = "mock-model"
_ROW = re.compile(r"^\d+\.\s+(\S+\.md)(?::(\d+))?\s+(.*?)（", re.M)


# —— 内置脚本化假 provider（离线）——


def _last_user_text(request: LlmRequest) -> str:
    for message in reversed(request.messages):
        if message.role in (Role.USER, "user"):
            return message.content
    return ""


def _is_tool_message(message: Any) -> bool:
    return message.role in (Role.TOOL, "tool")


def _estimate_tokens(request: LlmRequest, completion: str) -> Usage:
    prompt = max(1, sum(len(m.content) for m in request.messages) // 4)
    return Usage(prompt_tokens=prompt, completion_tokens=max(1, len(completion) // 4), estimated=True)


def _chunks(text: str, size: int = 12) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def _compose_answer(tool_text: str) -> str:
    """用工具结果拼出最终答案（含 `文件:行号` 锚点）。"""
    rows = _ROW.findall(tool_text)
    header = "（本回答由 `--mock` 脚本化假 provider 生成，不含真实模型推理。）"
    if not rows:
        return f"{header}\n工具没有命中任何知识点，因此无法给出带锚点的回答。"
    lines = [header, "这个知识库大致包含以下内容："]
    anchors: list[str] = []
    for rel, line, name in rows[:5]:
        location = f"{rel}:{line}" if line else rel
        anchors.append(location)
        lines.append(f"- `{location}` {name.strip()}")
    lines.append("引用锚点：" + "、".join(f"`{anchor}`" for anchor in anchors))
    return "\n".join(lines)


class ScriptedMockProvider:
    """两段脚本：第一次请求发 `search_kb`，第二次用工具结果产出最终答案。"""

    name = "mock"

    def __init__(self) -> None:
        self.calls = 0

    def stream(self, request: LlmRequest) -> Iterator[Any]:
        self.calls += 1
        tool_texts = [message.content for message in request.messages if _is_tool_message(message)]
        if not tool_texts:
            query = _last_user_text(request).strip() or "知识库"
            arguments = json.dumps({"query": query, "top_k": 5}, ensure_ascii=False)
            note = f"[mock] 先检索知识库：{query}"
            yield TextDelta(note)
            yield UsageEvent(_estimate_tokens(request, note))
            yield FinishEvent(
                reason=FinishReason.TOOL_CALLS,
                tool_calls=(ToolCall(id="mock-call-1", name="search_kb", arguments=arguments),),
            )
            return
        answer = _compose_answer(tool_texts[-1])
        for piece in _chunks(answer):
            yield TextDelta(piece)
        yield UsageEvent(_estimate_tokens(request, answer))
        yield FinishEvent(reason=FinishReason.STOP)


# —— CLI ——


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="知识库问答 CLI（dsh 移植 M1）")
    parser.add_argument("question", nargs="+", help="要问的问题")
    parser.add_argument("--kb", required=True, help="知识库目录（含 .memoria/）")
    parser.add_argument("--mock", action="store_true", help="离线：内置脚本化假 provider（不联网）")
    parser.add_argument("--model", default="", help="覆盖模型名")
    parser.add_argument("--max-iterations", type=int, default=8, help="模型步数上限（默认 8）")
    parser.add_argument("--top-k", type=int, default=5, help="search_kb 默认返回条数")
    parser.add_argument("--session-id", default="", help="复用/指定会话 id（默认新建）")
    parser.add_argument("--no-stream", action="store_true", help="不逐片打印回答，只在结束时打印")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    question = " ".join(args.question).strip()
    kb_path = str(Path(args.kb).expanduser().resolve())

    if args.mock:
        provider: Any = ScriptedMockProvider()
        model = args.model or MOCK_MODEL
        print(f"[mock] 离线脚本化假 provider（model={model}）")
    else:
        config = load_config()
        provider = create_provider(config=config)
        model = args.model or config.model
        print(f"[config] base_url={config.base_url or '（未配置）'} model={model} timeout={config.timeout_s}s")
        print(f"[config] api_key={mask_secret(config.api_key) or '（未配置，按无认证发送）'} source={config.source}")

    debug = prompt_debug_info(load_instructions(kb_path))
    print(f"[kb] {kb_path}")
    print(
        f"[prompt] 注入指令文件：{', '.join(debug['loaded']) or '（无）'}"
        f"；截断：{', '.join(debug['truncated']) or '无'}；省略：{', '.join(debug['omitted']) or '无'}"
    )
    print(f"[ask] {question}")
    print("[answer] ", end="", flush=True)

    def on_text(piece: str) -> None:
        if not args.no_stream:
            print(piece, end="", flush=True)

    result = ask(
        kb_path,
        question,
        provider=provider,
        model=model,
        session_id=args.session_id or None,
        max_iterations=args.max_iterations,
        top_k=args.top_k,
        on_text=on_text,
    )
    if args.no_stream:
        print(result.answer)
    else:
        print()

    print(f"[stop] reason={result.stop_reason} iterations={result.iterations}")
    if result.error:
        print(f"[error] {result.error}", file=sys.stderr)
    for index, call in enumerate(result.tool_calls, start=1):
        flag = "error" if call["is_error"] else "ok"
        print(f"[tool {index}] {call['name']} -> {flag}{(' (' + str(call['code']) + ')') if call['code'] else ''}")
    if result.anchors:
        print("[anchors]")
        for anchor in result.anchors:
            location = f"{anchor.get('file')}:{anchor.get('line')}" if anchor.get("line") else str(anchor.get("file"))
            print(f"  - {location}  {anchor.get('name') or anchor.get('kp_id') or ''}")
    else:
        print("[anchors] （无：本轮没有命中知识点）")
    usage = result.usage
    print(
        f"[usage] prompt={usage['prompt_tokens']} completion={usage['completion_tokens']}"
        f" total={usage['total_tokens']} estimated={'yes' if usage['estimated'] else 'no'}"
    )
    print(f"[session] id={result.session_id}")
    print(f"[session] file={result.session_path}")
    return 1 if result.stop_reason == "error" else 0


if __name__ == "__main__":
    if os.environ.get("MEMORIA_AGENT_DEBUG"):
        import logging

        logging.basicConfig(level=logging.DEBUG)
    raise SystemExit(main())
