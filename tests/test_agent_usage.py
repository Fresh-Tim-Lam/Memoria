# 配套单测：被测调用面语义移植自 deepseek-harness packages/llm/*（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""Agent 用量捕获与聚合的离线单测（不联网、不写知识库正文）。

覆盖（对应任务验收项）：
① DeepSeek 形态（顶层 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`）；
② OpenAI 形态（`prompt_tokens_details.cached_tokens`，未命中量可推）；
③ 两者都缺 ⇒ `cache_read_tokens is None` 且**不**把 `estimated` 误置真；
④ `Usage.plus()` / `UsageMeter` 合并新字段（None 与整数混合）；
⑤ 聚合：命中率计算、`cache_unknown_turns` 计数、命中率未知时为 `None` 而非 0；
⑥ 大文件扫描上限（超限 `capped=True`，只统计上限内的轮次）。
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from memoria.services.agent.llm import (
    AgentConfig,
    FinishEvent,
    FinishReason,
    LlmRequest,
    Message,
    Role,
    TextDelta,
    Usage,
    UsageEvent,
    UsageMeter,
)
from memoria.services.agent.llm.providers.openai_compatible import (
    OpenAICompatibleProvider,
    _usage_from_wire,
)
from memoria.services.agent.loop import AgentLoop
from memoria.services.agent.session.store import SessionStore, read_session
from memoria.services.agent.tools import ToolRegistry
from memoria.services.agent.usage_report import (
    SCAN_MAX_BYTES,
    aggregate_usage,
    turn_from_event,
    usage_stats,
)

MODEL = "test-model"


# —— 本地 stub 端点（照 tests/test_agent_llm.py 的最小形态）——


class _StubHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler 约定
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        for payload in self.server.payloads:  # type: ignore[attr-defined]
            self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
            self.wfile.flush()


@contextmanager
def stub_server(payloads: list[str]) -> Iterator[ThreadingHTTPServer]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    server.payloads = payloads  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _stream_usage(payloads: list[str]) -> Usage:
    with stub_server(payloads) as server:
        host, port = server.server_address[:2]
        provider = OpenAICompatibleProvider(AgentConfig(base_url=f"http://{host}:{port}/v1", model=MODEL))
        request = LlmRequest(model=MODEL, messages=(Message(role=Role.USER, content="你好"),), timeout_s=5.0)
        events = list(provider.stream(request))
    return next(event.usage for event in events if isinstance(event, UsageEvent))


def _delta(content: str) -> str:
    return json.dumps({"choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}]})


def _finish(reason: str = "stop") -> str:
    return json.dumps({"choices": [{"index": 0, "delta": {}, "finish_reason": reason}]})


def _usage_line(**usage: Any) -> str:
    return json.dumps({"choices": [], "usage": usage})


# —— ① / ② / ③ 端点形态 → Usage ——


def test_deepseek_cache_fields_are_parsed() -> None:
    """① DeepSeek：顶层 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` 直读。"""
    usage = _usage_from_wire(
        {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
            "prompt_cache_hit_tokens": 60,
            "prompt_cache_miss_tokens": 40,
        }
    )
    assert usage is not None
    assert usage.cache_read_tokens == 60
    assert usage.cache_miss_tokens == 40
    assert usage.estimated is False


def test_openai_cached_tokens_are_parsed_and_miss_is_derived() -> None:
    """② OpenAI 形态：`prompt_tokens_details.cached_tokens` + 可推的未命中量。"""
    usage = _usage_from_wire(
        {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "prompt_tokens_details": {"cached_tokens": 30},
        }
    )
    assert usage is not None
    assert usage.cache_read_tokens == 30
    assert usage.cache_miss_tokens == 70  # 100 - 30


def test_deepseek_fields_win_over_openai_details() -> None:
    """优先级：DeepSeek 顶层字段优先于 OpenAI 明细（两者同时出现时以顶层为准）。"""
    usage = _usage_from_wire(
        {
            "prompt_tokens": 100,
            "completion_tokens": 1,
            "prompt_cache_hit_tokens": 60,
            "prompt_cache_miss_tokens": 40,
            "prompt_tokens_details": {"cached_tokens": 10},
        }
    )
    assert usage is not None
    assert (usage.cache_read_tokens, usage.cache_miss_tokens) == (60, 40)


def test_missing_cache_fields_stay_none_and_are_not_estimated() -> None:
    """③ 端点**给了** usage 但缺 cache 字段 ⇒ None，且**不**因此置 `estimated`。"""
    usage = _usage_from_wire({"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12})
    assert usage is not None
    assert usage.cache_read_tokens is None
    assert usage.cache_miss_tokens is None
    assert usage.estimated is False

    # 反向：端点**完全没给** usage ⇒ 估算（estimated=True），cache 字段同样为 None
    estimated = _stream_usage([_delta("答"), _finish(), "[DONE]"])
    assert estimated.estimated is True
    assert estimated.cache_read_tokens is None and estimated.cache_miss_tokens is None


def test_stream_surfaces_deepseek_usage_on_the_wire() -> None:
    """SSE 全链路：usage 分片里的 DeepSeek 字段确实落到 `UsageEvent.usage`。"""
    usage = _stream_usage(
        [
            _delta("答"),
            _finish(),
            _usage_line(
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120,
                prompt_cache_hit_tokens=60,
                prompt_cache_miss_tokens=40,
            ),
            "[DONE]",
        ]
    )
    assert (usage.cache_read_tokens, usage.cache_miss_tokens) == (60, 40)
    assert usage.estimated is False


# —— ④ plus / meter 合并 ——


def test_usage_plus_and_meter_merge_cache_miss() -> None:
    left = Usage(prompt_tokens=1, completion_tokens=1, cache_read_tokens=5, cache_miss_tokens=None)
    right = Usage(prompt_tokens=2, completion_tokens=2, cache_read_tokens=None, cache_miss_tokens=3)
    merged = left.plus(right)
    assert merged.cache_read_tokens == 5
    assert merged.cache_miss_tokens == 3
    # 两侧都缺 ⇒ 仍为 None（不是 0）
    assert left.plus(Usage()).cache_miss_tokens is None
    assert left.plus(Usage()).cache_read_tokens == 5

    meter = UsageMeter()
    meter.add(left)
    meter.add(right)
    snapshot = meter.to_dict()
    assert snapshot["cache_read_tokens"] == 5
    assert snapshot["cache_miss_tokens"] == 3
    meter.reset()
    assert meter.to_dict()["cache_miss_tokens"] == 0


def test_loop_end_payload_carries_cache_fields(tmp_path: Path) -> None:
    """`loop/end.usage` 载荷带上新字段（会话落盘即为事实源）。"""

    class _Scripted:
        name = "scripted"

        def stream(self, request: LlmRequest) -> Iterator[Any]:
            yield TextDelta("答")
            yield UsageEvent(
                Usage(
                    prompt_tokens=100,
                    completion_tokens=20,
                    total_tokens=120,
                    cache_read_tokens=60,
                    cache_miss_tokens=40,
                )
            )
            yield FinishEvent(reason=FinishReason.STOP)

    kb = tmp_path / "kb"
    kb.mkdir()
    store = SessionStore(str(kb), "session-usage")
    loop = AgentLoop(provider=_Scripted(), tools=ToolRegistry(), model=MODEL, on_event=store.append)
    result = loop.run("问")
    assert result.usage_dict()["cache_miss_tokens"] == 40

    rows = read_session(str(kb), "session-usage")
    end = next(row for row in rows if row["type"] == "loop/end")
    assert end["data"]["usage"]["cache_read_tokens"] == 60
    assert end["data"]["usage"]["cache_miss_tokens"] == 40


# —— ⑤ 聚合口径 ——


def _loop_end(seq: int, *, prompt: int, completion: int, cache_hit: Any = None,
              cache_miss: Any = None, estimated: bool = False) -> str:
    usage: dict[str, Any] = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "estimated": estimated,
    }
    if cache_hit is not None:
        usage["cache_read_tokens"] = cache_hit
    if cache_miss is not None:
        usage["cache_miss_tokens"] = cache_miss
    return json.dumps(
        {"v": 1, "seq": seq, "time": 0, "type": "loop/end", "data": {"stop_reason": "final-answer", "usage": usage}}
    )


def _write_session(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_aggregate_hit_rate_and_cache_unknown_turns(tmp_path: Path) -> None:
    path = tmp_path / "session-a.jsonl"
    _write_session(
        path,
        [
            json.dumps({"v": 1, "type": "session/header", "data": {"id": "session-a"}}),
            _loop_end(1, prompt=100, completion=10, cache_hit=60, cache_miss=40),
            _loop_end(2, prompt=100, completion=10),  # 老式轮次：无 cache 字段
        ],
    )
    report = aggregate_usage([str(path)])
    summary = report["summary"]
    assert summary["turns"] == 2
    assert summary["cache_hit"] == 60
    assert summary["cache_miss"] == 40
    assert summary["hit_rate"] == 0.6  # 60 / 100（只算 cache 已知的那轮）
    assert summary["cache_unknown_turns"] == 1

    rows = report["turns"]
    assert rows[0]["hit_rate"] == 0.6
    assert rows[1]["cache_hit"] is None and rows[1]["hit_rate"] is None  # 未知 ≠ 0


def test_hit_rate_is_none_when_cache_is_unknown(tmp_path: Path) -> None:
    path = tmp_path / "session-old.jsonl"
    _write_session(path, [_loop_end(1, prompt=100, completion=10), _loop_end(2, prompt=50, completion=5)])
    summary = aggregate_usage([str(path)])["summary"]
    assert summary["cache_hit"] is None and summary["cache_miss"] is None
    assert summary["hit_rate"] is None  # 绝不静默算成 0
    assert summary["cache_unknown_turns"] == 2


def test_empty_cache_hit_zero_is_still_known(tmp_path: Path) -> None:
    """显式上报 `cache_read_tokens = 0` 是**已知**（命中率 0%），不是"未知"。"""
    path = tmp_path / "session-zero.jsonl"
    _write_session(path, [_loop_end(1, prompt=100, completion=10, cache_hit=0, cache_miss=100)])
    report = aggregate_usage([str(path)])
    assert report["turns"][0]["hit_rate"] == 0.0
    assert report["summary"]["cache_unknown_turns"] == 0
    assert report["summary"]["hit_rate"] == 0.0


def test_turn_from_event_derives_miss_for_openai_style(tmp_path: Path) -> None:
    record = json.loads(_loop_end(1, prompt=100, completion=10, cache_hit=30))
    row = turn_from_event(record, "s")
    assert row is not None
    assert row["cache_miss"] == 70  # 只给命中量时按 prompt - hit 补
    assert turn_from_event({"type": "user/message"}, "s") is None


def test_usage_stats_reads_a_real_session_store(tmp_path: Path) -> None:
    kb = tmp_path / "kb"
    kb.mkdir()
    store = SessionStore(str(kb), "session-live")
    store.append("loop/end", {"stop_reason": "final-answer", "usage": {
        "prompt_tokens": 200, "completion_tokens": 40, "total_tokens": 240,
        "estimated": False, "cache_read_tokens": 120, "cache_miss_tokens": 80,
    }})
    stats = usage_stats(str(kb), "session-live")
    assert stats["summary"]["turns"] == 1
    assert stats["summary"]["hit_rate"] == 0.6
    assert stats["summary"]["cache_unknown_turns"] == 0
    # 全库口径（不传 session_id）等价
    assert usage_stats(str(kb))["summary"] == stats["summary"]


# —— ⑥ 大文件扫描上限 ——


def test_scan_is_capped_for_oversized_session(tmp_path: Path) -> None:
    """超限会话按字节上限截断：只统计上限内的轮次，且 `capped=True`（不整体读入）。"""
    path = tmp_path / "session-big.jsonl"
    filler = json.dumps({"v": 1, "seq": 1, "type": "tool/result", "data": {"content": "x" * 4000}})
    lines = [json.dumps({"v": 1, "type": "session/header", "data": {"id": "session-big"}})]
    lines.append(_loop_end(0, prompt=100, completion=10, cache_hit=60, cache_miss=40))  # 上限内
    lines.extend(filler for _ in range(50))
    lines.append(_loop_end(999, prompt=1, completion=1, cache_hit=1, cache_miss=0))  # 上限外
    _write_session(path, lines)

    report = aggregate_usage([str(path)], max_bytes=4096)
    assert report["sessions"][0]["capped"] is True
    assert [row["seq"] for row in report["turns"]] == [0]

    # 默认上限是 2 MiB；构造一份超过它的文件，同样只统计上限内轮次
    big = tmp_path / "session-huge.jsonl"
    _write_session(
        big,
        [
            json.dumps({"v": 1, "type": "session/header", "data": {"id": "session-huge"}}),
            _loop_end(0, prompt=10, completion=1, cache_hit=5, cache_miss=5),
            json.dumps({"v": 1, "seq": 1, "type": "tool/result", "data": {"content": "y" * (SCAN_MAX_BYTES + 1024)}}),
            _loop_end(500, prompt=1, completion=1),
        ],
    )
    assert big.stat().st_size > SCAN_MAX_BYTES
    capped = aggregate_usage([str(big)])
    assert capped["sessions"][0]["capped"] is True
    assert [row["seq"] for row in capped["turns"]] == [0]
