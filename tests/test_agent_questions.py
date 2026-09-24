"""向用户提问（上游 `interaction/user-questions` seam + `interaction/tool-ask-user` 工具）的契约钉子。

本文件钉六件事：

1. **往返**：`questions.ask()` → 待答项进信箱（面板轮询能看到）→ `answer_question()` 回填 → 答案返回；
2. **四类失败全部 fail-closed**：没有面板（`NO_PROVIDER`，且**立刻**失败、不白等）、空批次
   （`EMPTY_QUESTIONS`）、本轮被取消（`ASK_ABORTED`）、等人超时（`NO_ANSWER`）；
3. **工具声明照搬上游**：`questions` 必填、`items` 必填 `id`/`question`、`options[].label`、
   `multi_select` 布尔、顶层 `additionalProperties: false`；
4. **工具只读** ⇒ 不经审批闸（`read_only=True`），且注册进 `KB_TOOL_NAMES`（2026-09-23 起它后面
   另接联网两把工具 `web_search` / `fetch_url`）；
5. **模型看到的就是答案 JSON**（上游 `render` 口径），失败时是 `Error: … (<CODE>)`；
6. **`tool/call` ↔ `tool/result` 配对不被破坏** —— 工具挂起等人期间，两条事件仍在、同 id、按序。

`NO_ANSWER` 是本地新增码（上游无超时，只等 signal）；其余三码与上游 `UserQuestionError.code` 逐字同名。
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from memoria.services.agent import approval_bridge, questions
from memoria.services.agent.llm.types import (
    FinishEvent,
    FinishReason,
    LlmRequest,
    TextDelta,
    ToolCall,
)
from memoria.services.agent.loop import AgentLoop
from memoria.services.agent.tools.kb import KB_TOOL_NAMES, build_kb_tools
from memoria.services.agent.tools.registry import INVALID_ARGUMENTS_CODE, ToolRegistry

#: 一批两个问题：一个单选（带候选），一个多选（**无候选** ⇒ 只能自己写）。
BATCH = [
    {
        "id": "mode",
        "question": "用哪种模式？",
        "header": "选择模式",
        "options": [
            {"label": "严格（推荐）", "description": "先问再写"},
            {"label": "宽松"},
        ],
    },
    {"id": "tags", "question": "还想加哪些标签？", "multi_select": True},
]

#: 人的作答（上游 `AskUserQuestionAnswerItem` 形态）。
ANSWERS = [
    {"id": "mode", "selected": ["严格（推荐）"]},
    {"id": "tags", "selected": [], "custom": "语法、阅读"},
]


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    """最小库根（问答面只按库根寻址，不读库内任何文件）。"""
    root = tmp_path / "kb"
    (root / ".memoria").mkdir(parents=True)
    return root


@pytest.fixture()
def attached(kb: Path) -> Iterator[Path]:
    """挂上问答信道（= 有面板在轮询），退出时摘除。"""
    approval_bridge.attach(str(kb))
    try:
        yield kb
    finally:
        approval_bridge.detach(str(kb))


def _wait_for(predicate: Any, *, timeout_s: float = 3.0) -> Any:
    """轮询等一个条件成立（只用于等后台线程把待答项登记进信箱）。"""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    return None


def _ask_in_thread(root: Path, *, timeout_s: float = 5.0) -> tuple[threading.Thread, list]:
    """在后台线程里 `ask()`（它会阻塞），返回线程与结果盒。"""
    box: list = []

    def _run() -> None:
        try:
            box.append(questions.ask(str(root), BATCH, timeout_s=timeout_s))
        except questions.QuestionError as exc:
            box.append(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread, box


def _tool(root: Path, name: str, arguments: dict) -> Any:
    registry = ToolRegistry(build_kb_tools(str(root)))
    call = ToolCall(id="c1", name=name, arguments=json.dumps(arguments, ensure_ascii=False))
    return registry.invoke(call)


# —— ① 往返 ——


def test_ask_round_trip_through_the_bridge(attached: Path) -> None:
    """提问登记进信箱 → 面板看到的就是**线上结构** → 回填后 `ask()` 返回该答案。"""
    thread, box = _ask_in_thread(attached)
    rows = _wait_for(lambda: approval_bridge.pending_questions_for(str(attached)))
    assert rows, "待答项没有登记进信箱（面板看不到 = 没人能作答）"

    row = rows[0]
    assert row["id"].startswith("q") and isinstance(row["created_at"], int) and row["created_at"] > 0
    assert row["questions"] == [
        {
            "id": "mode",
            "question": "用哪种模式？",
            "header": "选择模式",
            "options": [
                {"label": "严格（推荐）", "description": "先问再写"},
                {"label": "宽松"},
            ],
        },
        {"id": "tags", "question": "还想加哪些标签？", "multiSelect": True},
    ], "线上结构必须只含已知键（`multi_select` → `multiSelect`，与上游 execute 的映射一致）"

    assert approval_bridge.answer_question(str(attached), row["id"], ANSWERS) is True
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert box[0] == ANSWERS
    # 幂等：同一条已作答 ⇒ 再回填返回 False（不抛、不覆盖）
    assert approval_bridge.answer_question(str(attached), row["id"], ANSWERS) is False
    assert approval_bridge.pending_questions_for(str(attached)) == []


def test_unknown_question_id_is_answered_false(attached: Path) -> None:
    """未知/别人的 `qid` 一律 False（幂等，绝不误答别的库）。"""
    assert approval_bridge.answer_question(str(attached), "q-nope", ANSWERS) is False


# —— ② 四类失败 ——


def test_no_panel_fails_immediately_without_waiting(kb: Path) -> None:
    """**未挂载**（CLI 无面板）⇒ 立刻 `NO_PROVIDER`，而不是空挂 180 秒。"""
    started = time.monotonic()
    with pytest.raises(questions.QuestionError) as info:
        questions.ask(str(kb), BATCH)
    assert info.value.code == questions.NO_PROVIDER
    assert time.monotonic() - started < 1.0, "没有面板时不该等待"
    assert approval_bridge.pending_questions_for(str(kb)) == [], "未挂载时不该登记待答项"


def test_empty_batch_is_rejected_before_registering(attached: Path) -> None:
    """空批次 ⇒ `EMPTY_QUESTIONS`，且**不登记**待答项（上游 `ask()` 同序：先校验再找提供方）。"""
    with pytest.raises(questions.QuestionError) as info:
        questions.ask(str(attached), [])
    assert info.value.code == questions.EMPTY_QUESTIONS
    assert approval_bridge.pending_questions_for(str(attached)) == []


def test_abort_wakes_the_waiter(attached: Path) -> None:
    """本轮被取消（`abort()`）⇒ 挂起的提问立刻醒 ⇒ `ASK_ABORTED`。"""
    thread, box = _ask_in_thread(attached)
    assert _wait_for(lambda: approval_bridge.pending_questions_for(str(attached)))
    approval_bridge.abort(str(attached))
    thread.join(timeout=5)
    assert not thread.is_alive(), "abort 必须唤醒等待线程（否则工具线程挂到超时）"
    assert isinstance(box[0], questions.QuestionError) and box[0].code == questions.ASK_ABORTED


def test_detach_wakes_the_waiter_as_no_provider(attached: Path) -> None:
    """作业结束摘除挂载 ⇒ 未决提问按"没有应答者"收敛 ⇒ `NO_PROVIDER`。"""
    thread, box = _ask_in_thread(attached)
    assert _wait_for(lambda: approval_bridge.pending_questions_for(str(attached)))
    approval_bridge.detach(str(attached))
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert isinstance(box[0], questions.QuestionError) and box[0].code == questions.NO_PROVIDER


def test_timeout_is_fail_closed(attached: Path) -> None:
    """等人超时 ⇒ `NO_ANSWER`（**本地新增码**：上游无超时；绝不拿空答案冒充"问过了"）。"""
    started = time.monotonic()
    with pytest.raises(questions.QuestionError) as info:
        questions.ask(str(attached), BATCH, timeout_s=0.2)
    assert info.value.code == questions.NO_ANSWER
    assert 0.2 <= time.monotonic() - started < 2.0
    assert approval_bridge.pending_questions_for(str(attached)) == [], "超时后待答项要摘掉"


def test_default_timeout_is_the_bridge_constant(attached: Path) -> None:
    """不传 `timeout_s` 时用的就是 `QUESTION_TIMEOUT_S` 那个上界（180s：够读题作答，远小于面板 30 分钟兜底）。"""
    assert approval_bridge.QUESTION_TIMEOUT_S == 180.0
    assert questions.ask.__kwdefaults__["timeout_s"] is None, "默认让桥去取那个常量（不在 seam 里硬编一个数）"


# —— ③④ 工具声明与注册 ——


def test_tool_declaration_matches_upstream(kb: Path) -> None:
    """`ask_user_question` 的声明逐字段对齐上游 `defineTool`（仅文案本地化 + `minLength` 加固）。"""
    tools = {tool.name: tool for tool in build_kb_tools(str(kb))}
    tool = tools["ask_user_question"]
    assert tool.read_only is True, "提问不改知识库 ⇒ 不该走审批闸"

    schema = tool.parameters
    assert schema["required"] == ["questions"] and schema["additionalProperties"] is False
    questions_schema = schema["properties"]["questions"]
    assert questions_schema["type"] == "array"
    items = questions_schema["items"]
    assert items["type"] == "object" and items["additionalProperties"] is True
    assert items["required"] == ["id", "question"], "上游把必填写在属性里，本地翻写成对象级 required"
    props = items["properties"]
    assert set(props) == {"id", "question", "header", "options", "multi_select"}
    assert props["id"]["type"] == "string" and props["question"]["type"] == "string"
    assert props["id"]["minLength"] == 1 and props["question"]["minLength"] == 1
    assert props["options"]["items"]["required"] == ["label"]
    assert props["options"]["items"]["properties"]["label"]["type"] == "string"
    assert props["multi_select"]["type"] == "boolean"
    assert "推荐" in props["options"]["description"], "上游要求推荐项排第一并标注（本地化文案要保留该指令）"


def test_tool_is_registered_last_and_only_once(kb: Path) -> None:
    """注册只一次（`KB_TOOL_NAMES` 与实建工具集**逐项一致**；次序漂移会被这里与旧测试双杀）。

    2026-09-23 起 `ask_user_question` **不再是末位**（其后另有联网两把工具，见 §6.28）；
    2026-09-24 起其后再接脚本工作区四把（§3.4）⇒ 钉子改为「在联网两把之前、且只出现一次」。
    """
    built = tuple(tool.name for tool in build_kb_tools(str(kb)))
    assert built == KB_TOOL_NAMES
    assert KB_TOOL_NAMES[-7] == "ask_user_question"
    assert KB_TOOL_NAMES[-6:-4] == ("web_search", "fetch_url")
    assert KB_TOOL_NAMES[-4:] == ("scratch_list", "scratch_read", "scratch_write", "scratch_delete")
    assert KB_TOOL_NAMES.count("ask_user_question") == 1


# —— ⑤ 模型看到的文本 ——


def test_tool_result_is_the_answer_json(attached: Path) -> None:
    """成功 = 上游 `render` 的同一口径：`{"answers": [...]}` 的 JSON 文本（含 custom）。"""
    box: list = []
    thread = threading.Thread(
        target=lambda: box.append(_tool(attached, "ask_user_question", {"questions": BATCH})), daemon=True
    )
    thread.start()
    rows = _wait_for(lambda: approval_bridge.pending_questions_for(str(attached)))
    assert rows
    approval_bridge.answer_question(str(attached), rows[0]["id"], ANSWERS)
    thread.join(timeout=5)
    assert not thread.is_alive()

    result = box[0]
    assert result.is_error is False and result.output.code is None
    assert json.loads(result.content) == {"answers": ANSWERS}


def test_tool_error_carries_the_stable_code(kb: Path) -> None:
    """失败 = `Error: ask_user_question: … (<CODE>)`；没有面板时是 `NO_PROVIDER`（fail-closed）。"""
    result = _tool(kb, "ask_user_question", {"questions": BATCH})
    assert result.is_error is True and result.output.code == questions.NO_PROVIDER
    assert result.content.startswith("Error: ask_user_question: ") and result.content.endswith("(NO_PROVIDER)")


def test_tool_rejects_a_malformed_batch_via_the_schema(kb: Path) -> None:
    """`id` / `question` 非空由 schema 兜住（本地加固的 `minLength: 1`）⇒ `INVALID_ARGUMENTS`，不落进 seam。"""
    empty_id = _tool(kb, "ask_user_question", {"questions": [{"id": "", "question": "在吗"}]})
    assert empty_id.is_error and empty_id.output.code == INVALID_ARGUMENTS_CODE
    missing = _tool(kb, "ask_user_question", {"questions": [{"id": "a"}]})
    assert missing.is_error and missing.output.code == INVALID_ARGUMENTS_CODE


# —— ⑥ 与循环的配对 ——


class _ScriptedProvider:
    """按脚本产出流式事件的假 provider（与 `tests/test_agent_loop.py` 的替身同款、最小化）。"""

    name = "scripted"

    def __init__(self, script: Sequence[Sequence[Any]]) -> None:
        self.script: list[list[Any]] = [list(step) for step in script]

    def stream(self, request: LlmRequest) -> Iterator[Any]:
        step = self.script.pop(0) if self.script else [TextDelta("（脚本耗尽）"), FinishEvent(reason=FinishReason.STOP)]
        yield from step


def test_tool_call_and_result_stay_paired_while_the_loop_waits(attached: Path) -> None:
    """工具挂起等人期间：`tool/call` 已落（先于分发）、`tool/result` 事后补齐、**同 id 按序**。"""
    registry = ToolRegistry([tool for tool in build_kb_tools(str(attached)) if tool.name == "ask_user_question"])
    provider = _ScriptedProvider(
        [
            [
                FinishEvent(
                    reason=FinishReason.TOOL_CALLS,
                    tool_calls=(
                        ToolCall(
                            id="c-q1",
                            name="ask_user_question",
                            arguments=json.dumps({"questions": BATCH}, ensure_ascii=False),
                        ),
                    ),
                )
            ],
            [TextDelta("好，照你说的办。"), FinishEvent(reason=FinishReason.STOP)],
        ]
    )
    events: list[tuple[str, dict]] = []
    loop = AgentLoop(
        provider=provider,
        tools=registry,
        system="（测试）",
        max_iterations=3,
        on_event=lambda event_type, data: events.append((event_type, dict(data))),
    )
    box: list = []
    thread = threading.Thread(target=lambda: box.append(loop.run("问我一件事")), daemon=True)
    thread.start()

    rows = _wait_for(lambda: approval_bridge.pending_questions_for(str(attached)), timeout_s=5.0)
    assert rows, "循环没有把提问发给问答面"
    calls = [data for kind, data in events if kind == "tool/call"]
    assert [data["id"] for data in calls] == ["c-q1"], "`tool/call` 必须**先于分发**落（挂起前就该在）"
    assert [data for kind, data in events if kind == "tool/result"] == [], "还没作答，不该有结果"

    assert approval_bridge.answer_question(str(attached), rows[0]["id"], ANSWERS) is True
    thread.join(timeout=10)
    assert not thread.is_alive()

    kinds = [kind for kind, _ in events]
    assert kinds.count("tool/call") == 1 and kinds.count("tool/result") == 1, "一次调用恰一对"
    assert kinds.index("tool/call") < kinds.index("tool/result")
    result = next(data for kind, data in events if kind == "tool/result")
    assert result["id"] == "c-q1" and result["name"] == "ask_user_question" and result["is_error"] is False
    assert json.loads(result["content"]) == {"answers": ANSWERS}
