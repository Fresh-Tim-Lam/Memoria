# 配套单测：被测调用面语义移植自 deepseek-harness packages/core/{agent-loop,tools}、
# packages/session/*、packages/interaction/user-approval（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""agent 循环 / 工具 / 会话 / 审批 的离线单测：不联网、不写知识库正文。

覆盖（对应任务验收项）：
① loop 单轮无工具直接答；② 一轮工具调用后回填并给出最终答案；③ 未知工具/参数非法
→ 工具结果带错误且循环继续；④ 达 `max_iterations` 的终止行为；⑤ 会话 JSONL 追加与
回放；⑥ 审批默认策略**全线放行**（2026-09-21 起，写路径靠备份 + 撤销兜底）；⑦ 只读工具调用后知识库零写入。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from memoria.services.agent.approvals import (
    ApprovalOutcome,
    ApprovalRequest,
    AskPolicy,
    DefaultApprovalPolicy,
    NeverPolicy,
)
from memoria.services.agent.ask import ask
from memoria.services.agent.llm import (
    FinishEvent,
    FinishReason,
    LlmRequest,
    ProviderError,
    RetryPolicy,
    Role,
    TextDelta,
    ToolCall,
    Usage,
    UsageEvent,
)
from memoria.services.agent.loop import DEFAULT_MAX_ITERATIONS, AgentLoop, StopReason
from memoria.services.agent.prompt import FILE_REFERENCE_TOOLS, build_system_prompt
from memoria.services.agent.session.store import SessionStore, new_session_id, read_session
from memoria.services.agent.tools import (
    DENIED_CODE,
    INVALID_ARGUMENTS_CODE,
    KB_TOOL_NAMES,
    UNKNOWN_TOOL_CODE,
    Tool,
    ToolOutput,
    ToolRegistry,
    build_kb_tools,
)

NEURAL_MD = """# 神经网络

## 感知机

最古老的线性分类器。

## 多层感知机

MLP 由多层全连接组成。
"""

NEURAL_SIDECAR = """schema_version: 1
file: neural-network.md
knowledge_points:
- id: perceptron
  name: 感知机
  tags:
  - 神经网络
  range:
    start:
      snippet: '## 感知机'
      line_hint: 3
    end:
      snippet: 最古老的线性分类器。
      line_hint: 5
- id: mlp
  name: 多层感知机
  tags:
  - 神经网络
  range:
    start:
      snippet: '## 多层感知机'
      line_hint: 7
    end:
      snippet: MLP 由多层全连接组成。
      line_hint: 9
"""

SUPERVISED_MD = """# 监督学习

## 定义

用带标签的数据训练模型。
"""

SUPERVISED_SIDECAR = """schema_version: 1
file: supervised.md
knowledge_points:
- id: supervised
  name: 监督学习
  tags:
  - 学习范式
  range:
    start:
      snippet: '## 定义'
      line_hint: 3
    end:
      snippet: 用带标签的数据训练模型。
      line_hint: 5
"""

KB_SPEC = """# 知识库编撰与维护规范

KP 只认 sidecar；改 KP = 改 sidecar。
"""


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    """最小知识库：两篇文档 + 两个 sidecar + 一个指令文件；**故意不带任何缓存**。"""
    root = tmp_path / "kb"
    (root / ".memoria" / "sidecars").mkdir(parents=True)
    (root / ".memoria" / "agent").mkdir(parents=True)
    (root / "neural-network.md").write_text(NEURAL_MD, encoding="utf-8")
    (root / "supervised.md").write_text(SUPERVISED_MD, encoding="utf-8")
    (root / ".memoria" / "sidecars" / "neural-network.memoria.yaml").write_text(NEURAL_SIDECAR, encoding="utf-8")
    (root / ".memoria" / "sidecars" / "supervised.memoria.yaml").write_text(SUPERVISED_SIDECAR, encoding="utf-8")
    (root / ".memoria" / "agent" / "kb-spec.zh-CN.md").write_text(KB_SPEC, encoding="utf-8")
    return root


# —— 测试替身 ——


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


class AlwaysFailingProvider:
    """每次 `stream()` 都以同一可重试失败抛错（用于断言"已重试 N 次"）。"""

    name = "failing"

    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.calls = 0

    def stream(self, request: LlmRequest) -> Iterator[Any]:
        self.calls += 1
        raise self.error
        yield  # pragma: no cover —— 只为让本方法是生成器（与真 provider 一致）


def tool_step(*calls: ToolCall) -> list[Any]:
    return [FinishEvent(reason=FinishReason.TOOL_CALLS, tool_calls=calls)]


def kb_registry(kb: Path, **kwargs: Any) -> ToolRegistry:
    return ToolRegistry(build_kb_tools(str(kb), **kwargs))


def is_role(message: Any, role: Role) -> bool:
    return message.role == role or message.role == role.value


def _snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    """全库文件的 (mtime_ns, size, sha256) 快照（只比对文件，目录 mtime 不计）。"""
    out: dict[str, tuple[int, int, str]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        out[str(path.relative_to(root)).replace("\\", "/")] = (
            stat.st_mtime_ns,
            stat.st_size,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
    return out


# —— ① 单轮无工具 ——


def test_loop_answers_without_tools(kb: Path) -> None:
    provider = FakeProvider([text_step("直答：这是一个知识库。")])
    loop = AgentLoop(provider=provider, tools=kb_registry(kb), model="fake-model")

    result = loop.run("这是什么？")

    assert result.stop_reason is StopReason.FINAL_ANSWER
    assert result.answer == "直答：这是一个知识库。"
    assert result.iterations == 1
    assert result.tool_calls == () and result.anchors == ()
    assert result.usage.total == 15
    sent = provider.requests[0]
    assert sent.model == "fake-model"
    # 与工具集清单同源（原来这里是硬编码的五个名字，新增工具时会漂移）
    assert [tool.name for tool in sent.tools] == list(KB_TOOL_NAMES)
    assert sent.messages[-1].content == "这是什么？"


# —— ② 一轮工具调用后回填 ——


def test_loop_executes_tool_then_answers(kb: Path) -> None:
    provider = FakeProvider(
        [
            tool_step(ToolCall(id="c1", name="search_kb", arguments=json.dumps({"query": "多层感知机"}))),
            text_step("MLP 见 neural-network.md:7"),
        ]
    )
    loop = AgentLoop(provider=provider, tools=kb_registry(kb))

    result = loop.run("多层感知机讲的是什么？")

    assert result.stop_reason is StopReason.FINAL_ANSWER
    assert result.iterations == 2
    assert result.answer == "MLP 见 neural-network.md:7"
    assert [call.name for call in result.tool_calls] == ["search_kb"]
    assert not result.tool_calls[0].is_error
    anchors = {(anchor["file"], anchor["line"], anchor["kp_id"]) for anchor in result.anchors}
    assert ("neural-network.md", 7, "mlp") in anchors

    second = list(provider.requests[1].messages)
    assistant = next(message for message in second if is_role(message, Role.ASSISTANT))
    assert assistant.tool_calls[0].name == "search_kb"
    tool_message = next(message for message in second if is_role(message, Role.TOOL))
    assert tool_message.tool_call_id == "c1"
    assert "neural-network.md:7" in tool_message.content


# —— ③ 未知工具 / 参数非法 ——


def test_unknown_tool_and_invalid_arguments_keep_loop_running(kb: Path) -> None:
    provider = FakeProvider(
        [
            tool_step(
                ToolCall(id="c1", name="no_such_tool", arguments="{}"),
                ToolCall(id="c2", name="search_kb", arguments='{"query": 42}'),
                ToolCall(id="c3", name="search_kb", arguments="{不是 JSON"),
            ),
            text_step("已忽略那几个失败调用。"),
        ]
    )
    loop = AgentLoop(provider=provider, tools=kb_registry(kb))

    result = loop.run("随便问问")

    assert result.stop_reason is StopReason.FINAL_ANSWER
    assert [call.output.code for call in result.tool_calls] == [
        UNKNOWN_TOOL_CODE,
        INVALID_ARGUMENTS_CODE,
        INVALID_ARGUMENTS_CODE,
    ]
    assert all(call.content.startswith("Error: ") for call in result.tool_calls)
    tool_contents = [
        message.content for message in provider.requests[1].messages if is_role(message, Role.TOOL)
    ]
    assert len(tool_contents) == 3
    assert all(content.startswith("Error: ") for content in tool_contents)


# —— ④ 达上限 ——


def test_loop_stops_at_max_iterations(kb: Path) -> None:
    provider = FakeProvider(
        [tool_step(ToolCall(id=f"c{index}", name="kb_overview", arguments="{}")) for index in range(5)]
    )
    loop = AgentLoop(provider=provider, tools=kb_registry(kb), max_iterations=3)

    result = loop.run("一直查概览")

    assert result.stop_reason is StopReason.MAX_ITERATIONS
    assert result.iterations == 3
    assert len(result.tool_calls) == 3
    assert len(provider.requests) == 3


def test_default_iteration_budget_is_unbounded(kb: Path) -> None:
    """默认**不设**轮次预算（人 2026-09-22：「怎么有连续调用工具的 8 轮上限，上游都没有」）。

    对齐上游：`agent-loop/README.zh.md:200`「没有内置轮次预算：工具调用或 steering 会让当前轮次继续；
    限制失控轮次的策略必须从既有生命周期扩展点（如 `agent/turn-stopping`）执行取消」。

    **回归钉子**：旧默认 `max_iterations = 8` 会在第 8 步切断 ⇒ 本用例跑满 12 步工具调用再收尾，
    在旧默认下必然失败。
    """
    provider = FakeProvider(
        [tool_step(ToolCall(id=f"c{index}", name="kb_overview", arguments="{}")) for index in range(12)]
        + [text_step("查完了。")]
    )
    loop = AgentLoop(provider=provider, tools=kb_registry(kb))  # 不传 max_iterations ⇒ 用默认

    result = loop.run("连着查 12 次")

    assert DEFAULT_MAX_ITERATIONS == 0, "默认 = 无上限"
    assert result.stop_reason is StopReason.FINAL_ANSWER
    assert result.iterations == 13, "12 步工具调用 + 1 步收尾，一步没被砍"
    assert len(provider.requests) == 13


def test_iteration_budget_semantics(kb: Path) -> None:
    """`max_iterations`：0（与默认）= 无上限；正数仍是硬上限；负数非法（不静默当成 0）。"""
    with pytest.raises(ValueError):
        AgentLoop(provider=FakeProvider([]), tools=kb_registry(kb), max_iterations=-1)

    provider = FakeProvider(
        [tool_step(ToolCall(id=f"c{index}", name="kb_overview", arguments="{}")) for index in range(3)]
        + [text_step("收尾。")]
    )
    explicit_zero = AgentLoop(provider=provider, tools=kb_registry(kb), max_iterations=0)

    assert explicit_zero.run("查三个概览").stop_reason is StopReason.FINAL_ANSWER


def test_loop_reports_error_stop_reason(kb: Path) -> None:
    provider = FakeProvider([[TextDelta("半句"), FinishEvent(reason=FinishReason.ABORTED)]])
    loop = AgentLoop(provider=provider, tools=kb_registry(kb))

    result = loop.run("会被中断")

    assert result.stop_reason is StopReason.ABORTED
    assert result.answer == "半句"  # 已投递文本保留（对齐上游取消语义）


# —— ④b 最终错误串带重试次数 ——


def test_loop_appends_retry_count_to_final_error(kb: Path) -> None:
    provider = AlwaysFailingProvider(ProviderError("服务端错误", code="SERVER", status=500))
    loop = AgentLoop(
        provider=provider,
        tools=kb_registry(kb),
        retry_policy=RetryPolicy(max_retries=2, initial_delay_s=0.001, max_delay_s=0.01, jitter_ratio=0.0),
    )

    result = loop.run("会失败的问题")

    assert result.stop_reason is StopReason.ERROR
    assert provider.calls == 3  # 首次 + 2 次重试
    assert result.error is not None
    assert result.error.endswith("（已重试 2 次）")
    assert "服务端错误" in result.error


def test_loop_error_without_retry_has_no_retry_note(kb: Path) -> None:
    provider = AlwaysFailingProvider(ProviderError("服务端错误", code="SERVER", status=500))
    loop = AgentLoop(provider=provider, tools=kb_registry(kb), retry_policy=RetryPolicy(max_retries=0))

    result = loop.run("一次失败")

    assert provider.calls == 1
    assert result.error is not None and result.error == "服务端错误"  # N=0 时不加后缀


def test_loop_unreachable_error_fails_without_retry(kb: Path) -> None:
    """确定性连接失败（UNREACHABLE）：一次尝试即失败，且错误串不含重试次数。"""
    error = ProviderError("无法连接模型端点 X:1/v1：目标端口拒绝连接", code="UNREACHABLE")
    provider = AlwaysFailingProvider(error)
    loop = AgentLoop(
        provider=provider,
        tools=kb_registry(kb),
        retry_policy=RetryPolicy(max_retries=5, initial_delay_s=0.001, max_delay_s=0.01, jitter_ratio=0.0),
    )

    result = loop.run("必拒连")

    assert provider.calls == 1
    assert result.error is not None and "已重试" not in result.error


# —— ⑤ 会话 JSONL ——


def test_session_jsonl_append_and_replay(kb: Path) -> None:
    session_id = new_session_id()
    store = SessionStore(str(kb), session_id)
    path = Path(store.path)
    assert path.parent == kb / ".memoria" / "agent" / "sessions"

    first = store.append("user/message", {"text": "你好"})
    second = store.append("assistant/message", {"content": "在的"})
    store.flush()
    assert (first["seq"], second["seq"]) == (0, 1)

    records = read_session(str(kb), session_id)
    assert records[0]["type"] == "session/header"
    assert records[0]["data"]["id"] == session_id
    assert [row["seq"] for row in records[1:]] == [0, 1]
    assert records[1]["data"]["text"] == "你好"

    before = path.stat().st_size
    store.append("loop/end", {"stop_reason": "final-answer"})
    assert path.stat().st_size > before  # 只追加
    assert "你好" in path.read_text(encoding="utf-8").splitlines()[1]  # 历史行未被改写

    resumed = SessionStore(str(kb), session_id)  # 复用同一 id：seq 续接
    assert resumed.next_seq == 3
    assert resumed.append("x", {})["seq"] == 3

    with pytest.raises(ValueError):
        SessionStore(str(kb), "../escape")


# —— ⑥ 审批默认策略 ——


def test_default_approval_allows_writes_now(kb: Path) -> None:
    """默认策略**全线放行**（人 2026-09-21 拍板："搁置审计设计、全线放开写机制"）。

    旧行为是"`read_only=False` 一律拒绝"；写路径现在的兜底是**写前备份 + 可撤销**，不是这道闸门。
    更严的档位由调用方**注入**：`NeverPolicy` 确定性拒绝、`AskPolicy` 交给应答者（无应答者即拒绝）。
    """
    policy = DefaultApprovalPolicy()
    assert policy.decide(ApprovalRequest(tool="search_kb", read_only=True)).allowed
    assert policy.decide(ApprovalRequest(tool="write_document", read_only=False)).allowed

    # 对齐上游：无应答者 / 应答者抛错 / 词汇外取值 ⇒ unavailable ⇒ 按拒绝关闭
    assert AskPolicy().decide(ApprovalRequest(tool="w", read_only=False)).outcome is ApprovalOutcome.UNAVAILABLE

    def boom(_request: ApprovalRequest) -> ApprovalOutcome:
        raise RuntimeError("没有可用 UI")

    assert AskPolicy(boom).decide(ApprovalRequest(tool="w", read_only=False)).outcome is ApprovalOutcome.UNAVAILABLE
    assert (
        AskPolicy(lambda _request: "yes").decide(ApprovalRequest(tool="w", read_only=False)).outcome
        is ApprovalOutcome.UNAVAILABLE
    )
    assert NeverPolicy().decide(ApprovalRequest(tool="w", read_only=False)).outcome is ApprovalOutcome.REJECTED

    # 写类工具走完整流水线：默认策略下**放行**（工具真的执行、循环继续）
    write_tool = Tool(
        name="write_document",
        description="写入文档（仅测试用）",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        handler=lambda _arguments: ToolOutput("已写入"),
        read_only=False,
    )
    registry = ToolRegistry([*build_kb_tools(str(kb)), write_tool])
    provider = FakeProvider([tool_step(ToolCall(id="w1", name="write_document", arguments="{}")), text_step("写入完成")])
    loop = AgentLoop(provider=provider, tools=registry, approval=policy)

    result = loop.run("请写入一篇文档")

    assert not result.tool_calls[0].is_error
    assert result.tool_calls[0].content == "已写入"
    assert result.stop_reason is StopReason.FINAL_ANSWER


def test_loop_writes_through_the_write_tool_in_one_turn(kb: Path) -> None:
    """端到端（真注册表 + 真默认策略 + 假 provider）：模型一次工具调用 ⇒ 文件**当场**变了。

    这正是"写机制全线放开"的核心行为：**不再需要人点确认卡**；写入审计落在**这次会话**里
    （`build_kb_tools(session_id=…)` 把它带进工具）。
    """
    from memoria.services.agent.tools.kb import PROPOSE_TOOL_NAME

    registry = ToolRegistry(build_kb_tools(str(kb), session_id="session-write-1"))
    provider = FakeProvider(
        [
            # 2026-09-22 起多了**读后写闸**（`fs-observation-policy` 端口）⇒ 按真实回合的顺序：先读、再写
            tool_step(
                ToolCall(id="r1", name="read_document", arguments=json.dumps({"path": "neural-network.md"}))
            ),
            tool_step(
                ToolCall(
                    id="w1",
                    name=PROPOSE_TOOL_NAME,
                    arguments=json.dumps(
                        {
                            "intent": "给「感知机」建档",
                            "ops": [
                                {
                                    "op": "upsert_kp",
                                    "file": "neural-network.md",
                                    "kp_id": "perceptron",
                                    "name": "感知机",
                                    "range": {"start": {"line": 1}, "end": {"line": 3}},
                                }
                            ],
                        }
                    ),
                )
            ),
            text_step("已写入。"),
        ]
    )
    loop = AgentLoop(provider=provider, tools=registry, approval=DefaultApprovalPolicy())

    result = loop.run("给感知机建档")

    writes = [call for call in result.tool_calls if call.name == PROPOSE_TOOL_NAME]
    assert writes and writes[0].is_error is False, writes[0].content
    assert writes[0].content.startswith("**已写入**")
    # 侧车真的落盘了（"KP 只认 sidecar"：没有 sidecar 就等于没建点）
    assert (kb / ".memoria" / "sidecars" / "neural-network.memoria.yaml").is_file()
    # 审计落在**这次会话**里（不是 ui-plan 伪会话）
    audit = (kb / ".memoria" / "agent" / "sessions" / "session-write-1.jsonl").read_text(encoding="utf-8")
    assert "capability/apply" in audit


# —— ⑦ 只读工具零写入 ——


def test_read_only_tools_leave_knowledge_base_untouched(kb: Path) -> None:
    registry = kb_registry(kb)
    before = _snapshot(kb)
    assert not (kb / ".memoria" / "cache").exists()  # 库内本无缓存：一旦写入就会被发现

    calls = [
        ToolCall(id="c1", name="search_kb", arguments=json.dumps({"query": "多层感知机", "top_k": 5})),
        ToolCall(id="c2", name="read_document", arguments=json.dumps({"path": "neural-network.md"})),
        ToolCall(id="c3", name="read_kp", arguments=json.dumps({"id": "mlp"})),
        ToolCall(id="c4", name="kb_overview", arguments="{}"),
        ToolCall(id="c5", name="validate_kb", arguments="{}"),
    ]
    results = [registry.invoke(call, approval=DefaultApprovalPolicy()) for call in calls]

    assert not any(result.is_error for result in results), [r.content for r in results if r.is_error]
    assert "neural-network.md:7" in results[0].content
    assert "neural-network.md:7" in results[2].content
    assert not (kb / ".memoria" / "cache").exists()
    assert not (kb / ".memoria" / "agent" / "sessions").exists()
    assert not (kb / ".memoria" / "manifest.yaml").exists()
    assert _snapshot(kb) == before


def test_read_document_rejects_path_escape(kb: Path) -> None:
    registry = kb_registry(kb)
    result = registry.invoke(ToolCall(id="c1", name="read_document", arguments='{"path": "../outside.md"}'))
    assert result.is_error and result.output.code == INVALID_ARGUMENTS_CODE


# —— 附：prompt 组装与端到端竖切 ——


def test_system_prompt_injects_kb_instructions_and_tools(kb: Path) -> None:
    registry = kb_registry(kb)
    prompt = build_system_prompt(str(kb), tools=registry.schemas(), model="fake-model")

    assert "kb-spec.zh-CN.md" in prompt
    assert "KP 只认 sidecar" in prompt
    assert "`search_kb`" in prompt and "`read_kp`" in prompt
    assert "文件相对路径:行号" in prompt
    assert "只读" in prompt


def test_system_prompt_gates_file_reference_section_on_read_tool(kb: Path) -> None:
    """`@路径` 引用说明与上游同门控：**任一读取手段在场**才出现。

    语义移植自 `context/file-reference`（上游 `ctx.tools.get('read') === undefined ? '' : ...`）：
    模型没有读取手段时，教它"去读"没有意义。2026-09-20 起本地读取手段有四个
    （`read_document` / `glob` / `grep` / `read_image`，见 `prompt.FILE_REFERENCE_TOOLS`）。
    """
    schemas = kb_registry(kb).schemas()
    with_read = build_system_prompt(str(kb), tools=schemas, model="m")
    assert "用户引用（`@路径`）" in with_read
    assert '@"..."' in with_read
    assert "不得声称已经看过" in with_read

    # 只剩 `glob`（读文档/检索/读图都不在场）⇒ 仍是"有读取手段"⇒ 注入
    only_glob = build_system_prompt(
        str(kb),
        tools=tuple(s for s in schemas if s.name in ("glob", "search_kb", "kb_overview")),
        model="m",
    )
    assert "用户引用（`@路径`）" in only_glob

    without_read = build_system_prompt(
        str(kb),
        tools=tuple(s for s in schemas if s.name not in FILE_REFERENCE_TOOLS),
        model="m",
    )
    assert "用户引用（`@路径`）" not in without_read


def test_ask_end_to_end_offline_only_writes_session(kb: Path) -> None:
    provider = FakeProvider(
        [
            tool_step(ToolCall(id="c1", name="search_kb", arguments=json.dumps({"query": "多层感知机"}))),
            text_step("多层感知机见 `neural-network.md:7`。"),
        ]
    )
    before = _snapshot(kb)

    result = ask(str(kb), "多层感知机在哪？", provider=provider, model="fake-model", session_id="session-test-0001")

    assert result.answer == "多层感知机见 `neural-network.md:7`。"
    assert result.stop_reason == "final-answer"
    assert result.iterations == 2
    assert result.session_path == str(kb / ".memoria" / "agent" / "sessions" / "session-test-0001.jsonl")
    assert any(anchor["file"] == "neural-network.md" and anchor["line"] == 7 for anchor in result.anchors)
    assert result.usage["total_tokens"] > 0
    assert [call["name"] for call in result.tool_calls] == ["search_kb"]
    # 工具结果摘要（2026-09-21）：`{is_error, code, message}` —— 前端靠它在气泡末尾显示"这次动作
    # 成没成"（真机：`propose_write` 撞 WinError 5 整批失败，而前端过去完全不渲染工具结果 ⇒
    # 人以为"agent 没有做出行动"）。
    assert result.tool_calls[0]["is_error"] is False
    assert "code" in result.tool_calls[0]  # 成功时多为 None，失败时是稳定 code（`WRITE_FAILED` 等）
    assert isinstance(result.tool_calls[0]["message"], str) and result.tool_calls[0]["message"]

    records = read_session(str(kb), "session-test-0001")
    types = [row["type"] for row in records]
    assert types[0] == "session/header"
    for expected in ("user/message", "step/start", "assistant/message", "tool/call", "tool/result", "loop/end"):
        assert expected in types, f"会话缺少事件：{expected}"

    after = _snapshot(kb)
    changed = {name for name, value in after.items() if before.get(name) != value}
    assert changed == {".memoria/agent/sessions/session-test-0001.jsonl"}
    assert set(after) - set(before) == {".memoria/agent/sessions/session-test-0001.jsonl"}


def test_ask_rejects_missing_kb(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ask(str(tmp_path / "nope"), "在吗？", provider=FakeProvider([]))


# —— 附：时间上下文（`context/time-context`，见 design/dsh-agent-port.md §6.14）——
# 本段用函数内 import：文件上半部的 `import` 段被 `<文件>:<行号>` 锚点占用（零行漂移，见 §6.14）。


def test_system_prompt_time_context_section_is_not_tool_gated(kb: Path) -> None:
    """时间上下文段**不**按工具门控：上游按「插件被挂载」启停（与 `FILE_REFERENCE_SECTION` 不同）。"""
    from memoria.services.agent.prompt import TIME_CONTEXT_SECTION

    schemas = kb_registry(kb).schemas()
    with_kb_tools = build_system_prompt(str(kb), tools=schemas, model="m")
    without_tools = build_system_prompt(str(kb), tools=(), model="m")

    assert TIME_CONTEXT_SECTION in with_kb_tools
    assert TIME_CONTEXT_SECTION in without_tools
    assert "## 时间上下文" in without_tools
    assert "先向用户澄清" in without_tools


def test_system_prompt_carries_no_dynamic_time_reading(kb: Path) -> None:
    """动态读数**不进** system 段：否则整段可复用前缀每轮变化，KV 缓存命中率归零。"""
    sent = build_system_prompt(str(kb), tools=kb_registry(kb).schemas(), model="m")
    assert "当前本地时间：" not in sent  # 读数前缀只由 render_time_context() 产出


def test_time_context_reading_uses_documented_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """冻结时钟：读数格式为 `当前本地时间：YYYY-MM-DDTHH:MM:SS±HH:MM`（上游 `formatTimestamp()` 字段口径）。"""
    import datetime

    from memoria.services.agent import prompt as prompt_module

    moment = datetime.datetime(
        2026, 9, 20, 9, 37, 33, tzinfo=datetime.timezone(datetime.timedelta(hours=8))
    )
    monkeypatch.setattr(prompt_module, "_local_now", lambda: moment)

    assert prompt_module.render_time_context() == "当前本地时间：2026-09-20T09:37:33+08:00"
    assert prompt_module.format_time_context(moment) == "2026-09-20T09:37:33+08:00"
    # 同一时刻重复渲染结果一致（读数不掺入任何隐藏状态）
    assert prompt_module.render_time_context(moment) == prompt_module.render_time_context()


def test_ask_appends_time_reading_to_request_only(kb: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """读数只进本轮请求：请求末尾有、system 段没有、会话 JSONL 里也没有（与 §6.12 偏差 1 同口径）。"""
    import datetime

    from memoria.services.agent import prompt as prompt_module

    moment = datetime.datetime(
        2026, 9, 20, 9, 37, 33, tzinfo=datetime.timezone(datetime.timedelta(hours=8))
    )
    monkeypatch.setattr(prompt_module, "_local_now", lambda: moment)
    provider = FakeProvider([text_step("好的。")])

    ask(str(kb), "现在几点？", provider=provider, model="fake-model", session_id="session-time-0001")

    sent = provider.requests[0].messages
    assert len(sent) == 1  # 无历史 ⇒ 请求里只有本轮提问（system 走 LlmRequest.system）
    assert sent[-1].content.endswith("当前本地时间：2026-09-20T09:37:33+08:00")
    assert "当前本地时间" not in (provider.requests[0].system or "")

    user_rows = [row for row in read_session(str(kb), "session-time-0001") if row["type"] == "user/message"]
    assert user_rows
    assert all("当前本地时间" not in row["data"]["text"] for row in user_rows)


# —— 附：模型切换告知（`core/agent` 的 model-selection，见 design/dsh-agent-port.md §6.15）——
# 本段同样用函数内 import：文件上半部的 `import` 段被 `<文件>:<行号>` 锚点占用（零行漂移）。

NOTICE_HEAD = "[模型已更换："


def test_render_model_change_notice_text() -> None:
    """告知文本逐字钉住（上游 `modelSwitchNotice()` 的中文落法）；同模型或缺一边 ⇒ 空串。"""
    from memoria.services.agent.prompt import MODEL_CHANGE_NOTICE, render_model_change_notice

    assert render_model_change_notice("m1", "m2") == (
        "[模型已更换：本轮之前的助手回复由 m1 生成；本会话此后由 m2 继续]"
    )
    assert MODEL_CHANGE_NOTICE.format(previous="m1", current="m2") == render_model_change_notice("m1", "m2")
    assert render_model_change_notice("m1", "m1") == ""
    assert render_model_change_notice("", "m2") == ""
    assert render_model_change_notice("m1", "") == ""
    assert render_model_change_notice("   ", "m2") == ""


def test_loop_end_records_model(kb: Path) -> None:
    """`loop/end` 记本轮模型（切换告知与成本归属的比对基准）。"""
    provider = FakeProvider([text_step("好的。")])

    ask(str(kb), "记一下模型", provider=provider, model="model-alpha", session_id="session-model-0001")

    ends = [row for row in read_session(str(kb), "session-model-0001") if row["type"] == "loop/end"]
    assert [row["data"]["model"] for row in ends] == ["model-alpha"]


def test_resuming_with_new_model_appends_notice_to_request_only(kb: Path) -> None:
    """续聊换模型：本轮请求里出现告知（两端模型名都在、排在时间读数之前），且**不进会话 JSONL**。"""
    ask(
        str(kb), "第一问", provider=FakeProvider([text_step("第一轮。")]),
        model="model-alpha", session_id="session-model-0002",
    )
    second = FakeProvider([text_step("第二轮。")])

    ask(str(kb), "第二问", provider=second, model="model-beta", session_id="session-model-0002")

    sent = second.requests[0].messages[-1].content
    assert NOTICE_HEAD in sent
    assert "model-alpha" in sent and "model-beta" in sent
    assert sent.startswith("第二问")  # 告知加在用户原文之后（本轮请求文本不动）
    assert sent.index("模型已更换") < sent.index("当前本地时间")  # 告知在前、读数在末尾（§6.14 位置不变）

    rows = read_session(str(kb), "session-model-0002")
    assert all("模型已更换" not in str(row.get("data")) for row in rows)
    questions = [row["data"]["text"] for row in rows if row["type"] == "user/message"]
    assert questions == ["第一问", "第二问"]  # 会话文件里仍是用户输入的原文


def test_resuming_with_same_model_adds_no_notice(kb: Path) -> None:
    """模型没换 ⇒ 不告知（上游：provider/model 未变则不加 notice），请求里紧跟用户原文。"""
    ask(
        str(kb), "第一问", provider=FakeProvider([text_step("第一轮。")]),
        model="model-alpha", session_id="session-model-0003",
    )
    second = FakeProvider([text_step("第二轮。")])

    ask(str(kb), "第二问", provider=second, model="model-alpha", session_id="session-model-0003")

    sent = second.requests[0].messages[-1].content
    assert not sent.startswith(NOTICE_HEAD)
    assert sent.startswith("第二问")


def test_notice_compares_with_latest_recorded_model(kb: Path) -> None:
    """比对基准是**最近一轮**的模型：a→b→a 时第三次仍要告知（上游比的是最近一次 selection）。"""
    sid = "session-model-0004"
    ask(str(kb), "一", provider=FakeProvider([text_step("A1")]), model="model-alpha", session_id=sid)
    ask(str(kb), "二", provider=FakeProvider([text_step("B1")]), model="model-beta", session_id=sid)
    third = FakeProvider([text_step("A2")])

    ask(str(kb), "三", provider=third, model="model-alpha", session_id=sid)

    sent = third.requests[0].messages[-1].content
    assert NOTICE_HEAD in sent
    assert "model-beta" in sent and "model-alpha" in sent


def test_no_notice_for_session_without_recorded_model(kb: Path) -> None:
    """老会话（本字段之前落盘）没有模型记录 ⇒ 按「未知」处理，不告知（fail-safe）。"""
    store = SessionStore(str(kb), "session-model-0005")
    store.append("user/message", {"text": "老会话的第一问"})
    store.append("loop/end", {"stop_reason": "final-answer"})  # 无 model 键 = 本字段之前落盘的老会话
    provider = FakeProvider([text_step("续聊。")])

    ask(str(kb), "接着问", provider=provider, model="model-beta", session_id="session-model-0005")

    sent = provider.requests[0].messages[-1].content
    assert not sent.startswith(NOTICE_HEAD)
    assert sent.startswith("接着问")


def test_no_notice_when_replay_disabled(kb: Path) -> None:
    """`replay=False`（显式关闭回放）⇒ 请求里没有历史，告知无对象，故不追加。"""
    sid = "session-model-0006"
    ask(str(kb), "一", provider=FakeProvider([text_step("A1")]), model="model-alpha", session_id=sid)
    provider = FakeProvider([text_step("A2")])

    ask(str(kb), "二", provider=provider, model="model-beta", session_id=sid, replay=False)

    assert len(provider.requests[0].messages) == 1
    assert not provider.requests[0].messages[-1].content.startswith(NOTICE_HEAD)


def test_tool_message_is_collapsed_and_capped() -> None:
    """轮询载荷里的 `tool_calls[].message`：空白折叠 + 截断 240 字（不把整篇工具输出塞进去）。

    它是前端把"这次动作到底成没成"显示出来的**唯一**素材（`{id, name, is_error, code, message}`）：
    真机失败原文形如 `写入**失败**（backup_failed）：[WinError 5] 拒绝访问。` —— 多行 + 末尾换行，
    前端要的是一行可读摘要。
    """
    from memoria.services.agent.ask import _tool_message

    assert _tool_message("写入**失败**（backup_failed）：\n[WinError 5] 拒绝访问。\n") == (
        "写入**失败**（backup_failed）： [WinError 5] 拒绝访问。"
    )
    assert _tool_message(None) == ""
    assert _tool_message("  \n ") == ""
    assert _tool_message("x" * 500) == "x" * 240


def test_manager_poll_streams_process_rows_incrementally(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """实时过程行（2026-09-22）：工作线程把循环事件折成 tool/step 行，`process_delta` 按游标增量投递。

    用**真** `AgentLoop` + 脚本 provider（第 1 步发一次工具调用、第 2 步发最终文本）驱动
    `AskJobManager` 的工作线程：断言 `process_delta` 依次出现 running / ok 工具行与两条 step 行，
    且 `process_cursor` 单调前进、游标到末尾后**不重放**。
    """
    import time
    from types import SimpleNamespace

    from memoria.services.agent import ask_stream
    from memoria.services.agent.tools import ToolOutput

    kb = tmp_path / "kb"
    kb.mkdir()
    arguments = json.dumps({"path": "notes/a.md"}, ensure_ascii=False)
    provider = FakeProvider(
        [tool_step(ToolCall(id="c1", name="read_document", arguments=arguments)), text_step("最终答案")]
    )
    registry = ToolRegistry(
        [
            Tool(
                name="read_document",
                description="读文件",
                parameters={"type": "object", "properties": {}},
                handler=lambda _a: ToolOutput(text="读到的正文"),
            )
        ]
    )

    def fake_ask(kb_path: str, question: str, **kwargs: Any) -> Any:
        """用真 `AgentLoop` 跑一轮（不联网、不落会话），把 `on_event` 原样接上。"""
        loop = AgentLoop(
            provider=provider,
            tools=registry,
            on_text=kwargs.get("on_text"),
            on_reasoning=kwargs.get("on_reasoning"),
            on_event=kwargs.get("on_event"),
        )
        result = loop.run(question)
        return SimpleNamespace(
            answer=result.answer,
            anchors=(),
            tool_calls=({"id": "c1", "name": "read_document", "is_error": False, "code": "ok", "message": "读到的正文"},),
            usage=result.usage_dict(),
            session_id="session-process-0001",
            stop_reason=result.stop_reason.value,
            iterations=result.iterations,
            error=result.error,
        )

    monkeypatch.setattr(ask_stream, "ask", fake_ask)
    manager = ask_stream.AskJobManager()
    started = manager.start(str(kb), "问题", env={"MEMORIA_AGENT_BASE_URL": "http://panel.example/v1"})
    assert started["status"] == "ok"

    rows: list[dict[str, Any]] = []
    cursor = 0
    snap: dict[str, Any] = {}
    for _ in range(400):
        snap = manager.poll(started["job_id"], 0, 0, cursor)
        rows.extend(snap["process_delta"])
        new_cursor = int(snap["process_cursor"])
        assert new_cursor >= cursor  # 游标单调前进
        cursor = new_cursor
        if snap["status"] != ask_stream.RUNNING:
            break
        time.sleep(0.005)

    assert snap["status"] == ask_stream.DONE
    assert [row["kind"] for row in rows] == ["step", "tool", "tool", "step"]
    assert rows[1]["state"] == "running" and rows[1]["id"] == "c1" and rows[1]["summary"] == "notes/a.md"
    assert rows[2]["state"] == "ok" and rows[2]["id"] == "c1"
    assert rows[3]["text"] == "最终答案" and rows[3]["tool_calls"] == 0
    # 最终 `tool_calls` 载荷补了可读摘要（来源 = `tool/call` 的 arguments），只增不改
    assert snap["tool_calls"][0]["summary"] == "notes/a.md"

    again = manager.poll(started["job_id"], 0, 0, cursor)
    assert again["process_delta"] == [] and again["process_cursor"] == cursor  # 游标到末尾 ⇒ 不重放


# ── `tool/call` 落盘位次（2026-09-22 对齐上游）──────────────────────────────────────────
# 上游 `agent-loop/src/tool-calls.ts:168` 的 `appendToolCall()` **先于** `:174` 的 `dispatch()`：
# **先记账，再干活**。本地原先是在工具**跑完之后**才写 ⇒ ① 崩在工具里就**没有任何调用记录**；
# ② `tool/call.time` 与 `tool/result.time` 背靠背写入 ⇒ 两者之差恒 ≈0，`toolMs` 读不到真值。


def _probe_loop(kb: Path, store: SessionStore, handler: Any) -> AgentLoop:
    """一个有会话的 loop：`on_event` 与 `ask._chained_event()` 同序（**先落盘、再回调**）。"""
    registry = ToolRegistry(
        [Tool(name="probe", description="探针", parameters={"type": "object"}, handler=handler)]
    )
    return AgentLoop(
        provider=FakeProvider([tool_step(ToolCall(id="c1", name="probe", arguments="{}")), text_step("完")]),
        tools=registry,
        model="fake-model",
        on_event=lambda event_type, data: store.append(event_type, data),
    )


def test_tool_call_is_logged_before_the_tool_runs(kb: Path) -> None:
    """判据是**在工具体内**读会话文件：那一刻 `tool/call` 必须已经在盘上。"""
    store = SessionStore(str(kb), "session-call-order")
    on_disk_when_running: list[list[str]] = []

    def handler(arguments: Mapping[str, Any]) -> ToolOutput:
        on_disk_when_running.append([row["type"] for row in store.events()])
        return ToolOutput(text="probe ok")

    _probe_loop(kb, store, handler).run("问")

    assert on_disk_when_running, "工具没被执行到，用例失效"
    running = on_disk_when_running[0]
    assert "tool/call" in running, "工具跑起来时 `tool/call` 还没落盘（先记账再干活）"
    assert "tool/result" not in running, "`tool/result` 不该在工具跑之前落盘"
    types = [row["type"] for row in store.events()]
    assert types.index("tool/call") < types.index("tool/result")


def test_tool_call_and_result_stay_paired_even_when_the_tool_raises(kb: Path) -> None:
    """配对不变量：`invoke()` 把异常也转成带错误文本的结果 ⇒ 两条事件照旧一一对应。"""
    store = SessionStore(str(kb), "session-call-order-raise")

    def handler(arguments: Mapping[str, Any]) -> ToolOutput:
        raise RuntimeError("内部炸了")

    result = _probe_loop(kb, store, handler).run("问")

    types = [row["type"] for row in store.events()]
    assert types.count("tool/call") == 1 and types.count("tool/result") == 1
    assert types.index("tool/call") < types.index("tool/result")
    assert [call.is_error for call in result.tool_calls] == [True]
