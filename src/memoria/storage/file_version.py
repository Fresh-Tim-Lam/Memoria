"""写冲突保护：**文件版本令牌**（乐观并发）+ 两个 RPC 的等量委托入口。

口径（人已拍板，2026-09-20；见 `docs/design/agent-plugin-design.md §9`）：

1. **盘上版本 = 唯一权威**：任何写者写之前必须确认"我读到的版本 == 盘上版本"。
2. **人的当下操作最高**：agent 的批量写（apply）不得趁人正在编辑时抢写。
3. **冲突由人明示决定**：不一致就**拒写**并回报结构化错误，由前端弹「重载 / 以我为准」；
   **agent 不自动合并、不静默赢**，人的过期 buffer 也**不自动赢**。
4. 一切冲突**可见**（不静默）。

**为什么单独成模块**：`services/document.py` 与 `presentation/api/ui.py` 被大量
`file:line` 锚点引用（零行漂移是硬要求）⇒ 版本逻辑集中放这里，两处 RPC 用**等量替换**
委托进来（`ui.py:167` 的 `load_document`、`ui.py:200` 的 `save_document`），
`document.py` **一行未动**。

**版本取值**：文件字节的 `sha256`（内容相等 ⇒ 不算冲突；我们自己的写会返回新版本让前端跟进）。
缺文件回 `""`（调用方的"期望版本"为 `""` 即"允许在该文件尚不存在时写"）。
"""

from __future__ import annotations

import hashlib
import os
from typing import Any


def file_version(path: str) -> str:
    """文件内容版本（`sha256` 十六进制）；文件不存在或不可读回 `""`。"""
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def rel_version(kb_path: str | None, rel_path: str) -> str:
    """库内相对路径的版本（`kb_path` 为空 ⇒ `""`）。"""
    if not kb_path:
        return ""
    return file_version(os.path.join(kb_path, rel_path))


def with_version(doc: Any, kb_path: str | None, rel_path: str) -> Any:
    """给 `load_document()` 的结果**追加** `version` 字段（**只增不改**，旧读者忽略即可）。

    非 ok / 非 dict 一律原样返回 —— 委托入口不改变任何既有语义。
    """
    if isinstance(doc, dict) and doc.get("status") == "ok":
        doc["version"] = rel_version(kb_path, rel_path)
    return doc


def guard_save(service: Any, rel_path: str, body: str, base_version: str = "") -> dict:
    """带版本校验的保存：不一致 ⇒ **拒写**并回报 `stale_write`（不改盘上内容）。

    `base_version` 为空串 ⇒ **不做校验**（既有调用方的旧行为逐字不变）。
    成功时在返回值里追加 `version` = 写后新版本，供调用方更新自己的基线。
    """
    kb_path = getattr(service, "kb_path", None)
    want = (base_version or "").strip()
    if want and kb_path:
        current = rel_version(kb_path, rel_path)
        if current != want:
            return {
                "status": "error",
                "code": "stale_write",
                "message": "文件已被其它窗口或智能体修改：本次保存基于过期版本，未写入",
                "expected_version": want,
                "current_version": current,
            }
    result = service.save_document(rel_path, body)
    if isinstance(result, dict) and result.get("status") == "ok" and kb_path:
        result["version"] = rel_version(kb_path, rel_path)
    return result
