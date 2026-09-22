# 设计来源：`docs/design/dsh-agent-port.md` §6.23（上游 `interaction/commands` 的最小面）
# 上游语义：`dsh-src/packages/interaction/commands/src/index.ts`

"""斜杠命令（slash command）：**人类直呼、不进模型**的本地通路。

钉住五件事：

1. **行解析**逐字对齐上游：名字语法、`rawInput` **含**分隔空白、`/usr/bin` 与 `5/8` **不**是命令。
2. **未知名 ⇒ 不落任何事件、回落到普通提问**（上游 `execute()` 回 `undefined` 的口径）——
   这条是"斜杠不会吃掉正常文本"的保证。
3. **成对生命周期**：`command/run` → `command/done` 按 `commandId` 配对；handler 抛异常也**先**落
   `kind:"error"` 的 done 再抛；`recordInput:false` 不带 `args`。
4. **两条内建命令**：`/permission <档位>` 真切换（落 `permission/preset` 事件）、`/compact` 走**同一个**
   `ask._compact_if_needed(force=True)`（无可压区间时如实回报，且**零模型调用**）。
5. **`ask()` 分流**：命令那一轮**不落 `user/message`、不进 loop**（`provider.requests` 为空），
   回 `stop_reason="command"`；未注册的斜杠行照旧进模型。
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from os import PathLike
from pathlib import Path
from typing import Any

import pytest

from memoria.presentation.api.ui import UIAPI
from memoria.services.agent.ask import ask
from memoria.services.agent.commands import (
    EVENT_DONE,
    EVENT_RUN,
    CommandContext,
    CommandDefinition,
    CommandRegistry,
    CommandResult,
    default_registry,
    err,
    execute,
    handle_command_line,
    ok,
    parse_command,
)
from memoria.services.agent.llm import (
    FinishEvent,
    FinishReason,
    LlmRequest,
    TextDelta,
    Usage,
    UsageEvent,
)
from memoria.services.agent.session.store import SessionStore

SESSION = "session-20260922T220000Z-cmd1"
BODY = "# A 文档\n\n第一段。\n"


# —— 测试替身（与 tests/test_agent_loop.py 同形）——


class FakeProvider:
    """按脚本产出流式事件的假 provider；记录收到的请求以便断言"有没有真调模型"。"""

    name = "fake"

    def __init__(self, script: Sequence[Sequence[Any]] = ()) -> None:
        self.script: list[list[Any]] = [list(step) for step in script]
        self.requests: list[LlmRequest] = []

    def stream(self, request: LlmRequest) -> Iterator[Any]:
        self.requests.append(request)
        step = self.script.pop(0) if self.script else [
            TextDelta("（脚本耗尽）"),
            FinishEvent(reason=FinishReason.STOP),
        ]
        yield from step


def text_step(text: str) -> list[Any]:
    return [
        TextDelta(text),
        UsageEvent(Usage(prompt_tokens=10, completion_tokens=5)),
        FinishEvent(reason=FinishReason.STOP),
    ]


# —— 辅助 ——


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "a.md").write_text(BODY, encoding="utf-8", newline="")
    return tmp_path


def session_of(kb: PathLike[str], session_id: str = SESSION) -> SessionStore:
    return SessionStore(str(kb), session_id)


def event_types(session: SessionStore) -> list[str]:
    return [str(row.get("type") or "") for row in session.events()]


def event_payloads(session: SessionStore, event_type: str) -> list[dict[str, Any]]:
    return [dict(row.get("data") or {}) for row in session.events() if row.get("type") == event_type]


# —— ① 行解析（逐字对齐上游）——


def test_parse_command_matches_upstream_shape() -> None:
    plain = parse_command("/compact")
    assert plain is not None and plain.name == "compact" and plain.raw_input == ""

    with_arg = parse_command("/permission manual-approval")
    assert with_arg is not None and with_arg.name == "permission"
    # 上游：`rawInput = line.slice(match[0].length)`，而前瞻不消费分隔符 ⇒ **含**那个空格
    assert with_arg.raw_input == " manual-approval"

    hyphen = parse_command("/some-cmd_x 参数")
    assert hyphen is not None and hyphen.name == "some-cmd_x" and hyphen.raw_input == " 参数"


@pytest.mark.parametrize(
    "line",
    [
        "5/8 是一半",
        "/usr/bin/env python",
        "/Compact",  # 大写不合法（上游要求小写）
        "/-bad",
        "/9lives",
        "/compactx",  # 合法名字但带后缀 ⇒ 是**另一个**名字，仍会被解析（见下条断言）
        "//double",
        "/",
        "没有斜杠",
        "/空格 前导",  # 全角空格不是分隔符
    ],
)
def test_parse_command_rejects_non_commands(line: str) -> None:
    if line == "/compactx":
        parsed = parse_command(line)
        assert parsed is not None and parsed.name == "compactx"  # 解析成功，但**注册表里没有**它
        return
    assert parse_command(line) is None


def test_parse_command_is_anchored_at_line_start() -> None:
    assert parse_command("  /compact") is None  # 前导空白 ⇒ 不是命令行（上游同为行首锚定）


# —— ② 注册表 ——


def test_registry_rejects_bad_definitions() -> None:
    registry = CommandRegistry()
    with pytest.raises(ValueError):
        registry.register(CommandDefinition(name="Bad", description="x", handler=lambda inv: ok()))
    with pytest.raises(ValueError):
        registry.register(CommandDefinition(name="good", description="   ", handler=lambda inv: ok()))
    registry.register(CommandDefinition(name="good", description="x", handler=lambda inv: ok()))
    with pytest.raises(ValueError):
        registry.register(CommandDefinition(name="good", description="y", handler=lambda inv: ok()))


def test_descriptors_are_name_sorted_and_carry_the_input_hint() -> None:
    rows = default_registry().descriptors()
    assert [row["name"] for row in rows] == ["compact", "permission"]
    assert rows[0]["description"] and "input" not in rows[0]
    assert rows[1]["input"] == {"hint": "<档位>"}
    assert "handler" not in json.dumps(rows)  # 描述符里**不含** handler（上游 `CommandDescriptor` 同口径）


def test_unknown_name_logs_nothing_and_returns_none(kb: Path) -> None:
    """上游口径：未命中（语法/名字）**不落任何事件** —— 它从未进入 handler。"""
    session = session_of(kb)
    context = CommandContext(kb_path=str(kb), session=session)
    assert execute(default_registry(), context, "/nope") is None
    assert execute(default_registry(), context, "不是命令") is None
    assert event_types(session) == []


# —— ③ 生命周期事件 ——


def test_execute_pairs_run_and_done_events(kb: Path) -> None:
    session = session_of(kb)
    context = CommandContext(kb_path=str(kb), session=session)
    execution = execute(default_registry(), context, "/permission all-access")
    assert execution is not None and execution.result.kind == "success"
    kinds = event_types(session)
    # `run` 在最前、`done` 在最后；**领域事件落在这一对之间** —— 正是上游"领域事件自己记载荷"的形态
    assert kinds[0] == EVENT_RUN and kinds[-1] == EVENT_DONE
    assert "permission/preset" in kinds[1:-1]
    run, done = event_payloads(session, EVENT_RUN)[0], event_payloads(session, EVENT_DONE)[0]
    assert run["commandId"] == done["commandId"] == execution.command_id
    assert run["name"] == "permission" and run["args"] == " all-access" and run["source"] == {"kind": "user"}
    assert done["kind"] == "success" and "完全访问" in done["text"]
    assert all(payload["kind"] == "success" for payload in event_payloads(session, EVENT_DONE))


def test_record_input_false_omits_args(kb: Path) -> None:
    registry = CommandRegistry()
    registry.register(
        CommandDefinition(
            name="quiet", description="不记载荷", record_input=False, handler=lambda inv: ok("干了")
        )
    )
    session = session_of(kb)
    execute(registry, CommandContext(kb_path=str(kb), session=session), "/quiet 敏感参数")
    assert "args" not in event_payloads(session, EVENT_RUN)[0]


def test_handler_failure_logs_done_then_raises(kb: Path) -> None:
    def boom(invocation: Any) -> CommandResult:
        raise RuntimeError("内部炸了")

    registry = CommandRegistry()
    registry.register(CommandDefinition(name="boom", description="会炸", handler=boom))
    session = session_of(kb)
    with pytest.raises(RuntimeError):
        execute(registry, CommandContext(kb_path=str(kb), session=session), "/boom")
    # 先配对落 done（kind=error），**再**把异常交回调用方（上游同序）
    assert event_types(session) == [EVENT_RUN, EVENT_DONE]
    done = event_payloads(session, EVENT_DONE)[0]
    assert done["kind"] == "error" and "内部炸了" in done["text"]


def test_non_command_result_becomes_an_error_result(kb: Path) -> None:
    registry = CommandRegistry()
    registry.register(CommandDefinition(name="bad", description="返回错东西", handler=lambda inv: "不是结果"))
    session = session_of(kb)
    execution = execute(registry, CommandContext(kb_path=str(kb), session=session), "/bad")
    assert execution is not None and execution.result.kind == "error"
    assert "没有返回 CommandResult" in execution.result.text


def test_err_requires_a_non_empty_text() -> None:
    with pytest.raises(ValueError):
        err("   ")


# —— ④ 两条内建命令 ——


def test_permission_command_switches_the_session_preset(kb: Path) -> None:
    session = session_of(kb)
    execution = execute(
        default_registry(), CommandContext(kb_path=str(kb), session=session), "/permission manual-approval"
    )
    assert execution is not None and execution.result.kind == "success"
    assert "手动审批" in execution.result.text
    assert "permission/preset" in event_types(session)  # 复用 `permission_presets.set_preset()`
    assert "approval/policy" in event_types(session)


@pytest.mark.parametrize("line", ["/permission", "/permission   ", "/permission 乱填"])
def test_permission_command_reports_the_choices(kb: Path, line: str) -> None:
    session = session_of(kb)
    execution = execute(default_registry(), CommandContext(kb_path=str(kb), session=session), line)
    assert execution is not None and execution.result.kind == "error"
    assert "manual-approval" in execution.result.text  # 报错必须**可行动**：列出可选档位
    assert "permission/preset" not in event_types(session)  # 没切就不该落档位事件


def test_compact_command_without_history_says_so(kb: Path) -> None:
    session = session_of(kb)
    execution = execute(default_registry(), CommandContext(kb_path=str(kb), session=session), "/compact")
    assert execution is not None and execution.result.kind == "error"
    assert "还没有历史" in execution.result.text


def test_compact_command_with_nothing_to_compress_is_zero_model_calls(kb: Path) -> None:
    """`/compact` 走的是**同一个** `ask._compact_if_needed(force=True)`；选不出区间时如实回报。"""
    session = session_of(kb)
    session.append("user/message", {"text": "一句话"})
    provider = FakeProvider()
    execution = execute(
        default_registry(),
        CommandContext(
            kb_path=str(kb),
            session=session,
            history=[],
            provider=provider,
            system="sys",
            tools=(),
            model="fake-model",
        ),
        "/compact",
    )
    assert execution is not None
    assert execution.result.kind == "success" and "没有可压的区间" in execution.result.text
    assert provider.requests == [], "无可压区间 ⇒ 一次模型调用都不该发生"


def test_compact_command_actually_compacts_a_long_session(kb: Path) -> None:
    """`force=True` 真的压下去：摘要调用**恰好一次**、落一条 `compaction`，且复用同一份摘要指令。"""
    session = session_of(kb)
    for index in range(7):  # 7 轮 × 2 条 × ~4000 字符 ≈ 56k 字符 ⇒ 远超压缩阈值
        body = f"FILLER{index}-" + "x" * 4000
        session.append("user/message", {"text": body})
        session.append("assistant/message", {"content": body})
    session.flush()

    provider = FakeProvider([text_step("## 待办\n- (none)\n")])
    history = [object()]  # 非 None 即可（`force=True` 不读它的字符数，见 `_compact_if_needed`）
    execution = execute(
        default_registry(),
        CommandContext(
            kb_path=str(kb),
            session=session,
            history=history,
            provider=provider,
            system="sys",
            tools=(),
            model="probe-model",
        ),
        "/compact",
    )
    assert execution is not None and execution.result.kind == "success", execution
    assert "已压缩" in execution.result.text
    assert len(provider.requests) == 1, "只有那一次摘要调用"

    compactions = event_payloads(session, "compaction")
    assert len(compactions) == 1 and compactions[0]["shadowed"]
    assert compactions[0]["model"] == "probe-model" and compactions[0]["shadowed_chars"] > 0


# —— ⑤ `ask()` 分流 ——


def test_handle_command_line_returns_an_ask_result_for_commands(kb: Path) -> None:
    session = session_of(kb)
    result = handle_command_line(str(kb), session, "/permission all-access")
    assert result is not None
    assert result.stop_reason == "command"
    assert result.iterations == 0 and dict(result.usage) == {}
    assert "完全访问" in result.answer and result.error is None
    assert result.session_id == session.session_id


def test_handle_command_line_returns_an_error_answer_on_failure(kb: Path) -> None:
    session = session_of(kb)
    result = handle_command_line(str(kb), session, "/permission 乱填")
    assert result is not None and result.stop_reason == "command" and result.error
    assert "manual-approval" in result.answer


def test_handle_command_line_passes_through_non_commands(kb: Path) -> None:
    session = session_of(kb)
    assert handle_command_line(str(kb), session, "普通问题") is None
    assert handle_command_line(str(kb), session, "/usr/bin/env") is None
    assert handle_command_line(str(kb), session, "/nope") is None  # 合法语法但**没注册** ⇒ 放行
    assert event_types(session) == []


def test_ask_routes_a_command_line_without_touching_the_model(kb: Path) -> None:
    provider = FakeProvider([text_step("正常回答")])
    first = ask(str(kb), "先问一句", provider=provider, model="fake-model", session_id=SESSION)
    assert first.stop_reason != "command" and provider.requests
    before = len(provider.requests)  # 含**首轮一次**的模型标题调用（`max_tokens=96`）⇒ 只比"增量"

    routed = ask(
        str(kb), "/permission manual-approval", provider=provider, model="fake-model", session_id=SESSION
    )
    assert routed.stop_reason == "command"
    assert "手动审批" in routed.answer
    assert len(provider.requests) == before, "命令轮**不进 loop** ⇒ 一次模型调用都不该多"
    events = event_types(session_of(kb))
    assert "command/run" in events and "command/done" in events
    assert "permission/preset" in events
    # 命令轮**不产生模型消息**（上游口径）：`user/message` 只该有第一条那一次
    assert events.count("user/message") == 1


def test_ask_still_sends_unknown_slash_lines_to_the_model(kb: Path) -> None:
    provider = FakeProvider([text_step("回答一"), text_step("回答二")])
    ask(str(kb), "先问一句", provider=provider, model="fake-model", session_id=SESSION)
    before = len(provider.requests)
    result = ask(str(kb), "/usr/bin/env 是什么", provider=provider, model="fake-model", session_id=SESSION)
    assert result.stop_reason != "command" and len(provider.requests) == before + 1
    assert event_types(session_of(kb)).count("user/message") == 2
    assert "command/run" not in event_types(session_of(kb))


# —— ⑥ 发现面（RPC）——


def test_command_list_rpc_is_read_only(kb: Path) -> None:
    api = UIAPI(kb_path=str(kb))
    before = sorted(p.name for p in kb.rglob("*"))
    payload = api.agent_command_list()
    assert payload["status"] == "ok"
    assert [row["name"] for row in payload["commands"]] == ["compact", "permission"]
    assert sorted(p.name for p in kb.rglob("*")) == before, "列命令是纯只读：不建会话、不落事件、不碰库"
