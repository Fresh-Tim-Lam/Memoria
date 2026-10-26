"""task-183 探针 fixture 生成：复制 tests/probe-kb 到本目录 kb/，并写入固定会话。

会话形状与 `services/agent/session/history.py` 一致：
  session/header → user/message → assistant/message → loop/end(usage)
其中 loop/end.usage 含 cache_read_tokens=60 / cache_miss_tokens=40 / prompt=100
⇒ 面板载入该会话后，缓存格悬停明细必须出现 60 / 40 / 60%。
运行：python artifacts/agent/verify/todo/agent-panel-cache-indicator/make_fixture.py
"""
import io
import json
import os
import shutil
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", ".."))
SRC_KB = os.path.join(REPO, "tests", "probe-kb")
KB = os.path.join(HERE, "kb")
CONFIG = os.path.join(HERE, "config")
SID = "task183-cache-probe"


def main() -> int:
    if os.path.isdir(KB):
        shutil.rmtree(KB)
    shutil.copytree(SRC_KB, KB)
    os.makedirs(CONFIG, exist_ok=True)
    sdir = os.path.join(KB, ".memoria", "agent", "sessions")
    os.makedirs(sdir, exist_ok=True)
    now = int(time.time() * 1000)
    records = [
        {"v": 1, "type": "session/header",
         "data": {"id": SID, "created_at": now, "kb_path": KB, "agent": "memoria-agent-loop"}},
        {"v": 1, "seq": 1, "time": now, "type": "user/message",
         "data": {"text": "缓存命中率探针：这一轮用了多少缓存？"}},
        {"v": 1, "seq": 2, "time": now, "type": "assistant/message",
         "data": {"content": "这是 task-183 探针会话的固定回答（用于验证输入框下方悬停可见 hit/miss/rate 口径）。"}},
        {"v": 1, "seq": 3, "time": now, "type": "loop/end",
         "data": {"stop_reason": "final-answer",
                  "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110,
                            "cache_read_tokens": 60, "cache_miss_tokens": 40, "estimated": False}}},
    ]
    with io.open(os.path.join(sdir, SID + ".jsonl"), "w", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("fixture ready:", KB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())