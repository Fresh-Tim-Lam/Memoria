# 语义移植自 deepseek-harness packages/core/agent-loop（流式增量投递，MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""应用内对话的「伪流式」作业面（M1 首版对话面板的后端支撑）。

上游的对话是「流式增量 + 可中断」；本地 M1 的 `ask()` 是**同步阻塞**的（循环内
无取消点），但它的 `on_text` 回调已经是**实时逐片**投递的增量
（`ask.py:128` 透传到 `loop.py:118`，消费 provider 的 `TextDelta`，见
`loop.py` 的 `_stream_once`）。本模块把该回调接进一个**进程内单任务作业**，
让前端用「提交 + 按 cursor 轮询」拿到打字机效果：

- **单线程执行器**：一次只跑一个 ask，且**不占用** `MaintenanceExecutor` 的
  工作线程（后者只服务库维护类作业，见 `services/executor.py` 模块说明）；
  已有 ask 在飞时再次提交返回 `busy` 结构化错误（不抛异常、不排队）；
- **增量缓冲**：`on_text` 把片段追加进缓冲区，`poll(cursor)` 只返回
  `cursor` 之后的新增文本，前端无需重放全文；`on_event` 另把循环事件折成**过程行**（工具/步骤）追加进第三条缓冲，`poll(..., process_cursor)` 同样按游标增量投递（形状见 `turn_process.py`）；
- **真取消（M1 收尾）**：每个作业持一枚 `CancelToken`（`loop.py`），`cancel(job_id)`
  置位令牌并**立即**把作业收敛为 `done` + `stop_reason="aborted"`（保留已生成的
  部分文本为 `answer`）⇒ `busy` 立刻释放、可马上发起新提问；工作线程在下个检查点
  观察到取消后停止消费生成器（关闭底层 HTTP 响应）、正常落盘 `loop/end`
  （`stop_reason=aborted`）并返回，不会把取消改写回 `error`。取消是**协作式**的：
  阻塞中的 socket 读不会被抢占，最长等一个分片的到达；
- **有界重试**（交互路径）：作业固定使用 `PANEL_RETRY_POLICY`（`max_retries=2` /
  `total_timeout_s=20`），库层 `llm/retry.py` 的上游默认值不变；确定性连接失败
  （`UNREACHABLE`）不重试，故面板对"必拒连端点"是**立即失败**；
- **密钥不落本模块**：端点配置由 `llm/config.py` 读取，异常消息由
  `llm/errors.py` 保证不含凭据取值；
- **思考流既流式、又随步骤落盘（AG08，2026-09-22 口径更新）**：模型的 `ReasoningDelta`
  经 `ask(on_reasoning=…)` 追进 `reasoning_parts`，由 `poll` 以**独立游标**增量投递
  （`reasoning_delta` / `reasoning_cursor`，与文本游标互不影响）⇒ 面板生成中实时显示思考块；
  该步思考全文同时写进 `assistant/message.reasoning` **落盘** ⇒ 重载页面或载入旧会话**可回放**
  （回放按 `step.reasoning` 呈现）。但思考**仍不进模型请求**：`session/history.py::build_history`
  只读 `content`/`tool_calls`，新键被回放忽略（详见该模块「事件 → 消息」表）。

本模块不联网（联网只发生在注入的 provider 内）、不打印；`logging` 只记失败。
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from memoria.services.agent.ask import ask
from memoria.services.agent.approval_bridge import abort, attach, detach, pending_for
from memoria.services.agent.llm import RetryPolicy
from memoria.services.agent.loop import CancelToken, StopReason

logger = logging.getLogger(__name__)

__all__ = [
    "DONE",
    "ERROR",
    "PANEL_MAX_RETRIES",
    "PANEL_RETRY_POLICY",
    "PANEL_TOTAL_TIMEOUT_S",
    "RUNNING",
    "AskJob",
    "AskJobManager",
    "get_ask_jobs",
]

#: 作业状态（前端按此三分支渲染）。
RUNNING = "running"
DONE = "done"
ERROR = "error"

#: 被取消时 `stop_reason` 的取值（与 `loop.StopReason.ABORTED.value` 同源）。
STOP_ABORTED = StopReason.ABORTED.value

#: 稳定错误 code（前端据此本地化；不解析 message 文本）。
#: `no_kb` / `empty_question` / `net_disabled` / `no_base_url` / `busy` 由提交侧产生，
#: `unknown_job` 由轮询侧产生，`ask_failed` 兜底非 LLM 异常；LLM 异常沿用
#: `llm/errors.py` 的稳定 code（`AUTH` / `RATE_LIMIT` / `TIMEOUT` 等）。
CODE_NO_KB = "no_kb"
CODE_EMPTY_QUESTION = "empty_question"
CODE_NET_DISABLED = "net_disabled"
CODE_NO_BASE_URL = "no_base_url"
CODE_BUSY = "busy"
CODE_UNKNOWN_JOB = "unknown_job"
CODE_ASK_FAILED = "ask_failed"

# ── 面板路径的重试策略（**交互路径，等待必须有界**）──────────────────────────
# 库层 `llm/retry.py` 的 DEFAULT_*（5 次 / 0.5s 起 / 上限 10s / 总时限 120s）是上游
# 口径，**不改**；对话面板是交互路径，用户在等答案，故在此显式收紧：
# ① `max_retries=2`：首次 + 至多 2 次重试，足以覆盖偶发抖动（退避上限 0.5+1.0≈1.5s）；
# ② `total_timeout_s=20`：模型单次回答的长尾之外不再等待——超过 20s 的"无输出等待"
#    在面板里已属"像卡死"，宁可失败让用户重试（前端另有 5 分钟轮询兜底，更宽松）。
# 确定性连接失败（`UNREACHABLE`）不参与重试，故本策略只约束瞬时故障。
PANEL_MAX_RETRIES = 2
PANEL_TOTAL_TIMEOUT_S = 20.0
PANEL_RETRY_POLICY = RetryPolicy(max_retries=PANEL_MAX_RETRIES, total_timeout_s=PANEL_TOTAL_TIMEOUT_S)


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    """结构化错误（提交/轮询一律返回 dict，绝不向 RPC 抛裸异常）。"""
    return {"status": "error", "code": code, "message": message, **extra}


@dataclass
class AskJob:
    """一次 ask 的作业记录（含增量缓冲）。

    `parts` 由工作线程写入、RPC 线程读取，故所有访问都在 `lock` 内；
    增量文本按到达顺序拼接，`poll` 用字符下标做 cursor，不重放历史。

    `cancel_token` 是**跨线程**取消信号（`CancelToken` 自带线程安全），
    `cancelled` 是"已取消"的**终态标记**（在 `lock` 内读写），二者职责不同：
    前者通知工作线程停止消费，后者保证取消后不再被工作线程改写状态。
    """

    job_id: str
    kb_path: str
    question: str
    model: str = ""
    #: 本轮要**续接**的会话 id（前端带上上一轮 `session_id`）；None = 全新会话。
    resume_session_id: str | None = None
    #: 应用侧已装载的 `DocumentService`（2026-09-21 追加，可选）：agent **直接写入**时用它 ——
    #: 写后清它的解析缓存 ⇒ 前端重开文件看到的是新内容；也避免每次写入新建实例（那会写用户 config）。
    service: Any = None
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    cancel_token: CancelToken = field(default_factory=CancelToken, repr=False)
    status: str = RUNNING
    parts: list[str] = field(default_factory=list, repr=False)
    reasoning_parts: list[str] = field(default_factory=list, repr=False)
    #: 本轮**过程行**（工具/步骤，形状见 `turn_process.py`）；与另两条缓冲同一把锁。
    process: list[dict[str, Any]] = field(default_factory=list, repr=False)
    answer: str = ""
    anchors: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    stop_reason: str = ""
    iterations: int = 0
    error: str | None = None
    code: str | None = None
    cancelled: bool = False
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    # —— 工作线程侧 ——

    def note_delta(self, piece: str) -> None:
        """`ask(on_text=...)` 回调：追加剧增文本（空片段忽略）。"""
        if not piece:
            return
        with self.lock:
            self.parts.append(piece)

    def note_reasoning(self, piece: str) -> None:
        """`ask(on_reasoning=...)` 回调：追加剧增思考文本（空片段忽略）。

        与 `note_delta` 同一把锁、同一节奏；思考缓冲与文本缓冲**相互独立**，
        故 `poll` 的两个游标可以各自前进、互不影响。
        """
        if not piece:
            return
        with self.lock:
            self.reasoning_parts.append(piece)

    def note_process(self, item: Mapping[str, Any]) -> None:
        """`ask(on_event=...)` 回调：追加一条**过程行**（工具/步骤；空项忽略）。

        与 `note_delta` / `note_reasoning` 同一把锁、同一节奏；过程缓冲独立 ⇒
        `poll` 的第三个游标 `process_cursor` 可各自前进、互不影响。
        """
        if not item:
            return
        with self.lock:
            self.process.append(dict(item))

    def fail(self, error: str, code: str) -> None:
        with self.lock:
            if self.cancelled:
                # 取消是终态：工作线程后续的失败（含关闭响应引发的传输错误）
                # 不得把 `done/aborted` 改写回 `error`。
                return
            self.status = ERROR
            self.error = error
            self.code = code
            self.finished_at = time.time()

    def succeed(self, result: Any) -> None:
        """把 `AskResult` 落进作业；`result.error` 非空时判为 error（保留已投递文本）。"""
        with self.lock:
            if self.cancelled:
                # 取消后只允许补"取消时还不知道的"会话 id（供下一句续聊用），
                # 状态、答案、用量等一律以取消瞬间的快照为准。
                if self.session_id is None and getattr(result, "session_id", None):
                    self.session_id = str(result.session_id)
                return
            self.answer = result.answer
            self.anchors = [dict(anchor) for anchor in result.anchors]
            self.tool_calls = [dict(call) for call in result.tool_calls]
            self.usage = dict(result.usage)
            self.session_id = result.session_id
            self.stop_reason = result.stop_reason
            self.iterations = result.iterations
            self.error = result.error
            self.code = CODE_ASK_FAILED if result.error else None
            self.status = ERROR if result.error else DONE
            self.finished_at = time.time()

    # —— RPC 线程侧 ——

    def cancel(self) -> bool:
        """请求取消并**立即**收敛为 `done`/`aborted`；已结束时返回 False（幂等）。"""
        with self.lock:
            if self.finished_at is not None:
                return False
            self.cancel_token.cancel()
            self.cancelled = True
            self.status = DONE
            self.stop_reason = STOP_ABORTED
            self.answer = "".join(self.parts)
            self.code = None
            self.error = None
            self.finished_at = time.time()
            abort(self.kb_path)  # 唤醒挂起等确认的工具线程（按 cancelled 收敛，见 approval_bridge）
            return True

    def snapshot(self, cursor: int = 0, reasoning_cursor: int = 0, process_cursor: int = 0) -> dict[str, Any]:
        """轮询快照：`delta` / `reasoning_delta` / `process_delta` = 各自 `cursor` 之后的新增（不重放历史）。

        三条游标**完全独立**：思考游标只在自己那条缓冲上推进，过程游标只在**过程行**缓冲上推进；
        文本游标的语义（`0 < cursor <= len` 时切片、越界回落到 0 重放）在此**逐字保持不变**
        （过程游标同口径）。
        """
        with self.lock:
            text = "".join(self.parts)
            start = cursor if 0 < cursor <= len(text) else 0
            reasoning = "".join(self.reasoning_parts)
            r_start = reasoning_cursor if 0 < reasoning_cursor <= len(reasoning) else 0
            p_start = process_cursor if 0 < process_cursor <= len(self.process) else 0
            out: dict[str, Any] = {
                "status": self.status,
                "job_id": self.job_id,
                "delta": text[start:],
                "cursor": len(text),
                "reasoning_delta": reasoning[r_start:],
                "reasoning_cursor": len(reasoning),
                "process_delta": [dict(item) for item in self.process[p_start:]],
                "process_cursor": len(self.process),
                # 追加键（2026-09-22）：待人工确认的写类调用（逐条确认卡；只增不改）
                "pending_approvals": pending_for(self.kb_path),
                "answer": self.answer,
                "anchors": [dict(anchor) for anchor in self.anchors],
                "tool_calls": [dict(call) for call in self.tool_calls],
                "usage": dict(self.usage),
                "session_id": self.session_id,
                "stop_reason": self.stop_reason,
                "iterations": self.iterations,
                "error": self.error,
                "code": self.code,
                "cancelled": self.cancelled,
                "elapsed_ms": round(((self.finished_at or time.time()) - self.started_at) * 1000, 1),
            }
        return out


class AskJobManager:
    """单任务 ask 管理器：提交即返回 job_id，执行在独立单线程池。"""

    #: 保留最近作业数（前端只轮询最新一个，留几个便于诊断/重复轮询）。
    KEEP = 8

    def __init__(self) -> None:
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent-ask")
        self._lock = threading.RLock()
        self._jobs: dict[str, AskJob] = {}
        self._order: list[str] = []
        self._active: str | None = None

    # —— 提交 ——

    def start(
        self,
        kb_path: str,
        question: str,
        *,
        session_id: str | None = None,
        model: str = "",
        env: Mapping[str, str] | None = None,
        service: Any = None,
    ) -> dict:
        """校验并提交一次提问；返回 `{status:"ok", job_id}` 或结构化错误。

        `session_id` 非空 ⇒ 续聊（后端按会话文件回放历史，见 `ask()`）。
        `service`（2026-09-21 追加，可选）⇒ 应用侧已装载的 `DocumentService`，
        交给 agent 的**写入**路径复用（写后清解析缓存、避免新建实例）。
        """
        from memoria.services.agent.llm.config import is_enabled, load_config

        kb = os.path.abspath(kb_path or "")
        if not kb or not os.path.isdir(kb):
            return _error(CODE_NO_KB, "未打开知识库（或知识库目录不存在）")
        text = (question or "").strip()
        if not text:
            return _error(CODE_EMPTY_QUESTION, "问题不能为空")
        resume = (session_id or "").strip() or None
        try:
            enabled = is_enabled(env)
        except Exception as exc:  # noqa: BLE001 —— 配置不可读时按"不允许出网"处理，不裸抛
            return _error(CODE_NET_DISABLED, f"读取出网开关失败：{exc}")
        if not enabled:
            return _error(CODE_NET_DISABLED, "已关闭「出网」开关，模型调用被禁用")
        try:
            if not load_config(env).base_url.strip():
                return _error(CODE_NO_BASE_URL, "未配置模型端点（base_url）")
        except Exception as exc:  # noqa: BLE001 —— 配置文件损坏等
            return _error(CODE_NO_BASE_URL, f"读取模型配置失败：{exc}")

        with self._lock:
            running = self._jobs.get(self._active) if self._active else None
            if running is not None and running.status == RUNNING and not running.cancelled:
                return _error(
                    CODE_BUSY,
                    "上一个问题仍在生成，请先「停止」或等它结束后再提问",
                    job_id=running.job_id,
                )
            job = AskJob(
                job_id=uuid.uuid4().hex[:12],
                kb_path=kb,
                question=text,
                model=model,
                resume_session_id=resume,
                service=service,
            )
            self._jobs[job.job_id] = job
            self._order.append(job.job_id)
            self._active = job.job_id
            self._evict_locked()
        self._pool.submit(self._run, job)
        return {"status": "ok", "job_id": job.job_id, "job_status": RUNNING}

    def _run(self, job: AskJob) -> None:
        """工作线程：跑一次同步 ask，增量经 `on_text` 流入作业缓冲、过程行经 `on_event` 流入过程缓冲。"""
        from memoria.services.agent import turn_process

        current = 0  # 最近一次 `assistant/message` 的 iteration（工具行沿用）
        args_by_id: dict[str, Any] = {}  # id → tool/call 的参数（用于给最终 tool_calls 补 summary）
        # 挂载本库的审批信道：只有走到这里的（=有面板轮询的）作业才允许 `manual`/`auto` 档
        # 挂起等人；CLI 直接调 `ask()` 不经过本类 ⇒ 无应答者 ⇒ 立即 fail-closed 拒绝。
        attach(job.kb_path)

        def on_event(event_type: str, data: Mapping[str, Any]) -> None:
            nonlocal current
            if event_type == "assistant/message":
                current = int(data.get("iteration") or current)
                job.note_process(
                    turn_process.step_row(current, data.get("content"), data.get("tool_calls"), data.get("reasoning"))
                )
            elif event_type == "tool/call":
                args_by_id[str(data.get("id") or "")] = data.get("arguments")
                job.note_process(turn_process.tool_row(data, state="running", iteration=current))
            elif event_type == "tool/result":
                job.note_process(
                    turn_process.tool_row(
                        data, state="error" if data.get("is_error") else "ok", iteration=current
                    )
                )
            # 其它事件类型（step/start、usage、loop/end 等）一律丢弃：不发往前端

        try:
            result = ask(
                job.kb_path,
                job.question,
                model=job.model,
                session_id=job.resume_session_id,
                retry_policy=PANEL_RETRY_POLICY,
                on_text=job.note_delta,
                on_reasoning=job.note_reasoning,
                on_event=on_event,
                cancel=job.cancel_token,
                service=job.service,
            )
        except Exception as exc:  # noqa: BLE001 —— 失败只影响本作业
            code = getattr(exc, "code", None) or CODE_ASK_FAILED
            logger.warning("[agent-ask] 作业 %s 失败（code=%s）", job.job_id, code)
            job.fail(str(exc), str(code))
            detach(job.kb_path)
            return
        job.succeed(result)
        # 最终 `tool_calls` 载荷补一截**可读摘要**（来源是 `tool/call` 的 arguments；只增不改）；
        # 取消的作业 `succeed()` 早退、`tool_calls` 可能为空 ⇒ 自然跳过。
        with job.lock:
            for call in job.tool_calls:
                arguments = args_by_id.get(str(call.get("id") or ""))
                if arguments is None:
                    continue
                call.setdefault("summary", turn_process.arg_summary(str(call.get("name") or ""), arguments))
        detach(job.kb_path)

    # —— 取消 ——

    def cancel(self, job_id: str) -> dict:
        """取消在飞作业（幂等）：置取消令牌 ⇒ `busy` 立刻释放、可马上再提交。

        未知作业 ⇒ `{status:"error", code:"unknown_job", cancelled:false}`；
        已结束的作业 ⇒ `{status:"ok", cancelled:false}`（无可取消者）；均不抛异常。
        """
        key = str(job_id or "")
        with self._lock:
            job = self._jobs.get(key) if key else None
        if job is None:
            return _error(CODE_UNKNOWN_JOB, "未知任务（可能已重启或已被清理）", job_id=key, cancelled=False)
        return {
            "status": "ok",
            "job_id": job.job_id,
            "cancelled": job.cancel(),
            "job_status": job.snapshot(0)["status"],
        }

    # —— 查询 ——

    def poll(self, job_id: str, cursor: int = 0, reasoning_cursor: int = 0, process_cursor: int = 0) -> dict:
        """轮询作业：返回增量、状态与最终产物；未知 job 返回 `unknown_job`。

        `reasoning_cursor` / `process_cursor` 是**追加的可选参数**（AG08 / 2026-09-22）：
        既有两参调用的返回里只是多出 `reasoning_delta` / `reasoning_cursor` /
        `process_delta` / `process_cursor` 字段（**只增不改**），文本侧的 `delta` / `cursor`
        语义与形状完全不变。
        """
        with self._lock:
            job = self._jobs.get(job_id) if job_id else None
        if job is None:
            return _error(CODE_UNKNOWN_JOB, "未知任务（可能已重启或已被清理）", job_id=job_id)
        try:
            offset = max(0, int(cursor))
        except (TypeError, ValueError):
            offset = 0
        try:
            r_offset = max(0, int(reasoning_cursor))
        except (TypeError, ValueError):
            r_offset = 0
        try:
            p_offset = max(0, int(process_cursor))
        except (TypeError, ValueError):
            p_offset = 0
        return job.snapshot(offset, r_offset, p_offset)

    def active_job_id(self) -> str | None:
        """当前在飞作业 id（无则 None）；供诊断/测试观察并发约束。"""
        with self._lock:
            return self._active

    def _evict_locked(self) -> None:
        while len(self._order) > self.KEEP:
            stale = self._order.pop(0)
            if stale != self._active:
                self._jobs.pop(stale, None)


_MANAGER: AskJobManager | None = None
_MANAGER_LOCK = threading.Lock()


def get_ask_jobs() -> AskJobManager:
    """进程内单例（桌面应用共用一个对话作业面；测试可另建实例）。"""
    global _MANAGER  # noqa: PLW0603
    with _MANAGER_LOCK:
        if _MANAGER is None:
            _MANAGER = AskJobManager()
        return _MANAGER
