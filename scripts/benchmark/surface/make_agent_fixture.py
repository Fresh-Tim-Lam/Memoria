#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""make_agent_fixture.py —— 为 agent 面板流式断言造**临时 KB 副本 + 会话夹具**

纪律（Lead 要求）：
  - **绝不污染 `docs/example/**` 与用户库**：一律先复制到 `artifacts/_realapp_fixture_kb/`
  - 注入最小 `.memoria/agent/sessions/<id>.jsonl`，含 1 条带 markdown + 公式的 assistant 响应
  - 测完可整目录删除

会话 JSONL 格式（读码自 `services/agent/session/store.py`）：
  首行 header: {"v":..., "type":"session/header", "time":ms, "data":{id,createdAt,kb,agent}}
  后续记录:    {"v":..., "seq":n, "time":ms, "type":"user/message"|"assistant/message", "data":{...}}
  user/message       => data: {text}
  assistant/message  => data: {content, tool_calls?:[]}

用法：
    python scripts/benchmark/surface/make_agent_fixture.py [--src docs/example/行政法]
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = REPO_ROOT / "artifacts" / "_realapp_fixture_kb"

SESSION_FORMAT_VERSION = 1
HEADER_TYPE = "session/header"

# 带 markdown 结构 + 行内公式 + 块级公式的 assistant 响应
ASSISTANT_MD = """## 夹具响应（最小结构）

这是**加粗**与*斜体*，行内公式 $E = mc^2$，以及代码 `inline_code`。

- 列表项一
- 列表项二

| 列A | 列B |
|---|---|
| 1 | 2 |

```python
print("fixture")
```

$$
\\int_0^1 x^2 dx = \\frac{1}{3}
$$
"""

USER_TEXT = "请解释这个知识点（夹具）"


def _now_ms() -> int:
    return int(time.time() * 1000)


def make_fixture(src_kb: Path, dest: Path = FIXTURE_DIR) -> dict:
    if not src_kb.is_dir():
        raise SystemExit("源 KB 不存在: %s" % src_kb)
    # 每次都重建，保证可复现
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_kb, dest)

    sessions_dir = dest / ".memoria" / "agent" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    sid = "fixture-session-0001"
    path = sessions_dir / ("%s.jsonl" % sid)
    t = _now_ms()

    records = [
        {
            "v": SESSION_FORMAT_VERSION,
            "type": HEADER_TYPE,
            "time": t,
            "data": {"id": sid, "createdAt": t, "kb": str(dest), "agent": "fixture"},
        },
        {
            "v": SESSION_FORMAT_VERSION,
            "seq": 0,
            "time": t + 1,
            "type": "user/message",
            "data": {"text": USER_TEXT},
        },
        {
            "v": SESSION_FORMAT_VERSION,
            "seq": 1,
            "time": t + 2,
            "type": "assistant/message",
            "data": {"content": ASSISTANT_MD, "tool_calls": []},
        },
    ]
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    return {
        "kb": str(dest),
        "session_id": sid,
        "session_path": str(path),
        "records": len(records),
        "src_kb": str(src_kb),
        "cards": _write_review_cards(dest),
    }


# 复习卡字段（读码自 services/agent/tools/kb.py:4280 `_review_normalize_card`）：
#   card_id / type / front / back / source 必备；kp_id / file 可选
#   路径：<kb>/.memoria/agent/review/cards.json（REVIEW_CARDS_REL）
REVIEW_CARDS_REL = ".memoria/agent/review/cards.json"


def _write_review_cards(dest: Path) -> dict:
    """在**夹具副本**里造 1 张复习卡（含 markdown + 行内公式），供 review modal 断言。"""
    p = dest / REVIEW_CARDS_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    cards = [
        {
            "card_id": "fixture-card-0001",
            "kp_id": "",
            "file": "",
            "type": "basic",
            "front": "夹具卡面：这是什么？行内公式 $a^2+b^2=c^2$",
            "back": "夹具卡背：\n\n- 要点一\n- 要点二\n\n**加粗**与 `code`，公式 $E=mc^2$",
            "source": "fixture:make_agent_fixture.py",
            "created_at": "2026-10-20T00:00:00Z",
        }
    ]
    doc = {"v": 1, "updated_at": "2026-10-20T00:00:00Z", "cards": cards}
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(p), "count": len(cards)}


def main() -> int:
    ap = argparse.ArgumentParser(description="造 agent 会话夹具（临时 KB 副本）")
    ap.add_argument("--src", default="docs/example/行政法", help="源 KB（相对 repo 根）")
    ap.add_argument("--dest", default=str(FIXTURE_DIR), help="夹具目录")
    args = ap.parse_args()

    src = (REPO_ROOT / args.src).resolve()
    info = make_fixture(src, Path(args.dest))
    print("[fixture] 已造夹具 KB: %s" % info["kb"])
    print("[fixture] session: %s (%d 条记录)" % (info["session_path"], info["records"]))
    # 输出 JSON 供脚本解析
    print("__FIXTURE__" + json.dumps(info, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
