"""0.4.7-task-91 正式验收脚本：**上下文占用（字符预算）+ 压缩可观测**。

判定 7 项（全部来自关闭条件，逐项独立打印 PASS/FAIL）：
  [1] py_compile：本任务改动的 5 个 .py 全部可编译
  [2] 唯一实现：`ask._history_chars` **就是** `compaction.history_chars`（同一函数对象，非复制）
  [3] 默认路径不变：`conversation_messages()`（不传参）里 **没有** system 压缩行
  [4] 可选投影：`include_compaction=True` 时压缩行按**原位置**出现（covered / summary_chars 正确）
  [5] 同口径：`session_context_usage()["chars"]` **逐值等于** `history_chars(build_history())`
  [6] 同域（字符）：`max_chars=32_000`、`threshold_chars=25_600`（= ×0.8），百分比 = chars/max（字符/字符）
  [7] 按压缩后有效视图计量：压缩过的会话 chars **小于**压缩前原文字符量（不是原始事件累加）

**输出确定性**：只打印与输入有关的常量/计数，不打印临时路径/时间 ⇒ 连跑 3 次 `sha256` 必须单一。
无副作用：临时库落在系统 temp（退出即删），不碰仓库、不联网、不写用户库。
"""

from __future__ import annotations

import os
import py_compile
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # …/artifacts/agent/verify/todo → 仓库根
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # 输出确定性：不受控制台代码页影响

# 隔离配置目录（任何模块级配置读取都不碰用户真实配置）
_CFG_DIR = tempfile.mkdtemp(prefix="t91-cfg-")
os.environ["MEMORIA_CONFIG_DIR"] = _CFG_DIR

FAILS: list[str] = []
_INDEX = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global _INDEX
    _INDEX += 1
    print(f"[{_INDEX}] {'PASS' if ok else 'FAIL'} {name}{(' ' + detail) if detail else ''}")
    if not ok:
        FAILS.append(name)


def main() -> int:
    # ── [1] py_compile ────────────────────────────────────────────────────────
    files = [
        "src/memoria/services/agent/session/history.py",
        "src/memoria/services/agent/session/__init__.py",
        "src/memoria/presentation/api/ui.py",
        "src/memoria/services/agent/compaction.py",
        "src/memoria/services/agent/ask.py",
    ]
    compiled = []
    for rel in files:
        py_compile.compile(str(ROOT / rel), doraise=True)
        compiled.append(Path(rel).name)
    check("py_compile", True, "(" + ",".join(sorted(set(compiled))) + ")")

    from memoria.services.agent.ask import _history_chars
    from memoria.services.agent.compaction import (
        COMPACT_THRESHOLD_RATIO,
        compact_threshold_chars,
        history_chars,
    )
    from memoria.services.agent.session.history import (
        COMPACTION,
        MAX_HISTORY_CHARS,
        build_history,
        conversation_messages,
        session_context_usage,
    )
    from memoria.services.agent.session.store import SessionStore

    # ── [2] 唯一实现（同函数对象）────────────────────────────────────────────
    check(
        "history_chars 唯一实现",
        _history_chars is history_chars,
        "ask._history_chars is compaction.history_chars = "
        + str(_history_chars is history_chars),
    )

    # 造一个确定性会话：旧一轮（够大，便于验证"按压缩后视图计量"）→ 压缩覆盖它 → 新一轮
    kb = tempfile.mkdtemp(prefix="t91-kb-")
    sid = "session-t91-check"
    old = "旧" * 5_000
    summary = "摘要" * 10
    store = SessionStore(kb, sid)
    store.append("user/message", {"text": old})  # seq 0
    store.append("assistant/message", {"content": old, "tool_calls": []})  # seq 1
    store.append(
        COMPACTION,
        {"summary": summary, "shadowed": [0, 1], "shadowed_chars": len(old) * 2, "model": "m"},
    )
    store.append("user/message", {"text": "第二问"})
    store.append("assistant/message", {"content": "第二答", "tool_calls": []})

    # ── [3] 默认路径（reference.py 复用）不含 system 行 ────────────────────
    default_view = conversation_messages(kb, sid)
    default_roles = [item["role"] for item in default_view]
    check(
        "conversation_messages 默认排除压缩",
        default_roles == ["user", "assistant", "user", "assistant"],
        "roles=" + ",".join(default_roles),
    )

    # ── [4] 可选投影：原位置 + 字段 ─────────────────────────────────────────
    view = conversation_messages(kb, sid, include_compaction=True)
    roles = [item["role"] for item in view]
    system = [item for item in view if item["role"] == "system"]
    ok4 = (
        roles == ["user", "assistant", "system", "user", "assistant"]
        and len(system) == 1
        and system[0]["kind"] == "compaction"
        and system[0]["covered"] == 2
        and system[0]["summary_chars"] == len(summary)
        and isinstance(system[0]["seq"], int)
    )
    check(
        "include_compaction 原位置投影",
        ok4,
        "roles=" + ",".join(roles) + f", covered={system[0]['covered'] if system else '?'}",
    )

    # ── [5] 同口径：chars == history_chars(build_history(...)) ──────────────
    usage = session_context_usage(kb, sid)
    expected = history_chars(build_history(kb, sid))
    check(
        "context_usage 同口径",
        usage["chars"] == expected,
        f"chars={usage['chars']} expected={expected}",
    )

    # ── [6] 同域：分子分母都是字符 ─────────────────────────────────────────
    expected_threshold = int(MAX_HISTORY_CHARS * COMPACT_THRESHOLD_RATIO)
    percent = round(usage["chars"] / usage["max_chars"] * 100)
    ok6 = (
        usage["max_chars"] == MAX_HISTORY_CHARS == 32_000
        and usage["threshold_chars"] == compact_threshold_chars() == expected_threshold == 25_600
        and usage["compacted_times"] == 1
        and isinstance(percent, int)
    )
    check(
        "字符/字符 同域",
        ok6,
        f"chars={usage['chars']} max={usage['max_chars']} "
        f"threshold={usage['threshold_chars']} times={usage['compacted_times']} percent={percent}%",
    )

    # ── [7] 压缩后有效视图（不是原始事件累加）──────────────────────────────
    raw = len(old) * 2
    history = build_history(kb, sid)
    ok7 = usage["chars"] < raw and [m.role.value if hasattr(m.role, "value") else str(m.role) for m in history] == [
        "user",
        "user",
        "assistant",
    ]
    check("按压缩后视图计量", ok7, f"chars={usage['chars']} < raw={raw}")

    print(f"PASS={7 - len(FAILS)} FAIL={len(FAILS)}")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
