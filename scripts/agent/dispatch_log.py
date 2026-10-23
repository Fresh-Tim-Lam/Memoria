#!/usr/bin/env python3
"""派发日志（P3）：让「谁真的在干活」可验证。

append-only JSONL：每次 `spawn_teammate` / `send_message` / 收口 后由 Lead 追加一条。
Curator 用它判 `active`（V2/V3 的可复跑证据）。

用法
----
    python scripts/agent/dispatch_log.py append --actor lead --target executor-x --phase spawn \
        --task task-80 --desc "mapper 嵌套支持"
    python scripts/agent/dispatch_log.py append --actor lead --target executor-x --phase done \
        --task task-80 --outcome pass --report artifacts/agent/verify/xx.md
    python scripts/agent/dispatch_log.py check            # 人类可读，FAIL ⇒ 退出码 1
    python scripts/agent/dispatch_log.py check --json     # 机器可读
    python scripts/agent/dispatch_log.py --selftest       # 自测：绿/红路径都必须验证

字段
----
必需：ts / actor / phase（phase ∈ spawn|message|done|retire|backfill）
可选：target / task / desc / outcome / report / evidence / source

写入磁盘路径：artifacts/agent/dispatch-log.jsonl（append-only；禁止改写历史行）
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG = REPO_ROOT / "artifacts" / "agent" / "dispatch-log.jsonl"
PHASES = ("spawn", "message", "done", "retire", "backfill")
REQUIRED_FIELDS = ("ts", "actor", "phase")
MAX_AGE_DAYS = 7


def now_iso() -> str:
    """本地时区的 ISO-8601 秒级时间戳。"""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def append_entry(path: Path, entry: dict) -> None:
    """追加一条记录；父目录不存在时创建。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_entries(path: Path) -> tuple[list[dict], list[dict]]:
    """读取全部记录；返回 (合法记录, 坏行)。坏行不中断读取（审计要能看见损坏）。"""
    entries: list[dict] = []
    bad: list[dict] = []
    if not path.exists():
        return entries, bad
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            bad.append({"line": lineno, "error": str(exc)})
            continue
        if not isinstance(obj, dict):
            bad.append({"line": lineno, "error": "not-a-json-object"})
            continue
        entries.append(obj)
    return entries, bad


def parse_ts(value: str) -> datetime | None:
    """解析 ISO-8601（允许 Z 后缀）；无法解析返回 None。"""
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def check(path: Path, max_age_days: int = MAX_AGE_DAYS) -> dict:
    """校验日志：存在、可解析、字段齐全、时间可读、最近一条不超过 max_age_days。"""
    problems: list[dict] = []
    entries, bad = read_entries(path)
    if not path.exists():
        problems.append({"check": "exists", "detail": f"{path} 不存在（尚未记录任何派发）"})
    if bad:
        problems.append({"check": "json", "detail": bad})
    for lineno, entry in enumerate(entries, 1):
        missing = [field for field in REQUIRED_FIELDS if field not in entry]
        if missing:
            problems.append({"check": "fields", "line": lineno, "missing": missing})
        phase = entry.get("phase")
        if phase not in PHASES:
            problems.append({"check": "phase", "line": lineno, "value": phase})
    latest = None
    stamps = [ts for ts in (parse_ts(str(entry.get("ts", ""))) for entry in entries) if ts is not None]
    if stamps:
        latest = max(stamps)
        now = datetime.now(timezone.utc)
        latest_utc = latest.astimezone(timezone.utc)
        if now - latest_utc > timedelta(days=max_age_days):
            problems.append({
                "check": "recency",
                "latest": latest.isoformat(),
                "max_age_days": max_age_days,
                "detail": f"最近一条派发记录已超过 {max_age_days} 天",
            })
    elif entries:
        problems.append({"check": "recency", "detail": "没有可解析的 ts"})
    return {
        "ok": not problems,
        "path": str(path),
        "count": len(entries),
        "bad_lines": bad,
        "latest": latest.isoformat() if latest is not None else None,
        "max_age_days": max_age_days,
        "problems": problems,
    }


def build_entry(args: argparse.Namespace) -> dict:
    """按 CLI 参数构造一条记录（只写入显式提供的字段）。"""
    entry: dict = {
        "ts": args.ts or now_iso(),
        "actor": args.actor,
        "phase": args.phase,
        "target": args.target,
    }
    optional = {
        "task": args.task,
        "desc": args.desc,
        "outcome": args.outcome,
        "report": args.report,
        "evidence": args.evidence,
        "source": args.source,
    }
    entry.update({key: value for key, value in optional.items() if value is not None})
    return entry


def selftest() -> int:
    """自测：绿路径必须绿、红路径必须红（防「假通过」）。"""
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="dispatch-log-selftest-") as tmp:
        path = Path(tmp) / "dispatch-log.jsonl"

        def expect(name: str, condition: bool) -> None:
            if not condition:
                failures.append(name)

        # 红 1：文件不存在
        expect("missing-file-must-fail", check(path)["ok"] is False)

        # 绿：两条成对记录
        append_entry(path, {"ts": now_iso(), "actor": "lead", "phase": "spawn", "target": "executor"})
        append_entry(path, {"ts": now_iso(), "actor": "executor", "phase": "done", "target": "lead", "outcome": "pass"})
        ok_report = check(path)
        expect("paired-entries-must-pass", ok_report["ok"] is True)
        expect("count-must-be-2", ok_report["count"] == 2)

        # 红 2：最近记录过期
        old_path = Path(tmp) / "old.jsonl"
        append_entry(old_path, {"ts": "2026-01-01T00:00:00+08:00", "actor": "lead", "phase": "spawn", "target": "x"})
        expect("stale-log-must-fail", check(old_path)["ok"] is False)

        # 红 3：坏 JSON 行
        bad_path = Path(tmp) / "bad.jsonl"
        bad_path.write_text('{"ts":"2026-10-23T00:00:00+08:00","actor":"lead","phase":"spawn"}\nnot-json\n', encoding="utf-8")
        expect("corrupt-line-must-fail", check(bad_path)["ok"] is False)

        # 红 4：缺字段 / 非法 phase
        fields_path = Path(tmp) / "fields.jsonl"
        append_entry(fields_path, {"actor": "lead", "phase": "nonsense"})
        expect("missing-fields-must-fail", check(fields_path)["ok"] is False)

    if failures:
        print(f"FAIL: {', '.join(failures)}")
        return 1
    print("PASS: dispatch_log.py selftest (4 red fixtures red, 2 assertions green)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="派发日志 append / check / selftest")
    parser.add_argument("--selftest", action="store_true", help="运行自测并退出")
    parser.add_argument("--log", default=str(DEFAULT_LOG), help="日志路径（默认 artifacts/agent/dispatch-log.jsonl）")
    sub = parser.add_subparsers(dest="command")

    append_parser = sub.add_parser("append", help="追加一条派发记录")
    append_parser.add_argument("--actor", required=True, help="执行派发的 agent（lead / teammate 名）")
    append_parser.add_argument("--target", required=True, help="被派发/接收的 agent")
    append_parser.add_argument("--phase", required=True, choices=PHASES, help="派发阶段")
    append_parser.add_argument("--task", help="关联任务 id（如 task-80）")
    append_parser.add_argument("--desc", help="一句话说明")
    append_parser.add_argument("--outcome", help="done 阶段的结论（pass/fail/blocked）")
    append_parser.add_argument("--report", help="产出物路径（报告/提交）")
    append_parser.add_argument("--evidence", help="额外证据路径")
    append_parser.add_argument("--source", help="来源标记（如 backfill:team-board-snapshot.json）")
    append_parser.add_argument("--ts", help="显式时间戳（回填历史用；缺省取当前时间）")

    check_parser = sub.add_parser("check", help="校验日志是否可追溯")
    check_parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    check_parser.add_argument("--max-age-days", type=int, default=MAX_AGE_DAYS, help="最近记录的允许最大天数")

    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.command == "append":
        entry = build_entry(args)
        append_entry(Path(args.log), entry)
        print(json.dumps(entry, ensure_ascii=False))
        return 0
    if args.command == "check":
        report = check(Path(args.log), args.max_age_days)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            status = "PASS" if report["ok"] else "FAIL"
            print(f"{status}: {report['count']} 条派发记录, latest={report['latest']}, path={report['path']}")
            for problem in report["problems"]:
                print(f"  - {problem}")
        return 0 if report["ok"] else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
