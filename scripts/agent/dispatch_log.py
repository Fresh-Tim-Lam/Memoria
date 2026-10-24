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
      mode / modeExplicit（task-107：spawn 的模式决策；路由表见 `docs/guides/lead-dispatch-rules.md §1.3b`）
      corrects（更正协议，仅 backfill 用）

**L9 模式决策（task-107，2026-10-24）**
`AGENTS.md §0.5 L9`：spawn 必须**显式**选 `mode`（`mechanical`/`standard`/`deep`/`creator`）；
不传会被 DSH 静默默认为 `standard` = "没做决策"。因此本工具对 `phase=spawn` **fail-closed**：
- 缺 `--mode` ⇒ **拒绝写入**（与 `done 必须带 report` 同风格）；
- 若确实无法判断，用 `--mode-explicit false` 显式留下「未决定」痕迹（`modeExplicit=false`，不伪造 mode）；
- `--mode` 默认 `modeExplicit=true`；与 `--mode-explicit false` 同时用 ⇒ 拒绝（自相矛盾）。
`check` 对历史 spawn 行（无 mode 字段）只报 **WARN**（append-only，不回改历史），并给出可判定/不可判定计数。

**fail-closed 纪律（2026-10-23 第三轮新增）**
`--phase done` **必须**带 `--report`：完成声明如果没有绑定产物，事后无法验证「做完了没」
（Lead 错误清单 A5 的结构：该记的没记，且不报错）。要记「做完了但确实无产物」，用
`--no-report-reason "<为什么没有可验证产物>"` 显式声明，禁止静默留空。

**更正协议（append-only 的更正方式）**
历史行的路径失效（如资产迁移）不能改历史行，改为追加一条带 corrects 的 backfill：
    python scripts/agent/dispatch_log.py append --actor lead --target X --phase backfill \
        --corrects-line 7 --corrects-field report \
        --corrects-old artifacts/a/b.json --corrects-new team/a/b.json \
        --desc "team_assets 迁移后路径失效，按更正协议指向新路径"
`team_audit.py::silent_failure` 会验证 `--corrects-new` 指向的产物**真实存在**；
若更正本身也指不到东西，仍然 FAIL。

写入磁盘路径：team/dispatch-log.jsonl（append-only；禁止改写历史行）
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG = REPO_ROOT / "team" / "dispatch-log.jsonl"   # 2026-10-23 迁入版本控制（原 artifacts/agent/ 被 gitignore）
# 2026-10-24: when the DSH Agent Teams plugin's auditLog points at this same file
# (team/dispatch-log.jsonl) the plugin also writes the last three phases. Omitting them
# here would make our own `check` reject the plugin's rows and turn one shared fact source
# into a false "corrupt log" finding. Plugin side of truth: agent-team/src/audit.ts
# -> TeamAuditPhase.
# KEEP THIS TUPLE FREE OF INLINE COMMENTS: team_audit.py's contract_drift parser reads it
# as a flat literal list, and an inline comment gets mistaken for a list item.
PHASES = ("spawn", "message", "done", "retire", "backfill", "preflight", "reassign", "contract")
REQUIRED_FIELDS = ("ts", "actor", "phase")
# task-107：DSH 四档（源码 tool-agent-team/src/index.ts:448 mode 默认 standard）；路由表见 §1.3b
VALID_MODES = ("mechanical", "standard", "deep", "creator")
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
    """校验日志：存在、可解析、字段齐全、时间可读、最近一条不超过 max_age_days。

    task-107：对 `phase=spawn` 额外核对模式决策（缺 mode / 非法 mode / 缺 modeExplicit）——
    历史行（append-only）只报 **warnings**，不影响 `ok`（不阻断历史），但必须**可见**。
    """
    problems: list[dict] = []
    warnings: list[dict] = []
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
        # task-107 / L9：spawn 的模式决策可判定性（warnings，不阻断历史行）
        if phase == "spawn":
            mode = entry.get("mode")
            explicit = entry.get("modeExplicit")
            if mode is None and explicit is not False:
                warnings.append({
                    "check": "mode_missing", "line": lineno, "target": entry.get("target"),
                    "detail": "spawn 缺 mode 字段（历史记录无法判定是否做过模式决策；"
                              "新记录必须 --mode，或用 --mode-explicit false 显式留痕）",
                })
            elif mode is not None and mode not in VALID_MODES:
                warnings.append({"check": "mode_invalid", "line": lineno, "value": mode,
                                 "detail": f"mode={mode!r} 不在 DSH 四档 {list(VALID_MODES)}"})
            elif mode is not None and explicit is not True:
                warnings.append({"check": "mode_not_explicit", "line": lineno, "target": entry.get("target"),
                                 "detail": "有 mode 但 modeExplicit 不是 true（无法证明是显式决策）"})
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
    spawn_count = sum(1 for entry in entries if entry.get("phase") == "spawn")
    judgeable = 0
    for entry in entries:
        if entry.get("phase") != "spawn":
            continue
        if entry.get("mode") in VALID_MODES and entry.get("modeExplicit") is True:
            judgeable += 1  # 显式选了模式
        elif entry.get("mode") is None and entry.get("modeExplicit") is False:
            judgeable += 1  # 显式「未决定」也是一种可判定状态（不伪造 mode）
    mode_known = judgeable
    return {
        "ok": not problems,
        "path": str(path),
        "count": len(entries),
        "bad_lines": bad,
        "latest": latest.isoformat() if latest is not None else None,
        "max_age_days": max_age_days,
        "problems": problems,
        "warnings": warnings,
        "mode_coverage": {"spawn": spawn_count, "judgeable": mode_known,
                          "unknown": spawn_count - mode_known},
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
    # task-107 / L9：mode 与 modeExplicit（spawn 必填；其它 phase 可选）
    mode = getattr(args, "mode", None)
    mode_explicit = getattr(args, "mode_explicit", None)
    if mode is not None:
        entry["mode"] = mode
    if mode_explicit is not None:
        entry["modeExplicit"] = mode_explicit == "true"
    elif mode is not None and entry["phase"] == "spawn":
        # 显式传了 --mode 即视为显式决策；无需再额外传 true
        entry["modeExplicit"] = True
    if getattr(args, "no_report_reason", None):
        entry["no_report_reason"] = args.no_report_reason
    if getattr(args, "corrects_line", None) is not None:
        entry["corrects"] = {
            "line": args.corrects_line,
            "field": args.corrects_field or "report",
            "old": args.corrects_old,
            "new": args.corrects_new,
        }
        entry["corrects"] = {k: v for k, v in entry["corrects"].items() if v is not None}
    return entry


def validate_entry(entry: dict) -> list[str]:
    """fail-closed 校验：返回违规说明列表（空=合法）。

    这一层存在的理由：`check` 只能看见**已经写进磁盘**的坏记录；
    真正的静默失败发生在**写入之前**（该带产物却不带）。所以守卫必须挡在 append 前。
    """
    problems: list[str] = []
    phase = entry.get("phase")
    if entry.get("phase") == "done":
        has_report = bool(entry.get("report"))
        has_reason = bool(entry.get("no_report_reason"))
        if not has_report and not has_reason:
            problems.append(
                "phase=done 必须带 --report <产物路径>；若确实无可验证产物，"
                "必须用 --no-report-reason 显式说明（禁止静默留空）"
            )
    # task-107 / L9：spawn 的模式决策 fail-closed（不传 mode = 静默默认 standard = 没做决策）
    if phase == "spawn":
        mode = entry.get("mode")
        explicit = entry.get("modeExplicit")
        if mode is None and explicit is not False:
            problems.append(
                "phase=spawn 必须显式 --mode {mechanical|standard|deep|creator}（AGENTS.md §0.5 L9："
                "不传 mode 会被静默默认为 standard = 没做决策）；若确实无法判断，用 "
                "--mode-explicit false 显式留下「未决定」痕迹（modeExplicit=false，不伪造 mode）"
            )
        elif mode is not None and explicit is False:
            problems.append("--mode 与 --mode-explicit false 自相矛盾（既然选了模式就不能声明未决定）")
        elif mode is not None and mode not in VALID_MODES:
            problems.append(f"mode={mode!r} 不在 DSH 四档 {list(VALID_MODES)}")
    if "corrects" in entry:
        fix = entry["corrects"]
        if phase != "backfill":
            problems.append("corrects 只允许出现在 phase=backfill 记录里")
        if not isinstance(fix.get("line"), int) or fix["line"] < 1:
            problems.append("corrects.line 必须是 >=1 的整数（要更正的历史行号）")
        if not fix.get("new"):
            problems.append("corrects.new 必填（更正后的路径/值）")
    if phase not in PHASES:
        problems.append(f"phase={phase!r} 不在 {PHASES}")
    return problems


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

        # 红 5（2026-10-23 新增）：done 不带 report ⇒ append 必须被拒（静默失败守卫）
        guard_path = Path(tmp) / "guard.jsonl"
        code = main(["append", "--actor", "lead", "--target", "x", "--phase", "done",
                     "--log", str(guard_path)])
        expect("done-without-report-must-be-rejected", code == 2)
        expect("rejected-entry-must-not-be-written", not guard_path.exists())

        # 绿：done 带 --no-report-reason 时必须放行（合法豁免，而不是靠静默留空）
        code = main(["append", "--actor", "lead", "--target", "x", "--phase", "done",
                     "--no-report-reason", "纯会话操作，无磁盘产物", "--log", str(guard_path)])
        expect("done-with-explicit-reason-must-pass", code == 0)

        # 红 6：corrects 只允许 backfill，且必须带 line/new
        code = main(["append", "--actor", "lead", "--target", "x", "--phase", "done",
                     "--report", "team/dispatch-log.jsonl",
                     "--corrects-line", "3", "--corrects-new", "team/x.json",
                     "--log", str(guard_path)])
        expect("corrects-on-done-must-be-rejected", code == 2)
        code = main(["append", "--actor", "lead", "--target", "x", "--phase", "backfill",
                     "--corrects-line", "3", "--log", str(guard_path)])
        expect("corrects-without-new-must-be-rejected", code == 2)
        # 绿：合法更正记录
        code = main(["append", "--actor", "lead", "--target", "x", "--phase", "backfill",
                     "--corrects-line", "3", "--corrects-new", "team/dispatch-log.jsonl",
                     "--log", str(guard_path)])
        expect("valid-correction-must-pass", code == 0)
        guard_report = check(guard_path, max_age_days=36500)
        expect("guard-log-must-be-valid", guard_report["ok"] is True)
        expect("guard-log-must-have-2-entries", guard_report["count"] == 2)

        # 红 9（task-107 / L9）：spawn 不带 --mode ⇒ append 必须被拒；带 --mode 必须落盘且含字段；
        #    --mode-explicit false 是「显式未决定」留痕（允许，但缺 mode）；两者同用 ⇒ 拒绝。
        mode_path = Path(tmp) / "mode.jsonl"
        code = main(["append", "--actor", "lead", "--target", "worker", "--phase", "spawn",
                     "--task", "task-107", "--log", str(mode_path)])
        expect("spawn-without-mode-must-be-rejected", code == 2)
        expect("rejected-spawn-must-not-be-written", not mode_path.exists())
        code = main(["append", "--actor", "lead", "--target", "worker", "--phase", "spawn",
                     "--task", "task-107", "--mode", "mechanical", "--log", str(mode_path)])
        expect("spawn-with-mode-must-pass", code == 0)
        mode_rows = [json.loads(line) for line in mode_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        expect("spawn-mode-fields-written", bool(mode_rows) and mode_rows[0].get("mode") == "mechanical"
               and mode_rows[0].get("modeExplicit") is True)
        code = main(["append", "--actor", "lead", "--target", "undecided", "--phase", "spawn",
                     "--mode-explicit", "false", "--log", str(mode_path)])
        expect("spawn-explicit-undecided-allowed", code == 0)
        # 历史行（直接 append_entry，模拟 task-107 之前的旧记录）⇒ 必须只 WARN 不阻断
        append_entry(mode_path, {"ts": now_iso(), "actor": "lead", "phase": "spawn", "target": "legacy"})
        mode_report = check(mode_path, max_age_days=36500)
        coverage = mode_report["mode_coverage"]
        expect("mode-check-coverage-counted", coverage["spawn"] == 3 and coverage["judgeable"] == 2
               and coverage["unknown"] == 1)
        expect("mode-check-warns-legacy-row", any(w["check"] == "mode_missing" for w in mode_report["warnings"]))
        expect("mode-warnings-do-not-break-ok", mode_report["ok"] is True)
        code = main(["append", "--actor", "lead", "--target", "conflict", "--phase", "spawn",
                     "--mode", "standard", "--mode-explicit", "false", "--log", str(mode_path)])
        expect("mode-contradiction-must-be-rejected", code == 2)

        # 红 7（回归守卫）：子命令 --log 的 default=None 曾把默认路径吃掉 ⇒ Path(None) TypeError。
        #   断言「不给 --log 也必须能拿到非空路径」：用真实默认值构造一次 check（只读，不写）。
        code = main(["check"])
        expect("check-with-default-log-must-not-crash", code in (0, 1))
        if not DEFAULT_LOG.is_file():
            failures.append("DEFAULT_LOG 指向的 team/dispatch-log.jsonl 不存在（默认路径口径失效）")

    if failures:
        print(f"FAIL: {', '.join(failures)}")
        return 1
    print("PASS: dispatch_log.py selftest（红 9 类：缺文件/过期/坏JSON/缺字段/done无report被拒/"
          "corrects滥用被拒/默认路径回归/spawn无mode被拒/mode自相矛盾被拒；"
          "绿：成对记录、显式豁免、合法更正、spawn带mode落盘、显式未决定留痕；"
          "mode 覆盖计数与 warnings 可见）")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="派发日志 append / check / selftest")
    parser.add_argument("--selftest", action="store_true", help="运行自测并退出")
    parser.add_argument("--log", default=str(DEFAULT_LOG), help="日志路径（默认 team/dispatch-log.jsonl）")
    sub = parser.add_subparsers(dest="command")

    append_parser = sub.add_parser("append", help="追加一条派发记录")
    append_parser.add_argument("--actor", required=True, help="执行派发的 agent（lead / teammate 名）")
    append_parser.add_argument("--log", default=None,
                              help="日志路径（也可放在子命令前；两者等价）")
    append_parser.add_argument("--target", required=True, help="被派发/接收的 agent")
    append_parser.add_argument("--phase", required=True, choices=PHASES, help="派发阶段")
    append_parser.add_argument("--task", help="关联任务 id（如 task-80）")
    append_parser.add_argument("--desc", help="一句话说明")
    append_parser.add_argument("--outcome", help="done 阶段的结论（pass/fail/blocked）")
    append_parser.add_argument("--report", help="产出物路径（报告/提交）")
    append_parser.add_argument("--evidence", help="额外证据路径")
    append_parser.add_argument("--source", help="来源标记（如 backfill:team-board-snapshot.json）")
    append_parser.add_argument("--ts", help="显式时间戳（回填历史用；缺省取当前时间）")
    append_parser.add_argument("--mode", choices=VALID_MODES,
                               help="spawn 模式决策（L9，必填；路由表见 lead-dispatch-rules §1.3b）")
    append_parser.add_argument("--mode-explicit", choices=("true", "false"), default=None,
                               help="modeExplicit 布尔：true=显式决策；false=显式「未决定」留痕（与 --mode 互斥）")
    append_parser.add_argument("--no-report-reason",
                               help="phase=done 但确实无产物时的显式理由（替代 --report）")
    append_parser.add_argument("--corrects-line", type=int,
                               help="更正协议：要更正的历史行号（仅 phase=backfill）")
    append_parser.add_argument("--corrects-field", default="report",
                               help="更正协议：被更正的字段名（默认 report）")
    append_parser.add_argument("--corrects-old", help="更正协议：原值（留痕用，可省）")
    append_parser.add_argument("--corrects-new", help="更正协议：新值（必填，须可验证）")

    check_parser = sub.add_parser("check", help="校验日志是否可追溯")
    check_parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    check_parser.add_argument("--max-age-days", type=int, default=MAX_AGE_DAYS, help="最近记录的允许最大天数")
    check_parser.add_argument("--log", default=None,
                              help="日志路径（也可放在子命令前；两者等价）")

    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    # 子命令也接受 --log（等价写法），其 default=None 会覆盖顶层默认值 ⇒ 这里兜底。
    log_path = Path(args.log or DEFAULT_LOG)
    if args.command == "append":
        entry = build_entry(args)
        violations = validate_entry(entry)
        if violations:
            print("FAIL: 拒绝写入非法派发记录（fail-closed）：", file=sys.stderr)
            for item in violations:
                print(f"  - {item}", file=sys.stderr)
            return 2
        append_entry(log_path, entry)
        print(json.dumps(entry, ensure_ascii=False))
        return 0
    if args.command == "check":
        report = check(log_path, args.max_age_days)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            status = "PASS" if report["ok"] else "FAIL"
            coverage = report.get("mode_coverage") or {}
            print(f"{status}: {report['count']} 条派发记录, latest={report['latest']}, path={report['path']}"
                  f"；mode 可判定 {coverage.get('judgeable', 0)}/{coverage.get('spawn', 0)}")
            for problem in report["problems"]:
                print(f"  - {problem}")
            for warning in report.get("warnings") or []:
                print(f"  - [WARN] {warning}")
        return 0 if report["ok"] else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
