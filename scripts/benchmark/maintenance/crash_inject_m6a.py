#!/usr/bin/env python3
"""G4 M6a 崩溃注入：临时副本库上循环保存 + 随机时刻杀进程，校验无半包。

原理：正文写为 tmp + os.replace（barrier 默认）。在子进程循环大文件保存期间
随机杀进程，随后校验正式 .md 必为「旧完整内容」或「新完整内容」之一，
绝不半包/空文件；遗留 .tmp 允许且不影响重开。不动真实数据。

用法：python scripts/benchmark/maintenance/crash_inject_m6a.py [--attempts 20]
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

_HDR = "# A\n"
_LINE_A = "内容A-完整校验段落\n"
_LINE_B = "内容B-完整校验段落\n"
_PAY_N = 60_000
PAYLOAD_A = _HDR + (_LINE_A * _PAY_N)   # ~1.3MB
PAYLOAD_B = _HDR + (_LINE_B * _PAY_N)

_CHILD = """import os, sys, time
sys.path.insert(0, @SRC@)
kb = @KB@
from memoria.services.document import DocumentService
svc = DocumentService(); svc.kb_path = kb; svc._cache = {}
H = @H@; LA = @LA@; LB = @LB@; N = @N@
PAYLOAD_A = H + LA * N; PAYLOAD_B = H + LB * N
payloads = (PAYLOAD_A, PAYLOAD_B)
i = 0
while True:
    svc.save_document("a.md", payloads[i % 2])
    i += 1
    time.sleep(0.002)
"""


def run_one(attempt: int, kb: Path, child_src: Path) -> None:
    (kb / "a.md").write_text(PAYLOAD_A, encoding="utf-8")
    child_src.write_text(
        _CHILD
        .replace("@SRC@", repr(str(SRC)))
        .replace("@KB@", repr(str(kb)))
        .replace("@H@", repr(_HDR))
        .replace("@LA@", repr(_LINE_A))
        .replace("@LB@", repr(_LINE_B))
        .replace("@N@", repr(_PAY_N)),
        encoding="utf-8",
    )
    child = subprocess.Popen(
        [sys.executable, str(child_src)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # 在子进程写入期间随机时刻强杀
    time.sleep(0.003 + (attempt % 7) * 0.004)
    child.terminate()
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=5)
    raw = (kb / "a.md").read_text(encoding="utf-8")
    assert raw in (PAYLOAD_A, PAYLOAD_B), (
        f"attempt {attempt}: 正文不完整/损坏 len={len(raw)} first={raw[:40]!r}"
    )
    # 重开（新实例 load_document 应可解析；同进程不同实例模拟重启读盘）
    from memoria.services.document import DocumentService

    svc2 = DocumentService(); svc2.kb_path = str(kb); svc2._cache = {}
    doc = svc2.load_document("a.md")
    assert doc.get("status") == "ok", doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempts", type=int, default=20)
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="m6a-crash-"))
    child_src = tmp / "child.py"
    try:
        for i in range(a.attempts):
            run_one(i, tmp, child_src)
            print(f"attempt {i}: PASS（正文完整、重开可读）")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"CRASH INJECT PASS（{a.attempts} 次全部无半包）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
