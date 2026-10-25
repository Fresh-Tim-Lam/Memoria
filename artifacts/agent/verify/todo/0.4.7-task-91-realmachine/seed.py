"""task-133 种子：独立测试库 + 超阈值长会话 + 隔离配置（不碰用户库/用户配置）。

产出 `<work>/seed.json`，记录会话 id、库路径、期望字符量等，供编排器与报告引用。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "src"))

from memoria.services.agent.session.store import SessionStore  # noqa: E402

WORK = Path(os.environ["T133_WORK"])
KB = WORK / "kb"
CFG = WORK / "cfg"
SID = "session-t133-realmachine"
STUB_PORT = int(os.environ.get("T133_STUB_PORT", "9599"))

USER_TEXT = "请记住第{n}条线索：这是一段用于把上下文推到压缩阈值以上的真机验证历史。" + "旧" * 760
ASSIST_TEXT = "第{n}条线索已记录。" + "答" * 780


def _long_path(path: str) -> str:
    """Windows：把 8.3 短路径展开成长路径（`LAMTIM~1` → `Lam Tim`）。失败则原样返回。"""
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(32768)
        n = ctypes.windll.kernel32.GetLongPathNameW(path, buf, 32768)  # type: ignore[attr-defined]
        return buf.value if n else path
    except Exception:  # noqa: BLE001
        return path


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    if KB.exists():
        shutil.rmtree(KB)
    if CFG.exists():
        shutil.rmtree(CFG)
    shutil.copytree(REPO / "tests" / "probe-kb", KB)
    CFG.mkdir(parents=True, exist_ok=True)

    store = SessionStore(str(KB), SID)
    store.append("session/title", {"title": "task-133 真机压缩验证"})
    turns = 20  # 40 条消息 × ~790 字符 ≈ 31_600 字符（>25_600 阈值，且 ≤40 条/32_000 字符截断上限）
    for n in range(1, turns + 1):
        store.append("user/message", {"text": USER_TEXT.format(n=n)})
        store.append("assistant/message", {"content": ASSIST_TEXT.format(n=n), "tool_calls": []})
        store.append("loop/end", {"stop_reason": "final-answer"})

    # 隔离配置：端点指向本地桩（不消耗用户真实密钥），并预置"上次会话"⇒ 面板打开即自动载入
    (CFG / "agent.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "base_url": f"http://127.0.0.1:{STUB_PORT}/v1",
                "api_key": "t133-stub",
                "model": "t133-stub",
                "timeout_s": 60,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    kb_key = os.path.normcase(os.path.abspath(str(KB))).replace("/", "\\")
    # Windows 8.3 短路径（LAMTIM~1）与长路径是**同一个目录**，但面板按字节比较键 ⇒ 两个都写上
    long_kb = _long_path(str(KB))
    kb_key_long = os.path.normcase(long_kb).replace("/", "\\")
    session_map = {kb_key_long: SID}
    if kb_key != kb_key_long:
        session_map[kb_key] = SID
    (CFG / "ui-settings.json").write_text(
        json.dumps({"agent": {"lastSessionByKb": session_map}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    from memoria.services.agent.compaction import history_chars
    from memoria.services.agent.session.history import (
        MAX_HISTORY_CHARS,
        build_history,
        conversation_messages,
        session_context_usage,
    )

    history = build_history(str(KB), SID)
    usage = session_context_usage(str(KB), SID)
    seed = {
        "session_id": SID,
        "kb": str(KB),
        "kb_key": kb_key,
        "kb_key_long": kb_key_long,
        "cfg": str(CFG),
        "turns": turns,
        "history_messages": len(history),
        "history_chars": history_chars(history),
        "context_usage": usage,
        "percent": round(usage["chars"] / usage["max_chars"] * 100),
        "default_view_roles": [item["role"] for item in conversation_messages(str(KB), SID)],
        "with_compaction_roles": [
            item["role"] for item in conversation_messages(str(KB), SID, include_compaction=True)
        ],
        "stub_port": STUB_PORT,
    }
    (WORK / "seed.json").write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: seed[k] for k in ("session_id", "history_messages", "history_chars", "percent", "stub_port")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
