"""写路径的原子替换：`os.replace` + **有界退避重试**（只认 Windows 瞬时锁）。

**为什么需要**（实测，2026-09-20）：`tests/test_agent_apply.py` 连续多次写同一个 `.md`
时**偶发** `PermissionError: [WinError 5] 拒绝访问`（`tmp → 正文` 的 `os.replace`）；
同一文件连跑三次得到 1 挂 / 10 过 / 3 挂，单跑该用例必过，**重跑从不复现**。
`_write_body` 的句柄泄漏已排除（`with` + `flush` + `fsync` 之后才 `replace`；写的是
**另一个** `.tmp` 路径）⇒ 判定为同进程的后台词法索引线程 / 外部 AV、索引器**瞬时持有目标文件**。

**口径**（人已拍板，2026-09-20）：

1. **只**对 `WinError 5`（拒绝访问）/ `WinError 32`（共享冲突）重试 —— 其它 `OSError`
   （磁盘满、路径不存在、只读卷…）**立刻抛**，不被这里掩盖。
2. **有界**：`5 × 50 ms`（上限 250 ms），只吸收"瞬时"，不给真故障拖延。
3. **可见**：每次重试都 `logger.warning`（带 winerror、第几次、源/目标），
   `pytest -q` 或 `[job]` 日志里能直接看到"是被重试救回来的"。
4. **耗尽仍抛**：重试只是多给几次机会，绝不把失败吞成静默成功（写路径 fail-closed）。
"""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)

#: 可重试的 Windows 错误码（`ERROR_ACCESS_DENIED` / `ERROR_SHARING_VIOLATION`）；
#: 非 Windows 上 `OSError` 没有 `winerror`（取到 `None`）⇒ 本函数等价于裸 `os.replace`。
TRANSIENT_WINERRORS = (5, 32)

#: 重试次数与每次间隔（总上限 = `ATTEMPTS` × `DELAY` = 250 ms）
ATTEMPTS = 5
DELAY = 0.05


def replace_with_retry(src: str, dst: str) -> None:
    """`os.replace(src, dst)`，对 Windows 瞬时锁有界退避重试；耗尽后**原样抛出**。"""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            os.replace(src, dst)
            return
        except OSError as exc:
            if getattr(exc, "winerror", None) not in TRANSIENT_WINERRORS or attempt >= ATTEMPTS:
                raise
            logger.warning(
                "replace 被瞬时锁住（winerror=%s），%.0fms 后重试 %d/%d：%s → %s",
                exc.winerror,
                DELAY * 1000,
                attempt,
                ATTEMPTS,
                src,
                dst,
            )
            time.sleep(DELAY)
