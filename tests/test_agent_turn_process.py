# 配套单测（2026-09-22「一次回合的过程内容」）：
# 过程行形状（services/agent/turn_process.py）、思考随步骤落盘（loop.py）、
# 回放渲染视图带 process（session/history.py::conversation_messages）、
# 配置键 transcript_mode（services/agent/llm/config.py）。
# 上游语义：deepseek-harness 的 Turn Process Folding（MIT / BSD-3-Clause）；
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720

"""过程内容的离线单测：不联网、不写知识库正文。

覆盖（对应任务验收项）：
① `arg_summary` 按工具名挑键 / 回落第一个非空标量 / 坏 JSON 不抛 / 截断 120；
② `row_detail` 空白折叠 + 截断 240 + 空 ⇒ 空串；③ `tool_row` 两行同 id、state 随 `is_error`；
④ `step_row` 工具条数 + reasoning 空则**无该键**；⑤ `process_items` 按序出行并**跳过最终答案**；
⑥ 落盘：一轮后会话 JSONL 的 `assistant/message` 有思考时带 `reasoning`、无思考则不带，且
`build_history()` **不含** reasoning（不污染模型请求）；⑦ 回放 `conversation_messages()` 的
assistant 记录在有过程内容时带 `process`、无过程内容时**不带**该键；⑧ 配置 `transcript_mode`。
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from memoria.services.agent.ask import ask
from memoria.services.agent.llm import (
    FinishEvent,
    FinishReason,
    LlmRequest,
    ReasoningDelta,
    TextDelta,
)
from memoria.services.agent.llm.config import ConfigError
from memoria.services.agent.session.history import build_history, conversation_messages
from memoria.services.agent.session.store import SessionStore, read_session
from memoria.services.agent.turn_process import (
    arg_summary,
    process_items,
    row_detail,
    step_row,
    tool_row,
)

# —— 测试替身 ——


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    """最小知识库（空库即可：过程行 / 思考落盘与知识内容无关）。"""
    root = tmp_path / "kb"
    (root / ".memoria" / "agent").mkdir(parents=True)
    return root


class ScriptProvider:
    """按脚本逐步产出流式事件（每步一个 list）；记录收到的请求。"""

    name = "script"

    def __init__(self, script: Sequence[Sequence[Any]]) -> None:
        self.script: list[list[Any]] = [list(step) for step in script]
        self.requests: list[LlmRequest] = []

    def stream(self, request: LlmRequest) -> Iterator[Any]:
        self.requests.append(request)
        step = self.script.pop(0) if self.script else [TextDelta("（脚本耗尽）"), FinishEvent(reason=FinishReason.STOP)]
        yield from step


def text_step(text: str, reasoning: str = "") -> list[Any]:
    events: list[Any] = []
    if reasoning:
        events.append(ReasoningDelta(reasoning))
    events.extend([TextDelta(text), FinishEvent(reason=FinishReason.STOP)])
    return events


def session_events(kb: Path, session_id: str) -> list[dict[str, Any]]:
    return [row for row in read_session(str(kb), session_id) if isinstance(row.get("seq"), int)]


# —— ① `arg_summary` ——


def test_arg_summary_picks_key_by_tool_name() -> None:
    """按工具名挑键：read_document→path、grep→pattern（拼 include）、propose_write→intent。"""
    assert arg_summary("read_document", json.dumps({"path": "notes/a.md"})) == "notes/a.md"
    assert arg_summary("read_document", {"path": "notes/b.md"}) == "notes/b.md"  # dict 形态同样接受
    assert arg_summary("grep", json.dumps({"pattern": "多层", "include": "*.md"})) == "多层 *.md"
    assert arg_summary("propose_write", json.dumps({"intent": "写入新页", "path": "x.md"})) == "写入新页"


def test_arg_summary_falls_back_to_first_scalar_and_tolerates_bad_json() -> None:
    """未知工具 ⇒ 第一个非空标量值；坏 JSON / 非对象 / 缺参 ⇒ 空串（不抛）。"""
    assert arg_summary("神秘工具", json.dumps({"b": "有值", "a": 2})) == "有值"
    assert arg_summary("read_document", "{不是 JSON") == ""
    assert arg_summary("read_document", None) == ""
    assert arg_summary("read_document", json.dumps([1, 2])) == ""


def test_arg_summary_truncates_to_120() -> None:
    assert len(arg_summary("search_kb", json.dumps({"query": "长" * 200}))) == 120


# —— ② `row_detail` ——


def test_row_detail_folds_whitespace_and_truncates() -> None:
    assert row_detail("a\n\nb\tc") == "a b c"
    assert len(row_detail("x" * 300)) == 240
    assert row_detail(None) == "" and row_detail("") == ""


# —— ③ `tool_row` ——


def test_tool_row_call_and_result_share_id_and_state() -> None:
    arguments = json.dumps({"path": "notes/a.md"})
    running = tool_row({"id": "c1", "name": "read_document", "arguments": arguments}, state="running", iteration=1)
    assert running["kind"] == "tool" and running["id"] == "c1" and running["state"] == "running"
    assert running["summary"] == "notes/a.md" and running["detail"] == "" and running["code"] is None

    ok = tool_row(
        {"id": "c1", "name": "read_document", "is_error": False, "code": "ok", "content": "正文\n第二行"},
        state="ok",
        iteration=1,
    )
    assert ok["id"] == running["id"]  # 同一 id ⇒ 前端合并
    assert ok["state"] == "ok" and ok["code"] == "ok" and ok["detail"] == "正文 第二行"

    err = tool_row(
        {"id": "c2", "name": "propose_write", "is_error": True, "code": "backup_failed", "content": "Error: 写入失败"},
        state="error",
        iteration=2,
    )
    assert err["state"] == "error" and err["code"] == "backup_failed" and err["detail"].startswith("Error:")


# —— ④ `step_row` ——


def test_step_row_counts_tool_calls_and_omits_empty_reasoning() -> None:
    row = step_row(1, "我先查一下", [{"id": "c1"}], reasoning="想一想")
    assert row == {"kind": "step", "iteration": 1, "text": "我先查一下", "tool_calls": 1, "reasoning": "想一想"}
    assert "reasoning" not in step_row(2, "答案", [], reasoning="")  # 空思考 ⇒ 不出现该键
    bare = step_row(2, None, None)
    assert bare["text"] == "" and bare["tool_calls"] == 0 and "reasoning" not in bare


# —— ⑤ `process_items` ——


def test_process_items_orders_rows_and_skips_final_answer() -> None:
    """一段含 2 步 + 1 次工具的事件序列 ⇒ 按事件顺序出行，且跳过最后一条 assistant/message。"""
    arguments = json.dumps({"query": "多层感知机"}, ensure_ascii=False)
    events = [
        {
            "seq": 1,
            "type": "assistant/message",
            "data": {
                "iteration": 1,
                "content": "我查一下。",
                "tool_calls": [{"id": "c1", "name": "search_kb", "arguments": arguments}],
                "reasoning": "先检索",
            },
        },
        {"seq": 2, "type": "tool/call", "data": {"id": "c1", "name": "search_kb", "arguments": arguments}},
        {"seq": 3, "type": "tool/result", "data": {"id": "c1", "name": "search_kb", "is_error": False, "code": "ok", "content": "neural-network.md:7"}},
        {"seq": 4, "type": "assistant/message", "data": {"iteration": 2, "content": "见 neural-network.md:7。", "tool_calls": []}},
    ]
    rows = process_items(events)
    assert [row["kind"] for row in rows] == ["step", "tool", "tool"]
    assert rows[0]["text"] == "我查一下。" and rows[0]["reasoning"] == "先检索" and rows[0]["tool_calls"] == 1
    assert rows[1]["id"] == rows[2]["id"] == "c1"
    assert (rows[1]["state"], rows[2]["state"]) == ("running", "ok")
    assert rows[1]["iteration"] == 1 and rows[2]["iteration"] == 1


def test_process_items_keeps_last_step_when_not_final_answer() -> None:
    """末条 `assistant/message` 带工具调用（非最终答案）⇒ 整轮过程全部保留可见。"""
    arguments = json.dumps({"pattern": "*.md"})
    events = [
        {"seq": 1, "type": "assistant/message", "data": {"iteration": 1, "content": "查一下", "tool_calls": [{"id": "c1", "name": "glob", "arguments": arguments}]}},
        {"seq": 2, "type": "tool/call", "data": {"id": "c1", "name": "glob", "arguments": arguments}},
        {"seq": 3, "type": "tool/result", "data": {"id": "c1", "name": "glob", "is_error": True, "code": "denied", "content": "拒绝访问"}},
    ]
    rows = process_items(events)
    assert [row["kind"] for row in rows] == ["step", "tool", "tool"]
    assert rows[2]["state"] == "error" and rows[2]["detail"] == "拒绝访问"


# —— ⑥ 落盘：思考随 `assistant/message` ——


def test_chained_event_persists_before_panel_and_survives_panel_error() -> None:
    """`_chained_event`：**先落盘、再回调**；面板回调抛异常也不漏落盘、不外抛。"""
    from memoria.services.agent.ask import _chained_event

    seen: list[str] = []

    class Store:
        """与 `SessionStore.append` 同签名的替身。"""

        def append(self, event_type: str, data: Any) -> None:
            seen.append("persist")

    def boom(event_type: str, data: Any) -> None:
        seen.append("panel")
        raise RuntimeError("面板坏了")

    emit = _chained_event(Store(), boom)
    assert emit is not None
    emit("tool/call", {"id": "c1"})  # 面板抛异常不外抛
    assert seen == ["persist", "panel"]
    assert _chained_event(None, None) is None  # 两路都为 None ⇒ 短路


def test_reasoning_persisted_with_assistant_message(kb: Path) -> None:
    session_id = "session-reason-0001"
    ask(str(kb), "问题", provider=ScriptProvider([text_step("最终答案", reasoning="先想一想")]), model="fake-model", session_id=session_id)

    assistant_rows = [row for row in session_events(kb, session_id) if row["type"] == "assistant/message"]
    assert assistant_rows and assistant_rows[0]["data"]["reasoning"] == "先想一想"


def test_reasoning_key_absent_without_reasoning(kb: Path) -> None:
    session_id = "session-noreason-0001"
    ask(str(kb), "问题", provider=ScriptProvider([text_step("答案")]), model="fake-model", session_id=session_id)

    assistant_rows = [row for row in session_events(kb, session_id) if row["type"] == "assistant/message"]
    assert assistant_rows and "reasoning" not in assistant_rows[0]["data"]


def test_build_history_does_not_carry_reasoning(kb: Path) -> None:
    """落盘的 `reasoning` **不注入**模型请求：回放只读 `content`/`tool_calls`。"""
    session_id = "session-reason-history-0001"
    ask(str(kb), "问题", provider=ScriptProvider([text_step("答案", reasoning="秘密思考")]), model="fake-model", session_id=session_id)

    history = build_history(str(kb), session_id)
    contents = [str(message.content) for message in history]
    assert "答案" in contents  # 正文照常回放
    assert all("秘密思考" not in content for content in contents)  # 思考不注入模型请求


# —— ⑦ 回放：`conversation_messages()` 带 `process` ——


def test_conversation_messages_carries_process_for_tool_turn(kb: Path) -> None:
    session_id = "session-view-process"
    arguments = json.dumps({"query": "多层感知机"}, ensure_ascii=False)
    store = SessionStore(str(kb), session_id)
    store.append("user/message", {"text": "在哪？"})
    store.append(
        "assistant/message",
        {"iteration": 1, "content": "我查一下。", "tool_calls": [{"id": "c1", "name": "search_kb", "arguments": arguments}], "reasoning": "先检索"},
    )
    store.append("tool/call", {"id": "c1", "name": "search_kb", "arguments": arguments})
    store.append("tool/result", {"id": "c1", "name": "search_kb", "is_error": False, "code": "ok", "content": "neural-network.md:7", "anchors": []})
    store.append("assistant/message", {"iteration": 2, "content": "见 neural-network.md:7。", "tool_calls": []})

    view = conversation_messages(str(kb), session_id)
    assert [item["role"] for item in view] == ["user", "assistant"]
    assert view[1]["text"] == "见 neural-network.md:7。"  # 答案口径不变：仍取最后一条非空 assistant/message
    process = view[1]["process"]
    assert [row["kind"] for row in process] == ["step", "tool", "tool"]
    assert process[0]["text"] == "我查一下。" and process[0]["reasoning"] == "先检索"
    assert process[1]["summary"] == "多层感知机"


def test_conversation_messages_keeps_final_answer_step_reasoning(kb: Path) -> None:
    """**单步回合**的思考不能丢：唯一那条 `assistant/message` 既是过程又是答复。

    L4 实测（harness 8647，合成会话）：该条带 `reasoning`，但 `process_items()` 有意跳过"构成最终
    答复的那一步"（免得正文在过程列表里重复）⇒ 若不在气泡记录上单列 `reasoning`，前端连思考块都
    不建（`.-agent-think-body` 计数 0、思考里的公式一个字都看不到）。
    """
    session_id = "session-view-final-reasoning"
    store = SessionStore(str(kb), session_id)
    store.append("user/message", {"text": "算个公式"})
    store.append(
        "assistant/message",
        {"iteration": 1, "content": "行内 $E=mc^2$。", "reasoning": "先想：$a^2+b^2=c^2$", "tool_calls": []},
    )

    view = conversation_messages(str(kb), session_id)
    assert view[1]["text"] == "行内 $E=mc^2$。"
    assert view[1]["reasoning"] == "先想：$a^2+b^2=c^2$", "最终答复那一步的思考要单列在记录上"
    assert "process" not in view[1], "只有一步且它就是答复 ⇒ 无过程行（正文不重复）"


def test_conversation_messages_omits_process_key_without_process(kb: Path) -> None:
    session_id = "session-view-plain"
    store = SessionStore(str(kb), session_id)
    store.append("user/message", {"text": "问"})
    store.append("assistant/message", {"content": "答"})

    view = conversation_messages(str(kb), session_id)
    assert [item["role"] for item in view] == ["user", "assistant"]
    assert "process" not in view[1]  # 无过程内容 ⇒ 保持旧形状（不写该键）


# —— ⑧ 配置键 `transcript_mode` ——


def test_transcript_mode_default_write_and_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """配置键 `transcript_mode`：默认 compact、可存 normal、非法值报 ConfigError 且不落盘。"""
    from memoria.services.agent.llm import config as config_module

    config_file = tmp_path / "agent.json"
    monkeypatch.setenv("MEMORIA_AGENT_CONFIG", str(config_file))

    assert config_module.DEFAULT_TRANSCRIPT_MODE == "compact"
    assert config_module.transcript_mode() == "compact"  # 缺省
    assert not hasattr(config_module.load_config(), "transcript_mode")  # UI 旋钮，不进调用参数

    assert config_module.save_config({"transcript_mode": "normal"})["transcript_mode"] == "normal"
    assert config_module.transcript_mode() == "normal"  # 可存 normal 并读回

    assert config_module.save_config({"transcript_mode": ""})["transcript_mode"] == "normal"  # 空值 = 不修改
    with pytest.raises(ConfigError):
        config_module.save_config({"transcript_mode": "wide"})  # 非法值不落盘
    assert config_module.transcript_mode() == "normal"

    config_file.write_text(json.dumps({"transcript_mode": "oops"}), encoding="utf-8")
    assert config_module.transcript_mode() == "compact"  # 手改坏值 ⇒ 读侧宽松回退


def test_agent_get_config_reads_transcript_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`agent_get_config` 能把 `transcript_mode` 读回（默认 compact，可存 normal）。"""
    from memoria.presentation.api.ui import UIAPI

    kb = tmp_path / "kb"
    (kb / ".memoria" / "agent").mkdir(parents=True)
    monkeypatch.setenv("MEMORIA_AGENT_CONFIG", str(tmp_path / "agent.json"))

    api = UIAPI(kb_path=str(kb))
    assert api.agent_get_config()["transcript_mode"] == "compact"
    api.agent_save_config({"transcript_mode": "normal"})
    assert api.agent_get_config()["transcript_mode"] == "normal"
