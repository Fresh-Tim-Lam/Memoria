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
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from memoria.services.agent.approvals import DEFAULT_POLICY, ApprovalPolicy
from memoria.services.agent.llm import (
    AgentConfig,
    LlmProvider,
    Message,
    RetryPolicy,
    create_provider,
    load_config,
)
from memoria.services.agent.loop import DEFAULT_MAX_ITERATIONS, AgentLoop, CancelToken, LoopResult
from memoria.services.agent.prompt import build_system_prompt
from memoria.services.agent.session.history import build_history
from memoria.services.agent.session.store import SessionStore, new_session_id, session_file
from memoria.services.agent.tools.kb import DEFAULT_TOP_K, build_kb_tools
from memoria.services.agent.tools.registry import ToolRegistry

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
    """组装一个绑定了知识库只读工具的循环（供 `ask()` 与测试复用）。"""
    registry = ToolRegistry(build_kb_tools(kb_path, top_k=top_k))
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

    history: list[Message] | None = None
    if replay and session_id:
        try:
            resumed = os.path.isfile(session_file(root, session_id))
        except ValueError:
            resumed = False  # 非法 id 交由 SessionStore 抛同一异常（保持既有行为）
        if resumed:
            history = build_history(root, session_id)

    session = SessionStore(root, session_id or new_session_id())
    session.append("user/message", {"text": text})
    loop = build_loop(
        root,
        provider=active_provider,
        model=active_model,
        session=session,
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
    result: LoopResult = loop.run(text, messages=history)
    session.flush()

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
