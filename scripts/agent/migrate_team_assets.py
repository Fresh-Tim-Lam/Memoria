"""migrate_team_assets.py —— 团队资产从 artifacts/agent/ 迁到 team/（入库）

理由：`artifacts/` 被 .gitignore 整个忽略 ⇒ 团队"单一事实源"零版本历史
（2026-10-23 已两次因无历史吃亏：hw-003 fixture 被覆盖无法恢复；
 Lead 重导出快照写错字段名也无法回滚）。

搬什么（**团队资产**）：
  artifacts/agent/agents.json              → team/agents.json
  artifacts/agent/dispatch-log.jsonl       → team/dispatch-log.jsonl
  artifacts/agent/team-board-snapshot.json → team/team-board-snapshot.json
  artifacts/agent/prompts/**               → team/prompts/**
  artifacts/agent/curator/**               → team/curator/**

不搬（**产物**，量大且可再生产）：
  artifacts/agent/verify/**    （109 份验证报告）
  artifacts/agent/*.json 诊断快照

用法：
  python scripts/agent/migrate_team_assets.py --check    # 只报告
  python scripts/agent/migrate_team_assets.py --apply    # 执行
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OLD = REPO / "artifacts" / "agent"
NEW = REPO / "team"

# 逐条：旧相对路径 → 新相对路径（目录用 / 结尾）
MOVES = [
    ("agents.json", "agents.json"),
    ("dispatch-log.jsonl", "dispatch-log.jsonl"),
    ("team-board-snapshot.json", "team-board-snapshot.json"),
    ("prompts/", "prompts/"),
    ("curator/", "curator/"),
]

# 引用替换表：只替换「团队资产」路径，**不碰 artifacts/agent/verify**
REPLACEMENTS = [
    ("artifacts/agent/agents.json", "team/agents.json"),
    ("artifacts/agent/team-board-snapshot.json", "team/team-board-snapshot.json"),
    ("artifacts/agent/dispatch-log.jsonl", "team/dispatch-log.jsonl"),
    ("artifacts/agent/prompts/", "team/prompts/"),
    ("artifacts/agent/curator/", "team/curator/"),
    ("artifacts\\agent\\agents.json", "team\\agents.json"),
    ("artifacts\\agent\\team-board-snapshot.json", "team\\team-board-snapshot.json"),
    ("artifacts\\agent\\dispatch-log.jsonl", "team\\dispatch-log.jsonl"),
    ("artifacts\\agent\\prompts\\", "team\\prompts\\"),
    ("artifacts\\agent\\curator\\", "team\\curator\\"),
    # 脚本里的父目录推导（Path 拼接形态）
    ('REPO / "artifacts" / "agent"', 'REPO / "team"'),
]

TEXT_EXT = {".py", ".md", ".json", ".mjs", ".js", ".ps1", ".yaml", ".yml", ".txt"}
SKIP_DIRS = {"artifacts", "node_modules", ".git", "Package", ".venv", "__pycache__"}


def plan_moves() -> list[tuple[Path, Path]]:
    out = []
    for src_rel, dst_rel in MOVES:
        src = OLD / src_rel
        if not src.exists():
            continue
        out.append((src, NEW / dst_rel))
    return out


def do_moves(check_only: bool) -> None:
    NEW.mkdir(parents=True, exist_ok=True)
    for src, dst in plan_moves():
        kind = "DIR " if src.is_dir() else "FILE"
        print("  %s %s -> %s" % (kind, src.relative_to(REPO), dst.relative_to(REPO)))
        if check_only:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            print("    ⚠ 目标已存在，跳过（不覆盖）")
            continue
        shutil.move(str(src), str(dst))


def iter_text_files():
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            p = Path(root) / f
            if p.suffix.lower() in TEXT_EXT:
                yield p


def do_replace(check_only: bool) -> int:
    changed = 0
    for p in iter_text_files():
        # 不改自己（否则 REPLACEMENTS 字面量会被自替换）
        if p.name == "migrate_team_assets.py":
            continue
        try:
            txt = io.open(p, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        orig = txt
        for old, new in REPLACEMENTS:
            if old in txt:
                txt = txt.replace(old, new)
        if txt != orig:
            changed += 1
            print("  edit %s" % p.relative_to(REPO))
            if not check_only:
                io.open(p, "w", encoding="utf-8", newline="").write(txt)
    return changed


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    check = args.check

    print("=== 1. 迁移文件 ===")
    do_moves(check)
    print("=== 2. 更新引用 ===")
    n = do_replace(check)
    print("  %d 个文件引用已更新" % n)
    if check:
        print("\n（--check 模式，未改动任何文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
