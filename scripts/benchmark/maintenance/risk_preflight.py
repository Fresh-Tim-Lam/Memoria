#!/usr/bin/env python3
"""单向门操作前置检查（risk-management.md §4 协议 A 的自动化部分）。

用法：
    # 默认检查（src 干净 + HEAD + 无必需基线）
    python scripts/benchmark/maintenance/risk_preflight.py --operation "P6a"

    # 指定必需基线 + 已知的非本项目脏文件
    python scripts/benchmark/maintenance/risk_preflight.py \
        --operation "P6a renderPreview 切 render-core" \
        --require-baseline artifacts/baseline/s_render_frozen \
        --require-baseline artifacts/baseline/p5_perf_frozen \
        --allow-dirty-src src/memoria/services/agent/ask_stream.py

退出码：
    0  全部通过（可以开始）
    2  有缺口（不得开始，按输出逐项补齐）

设计依据：docs/guides/risk-management.md §4 协议 A。
只做"能不能开始"的机械检查；pre-mortem / 人类确认这类判断项不在此脚本内。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _run(args: list[str]) -> tuple[int, str]:
    """返回**未 strip** 的 stdout —— 调用方自行决定 strip 方式。

    ⚠️ 2026-10-21 踩过的坑：曾在这里 `.strip()`，而 `git status --porcelain` 的
    首行形如 `" M src/..."`（前导空格是状态位的一部分）⇒ 整体 strip 会吃掉首行
    前导空格 ⇒ 后续 `ln[3:]` 少切一个字符 ⇒ 路径变成 `rc/...`。
    教训与今日其它 bug 同族：**解析器写错，而检查器本身没被检查**。
    故本文件提供 `--self-test` 验证路径解析。
    """
    proc = subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "")


def _git(*args: str) -> tuple[int, str]:
    return _run(["git", *args])


def parse_porcelain_path(line: str) -> str:
    """把 `git status --porcelain` 的一行解析成路径（纯函数，可自测）。

    格式：`XY<空格>PATH`（X/Y 为状态位，可能都是空格）⇒ 路径从第 4 个字符起。
    但若行长度不足 4，退化为 strip。
    """
    if len(line) >= 4 and line[2] == " ":
        return line[3:].strip().replace("\\", "/")
    return line.strip().replace("\\", "/")


def check_head() -> tuple[bool, str]:
    code, out = _git("rev-parse", "--short", "HEAD")
    txt = out.strip()
    if code != 0 or not txt:
        return False, "无法获取 HEAD（不是 git 仓库？）"
    return True, txt


def check_src_clean(allow: list[str]) -> tuple[bool, str]:
    code, out = _git("status", "--porcelain", "--", "src/")
    if code != 0:
        return False, "git status 失败"
    lines = [ln for ln in out.splitlines() if ln.strip()]
    if not lines:
        return True, "src/ 干净"
    allowed = {p.replace("\\", "/").strip() for p in allow}
    dirty = []
    for ln in lines:
        norm = parse_porcelain_path(ln)
        if norm in allowed:
            continue
        dirty.append(norm)
    if dirty:
        return False, "src/ 有未归属的未提交改动：" + "、".join(sorted(dirty))
    return True, "src/ 干净（" + str(len(lines)) + " 项已声明为非本项目改动）"


def check_baseline(paths: list[str]) -> tuple[bool, str]:
    if not paths:
        return True, "未指定必需基线（如本操作需要基线，请用 --require-baseline）"
    missing = []
    for p in paths:
        full = REPO_ROOT / p
        if not full.exists():
            missing.append(p + "（不存在）")
        elif full.is_dir() and not any(full.iterdir()):
            missing.append(p + "（空目录）")
    if missing:
        return False, "必需基线缺失：" + "、".join(missing)
    return True, "基线齐全：" + "、".join(paths)


def check_git_depth() -> tuple[bool, str]:
    """回滚需要历史；浅克隆会失去可恢复性。"""
    code, out = _git("rev-parse", "--is-shallow-repository")
    if code == 0 and out.strip() == "true":
        return False, "仓库是浅克隆（shallow），删除的文件可能无法从 history 恢复"
    return True, "非浅克隆，删除的文件可从 history 恢复"


def self_test() -> int:
    """自检：证明路径解析对。**检查器本身也要被检查**（今日教训）。"""
    cases = [
        (" M src/memoria/services/agent/ask_stream.py", "src/memoria/services/agent/ask_stream.py"),
        ("?? src/memoria/ui/static/app/js/new-file.js", "src/memoria/ui/static/app/js/new-file.js"),
        ("MM src/a.py", "src/a.py"),
        (" D src/b.py", "src/b.py"),
        ("A  src/c.py", "src/c.py"),
    ]
    failed = 0
    for raw, want in cases:
        got = parse_porcelain_path(raw)
        ok = got == want
        print("  [" + ("OK  " if ok else "FAIL") + "] " + repr(raw) + " -> " + repr(got))
        if not ok:
            print("         期望: " + repr(want))
            failed += 1
    print("")
    if failed:
        print("[self-test] " + str(failed) + " 项失败 —— 路径解析有 bug，检查器不可信")
        return 2
    print("[self-test] 全部通过（" + str(len(cases)) + " 项）")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="单向门操作前置检查（risk-management.md §4 协议 A）")
    ap.add_argument("--operation", help="要执行的操作名（写进输出，便于留痕）")
    ap.add_argument("--require-baseline", action="append", default=[], help="必需的基线目录（可重复）")
    ap.add_argument("--allow-dirty-src", action="append", default=[], help="已声明归属的 src/ 脏文件（可重复）")
    ap.add_argument("--self-test", action="store_true", help="自检路径解析（检查器本身也要被检查）")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    if not args.operation:
        ap.error("--operation 必填（或用 --self-test）")

    print("[preflight] 操作：" + args.operation)

    results: list[tuple[str, bool, str]] = []

    ok, msg = check_head()
    results.append(("HEAD 可记录", ok, msg))
    head = msg if ok else ""

    ok, msg = check_src_clean(args.allow_dirty_src)
    results.append(("src/** 干净或有归属", ok, msg))

    ok, msg = check_baseline(args.require_baseline)
    results.append(("必需基线存在", ok, msg))

    ok, msg = check_git_depth()
    results.append(("回滚历史可用", ok, msg))

    failed = False
    for name, ok, msg in results:
        mark = "OK  " if ok else "FAIL"
        print("  [" + mark + "] " + name + " — " + msg)
        if not ok:
            failed = True

    print("")
    if failed:
        print("[preflight] 不可开始：按上面 FAIL 项逐项补齐（见 docs/guides/risk-management.md §4）")
        return 2

    print("[preflight] 全部通过。起始 commit = " + head)
    print("[preflight] 仍需人工完成：pre-mortem（§5）、回滚计划（§6）、人类确认（R0/R1 时）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
