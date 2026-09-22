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

**本阶段的默认策略**：**全线放行**（读类、写类都放行）—— 2026-09-21 人拍板"搁置审计（审批）的
设计、全线放开写机制"，审批档位（`manual approval` / `auto approval` / `custom` / `all access`）
作为**以后的运行模式**。更严的档位由调用方**注入**：逐条确认用 `AskPolicy`（无应答者即拒绝）、
确定性拒绝用 `NeverPolicy`。写路径的安全兜底是**备份 + 可撤销**，不是这道闸门。

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
    "AskPolicy", "GuardedPolicy",
    "DefaultApprovalPolicy", "RISKY_OPS", "write_is_risky",
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
    """本阶段默认策略：**全线放行**（读类、写类都 `allowed-once`）。

    2026-09-21 人拍板：「搁置审计（审批）的设计，全线放开写机制；审计作为**以后的运行模式之一**
    （`manual approval` / `auto approval` / `custom` / `all access`）」。⇒ 默认档 = **自动放行**。

    **兜底不靠闸门、靠备份**：任何写入都必须先落 pre-image 快照（备份失败即**不写**），写入可
    整批撤销、外部改动受保护（`services/agent/backup.py`、设计 §4 Q7 与 §9）。

    要更严的档位请**注入**策略：逐条确认用 `AskPolicy`（无应答者即拒绝）、确定性拒绝用
    `NeverPolicy`。本类不再自行拒绝写工具（旧行为：`read_only=False` 一律 `rejected`）。
    """

    def decide(self, request: ApprovalRequest) -> ApprovalDecision:
        return ALLOWED_ONCE


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


# ── 2026-09-22 追加：`auto` 档策略（「自动放行但保留闸门」，人拍板的档位语义之一）──────
# 本块是**末尾追加** ⇒ 上方 `ApprovalOutcome`(50) / `DefaultApprovalPolicy`(102) /
# `AskPolicy`(128) 等既有行号锚点零漂移。

#: 「风险条件」命中的 op 动词：**动"路径/归属"这个坐标系、或整篇消失**的动作（`rename_file`
#: 改名并级联改写全库 `[[…]]`、`delete_file` 删整篇 + 其侧车、`move_file` 跨目录搬整篇）。
#: 词表取自计划层的 op 全集（`services/agent/plan.py::KNOWN_OPS`）。批量大小**不算**风险 ——
#: 每批都是 all-or-nothing + 写前备份 + 可整批撤销（人 2026-09-22 口径）。
#:
#: **2026-09-22 补两个 sidecar 结构 op**（同日新增，设计 §7 的 1.7 / 1.8）：
#: `delete_kp` 会让**别的**文档里的 `[[id]]` 变成悬空虚链（影响面超出本文档）、`rename_kp` 是**全库**
#: 级联改名（与 `rename_file` 同级）⇒ 两者都进风险表（设计里这两行的「审批档」建议就是 `confirm`，
#: 且删除类不设 `auto`）。`upsert_edge` 只往本文档的 sidecar 加一条边、完全自包含 ⇒ **不进**
#: （它连"牵连别的文件"都算不上）。
#:
#: **2026-09-22 订正（人点名"删行要人点确认"这条摩擦）**：`delete_lines` **移出**风险表。
#: 理由两条：① 与本块既有的判据自相矛盾 —— 判据是"不可逆"，而 `delete_lines` 有逐字 `expect`
#: 前置校验 + 写前备份 + 整批撤销，可逆性与 `replace_lines`（一直免问）**没有区别**
#: （把整段替换成空串同样是删）；② 与设计口径冲突 —— 设计里"不设 `auto`"针对的是**删除类**
#: （`kb.file.delete` / `kb.kp.delete`，§7 2.5），不是"改正文"。真机后果：整理教材残渣这类
#: **纯删行**任务会**每批**都弹确认卡、没人点就挂满 `APPROVAL_TIMEOUT_S`(120s) 后按拒绝关闭 ⇒
#: agent 反复"写不进去"（`D:\AAA_Courses\软件工程概论` 2026-09-22 会话实测到连续 3 次 120s 超时）。
RISKY_OPS = frozenset({"rename_file", "delete_file", "move_file", "delete_kp", "rename_kp"})


def write_is_risky(request: ApprovalRequest) -> bool:
    """写类调用是否命中「风险条件」；**形状不认识一律按风险**（fail-closed）。

    只对「能识别的写计划」免问：`arguments["ops"]` 必须是**非空**列表，且每一项都能读出
    `op` 动词 —— 认不出（新写工具 / 参数换了形状）就当作危险，交给应答者。
    """
    arguments = request.arguments if isinstance(request.arguments, Mapping) else {}
    ops = arguments.get("ops")
    if not isinstance(ops, (list, tuple)) or not ops:
        return True
    for row in ops:
        if not isinstance(row, Mapping):
            return True
        verb = str(row.get("op") or "").strip()
        if not verb or verb in RISKY_OPS:  # 读不出动词（形状变了）也算风险
            return True
    return False


class GuardedPolicy:
    """`auto` 档：读类免审批；常规写自动放行；命中风险条件才交给应答者逐条确认。

    无应答者（CLI / 面板未挂载）⇒ 风险分支走 `AskPolicy(None)` ⇒ `unavailable` ⇒ **拒绝**
    （fail-closed；见 `services/agent/approval_bridge.py` 的四条关闭路径）。
    """

    def __init__(self, answerer: Callable[[ApprovalRequest], ApprovalOutcome | None] | None = None) -> None:
        self._answerer = answerer

    def decide(self, request: ApprovalRequest) -> ApprovalDecision:
        if request.read_only:
            return ALLOWED_ONCE
        if not write_is_risky(request):
            return ALLOWED_ONCE
        return AskPolicy(self._answerer).decide(request)
