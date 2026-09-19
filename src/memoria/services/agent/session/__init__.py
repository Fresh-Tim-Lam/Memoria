# 语义移植自 deepseek-harness packages/session/session-persistence + session-format（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""会话持久化（JSONL）：仅追加的会话事件日志。

| 模块 | 上游 | 职责 |
|---|---|---|
| `store.py` | `session-persistence` + `session-persistence-jsonl`（当前格式）+ `session-format` | 会话 id、header、逐行追加与回放 |
| `history.py` | （本地新增，M1c） | 把会话事件**语义回放**成可再发的消息序列 / 渲染视图 |

只取**当前格式**：上游的 `session-format-v0-to-v1/v1-to-v2/v2-to-v3` 迁移链
与 Zstandard 压缩、单写者租约、崩溃修复（`interruptedTurnClosers`）均未移植
（M1 无并发会话、无历史代际）。事实源位置由用户拍板：`<kb>/.memoria/agent/sessions/*.jsonl`。
"""

from __future__ import annotations

from memoria.services.agent.session.history import (
    MAX_HISTORY_CHARS,
    MAX_HISTORY_MESSAGES,
    SESSION_SCAN_MAX_BYTES,
    build_history,
    conversation_messages,
    summarize_events,
    summarize_session,
    summarize_session_file,
)
from memoria.services.agent.session.reference import (
    MAX_REFERENCES,
    REFERENCE_MAX_BYTES,
    SESSION_REFERENCE_SCHEME,
    SessionReferenceError,
    build_snapshot,
    decode_session_uri,
    encode_session_uri,
    format_session_mention,
    list_candidates,
    parse_session_references,
)
from memoria.services.agent.session.store import (
    SESSION_FORMAT_VERSION,
    SessionHeader,
    SessionStore,
    list_sessions,
    new_session_id,
    read_session,
    session_file,
    sessions_dir,
)

__all__ = [
    "MAX_HISTORY_CHARS",
    "MAX_HISTORY_MESSAGES",
    "MAX_REFERENCES",
    "REFERENCE_MAX_BYTES",
    "SESSION_FORMAT_VERSION",
    "SESSION_REFERENCE_SCHEME",
    "SESSION_SCAN_MAX_BYTES",
    "SessionHeader",
    "SessionReferenceError",
    "SessionStore",
    "build_history",
    "build_snapshot",
    "conversation_messages",
    "decode_session_uri",
    "encode_session_uri",
    "format_session_mention",
    "list_candidates",
    "list_sessions",
    "new_session_id",
    "parse_session_references",
    "read_session",
    "session_file",
    "sessions_dir",
    "summarize_events",
    "summarize_session",
    "summarize_session_file",
]
