# 语义移植自 deepseek-harness packages/core/agent-loop（会话驱动的创建与运行）
# 与 packages/core/agent（Agent 句柄的服务入口）（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""应用内提问入口：组装 prompt/工具 → 跑循环 → 落会话 → 返回结构化结果。

这是 M1 竖切（应用内对话 + 读库问答）的**调用面**，等价于上游
「`ctx.agents.create()` 建 agent → 会话写句柄持久化 → 轮次由 loop 驱动」那一段：
本地把「创建 + 持久化 + 驱动」收敛成一个同步函数，返回
`{answer, anchors, tool_calls, usage, session_id, session_path}`。

会话事实源：`<kb>/.memoria/agent/sessions/<session-id>.jsonl`（用户 P3 拍板）。
除该目录外，本模块不写知识库任何内容（工具面自带零写入守卫）。

**多轮续聊（M1c）**：`session_id` 指向的会话文件**已存在**时，先按
`session/history.py::build_history()` 把它回放成消息序列，作为 `messages=` 传给
`loop.run(question, messages=history)`（在追加本轮 `user/message` **之前**回放，
故历史里不含本轮问题，不会被重复加入）。`session_id` 省略或文件不存在 ⇒ 全新会话，
行为与 M1b 完全一致。`replay=False` 可显式关闭回放（测试/脚本用）。

密钥与端点**不另起实现**：上游 `dsh-credentials-local` 的"配置写名不写值"语义已由
第一块 `llm/config.py`（环境变量 / `config/agent.json` + 掩码 + 格式校验）覆盖，
M1 无新增价值，故此处只引用 `load_config()` / `create_provider()`；等 M3 需要
多凭据引用与授权流程时再评估是否补 `credentials.py`。

`provider` 可注入：省略时才 `load_config()` + `create_provider()`（联网由 provider
承担，本模块自身不联网）。

**长会话压缩（M2）**：追加本轮 `user/message` **之前**，若回放出的历史超过
`compaction.compact_threshold_chars()`，**先**跑一遍免模型的**工具结果裁剪**
（`pruner.prune_plan()` → 落一条 `compaction/prune`，把超预算的旧工具输出换成「头 + 标记 + 尾」；
裁剪可能已把压力降到阈值之下 ⇒ **免掉这次摘要调用**），**再**按 `compaction.select_span()`
选出最旧的合法区间、跑一次摘要调用，并把结果作为一条 `compaction` 事件落盘（被覆盖的 seq 记在
`shadowed` 里；`build_history()` 回放时据此在原位置出摘要）。两步都**失败不打断提问**（见
`_compact_if_needed()`：`summarize_span()` 自身 fail-closed，但这里只记日志、按未压缩历史继续）。
为了让摘要调用成为「上一次已路由请求」的真实前缀（复用 provider 的 KV 缓存），压缩与主回合
**共用同一份 `system` + 工具集** —— 故本模块先建一次 `registry` / `system` 再传给 `build_loop()`。

**会话标题（M2）**：标题是 **log-only** 的 `session/title` 事件（**永不进模型输入**，见 `title.py`）。
本地分两步、都在 `ask()` 里：① 追加本轮 `user/message` **之后**立刻补一条**确定性兜底**标题
（零模型调用、零网络，会话已有标题则跳过）；② 主回合结束后跑**首轮一次**的模型标题
（`first-prompt` 节律：会话里恰好一条合格人类消息时；**被取消的轮次跳过**）。两步都 fail-open
（失败只记 warning）；代价是「面板的 `done` 会晚一个极小辅助调用的时间，仅每会话首轮一次」。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from memoria.services.agent.approvals import DEFAULT_POLICY, ApprovalPolicy
from memoria.services.agent.compaction import (
    CompactionError,
    compact_threshold_chars,
    event_chars,
    select_span,
    summarize_span,
)
from memoria.services.agent.llm import (
    AgentConfig,
    LlmProvider,
    Message,
    RetryPolicy,
    create_provider,
    load_config,
)
from memoria.services.agent.loop import (
    DEFAULT_MAX_ITERATIONS,
    AgentLoop,
    CancelToken,
    LoopResult,
    StopReason,
    usage_payload,
)
from memoria.services.agent.prompt import build_system_prompt
from memoria.services.agent.pruner import (
    PRUNE,
    applied_chars,
    prune_applied,
    prune_plan,
)
from memoria.services.agent.session.history import (
    COMPACTION,
    build_history,
    compaction_shadowed,
    conversation_events,
    replay_events,
)
from memoria.services.agent.session.reference import build_snapshot, parse_session_references
from memoria.services.agent.session.store import SessionStore, new_session_id, session_file
from memoria.services.agent.tools.kb import DEFAULT_TOP_K, build_kb_tools
from memoria.services.agent.tools.registry import ToolRegistry
from memoria.services.agent.title import TitleError, auto_title, ensure_fallback

logger = logging.getLogger(__name__)

__all__ = ["AskResult", "ask", "build_loop"]


@dataclass(frozen=True, slots=True)
class AskResult:
    """一次提问的完整结果。"""

    answer: str
    anchors: tuple[Mapping[str, Any], ...]
    tool_calls: tuple[Mapping[str, Any], ...]
    usage: Mapping[str, Any]
    session_id: str
    session_path: str
    stop_reason: str
    iterations: int
    error: str | None = None


def _dedupe_anchors(anchors: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    seen: set[tuple[str, Any, str]] = set()
    out: list[Mapping[str, Any]] = []
    for anchor in anchors:
        key = (str(anchor.get("file") or ""), anchor.get("line"), str(anchor.get("kp_id") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(anchor)
    return tuple(out)


def build_loop(
    kb_path: str,
    *,
    provider: Any,
    model: str = "",
    session: SessionStore | None = None,
    registry: ToolRegistry | None = None,
    system: str | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    top_k: int = DEFAULT_TOP_K,
    approval: ApprovalPolicy | None = None,
    retry_policy: RetryPolicy | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout_s: float | None = None,
    on_text: Callable[[str], None] | None = None,
    cancel: CancelToken | None = None,
) -> AgentLoop:
    """组装一个绑定了知识库只读工具的循环（供 `ask()` 与测试复用）。

    `registry` / `system` 可**预置**：`ask()` 为了让压缩调用与主回合共用同一份 system + 工具集
    （KV 前缀缓存对齐，见 `_compact_if_needed()`）而先建一次再传进来。省略时按
    `kb_path` + `model` 就地构建，与 M1 行为完全一致。
    """
    if registry is None:
        registry = ToolRegistry(build_kb_tools(kb_path, top_k=top_k))
    if system is None:
        system = build_system_prompt(kb_path, tools=registry.schemas(), model=model)
    return AgentLoop(
        provider=provider,
        tools=registry,
        model=model,
        system=system,
        max_iterations=max_iterations,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_s=timeout_s,
        approval=approval if approval is not None else DEFAULT_POLICY,
        retry_policy=retry_policy,
        on_text=on_text,
        on_event=session.append if session is not None else None,
        cancel=cancel,
    )


def _history_chars(messages: Sequence[Message]) -> int:
    """消息序列的字符量（与 `compaction.event_chars()` 同口径：正文 + 工具调用名与参数）。"""
    total = 0
    for message in messages:
        total += len(message.content or "")
        for call in message.tool_calls or ():
            total += len(call.arguments or "") + len(call.name or "")
    return total


def _compact_if_needed(
    root: str,
    session: SessionStore,
    *,
    history: Sequence[Message],
    provider: Any,
    system: str,
    tools: Sequence[Any],
    model: str,
    timeout_s: float | None,
    retry_policy: RetryPolicy | None,
    cancel: CancelToken | None,
) -> bool:
    """历史超过预算时**先裁旧工具输出、再按需压成 checkpoint**；返回是否落了事件。

    顺序对齐上游 `compaction-basic`：压力确认后**先**跑工具结果裁剪（免模型），**再**选择压缩
    区间 —— 裁剪可能已把压力降到阈值之下，那就**免掉这次摘要调用**（上游：*trimming may relieve
    enough token pressure to skip summarization*）。裁出来的有效字符数一并交给 `select_span()`
    计账，免得区域选择按原文（未裁）大小高估尾部、把本可保留的轮次也压掉。

    **失败不打断提问**（fail-open）：`summarize_span()` 自身是 fail-closed 的（任何异常路径都
    抛 `CompactionError`，不产出半份摘要），这里只记一条 warning，让本轮按**未压缩**的历史继续
    走 —— 压缩是优化，不该让用户的问题问不出去。
    """
    if _history_chars(history) <= compact_threshold_chars():
        return False
    events = conversation_events(root, session.session_id)
    changed = False
    plan = prune_plan(events, skip=compaction_shadowed(events))
    if plan:
        session.append(
            PRUNE,
            {
                "pruned": plan,
                "chars_removed": sum(int(item["chars_before"]) - int(item["chars_after"]) for item in plan),
            },
        )
        logger.info(
            "[agent-prune] 已裁 %d 条工具结果（%d → %d 字符）",
            len(plan),
            sum(int(item["chars_before"]) for item in plan),
            sum(int(item["chars_after"]) for item in plan),
        )
        changed = True
        events = conversation_events(root, session.session_id)
        if _history_chars(build_history(root, session.session_id)) <= compact_threshold_chars():
            return True  # 裁剪已把压力降到阈值之下 ⇒ 免掉这次摘要调用
    applied = prune_applied(events)
    effective = (
        {seq: applied_chars(head, tail) for seq, (head, tail) in applied.items()} if applied else None
    )
    span = select_span(events, effective_chars=effective)
    if span is None:
        return changed
    covered = list(events[span[0] : span[1]])
    try:
        call = summarize_span(
            provider,
            replay_events(covered, prune=applied),
            system=system,
            tools=tools,
            model=model,
            timeout_s=timeout_s,
            retry_policy=retry_policy,
            cancel=cancel,
        )
    except CompactionError as exc:
        logger.warning("[agent-compaction] 压缩失败，本轮按未压缩历史继续：%s", exc)
        return changed
    shadowed = [int(event["seq"]) for event in covered if isinstance(event.get("seq"), int)]
    if not shadowed:
        return changed
    shadowed_chars = sum(event_chars(event, effective_chars=effective) for event in covered)
    data: dict[str, Any] = {
        "summary": call.text,
        "shadowed": shadowed,
        "shadowed_chars": shadowed_chars,
        "model": call.model,
    }
    if call.usage is not None:
        data["usage"] = usage_payload(call.usage)
    session.append(COMPACTION, data)
    logger.info(
        "[agent-compaction] 已覆盖 %d 条事件（%d 字符）→ 摘要 %d 字符",
        len(shadowed),
        shadowed_chars,
        len(call.text),
    )
    return True


def _append_fallback_title(root: str, session: SessionStore) -> None:
    """在**追加本轮提问之后**补一条兜底标题（零模型调用、零网络，见 `title.py`）。

    与压缩/裁剪同理，标题是**优化**：任何意外都不该让用户的问题问不出去 —— 失败只记 warning。
    """
    try:
        if ensure_fallback(session, conversation_events(root, session.session_id)):
            logger.info("[agent-title] 已落兜底标题")
    except (TitleError, OSError, ValueError) as exc:
        logger.warning("[agent-title] 兜底标题失败（不影响问答）：%s", exc)


def _maybe_generate_title(
    root: str,
    session: SessionStore,
    *,
    result: LoopResult,
    provider: Any,
    model: str,
    timeout_s: float | None,
    retry_policy: RetryPolicy | None,
    cancel: CancelToken | None,
) -> None:
    """主回答结束后的**首轮一次**模型标题（`first-prompt` 节律，见 `title.auto_title()`）。

    两个本地取舍：① 排在**主回合之后**（本地没有异步的标题服务），故只影响「面板的 `done` 晚一点」，
    且**仅每会话首轮一次**；② **被取消的那一轮不生成**（用户已喊停，不再多花一次调用）。
    失败 fail-open：只记 warning（标题是优化，不该影响问答）。
    """
    if result.stop_reason is StopReason.ABORTED:
        return
    try:
        call = auto_title(
            session,
            conversation_events(root, session.session_id),
            provider=provider,
            model=model,
            timeout_s=timeout_s,
            retry_policy=retry_policy,
            cancel=cancel,
        )
    except TitleError as exc:
        logger.warning("[agent-title] 标题生成失败（不影响问答）：%s", exc)
        return
    if call is None:
        logger.debug("[agent-title] 非首轮（first-prompt 节律未命中），不生成标题")


def ask(
    kb_path: str,
    question: str,
    *,
    provider: LlmProvider | Any = None,
    model: str = "",
    session_id: str | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    top_k: int = DEFAULT_TOP_K,
    approval: ApprovalPolicy | None = None,
    retry_policy: RetryPolicy | None = None,
    config: AgentConfig | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout_s: float | None = None,
    on_text: Callable[[str], None] | None = None,
    replay: bool = True,
    cancel: CancelToken | None = None,
) -> AskResult:
    """问一个关于知识库的问题；返回答案、锚点、工具调用、用量与会话位置。

    `session_id` 指向**已存在**的会话文件且 `replay=True` 时，先回放该会话的消息
    作为上下文（续聊），再追加本轮问题（见模块 docstring）。

    `cancel`（M1 收尾**追加的可选参数**，不影响既有调用）：取消令牌透传到
    `AgentLoop`；取消时本轮以 `stop_reason="aborted"` 结束、**保留已生成的部分
    文本**作为 `answer`，并照常落盘 `loop/end`（不抛异常）。
    """
    root = os.path.abspath(kb_path or "")
    if not os.path.isdir(root):
        raise ValueError(f"知识库目录不存在：{kb_path!r}")
    text = (question or "").strip()
    if not text:
        raise ValueError("问题不能为空")

    settings = config if config is not None else (None if provider is not None else load_config())
    active_provider = provider if provider is not None else create_provider(None, config=settings)
    active_model = model or (settings.model if settings is not None else "")

    # 压缩与主回合**共用**同一份 system + 工具集（KV 前缀对齐，见模块 docstring 的 M2 段）
    registry = ToolRegistry(build_kb_tools(root, top_k=top_k))
    system = build_system_prompt(root, tools=registry.schemas(), model=active_model)

    history: list[Message] | None = None
    if replay and session_id:
        try:
            resumed = os.path.isfile(session_file(root, session_id))
        except ValueError:
            resumed = False  # 非法 id 交由 SessionStore 抛同一异常（保持既有行为）
        if resumed:
            history = build_history(root, session_id)

    session = SessionStore(root, session_id or new_session_id())
    if history and _compact_if_needed(
        root,
        session,
        history=history,
        provider=active_provider,
        system=system,
        tools=registry.schemas(),
        model=active_model,
        timeout_s=timeout_s,
        retry_policy=retry_policy,
        cancel=cancel,
    ):
        # 裁剪/压缩已落盘 ⇒ 重新回放，让本轮请求用上裁剪与摘要视图（被覆盖区间不再逐字重发）
        history = build_history(root, session.session_id)
    # 跨会话引用（M2 收尾）：mention 改写为可读 `@label`，快照**只**进本轮 `loop.run()` 的请求。
    # 有意偏差：上游把快照作为**第二条 user 消息**持久化进目标会话；本地会话文件同时是读取路径的
    # 事实源（`agent_sessions_list` 以 2 MiB 上限做原始行扫描、`agent_session_load` 直接回放成渲染
    # 视图），故 JSONL 里只留干净的 `@label` 原文，不受信背景不落盘（标题生成/日志也因此拿不到它）。
    # 用户**再次 mention** 即可重新附带该会话 —— 这就是本地"重新挂载"的方式。
    rendered_text, references = parse_session_references(text)
    snapshot = (
        build_snapshot(root, references, exclude_session_id=session.session_id) if references else None
    )
    session.append("user/message", {"text": rendered_text})
    # 标题（M2）第 1 步：兜底标题 —— 零成本、零模型调用，先落一条（对齐上游 onUserMessage 的节律）
    _append_fallback_title(root, session)
    loop = build_loop(
        root,
        provider=active_provider,
        model=active_model,
        session=session,
        registry=registry,
        system=system,
        max_iterations=max_iterations,
        top_k=top_k,
        approval=approval,
        retry_policy=retry_policy,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_s=timeout_s,
        on_text=on_text,
        cancel=cancel,
    )
    prompt = rendered_text if snapshot is None else rendered_text + "\n\n" + snapshot
    result: LoopResult = loop.run(prompt, messages=history)
    session.flush()
    # 标题（M2）第 2 步：模型标题 —— 只跑首轮一次、fail-open、被取消的轮次跳过
    _maybe_generate_title(
        root,
        session,
        result=result,
        provider=active_provider,
        model=active_model,
        timeout_s=timeout_s,
        retry_policy=retry_policy,
        cancel=cancel,
    )

    tool_calls = tuple(
        {
            "id": call.call_id,
            "name": call.name,
            "is_error": call.is_error,
            "code": call.output.code,
        }
        for call in result.tool_calls
    )
    return AskResult(
        answer=result.answer,
        anchors=_dedupe_anchors(result.anchors),
        tool_calls=tool_calls,
        usage=result.usage_dict(),
        session_id=session.session_id,
        session_path=session.path,
        stop_reason=result.stop_reason.value,
        iterations=result.iterations,
        error=result.error,
    )
