"""判别力证明：把 `gate` 临时改回 v1（只改 src 一处），确认新断言**变红**，再原样还原。

步骤：
1. 备份 `plugins.py` 字节 + sha256；
2. 把 `REMOVED_TOOL_FIELDS` 里的 `"gate"` 去掉（= 把字段改回 v1）；
3. 跑 `pytest -k "gate or without_gate"` ⇒ 期望**红**（新断言有判别力）；
4. 用备份字节还原，校验 sha256 与备份一致；
5. 再跑一次 ⇒ 期望绿。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
TARGET = os.path.join(REPO, "src", "memoria", "services", "agent", "plugins.py")
BACKUP = os.path.join(tempfile.mkdtemp(prefix="plugins-backup-"), "plugins.py")


def sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def run_k(expr: str) -> tuple[int, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_agent_plugins.py", "-k", expr, "--no-header", "--tb=line"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", env=env,
    )
    tail = (proc.stdout or "").strip().splitlines()[-1:] or [""]
    return proc.returncode, tail[0]


def main() -> int:
    original_sha = sha(TARGET)
    shutil.copyfile(TARGET, BACKUP)
    print(f"[1] 备份完成 sha={original_sha[:16]}…")

    with open(TARGET, encoding="utf-8") as fh:
        src = fh.read()
    old = 'REMOVED_TOOL_FIELDS = ("gate", "constrain", "tool_schema_ref", "budget")'
    new = 'REMOVED_TOOL_FIELDS = ("constrain", "tool_schema_ref", "budget")'
    if old not in src:
        print("✗ 找不到 REMOVED_TOOL_FIELDS 定义（源码已变，判定失败）")
        return 2
    with open(TARGET, "w", encoding="utf-8", newline="") as fh:
        fh.write(src.replace(old, new, 1))
    print("[2] 已把 gate 临时改回 v1（REMOVED_TOOL_FIELDS 去掉 gate）")

    code, tail = run_k("gate or without_gate")
    print(f"[3] 临时改回后：exit={code} | {tail}")
    red_ok = code != 0

    shutil.copyfile(BACKUP, TARGET)
    restored_sha = sha(TARGET)
    print(f"[4] 已还原 sha={restored_sha[:16]}… | 与备份一致={restored_sha == original_sha}")

    code2, tail2 = run_k("gate or without_gate")
    print(f"[5] 还原后：exit={code2} | {tail2}")
    green_ok = code2 == 0

    ok = red_ok and restored_sha == original_sha and green_ok
    print(f"\n== 判别力证明: {'PASS' if ok else 'FAIL'} ==  "
          f"(改回⇒红={red_ok}, 还原一致={restored_sha == original_sha}, 还原⇒绿={green_ok})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
