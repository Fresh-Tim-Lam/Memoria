# 语义移植自 deepseek-harness packages/compaction/compaction + packages/compaction/compaction-basic
# （MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""长会话压缩（M2）：把旧的对话区间摘成一份结构化 checkpoint 并替换进请求。

对照上游两处语义：

**1. `dsh-compaction`（接缝 / 不变量 / 工具配对）**

- 压缩是一次**表面替换**：被覆盖区间从表面消失，取而代之是一条携带摘要的 `user` 消息；
- **切割点必须工具配对平衡** —— 不得落在「assistant 的 `tool_calls` 与其 `tool` 结果」之间
  （上游 `tool-pairing.ts` 的 `toolPairingBalancedBefore`，用「未闭合工具调用数」折叠判定）；
- 摘要失败一律 **fail-closed**（上游 `finishError`：`error` / `aborted` / `max-tokens` 都算失败，
  不落地半份摘要）。

**2. `dsh-compaction-basic`（区域选择 + 摘要器）**

- 阈值与保留量是**上下文窗口的比例**：`thresholdRatio = 0.8`、`retainRatio = 0.16`，且不变量
  `retain < threshold`（上游 `config.ts:20-23,144-154`）；
- 摘要调用**把压缩指令作为「回放对话之后的最后一条 user 消息」下发**，而不是另开一个
  summarizer system prompt。上游给出理由（`summarizer.ts:24-30` 原文）：*"Keeping the
  conversation's own system prompt, tools, and message prefix in front of it makes the
  auxiliary call a genuine prefix of the last routed request, so the provider's KV cache is
  reused instead of invalidated."* 本地同构 —— 同一份 `system` + `tools` + 被覆盖区间消息，
  末尾才追加指令；
- 摘要固定 **8 段结构化 Markdown**、空段写 `(none)`、**已有旧 checkpoint 则合并而非照抄**；
- 替换消息用一段 preamble 框成「既成背景」（上游 `CHECKPOINT_PREAMBLE` + `<compacted-summary>`
  包裹，`frameSummary`）。

## 本地适配与偏差（已登记进 `docs/design/dsh-agent-port.md §6.8`）

- **没有「上下文窗口」概念**（本地配置无该字段、也不内嵌权重）：阈值与保留量改用同一组比例的
  **字符预算** —— `MAX_HISTORY_CHARS * 0.8` 触发、`* 0.16` 逐字保留；
- **落盘形态**：上游把摘要写进会话事件面（`compaction/summary` + 紧随其后的替换 `user/message`）；
  本地在会话 JSONL 追加**一条** `compaction` 事件（`shadowed` = 被覆盖的 `seq` 列表），由
  `history.build_history()` 回放时在原位置出摘要。**不移植**上游的 start/end 事务锁 —— 那是为
  多写者并发准备的，本地是单写者 + 仅追加；
- **本地新增两条下限**：一次压缩至少覆盖 `MIN_SPAN_CHARS` 字符，且区间内至少含一条
  `user/message`（否则不值得一次模型调用）。上游无对应项；
- 未移植 `compaction-image-offload`（本地无图片）、`command-compact`（slash 命令，M1 已定不做）；
  `compaction-tool-result-pruner` 已另行落为 `services/agent/pruner.py`（免模型的旧工具输出裁剪），
  由 `ask._compact_if_needed()` 在**选区间之前**先跑，故本模块只按传入的**有效字符表**计账。

## 不写盘

本模块**不写盘**：压缩结果由调用方（`ask.py`）经 `SessionStore.append()` 落盘；本模块唯一的
副作用是一次**模型调用**（`summarize_span()`）。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from memoria.services.agent.llm import (
    FinishEvent,
    FinishReason,
    LlmRequest,
    Message,
    RetryPolicy,
    Role,
    TextDelta,
    ToolSchema,
    Usage,
    UsageEvent,
    iter_with_retry,
)
from memoria.services.agent.loop import CancelToken
from memoria.services.agent.session.history import (
    ASSISTANT_MESSAGE,
    COMPACTION,
    MAX_HISTORY_CHARS,
    TOOL_RESULT,
    USER_MESSAGE,
)

logger = logging.getLogger(__name__)

__all__ = [
    "CHECKPOINT_PREAMBLE",
    "COMPACTION_INSTRUCTION",
    "COMPACT_THRESHOLD_RATIO",
    "CompactionError",
    "MIN_SPAN_CHARS",
    "RETAIN_RATIO",
    "SUMMARY_CLOSE_TAG",
    "SUMMARY_MAX_TOKENS",
    "SUMMARY_OPEN_TAG",
    "SUMMARY_RETRY_POLICY",
    "SummaryCall",
    "balanced_cuts",
    "compact_threshold_chars",
    "event_chars",
    "frame_summary",
    "retain_chars",
    "select_span",
    "summarize_span",
]

#: 触发压缩的字符预算比例（对齐上游 `DEFAULT_THRESHOLD_RATIO`）。
COMPACT_THRESHOLD_RATIO = 0.8
#: 逐字保留的最新尾部比例（对齐上游 `DEFAULT_RETAIN_RATIO`）。
RETAIN_RATIO = 0.16
#: 一次压缩最少要覆盖的字符数（**本地新增**：太少则不值得一次模型调用）。
MIN_SPAN_CHARS = 2_000
#: 摘要调用的生成上限（对齐上游 `maxTokens` 默认值 8192）。
SUMMARY_MAX_TOKENS = 8_192

#: 摘要调用的重试策略（对齐上游 `compactionRetries` 默认 1；总时限收紧到 60s）。
SUMMARY_RETRY_POLICY = RetryPolicy(max_retries=1, total_timeout_s=60.0)

#: 摘要在 checkpoint 里的包裹标记（对齐上游 `SUMMARY_OPEN_TAG` / `SUMMARY_CLOSE_TAG`）。
SUMMARY_OPEN_TAG = "<compacted-summary>"
SUMMARY_CLOSE_TAG = "</compacted-summary>"

#: 替换消息的框定语（上游 `CHECKPOINT_PREAMBLE` 的语义落法：让模型当作既成背景、不要复述、
#: 不要提及这份 checkpoint）。
CHECKPOINT_PREAMBLE = (
    "以下是自动生成的 checkpoint，用于压缩早前的对话以腾出上下文。"
    "把其中的内容当作**既成背景**直接沿用，不要复述；"
    "从后面的消息继续任务，不要提及或确认这份 checkpoint。"
)

#: 摘要指令。上游原文（`compaction-basic/src/summarizer.ts:31-66`）是英文固定 8 段骨架；
#: 本地按仓库口径**落为中文**（对话本身是中文），但**段名与顺序、以及四条规则一条不少**：
#: 逐字保留确切路径/命令/错误串/标识符/数值/签名、忠实记录用户纠正、不得提及本次压缩、
#: 只输出正文且不调用工具、遇到旧 `<compacted-summary>` 要**合并**而不是照抄。
COMPACTION_INSTRUCTION = "\n".join(
    [
        "你现在充当这次对话的压缩引擎。把**上面的对话**浓缩成一份结构化 checkpoint，",
        "让另一个模型能在不丢失关键上下文的前提下接着干。",
        "",
        "严格按下面的 Markdown 结构输出，**每一节都要在、顺序不变**；用简短的项目符号，不要散文段落；",
        "某一节为空就写 `(none)`，**绝不省略节**。",
        "",
        "## 用户的原始诉求与意图演变",
        "- [用户最初与后来的目标；措辞本身重要时逐字引用]",
        "",
        "## 关键概念",
        "- [涉及的术语、约定、格式、算法]",
        "",
        "## 文件与内容",
        "- [确切路径：为什么相关、关键改动或片段]",
        "",
        "## 错误与修法",
        "- [错误：如何解决，以及相关的用户反馈]",
        "",
        "## 待办",
        "- [用户明确要求但尚未完成的]",
        "",
        "## 当前进展",
        "- [生成这份 checkpoint 时正在进行的事]",
        "",
        "## 下一步",
        "- [与最近一次请求直接对齐的**单个**下一步动作；没有就写 `(none)`]",
        "",
        "## 关键上下文",
        "- [决定及其理由、约束、用户偏好、未决问题、继续所需的数据]",
        "",
        "规则：",
        "- 写简洁的工程化中文。**原样保留**确切的路径、命令、错误串、标识符、数值、函数签名与语法片段。",
        "- 忠实记录用户的反馈与明确指示，尤其是**纠正**。",
        "- **不要提及这次压缩请求**，也不要提到上下文被压缩过。",
        "- 只输出 checkpoint 正文：不要调用任何工具，不要做其它动作。",
        f"- 如果上面的对话里已经含有一个 {SUMMARY_OPEN_TAG} 区块，那是**先前的 checkpoint**："
        "不要照抄，保留仍然成立的事实、丢掉过时的，把新信息并进同一份骨架。",
    ]
)


class CompactionError(RuntimeError):
    """压缩失败。fail-closed 语义：宁可**不压缩**，也不落地半份摘要。"""


@dataclass(frozen=True, slots=True)
class SummaryCall:
    """一次摘要调用的结果（`text` 落盘，`model` / `usage` 随事件留档）。"""

    text: str
    model: str
    usage: Usage | None = None


def compact_threshold_chars(max_chars: int = MAX_HISTORY_CHARS) -> int:
    """触发压缩的字符阈值（`max_chars * COMPACT_THRESHOLD_RATIO`）。"""
    return int(max(0, max_chars) * COMPACT_THRESHOLD_RATIO)


def retain_chars(max_chars: int = MAX_HISTORY_CHARS) -> int:
    """逐字保留的最新尾部字符数（`max_chars * RETAIN_RATIO`）。

    与 `compact_threshold_chars()` 满足上游不变量 `retain < threshold`（0.16 < 0.8）。
    """
    return int(max(0, max_chars) * RETAIN_RATIO)


def frame_summary(summary: str) -> str:
    """把摘要包成替换消息的正文（上游 `frameSummary`）。"""
    body = (summary or "").strip()
    return f"{CHECKPOINT_PREAMBLE}\n\n{SUMMARY_OPEN_TAG}\n{body}\n{SUMMARY_CLOSE_TAG}"


def _data(event: Mapping[str, Any]) -> Mapping[str, Any]:
    value = event.get("data")
    return value if isinstance(value, Mapping) else {}


def _tool_calls_of(event: Mapping[str, Any]) -> Sequence[Any]:
    calls = _data(event).get("tool_calls")
    if isinstance(calls, Sequence) and not isinstance(calls, (str, bytes)):
        return calls
    return ()


def event_chars(
    event: Mapping[str, Any],
    *,
    effective_chars: Mapping[int, int] | None = None,
) -> int:
    """该事件**回放后**的字符成本（与 `history._replay` 的口径一致）。

    `tool/call` 与 `step/*` / `loop/*` 都不进消息序列，故计 0；`compaction` 事件按其摘要正文计。

    `effective_chars`（可选）：`seq -> 有效字符数` 的**覆盖表**。被 `compaction/prune` 裁过的
    工具结果在日志里仍是原文，只有回放视图变短 ⇒ 区域选择必须按**有效视图**计量，否则会高估
    尾部大小、把本可逐字保留的轮次也压掉（见 §6.10）。
    """
    if effective_chars:
        seq = event.get("seq")
        if isinstance(seq, int) and seq in effective_chars:
            return int(effective_chars[seq])
    data = _data(event)
    kind = event.get("type")
    if kind == USER_MESSAGE:
        return len(str(data.get("text") or ""))
    if kind == ASSISTANT_MESSAGE:
        total = len(str(data.get("content") or ""))
        for call in _tool_calls_of(event):
            if isinstance(call, Mapping):
                total += len(str(call.get("arguments") or "")) + len(str(call.get("name") or ""))
        return total
    if kind == TOOL_RESULT:
        return len(str(data.get("content") or ""))
    if kind == COMPACTION:
        return len(str(data.get("summary") or ""))
    return 0


def balanced_cuts(events: Sequence[Mapping[str, Any]]) -> list[bool]:
    """`out[i]` = 「在 `events[i]` **之前**切割」是否工具配对平衡。

    对齐上游 `tool-pairing.ts` 的 `toolPairingBalancedBefore`：折叠「未闭合的工具调用数」，
    仅当为 0 时该切割点平衡。折叠在**原始日志**上进行 —— 我们只压平衡区间，故有效视图的
    平衡性与原始日志一致（见模块 docstring 的适配说明）。
    """
    out = [True]
    pending = 0
    for event in events:
        kind = event.get("type")
        if kind == ASSISTANT_MESSAGE:
            pending += len(_tool_calls_of(event))
        elif kind == TOOL_RESULT:
            pending -= 1
        out.append(pending == 0)
    return out


def select_span(
    events: Sequence[Mapping[str, Any]],
    *,
    max_chars: int = MAX_HISTORY_CHARS,
    effective_chars: Mapping[int, int] | None = None,
) -> tuple[int, int] | None:
    """选出**要被摘要覆盖**的事件下标区间 `[start, end)`；无可压区间则 `None`。

    规则（对齐上游区域选择的可观察语义 + 两条本地下限）：

    1. 尾部逐字保留：切割点**之后**的部分字符数不得少于 `retain_chars(max_chars)`；
    2. 切割点必须**工具配对平衡**（`balanced_cuts`）；
    3. 满足上两条时**尽量多压**（取最靠后的合法切割点）；
    4. 本地下限：被覆盖区间至少 `MIN_SPAN_CHARS` 字符，且至少含一条 `user/message`。

    区间恒为**前缀**（`start == 0`）—— 被压缩的总是最旧的那一段，摘要在回放时出现在最前。
    `effective_chars` 见 `event_chars()`（裁剪后的工具结果按有效字符数计账）。
    """
    total = len(events)
    if total == 0:
        return None
    keep = retain_chars(max_chars)
    cuts = balanced_cuts(events)
    prefix = [0] * (total + 1)
    for index, event in enumerate(events):
        prefix[index + 1] = prefix[index] + event_chars(event, effective_chars=effective_chars)
    total_chars = prefix[total]
    best: int | None = None
    for end in range(1, total + 1):
        if not cuts[end]:
            continue
        if total_chars - prefix[end] < keep:
            continue
        if prefix[end] < MIN_SPAN_CHARS:
            continue
        best = end
    if best is None:
        return None
    if not any(events[index].get("type") == USER_MESSAGE for index in range(best)):
        return None
    return (0, best)


def summarize_span(
    provider: Any,
    messages: Sequence[Message],
    *,
    system: str | None = None,
    tools: Sequence[ToolSchema] = (),
    model: str = "",
    max_tokens: int = SUMMARY_MAX_TOKENS,
    timeout_s: float | None = None,
    retry_policy: RetryPolicy | None = None,
    cancel: CancelToken | None = None,
) -> SummaryCall:
    """跑一次**一次性**摘要调用；任何异常路径都抛 `CompactionError`（fail-closed）。

    请求形状与普通回合一致（同一份 `system` + `tools` + 被覆盖区间的消息），只在末尾追加
    `COMPACTION_INSTRUCTION` 作为最后一条 `user` 消息 —— 为的是复用 provider 的 KV 前缀缓存
    （理由见模块 docstring 与上游 `summarizer.ts:24-30`）。

    失败判据对齐上游 `finishError` + 本地补充：无终止事件 / `error` / `aborted` /
    `max-tokens`（checkpoint 不完整）/ 返回了工具调用 / 正文为空。
    """
    request = LlmRequest(
        model=model,
        messages=tuple(messages) + (Message(role=Role.USER, content=COMPACTION_INSTRUCTION),),
        system=system,
        max_tokens=max_tokens,
        tools=tuple(tools),
        stream=True,
        timeout_s=timeout_s,
    )
    parts: list[str] = []
    usage: Usage | None = None
    finish: FinishEvent | None = None
    stream = iter_with_retry(
        lambda: provider.stream(request),
        policy=retry_policy if retry_policy is not None else SUMMARY_RETRY_POLICY,
    )
    try:
        for event in stream:
            if cancel is not None and cancel.is_cancelled():
                raise CompactionError("压缩被取消")
            if isinstance(event, TextDelta):
                parts.append(event.text)
            elif isinstance(event, UsageEvent):
                usage = event.usage
            elif isinstance(event, FinishEvent):
                finish = event
    finally:
        # 与循环的取消路径同理：显式关掉生成器才会关闭底层 HTTP 响应
        closer = getattr(stream, "close", None)
        if closer is not None:
            closer()

    if finish is None:
        raise CompactionError("摘要调用未返回终止事件")
    reason = finish.reason
    if reason in (FinishReason.ERROR, FinishReason.ABORTED):
        detail = finish.failure
        raise CompactionError(f"摘要调用失败：{detail if detail is not None else reason.value}")
    if reason is FinishReason.MAX_TOKENS:
        raise CompactionError("摘要在生成上限处被截断（checkpoint 不完整）")
    if finish.tool_calls:
        raise CompactionError("摘要调用返回了工具调用，不是 checkpoint 正文")
    text = "".join(parts).strip()
    if not text:
        raise CompactionError("摘要调用没有产出正文")
    return SummaryCall(text=text, model=model, usage=usage if usage is not None else finish.usage)
