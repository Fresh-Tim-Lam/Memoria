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
  `cursor` 之后的新增文本，前端无需重放全文；
- **不做真取消**（M1 无取消点）：`abandon` 由前端自行实现为「丢弃后续结果 +
  停止轮询」，本模块不提供假的取消语义；
- **密钥不落本模块**：端点配置由 `llm/config.py` 读取，异常消息由
  `llm/errors.py` 保证不含凭据取值。

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

logger = logging.getLogger(__name__)

__all__ = [
    "DONE",
    "ERROR",
    "RUNNING",
    "AskJob",
    "AskJobManager",
    "get_ask_jobs",
]

#: 作业状态（前端按此三分支渲染）。
RUNNING = "running"
DONE = "done"
ERROR = "error"

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


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    """结构化错误（提交/轮询一律返回 dict，绝不向 RPC 抛裸异常）。"""
    return {"status": "error", "code": code, "message": message, **extra}


@dataclass
class AskJob:
    """一次 ask 的作业记录（含增量缓冲）。

    `parts` 由工作线程写入、RPC 线程读取，故所有访问都在 `lock` 内；
    增量文本按到达顺序拼接，`poll` 用字符下标做 cursor，不重放历史。
    """

    job_id: str
    kb_path: str
    question: str
    model: str = ""
    #: 本轮要**续接**的会话 id（前端带上上一轮 `session_id`）；None = 全新会话。
    resume_session_id: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    status: str = RUNNING
    parts: list[str] = field(default_factory=list, repr=False)
    answer: str = ""
    anchors: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    stop_reason: str = ""
    iterations: int = 0
    error: str | None = None
    code: str | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    # —— 工作线程侧 ——

    def note_delta(self, piece: str) -> None:
        """`ask(on_text=...)` 回调：追加剧增文本（空片段忽略）。"""
        if not piece:
            return
        with self.lock:
            self.parts.append(piece)

    def fail(self, error: str, code: str) -> None:
        with self.lock:
            self.status = ERROR
            self.error = error
            self.code = code
            self.finished_at = time.time()

    def succeed(self, result: Any) -> None:
        """把 `AskResult` 落进作业；`result.error` 非空时判为 error（保留已投递文本）。"""
        with self.lock:
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

    def snapshot(self, cursor: int = 0) -> dict[str, Any]:
        """轮询快照：`delta` = `cursor` 之后的新增文本，`cursor` = 已投递字符数。"""
        with self.lock:
            text = "".join(self.parts)
            start = cursor if 0 < cursor <= len(text) else 0
            out: dict[str, Any] = {
                "status": self.status,
                "job_id": self.job_id,
                "delta": text[start:],
                "cursor": len(text),
                "answer": self.answer,
                "anchors": [dict(anchor) for anchor in self.anchors],
                "tool_calls": [dict(call) for call in self.tool_calls],
                "usage": dict(self.usage),
                "session_id": self.session_id,
                "stop_reason": self.stop_reason,
                "iterations": self.iterations,
                "error": self.error,
                "code": self.code,
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
    ) -> dict:
        """校验并提交一次提问；返回 `{status:"ok", job_id}` 或结构化错误。

        `session_id` 非空 ⇒ 续聊（后端按会话文件回放历史，见 `ask()`）。
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
            if running is not None and running.status == RUNNING:
                return _error(
                    CODE_BUSY,
                    "上一个问题仍在生成（M1 无真取消），请等它结束后再提问",
                    job_id=running.job_id,
                )
            job = AskJob(
                job_id=uuid.uuid4().hex[:12],
                kb_path=kb,
                question=text,
                model=model,
                resume_session_id=resume,
            )
            self._jobs[job.job_id] = job
            self._order.append(job.job_id)
            self._active = job.job_id
            self._evict_locked()
        self._pool.submit(self._run, job)
        return {"status": "ok", "job_id": job.job_id, "job_status": RUNNING}

    def _run(self, job: AskJob) -> None:
        """工作线程：跑一次同步 ask，增量经 `on_text` 流入作业缓冲。"""
        try:
            result = ask(
                job.kb_path,
                job.question,
                model=job.model,
                session_id=job.resume_session_id,
                on_text=job.note_delta,
            )
        except Exception as exc:  # noqa: BLE001 —— 失败只影响本作业
            code = getattr(exc, "code", None) or CODE_ASK_FAILED
            logger.warning("[agent-ask] 作业 %s 失败（code=%s）", job.job_id, code)
            job.fail(str(exc), str(code))
            return
        job.succeed(result)

    # —— 查询 ——

    def poll(self, job_id: str, cursor: int = 0) -> dict:
        """轮询作业：返回增量、状态与最终产物；未知 job 返回 `unknown_job`。"""
        with self._lock:
            job = self._jobs.get(job_id) if job_id else None
        if job is None:
            return _error(CODE_UNKNOWN_JOB, "未知任务（可能已重启或已被清理）", job_id=job_id)
        try:
            offset = max(0, int(cursor))
        except (TypeError, ValueError):
            offset = 0
        return job.snapshot(offset)

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
