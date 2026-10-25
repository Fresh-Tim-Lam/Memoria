"""task-134 只读取证：`agent-panel.js` 的 IIFE 门面 `return {` 演进 + 错误约定注释的历史来源。"""

from __future__ import annotations

import re
import subprocess
import sys

FILE = "src/memoria/ui/static/app/js/agent-panel.js"
REPO = r"D:\AAA_Jupyter\Memoria"


def git(*args: str) -> str:
    out = subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise RuntimeError(out.stderr[-500:])
    return out.stdout


def show(commit: str) -> list[str]:
    return git("show", f"{commit}:{FILE}").splitlines()


def probe(commit: str) -> dict:
    lines = show(commit)
    facade = [i + 1 for i, l in enumerate(lines) if l.rstrip() == "  return {"]
    iife_close = [i + 1 for i, l in enumerate(lines) if l.strip() == "})();"]
    wrong_comment = [i + 1 for i, l in enumerate(lines) if "})();` 之前" in l]
    doc_resource = [i + 1 for i, l in enumerate(lines) if "intakeResourceFiles" in l]
    return {
        "total": len(lines),
        "facade_return_lines": facade,
        "iife_close_lines": iife_close,
        "wrong_comment_lines": wrong_comment,
        "doc_resource_lines": doc_resource[:3],
    }


def main() -> int:
    commits = [
        "2f9a88f9",
        "8818ce16",
        "af44c1f0",
        "1fe97fa7",
        "b2310f88",
        "a68ab655",
        "22b4391c",  # HEAD（Lead 已提交 task-133/task-92 后）
    ]
    print("== 指定 commit 的结构探针 ==")
    for c in commits:
        try:
            r = probe(c)
        except Exception as exc:  # noqa: BLE001
            print(c, "ERR", exc)
            continue
        date = git("show", "-s", "--format=%ci", c).strip()
        subj = git("show", "-s", "--format=%s", c).strip()
        print(f"{c} {date}\n  {subj}\n  {r}")

    print("\n== agent-panel.js 历史：最早出现 IIFE 级 `  return {` 的 commit ==")
    log = git("log", "--reverse", "--format=%h", "--", FILE).split()
    first = None
    for c in log:
        try:
            r = probe(c)
        except Exception:  # noqa: BLE001
            continue
        if r["facade_return_lines"]:
            first = (c, r)
            break
    if first:
        c, r = first
        print(c, r)
        print("  subj:", git("show", "-s", "--format=%s", c).strip())
        print("  date:", git("show", "-s", "--format=%ci", c).strip())
    else:
        print("未找到")
    print("commit 总数(触及该文件):", len(log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
