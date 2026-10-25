"""task-134 真机验证 · 种子：独立测试库 + 隔离配置（指向本地 SSE 桩）。"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(REPO / "src"))

WORK = Path(os.environ["T134_WORK"])
KB = WORK / "kb"
CFG = WORK / "cfg"
STUB_PORT = int(os.environ.get("T134_STUB_PORT", "9599"))


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    for d in (KB, CFG):
        if d.exists():
            shutil.rmtree(d)
    shutil.copytree(REPO / "tests" / "probe-kb", KB)
    CFG.mkdir(parents=True, exist_ok=True)
    (CFG / "agent.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "base_url": f"http://127.0.0.1:{STUB_PORT}/v1",
                "api_key": "t134-stub",
                "model": "t134-stub",
                "timeout_s": 60,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    meta = {"kb": str(KB), "cfg": str(CFG), "stub_port": STUB_PORT}
    (WORK / "seed.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
