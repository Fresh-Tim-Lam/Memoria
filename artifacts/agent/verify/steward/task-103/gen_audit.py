#!/usr/bin/env python3
"""生成 task-103 首轮审计收据（standards_read.json + findings.jsonl）。

只用一次：本轮审计启动脚本；产物进 team/steward/**（append-only 由后续人工/工具维护）。
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "scripts/agent")
import decide  # noqa: E402

repo = Path(".").resolve()
now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
AUDIT_TS = now
AUDIT_DIR = repo / "team/steward/audit-2026-10-24"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def F(fid, severity, check, rule_ref, claim, evidence, disposition, task_id=None,
      mechanized_as=None, note=None, proposal_gap=None):
    return {
        "finding_id": fid, "audit_ts": AUDIT_TS, "severity": severity, "check": check,
        "rule_ref": rule_ref, "claim": claim, "evidence": evidence, "task_id": task_id,
        "disposition": disposition, "mechanized_as": mechanized_as,
        "disposition_by": "steward2" if disposition != "open" else None,
        "disposition_at": AUDIT_TS if disposition != "open" else None,
        "note": note, "proposal_gap": proposal_gap,
    }


findings = [
    F("SF-20261024-001", "WARN", "plan_consulted", "AGENTS.md#0.5 L8",
      "版本 0.4.7 的实施提交 a68ab655（10-23 13:19）早于台账计划落盘（docs/todo.md 最早 10-23 22:52）",
      ["git:a68ab655", "docs/todo.md -S'0.4.7'", "python scripts/agent/team_audit.py"],
      "mechanized", task_id="task-100", mechanized_as="team_audit.py::plan_consulted"),
    F("SF-20261024-002", "WARN", "dead_path_edit", "docs/guides/agent-team-lessons.md#L0.3",
      "近 7 天 12 个 src/scripts 改动文件在全仓没有任何外部引用（均为 benchmark 一次性探针）",
      ["artifacts/agent/verify/steward/task-100/dead-paths-full.txt",
       "git grep -l -F <basename> HEAD"],
      "open", note="待 Lead/人三选一：加 @entry / 归档 / 删除"),
    F("SF-20261024-003", "WARN", "mode_policy", "AGENTS.md#0.5 L9",
      "dispatch-log 中 14 条 phase=spawn 记录全部缺 mode 字段，无法判定是否做过模式决策（不静默判绿）",
      ["team/dispatch-log.jsonl:phase=spawn", "python scripts/agent/team_audit.py"],
      "open", task_id="task-107", note="task-107：dispatch_log.py 增加 --mode"),
    F("SF-20261024-004", "WARN", "decision_trail", "docs/guides/lead-dispatch-rules.md#6.5",
      "近 14 天 39 个 T1/T3 触发提交中 37 个缺 Decision/Why trailer（条款 2026-10-24 落地，首两周宽限 WARN）",
      ["git:f3002190", "git:3cd7a13f", "git:4bbd7685", "python scripts/agent/team_audit.py"],
      "open", note="宽限至 2026-11-07；历史提交不回改（A3），新提交起必须带 trailer"),
    F("SF-20261024-005", "FIXED", "role_registration", "docs/guides/agent-team-org.md#2.3",
      "task-98 前：快照 exportedAt 早于 org.md 修改时间 ⇒ 快照不可能反映注册修改",
      ["team/team-board-snapshot.json:exportedAt", "docs/guides/agent-team-org.md"],
      "fixed", note="Lead 重导出快照（12:06:52Z）；现 role_registration = INFO，三方 9/9/9"),
    F("SF-20261024-006", "FIXED", "-", "AGENTS.md#0.5 L10",
      "G1：决策理由不可查询（近 3 天 210 提交中结构化 trailer = 0，理由只存在于会话）",
      ["scripts/agent/decide.py", "team/decisions.jsonl", "scripts/agent/work_record.py decision"],
      "fixed", note="D1 trailer 解析 + D2 decisions.jsonl 建库 + work_record decision 查询"),
    F("SF-20261024-007", "FIXED", "-", "docs/guides/agent-team-org.md#2.6 B1",
      "G2：任务档案缺半边（快照 tasks[] 只有 7 字段，无 description/evidence/时间戳）",
      ["scripts/agent/work_record.py", "team/team-board-snapshot.json:tasks[]"],
      "fixed", note="work_record task 已 join 补齐；快照缺 createdAt/updatedAt 属插件 R10（未落地）"),
    F("SF-20261024-008", "MECHANIZED", "-", "docs/guides/agent-team-org.md#2.3",
      "G3：快照时效没有审计前门禁（过期快照无人处置，会审计一个不存在的世界）",
      ["scripts/agent/work_record.py doctor", "team_audit.py::role_registration"],
      "mechanized", mechanized_as="work_record.py::doctor + team_audit.py::role_registration"),
    F("SF-20261024-009", "OPEN", "-", "docs/guides/agent-team-org.md#2.6 B2",
      "G4：动作层缺失（无 trajectory），过程风险只能靠 git/报告反查",
      ["team/trajectory/ 不存在", "task-95 pending"],
      "open", task_id="task-95"),
    F("SF-20261024-010", "MECHANIZED", "role_registration", "docs/guides/agent-team-org.md#2.3",
      "G5：新角色注册不是原子操作（本轮实测 agents/org/快照三处不同步，team_audit FAIL=3）",
      ["git:b1f6d56e", "team_audit.py::role_registration"],
      "mechanized", mechanized_as="team_audit.py::role_registration"),
    F("SF-20261024-011", "WARN", "-", None,
      "lead-dispatch-rules.md 存在两个 §6（机检对应表 + 决策记录义务），章节号重复",
      ["docs/guides/lead-dispatch-rules.md:174", "docs/guides/lead-dispatch-rules.md:194",
       "git:4bbd7685"],
      "proposal", note="Lead 已按 proposal 修复（4bbd7685：机检对应表改 §7，决策保持 §6）",
      proposal_gap="现行规范没有「章节号必须唯一」条款 ⇒ 只能建议新增，不能算违规"),
    F("SF-20261024-012", "WARN", "-", None,
      "A2 时效窗口的精确值（10 分钟）未写成条款，只存在于实现常量",
      ["scripts/agent/decide.py:RECONSTRUCTED_THRESHOLD_SECONDS",
       "docs/guides/lead-dispatch-rules.md#6.7"],
      "proposal", note="Lead 裁决：窗口值保持实现常量（§6.7 已注明不写死），故不改条款",
      proposal_gap="条款只写「超窗 ⇒ 标 reconstructed」，未给具体分钟数"),
    F("SF-20261024-013", "FIXED", "-", "docs/guides/agent-team-org.md#2.6 B3",
      "steward 缺少 standards_read 收据机制（无法证明「重读标准而不是凭记忆」）",
      ["team/steward/audit-2026-10-24/standards_read.json", "team_audit.py::steward_self_audit"],
      "fixed", note="本轮首次产出四标准 sha256 收据；由 steward_self_audit 机检"),
]

for f in findings:
    if f["disposition"] != "proposal":
        assert f["rule_ref"], f"缺 rule_ref: {f['finding_id']}"
        ok, detail = decide.validate_rule_ref(repo, f["rule_ref"])
        assert ok, f"{f['finding_id']} rule_ref 不可解析: {detail}"
    elif f["rule_ref"]:
        ok, detail = decide.validate_rule_ref(repo, f["rule_ref"])
        assert ok, f"{f['finding_id']} rule_ref 不可解析: {detail}"

body = "\n".join(json.dumps(f, ensure_ascii=False) for f in findings) + "\n"
(repo / "team/steward").mkdir(parents=True, exist_ok=True)
(repo / "team/steward/findings.jsonl").write_text(body, encoding="utf-8", newline="\n")
(AUDIT_DIR / "findings.jsonl").write_text(body, encoding="utf-8", newline="\n")

standards = []
for path_rel, sections in (
    ("AGENTS.md", "§0.5"),
    ("docs/guides/lead-dispatch-rules.md", "全部"),
    ("docs/guides/agent-team-lessons.md", "全部"),
    ("scripts/agent/team_audit.py", "检查清单"),
):
    p = repo / path_rel
    standards.append({
        "path": path_rel,
        "sections": sections,
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "read_at": AUDIT_TS,
    })

receipt = {
    "schema": "steward-standards-read/v1",
    "audit_ts": AUDIT_TS,
    "tool": "team_audit.py@" + hashlib.sha256(
        (repo / "scripts/agent/team_audit.py").read_bytes()).hexdigest()[:12],
    "standards": standards,
    "not_read": [
        "docs/guides/agent-team-org.md#§13（本轮只读 §2.3/§2.6/§2.1，未逐条复核 §13 台账）",
        "src/**（产品代码质量/性能不在 steward 审计范围）",
        "session 正文（42MB，按设计不读，只作证据引用）",
    ],
}
(AUDIT_DIR / "standards_read.json").write_text(
    json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print("wrote", len(findings), "findings")
for s in standards:
    print(s["path"], s["sha256"][:12])
