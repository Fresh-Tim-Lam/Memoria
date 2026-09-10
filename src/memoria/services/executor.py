"""后端维护作业执行器（G5.3 / M7b，见 docs/design/maintenance-jobs.md §3.4）。

职责：把 RPC 触发的重活（全库 validate/audit 等）搬出 RPC 线程——
**提交即返回 job_id**，执行在线程池；同 kind+key 的重复提交按 replace 合并
（顶替仍排队中的旧作业）；保留最近结果供前端轮询。

与 M3 的关系：资源级串行仍由作业自身加锁（如词法索引用 `_lex_lock`），
本执行器只负责「不阻塞 RPC」与「合并/去重」，不改变既有锁语义。

用法：
    from memoria.services.executor import get_executor
    ex = get_executor()
    r = ex.submit("validate_kb", lambda: svc.validate_kb(), key=svc.kb_path)
    ex.status(r["job_id"])  # {"status": "queued|running|done|error|superseded", ...}
"""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

PENDING = "queued"
RUNNING = "running"
DONE = "done"
ERROR = "error"
SUPERSEDED = "superseded"


class MaintenanceExecutor:
    """线程池 + 作业表：提交即返回，执行在后台。"""

    def __init__(self, max_workers: int = 2, keep: int = 64) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="maint")
        self._lock = threading.RLock()
        self._jobs: dict[str, dict] = {}
        self._order: list[str] = []
        self._keep = keep
        self._counters = {"scheduled": 0, "executed": 0, "merged": 0, "superseded_run": 0, "error": 0}

    # ── 提交 ────────────────────────────────────────────────────────────────

    def submit(self, kind: str, fn: Callable[[], Any], *, key: str = "", replace: bool = True) -> dict:
        """登记作业并立即返回；同 kind+key 的 queued 旧作业被顶替（replace）。"""
        with self._lock:
            if replace and key:
                for job in self._jobs.values():
                    if job["kind"] == kind and job["key"] == key and job["status"] == PENDING:
                        job["status"] = SUPERSEDED
                        self._counters["merged"] += 1
            job_id = uuid.uuid4().hex[:12]
            self._jobs[job_id] = {
                "id": job_id,
                "kind": kind,
                "key": key,
                "status": PENDING,
                "submitted_at": time.time(),
                "started_at": None,
                "finished_at": None,
                "result": None,
                "error": None,
            }
            self._order.append(job_id)
            self._counters["scheduled"] += 1
            self._evict_locked()
        self._pool.submit(self._run, job_id, fn)
        return {"status": "ok", "job_id": job_id, "job_status": PENDING, "kind": kind}

    def _run(self, job_id: str, fn: Callable[[], Any]) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if job["status"] == SUPERSEDED:
                self._counters["superseded_run"] += 1
                return
            job["status"] = RUNNING
            job["started_at"] = time.time()
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 —— 作业失败只影响自身
            with self._lock:
                job["status"] = ERROR
                job["error"] = str(exc)
                job["finished_at"] = time.time()
                self._counters["error"] += 1
            return
        with self._lock:
            job["result"] = result
            job["status"] = DONE
            job["finished_at"] = time.time()
            self._counters["executed"] += 1

    # ── 查询 ────────────────────────────────────────────────────────────────

    def status(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return {"status": "error", "message": "未知作业"}
            return self._public(job)

    def latest(self, kind: str, key: str | None = None) -> dict | None:
        with self._lock:
            for job_id in reversed(self._order):
                job = self._jobs.get(job_id)
                if job and job["kind"] == kind and (key is None or job["key"] == key):
                    return self._public(job)
        return None

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "queued": sum(1 for j in self._jobs.values() if j["status"] == PENDING),
                "running": sum(1 for j in self._jobs.values() if j["status"] == RUNNING),
            }

    def counters(self) -> dict:
        with self._lock:
            return dict(self._counters)

    def wait(self, job_id: str, timeout: float = 60.0, poll: float = 0.05) -> dict:
        """测试/命令行辅助：阻塞至作业结束（RPC 路径不应使用）。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            st = self.status(job_id)
            if st.get("status") in (DONE, ERROR, SUPERSEDED):
                return st
            time.sleep(poll)
        return {"status": "timeout", "job_id": job_id}

    @staticmethod
    def _public(job: dict) -> dict:
        out: dict = {"job_id": job["id"], "kind": job["kind"], "key": job["key"], "status": job["status"]}
        if job["started_at"]:
            end = job["finished_at"] or time.time()
            out["elapsed_ms"] = round((end - job["started_at"]) * 1000, 1)
        if job["status"] == DONE:
            out["result"] = job["result"]
        if job["status"] == ERROR:
            out["error"] = job["error"]
        return out

    def _evict_locked(self) -> None:
        while len(self._order) > self._keep:
            self._jobs.pop(self._order.pop(0), None)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False)


_EXECUTOR: MaintenanceExecutor | None = None
_EXECUTOR_LOCK = threading.Lock()


def get_executor() -> MaintenanceExecutor:
    """进程内单例（桌面应用共用；测试可另建实例）。"""
    global _EXECUTOR  # noqa: PLW0603
    with _EXECUTOR_LOCK:
        if _EXECUTOR is None:
            _EXECUTOR = MaintenanceExecutor()
        return _EXECUTOR
