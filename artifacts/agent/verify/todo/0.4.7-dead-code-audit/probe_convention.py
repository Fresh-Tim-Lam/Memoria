"""task-134 只读取证（二）：所有「落点纪律」注释的出现点，及其相对 IIFE 门面 `return {` 的位置。

回答两个问题：
1. 这条纪律**最初**是对的吗？（注释块当时是否在 return 之前）
2. 从哪个 commit 起出现「`})();` 之前」变体，它当时是否已经错（在 return 之后 ⇒ 出生即死）。
"""

from __future__ import annotations

import subprocess
import sys

FILE = "src/memoria/ui/static/app/js/agent-panel.js"
REPO = r"D:\AAA_Jupyter\Memoria"


def git(*args: str) -> str:
    out = subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise RuntimeError(out.stderr[-400:])
    return out.stdout


def lines_of(commit: str) -> list[str]:
    return git("show", f"{commit}:{FILE}").splitlines()


def main() -> int:
    # 所有改动过该文件的 commit（reverse 时间序）
    log = git("log", "--reverse", "--format=%h", "--", FILE).split()
    print(f"commits touching file: {len(log)}")
    rows = []
    for c in log:
        try:
            lines = lines_of(c)
        except Exception:  # noqa: BLE001
            continue
        return_lines = [i + 1 for i, l in enumerate(lines) if l.rstrip() == "  return {"]
        first_return = return_lines[0] if return_lines else None
        markers = []
        for i, l in enumerate(lines):
            if "落点纪律" in l:
                markers.append((i + 1, "`})();` 之前" in l, l.strip()[:70]))
        if markers:
            rows.append((c, first_return, len(lines), markers))
    for c, ret, total, markers in rows:
        date = git("show", "-s", "--format=%ci", c).strip()
        subj = git("show", "-s", "--format=%s", c).strip()[:60]
        verdict = []
        for ln, wrong_variant, text in markers:
            if ret is None:
                verdict.append(f"L{ln}{'[WRONG-VARIANT]' if wrong_variant else ''}: no-return")
            else:
                verdict.append(f"L{ln}{'[WRONG-VARIANT]' if wrong_variant else ''}: {'BBEFORE' if ln < ret else 'AFTER'} return L{ret}")
        print(f"{c} {date} | {subj}")
        print("   ", "; ".join(verdict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
