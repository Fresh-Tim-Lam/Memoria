"""task-134 只读取证（三）：
1. `askRecordText` / `toolDisplayDetail`（当前在 return 之后的 hoisted 函数）何时被追加、当时在 return 前还是后；
2. 当前文件里 A' 函数（引用死区 const 的 hoisted 函数）的**调用点**是否也全在死区（决定 TDZ 是"潜伏"还是"已触发"）。
"""

from __future__ import annotations

import subprocess
import sys

FILE = "src/memoria/ui/static/app/js/agent-panel.js"
REPO = r"D:\AAA_Jupyter\Memoria"
HEAD = "22b4391c"


def git(*args: str) -> str:
    out = subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise RuntimeError(out.stderr[-400:])
    return out.stdout


def main() -> int:
    print("== 1) hoisted 函数被追加时的位置（相对当时的门面 return）==")
    for needle in ("askRecordText", "toolDisplayDetail", "intakeResourceFiles", "isResourceFile"):
        commits = git("log", "--reverse", "--format=%h", "-S", needle, "--", FILE).split()
        print(f"-- {needle}: {len(commits)} commits")
        for c in commits[:3]:
            lines = git("show", f"{c}:{FILE}").splitlines()
            rets = [i + 1 for i, l in enumerate(lines) if l.rstrip() == "  return {"]
            hits = [i + 1 for i, l in enumerate(lines) if needle in l]
            date = git("show", "-s", "--format=%ci", c).strip()
            pos = []
            for h in hits[:3]:
                pos.append(f"L{h}{'<' if rets and h < rets[0] else '>' if rets else '?'}return{rets[0] if rets else '-'}")
            print(f"   {c} {date}: {pos}")

    print("\n== 2) 当前 HEAD 的 A' 函数调用点（死区 = 7086-7282）==")
    text = git("show", f"{HEAD}:{FILE}")
    lines = text.splitlines()
    dead_lo, dead_hi = 7086, 7282
    names = ["isResourceFile", "uploadResource", "intakeResourceFiles", "resourceNote", "removeResourceAt", "clearResourceItems", "resourceErrorText"]
    for name in names:
        calls = []
        for i, line in enumerate(lines, 1):
            if name in line and "function " + name not in line and "function " + name + "(" not in line:
                calls.append((i, "DEAD" if dead_lo <= i <= dead_hi else "LIVE", line.strip()[:80]))
        live = [c for c in calls if c[1] == "LIVE"]
        print(f"  {name}: calls={len(calls)} live_calls={len(live)}")
        for c in calls[:6]:
            print(f"     L{c[0]} [{c[1]}] {c[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
