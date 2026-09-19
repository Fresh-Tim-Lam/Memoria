# 语义移植自 deepseek-harness packages/session/session-title（规范化 / 折叠 / 兜底）、
# packages/session/session-title-llm（共享调用策略）与
# packages/session/session-title-first-prompt-llm（首条消息选材）（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""会话标题（M2）：log-only 的 `session/title` 事件 + 确定性兜底 + 首轮一次模型标题。

对照上游的可观察语义：

**1. 来源与「最新者胜」** —— 标题有三个来源，**后写的覆盖先写的**：

| 来源 | 何时产生 | 成本 |
|---|---|---|
| `fallback`（确定性兜底） | 会话还没有标题、且已有 ≥ 1 条合格人类消息时**自动**补一条 | **零模型调用、零网络** |
| `provider`（模型标题） | `first-prompt` 节律：会话里**恰好一条**合格人类消息时生成一次 | 一次**极小**的辅助调用 |
| `user`（用户改名） | 用户显式改名（本地**未移植**，见下） | — |

**2. 合格消息**：只有**人类** `user/message` 且其文本**规范化后非空**才算（空白/纯控制字符的提问要等后面的）。

**3. 规范化**（上游 `normalize.ts`）：先去掉终端控制序列（OSC / CSI / 其余 ESC 两字节序列）、非空白
C0/C1 控制字符、以及**方向与隐形控制字符**（它们能让标题看起来与实际不符），再把空白折叠成单个空格并
首尾去空白，最后按 **UTF-8 字节**上限截断（**不切开码点**）。限额：兜底 **8 词 / 96 字节**，任何来源
**120 字节**。

**4. log-only**：`session/title` **绝不进模型输入** —— 回放（`history._replay`）对未知 type 直接跳过，
`compaction.event_chars()` 计 0，`session/query.py` 的语义抽取也不含它。故标题既不改请求体、也不动
KV 前缀。

## 本地适配与偏差（登记进 `docs/design/dsh-agent-port.md §6.11`）

- **没有异步服务**：上游是常驻服务（`SessionTitleService`），自动生成**从不阻塞主回答**，并用
  `AbortController` 处理取代/超时/生命周期。本地 `ask()` 是**同步**调用面 ⇒ 标题调用排在**主回合之后**
  （`loop/end` 已落盘），且 **fail-open**（失败只记 warning，绝不影响问答）。**代价**：面板的 `done` 会晚
  一个极小辅助调用的时间，**仅每会话首轮一次**；**被取消的那一轮不生成标题**（本地新增 —— 用户已喊停，
  不再多花一次调用）。
- **只吃 `first-prompt`**：不吃 `session-title-all-prompts-llm`（每来一句就重算一次标题 —— 本地方针是
  "能省则省"，不值得每轮多一次调用）。故也不做上游那层「provider 注册表 + automatic 节律」抽象，
  只有一条内联路径。
- **不吃 `rename()`**（`source.kind == "user"`）：本地没有改名入口。事件形状保留 `source` 字段，
  折叠时**不解释**它（任何 `session/title` 都算、最新者胜）⇒ 将来接改名 UI 无需改回放。
- **不吃 `session/title-llm-request` 预派发记录**：上游用它自证"这次辅助调用的路由与已记录的主请求路由
  一致"（本地路由就是本轮的 provider/model，无需自证）。
- **不移植投影框架**：上游把标题注册为 `sessionProjections` 的 `title` / `titleInput` 两个单元；本地直接
  **折叠**（`fold_title()` = 取最后一条 `session/title`），会话列表用**原始行扫描**取它（见 `history.py`）。
- **限额取值**：上游三个限额**必填、库内无默认**；本地取它 README 示例里的 8 / 96 / 120。共享调用策略里
  的"目标长度"上游同样必填，本地取值 `TITLE_TARGET_WORDS = 6` / `TITLE_TARGET_CJK_CHARS = 12`。
- **不做 `message_seqs` 的全部校验**：上游要求 seq 唯一、有序、且来自本次请求；本地由**自己的选材函数**
  产出（即 `collect_title_messages()` 的子集），故只做形状断言。

## 网络与写盘

`generate_title()` 会**调用模型端点一次**（辅助调用）；`ensure_fallback()` / `fold_title()` 不联网、不写盘。
落盘只有 `SessionStore.append()`（由本模块显式调用）。
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from memoria.services.agent.llm import (
    AgentLlmError,
    FinishEvent,
    FinishReason,
    LlmRequest,
    Message,
    RetryPolicy,
    Role,
    TextDelta,
    Usage,
    UsageEvent,
    iter_with_retry,
)
from memoria.services.agent.loop import CancelToken, usage_payload
from memoria.services.agent.session.store import SessionStore

logger = logging.getLogger(__name__)

__all__ = [
    "SESSION_TITLE",
    "TITLE_FALLBACK_MAX_BYTES",
    "TITLE_FALLBACK_MAX_WORDS",
    "TITLE_MAX_BYTES",
    "TitleCall",
    "TitleError",
    "TitleMessage",
    "TitleSnapshot",
    "auto_title",
    "clean_title_text",
    "collect_title_messages",
    "ensure_fallback",
    "fallback_title",
    "fold_title",
    "frame_messages",
    "generate_title",
    "normalize_title",
    "title_message",
    "title_system_prompt",
    "truncate_title_utf8",
]

#: 承载标题的会话事件类型（对齐上游 `session/title`；**log-only**，永不进模型输入）。
SESSION_TITLE = "session/title"

#: 兜底标题的 whitespace 分词上限（上游 `fallbackMaxWords`；本地取它 README 示例值）。
TITLE_FALLBACK_MAX_WORDS = 8
#: 兜底标题的 UTF-8 字节上限（上游 `fallbackMaxBytes`）。
TITLE_FALLBACK_MAX_BYTES = 96
#: **任何来源**的标题的 UTF-8 字节上限（上游 `maxTitleBytes`）。
TITLE_MAX_BYTES = 120
#: 模型标题的目标长度（上游共享调用策略的 `targetWords` / `targetCjkCharacters`，本地取值）。
TITLE_TARGET_WORDS = 6
TITLE_TARGET_CJK_CHARS = 12
#: 辅助调用的**输入**字节上限（上游 `maxInputBytes`，超出即拒绝，不截断）。
TITLE_MAX_INPUT_BYTES = 32_768
#: 辅助调用的**输出** token 上限（上游 `maxOutputTokens`：标题很短，给足即可）。
TITLE_MAX_OUTPUT_TOKENS = 96
#: 辅助调用的端到端超时与重试策略（上游 `timeoutMs` + 一次重试）。
TITLE_TIMEOUT_S = 20.0
TITLE_RETRY_POLICY = RetryPolicy(max_retries=1, total_timeout_s=TITLE_TIMEOUT_S)

#: 本地会话事件里人类提问的类型（与 `history.USER_MESSAGE` 同值；此处写字面量以避免反向依赖）。
_USER_MESSAGE = "user/message"

# —— 控制序列与隐形字符（上游 `normalize.ts` 的同名模式）——

#: 操作系统命令序列（含未终结的尾巴）。
_OSC_SEQUENCE = re.compile(r"(?:\x1b\]|\x9d)(?:(?!\x07|\x1b\\)[\s\S])*(?:\x07|\x1b\\|$)")
#: 控制序列引导符转义（如 SGR 颜色码）。
_CSI_SEQUENCE = re.compile(r"(?:\x1b\[|\x9b)[0-?]*[ -/]*[@-~]")
#: 其余两字节 ESC 控制序列。
_ESC_SEQUENCE = re.compile(r"\x1b[@-_]")
#: 非空白 C0/C1 控制字符。
_CONTROL_CHARACTER = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
#: 方向与隐形控制字符（可让显示出来的标题具有误导性）。
_DIRECTIONAL_CONTROL = re.compile(
    r"[\u200b\u200e\u200f\u202a-\u202e\u2060-\u2064\u2066-\u206f\ufeff]"
)


class TitleError(RuntimeError):
    """标题生成失败（fail-closed：宁可**不落标题**，也不落一个可疑标题）。"""


@dataclass(frozen=True, slots=True)
class TitleMessage:
    """一条**合格**的人类消息（对应上游 `SessionTitleUserMessage`）。"""

    seq: int
    text: str


@dataclass(frozen=True, slots=True)
class TitleSnapshot:
    """折叠出的最新标题（对应上游 `SessionTitleSnapshot`）。"""

    title: str
    message_seqs: tuple[int, ...]
    source: str
    event_seq: int
    updated_at: int


@dataclass(frozen=True, slots=True)
class TitleCall:
    """一次模型标题调用的结果。"""

    title: str
    model: str
    usage: Usage | None


def clean_title_text(text: str) -> str:
    """去控制序列与隐形字符，并折叠成**一行**去空白文本（上游 `cleanTitleText`）。"""
    out = str(text or "")
    for pattern in (
        _OSC_SEQUENCE,
        _CSI_SEQUENCE,
        _ESC_SEQUENCE,
        _CONTROL_CHARACTER,
        _DIRECTIONAL_CONTROL,
    ):
        out = pattern.sub("", out)
    return re.sub(r"\s+", " ", out).strip()


def truncate_title_utf8(text: str, max_bytes: int) -> str:
    """按 **UTF-8 字节**预算截断，**绝不切开码点**（上游 `truncateTitleUtf8`）。"""
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0:
        raise TitleError(f"标题字节上限必须是正整数（收到 {max_bytes!r}）")
    if len(text.encode("utf-8")) <= max_bytes:
        return text
    used = 0
    parts: list[str] = []
    for char in text:
        size = len(char.encode("utf-8"))
        if used + size > max_bytes:
            break
        parts.append(char)
        used += size
    return "".join(parts)


def normalize_title(text: str, *, max_bytes: int = TITLE_MAX_BYTES) -> str:
    """规范化一条待接受的标题，并施加 UTF-8 字节上限（上游 `normalizeSessionTitle`）。"""
    return truncate_title_utf8(clean_title_text(text), max_bytes).rstrip()


def fallback_title(
    text: str,
    *,
    max_words: int = TITLE_FALLBACK_MAX_WORDS,
    max_bytes: int = TITLE_FALLBACK_MAX_BYTES,
) -> str:
    """由首条合格人类消息派生的**确定性**兜底标题（上游 `fallbackSessionTitle`）。"""
    words = [word for word in clean_title_text(text).split(" ") if word][:max_words]
    return truncate_title_utf8(" ".join(words), max_bytes).rstrip()


def _data(event: Mapping[str, Any]) -> Mapping[str, Any]:
    value = event.get("data")
    return value if isinstance(value, Mapping) else {}


def title_message(event: Mapping[str, Any]) -> TitleMessage | None:
    """抽取一条**合格**人类消息；不合格（非 `user/message`、或规范化后为空）返回 `None`。

    上限传一个足够大的值：资格判据看的是"是否有可见内容"，与最终标题的字节上限无关（同上游）。
    """
    if event.get("type") != _USER_MESSAGE:
        return None
    seq = event.get("seq")
    if not isinstance(seq, int):
        return None
    text = str(_data(event).get("text") or "")
    if not normalize_title(text, max_bytes=1 << 30):
        return None
    return TitleMessage(seq=seq, text=text)


def collect_title_messages(
    events: Sequence[Mapping[str, Any]],
    *,
    through_seq: int | None = None,
) -> tuple[TitleMessage, ...]:
    """按 seq 顺序收集合格人类消息；`through_seq` 为**闭区间**上界（上游同语义）。"""
    out: list[TitleMessage] = []
    for event in events:
        seq = event.get("seq")
        if through_seq is not None and isinstance(seq, int) and seq > through_seq:
            break
        message = title_message(event)
        if message is not None:
            out.append(message)
    return tuple(out)


def fold_title(events: Sequence[Mapping[str, Any]]) -> TitleSnapshot | None:
    """折叠出**最新**标题（= 最后一条**非空** `session/title`）；没有则 `None`（上游 `foldSessionTitle`）。

    「非空」这一层是本地加固：空标题记录**视作没有**（fail-safe —— 宁可继续用前一条有效标题，
    也不要显示空标题；与 `history.summarize_session_file()` 的原始行扫描**同口径**）。
    """
    latest: Mapping[str, Any] | None = None
    for event in events:
        if event.get("type") != SESSION_TITLE:
            continue
        if not str(_data(event).get("title") or ""):
            continue
        latest = event
    if latest is None:
        return None
    data = _data(latest)
    title = str(data.get("title") or "")
    raw_seqs = data.get("message_seqs")
    seqs = (
        tuple(seq for seq in raw_seqs if isinstance(seq, int))
        if isinstance(raw_seqs, Sequence) and not isinstance(raw_seqs, (str, bytes))
        else ()
    )
    source = data.get("source")
    kind = str(source.get("kind") or "") if isinstance(source, Mapping) else ""
    return TitleSnapshot(
        title=title,
        message_seqs=seqs,
        source=kind,
        event_seq=int(latest.get("seq") or 0),
        updated_at=int(latest.get("time") or 0),
    )


def _append(
    session: SessionStore,
    *,
    title: str,
    message_seqs: Sequence[int],
    source: Mapping[str, Any],
    usage: Usage | None = None,
) -> None:
    """落一条 `session/title`；`usage`（可选）是**这次标题调用**的用量，形状同 `loop/end.usage`。

    **本地扩展**：上游的标题事件不带用量。记下来便于事后核对"标题这一小块花了多少"，
    且与 `compaction.usage` 同口径（也**同样不进** benchmark —— 报告只扫 `loop/end`）。
    """
    data: dict[str, Any] = {
        "title": title,
        "message_seqs": list(message_seqs),
        "source": dict(source),
    }
    if usage is not None:
        data["usage"] = usage_payload(usage)
    session.append(SESSION_TITLE, data)


def ensure_fallback(session: SessionStore, events: Sequence[Mapping[str, Any]]) -> bool:
    """会话**还没有标题**时，按首条合格人类消息落一条 `fallback` 标题。

    零模型调用、零网络；派生不出（首条消息过滤后为空）则不落。返回是否真的落了事件。
    """
    if fold_title(events) is not None:
        return False
    first = next(iter(collect_title_messages(events)), None)
    if first is None:
        return False
    title = fallback_title(first.text)
    if not title:
        return False
    _append(session, title=title, message_seqs=[first.seq], source={"kind": "fallback"})
    return True


def title_system_prompt() -> str:
    """标题辅助调用的系统提示（上游共享调用策略的 `systemPrompt`，中文落法）。"""
    return "\n".join(
        [
            "为一段 AI 助手会话起一个简洁标题。",
            "只输出标题本身（一行纯文本、自然语言），不要引号、前缀、解释、Markdown、XML 或终端控制字符；不要输出代码。",
            "使用消息所用的语言。",
            f"非中日韩文字约 {TITLE_TARGET_WORDS} 个词，中日韩文字约 {TITLE_TARGET_CJK_CHARS} 个字。",
        ]
    )


def frame_messages(messages: Sequence[TitleMessage]) -> str:
    """把选材消息**框成 JSON**，使提问正文无法破坏结构分隔（上游 `frameMessages`）。"""
    payload = json.dumps(
        [{"seq": message.seq, "text": message.text} for message in messages],
        ensure_ascii=False,
    )
    return f"根据这个 JSON 数组里的人类消息生成会话标题：\n{payload}"


def generate_title(
    provider: Any,
    messages: Sequence[TitleMessage],
    *,
    model: str = "",
    system: str | None = None,
    max_input_bytes: int = TITLE_MAX_INPUT_BYTES,
    max_output_tokens: int = TITLE_MAX_OUTPUT_TOKENS,
    timeout_s: float | None = None,
    retry_policy: RetryPolicy | None = None,
    cancel: CancelToken | None = None,
) -> TitleCall:
    """跑一次**一次性**标题调用；任何异常路径都抛 `TitleError`（fail-closed）。

    请求形状：**同一份 system** + **一条 `user` 消息**（框成 JSON 的选材消息），不带工具。
    失败判据对齐上游 `finishError`：无终止事件 / `error` / `aborted` / `max-tokens` / 返回工具调用 /
    **其它非 `stop` 的终止原因**（含 `content-filter`）/ 正文规范化后为空。

    与 `compaction.summarize_span()` 是**同构的采集循环**，但请求形状与 system 都不同，故不共用实现。
    """
    if not messages:
        raise TitleError("标题调用至少需要一条源消息")
    framed = frame_messages(messages)
    if len(framed.encode("utf-8")) > max_input_bytes:
        raise TitleError(f"标题输入超过上限（{len(framed.encode('utf-8'))} > {max_input_bytes} 字节）")
    request = LlmRequest(
        model=model,
        messages=(Message(role=Role.USER, content=framed),),
        system=system if system is not None else title_system_prompt(),
        max_tokens=max_output_tokens,
        stream=True,
        timeout_s=timeout_s,
    )
    parts: list[str] = []
    usage: Usage | None = None
    finish: FinishEvent | None = None
    stream = iter_with_retry(
        lambda: provider.stream(request),
        policy=retry_policy if retry_policy is not None else TITLE_RETRY_POLICY,
    )
    try:
        for event in stream:
            if cancel is not None and cancel.is_cancelled():
                raise TitleError("标题生成被取消")
            if isinstance(event, TextDelta):
                parts.append(event.text)
            elif isinstance(event, UsageEvent):
                usage = event.usage
            elif isinstance(event, FinishEvent):
                finish = event
    except AgentLlmError as exc:
        raise TitleError(f"标题调用失败：{exc}") from exc
    finally:
        # 与循环/压缩的取消路径同理：显式关掉生成器才会关闭底层 HTTP 响应
        closer = getattr(stream, "close", None)
        if closer is not None:
            closer()

    if finish is None:
        raise TitleError("标题调用未返回终止事件")
    reason = finish.reason
    if reason in (FinishReason.ERROR, FinishReason.ABORTED):
        detail = finish.failure
        raise TitleError(f"标题调用失败：{detail if detail is not None else reason.value}")
    if reason is FinishReason.MAX_TOKENS:
        raise TitleError("标题在输出上限处被截断")
    if finish.tool_calls:
        raise TitleError("标题调用返回了工具调用，不是标题正文")
    if reason is not FinishReason.STOP:
        raise TitleError(f"标题调用以非预期原因结束：{reason.value}")
    title = normalize_title("".join(parts))
    if not title:
        raise TitleError("标题调用没有产出可见正文")
    return TitleCall(title=title, model=model, usage=usage if usage is not None else finish.usage)


def auto_title(
    session: SessionStore,
    events: Sequence[Mapping[str, Any]],
    *,
    provider: Any,
    model: str = "",
    timeout_s: float | None = None,
    retry_policy: RetryPolicy | None = None,
    cancel: CancelToken | None = None,
) -> TitleCall | None:
    """`first-prompt` 节律的自动标题：会话里**恰好一条**合格人类消息时生成并落一条 `provider` 标题。

    返回 `None` 表示**节律未命中**（不是失败）—— 第 2 轮起不再重算，对齐上游
    `automatic === 'first-prompt'` 的调度条件（`count === 1`）；本地无改名，故不需要"用户标题钉住"分支。
    """
    messages = collect_title_messages(events)
    if len(messages) != 1:
        return None
    call = generate_title(
        provider,
        messages,
        model=model,
        timeout_s=timeout_s,
        retry_policy=retry_policy,
        cancel=cancel,
    )
    _append(
        session,
        title=call.title,
        message_seqs=[message.seq for message in messages],
        source={
            "kind": "provider",
            "provider": str(getattr(provider, "name", "") or "llm"),
            "model": model,
        },
        usage=call.usage,
    )
    logger.info("[agent-title] 已落模型标题（%d 字）：%s", len(call.title), call.title)
    return call
