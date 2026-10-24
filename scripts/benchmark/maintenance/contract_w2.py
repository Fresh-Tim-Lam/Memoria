#!/usr/bin/env python
"""W2 读后写守卫 + R-S2-1 接缝 的可测 fixture（`contract_w2`）。

## 为什么这是"必红 fixture"而不是 `assert raises`

我们这一轮反复栽在"看起来有守卫其实没有"（gate 死字段 / constrain 死字段 / `heading=None` 静默回 `sections[0]`）。
所以这里的每一条都**真的构造违规路径**，再断言它被拒绝或放行 —— 判别力来自"它会在错误的实现上红"：

- **`test_section_then_write_allowed`**：在 R-S2-1 修复**之前**，这条是 `FS_NOT_OBSERVED`（红）。
  `section` 不喂观察表 + 不线程 session_id ⇒ 模型"读完一节就写"被自己的读闸挡下。
  修复后必须 `None`（放行）。**若这条回到红，说明接缝修复被回退了。**
- **`test_snippet_then_write_not_observed`**：`snippet` 是片段窗口（同 grep/glob），**不构成"看过这个文件"**，
  读后写仍必须 `FS_NOT_OBSERVED`。若这条"变绿"（放行），说明有人给 snippet 顺手补了观察 —— 也是回退。
- **`test_no_read_write_rejected`**：未任何读就写 ⇒ `FS_NOT_OBSERVED`（守卫本身在）。
- **`test_external_change_stale`**：读后被外部改写 ⇒ `FS_STALE_VERSION`（版本号用真实 `rel_version`，
  不是空串 —— `record_read(version="")` 会被误判成 STALE，见 R-S2-1 附注）。

## 用法

    python scripts/benchmark/maintenance/contract_w2.py [--json out.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))

# ── 密封性（R-S1A-3）──
os.environ.setdefault("MEMORIA_CONFIG_DIR", tempfile.mkdtemp(prefix="memoria-cfg-"))

from memoria.services.agent import observation  # noqa: E402
from memoria.services.agent.tools.kb import build_kb_tools  # noqa: E402

RESULTS: list[dict] = []


def check(name: str, ok: bool, detail: str, falsifier: str = "") -> None:
    RESULTS.append({"name": name, "ok": bool(ok), "detail": detail, "falsifier": falsifier})


def _ops(rel: str = "d.md") -> list[dict]:
    return [
        {"op": "replace_lines", "op_id": "w1", "file": rel,
         "range": {"start": 4, "end": 4}, "text": "新正文", "expect": "小节正文"}
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    kb = tempfile.mkdtemp(prefix="memoria-w2-")
    with open(os.path.join(kb, "d.md"), "w", encoding="utf-8", newline="") as fh:
        fh.write("# 甲\n甲第一行\n\n## 小节\n小节正文\n")
    sid = "sess-w2"
    tools = {t.name: t for t in build_kb_tools(kb, session_id=sid)}
    ops = _ops()

    # ① 未任何读 ⇒ 拒
    verdict = observation.gate_ops(kb, sid, ops)
    check(
        "W2 未任何读就写 ⇒ FS_NOT_OBSERVED",
        verdict is not None and verdict[0] == observation.CODE_NOT_OBSERVED,
        f"verdict={verdict}",
        "放行 ⇒ 读后写守卫完全失效",
    )

    # ② section 读后写 ⇒ 必须放行（R-S2-1 修复；修复前这里是 FS_NOT_OBSERVED）
    observation.clear(kb, sid)
    tools["section"].handler({"file": "d.md", "heading": "小节"})
    verdict = observation.gate_ops(kb, sid, ops)
    check(
        "W2 read_section 后写 ⇒ 放行（R-S2-1 接缝；修复前=FS_NOT_OBSERVED）",
        verdict is None,
        f"verdict={verdict}",
        "仍是 FS_NOT_OBSERVED ⇒ 接缝修复被回退，S1 收益被读闸自吞",
    )

    # ③ outline 读后写 ⇒ 放行
    observation.clear(kb, sid)
    tools["outline"].handler({"file": "d.md"})
    verdict = observation.gate_ops(kb, sid, ops)
    check(
        "W2 read_outline 后写 ⇒ 放行",
        verdict is None,
        f"verdict={verdict}",
    )

    # ④ snippet 读后写 ⇒ 仍拒（片段不构成"看过"）
    observation.clear(kb, sid)
    tools["snippet"].handler({"file": "d.md", "query": "小节正文"})
    verdict = observation.gate_ops(kb, sid, ops)
    check(
        "W2 read_snippet 后写 ⇒ 仍 FS_NOT_OBSERVED（片段≠看过）",
        verdict is not None and verdict[0] == observation.CODE_NOT_OBSERVED,
        f"verdict={verdict}",
        "放行 ⇒ 有人给 snippet 补了观察，把'片段=看过'写死成错误口径",
    )

    # ⑤ 读后被外部改 ⇒ STALE（用真实版本号，非空串）
    observation.clear(kb, sid)
    tools["section"].handler({"file": "d.md", "heading": "小节"})
    with open(os.path.join(kb, "d.md"), "w", encoding="utf-8", newline="") as fh:
        fh.write("# 甲\n甲第一行（外部改动）\n\n## 小节\n小节正文\n")
    verdict = observation.gate_ops(kb, sid, ops)
    check(
        "W2 读后被外部改 ⇒ FS_STALE_VERSION",
        verdict is not None and verdict[0] == observation.CODE_STALE_VERSION,
        f"verdict={verdict}",
    )

    payload = {
        "schema": "contract-w2/v1",
        "guard": "observation.gate_ops (FS_NOT_OBSERVED / FS_NOT_FOUND / FS_STALE_VERSION)",
        "seam_fix": "R-S2-1: read_section / read_outline 记观察；read_snippet 不记；session_id 线程",
        "assertions": RESULTS,
        "passed": all(r["ok"] for r in RESULTS),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    payload["artifactSha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    for r in RESULTS:
        print(f"  [{'OK' if r['ok'] else 'FAIL'}] {r['name']}: {r['detail']}")
        if not r["ok"] and r["falsifier"]:
            print(f"        falsifier: {r['falsifier']}")
    print(f"\n== RESULT: {'PASS' if payload['passed'] else 'FAIL'} ==  (sha256 {payload['artifactSha256'][:16]}…)")

    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(REPO, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        print(f"wrote: {args.json}")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
