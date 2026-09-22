# 语义移植自 deepseek-harness packages/fs/fs-observation-policy（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""读后写守卫：**未读过的文件不许改**，读过之后被外部改动也不许改（`fs-observation-policy` 的本地版）。

上游口径（`fs/fs-observation-policy/README.md`）：

| 上游 | 本地 |
|---|---|
| 观察态是"**先验观察记录**"：`unseen` / `confirmed absent` / `present at a version` | 同一套三态：`{rel: (present, version)}`，`version` = 文件内容的 `sha256` |
| `write`：新建可以；**覆盖未读过的已存在文件 ⇒ 拒**；未读 ⇒ 降级为 `createIfAbsent`；已读 ⇒ `replaceIfVersion` | 本地 `create_file` op（新建）**不要求**观察，**本批自己新建出来的文件**同样不要求（同批后面给它建点 / 挂链写的是模型自己刚给的正文，见 `write_targets()`）；其余 op（改正文 / KP 元数据 / 改名 / 删整篇）**必须** `present@version` |
| `edit`：未读 ⇒ `FS_NOT_OBSERVED`；读到"不存在" ⇒ `FS_NOT_FOUND` | 同码同义（本地唯一的写工具 `propose_write` 走 `edit` 口径） |
| 读后被改 ⇒ `FS_STALE_VERSION`（+「re-read, then retry」） | 同码：观察到的 `sha256` ≠ 当前 `sha256` |
| **读一个不存在的路径 = 确认不存在**（授权之后的 guarded create，并防并发创建者） | `read_document` 的 `NOT_FOUND` 也记一条 `present=False` |
| **不跨会话存活**：resume 后必须重读 | 进程内、按 `(库根, 会话)` 记账；新进程/新会话 ⇒ 空表（**不落盘**） |
| Actor 无 agent 会话 ⇒ **永远过不了闸** | 无 `session_id` 时用 `AUTO_SESSION_ID`（`agent-auto`）当 owner ⇒ 同样要"先读再写" |

**为什么要有它**：写机制自 2026-09-21 起"全线放开"（`propose_write` 调用内直接落盘），而本地此前的
兜底只有**内容级**守卫（正文 op 的 `expect` 逐字比对 + apply 的 `base_versions`）—— 它挡得住"按旧文本改写"，
挡不住"**没读就凭印象写 KP 元数据**"（`upsert_kp` / `attach_links` 不带 `expect`）。本模块把那条
"先观察、再改写"的闸补上（`docs/design/dsh-agent-port.md` §5.1 的 gap 清单第 ① 条：**写能力上线前必须补**）。

**偏差（如实登记）**：① 上游由 `fs/*` 事件闸 + provider 的原子 compare-and-swap 实现，本地没有事件层，
闸就落在**工具处理器**（`propose_write` 的 `_bound`）里，比较-写之间不是原子的（单写者 + 事务锁已覆盖）；
② 上游的 owner 是 agent 会话对象，本地用 `session_id` 字符串；③ 本地把 `read_kp` 也算一次观察
（上游只认 `read`），因为 `read_kp` 确实给出该文件的正文片段；`search_kb` / `grep` / `glob` **不算**
（只给指针与片段，不构成"看过这个文件"）。
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Iterable, Mapping
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "CODE_NOT_OBSERVED",
    "CODE_NOT_FOUND",
    "CODE_STALE_VERSION",
    "AUTO_OWNER",
    "clear",
    "gate_ops",
    "record_absent",
    "record_read",
    "session_owner",
    "write_targets",
]

#: 稳定错误码（与上游同名；`tools/kb.py` 直接用它们给 `error_text()`）。
CODE_NOT_OBSERVED = "FS_NOT_OBSERVED"
CODE_STALE_VERSION = "FS_STALE_VERSION"
CODE_NOT_FOUND = "FS_NOT_FOUND"

#: 缺省 owner：调用方没给 `session_id`（CLI / 测试）时与 `propose_write` 的审计归属同一口径。
AUTO_OWNER = "agent-auto"

_lock = threading.RLock()
#: `(库根绝对路径, owner)` → `{相对路径: (present, version)}`。**进程内、不落盘**：进程重启即空表
#: （= 上游"观察态不跨会话存活，resume 后须重读"）。条数随会话数增长，但每个会话只记它读过的文件，
#: 桌面端一个进程里会话数有限 ⇒ 不做淘汰（与 `approval_bridge` 同性质的运行期状态）。
_STATE: dict[tuple[str, str], dict[str, tuple[bool, str]]] = {}


def session_owner(session_id: str | None) -> str:
    """owner 键：`session_id` 去空白；空则回落到 `AUTO_OWNER`（与写入审计同一口径）。"""
    return str(session_id or "").strip() or AUTO_OWNER


def _key(kb_path: str, owner: str) -> tuple[str, str]:
    return (os.path.abspath(kb_path or ""), owner)


def record_read(
    kb_path: str,
    session_id: str | None,
    rel_path: str,
    *,
    present: bool = True,
    version: str = "",
) -> None:
    """记一次观察：`present=True` 记"此刻是这一版"，`present=False` 记"此刻不存在"（上游同口径）。"""
    rel = str(rel_path or "").strip().replace("\\", "/")
    if not rel or rel.endswith("/"):
        return
    owner = session_owner(session_id)
    with _lock:
        _STATE.setdefault(_key(kb_path, owner), {})[rel] = (bool(present), str(version or ""))


def record_absent(kb_path: str, session_id: str | None, rel_path: str) -> None:
    """记一次"读到不存在"（`read_document` 的 `NOT_FOUND`）：授权之后的 `create_file`，并防并发创建者。"""
    record_read(kb_path, session_id, rel_path, present=False, version="")


def clear(kb_path: str, session_id: str | None = None) -> None:
    """清掉某库（或某库某会话）的观察表；测试与将来的"重开会话"用。"""
    with _lock:
        if session_id is None:
            for key in [k for k in _STATE if k[0] == os.path.abspath(kb_path or "")]:
                _STATE.pop(key, None)
            return
        _STATE.pop(_key(kb_path, session_owner(session_id)), None)


def write_targets(ops: Iterable[Mapping[str, Any]]) -> list[str]:
    """写工具参数里**需要"读过"的目标文件**（相对路径，去重保序）。

    两类目标**不进**这份表：

    1. `create_file` 那一行本身 —— 它是**新建**（上游 `write` 的新建路径不要求观察；已存在与否交给
       计划编译器）；
    2. **本批自己刚建出来的文件** —— op 按顺序执行，`create_file` 之后那些"给新文件建点 / 挂链 /
       改正文"的 op 写的是**模型自己在这一批里给出的正文**，不存在"凭印象改一个没看过的文件"的风险；
       这与 `plan._View`（校验期把新文件种进文件集）是**同一套批内视图**口径。

    其余 op（改正文 / KP 元数据 / 插图 / 改名 / 删整篇）都落在"编辑已存在文件"口径上，必须读过。
    """
    rows = [row for row in ops if isinstance(row, Mapping)]
    created = {
        str(row.get("file") or "").strip().replace("\\", "/")
        for row in rows
        if str(row.get("op") or "").strip() == "create_file"
    }
    out: list[str] = []
    for row in rows:
        if str(row.get("op") or "").strip() == "create_file":
            continue
        rel = str(row.get("file") or "").strip().replace("\\", "/")
        if rel and rel not in created and rel not in out:
            out.append(rel)
    return out


def gate_ops(
    kb_path: str,
    session_id: str | None,
    ops: Iterable[Mapping[str, Any]],
    *,
    current_version=None,
) -> tuple[str, str] | None:
    """写前闸：返回 `(code, message)` 表示**该拒**，`None` 表示放行。

    - 未读过（`unseen`）⇒ `FS_NOT_OBSERVED`
    - 读过但当时不存在（`confirmed absent`）⇒ `FS_NOT_FOUND`（上游同码）
    - 读过、但现在内容版本不同（外部改动）⇒ `FS_STALE_VERSION`

    `current_version` 可注入（`rel -> sha256`），缺省用 `storage/file_version.rel_version()`。
    """
    owner = session_owner(session_id)
    targets = write_targets(ops)
    if not targets:
        return None
    with _lock:
        seen = dict(_STATE.get(_key(kb_path, owner)) or {})
    if current_version is None:
        from memoria.storage.file_version import rel_version

        current_version = lambda rel: rel_version(kb_path, rel)  # noqa: E731 —— 局部注入，不引模块级状态
    for rel in targets:
        if rel not in seen:
            return (
                CODE_NOT_OBSERVED,
                f"还没有读过 {rel} —— 不能凭印象改它。请先用 `read_document` 读一遍这个文件"
                "（拿到**当前**行号与逐字原文），再重提这一批。",
            )
        present, observed = seen[rel]
        if not present:
            return (
                CODE_NOT_FOUND,
                f"读的时候 {rel} 还不存在 —— 要新建它请用 `create_file`；"
                "若现在已经有这个文件了，请先 `read_document` 读一遍再改。",
            )
        now = str(current_version(rel) or "")
        if not now:
            return (
                CODE_STALE_VERSION,
                f"{rel} 在读过之后被删掉或读不到了 —— 请重新 `read_document` 确认现状，再重提这一批。",
            )
        if now != observed:
            return (
                CODE_STALE_VERSION,
                f"{rel} 在你读过之后又被改过了（内容已变）—— 请**重新** `read_document` 读一遍，"
                "按新的行号与原文重提这一批（别照着记忆改）。",
            )
    return None
