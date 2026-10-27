"""追踪 read_kp 的 id 可发现性：在首次 read_kp 调用之前，哪些工具结果/消息里出现过这些 id。"""

from __future__ import annotations

import io
import json
import re

PATH = r"D:\AAA_Courses\数字通信原理\.memoria\agent\sessions\session-20261027T011706Z-0cb419b6.jsonl"
IDS = ["aliasing", "uniform-quantization", "bandpass-sampling", "ch3-summary", "pcm"]
EXACT = {i: re.compile(r"(?<![-\w])" + re.escape(i) + r"(?![-\w])") for i in IDS}


def main() -> int:
    events: list[dict] = []
    with io.open(PATH, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    first_read_kp = next(
        e for e in events
        if e.get("type") == "tool/call" and (e.get("data") or {}).get("name") == "read_kp"
    )
    print("first read_kp seq:", first_read_kp.get("seq"), "args:", (first_read_kp.get("data") or {}).get("arguments"))
    print()
    for target in IDS:
        hits = []
        for e in events:
            if e.get("seq", 0) > first_read_kp.get("seq", 0):
                break
            data = e.get("data") or {}
            name = data.get("name") or ""
            content = str(data.get("content") or "")
            blob = json.dumps(e, ensure_ascii=False)
            if name in ("read_document", "kb_overview", "outline", "grep", "snippet") and EXACT[target].search(content):
                hits.append((e.get("seq"), e.get("type"), name, EXACT[target].search(content).start()))
        print(f"{target}: {len(hits)} 处（首次 read_kp 前，在 tool 结果正文里）")
        for h in hits[:3]:
            print("   ", h)
    print()
    # 打印首次 read_kp 所在轮的完整工具序列与各结果头部
    turn_seq = first_read_kp.get("seq", 0) or 0
    print("=== 首次 read_kp 前 12 条 tool 结果（名称/长度/头部） ===")
    recent = [e for e in events if e.get("type") == "tool/result" and e.get("seq", 0) < turn_seq][-12:]
    for e in recent:
        d = e.get("data") or {}
        c = str(d.get("content") or "")
        print(f"- {d.get('name')}: chars={len(c)} head={c[:120]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
