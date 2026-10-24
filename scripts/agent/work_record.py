#!/usr/bin/env python3
"""成员工作记录只读投影（work_record.py，task-101）。

**投影不是事实源，删除可重建。**
本脚本不新建任何存储、不写任务板、不写 `team/**`：每次查询时在内存里 join 现有磁盘事实。
判定标准（设计稿 §2.2）：删掉本脚本的所有输出，重启后可由源数据逐字节重建；
如果同一事实在磁盘上出现第二份可写副本，它一定会分叉（教训 L1.1）。

数据源（各自唯一写入者，本脚本只读）
------------------------------------
| 层 | 源 | 唯一写入者 |
|---|---|---|
| 任务层 | `team/team-board-snapshot.json`（任务板磁盘投影） | Lead 导出 |
| 动作层 | `team/dispatch-log.jsonl`（生命周期）+ `git log`（改了什么） | Lead / 人 |
| 决策层 | `team/decisions.jsonl`（task-102 建立；当前可能缺失 ⇒ 显式 NOT_ESTABLISHED） | 决策者 |
| 产物 | 任务 `evidence[]` / dispatch `report` 指向的磁盘文件 | 执行者 |
| 成员经验 | `team/memory/<member>.md`（task-87 记忆卡，当前刚起步） | 插件/Lead |

已知边界（不静默）
------------------
- 快照 `tasks[]` 只有 7 字段（无 description / 时间戳 / 部分 evidence）⇒ 任务档案会显式标
  `source: snapshot` 与 `data_gaps`，不假装拿到 live 任务板。
- `artifacts/` 被 `.gitignore` 排除 ⇒ 证据路径分三类：`exists` / `gitignored`（不入库≠缺失）/ `missing`。
- 动作层 Phase 0 只覆盖 git 可观测子集；`write_without_read` / `gate_fail_continue` 需要 task-95 轨迹（未落地）。
- 决策索引未建立前，`decision` 命令返回 `NOT_ESTABLISHED`，**不是**"没有决策"。

用法
----
    python scripts/agent/work_record.py task     --id task-101 [--json] [--full]
    python scripts/agent/work_record.py member   --id steward2 --since 7d [--json] [--full]
    python scripts/agent/work_record.py decision --grep "0.4.6" [--limit 5] [--json]
    python scripts/agent/work_record.py decision --doctor          # 校验决策索引（通道③）
    python scripts/agent/work_record.py risk     --since 7d [--json]
    python scripts/agent/work_record.py doctor   [--json]          # 数据源自查；FAIL ⇒ 退出码 1
    python scripts/agent/work_record.py --selftest                 # 自测：红/绿路径都必须验证

退出码
------
0 = 数据源可读且查询完成（可能带 WARN / NOT_ESTABLISHED）
1 = 数据源 FAIL（doctor / decision --doctor）
2 = 用法错误
3 = 明确的功能不可用（暂未使用；保留）
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径与预算常量
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_REL = "team/team-board-snapshot.json"
DISPATCH_LOG_REL = "team/dispatch-log.jsonl"
AGENTS_REL = "team/agents.json"
DECISIONS_REL = "team/decisions.jsonl"
MEMORY_DIR_REL = "team/memory"
TRAJECTORY_DIR_REL = "team/trajectory"

TASK_OUTPUT_BUDGET = 8192        # 设计 §2.4：单任务档案 ≤8 KB
MEMBER_OUTPUT_BUDGET = 12288
DECISION_OUTPUT_BUDGET = 4096    # 默认 5 条 / ≤4 KB
SNAPSHOT_MAX_AGE_HOURS = 24      # 设计 G3：审计必须在新鲜快照上做
DISPATCH_MAX_AGE_DAYS = 7

TASK_SECTION_LIMITS = {"evidence": 60, "dispatch": 20, "commits": 20, "decisions": 5, "memory": 3}
_MIN_SECTION_LIMIT = 2

VALID_PHASES = ("spawn", "message", "done", "retire", "backfill")
RISK_DELETE_LINES = 20           # 设计 §2.3.6 T2：删除 ≥20 行 = 单向门候选
SELF_FIX_RE = re.compile(r"(修复.*(引入|上个提交|上一提交)|回退|revert|Revert)")
REVERT_SUBJECT_RE = re.compile(r"^(Revert\b|revert\b)|This reverts commit")
VERSION_FILE_REL = "src/memoria/__version__.py"

# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def _setup_stdio() -> None:
    """Windows 控制台默认 cp1252 会因中文输出抛 UnicodeEncodeError；统一改 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def now_local() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def now_iso() -> str:
    return now_local().isoformat(timespec="seconds")


def parse_ts(value) -> datetime | None:
    """解析 ISO-8601（允许 Z / 纯日期）；失败返回 None（不猜）。"""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone()


def parse_since(text: str | None) -> datetime | None:
    """`--since 7d|12h|2w|30m`（m=30 天）或 ISO 日期；None 表示不限。"""
    if not text:
        return None
    match = re.fullmatch(r"\s*(\d+)\s*([hdwm])\s*", text)
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        delta = {
            "h": timedelta(hours=amount),
            "d": timedelta(days=amount),
            "w": timedelta(weeks=amount),
            "m": timedelta(days=30 * amount),
        }[unit]
        return now_local() - delta
    parsed = parse_ts(text)
    if parsed is None:
        raise ValueError(f"无法解析 --since {text!r}（支持 7d/12h/2w 或 ISO 日期）")
    return parsed


def fmt_ts(value) -> str:
    parsed = parse_ts(value)
    return parsed.strftime("%m-%d %H:%M") if parsed else str(value)


def fmt_iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


def human_age(value: datetime | None) -> str:
    if value is None:
        return "?"
    seconds = (now_local() - value).total_seconds()
    if seconds < 0:
        return f"-{abs(seconds) / 3600:.1f}h(未来)"
    if seconds < 3600:
        return f"{seconds / 60:.0f}m"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def git(repo: Path, *args: str) -> tuple[bool, str, str]:
    """只读 git 调用；`core.quotepath=false` 防中文路径被转义。"""
    cmd = ["git", "-c", "core.quotepath=false", *args]
    try:
        proc = subprocess.run(
            cmd, cwd=str(repo), capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
    except (FileNotFoundError, OSError) as exc:  # git 不可用
        return False, "", str(exc)
    return proc.returncode == 0, proc.stdout, proc.stderr


def git_check_ignore(repo: Path, rel_path: str) -> str | None:
    """返回命中 .gitignore 的那一行（如 `.gitignore:15:artifacts/`）；未被忽略返回 None。"""
    ok, out, _err = git(repo, "check-ignore", "-v", "--", rel_path)
    if not ok:
        return None
    first = out.strip().splitlines()
    return first[0] if first else "(ignored)"


def read_jsonl(path: Path) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    bad: list[dict] = []
    if not path.is_file():
        return rows, bad
    for lineno, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
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
        rows.append(obj)
    return rows, bad


def read_json(path: Path) -> tuple[dict | None, str | None]:
    if not path.is_file():
        return None, "missing"
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace")), None
    except (json.JSONDecodeError, OSError) as exc:
        return None, str(exc)


def rel(repo: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def hard_truncate(text: str, budget: int) -> str:
    """把文本硬压到 budget 字节内（UTF-8 边界安全），并加截断标记。"""
    marker = "\n…（超出输出预算，已截断；用 --full 或 --json 查看完整数据）\n"
    encoded = text.encode("utf-8")
    if len(encoded) <= budget:
        return text
    keep = budget - len(marker.encode("utf-8"))
    # 按字符逐步收缩，避免截断多字节字符
    chars = len(text)
    while chars > 0 and len(text[:chars].encode("utf-8")) > keep:
        chars = int(chars * 0.9) if chars > 1 else 0
    return text[:chars] + marker


# ---------------------------------------------------------------------------
# 数据源加载（缺失/损坏必须显式状态，不静默空）
# ---------------------------------------------------------------------------
def load_snapshot(repo: Path) -> dict:
    path = repo / SNAPSHOT_REL
    data, err = read_json(path)
    result = {
        "path": SNAPSHOT_REL,
        "status": "ok",
        "exported_at": None,
        "exported_by": None,
        "tasks": {},
        "recent": [],
        "members": [],
        "retired": [],
        "error": None,
        "task_count": 0,
    }
    if err == "missing":
        result["status"] = "missing"
        return result
    if err is not None:
        result["status"] = "corrupt"
        result["error"] = err
        return result
    assert data is not None
    if not isinstance(data, dict):
        result["status"] = "corrupt"
        result["error"] = "snapshot 顶层不是 JSON object"
        return result
    result["exported_at"] = parse_ts(data.get("exportedAt"))
    result["exported_by"] = data.get("exportedBy")
    tasks = [t for t in data.get("tasks", []) if isinstance(t, dict) and t.get("id")]
    result["tasks"] = {str(t["id"]): t for t in tasks}
    result["task_count"] = len(tasks)
    result["recent"] = [t for t in data.get("completedRecent", []) if isinstance(t, dict)]
    result["members"] = [m for m in data.get("members", []) if isinstance(m, dict)]
    result["retired"] = [m for m in data.get("retired", []) if isinstance(m, dict)]
    return result


def load_dispatch(repo: Path) -> dict:
    path = repo / DISPATCH_LOG_REL
    rows, bad = read_jsonl(path)
    stamps = [ts for ts in (parse_ts(row.get("ts")) for row in rows) if ts]
    result = {
        "path": DISPATCH_LOG_REL,
        "status": "ok",
        "rows": rows,
        "bad": bad,
        "count": len(rows),
        "latest": max(stamps) if stamps else None,
        "problems": [],
    }
    if not path.is_file():
        result["status"] = "missing"
    if bad:
        result["status"] = "corrupt"
        result["problems"] = bad
    for index, row in enumerate(rows, 1):
        missing = [field for field in ("ts", "actor", "phase") if not row.get(field)]
        if missing:
            result["problems"].append({"line": index, "error": f"缺字段 {missing}"})
        elif row.get("phase") not in VALID_PHASES:
            result["problems"].append({"line": index, "error": f"非法 phase={row.get('phase')!r}"})
    if result["problems"] and result["status"] == "ok":
        result["status"] = "corrupt"
    return result


def load_decisions(repo: Path) -> dict:
    path = repo / DECISIONS_REL
    rows, bad = read_jsonl(path)
    status = "ok"
    if not path.is_file():
        status = "missing"
    elif bad:
        status = "corrupt"
    return {"path": DECISIONS_REL, "status": status, "rows": rows, "bad": bad}


def load_agents(repo: Path) -> dict:
    path = repo / AGENTS_REL
    data, err = read_json(path)
    result = {"path": AGENTS_REL, "status": "ok", "agents": [], "error": None}
    if err == "missing":
        result["status"] = "missing"
        return result
    if err is not None:
        result["status"] = "corrupt"
        result["error"] = err
        return result
    assert data is not None
    result["agents"] = [a for a in data.get("agents", []) if isinstance(a, dict)]
    return result


def load_memory_cards(repo: Path) -> dict:
    directory = repo / MEMORY_DIR_REL
    if not directory.is_dir():
        return {"path": MEMORY_DIR_REL, "status": "missing", "cards": {}}
    cards = {}
    for path in sorted(directory.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        cards[path.stem] = path.read_text(encoding="utf-8", errors="replace")
    return {"path": MEMORY_DIR_REL, "status": "ok", "cards": cards}


# ---------------------------------------------------------------------------
# git 查询
# ---------------------------------------------------------------------------
def git_commits(
    repo: Path, needle: str | None = None, since: datetime | None = None, max_count: int = 30
) -> tuple[list[dict], str | None]:
    args = ["log", "--all", "--format=%H%x1f%aI%x1f%s"]
    if since is not None:
        args.append(f"--since={since.isoformat(timespec='seconds')}")
    if needle:
        args += ["--fixed-strings", f"--grep={needle}"]
    args.append(f"--max-count={max_count}")
    ok, out, err = git(repo, *args)
    if not ok:
        return [], err.strip() or "git log 失败（不是 git 仓库或 git 不可用）"
    commits = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) >= 3:
            commits.append({"sha": parts[0], "date": parts[1], "subject": parts[2]})
    return commits, None


def git_head(repo: Path) -> dict:
    ok, out, err = git(repo, "rev-parse", "--short", "HEAD")
    if not ok:
        return {"ok": False, "head": None, "error": err.strip() or "not-a-git-repo"}
    ok_branch, branch, _ = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    return {"ok": True, "head": out.strip(), "branch": branch.strip() if ok_branch else None}


# ---------------------------------------------------------------------------
# 证据路径解析：exists / gitignored / missing（区分"缺失"与"不入库"）
# ---------------------------------------------------------------------------
def resolve_evidence(repo: Path, raw) -> dict:
    text = ""
    sha = None
    if isinstance(raw, dict):
        text = str(raw.get("ref") or raw.get("path") or "")
        sha = raw.get("sha256")
    elif raw is not None:
        text = str(raw)
    text = text.strip().strip("`")
    result = {"raw": text, "state": "empty", "detail": "", "size": None, "sha256": sha}
    if not text:
        return result
    if re.match(r"^[A-Za-z]:[\\/]", text) or text.startswith("/"):
        target = Path(text)
        rel_path = None
    else:
        rel_path = text.replace("\\", "/")
        target = repo / rel_path
    if "*" in text or "?" in text:
        try:
            matches = sorted(repo.glob(rel_path or text))
        except (ValueError, OSError):
            matches = []
        result["state"] = "glob"
        result["detail"] = f"通配符匹配 {len(matches)} 个文件" + (
            f"：{', '.join(rel(repo, m) for m in matches[:3])}" if matches else "（匹配为空）"
        )
        return result
    if target.exists():
        result["state"] = "exists"
        if target.is_file():
            result["size"] = target.stat().st_size
            result["detail"] = f"{result['size']} B"
        else:
            result["detail"] = "目录"
        return result
    if rel_path is not None:
        ignored = git_check_ignore(repo, rel_path)
        if ignored:
            result["state"] = "gitignored"
            result["detail"] = f"被 .gitignore 排除（{ignored.splitlines()[0]}）⇒ 不入库≠缺失"
        else:
            result["state"] = "missing"
            detail = "路径不存在且未被 .gitignore 排除"
            if rel_path.startswith(("packages/", "apps/")):
                detail += "（疑似 DSH 仓库相对路径；不在本仓库 ⇒ 需在 DSH checkout 里验证）"
            result["detail"] = detail
    else:
        result["state"] = "missing"
        result["detail"] = "仓库外绝对路径不存在"
    return result


def scan_memory_for(repo: Path, needle: str) -> list[dict]:
    memory = load_memory_cards(repo)
    hits = []
    for name, text in memory["cards"].items():
        matched = [line.strip() for line in text.splitlines() if needle in line]
        if matched:
            hits.append(
                {"card": f"{MEMORY_DIR_REL}/{name}.md", "matches": matched[:3], "match_count": len(matched)}
            )
    return hits


# ---------------------------------------------------------------------------
# 1) task —— 任务档案
# ---------------------------------------------------------------------------
def collect_task(repo: Path, task_id: str, full: bool) -> dict:
    gaps: list[str] = []
    snapshot = load_snapshot(repo)
    board = None
    if snapshot["status"] != "ok":
        gaps.append(f"任务板快照不可用（{snapshot['status']}），任务档案缺「任务板条目」半边")
    else:
        task = snapshot["tasks"].get(task_id)
        if task:
            board = {
                "source": "snapshot.tasks",
                "status": task.get("status"),
                "subject": task.get("subject"),
                "owner": task.get("owner"),
                "revision": task.get("revision"),
                "write_scopes": task.get("writeScopes", []),
                "blocked_by": task.get("blockedBy", []),
                "evidence": task.get("evidence", []),
                "note": "快照 tasks[] 无 description/时间戳（设计 G2）；live 任务板为准",
            }
        else:
            recent = next((r for r in snapshot["recent"] if r.get("id") == task_id), None)
            if recent:
                board = {
                    "source": "snapshot.completedRecent",
                    "status": None,
                    "subject": recent.get("subject"),
                    "owner": recent.get("ownerName"),
                    "revision": None,
                    "write_scopes": [],
                    "blocked_by": [],
                    "evidence": [],
                    "note": "仅 completedRecent 摘要（缺 status/evidence/时间戳）",
                }
            else:
                gaps.append(
                    "快照中未找到该任务（可能已删除，或快照早于任务创建/变更）；需 Lead 重导出快照确认"
                )

    dispatch = load_dispatch(repo)
    if dispatch["status"] != "ok":
        gaps.append(f"dispatch-log 不可用（{dispatch['status']}），档案缺「谁被派/何时收口」")
    dispatch_rows = sorted(
        [row for row in dispatch["rows"] if row.get("task") == task_id],
        key=lambda row: parse_ts(row.get("ts")) or now_local(),
    )

    commits, git_error = git_commits(repo, needle=task_id, max_count=200 if full else 30)
    if git_error:
        gaps.append(f"git log 不可用：{git_error}")
    head = git_head(repo)
    if not head["ok"]:
        gaps.append("git 仓库不可用（git log/提交回溯全部缺失）")

    decisions = load_decisions(repo)
    decision_items = [row for row in decisions["rows"] if row.get("task_id") == task_id]
    if decisions["status"] == "missing":
        gaps.append(f"决策索引未建立（{DECISIONS_REL} 不存在；task-102/task-99 未落地）⇒ 裁决字段缺失")

    evidence_paths: list = []
    if board:
        evidence_paths.extend(board.get("evidence") or [])
    for row in dispatch_rows:
        for key in ("report", "evidence"):
            if row.get(key):
                evidence_paths.append(row[key])
    for row in decision_items:
        for item in row.get("evidence") or []:
            evidence_paths.append(item)
    # 去重（保留首次出现顺序）
    deduped = []
    seen = set()
    for item in evidence_paths:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, dict) else str(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    evidence = [resolve_evidence(repo, item) for item in deduped]

    memory_hits = scan_memory_for(repo, task_id)
    if not memory_hits:
        gaps.append(
            "memory 卡中没有该任务段（task-87 卡机制刚起步；「弯路」暂只能从报告/提交反查）"
        )

    return {
        "command": "task",
        "generated_at": now_iso(),
        "id": task_id,
        "sources": {
            "board": {
                "path": snapshot["path"],
                "status": snapshot["status"],
                "exported_at": fmt_iso(snapshot["exported_at"]),
                "exported_by": snapshot["exported_by"],
            },
            "dispatch_log": {"path": dispatch["path"], "status": dispatch["status"], "count": dispatch["count"]},
            "git": head,
            "decisions": {"path": decisions["path"], "status": decisions["status"], "count": len(decisions["rows"])},
            "memory": {"path": MEMORY_DIR_REL, "cards_with_task": len(memory_hits)},
        },
        "board": board,
        "dispatch": dispatch_rows,
        "commits": commits,
        "decisions": decision_items if decisions["status"] == "ok" else [],
        "decisions_status": decisions["status"],
        "evidence": evidence,
        "memory": memory_hits,
        "data_gaps": gaps,
    }


def _render_task_md(data: dict, limits: dict) -> str:
    board = data["board"]
    lines: list[str] = [f"# 任务档案：{data['id']}（只读投影）", ""]
    src = data["sources"]
    lines.append(
        f"> 生成 {data['generated_at']}；源：board {src['board']['path']}@{src['board']['exported_at'] or '?'} "
        f"({src['board']['status']}) · dispatch-log {src['dispatch_log']['count']} 条 · git "
        f"{src['git'].get('head') or '不可用'} · decisions {src['decisions']['status']}"
    )
    lines.append("> 投影不是事实源，删除可重建（work_record.py task-101）。")
    lines.append("")

    lines.append("## 1. 任务板")
    if board:
        lines.append(f"- 来源：{board['source']}（{board['note']}）")
        if board.get("status"):
            lines.append(f"- status：**{board['status']}**；owner：{board.get('owner') or '(无)'}；revision：{board.get('revision')}")
        else:
            lines.append(f"- owner：{board.get('owner') or '(无)'}；status：未知（仅摘要）")
        lines.append(f"- subject：{board.get('subject')}")
        if board.get("write_scopes"):
            lines.append(f"- writeScopes：{', '.join(board['write_scopes'])}")
        if board.get("blocked_by"):
            lines.append(f"- blockedBy：{', '.join(board['blocked_by'])}")
    else:
        lines.append("- **不可用**：见文末 data_gaps")
    lines.append("")

    lines.append(f"## 2. 派发记录（{len(data['dispatch'])} 条）")
    shown = data["dispatch"][: limits["dispatch"]]
    if not shown:
        lines.append("- （dispatch-log 中无该 task 的行）")
    for row in shown:
        head = f"- {fmt_ts(row.get('ts'))} `{row.get('phase')}` {row.get('actor')} → {row.get('target')}"
        detail = row.get("desc") or ""
        tail = ""
        if row.get("outcome"):
            tail += f" [outcome={row['outcome']}]"
        if row.get("report"):
            tail += f" report={row['report']}"
        if row.get("no_report_reason"):
            tail += f" no_report_reason={row['no_report_reason']}"
        lines.append(head + (f"：{detail}" if detail else "") + tail)
    if len(data["dispatch"]) > len(shown):
        lines.append(f"- …另有 {len(data['dispatch']) - len(shown)} 条（--full 展开）")
    lines.append("")

    lines.append(f"## 3. 相关提交（git log --grep={data['id']}，{len(data['commits'])} 条）")
    shown = data["commits"][: limits["commits"]]
    if not shown:
        lines.append("- （没有提交信息含该 task id 的提交；≠ 没干活，可能未按 id 提交）")
    for commit in shown:
        lines.append(f"- `{commit['sha'][:10]}` {fmt_ts(commit['date'])} {commit['subject']}")
    if len(data["commits"]) > len(shown):
        lines.append(f"- …另有 {len(data['commits']) - len(shown)} 条（--full 展开）")
    lines.append("")

    lines.append("## 4. 决策（关联裁决）")
    if data["decisions_status"] == "missing":
        lines.append(f"- **NOT_ESTABLISHED**：{DECISIONS_REL} 未建立（task-102/task-99 未落地）—— 不是「无决策」")
    elif not data["decisions"]:
        lines.append("- 决策索引中无该 task 的记录（索引已建立，可视为「未记录」）")
    else:
        for row in data["decisions"][: limits["decisions"]]:
            lines.append(f"- `{row.get('id')}` {row.get('choice')} —— why: {row.get('why')}")
    lines.append("")

    lines.append(f"## 5. 证据路径解析（{len(data['evidence'])} 条）")
    shown = data["evidence"][: limits["evidence"]]
    if not shown:
        lines.append("- （任务未声明 evidence，且 dispatch 未带 report ⇒ 无产物可验：这本身是 finding 素材）")
    for item in shown:
        mark = {"exists": "[exists]", "gitignored": "[gitignored]", "missing": "[missing]", "glob": "[glob]", "empty": "[empty]"}.get(
            item["state"], f"[{item['state']}]"
        )
        lines.append(f"- {mark} `{item['raw']}` —— {item['detail']}")
    if len(data["evidence"]) > len(shown):
        lines.append(f"- …另有 {len(data['evidence']) - len(shown)} 条（--full 展开）")
    lines.append("")

    lines.append("## 6. 弯路（memory 卡段）")
    if not data["memory"]:
        lines.append("- 无（卡机制 task-87 刚起步；见 data_gaps）")
    else:
        for hit in data["memory"][: limits["memory"]]:
            lines.append(f"- `{hit['card']}`：")
            for line in hit["matches"]:
                lines.append(f"  - {line}")
    lines.append("")

    if data["data_gaps"]:
        lines.append("## 7. 数据缺口（显式，不静默）")
        for gap in data["data_gaps"]:
            lines.append(f"- {gap}")
        lines.append("")
    return "\n".join(lines)


def fit_task_md(data: dict, full: bool) -> tuple[str, bool, dict]:
    """渲染任务档案并按 ≤8 KB 预算收缩；返回 (md, truncated, limits)。"""
    limits = {key: 10**6 for key in TASK_SECTION_LIMITS} if full else dict(TASK_SECTION_LIMITS)
    md = _render_task_md(data, limits)
    if full:
        return md, False, limits
    truncated = False
    while len(md.encode("utf-8")) > TASK_OUTPUT_BUDGET:
        progressed = False
        for key in ("evidence", "dispatch", "commits", "decisions", "memory"):
            if limits[key] > _MIN_SECTION_LIMIT:
                limits[key] = max(_MIN_SECTION_LIMIT, limits[key] // 2)
                progressed = True
                break
        if not progressed:
            break
        truncated = True
        md = _render_task_md(data, limits)
    if len(md.encode("utf-8")) > TASK_OUTPUT_BUDGET:
        md = hard_truncate(md, TASK_OUTPUT_BUDGET)
        truncated = True
    # 即使不超预算，只要源数据条数被 section 上限截过，也要标 truncated（不静默省略）
    if any(len(data.get(key, [])) > limits[key] for key in TASK_SECTION_LIMITS):
        truncated = True
    return md, truncated, limits


def cmd_task(repo: Path, args) -> int:
    data = collect_task(repo, args.id, args.full)
    md, truncated, limits = fit_task_md(data, args.full)
    data["output"] = {
        "bytes": len(md.encode("utf-8")),
        "budget": None if args.full else TASK_OUTPUT_BUDGET,
        "truncated": truncated,
        "section_limits": limits if truncated else None,
    }
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(md)
    return 0


# ---------------------------------------------------------------------------
# 2) member —— 成员时间线
# ---------------------------------------------------------------------------
def collect_member(repo: Path, member: str, since: datetime | None) -> dict:
    snapshot = load_snapshot(repo)
    agents = load_agents(repo)
    identity = None
    for entry in agents["agents"]:
        if entry.get("id") == member:
            identity = {
                "source": AGENTS_REL,
                "name": entry.get("name"),
                "status": entry.get("status"),
                "model": entry.get("model"),
                "tier": entry.get("tier"),
                "domain": entry.get("domain"),
            }
            break
    if identity is None:
        for entry in snapshot["members"]:
            if entry.get("target") == member:
                identity = {
                    "source": f"{SNAPSHOT_REL}:members",
                    "name": entry.get("target"),
                    "status": entry.get("status"),
                    "model": entry.get("model"),
                    "tier": None,
                    "domain": entry.get("description"),
                }
                break
    if identity is None:
        retired = next((r for r in snapshot["retired"] if r.get("target") == member), None)
        identity = {
            "source": "未在 agents.json / snapshot 中找到（可能是已退役或从未存在）",
            "status": "unknown",
            "retired_entry": retired,
        }

    dispatch = load_dispatch(repo)
    events = []
    for row in dispatch["rows"]:
        if member not in (row.get("actor"), row.get("target")):
            continue
        stamp = parse_ts(row.get("ts"))
        if since is not None and stamp is not None and stamp < since:
            continue
        events.append(row)
    events.sort(key=lambda row: parse_ts(row.get("ts")) or now_local(), reverse=True)

    commits, git_error = git_commits(repo, needle=member, since=since, max_count=50)

    tasks = []
    for task in snapshot["tasks"].values():
        if task.get("owner") == member:
            tasks.append(
                {
                    "id": task.get("id"),
                    "status": task.get("status"),
                    "subject": task.get("subject"),
                    "revision": task.get("revision"),
                }
            )
    for recent in snapshot["recent"]:
        if recent.get("ownerName") == member and not any(t["id"] == recent.get("id") for t in tasks):
            tasks.append({"id": recent.get("id"), "status": "completed", "subject": recent.get("subject"), "revision": None})

    memory = load_memory_cards(repo)
    card_text = memory["cards"].get(member)
    gaps = []
    if dispatch["status"] != "ok":
        gaps.append(f"dispatch-log 不可用（{dispatch['status']}）")
    if git_error:
        gaps.append(f"git log 不可用：{git_error}")
    if snapshot["status"] != "ok":
        gaps.append(f"任务板快照不可用（{snapshot['status']}），名下任务可能不全")
    if card_text is None:
        gaps.append("该成员没有 memory 卡（task-87 机制刚起步；退役时才会强制生成）")

    return {
        "command": "member",
        "generated_at": now_iso(),
        "id": member,
        "since": fmt_iso(since),
        "identity": identity,
        "sources": {
            "agents": {"path": AGENTS_REL, "status": agents["status"]},
            "snapshot": {"path": SNAPSHOT_REL, "status": snapshot["status"], "exported_at": fmt_iso(snapshot["exported_at"])},
            "dispatch_log": {"path": DISPATCH_LOG_REL, "status": dispatch["status"]},
            "memory": {"path": MEMORY_DIR_REL, "status": memory["status"]},
        },
        "dispatch": events,
        "commits": commits,
        "tasks": tasks,
        "memory_card": {"path": f"{MEMORY_DIR_REL}/{member}.md", "present": card_text is not None,
                        "bytes": len(card_text.encode("utf-8")) if card_text else 0},
        "data_gaps": gaps,
        "summary": {
            "events": len(events),
            "commits": len(commits),
            "tasks": len(tasks),
            "last_event": fmt_iso(parse_ts(events[0].get("ts"))) if events else None,
        },
    }


def _render_member_md(data: dict, limit: int) -> str:
    ident = data["identity"]
    lines = [f"# 成员时间线：{data['id']}（只读投影，since={data['since'] or '全部'})", ""]
    lines.append(
        f"> 生成 {data['generated_at']}；源：agents {data['sources']['agents']['status']} · "
        f"snapshot@{data['sources']['snapshot']['exported_at'] or '?'} · dispatch {data['sources']['dispatch_log']['status']} · "
        f"memory {data['sources']['memory']['status']}"
    )
    lines.append("> 投影不是事实源，删除可重建。")
    lines.append("")
    lines.append("## 身份")
    lines.append(f"- 来源：{ident.get('source')}")
    if ident.get("status"):
        lines.append(f"- status：{ident['status']}；model：{ident.get('model') or '?'}；tier：{ident.get('tier') or '?'}")
    if ident.get("domain"):
        lines.append(f"- domain/描述：{ident['domain']}")
    lines.append("")
    lines.append(
        f"## 派发/生命周期（{len(data['dispatch'])} 条；最近：{data['summary']['last_event'] or '—'}）"
    )
    for row in data["dispatch"][:limit]:
        detail = row.get("desc") or ""
        lines.append(
            f"- {fmt_ts(row.get('ts'))} `{row.get('phase')}` {row.get('actor')} → {row.get('target')}"
            + (f"：{detail}" if detail else "")
            + (f" task={row['task']}" if row.get("task") else "")
        )
    if len(data["dispatch"]) > limit:
        lines.append(f"- …另有 {len(data['dispatch']) - limit} 条（--full 展开）")
    lines.append("")
    lines.append(f"## 提交（提交信息含成员名，{len(data['commits'])} 条）")
    for commit in data["commits"][:limit]:
        lines.append(f"- `{commit['sha'][:10]}` {fmt_ts(commit['date'])} {commit['subject']}")
    if len(data["commits"]) > limit:
        lines.append(f"- …另有 {len(data['commits']) - limit} 条（--full 展开）")
    lines.append("")
    lines.append(f"## 名下任务（快照口径，{len(data['tasks'])} 条）")
    for task in data["tasks"]:
        lines.append(f"- `{task['id']}` **{task['status']}** {task['subject']}")
    lines.append("")
    card = data["memory_card"]
    lines.append("## 记忆卡")
    lines.append(
        f"- `{card['path']}`：" + (f"存在（{card['bytes']} B）" if card["present"] else "不存在（task-87 机制刚起步）")
    )
    lines.append("")
    if data["data_gaps"]:
        lines.append("## 数据缺口")
        for gap in data["data_gaps"]:
            lines.append(f"- {gap}")
        lines.append("")
    return "\n".join(lines)


def cmd_member(repo: Path, args) -> int:
    since = parse_since(args.since)
    data = collect_member(repo, args.id, since)
    md = _render_member_md(data, 10**6 if args.full else 15)
    if not args.full and len(md.encode("utf-8")) > MEMBER_OUTPUT_BUDGET:
        md = hard_truncate(md, MEMBER_OUTPUT_BUDGET)
        data["output"] = {"bytes": len(md.encode("utf-8")), "budget": MEMBER_OUTPUT_BUDGET, "truncated": True}
    else:
        data["output"] = {"bytes": len(md.encode("utf-8")), "budget": None, "truncated": False}
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(md)
    return 0


# ---------------------------------------------------------------------------
# 3) decision —— 决策检索 + 索引自检（通道③）
# ---------------------------------------------------------------------------
def decision_matches(row: dict, keyword: str) -> bool:
    haystack = [
        str(row.get("question") or ""),
        str(row.get("choice") or ""),
        str(row.get("why") or ""),
        str(row.get("scope") or ""),
        str(row.get("task_id") or ""),
        str(row.get("id") or ""),
    ]
    for alt in row.get("alternatives") or []:
        if isinstance(alt, dict):
            haystack.extend([str(alt.get("option") or ""), str(alt.get("why_rejected") or "")])
    return keyword.lower() in "\n".join(haystack).lower()


def validate_decision_index(repo: Path, rows: list[dict]) -> dict:
    """按设计 §2.3.3 六条做轻量校验（fail-closed 的读侧对应物）。"""
    problems: list[dict] = []
    id_re = re.compile(r"^dec-\d{8}-[0-9a-f]{8}$")
    last_ts: datetime | None = None
    ids: set[str] = set()
    for index, row in enumerate(rows, 1):
        rid = row.get("id")
        if not rid or not id_re.match(str(rid)):
            problems.append({"line": index, "rule": "id-shape", "detail": f"id={rid!r} 不匹配 dec-YYYYMMDD-<sha8>"})
        elif rid in ids:
            problems.append({"line": index, "rule": "id-unique", "detail": f"id={rid} 重复"})
        else:
            ids.add(rid)
        stamp = parse_ts(row.get("ts"))
        if stamp is None:
            problems.append({"line": index, "rule": "ts-parse", "detail": f"ts={row.get('ts')!r} 不可解析"})
        else:
            if last_ts is not None and stamp < last_ts:
                problems.append({"line": index, "rule": "ts-monotonic", "detail": "ts 早于上一条（append-only 时间倒流）"})
            last_ts = stamp
        if not row.get("decided_by"):
            problems.append({"line": index, "rule": "decided_by", "detail": "缺 decided_by"})
        if not row.get("choice"):
            problems.append({"line": index, "rule": "choice", "detail": "缺 choice"})
        alternatives = row.get("alternatives")
        if not alternatives and not row.get("no_alternative_reason"):
            problems.append(
                {"line": index, "rule": "alternatives", "detail": "alternatives 为空且无 no_alternative_reason"}
            )
        if not isinstance(row.get("reconstructed"), bool):
            problems.append({"line": index, "rule": "reconstructed", "detail": "reconstructed 必须是布尔（防「事后编理由」伪装）"})
        for item in row.get("evidence") or []:
            if isinstance(item, dict) and item.get("ref"):
                resolved = resolve_evidence(repo, item)
                if resolved["state"] in ("missing", "empty"):
                    problems.append(
                        {
                            "line": index,
                            "rule": "evidence-ref",
                            "detail": f"evidence.ref={item.get('ref')!r} 不可解析（{resolved['detail']}）",
                        }
                    )
    return {
        "checked_count": len(rows),
        "bad_count": len(problems),
        "ok": not problems,
        "problems": problems,
        "max_ts": fmt_iso(last_ts),
    }


def _render_decision_md(data: dict, limit: int) -> str:
    lines = [f"# 决策检索：{data['query']!r}（只读投影）", ""]
    lines.append(f"> 生成 {data['generated_at']}；源：{DECISIONS_REL}（{data['status']}）")
    lines.append("> 投影不是事实源；长论证留在 evidence 指向的文档，索引只存 choice/why/指针（设计 §2.3）。")
    lines.append("")
    if data["status"] == "not_established":
        lines.append("**NOT_ESTABLISHED**：决策索引尚未建立（task-102 未落地）。")
        lines.append("⇒ 这表示「查询不到」，**不代表没有做过决策**；当前决策理由仍散落在提交/报告里。")
        return "\n".join(lines)
    if data["status"] == "corrupt":
        lines.append(f"**FAIL**：决策索引存在坏行 {len(data.get('bad_lines', []))} 条，查询结果不可靠：")
        for bad in data.get("bad_lines", []):
            lines.append(f"- line {bad['line']}: {bad['error']}")
        lines.append("")
    lines.append(f"## 命中 {data['matched_count']} 条（展示 ≤{limit}）")
    for row in data["items"][:limit]:
        lines.append(f"### `{row.get('id')}` · {fmt_ts(row.get('ts'))} · {row.get('decided_by')}")
        lines.append(f"- question：{row.get('question')}")
        lines.append(f"- choice：**{row.get('choice')}**")
        for alt in row.get("alternatives") or []:
            if isinstance(alt, dict):
                lines.append(f"- 放弃：{alt.get('option')} —— {alt.get('why_rejected')}")
        lines.append(f"- why：{row.get('why')}")
        if row.get("rule_refs"):
            lines.append(f"- rule_refs：{', '.join(row['rule_refs'])}")
        lines.append(
            f"- reversibility：{row.get('reversibility') or 'R2(默认)'}；reconstructed：{row.get('reconstructed')}"
            f"；task：{row.get('task_id') or '—'}"
        )
        for item in row.get("evidence") or []:
            resolved = resolve_evidence(data.get("_repo"), item) if isinstance(item, dict) else None
            ref = item.get("ref") if isinstance(item, dict) else item
            state = f" [{resolved['state']}]" if resolved else ""
            lines.append(f"- evidence：`{ref}`{state}")
        lines.append("")
    if data["status"] == "ok" and not data["items"]:
        lines.append("- （索引已建立，但没有命中该关键词的决策）")
    return "\n".join(lines)


def collect_decisions(repo: Path, keyword: str | None, since: datetime | None, limit: int, doctor: bool) -> dict:
    index = load_decisions(repo)
    data = {
        "command": "decision",
        "generated_at": now_iso(),
        "query": keyword,
        "since": fmt_iso(since),
        "status": index["status"],
        "path": index["path"],
        "total": len(index["rows"]),
        "bad_lines": index["bad"],
        "items": [],
        "matched_count": 0,
        "doctor": None,
        "_repo": repo,
    }
    if doctor:
        data["doctor"] = validate_decision_index(repo, index["rows"])
        if index["status"] == "missing":
            data["status"] = "not_established"
            data["doctor"]["ok"] = False
            data["doctor"]["problems"].append({"rule": "index-missing", "detail": f"{DECISIONS_REL} 不存在（task-102 未落地）"})
        return data
    if index["status"] != "ok":
        if index["status"] == "missing":
            data["status"] = "not_established"  # 不是「没有决策」
        return data
    items = []
    for row in index["rows"]:
        if keyword and not decision_matches(row, keyword):
            continue
        if since is not None:
            stamp = parse_ts(row.get("ts"))
            if stamp is not None and stamp < since:
                continue
        items.append(row)
    items.sort(key=lambda row: parse_ts(row.get("ts")) or now_local(), reverse=True)
    data["matched_count"] = len(items)
    data["items"] = items
    return data


def cmd_decision(repo: Path, args) -> int:
    data = collect_decisions(repo, args.grep, parse_since(args.since), args.limit, args.doctor)
    md = _render_decision_md(data, max(1, args.limit))
    if len(md.encode("utf-8")) > DECISION_OUTPUT_BUDGET:
        md = hard_truncate(md, DECISION_OUTPUT_BUDGET)
    data["output"] = {"bytes": len(md.encode("utf-8")), "budget": DECISION_OUTPUT_BUDGET}
    clean = {key: value for key, value in data.items() if key != "_repo"}
    if args.doctor:
        if clean["status"] == "not_established":
            md = _render_decision_md(data, max(1, args.limit))
        if args.json:
            print(json.dumps(clean, ensure_ascii=False, indent=2))
        else:
            print(md)
            print(f"\nDOCTOR: {'PASS' if clean['doctor']['ok'] else 'FAIL'}"
                  f"（checked={clean['doctor']['checked_count']}，bad={clean['doctor']['bad_count']}）")
            for problem in clean["doctor"]["problems"]:
                print(f"  - [{problem.get('rule')}] {problem.get('detail')}")
        return 0 if clean["doctor"]["ok"] else 1
    if clean["status"] == "corrupt":
        if args.json:
            print(json.dumps(clean, ensure_ascii=False, indent=2))
        else:
            print(md)
        return 1
    if args.json:
        print(json.dumps(clean, ensure_ascii=False, indent=2))
    else:
        print(md)
    return 0


# ---------------------------------------------------------------------------
# 4) risk —— R0/R1 风险动作清单（Phase 0 = git 可观测子集）
# ---------------------------------------------------------------------------
def _risk_from_commits(repo: Path, since: datetime) -> tuple[list[dict], list[str]]:
    args = [
        "log",
        "--all",
        f"--since={since.isoformat(timespec='seconds')}",
        "--format=@@%H%x1f%aI%x1f%s",
        "--numstat",
        "-M",
    ]
    ok, out, err = git(repo, *args)
    if not ok:
        return [], [f"git log 不可用：{err.strip() or 'not-a-git-repo'}"]

    commits: list[dict] = []
    current: dict | None = None
    for line in out.splitlines():
        if line.startswith("@@"):
            parts = line[2:].split("\x1f")
            current = {"sha": parts[0] if parts else "", "date": parts[1] if len(parts) > 1 else "",
                       "subject": parts[2] if len(parts) > 2 else "", "paths": [], "added": 0, "removed": 0}
            commits.append(current)
            continue
        match = re.match(r"^(\d+|-)\t(\d+|-)\t(.+)$", line)
        if match and current is not None:
            added = 0 if match.group(1) == "-" else int(match.group(1))
            removed = 0 if match.group(2) == "-" else int(match.group(2))
            current["added"] += added
            current["removed"] += removed
            current["paths"].append(match.group(3))

    risks: list[dict] = []
    t2_candidates: list[dict] = []
    t3_candidates: list[dict] = []
    for commit in commits:
        sha = commit["sha"][:10]
        date = fmt_ts(commit["date"])
        paths = commit["paths"]
        # R1 单向门：打包/发版资产（lessons §7：预验 + 回滚方案 + 人确认）
        if any(path == VERSION_FILE_REL or path.startswith("Package/") for path in paths):
            touched = [p for p in paths if p == VERSION_FILE_REL or p.startswith("Package/")]
            risks.append({
                "risk": "R1", "source": f"git:{sha}", "ts": date,
                "detail": f"改版本/打包资产：{', '.join(touched[:4])}",
                "rule_ref": "AGENTS.md#§0.5 L5；docs/guides/lead-dispatch-rules.md#4",
                "note": "发版/打包类单向门，需人授权并按 L5 先给回滚方案",
            })
        elif any(path == "pyproject.toml" for path in paths):
            risks.append({
                "risk": "R1", "source": f"git:{sha}", "ts": date,
                "detail": "改 pyproject.toml（可能含 version 行；需人工确认）",
                "rule_ref": "AGENTS.md#§0.5 L4；docs/guides/lead-dispatch-rules.md#4",
                "note": "版本文件属人权限（L4）；若仅改依赖需在报告中说明",
            })
        # T2 决策义务候选：删除 ≥20 行（设计 §2.3.6 T2）——不是风险判决，是「须写 Decision/Why」的触发
        if commit["removed"] >= RISK_DELETE_LINES:
            t2_candidates.append({
                "kind": "T2", "source": f"git:{sha}", "ts": date,
                "removed": commit["removed"], "added": commit["added"], "paths": len(paths),
                "stale_buffer_signal": commit["removed"] > commit["added"],
                "subject": commit["subject"][:80],
                "rule_ref": "设计稿 §2.3.6 T2；docs/guides/agent-team-lessons.md#§7（removed>added = 陈旧缓冲区覆盖信号）",
            })
        # T3 决策义务候选：回退/自修（设计 §2.3.6 T3）——须写 Decision/Why/Alternatives
        if REVERT_SUBJECT_RE.search(commit["subject"]) or SELF_FIX_RE.search(commit["subject"]):
            t3_candidates.append({
                "kind": "T3", "source": f"git:{sha}", "ts": date,
                "subject": commit["subject"][:100],
                "rule_ref": "设计稿 §2.3.6 T3；docs/guides/agent-team-lessons.md#§7",
            })
    t2_candidates.sort(key=lambda item: item["removed"], reverse=True)
    return risks, t2_candidates, t3_candidates, []


def _risk_from_reflog(repo: Path, since: datetime) -> tuple[list[dict], str | None]:
    ok, out, err = git(repo, "reflog", "show", "--date=iso-strict", "--format=%H%x1f%gd%x1f%gs")
    if not ok:
        return [], err.strip() or "git reflog 不可用"
    items: list[dict] = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) < 3:
            continue
        sha, gd, subject = parts[0], parts[1], parts[2]
        date_match = re.search(r"\{(.+?)\}", gd)
        stamp = parse_ts(date_match.group(1)) if date_match else None
        if stamp is None or stamp < since:
            continue
        if re.match(r"^(reset|checkout|restore):", subject):
            items.append({
                "risk": "R0", "source": f"reflog:{sha[:10]}", "ts": fmt_ts(stamp),
                "detail": subject[:120],
                "rule_ref": "docs/guides/agent-team-lessons.md#§7",
                "note": "reflog 是本地证据：可能是无害切换，需人工确认是否作用于 src/** 或未提交工作",
            })
    return items, None


def collect_risk(repo: Path, since: datetime) -> dict:
    risks, t2_candidates, t3_candidates, gaps = _risk_from_commits(repo, since)
    reflog_items, reflog_error = _risk_from_reflog(repo, since)
    risks.extend(reflog_items)
    if reflog_error:
        gaps.append(f"reflog 不可用：{reflog_error}")

    trajectory_dir = repo / TRAJECTORY_DIR_REL
    trajectory_items = []
    if trajectory_dir.is_dir():
        for path in sorted(trajectory_dir.glob("*.jsonl")):
            rows, _bad = read_jsonl(path)
            for row in rows:
                risk = row.get("risk") or row.get("kind")
                if risk in ("R0", "R1", "gate_fail_continue", "write_without_read"):
                    if since is not None and (parse_ts(row.get("ts")) or since) < since:
                        continue
                    trajectory_items.append({"risk": risk, "source": f"{TRAJECTORY_DIR_REL}/{path.name}",
                                             "ts": fmt_ts(row.get("ts")), "detail": str(row)[:200],
                                             "rule_ref": "设计稿 §2.1(c)", "note": "来自 task-95 轨迹"})
        risks.extend(trajectory_items)
    else:
        gaps.append(
            "trajectory 未落地（task-95 未完成）⇒ 只能覆盖 git 可观测子集；"
            "`write_without_read` / `gate_fail_continue` 两类风险目前完全不可见"
        )
    gaps.append("force push / 无提交的 checkout 在 git log 中不可见（reflog 仅本地、非权威）；需远端审计或插件轨迹")
    gaps.append("R0/R1 的对抗复核到期（A5）需决策索引（task-102）落地后才能机检")

    counts: dict[str, int] = {"R0": 0, "R1": 0}
    for item in risks:
        counts[item["risk"]] = counts.get(item["risk"], 0) + 1
    counts["T2"] = len(t2_candidates)
    counts["T3"] = len(t3_candidates)
    risks.sort(key=lambda item: item.get("ts") or "", reverse=True)
    return {
        "command": "risk",
        "generated_at": now_iso(),
        "since": fmt_iso(since),
        "risks": risks,
        "count": len(risks),
        "counts": counts,
        "t2_candidates": t2_candidates,
        "t3_candidates": t3_candidates,
        "trajectory": {"path": TRAJECTORY_DIR_REL, "status": "ok" if trajectory_dir.is_dir() else "missing",
                       "items": len(trajectory_items)},
        "coverage_gaps": gaps,
    }


def cmd_risk(repo: Path, args) -> int:
    since = parse_since(args.since) or (now_local() - timedelta(days=7))
    data = collect_risk(repo, since)
    full = args.full
    risk_limit = 10**6 if full else 40
    t2_limit = 10**6 if full else 10
    t3_limit = 10**6 if full else 5
    lines = [f"# 风险动作清单（since={data['since']}；Phase 0 = git 可观测子集）", ""]
    lines.append(
        f"> 生成 {data['generated_at']}；R0/R1 命中 {data['count']} 条；统计 {data['counts']}"
    )
    lines.append("> 这是**清单**不是判决：每条都需人工/对抗复核（steward 不阻断，设计 §3.3 B2）。")
    lines.append("> 口径：R0/R1 引用 `agent-team-lessons.md §7`；T2/T3 是**决策记录义务候选**（设计 §2.3.6），不是风险判决。")
    lines.append("")
    lines.append(f"## 1. R0/R1 风险动作（{data['count']} 条，展示 ≤{risk_limit}）")
    if not data["risks"]:
        lines.append("- 窗口内无可从 git 观测到的 R0/R1 动作（**不等于**没发生：见覆盖盲区）")
    for item in data["risks"][:risk_limit]:
        lines.append(f"- **[{item['risk']}]** {item['ts']} `{item['source']}` —— {item['detail']}")
        lines.append(f"  - rule_ref：{item['rule_ref']}；{item['note']}")
    if len(data["risks"]) > risk_limit:
        lines.append(f"- …另有 {len(data['risks']) - risk_limit} 条（--full 展开）")
    lines.append("")
    lines.append(
        f"## 2. 单向门候选 T2（删除 ≥{RISK_DELETE_LINES} 行，{len(data['t2_candidates'])} 条，"
        f"按删除量降序展示 ≤{t2_limit}）"
    )
    lines.append("- 这些**不是**风险动作本身，而是「该提交应带 Decision/Why」的触发（设计 §2.3.6 T2）；")
    lines.append("  `removed>added` 另是「陈旧缓冲区覆盖」信号（lessons §7），需停手核对 diff。")
    for item in data["t2_candidates"][:t2_limit]:
        signal = "；**removed>added（疑似陈旧缓冲区覆盖）**" if item["stale_buffer_signal"] else ""
        lines.append(
            f"- {item['ts']} `{item['source']}` 删除 {item['removed']} / 新增 {item['added']} 行，"
            f"{item['paths']} 个文件{signal} —— {item['subject']}"
        )
    if len(data["t2_candidates"]) > t2_limit:
        lines.append(f"- …另有 {len(data['t2_candidates']) - t2_limit} 条（--full / --json 展开）")
    lines.append("")
    lines.append(f"## 3. 回退/自修候选 T3（{len(data['t3_candidates'])} 条，展示 ≤{t3_limit}）")
    lines.append("- 同样不是风险判决：T3 触发「必须写 Decision/Why/Alternatives」的决策记录义务。")
    for item in data["t3_candidates"][:t3_limit]:
        lines.append(f"- {item['ts']} `{item['source']}` —— {item['subject']}")
    if len(data["t3_candidates"]) > t3_limit:
        lines.append(f"- …另有 {len(data['t3_candidates']) - t3_limit} 条（--full 展开）")
    lines.append("")
    lines.append("## 4. 覆盖盲区（显式，不静默）")
    for gap in data["coverage_gaps"]:
        lines.append(f"- {gap}")
    lines.append("")
    md = "\n".join(lines)
    data["output"] = {"bytes": len(md.encode("utf-8"))}
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(md)
    return 0


# ---------------------------------------------------------------------------
# 5) doctor —— 数据源自查（显式 FAIL，不静默空）
# ---------------------------------------------------------------------------
def collect_doctor(repo: Path) -> dict:
    checks: list[dict] = []

    def add(name: str, status: str, detail: str, **extra) -> None:
        checks.append({"check": name, "status": status, "detail": detail, **extra})

    head = git_head(repo)
    add("git", "OK" if head["ok"] else "FAIL",
        f"{head.get('branch')}@{head.get('head')}" if head["ok"] else f"不可用：{head.get('error')}")

    snapshot = load_snapshot(repo)
    if snapshot["status"] != "ok":
        add("snapshot", "FAIL", f"{SNAPSHOT_REL} {snapshot['status']}" + (f"：{snapshot['error']}" if snapshot["error"] else ""))
    else:
        exported = snapshot["exported_at"]
        problems: list[str] = []
        if exported is None:
            problems.append("exportedAt 不可解析")
        else:
            age = now_local() - exported
            if age > timedelta(hours=SNAPSHOT_MAX_AGE_HOURS):
                problems.append(f"快照已 {human_age(exported)} 未重导出（阈值 {SNAPSHOT_MAX_AGE_HOURS}h）")
            agents_path = repo / AGENTS_REL
            if agents_path.is_file():
                agents_mtime = datetime.fromtimestamp(agents_path.stat().st_mtime).astimezone()
                if exported < agents_mtime - timedelta(seconds=30):
                    problems.append("快照 exportedAt 早于 agents.json mtime（快照不可能反映名册注册修改）")
            dispatch_for_fresh = load_dispatch(repo)
            if dispatch_for_fresh["latest"] and exported + timedelta(seconds=30) < dispatch_for_fresh["latest"]:
                problems.append(f"快照早于最新派发记录（{fmt_iso(dispatch_for_fresh['latest'])}）⇒ 可能缺任务")
        if problems:
            add("snapshot", "FAIL", "；".join(problems), exported_at=fmt_iso(exported))
        else:
            add("snapshot", "OK",
                f"{snapshot['task_count']} 任务 / {len(snapshot['members'])} 成员；exportedAt={fmt_iso(exported)}"
                f"（{human_age(exported)} 前）", exported_at=fmt_iso(exported))

    dispatch = load_dispatch(repo)
    if dispatch["status"] == "missing":
        add("dispatch_log", "FAIL", f"{DISPATCH_LOG_REL} 不存在")
    elif dispatch["status"] == "corrupt":
        add("dispatch_log", "FAIL", f"{DISPATCH_LOG_REL} 有坏行/坏字段：{dispatch['problems'][:3]}")
    else:
        stale = dispatch["latest"] is None or (now_local() - dispatch["latest"]) > timedelta(days=DISPATCH_MAX_AGE_DAYS)
        add("dispatch_log", "WARN" if stale else "OK",
            f"{dispatch['count']} 条，latest={fmt_iso(dispatch['latest'])}"
            + ("（超过 7 天未追加：可能只是没派发，也可能是没记录）" if stale else ""),
            count=dispatch["count"])

    agents = load_agents(repo)
    add("agents", "OK" if agents["status"] == "ok" else "WARN",
        f"{AGENTS_REL} {agents['status']}" + (f"（{len(agents['agents'])} 名成员）" if agents["status"] == "ok" else "（member 命令将退回快照口径）"))

    decisions = load_decisions(repo)
    if decisions["status"] == "missing":
        add("decisions", "WARN",
            f"{DECISIONS_REL} 不存在（task-102/task-99 未落地）⇒ decision 查询返回 NOT_ESTABLISHED，不是「无决策」")
    elif decisions["status"] == "corrupt":
        add("decisions", "FAIL", f"{DECISIONS_REL} 存在坏行：{decisions['bad'][:3]}")
    else:
        validation = validate_decision_index(repo, decisions["rows"])
        add("decisions", "OK" if validation["ok"] else "FAIL",
            f"{len(decisions['rows'])} 条决策，索引校验 bad={validation['bad_count']}"
            + ("" if validation["ok"] else f"：{validation['problems'][:3]}"),
            checked_count=validation["checked_count"])

    memory = load_memory_cards(repo)
    add("memory", "OK" if memory["status"] == "ok" else "WARN",
        f"{MEMORY_DIR_REL} {memory['status']}" + (f"（{len(memory['cards'])} 张卡）" if memory["status"] == "ok" else "（task-87 卡机制刚起步）"))

    trajectory_dir = repo / TRAJECTORY_DIR_REL
    add("trajectory", "WARN" if not trajectory_dir.is_dir() else "OK",
        f"{TRAJECTORY_DIR_REL} " + ("不存在（task-95 未落地）⇒ risk 只覆盖 git 子集" if not trajectory_dir.is_dir() else "存在"))

    if snapshot["status"] == "ok":
        tasks = list(snapshot["tasks"].values())
        with_evidence = [t for t in tasks if t.get("evidence")]
        add("snapshot_task_fields", "INFO",
            f"tasks[] {len(tasks)} 条，含 evidence {len(with_evidence)} 条；"
            "无 description/createdAt/updatedAt（设计 G2，靠 live 任务板补）")

    fails = [check for check in checks if check["status"] == "FAIL"]
    warns = [check for check in checks if check["status"] == "WARN"]
    return {
        "command": "doctor",
        "generated_at": now_iso(),
        "ok": not fails,
        "fails": len(fails),
        "warns": len(warns),
        "checks": checks,
    }


def cmd_doctor(repo: Path, args) -> int:
    data = collect_doctor(repo)
    lines = ["# work_record.py doctor（数据源自查）", ""]
    lines.append(f"> 生成 {data['generated_at']}；只读，不修复。FAIL ⇒ 退出码 1（不静默空）。")
    lines.append("")
    for check in data["checks"]:
        lines.append(f"- [{check['status']}] **{check['check']}**：{check['detail']}")
    lines.append("")
    lines.append(f"RESULT: {'PASS' if data['ok'] else 'FAIL'}（FAIL={data['fails']}，WARN={data['warns']}）")
    md = "\n".join(lines)
    data["output"] = {"bytes": len(md.encode("utf-8"))}
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(md)
    return 0 if data["ok"] else 1


# ---------------------------------------------------------------------------
# 自测：绿路径必须绿、红路径必须红
# ---------------------------------------------------------------------------
def _selftest_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _selftest_commit(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    ok, out, err = git(repo, "commit", "-q", "-m", message)
    if not ok:
        raise RuntimeError(f"selftest git commit 失败：{err}")
    ok, out, _ = git(repo, "rev-parse", "HEAD")
    return out.strip() if ok else ""


def _selftest_capture(argv: list[str]) -> tuple[int, str]:
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(argv)
    return code, buffer.getvalue()


def selftest() -> int:
    failures: list[str] = []

    def expect(name: str, condition: bool) -> None:
        if not condition:
            failures.append(name)

    iso = lambda delta: (now_local() + delta).isoformat(timespec="seconds")  # noqa: E731

    with tempfile.TemporaryDirectory(prefix="work-record-selftest-") as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()

        # --- 初始化 fixture 仓库 ---
        _selftest_write(repo / ".gitignore", "artifacts/\n")
        _selftest_write(repo / "docs" / "plan.md", "# plan\n")
        _selftest_write(repo / "src" / "old_module.py", "\n".join(f"line {i}" for i in range(30)) + "\n")
        _selftest_write(repo / "Package" / "installer.txt", "pack-1\n")
        _selftest_write(repo / "pyproject.toml", "[project]\nname='x'\nversion='0.0.1'\n")
        _selftest_write(repo / "team" / "memory" / "worker.md",
                        "## worker · task-95\n### 我试过但失败的路\n- 用 session 替代轨迹 —— 失败原因：42MB 且污染判断\n")
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "selftest@example.com")
        git(repo, "config", "user.name", "selftest")
        git(repo, "config", "commit.gpgsign", "false")
        _selftest_commit(repo, "feat: task-95 轨迹投影第一阶段")
        # 删除 ≥20 行
        _selftest_write(repo / "src" / "old_module.py", "line 0\n")
        _selftest_commit(repo, "fix: 清理旧实现")
        # 改 Package（R1）
        _selftest_write(repo / "Package" / "installer.txt", "pack-2\n")
        _selftest_commit(repo, "chore(release): Package 打包资产更新")
        # 回退类提交
        _selftest_write(repo / "src" / "tmp_probe.py", "x = 1\n")
        _selftest_commit(repo, "feat: 临时探针")
        git(repo, "revert", "--no-edit", "HEAD")

        # --- 任务板快照 fixture ---
        long_evidence = [
            f"artifacts/agent/verify/some-rather-long-directory-name-{i:03d}/report-with-long-name-{i:03d}.md"
            for i in range(120)
        ]
        snapshot = {
            "schema": "team-board-snapshot/v3",
            "exportedAt": iso(timedelta(minutes=-1)),
            "exportedBy": "selftest",
            "members": [{"target": "worker", "role": "teammate", "status": "active", "model": "deepseek-flash"}],
            "retired": [],
            "tasks": [
                {"id": "task-95", "status": "in_progress", "subject": "轨迹机制", "owner": "worker",
                 "writeScopes": ["docs/**"], "blockedBy": [], "revision": 1,
                 "evidence": ["docs/plan.md", "artifacts/agent/verify/x.md", "docs/missing.md"]},
                {"id": "task-87", "status": "completed", "subject": "大任务（预算测试）", "owner": "worker",
                 "writeScopes": [], "blockedBy": [], "revision": 2, "evidence": long_evidence},
            ],
            "completedRecent": [], "inactiveOwners": [], "note": "selftest",
        }
        _selftest_write(repo / SNAPSHOT_REL, json.dumps(snapshot, ensure_ascii=False))
        _selftest_write(repo / DISPATCH_LOG_REL, "\n".join(json.dumps(row, ensure_ascii=False) for row in [
            {"ts": iso(timedelta(hours=-2)), "actor": "lead", "phase": "spawn", "target": "worker",
             "task": "task-95", "desc": "派发任务"},
            {"ts": iso(timedelta(hours=-1)), "actor": "worker", "phase": "done", "target": "lead",
             "task": "task-95", "desc": "完成", "outcome": "pass", "report": "artifacts/agent/verify/x.md"},
        ]) + "\n")

        # --- doctor：正常 fixture 必须 PASS（decisions 缺失只是 WARN）---
        code, out = _selftest_capture(["--repo", str(repo), "doctor", "--json"])
        report = json.loads(out)
        expect("doctor-normal-must-pass", code == 0 and report["ok"] is True)
        expect("doctor-decisions-missing-is-warn", any(
            c["check"] == "decisions" and c["status"] == "WARN" for c in report["checks"]))
        expect("doctor-trajectory-missing-is-warn", any(
            c["check"] == "trajectory" and c["status"] == "WARN" for c in report["checks"]))

        # --- task：任务档案 join 与证据三态 ---
        code, out = _selftest_capture(["--repo", str(repo), "task", "--id", "task-95", "--json"])
        task = json.loads(out)
        expect("task-exit-0", code == 0)
        expect("task-board-found", task["board"] is not None and task["board"]["owner"] == "worker")
        expect("task-dispatch-2", len(task["dispatch"]) == 2)
        expect("task-commits-found", len(task["commits"]) >= 1)
        states = {item["raw"]: item["state"] for item in task["evidence"]}
        expect("task-evidence-exists", states.get("docs/plan.md") == "exists")
        expect("task-evidence-gitignored", states.get("artifacts/agent/verify/x.md") == "gitignored")
        expect("task-evidence-missing", states.get("docs/missing.md") == "missing")
        expect("task-decisions-not-established", task["decisions_status"] == "missing" and any(
            "决策索引未建立" in gap for gap in task["data_gaps"]))
        expect("task-memory-hit", len(task["memory"]) == 1)

        # --- 不存在的任务：必须显式 data_gaps，而不是空结果 ---
        code, out = _selftest_capture(["--repo", str(repo), "task", "--id", "task-999", "--json"])
        missing_task = json.loads(out)
        expect("task-unknown-id-explicit-gap", code == 0 and any(
            "未找到该任务" in gap for gap in missing_task["data_gaps"]))

        # --- 体量预算：默认 ≤8 KB 且标 truncated；--full 可超 ---
        _code, out_default = _selftest_capture(["--repo", str(repo), "task", "--id", "task-87"])
        _code, out_full = _selftest_capture(["--repo", str(repo), "task", "--id", "task-87", "--full"])
        expect("task-default-budget-le-8kb", len(out_default.encode("utf-8")) <= TASK_OUTPUT_BUDGET + 200)
        expect("task-default-truncated-marker", "截断" in out_default or "预算" in out_default)
        expect("task-full-larger-than-default", len(out_full.encode("utf-8")) > len(out_default.encode("utf-8")))
        code, out = _selftest_capture(["--repo", str(repo), "task", "--id", "task-87", "--json"])
        task87 = json.loads(out)
        expect("task-json-truncated-true", task87["output"]["truncated"] is True)
        expect("task-json-bytes-le-8kb", task87["output"]["bytes"] <= TASK_OUTPUT_BUDGET)

        # --- member 时间线 ---
        code, out = _selftest_capture(["--repo", str(repo), "member", "--id", "worker", "--since", "7d", "--json"])
        member = json.loads(out)
        expect("member-exit-0", code == 0)
        expect("member-dispatch-2", len(member["dispatch"]) == 2)
        expect("member-tasks-2", len(member["tasks"]) == 2)
        expect("member-identity", member["identity"].get("status") == "active")
        expect("member-memory-card-present", member["memory_card"]["present"] is True)

        # --- decision：索引未建立必须 NOT_ESTABLISHED ---
        code, out = _selftest_capture(["--repo", str(repo), "decision", "--grep", "轨迹", "--json"])
        decision = json.loads(out)
        expect("decision-not-established", code == 0 and decision["status"] == "not_established")
        code, _out = _selftest_capture(["--repo", str(repo), "decision", "--doctor"])
        expect("decision-doctor-missing-index-fails", code == 1)

        # --- decision：合法索引可检索 ---
        valid_decision = {
            "id": "dec-20261024-abcdef01", "ts": iso(timedelta(minutes=-30)), "decided_by": "lead",
            "scope": "task-95", "question": "轨迹存哪", "choice": "artifacts/ 不进 git",
            "alternatives": [{"option": "进 git", "why_rejected": "体量大且可再生"}],
            "why": "体量大且可再生", "evidence": [{"kind": "doc", "ref": "docs/plan.md"}],
            "rule_refs": ["设计稿#§2.1"], "reversibility": "R2", "task_id": "task-95",
            "reconstructed": False,
        }
        _selftest_write(repo / DECISIONS_REL, json.dumps(valid_decision, ensure_ascii=False) + "\n")
        code, out = _selftest_capture(["--repo", str(repo), "decision", "--grep", "轨迹", "--json"])
        decision = json.loads(out)
        expect("decision-grep-hit", code == 0 and decision["matched_count"] == 1)
        code, out = _selftest_capture(["--repo", str(repo), "decision", "--doctor", "--json"])
        expect("decision-doctor-valid", code == 0 and json.loads(out)["doctor"]["ok"] is True)
        code, out = _selftest_capture(["--repo", str(repo), "task", "--id", "task-95", "--json"])
        expect("task-decision-joined", len(json.loads(out)["decisions"]) == 1)

        # --- 非法决策（缺 choice / reconstructed 非布尔）⇒ doctor 与 decision --doctor 都必须红 ---
        bad_decision = {"id": "bad-id", "ts": iso(timedelta(minutes=-10)), "decided_by": "lead"}
        _selftest_write(repo / DECISIONS_REL,
                        json.dumps(valid_decision, ensure_ascii=False) + "\n" +
                        json.dumps(bad_decision, ensure_ascii=False) + "\n")
        code, _out = _selftest_capture(["--repo", str(repo), "decision", "--doctor"])
        expect("decision-doctor-invalid-fails", code == 1)
        code, _out = _selftest_capture(["--repo", str(repo), "doctor"])
        expect("doctor-invalid-decisions-fails", code == 1)
        # 还原为合法索引
        _selftest_write(repo / DECISIONS_REL, json.dumps(valid_decision, ensure_ascii=False) + "\n")
        code, _out = _selftest_capture(["--repo", str(repo), "doctor"])
        expect("doctor-back-to-pass", code == 0)

        # --- risk：Package / 删除≥20行 / 回退 必须被识别 ---
        code, out = _selftest_capture(["--repo", str(repo), "risk", "--since", "7d", "--json"])
        risk = json.loads(out)
        risk_details = " ".join(item["detail"] for item in risk["risks"])
        t2_sources = " ".join(item["source"] for item in risk["t2_candidates"])
        t3_subjects = " ".join(item["subject"] for item in risk["t3_candidates"])
        expect("risk-exit-0", code == 0)
        expect("risk-package-detected", "打包资产" in risk_details)
        expect("risk-t2-large-deletion-detected", len(risk["t2_candidates"]) >= 1 and t2_sources)
        expect("risk-t3-revert-detected", "Revert" in t3_subjects or "回退" in t3_subjects)
        expect("risk-coverage-gaps-explicit", any("trajectory" in gap for gap in risk["coverage_gaps"]))
        expect("risk-counts-consistent", risk["counts"]["R1"] >= 1)

        # --- doctor 红路径：缺 snapshot / 坏 JSON / 快照过旧 ---
        snapshot_path = repo / SNAPSHOT_REL
        snapshot_path.rename(repo / "snapshot.bak")
        code, _out = _selftest_capture(["--repo", str(repo), "doctor"])
        expect("doctor-missing-snapshot-fails", code == 1)
        (repo / "snapshot.bak").rename(snapshot_path)

        snapshot_path.write_text("{not-json", encoding="utf-8")
        code, _out = _selftest_capture(["--repo", str(repo), "doctor"])
        expect("doctor-corrupt-snapshot-fails", code == 1)

        stale = dict(snapshot)
        stale["exportedAt"] = iso(timedelta(hours=-48))
        snapshot_path.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")
        code, _out = _selftest_capture(["--repo", str(repo), "doctor"])
        expect("doctor-stale-snapshot-fails", code == 1)

        # 还原
        snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
        code, _out = _selftest_capture(["--repo", str(repo), "doctor"])
        expect("doctor-final-pass", code == 0)

    if failures:
        print(f"FAIL: {', '.join(failures)}")
        return 1
    print(
        "PASS: work_record.py selftest（绿：task join/证据三态/预算≤8KB/member/decision/risk/doctor；"
        "红：未知任务显式缺口、决策未建立、非法决策、缺快照、坏 JSON、快照过旧）"
    )
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="成员工作记录只读投影（task/member/decision/risk/doctor）；不写任何文件。"
    )
    parser.add_argument("--selftest", action="store_true", help="运行自测并退出")
    parser.add_argument("--repo", default=None, help="仓库根（默认脚本所在仓库；自测用）")
    sub = parser.add_subparsers(dest="command")

    task_parser = sub.add_parser("task", help="任务档案（join 任务板×dispatch-log×git×证据×决策×memory）")
    task_parser.add_argument("--id", required=True, help="任务 id（如 task-101）")
    task_parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    task_parser.add_argument("--full", action="store_true", help="展开全部（默认按 ≤8 KB 摘要）")

    member_parser = sub.add_parser("member", help="成员时间线")
    member_parser.add_argument("--id", required=True, help="成员 id（如 steward2）")
    member_parser.add_argument("--since", default="7d", help="时间窗（7d/12h/2w 或 ISO 日期）")
    member_parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    member_parser.add_argument("--full", action="store_true", help="展开全部")

    decision_parser = sub.add_parser("decision", help="决策检索 / 索引自检")
    decision_parser.add_argument("--grep", default=None, help="关键词（匹配 question/choice/why/alternatives/task/scope）")
    decision_parser.add_argument("--since", default=None, help="时间窗")
    decision_parser.add_argument("--limit", type=int, default=5, help="最多展示条数（默认 5）")
    decision_parser.add_argument("--doctor", action="store_true", help="校验决策索引（通道③完成判据：0 漏抽）")
    decision_parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")

    risk_parser = sub.add_parser("risk", help="R0/R1 风险动作清单（Phase 0 = git 可观测子集）")
    risk_parser.add_argument("--since", default="7d", help="时间窗（默认 7d）")
    risk_parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    risk_parser.add_argument("--full", action="store_true", help="展开全部")

    doctor_parser = sub.add_parser("doctor", help="数据源自查（缺失/坏 JSON/快照过旧 ⇒ FAIL）")
    doctor_parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    _setup_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    repo = Path(args.repo).resolve() if args.repo else REPO_ROOT
    if args.command == "task":
        return cmd_task(repo, args)
    if args.command == "member":
        return cmd_member(repo, args)
    if args.command == "decision":
        return cmd_decision(repo, args)
    if args.command == "risk":
        return cmd_risk(repo, args)
    if args.command == "doctor":
        return cmd_doctor(repo, args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
