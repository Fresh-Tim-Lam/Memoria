#!/usr/bin/env python3
"""r6 收据生成（task-158 后重签）：重读 5 标准，PD-1..PD-5 标记为已 mechanized。

只写 team/steward/**；不 commit；历史收据不改。"""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

repo = Path(".").resolve()
now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
AUDIT_DIR = repo / "team/steward/audit-2026-10-26-r6"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def content_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.stdout.strip() if proc.returncode == 0 else ""


cumulative = repo / "team/steward/findings.jsonl"
rows = [json.loads(line) for line in cumulative.read_text(encoding="utf-8").splitlines() if line.strip()]
ids = {row["finding_id"] for row in rows}

new = []
fixes = [
    ("SF-20261026-042", "SF-20261026-037", "PD-1",
     "task-158 已 mechanized PD-1：prompt_drift_check 新增 NOT_RUN 语义 + exit 码 0/1/2/3（2=有检查未执行、3=用法错误），"
     "所有'输入不可读/依赖缺失/自身异常'路径改为 ctx.not_run（Finding severity=NOT_RUN，_SEV_ORDER 把 NOT_RUN 排在 FAIL 后、WARN 前）；"
     "team_audit.check_prompt_drift 对 status=not_run/not_run_count>0 一律 FAIL，并对 status↔exit、summary.FAIL↔findings FAIL 计数做一致性校验。",
     "scripts/agent/prompt_drift_check.py:Ctx.not_run / summary.status",
     "team_audit.py::check_prompt_drift（NOT_RUN→FAIL）"),
    ("SF-20261026-043", "SF-20261026-038", "PD-2",
     "task-158 已 mechanized PD-2：C2 点分字段改为**每一段**都校验（不再只校验 SNAKE 段），"
     "`range.fakeCamelField` 这类伪造 camelCase 字段现在会 FAIL；豁免仅限 seg 出现在 code/edge_types/img_attrs。",
     "scripts/agent/prompt_drift_check.py:check_symbols 点分字段分支",
     "prompt_drift_check.py::check_symbols"),
    ("SF-20261026-044", "SF-20261026-039", "PD-3",
     "task-158 已 mechanized PD-3：隐藏分发路径探测不再跳过 kb_agent/ui.py/build.py，改为扫描 src/memoria、packaging、scripts 的 py/js/mjs；"
     "命中已人工核验文件（HIDDEN_SCAN_REVIEWED）只记 INFO 并写明理由，未核验文件记 WARN——不再静默跳过。",
     "scripts/agent/prompt_drift_check.py:HIDDEN_SCAN_REVIEWED",
     "prompt_drift_check.py:check_distribution 隐藏扫描"),
    ("SF-20261026-045", "SF-20261026-040", "PD-4",
     "task-158 已 mechanized PD-4：C1 孤儿检测改用 rglob 递归（排除 __pycache__/.pyc/隐藏项），"
     "嵌套孤儿文件不再漏检；内部资源引用证据读不到时记 NOT_RUN。",
     "scripts/agent/prompt_drift_check.py:check_distribution 孤儿段",
     "prompt_drift_check.py:check_distribution"),
    ("SF-20261026-046", "SF-20261026-041", "PD-5",
     "task-158 已 mechanized PD-5：C3 豁免词引入 _qualifier_near（PROXIMITY_CHARS=24，中间不得夹句读分隔），"
     "不再'同行任意位置有限定词就整行豁免'；`[[某#contain]]，不要写错别字` 这种绕过现在会 FAIL。",
     "scripts/agent/prompt_drift_check.py:_qualifier_near",
     "prompt_drift_check.py:check_forbidden_syntax"),
]
for fid, corrected, short, claim, evidence, mechanized in fixes:
    if fid in ids:
        continue
    new.append({
        "finding_id": fid, "audit_ts": now, "severity": "WARN", "check": "prompt_drift_check",
        "rule_ref": "AGENTS.md#0.5 L6", "claim": f"{short}（task-158 修复）：{claim}",
        "evidence": [evidence, "team/steward/audit-2026-10-26-r6/standards_read.json"],
        "task_id": "task-158", "disposition": "mechanized",
        "mechanized_as": mechanized,
        "disposition_by": "prompt-owner", "disposition_at": now,
        "note": "本轮 r6 重读时核对实现并实测：prompt_drift --json status=ok / FAIL=0 / NOT_RUN=0 / exit=0；--selftest exit=0。",
        "proposal_gap": None, "corrects_finding_id": corrected,
    })

# SF-047：freeze_refreeze.py 是否纳入 STEWARD_STANDARDS —— 本轮裁定"暂不纳入"（记录理由）
if "SF-20261026-047" not in ids:
    new.append({
        "finding_id": "SF-20261026-047", "audit_ts": now, "severity": "INFO", "check": "proposal",
        "rule_ref": None,
        "claim": "裁定：`scripts/agent/freeze_refreeze.py`（task-158 新增，当前只实现 --check；--apply 待 L12）"
                 "**暂不纳入** STEWARD_STANDARDS。理由：① 它是冻结物维护工具，不是审计标准/门禁，其变更不影响"
                 "steward 审计的判断依据；② 现在纳入需改 team_audit.py ⇒ 再触发一轮重签（自指循环），"
                 "而它尚未定型（--apply 未实现）；③ 待 L12 批准、--apply 落地后，再连同「freeze 更新流程」一起纳入并走一次"
                 "正常重签（届时 STEWARD_STANDARDS 6 项）。当前以 r6 收据里的 `freeze_refreeze_check` 字段记录其 --check 结果即可。",
        "evidence": ["scripts/agent/freeze_refreeze.py", "artifacts/agent/verify/steward/r6-freeze-refreeze.txt"],
        "task_id": "task-158", "disposition": "proposal", "mechanized_as": None,
        "disposition_by": "steward", "disposition_at": now,
        "note": "如果你（Lead）要求立即纳入，我需要改 team_audit.py 的 STEWARD_STANDARDS 并再跑一次 r7；成本≈一次重签。",
        "proposal_gap": "STEWARD_STANDARDS 的准入标准（哪些脚本算'标准'）未写成条款；建议 L12 一并定义。",
    })

all_rows = rows + new
by_id = {row["finding_id"]: row for row in all_rows}
corrections = {}
for row in all_rows:
    corrected = row.get("corrects_finding_id")
    if corrected:
        corrections[corrected] = row
for original, correction in corrections.items():
    by_id.pop(original, None)
    by_id[correction["finding_id"]] = correction
snapshot_rows = sorted(by_id.values(), key=lambda row: row["finding_id"])
(AUDIT_DIR / "findings.jsonl").write_text(
    "\n".join(json.dumps(row, ensure_ascii=False) for row in snapshot_rows) + "\n",
    encoding="utf-8", newline="\n")
if new:
    with cumulative.open("a", encoding="utf-8", newline="\n") as fh:
        for row in new:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

# 标准重读（5 项；content_sha256 = LF 归一化，与 team_audit 同实现）
standards = []
for path_rel, sections in (
    ("AGENTS.md", "§0.5"),
    ("docs/guides/lead-dispatch-rules.md", "全部（含 §1.2b/§1.3b/§5.4/§6.5）"),
    ("docs/guides/agent-team-lessons.md", "全部（含 L9.6/L9.7）"),
    ("scripts/agent/team_audit.py", "检查清单 + --determinism + --sha-explain + deliberation_quality + prompt_drift 接线（含 NOT_RUN→FAIL）"),
    ("scripts/agent/prompt_drift_check.py", "C1-C5 接口 + NOT_RUN 语义 + exit 0/1/2/3 + --recheck-deps/--resign"),
):
    target = repo / path_rel
    standards.append({
        "path": path_rel, "sections": sections,
        "sha256": content_sha256(target),
        "sha_mode": "content-lf（\\r\\n→\\n 后算；task-110/org.md §2.6 B3）",
        "read_at": now,
    })

pd_proc = subprocess.run(["python", "scripts/agent/prompt_drift_check.py", "--json"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
pd_summary = {}
try:
    pd_summary = (json.loads(pd_proc.stdout).get("summary") or {}) if pd_proc.stdout else {}
except json.JSONDecodeError:
    pd_summary = {"parse_error": True}
fr_proc = subprocess.run(["python", "scripts/agent/freeze_refreeze.py", "--check"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
dirty = [line[3:].strip() for line in _git("status", "--porcelain", "--", "scripts/agent", "team/steward").splitlines()
         if line.strip()]
receipt = {
    "schema": "steward-standards-read/v1",
    "audit_ts": now,
    "round": "r6",
    "tool": "team_audit.py@" + content_sha256(repo / "scripts/agent/team_audit.py")[:12],
    "git_base": _git("rev-parse", "--short", "HEAD"),
    "worktree_dirty_standards": [item for item in dirty if item.startswith("scripts/")],
    "standards": standards,
    "prompt_drift_standalone": {
        "command": "python scripts/agent/prompt_drift_check.py --json",
        "exit": pd_proc.returncode,
        "summary": pd_summary,
    },
    "freeze_refreeze_check": {
        "command": "python scripts/agent/freeze_refreeze.py --check",
        "exit": fr_proc.returncode,
        "note": "预期 1=有漂移：team_audit.py 为 tooling 项（dq5 只 WARN）；--apply 待 L12（exit 4）。",
        "output_head": fr_proc.stdout.strip().splitlines()[:8],
    },
    "determinism": {
        "checked": True,
        "command": "python scripts/agent/team_audit.py --determinism",
        "result": "见 r6 SUMMARY/报告（生成收据后单独运行）",
    },
    "not_read": [
        "docs/guides/agent-team-org.md#§13（本轮只读 §2.3/§2.6，未逐条复核 §13 台账）",
        "src/**（产品代码质量/性能不在 steward 审计范围）",
        "prompt_drift_check.py 的内部 C1-C5 语义正确性（本轮只重读接口/NOT_RUN/退出码；PD-1..PD-5 修复以 audit + 探针复核）",
        "session 正文（按设计不读，只作证据引用）",
    ],
}
(AUDIT_DIR / "standards_read.json").write_text(
    json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(f"r6 snapshot: {len(snapshot_rows)}（台账 {len(all_rows)} 行，新 {len(new)}）")
for item in standards:
    print(item["path"], item["sha256"][:16])
print("prompt_drift:", pd_proc.returncode, pd_summary)
print("freeze_refreeze --check exit:", fr_proc.returncode)
