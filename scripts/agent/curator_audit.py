#!/usr/bin/env python3
"""Curator 审计采集器（P4/V5 的可复跑实现）。

只读仓库，不修改任何文件；把审计所需证据一次采集成：
    team/curator/audit-<date>/raw.json    （机器可读）
    team/curator/audit-<date>/SUMMARY.md  （人可读，每条结论附命令）

用法
----
    python scripts/agent/curator_audit.py                    # 默认今天、默认输出目录
    python scripts/agent/curator_audit.py --date 2026-10-23
    python scripts/agent/curator_audit.py --json             # 只打印 raw JSON，不写文件

它替代「人工翻 813 个文件才发现注册表空转」；Curator 的职责判断仍由 agent 完成，
本脚本只提供证据与清理候选，不做删除（P5 删除必须人类确认）。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# 2026-10-23：团队资产已迁出 artifacts/（那里被 gitignore，零版本历史）
TEAM_DIR = REPO_ROOT / "team"                 # 入库：agents.json / dispatch-log / 快照 / prompts / curator 审计
VERIFY_DIR = REPO_ROOT / "artifacts" / "agent" / "verify"   # 仍是产物（109 份验证报告，不入库）
AGENT_LEGACY = REPO_ROOT / "artifacts" / "agent"            # 兼容：体积统计仍扫这里（verify 占绝大部分）
CLEANUP_MIN_BYTES = 5 * 1024 * 1024
ACTIVE_WINDOW_DAYS = 14


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def age_days(moment: datetime) -> float:
    return round((datetime.now(timezone.utc) - moment.astimezone(timezone.utc)).total_seconds() / 86400, 1)


def git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def collect_registry(raw: dict) -> None:
    registry = load_json(TEAM_DIR / "agents.json")
    entry: dict = {"path": "team/agents.json", "exists": registry is not None}
    if registry:
        agents = registry.get("agents", [])
        retired = registry.get("retired_agents", [])
        entry.update({
            "schema_version": registry.get("schema_version"),
            "carrier": registry.get("carrier"),
            "active_agents": [
                {
                    "id": agent.get("id"),
                    "status": agent.get("status"),
                    "trigger_type": (agent.get("trigger_channel") or {}).get("type"),
                    "trigger_mechanism": (agent.get("trigger_channel") or {}).get("mechanism"),
                    "prompt_ref": agent.get("prompt_ref"),
                }
                for agent in agents
            ],
            "retired_agents": [
                {"id": agent.get("id"), "previous_id": agent.get("previous_id"), "status": agent.get("status")}
                for agent in retired
            ],
            "missing_trigger_channel": [
                agent.get("id") for agent in agents if not (agent.get("trigger_channel") or {}).get("mechanism")
            ],
        })
    raw["registry"] = entry


def collect_prompts(raw: dict) -> None:
    prompts: list[dict] = []
    prompt_dir = TEAM_DIR / "prompts"
    if prompt_dir.exists():
        for path in sorted(prompt_dir.glob("*.md")):
            stat = path.stat()
            prompts.append({
                "path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).astimezone().isoformat(timespec="seconds"),
                "age_days": age_days(datetime.fromtimestamp(stat.st_mtime, timezone.utc)),
                "bytes": stat.st_size,
            })
    raw["legacy_prompts"] = prompts


def collect_event_stream(raw: dict) -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "agent"))
    try:
        from dispatch_log import check as check_dispatch  # noqa: PLC0415
        report = check_dispatch(TEAM_DIR / "dispatch-log.jsonl")
    except ImportError:
        report = {"ok": False, "error": "scripts/agent/dispatch_log.py 不可导入"}
    raw["event_stream"] = {
        "legacy_events_jsonl": {
            "path": "artifacts/agent/events.jsonl",
            "exists": (AGENT_LEGACY / "events.jsonl").exists(),   # 历史事件流（从未落盘）
            "note": "Trae 载体事件流；DSH 下从未落盘",
        },
        "dispatch_log": report,
    }


def collect_task_board(raw: dict) -> None:
    snapshot = load_json(TEAM_DIR / "team-board-snapshot.json")
    entry: dict = {"path": "team/team-board-snapshot.json", "exists": snapshot is not None}
    if snapshot:
        members = snapshot.get("members", [])
        tasks = snapshot.get("tasks", [])
        entry.update({
            "exported_at": snapshot.get("exportedAt"),
            "limit": snapshot.get("limit"),
            "members": [{"target": m.get("target"), "status": m.get("status")} for m in members],
            "retired": [{"target": m.get("target"), "reason": m.get("reason")} for m in snapshot.get("retired", [])],
            "in_progress": [t for t in tasks if t.get("status") == "in_progress"],
            "completed_recent": snapshot.get("completedRecent", []),
        })
    raw["task_board"] = entry


def collect_artifacts(raw: dict) -> None:
    files = [p for p in TEAM_DIR.rglob("*") if p.is_file()] + [p for p in AGENT_LEGACY.rglob("*") if p.is_file()]
    total_bytes = sum(p.stat().st_size for p in files)
    by_top: dict[str, dict[str, int]] = {}
    for path in files:
        rel = path.relative_to(TEAM_DIR) if str(path).startswith(str(TEAM_DIR)) else path.relative_to(AGENT_LEGACY)
        top = rel.parts[0] if len(rel.parts) > 1 else "(root files)"
        bucket = by_top.setdefault(top, {"files": 0, "bytes": 0})
        bucket["files"] += 1
        bucket["bytes"] += path.stat().st_size
    candidates: list[dict] = []
    for path in sorted(files, key=lambda p: p.stat().st_size, reverse=True):
        if path.suffix.lower() in {".md"}:
            continue
        stat = path.stat()
        if stat.st_size < CLEANUP_MIN_BYTES:
            continue
        rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        basename = path.name
        refs = git("grep", "-l", "--fixed-strings", basename, "--", "docs", "src", "scripts")
        referenced = bool(refs.strip())
        # 文件名精确未命中时，再查同族前缀（如 p6c / heap / p62），供人类判断是否被脚本按模式消费。
        family = basename.split(".")[0].split("-")[0]
        family_refs = git("grep", "-l", "--fixed-strings", family, "--", "docs", "src", "scripts")
        candidates.append({
            "path": rel,
            "bytes": stat.st_size,
            "mb": round(stat.st_size / 1024 / 1024, 2),
            "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).astimezone().isoformat(timespec="seconds"),
            "referenced_in_repo": referenced,
            "referencing_files": refs.strip().splitlines()[:5],
            "family": family,
            "family_referenced_in_repo": bool(family_refs.strip()),
            "family_referencing_files": family_refs.strip().splitlines()[:5],
            "git_tracked": bool(git("ls-files", "--error-unmatch", rel).strip()),
        })
    cleanup_bytes = sum(c["bytes"] for c in candidates if not c["referenced_in_repo"])
    raw["artifacts"] = {
        "total_files": len(files),
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / 1024 / 1024, 1),
        "by_top_dir": by_top,
        "cleanup_min_bytes": CLEANUP_MIN_BYTES,
        "cleanup_candidates": candidates,
        "cleanup_candidate_bytes": cleanup_bytes,
        "cleanup_candidate_mb": round(cleanup_bytes / 1024 / 1024, 1),
        "target_total_mb_after_cleanup": round((total_bytes - cleanup_bytes) / 1024 / 1024, 1),
    }


def collect_owner_activity(raw: dict) -> None:
    """以 verify 报告 mtime 作为领域 Owner 的近期运行证据（磁盘证据，非猜测）。"""
    snapshot = load_json(TEAM_DIR / "team-board-snapshot.json") or {}
    members = [m.get("target") for m in snapshot.get("members", []) if m.get("role") == "teammate"]
    verify_files = [p for p in VERIFY_DIR.rglob("*.md") if p.is_file()] if VERIFY_DIR.exists() else []
    activity: list[dict] = []
    for owner in members:
        matches = [p for p in verify_files if owner and owner.lower() in p.name.lower()]
        latest = max((p.stat().st_mtime for p in matches), default=None)
        activity.append({
            "owner": owner,
            "report_matches": len(matches),
            "latest_report": (
                datetime.fromtimestamp(latest, timezone.utc).astimezone().isoformat(timespec="seconds")
                if latest else None
            ),
            "days_since_report": age_days(datetime.fromtimestamp(latest, timezone.utc)) if latest else None,
            "judgement": "active" if latest and age_days(datetime.fromtimestamp(latest, timezone.utc)) <= ACTIVE_WINDOW_DAYS else "inactive",
        })
    raw["owner_activity"] = {
        "window_days": ACTIVE_WINDOW_DAYS,
        "source": "artifacts/agent/verify/**/*.md 文件名含 owner 名",
        "owners": activity,
    }


def findings(raw: dict) -> list[dict]:
    out: list[dict] = []
    stream = raw["event_stream"]
    legacy = stream["legacy_events_jsonl"]
    dispatch = stream["dispatch_log"]
    out.append({
        "id": "F1",
        "severity": "high" if not legacy["exists"] else "info",
        "conclusion": "Trae 事件流（events.jsonl）不存在 ⇒ 旧 on_events 触发器 0 次；DSH 下仅 dispatch-log 生效",
        "evidence": f"Test-Path artifacts/agent/events.jsonl = {legacy['exists']}; dispatch-log count={dispatch.get('count')}, ok={dispatch.get('ok')}",
    })
    prompts = raw["legacy_prompts"]
    stale = [p for p in prompts if p["age_days"] > 30]
    out.append({
        "id": "F2",
        "severity": "medium" if stale else "info",
        "conclusion": f"历史角色提示词 {len(stale)}/{len(prompts)} 份超过 30 天未改动 ⇒ 判 inactive（保留历史）",
        "evidence": "; ".join(f"{p['path']} age={p['age_days']}d" for p in stale) or "无",
    })
    missing = raw["registry"].get("missing_trigger_channel", [])
    out.append({
        "id": "F3",
        "severity": "high" if missing else "info",
        "conclusion": "非退役角色全部具备真实触发通道" if not missing else f"角色缺触发通道: {missing}",
        "evidence": "agents.json agents[].trigger_channel.mechanism 逐项检查",
    })
    inactive_owners = [o["owner"] for o in raw["owner_activity"]["owners"] if o["judgement"] == "inactive"]
    out.append({
        "id": "F4",
        "severity": "medium" if inactive_owners else "info",
        "conclusion": "存在 14 天内无磁盘产出证据的 Owner" if inactive_owners else "全部运行时 Owner 14 天内有磁盘产出证据",
        "evidence": f"inactive owners = {inactive_owners or '[]'}（窗口 {ACTIVE_WINDOW_DAYS} 天，依据 verify 报告 mtime）",
    })
    artifacts = raw["artifacts"]
    out.append({
        "id": "F5",
        "severity": "medium",
        "conclusion": f"artifacts/agent 体积 {artifacts['total_mb']} MB；未引用的大文件可清理 {artifacts['cleanup_candidate_mb']} MB（需人类确认）",
        "evidence": f"{artifacts['total_files']} files; cleanup candidates={len(artifacts['cleanup_candidates'])}; post-cleanup≈{artifacts['target_total_mb_after_cleanup']} MB",
    })
    return out


def verification_commands() -> list[str]:
    return [
        "python scripts/agent/dispatch_log.py check",
        "python scripts/agent/dispatch_log.py --selftest",
        "python scripts/agent/curator_audit.py --json",
        "powershell -Command \"(Get-Content team/agents.json -Raw | ConvertFrom-Json).agents | Select-Object id,status\"",
        "powershell -Command \"Get-ChildItem artifacts/agent -Recurse -File | Measure-Object Length -Sum\"",
        "git status --short docs/guides artifacts/agent",
    ]


def render_summary(raw: dict) -> str:
    findings_list = raw["findings"]
    owners = raw["owner_activity"]["owners"]
    artifacts = raw["artifacts"]
    dispatch = raw["event_stream"]["dispatch_log"]
    lines = [
        f"# Curator 审计摘要（{raw['date']}）",
        "",
        f"> 采集时间：{raw['generated_at']}；采集器：`scripts/agent/curator_audit.py`（只读）。",
        "> 每条结论附复跑命令；删除建议**未执行**，需人类确认（P5）。",
        "",
        "## 1. 结论先行",
        "",
        f"- **派发可追溯**：dispatch-log {dispatch.get('count')} 条，最新 {dispatch.get('latest')}，check={dispatch.get('ok')}。",
        f"- **团队资产体积**：{artifacts['total_mb']} MB / {artifacts['total_files']} 文件；未引用大文件候选 {artifacts['cleanup_candidate_mb']} MB。",
        f"- **旧事件流**：events.jsonl exists={raw['event_stream']['legacy_events_jsonl']['exists']} ⇒ Trae 触发器 0 次。",
        "",
        "## 2. 证据与判定",
        "",
        "| # | 结论 | 证据 |",
        "|---|---|---|",
    ]
    for finding in findings_list:
        lines.append(f"| {finding['id']} | {finding['conclusion']} | {finding['evidence']} |")
    lines += [
        "",
        "## 3. 运行时 Owner 活性（14 天窗口，磁盘证据）",
        "",
        "> 判据口径：仅以 `artifacts/agent/verify/**` 中**文件名含 owner 名**的报告 mtime 为据；",
        "> 不含提交/任务板/领域内其他报告 ⇒ 判 `inactive` 只能作为**待复核线索**，不能直接当结论。",
        "",
        "| Owner | 匹配报告数 | 最新报告 | 天数 | 判定 |",
        "|---|---|---|---|---|",
    ]
    for owner in owners:
        lines.append(
            f"| `{owner['owner']}` | {owner['report_matches']} | {owner['latest_report'] or '—'} | "
            f"{owner['days_since_report'] if owner['days_since_report'] is not None else '—'} | {owner['judgement']} |"
        )
    lines += [
        "",
        "## 4. 清理候选（P5，待人类确认，**未删除**）",
        "",
        f"候选合计 **{artifacts['cleanup_candidate_mb']} MB**；清理后预计 **{artifacts['target_total_mb_after_cleanup']} MB**。",
        "",
        "| 文件 | MB | 最后修改 | 精确文件名被引用 | 同族前缀被引用（需人工判断） |",
        "|---|---|---|---|---|",
    ]
    for candidate in artifacts["cleanup_candidates"]:
        if candidate["referenced_in_repo"]:
            continue
        family_hit = "是" if candidate.get("family_referenced_in_repo") else "否"
        lines.append(
            f"| `{candidate['path']}` | {candidate['mb']} | {candidate['mtime']} | 否 | "
            f"{candidate.get('family')} → {family_hit} |"
        )
    lines += [
        "",
        "## 5. 最该改的一件事",
        "",
        "**把 dispatch-log 变成 Lead 收口必跑项**：每次 spawn/send/收口后立刻 `python scripts/agent/dispatch_log.py append ...`，",
        "收口前跑 `python scripts/agent/dispatch_log.py check`。否则「谁在干活」仍只能靠 813 个磁盘文件反推。",
        "",
        "## 6. 复跑命令",
        "",
        "```powershell",
        "$env:PYTHONIOENCODING='utf-8'",
        *verification_commands(),
        "```",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Curator 审计采集（只读）")
    parser.add_argument("--date", default=datetime.now().astimezone().strftime("%Y-%m-%d"), help="审计日期")
    parser.add_argument("--out-dir", default=None, help="输出目录（默认 team/curator/audit-<date>）")
    parser.add_argument("--json", action="store_true", help="只打印 raw JSON，不写文件")
    args = parser.parse_args(argv)

    raw: dict = {
        "schema": "curator-audit/v1",
        "date": args.date,
        "generated_at": iso_now(),
        "repo_root": str(REPO_ROOT),
    }
    collect_registry(raw)
    collect_prompts(raw)
    collect_event_stream(raw)
    collect_task_board(raw)
    collect_artifacts(raw)
    collect_owner_activity(raw)
    raw["findings"] = findings(raw)
    raw["verification_commands"] = verification_commands()

    if args.json:
        print(json.dumps(raw, ensure_ascii=False, indent=2))
        return 0
    out_dir = Path(args.out_dir) if args.out_dir else TEAM_DIR / "curator" / f"audit-{args.date}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "SUMMARY.md").write_text(render_summary(raw), encoding="utf-8")
    print(f"wrote {out_dir / 'raw.json'}")
    print(f"wrote {out_dir / 'SUMMARY.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
