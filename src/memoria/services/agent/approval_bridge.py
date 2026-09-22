# 语义移植自 deepseek-harness packages/interaction/user-approval（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""逐条确认桥：把「写类工具要批」变成「挂起等面板应答」，无应答即拒绝（fail-closed）。

上游把审批做成运行时询问瀑布（`approval/request`），应答者由上层 UI 注入，结果词汇封闭为
`allowed-once` / `rejected` / `cancelled` / `unavailable`，且**调用方对 `unavailable` 一律
按拒绝关闭**（`interaction/user-approval/src/types.ts:30`）。本地没有瀑布，只有一条**进程内
信箱**（与 `tools/kb.py::_PROPOSALS` 同性质的运行期信道，**不落盘**）：

1. 工具体所在线程（单线程池里的 ask 作业）在**分发前**调 `AskPolicy` / `GuardedPolicy`；
2. 策略把请求交给本模块的**应答者** ⇒ 登记一条待批项、阻塞等待；
3. 面板每 250ms 轮询 `agent_ask_poll`，从 `pending_approvals` 看到待批项、渲染确认卡；
4. 用户点「允许一次 / 拒绝」 ⇒ RPC `agent_approval_answer` 回填裁决 ⇒ 挂起线程继续。

**四条关闭路径全部 fail-closed**（对齐上游「Callers fail closed on `unavailable`」）：

| 情形 | 结果 |
|---|---|
| 超时（`APPROVAL_TIMEOUT_S`） | `unavailable` ⇒ 拒绝 |
| 本轮被取消（`AskJob.cancel()` ⇒ `abort()`） | `cancelled` ⇒ 拒绝 |
| **没有挂载**（CLI / 无面板进程） | 应答者缺失 ⇒ `unavailable` ⇒ 拒绝（由 `AskPolicy` 兜住，本模块不参与等待） |
| 应答者返回词汇外取值 / 抛错 | `unavailable` ⇒ 拒绝（`approvals.AskPolicy` 归一） |

「挂载」是显式动作（`attach()` / `detach()`）：只有把待批项交给面板的进程才登记，因此 CLI
（`scripts/agent_ask.py`）不会在写工具上白等 120 秒，而是立刻以「无应答者」拒绝。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from memoria.services.agent.approvals import ApprovalOutcome, ApprovalRequest

logger = logging.getLogger(__name__)

__all__ = [
    "APPROVAL_TIMEOUT_S",
    "EVENT_ASKED",
    "EVENT_DECIDED",
    "abort",
    "answer",
    "answerer_for",
    "attach",
    "attach_audit",
    "detach",
    "pending_for",
    "wait_for_answer",
]

#: 审计事件类型（**与上游 `interaction/user-approval` 的同名事件逐字对齐**；log-only、不进模型请求）。
#: `approval/asked` 载荷 = `{id, tool, reason}`（上游是 `{id, toolName, callId?, reason?}`，本地 `id` 就是
#: 那次工具调用的 id —— 与 `tool/call`/`tool/result` 的 `id` 同一空间）；`approval/decided` = `{id, outcome}`，
#: **每次 ask 恰一条**（决定 / 取消 / fail-closed 的 `unavailable` 都算）。见 `docs/design/agent-plugin-design.md` §5。
EVENT_ASKED = "approval/asked"
EVENT_DECIDED = "approval/decided"

#: 人工确认的等待上限（秒）；超时按 `unavailable` 拒绝。取值远大于正常思考时间、
#: 又小于面板轮询的 5 分钟兜底（`agent-panel.js::POLL_TIMEOUT_MS`）。
APPROVAL_TIMEOUT_S = 120.0

#: 阻塞等待的轮询步长（秒）：只为周期性复核超时/中止，不产生忙等。
_POLL_STEP_S = 0.25


@dataclass
class _Pending:
    """一条待批项（线程间握手：`event` 置位即裁决已回填）。"""

    tool: str
    call_id: str
    arguments: Mapping[str, Any]
    reason: str
    created_at: float
    event: threading.Event = field(default_factory=threading.Event, repr=False)
    outcome: ApprovalOutcome | None = None

    def view(self) -> dict[str, Any]:
        """给面板的只读视图（**只含工具名与参数**，不含任何密钥面）。"""
        return {
            "id": self.call_id,
            "tool": self.tool,
            "arguments": dict(self.arguments),
            "reason": self.reason,
            "created_at": int(self.created_at * 1000),
        }


_lock = threading.RLock()
#: 已挂载的库根 → 挂载计数（同一库可有多个作业面；计数到 0 才真正摘除）。
_attached: dict[str, int] = {}
#: 库根 → 待批项（按到达顺序；先进先出，面板逐条展示）。
_pending: dict[str, list[_Pending]] = {}
#: 库根 → **审计落盘回调**（`session.append`；由 `ask._bind_permission()` 按本次会话装上、随 `detach()` 摘除）。
#: 不落盘、不参与裁决 —— 只是把 `approval/asked`/`approval/decided` 写进会话日志（log-only 审计面）。
_audit: dict[str, Callable[[str, Mapping[str, Any]], None]] = {}


def attach_audit(kb_path: str, append: Callable[[str, Mapping[str, Any]], None]) -> None:
    """给某库装审计落盘回调（本次会话的 `session.append`）；同一库后装的覆盖先装的（单飞作业）。"""
    with _lock:
        _audit[os.path.abspath(kb_path or "")] = append


def _emit_audit(key: str, event_type: str, payload: Mapping[str, Any]) -> None:
    """写一条审计事件；**审计失败绝不打断审批**（吞掉异常并记 warning）。"""
    with _lock:
        append = _audit.get(key)
    if append is None:
        return
    try:
        append(event_type, dict(payload))
    except Exception as exc:  # noqa: BLE001 —— 审计是旁路，不得影响裁决
        logger.warning("[agent-approval] 审计事件落盘失败（%s）：%r", event_type, exc)


def attach(kb_path: str) -> None:
    """挂载某库的审批信道（由 ask 作业在提交时调用）；幂等、可重入计数。"""
    key = os.path.abspath(kb_path or "")
    with _lock:
        _attached[key] = _attached.get(key, 0) + 1


def detach(kb_path: str) -> None:
    """摘除某库的审批信道；计数归零时**清空**该库的待批项（未决项按拒绝收敛）。

    **审计回调刻意不在此摘除**：`detach` 会把未决项收敛为 `unavailable`，而等待线程是**异步**醒来后才写
    `approval/decided` 的 —— 这里若先摘掉回调，那条 decided 就丢了。回调按库只留一条、由下一次
    `attach_audit()` 覆盖（单飞作业 ⇒ 永远是"最后一次提问的那个会话"），故不留泄漏。
    """
    key = os.path.abspath(kb_path or "")
    with _lock:
        left = _attached.get(key, 0) - 1
        if left > 0:
            _attached[key] = left
            return
        _attached.pop(key, None)
        _resolve_locked(key, ApprovalOutcome.UNAVAILABLE)


def is_attached(kb_path: str) -> bool:
    """该库是否挂了审批信道。"""
    with _lock:
        return os.path.abspath(kb_path or "") in _attached


def abort(kb_path: str) -> None:
    """中止某库的全部待批项（本轮被取消时调用）：一律按 `cancelled` 收敛。"""
    key = os.path.abspath(kb_path or "")
    with _lock:
        _resolve_locked(key, ApprovalOutcome.CANCELLED)


def _resolve_locked(key: str, outcome: ApprovalOutcome) -> None:
    """（持锁）把该库所有未决项按 `outcome` 收敛并唤醒等待线程。"""
    for item in _pending.pop(key, []):
        item.outcome = outcome
        item.event.set()


def answerer_for(kb_path: str) -> Callable[[ApprovalRequest], ApprovalOutcome] | None:
    """给定库根，返回可用应答者；**未挂载/空库根 ⇒ None**（调用方据此 fail-closed）。"""
    key = os.path.abspath(kb_path or "")
    if not key or not is_attached(key):
        return None

    def answerer(request: ApprovalRequest) -> ApprovalOutcome:
        return wait_for_answer(key, request)

    return answerer


def wait_for_answer(
    kb_path: str,
    request: ApprovalRequest,
    *,
    timeout_s: float = APPROVAL_TIMEOUT_S,
) -> ApprovalOutcome:
    """登记待批项并阻塞等待裁决；超时 ⇒ `unavailable`（拒绝），无应答者路径见模块 docstring。"""
    key = os.path.abspath(kb_path or "")
    item = _Pending(
        tool=request.tool,
        call_id=request.call_id,
        arguments=request.arguments if isinstance(request.arguments, Mapping) else {},
        reason=request.reason,
        created_at=time.time(),
    )
    with _lock:
        _pending.setdefault(key, []).append(item)
    logger.info("[agent-approval] 等待人工确认：%s（call_id=%s）", item.tool, item.call_id or "-")
    _emit_audit(key, EVENT_ASKED, {"id": item.call_id, "tool": item.tool, "reason": item.reason})
    deadline = time.monotonic() + max(0.0, float(timeout_s))
    try:
        while not item.event.wait(_POLL_STEP_S):
            if time.monotonic() >= deadline:
                item.outcome = ApprovalOutcome.UNAVAILABLE
                logger.warning("[agent-approval] %s 等待确认超时（%.0fs），按拒绝关闭", item.tool, timeout_s)
                break
    finally:
        with _lock:
            bucket = _pending.get(key)
            if bucket and item in bucket:
                bucket.remove(item)
            if bucket is not None and not bucket:
                _pending.pop(key, None)
    outcome = item.outcome or ApprovalOutcome.UNAVAILABLE
    # 每次 ask **恰一条** decided（决定 / 取消 / 超时 / 摘除 都走这条出口）——与上游同口径
    _emit_audit(key, EVENT_DECIDED, {"id": item.call_id, "outcome": outcome.value})
    return outcome


def pending_for(kb_path: str) -> list[dict[str, Any]]:
    """该库当前**未决**的待批项（面板轮询载荷 `pending_approvals` 的来源）。"""
    key = os.path.abspath(kb_path or "")
    with _lock:
        return [item.view() for item in _pending.get(key, [])]


def answer(kb_path: str, call_id: str, outcome: ApprovalOutcome) -> bool:
    """回填一次裁决；未知/已处理的 `call_id` 返回 False（幂等、不抛）。"""
    key = os.path.abspath(kb_path or "")
    wanted = str(call_id or "")
    with _lock:
        for item in _pending.get(key, []):
            if item.call_id == wanted and not item.event.is_set():
                item.outcome = outcome
                item.event.set()
                logger.info("[agent-approval] %s 裁决：%s", item.tool, outcome.value)
                return True
    return False
