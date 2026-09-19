# 配套单测：被测调用面语义移植自 deepseek-harness packages/compaction/compaction-tool-result-pruner
# （MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""工具结果裁剪（M2）离线单测：不联网、不写知识库正文。

覆盖：
① 纯函数（超预算才裁、头/标记/尾形状、`tail=0` 不退化、预算构造期校验、清单筛选与幂等、
   畸形记录 fail-safe）；
② 回放（裁剪记录就地生效、原事件仍在、可取原始视图、未知 seq 忽略、后写覆盖）；
③ 计账（`event_chars` 的有效字符覆盖表、`select_span` 按有效视图选区间）；
④ 端到端（压力确认后先裁、裁完够用就**免掉**摘要调用、仍超则照常压缩且摘要器读裁剪视图、
   预算内一次多余调用都不发、仅追加 + seq 连续）。
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from memoria.services.agent.ask import ask
from memoria.services.agent.compaction import (
    COMPACTION_INSTRUCTION,
    event_chars,
    select_span,
)
from memoria.services.agent.llm import (
    FinishEvent,
    FinishReason,
    LlmRequest,
    Role,
    TextDelta,
    Usage,
    UsageEvent,
)
from memoria.services.agent.pruner import (
    PRUNE,
    PRUNE_MARKER,
    PruneBudgets,
    PruneError,
    applied_chars,
    apply_budget,
    prune_applied,
    prune_plan,
    prune_records,
    prune_text,
)
from memoria.services.agent.session.history import (
    ASSISTANT_MESSAGE,
    COMPACTION,
    TOOL_RESULT,
    USER_MESSAGE,
    build_history,
    replay_events,
)
from memoria.services.agent.session.store import SessionStore, read_session

# —— 测试替身（与 tests/test_agent_compaction.py 同形）——


class FakeProvider:
    """按脚本产出流式事件的假 provider；记录收到的请求以便断言。"""

    name = "fake"

    def __init__(self, script: Sequence[Sequence[Any]]) -> None:
        self.script: list[list[Any]] = [list(step) for step in script]
        self.requests: list[LlmRequest] = []

    def stream(self, request: LlmRequest) -> Iterator[Any]:
        self.requests.append(request)
        step = self.script.pop(0) if self.script else [TextDelta("（脚本耗尽）"), FinishEvent(reason=FinishReason.STOP)]
        yield from step


def text_step(text: str) -> list[Any]:
    return [
        TextDelta(text),
        UsageEvent(Usage(prompt_tokens=10, completion_tokens=5)),
        FinishEvent(reason=FinishReason.STOP),
    ]


SUMMARY_TEXT = "## 待办\n- (none)\n"

# —— 辅助 ——


def _session(root: Path, session_id: str, events: Sequence[tuple[str, dict[str, Any]]]) -> SessionStore:
    store = SessionStore(str(root), session_id)
    for kind, data in events:
        store.append(kind, data)
    store.flush()
    return store


def _kb(root: Path) -> Path:
    (root / ".memoria" / "agent").mkdir(parents=True, exist_ok=True)
    (root / "doc.md").write_text("# 文档\n\n正文。\n", encoding="utf-8")
    return root


def _turn(index: int, size: int) -> list[tuple[str, dict[str, Any]]]:
    """一轮纯文本问答（正文带 `FILLER<index>` 标记）。"""
    body = f"FILLER{index}-" + "x" * size
    return [(USER_MESSAGE, {"text": body}), (ASSISTANT_MESSAGE, {"content": body})]


def _tool_turn(index: int, size: int) -> list[tuple[str, dict[str, Any]]]:
    """一轮**带工具调用**的问答；工具结果首尾带可辨识标记、中段全是 `M`（便于断言中段被删）。"""
    call_id = f"call-{index}"
    body = f"HEAD-BIG-{index}-" + "M" * size + f"-TAIL-BIG-{index}"
    return [
        (USER_MESSAGE, {"text": f"看看这个 FILLER{index}"}),
        (
            ASSISTANT_MESSAGE,
            {"content": "", "tool_calls": [{"id": call_id, "name": "search_kb", "arguments": "{}"}]},
        ),
        (TOOL_RESULT, {"id": call_id, "name": "search_kb", "content": body, "anchors": []}),
        (ASSISTANT_MESSAGE, {"content": f"答案 FILLER{index}"}),
    ]


def _tool_messages(messages: Sequence[Any]) -> list[Any]:
    return [message for message in messages if message.role == Role.TOOL]


# —— ① 纯函数 ——


def test_prune_text_is_none_within_budget() -> None:
    budgets = PruneBudgets(threshold=100, head=40, tail=20)
    assert prune_text("x" * 100, budgets=budgets) is None, "恰好等于阈值不算超预算"
    assert prune_text("x" * 60, budgets=budgets) is None


def test_prune_text_keeps_head_marker_tail() -> None:
    budgets = PruneBudgets(threshold=60, head=10, tail=10)
    body = "H" * 10 + "M" * 100 + "T" * 10
    out = prune_text(body, budgets=budgets)
    assert out == "H" * 10 + PRUNE_MARKER + "T" * 10
    assert len(out) == applied_chars(10, 10) <= budgets.threshold, "产出必须不超过阈值"
    assert len(out) < len(body), "产出必须严格变短"


def test_apply_budget_with_zero_tail_keeps_no_tail() -> None:
    """`tail=0` 时不得把整段正文当"末段"再拼一次（`text[-0:]` 的经典陷阱）。"""
    out = apply_budget("A" * 100, 3, 0)
    assert out == "AAA" + PRUNE_MARKER


@pytest.mark.parametrize(
    "kwargs",
    [
        {"threshold": 0},
        {"threshold": -1},
        {"threshold": True},
        {"head": -1},
        {"tail": -1},
        {"head": 1.5},
        {"head": 8_000, "tail": 1_000},  # head + 标记 + tail > threshold ⇒ 会变长，必须拒绝
    ],
)
def test_budgets_reject_invalid_values(kwargs: dict[str, Any]) -> None:
    with pytest.raises(PruneError):
        PruneBudgets(**kwargs)


def test_prune_plan_selects_only_over_budget_tool_results() -> None:
    big = "B" * 20_000
    events: list[dict[str, Any]] = [
        {"seq": 0, "type": USER_MESSAGE, "data": {"text": "x" * 20_000}},
        {"seq": 1, "type": TOOL_RESULT, "data": {"id": "a", "content": big}},
        {"seq": 2, "type": TOOL_RESULT, "data": {"id": "b", "content": "small"}},
        {"seq": 3, "type": ASSISTANT_MESSAGE, "data": {"content": big}},
    ]
    plan = prune_plan(events)
    assert [item["seq"] for item in plan] == [1]
    item = plan[0]
    assert item["id"] == "a"
    assert item["chars_before"] == 20_000
    assert item["chars_after"] == applied_chars(4_096, 1_024)
    assert (item["head"], item["tail"]) == (4_096, 1_024)


def test_prune_plan_skips_shadowed_and_already_pruned() -> None:
    big = "B" * 20_000
    events: list[dict[str, Any]] = [
        {"seq": 0, "type": TOOL_RESULT, "data": {"id": "a", "content": big}},
        {"seq": 1, "type": TOOL_RESULT, "data": {"id": "b", "content": big}},
        {"seq": 2, "type": PRUNE, "data": {"pruned": [{"seq": 1, "head": 4_096, "tail": 1_024}]}},
    ]
    assert [item["seq"] for item in prune_plan(events)] == [0], "已裁过的 seq 不得重复记录"
    assert prune_plan(events, skip={0}) == [], "被压缩覆盖的 seq 不必裁"
    assert prune_records(events) == {1}


def test_prune_applied_ignores_malformed_records() -> None:
    events: list[dict[str, Any]] = [
        {
            "seq": 9,
            "type": PRUNE,
            "data": {
                "pruned": [
                    {"seq": 1, "head": 10, "tail": 5},
                    {"seq": 2, "head": 10},  # 缺 tail
                    {"seq": 3, "head": "10", "tail": 5},  # 类型不对
                    {"seq": 4, "head": -1, "tail": 5},  # 负数
                    {"head": 10, "tail": 5},  # 缺 seq
                    "not-a-mapping",
                ]
            },
        },
        {"seq": 10, "type": PRUNE, "data": {}},
    ]
    assert prune_applied(events) == {1: (10, 5)}


# —— ② 回放 ——


def test_build_history_applies_prune_record(tmp_path: Path) -> None:
    root = _kb(tmp_path / "kb")
    _session(root, "pruned", _tool_turn(0, 20_000))
    events = read_session(str(root), "pruned")
    seq = next(row["seq"] for row in events if row.get("type") == TOOL_RESULT)
    original = next(row for row in events if row.get("type") == TOOL_RESULT)["data"]["content"]

    store = SessionStore(str(root), "pruned")
    store.append(PRUNE, {"pruned": [{"seq": seq, "head": 100, "tail": 50}], "chars_removed": 1})
    store.flush()

    tool = _tool_messages(build_history(str(root), "pruned"))[0]
    assert tool.content == apply_budget(original, 100, 50)
    assert PRUNE_MARKER in tool.content
    # 原始视图：不带 prune 表就照原文回放（日志里仍是原文）
    covered = [row for row in read_session(str(root), "pruned") if isinstance(row.get("seq"), int)]
    raw_tool = _tool_messages(replay_events(covered))[0]
    assert raw_tool.content == original, "原事件必须逐字保留（append-only）"


def test_prune_record_for_unknown_seq_is_ignored(tmp_path: Path) -> None:
    """指向不存在 seq 的裁剪记录不得影响回放（也不吞掉任何事件）。"""
    root = _kb(tmp_path / "kb")
    _session(root, "dangling", _turn(0, 100))
    store = SessionStore(str(root), "dangling")
    store.append(PRUNE, {"pruned": [{"seq": 999, "head": 10, "tail": 5}]})
    store.flush()
    messages = build_history(str(root), "dangling")
    assert [message.content for message in messages] == ["FILLER0-" + "x" * 100] * 2


def test_later_prune_record_wins(tmp_path: Path) -> None:
    root = _kb(tmp_path / "kb")
    _session(root, "chain", _tool_turn(0, 20_000))
    events = read_session(str(root), "chain")
    seq = next(row["seq"] for row in events if row.get("type") == TOOL_RESULT)
    original = next(row for row in events if row.get("type") == TOOL_RESULT)["data"]["content"]
    store = SessionStore(str(root), "chain")
    store.append(PRUNE, {"pruned": [{"seq": seq, "head": 100, "tail": 50}]})
    store.append(PRUNE, {"pruned": [{"seq": seq, "head": 20, "tail": 10}]})
    store.flush()
    assert _tool_messages(build_history(str(root), "chain"))[0].content == apply_budget(original, 20, 10)


# —— ③ 计账 ——


def test_event_chars_uses_effective_chars() -> None:
    event = {"seq": 5, "type": TOOL_RESULT, "data": {"content": "x" * 100}}
    assert event_chars(event) == 100
    assert event_chars(event, effective_chars={5: 20}) == 20
    assert event_chars(event, effective_chars={6: 20}) == 100, "未命中的 seq 按原文计"
    assert event_chars(event, effective_chars={}) == 100


def test_select_span_accounts_for_effective_chars() -> None:
    """尾部被裁小 ⇒ 有效视图认为尾部不够 `retain`，于是……裁得**更少**（返回 None）。"""
    events: list[dict[str, Any]] = []
    for index in range(10):
        kind = USER_MESSAGE if index % 2 == 0 else ASSISTANT_MESSAGE
        key = "text" if index % 2 == 0 else "content"
        events.append({"seq": index, "type": kind, "data": {key: "x" * 1_000}})
    assert select_span(events) == (0, 4)
    # 前 6 条事件的有效字符为 0 ⇒ 有效总量只剩 4000 < retain(5120) ⇒ 无可压区间
    assert select_span(events, effective_chars={index: 0 for index in range(6)}) is None


# —— ④ 端到端 ——


def test_ask_prunes_and_skips_summary_when_pressure_relieved(tmp_path: Path) -> None:
    """压力来自一个超大工具结果：裁完已低于阈值 ⇒ **一次模型调用都不多发**。"""
    root = _kb(tmp_path / "kb")
    _session(root, "big-tool", _tool_turn(0, 30_000))
    before = read_session(str(root), "big-tool")

    provider = FakeProvider([text_step("裁剪后的答案")])
    result = ask(str(root), "接着说说", provider=provider, model="probe-model", session_id="big-tool")

    assert result.answer == "裁剪后的答案"
    assert len(provider.requests) == 1, "裁剪已解除压力，不该再发摘要调用"
    tool = _tool_messages(provider.requests[0].messages)[0]
    assert PRUNE_MARKER in tool.content
    assert len(tool.content) == applied_chars(4_096, 1_024)
    assert "M" * 5_000 not in tool.content, "被删的中段不得再进请求"
    assert "HEAD-BIG-0-" in tool.content and "-TAIL-BIG-0" in tool.content

    after = read_session(str(root), "big-tool")
    assert after[: len(before)] == before, "既有记录必须逐条不变（仅追加）"
    records = [row for row in after if row.get("type") == PRUNE]
    assert len(records) == 1
    assert not [row for row in after if row.get("type") == COMPACTION]
    item = records[0]["data"]["pruned"][0]
    assert item["chars_before"] == 30_022
    assert item["chars_after"] == applied_chars(4_096, 1_024)
    assert records[0]["data"]["chars_removed"] == item["chars_before"] - item["chars_after"]
    # 日志里仍是原文（回放安全）
    original = next(row for row in after if row.get("type") == TOOL_RESULT)
    assert len(original["data"]["content"]) == 30_022
    # 幂等：再扫一遍不会有新的裁剪项
    assert prune_plan(after) == []
    # seq 连续
    seqs = [row["seq"] for row in after if isinstance(row.get("seq"), int)]
    assert seqs == list(range(len(seqs)))


def test_ask_prunes_then_still_compacts_when_pressure_remains(tmp_path: Path) -> None:
    """裁完仍超预算 ⇒ 照常压缩，且**摘要器读的是裁剪视图**（工具结果落在被压区间内）。"""
    root = _kb(tmp_path / "kb")
    events: list[tuple[str, dict[str, Any]]] = list(_tool_turn(9, 30_000))
    for index in range(4):
        events += _turn(index, 4_000)
    _session(root, "mixed", events)

    provider = FakeProvider([text_step(SUMMARY_TEXT), text_step("压缩后的答案")])
    result = ask(str(root), "接着说说", provider=provider, model="probe-model", session_id="mixed")

    assert result.answer == "压缩后的答案"
    assert len(provider.requests) == 2, "第一次是摘要、第二次是主回合"
    assert provider.requests[0].messages[-1].content == COMPACTION_INSTRUCTION
    summarizer_input = "\n".join(message.content for message in provider.requests[0].messages)
    assert PRUNE_MARKER in summarizer_input, "摘要器必须读到裁剪后的表面"
    assert "M" * 5_000 not in summarizer_input
    assert "HEAD-BIG-9-" in summarizer_input and "-TAIL-BIG-9" in summarizer_input

    records = read_session(str(root), "mixed")
    assert len([row for row in records if row.get("type") == PRUNE]) == 1
    assert len([row for row in records if row.get("type") == COMPACTION]) == 1
    # 主回合：checkpoint 到了（覆盖区间不再逐字重发）
    main = "\n".join(message.content for message in provider.requests[1].messages)
    assert "(none)" in main
    # 文件仍是「一行一个 JSON 对象」
    path = root / ".memoria" / "agent" / "sessions" / "mixed.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        assert isinstance(json.loads(line), dict)


def test_ask_does_not_prune_within_budget(tmp_path: Path) -> None:
    """历史在预算内 ⇒ 一次多余的模型调用都不发、也不落任何 `compaction*` 记录。"""
    root = _kb(tmp_path / "kb")
    _session(root, "short", _turn(0, 100))
    provider = FakeProvider([text_step("答案")])
    result = ask(str(root), "再问一句", provider=provider, model="probe-model", session_id="short")
    assert result.answer == "答案"
    assert len(provider.requests) == 1
    kinds = {row.get("type") for row in read_session(str(root), "short")}
    assert PRUNE not in kinds and COMPACTION not in kinds
