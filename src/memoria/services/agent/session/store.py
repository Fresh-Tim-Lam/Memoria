# 语义移植自 deepseek-harness packages/session/session-persistence-jsonl（当前格式）
# 与 packages/session/session-format（header/event 逻辑记录）（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""会话 JSONL 存储：`<kb>/.memoria/agent/sessions/<session-id>.jsonl`。

对照上游 `dsh-session-persistence-jsonl` 的当前格式，取其可观察语义：

- **一个会话一份产物**，物理行 = 一行 JSON（上游可用行读取的 `compression: 'none'` 形态）；
- **首行是 header**（`version` / `id` / `createdAt` 等逻辑元数据），其后每行一个事件
  （`seq` / `time` / `type` / `data`）——与 `session-format` 的逻辑记录一一对应；
- **仅追加、连续 `seq`**：已提交的事件绝不重写；`seq` 从 0 起连续递增，缺口视为损坏；
- **撕裂尾部对读者不可见**：未写完的最后一行在回放时被跳过（上游由写路径截断，
  本地因为只追加且不重写，采用"跳过并在日志中说明"的等价处理）。

未移植的部分（M1 无对应需求，已在报告偏差表登记）：Zstandard 帧、祖先代际迁移链、
单写者租约与跨进程锁、崩溃轮次修复（合成 closer）、`stat`/`list` 的 revision 语义、
`session/flush` 批处理窗口（本地 `flush()` 即 fsync 屏障）。

本模块不联网、不打印；只有显式 append/flush 才写盘。
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "SESSION_FORMAT_VERSION",
    "SessionHeader",
    "SessionStore",
    "list_sessions",
    "new_session_id",
    "read_session",
    "session_file",
    "sessions_dir",
]

#: 逻辑格式版本（对齐上游 `SESSION_FORMAT_VERSION` 的角色：只写当前格式）。
SESSION_FORMAT_VERSION = 1

_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_HEADER_TYPE = "session/header"


def sessions_dir(kb_path: str) -> str:
    """会话目录：`<kb>/.memoria/agent/sessions`。"""
    return os.path.join(os.path.abspath(kb_path), ".memoria", "agent", "sessions")


def session_file(kb_path: str, session_id: str) -> str:
    """会话文件绝对路径；非法 id 直接报错（防目录穿越与冲突）。"""
    key = (session_id or "").strip()
    if not _SESSION_ID_RE.match(key):
        raise ValueError(f"非法会话 id：{session_id!r}（只允许字母数字与 . _ -）")
    return os.path.join(sessions_dir(kb_path), f"{key}.jsonl")


def new_session_id(*, now: datetime | None = None, prefix: str = "session") -> str:
    """生成会话 id：`<prefix>-<UTC 时间戳>-<随机后缀>`。"""
    moment = now or datetime.now(timezone.utc)
    stamp = moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{stamp}-{secrets.token_hex(4)}"


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


@dataclass(frozen=True, slots=True)
class SessionHeader:
    """会话 header（首行记录，不含 `seq`）。"""

    id: str
    created_at: int
    kb_path: str
    agent: str = "memoria-agent-loop"
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return {
            "v": SESSION_FORMAT_VERSION,
            "type": _HEADER_TYPE,
            "time": self.created_at,
            "data": {
                "id": self.id,
                "createdAt": self.created_at,
                "kb": self.kb_path,
                "agent": self.agent,
                **dict(self.extra),
            },
        }


def _encode(record: Mapping[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=False) + "\n"


def _decode_line(line: str) -> dict[str, Any] | None:
    text = line.strip()
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _read_all(path: str) -> list[dict[str, Any]]:
    """回放一个会话文件；撕裂尾部被跳过（读取方绝不看到撕裂记录）。"""
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    records: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        record = _decode_line(line)
        if record is None:
            if line.strip() and index == len(lines) - 1:
                logger.warning("[agent-session] 跳过撕裂尾部（%s 第 %d 行）", path, index + 1)
                continue
            raise ValueError(f"会话文件损坏：{path} 第 {index + 1} 行不是合法 JSON 对象")
        records.append(record)
    return records


def read_session(kb_path: str, session_id: str) -> list[dict[str, Any]]:
    """回放指定会话的全部记录（含 header）。"""
    return _read_all(session_file(kb_path, session_id))


def list_sessions(kb_path: str) -> list[dict[str, Any]]:
    """列出库内已有会话（按文件修改时间倒序，只读目录）。"""
    directory = sessions_dir(kb_path)
    if not os.path.isdir(directory):
        return []
    rows: list[dict[str, Any]] = []
    for name in os.listdir(directory):
        if not name.endswith(".jsonl"):
            continue
        path = os.path.join(directory, name)
        try:
            stat = os.stat(path)
        except OSError:
            continue
        rows.append(
            {
                "session_id": name[: -len(".jsonl")],
                "path": path,
                "size_bytes": stat.st_size,
                "modified_at": int(stat.st_mtime * 1000),
            }
        )
    rows.sort(key=lambda row: int(row["modified_at"]), reverse=True)
    return rows


@dataclass
class SessionStore:
    """一个会话的写句柄：append-only，从不改写历史。

    `append()` 写一行并 flush（尽力而为，对齐上游 `append` 的语义）；
    `flush()` 是 fsync 持久性屏障（对齐上游 `flush`：只有它承诺崩溃后仍在）。
    """

    kb_path: str
    session_id: str
    agent: str = "memoria-agent-loop"
    header_extra: Mapping[str, Any] = field(default_factory=dict)
    _seq: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        # `self.path`（会话文件绝对路径）在下方设定，刻意不写成注解：dataclass
        # 会把任何注解当成字段，从而破坏"带默认值字段之后不得再有必填字段"的顺序。
        self.kb_path = os.path.abspath(self.kb_path)
        self.path = session_file(self.kb_path, self.session_id)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        records = _read_all(self.path)
        header = records[0] if records and records[0].get("type") == _HEADER_TYPE else None
        if header is None:
            self._write(SessionHeader(id=self.session_id, created_at=_now_ms(), kb_path=self.kb_path,
                                      agent=self.agent, extra=self.header_extra).to_record())
            records = []
        self._seq = len([row for row in records if isinstance(row.get("seq"), int)])

    #: 会话文件绝对路径（`__post_init__` 中设定）。
    @property
    def next_seq(self) -> int:
        return self._seq

    def _write(self, record: Mapping[str, Any]) -> None:
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(_encode(record))
            handle.flush()

    def append(self, event_type: str, data: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """追加一条事件记录并返回它（`seq` 连续、`time` 为 epoch 毫秒）。"""
        kind = (event_type or "").strip()
        if not kind:
            raise ValueError("事件类型不能为空")
        record = {
            "v": SESSION_FORMAT_VERSION,
            "seq": self._seq,
            "time": _now_ms(),
            "type": kind,
            "data": dict(data or {}),
        }
        self._write(record)
        self._seq += 1
        return record

    def flush(self) -> None:
        """持久性屏障：把已追加内容 fsync 到磁盘。"""
        if not os.path.isfile(self.path):
            return
        with open(self.path, "r+", encoding="utf-8") as handle:
            handle.flush()
            os.fsync(handle.fileno())

    def replay(self) -> list[dict[str, Any]]:
        """回放本会话的全部记录（含 header）。"""
        return _read_all(self.path)

    def events(self) -> list[dict[str, Any]]:
        """只回放事件记录（跳过 header）。"""
        return [row for row in self.replay() if row.get("type") != _HEADER_TYPE]
