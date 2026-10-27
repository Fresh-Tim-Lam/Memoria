"""找 KP id 在会话里【第一次出现】的位置：证明 read_kp 的 id 从哪来（可发现性证据）。"""

from __future__ import annotations

import io
import json

PATH = r"D:\AAA_Courses\数字通信原理\.memoria\agent\sessions\session-20261027T011706Z-0cb419b6.jsonl"
TARGETS = ["aliasing", "uniform-quantization", "ch3-summary", "bandpass-sampling", "pcm"]


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
    for target in TARGETS:
        for event in events:
            blob = json.dumps(event, ensure_ascii=False)
            if target not in blob:
                continue
            data = event.get("data") or {}
            print(f"FIRST {target!r} @ type={event.get('type')} seq={event.get('seq')}")
            pos = blob.find(target)
            print("   ctx:", blob[max(0, pos - 220): pos + 220].replace("\n", " "))
            print()
            break
        else:
            print(f"{target!r}: NOT FOUND")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
