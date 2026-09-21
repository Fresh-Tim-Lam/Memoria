# 设计来源（权威）：`docs/design/agent-capabilities.md` §2.3.2 第 8 步「审计 append」；
# 口径：`docs/design/agent-plugin-design.md` §9（写冲突）与 §5（实现记录）。

"""写模块的**审计事件**（第二片 ③ 的一半）：把写动作与会话记录同源落盘（**log-only**）。

**为什么写成会话事件**：本产品"会话即审计" —— `SessionStore` 的 JSONL 是对话自身的权威记录，
回放（`history._replay`）对未知 `type` **直接跳过**、`compaction.event_chars()` 计 0、语义抽取也不含它
⇒ 追加新事件类型**不改请求体、不动 KV 前缀、不影响回放**（同 `session/title` 的既有性质）。

**事件类型（只增不改）**：

| type | 何时 | 关键字段 |
|---|---|---|
| `capability/apply` | 一次 plan 的**落地尝试**（成功 / 被拒 / 失败回滚都记） | `status`、`code?`、`txid`、`dir`、`backup{txid,files,bytes}`、`files[]`、`applied[]`、`rolled_back?`、`intent?` |
| `capability/undo` | 撤销一个批次成功 | `txid`、`files[]`、`verified` |
| `capability/force_save` | 用户明示「以我为准」覆盖（人机 UI） | `rel_path`、`txid`、`backup_dir` |

**fail-open 但如实**：审计发生在**写已完成之后**（§2.3.2 第 8 步在四原语之后）⇒ 审计失败
**绝不能回滚已落盘的写入**，但也**不许静默** —— 一律返回结构化结果，由调用方放进返回值里。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

EVENT_APPLY = "capability/apply"
EVENT_UNDO = "capability/undo"
EVENT_FORCE_SAVE = "capability/force_save"


def append(kb_path: str | None, session_id: str | None, event_type: str, payload: Mapping[str, Any]) -> dict:
    """向会话追加一条审计事件；**不抛**，任何失败都返回结构化结果。

    `{status:"ok", seq, type}` = 已落盘；`{status:"skipped", reason}` = 没有会话可写
    （如测试或人机手动路径未带会话）—— **skipped 不算错误**，但要如实带出来；
    `{status:"error", message}` = 写失败（调用方仍应继续，不该回滚已完成的写入）。
    """
    if not kb_path or not session_id:
        return {"status": "skipped", "reason": "no_session"}
    try:
        from memoria.services.agent.session.store import SessionStore

        store = SessionStore(str(kb_path), str(session_id))
        record = store.append(event_type, dict(payload))
        store.flush()  # 审计的即时性靠它（append 已尽力 flush，这里再上一道屏障）
    except (OSError, ValueError) as e:
        return {"status": "error", "message": str(e)}
    return {"status": "ok", "seq": record.get("seq"), "type": event_type}
