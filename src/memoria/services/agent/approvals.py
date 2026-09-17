# 语义移植自 deepseek-harness packages/interaction/user-approval 与 packages/interaction/tool-ask-user（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""最小审批面：一次性决定 + **无应答即拒绝**（fail-closed）。

对应上游 `dsh-user-approval` 的可观察约定，收敛到 M1 需要的形状：

| 上游 | 本地 |
|---|---|
| 结果词汇 `allowed-once` / `rejected` / `cancelled` / `unavailable` | `ApprovalOutcome` 四值枚举（同名同义） |
| `policy: ask`（默认，委托应答者）/ `never`（确定性拒绝） | `AskPolicy` / `NeverPolicy` |
| 应答者缺失、抛错或返回词汇外取值 ⇒ `unavailable` ⇒ 按拒绝关闭 | `AskPolicy.decide` 的三条 fail-closed 分支 |
| 服务自身绝不提示人类 | 本模块不打印、不读终端；应答者由调用方注入 |

**本阶段的默认策略更严**：只读工具免审批，任何声明 `read_only=False` 的工具
一律拒绝（`rejected`）。M1 没有写工具，因此这里主要提供接口与默认策略，
供 M3「提议 → 确认 → 应用」复用同一 seam。

`dsh-tool-ask-user`（`ask_user_question` 工具）依赖 UI 问答 seam，M1 无
前端交互面，故只取其 fail-closed 结论（无应答者 = 拒绝），不注册该工具。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

__all__ = [
    "ALLOWED_ONCE",
    "DEFAULT_POLICY",
    "REJECTED",
    "UNAVAILABLE",
    "ApprovalDecision",
    "ApprovalOutcome",
    "ApprovalPolicy",
    "ApprovalRequest",
    "AskPolicy",
    "DefaultApprovalPolicy",
    "NeverPolicy",
]


class ApprovalOutcome(str, Enum):
    """封闭的审批结果词汇（与上游 `ApprovalOutcome` 一一对应）。"""

    ALLOWED_ONCE = "allowed-once"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """一次审批决定；只有 `allowed-once` 放行（一次性授权，无长期记忆）。"""

    outcome: ApprovalOutcome
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.outcome is ApprovalOutcome.ALLOWED_ONCE


ALLOWED_ONCE = ApprovalDecision(ApprovalOutcome.ALLOWED_ONCE)
REJECTED = ApprovalDecision(ApprovalOutcome.REJECTED)
UNAVAILABLE = ApprovalDecision(ApprovalOutcome.UNAVAILABLE)
"""无应答者 / 应答者失败：按拒绝关闭（fail-closed）。"""


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """一次审批请求。

    上游的请求**不携带工具参数**（应答者只看到工具名、原因与调用 id）；
    本地把参数一并给出，便于 M3 的「逐条确认」在 UI 上展示将写入什么——
    这是本阶段唯一的语义放宽，已在报告偏差表中登记。
    """

    tool: str
    call_id: str = ""
    arguments: Mapping[str, Any] = field(default_factory=dict)
    reason: str = ""
    read_only: bool = True


@runtime_checkable
class ApprovalPolicy(Protocol):
    """审批策略：给一次调用裁决，绝不抛异常（抛出即视为不可用 → 拒绝）。"""

    def decide(self, request: ApprovalRequest) -> ApprovalDecision:
        """返回一次性决定。"""
        ...


class DefaultApprovalPolicy:
    """M1 默认策略：只读免审批；写类一律拒绝。

    只读工具不改动知识库，按上游「只对需要审批的操作发起询问」的语义直接
    放行；其余（含未来新增但忘记声明 `read_only=False` 的工具）**拒绝**，
    而不是默认放行——这正是 fail-closed 的含义。
    """

    def decide(self, request: ApprovalRequest) -> ApprovalDecision:
        if request.read_only:
            return ALLOWED_ONCE
        return ApprovalDecision(
            ApprovalOutcome.REJECTED,
            f"本阶段只提供只读工具，{request.tool} 属于写类操作，已按默认策略拒绝",
        )


class NeverPolicy:
    """对齐上游 `policy: never`：需审批的操作确定性拒绝，不询问任何应答者。"""

    def decide(self, request: ApprovalRequest) -> ApprovalDecision:
        if request.read_only:
            return ALLOWED_ONCE
        return ApprovalDecision(ApprovalOutcome.REJECTED, f"当前策略为 never：{request.tool} 需审批，已确定性拒绝")


class AskPolicy:
    """对齐上游 `policy: ask`：把请求交给应答者；无应答者/应答者失败 = 拒绝。

    `answerer` 收到请求并返回 `ApprovalOutcome`（或 `None` 表示"不处理"）；
    返回其它类型、抛异常、或未注入应答者，都归一到 `unavailable`。
    """

    def __init__(self, answerer: Callable[[ApprovalRequest], ApprovalOutcome | None] | None = None) -> None:
        self._answerer = answerer

    def decide(self, request: ApprovalRequest) -> ApprovalDecision:
        if request.read_only:
            return ALLOWED_ONCE
        if self._answerer is None:
            logger.info("[agent-approval] 无应答者，%s 按拒绝关闭", request.tool)
            return ApprovalDecision(ApprovalOutcome.UNAVAILABLE, "没有可用的审批应答者")
        try:
            outcome = self._answerer(request)
        except Exception as exc:  # noqa: BLE001 — 应答者失败即不可用
            logger.warning("[agent-approval] 应答者失败：%r", exc)
            return ApprovalDecision(ApprovalOutcome.UNAVAILABLE, f"审批应答者失败：{exc}")
        if not isinstance(outcome, ApprovalOutcome):
            return ApprovalDecision(ApprovalOutcome.UNAVAILABLE, f"应答者返回了词汇外的结果：{outcome!r}")
        if outcome is ApprovalOutcome.ALLOWED_ONCE:
            return ALLOWED_ONCE
        return ApprovalDecision(outcome, f"应答者裁决：{outcome.value}")


#: M1 生产默认策略（`ask.py` 在调用方未注入策略时使用它）。
DEFAULT_POLICY: ApprovalPolicy = DefaultApprovalPolicy()
