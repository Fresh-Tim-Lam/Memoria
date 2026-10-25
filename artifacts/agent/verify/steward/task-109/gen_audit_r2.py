#!/usr/bin/env python3
"""task-109：生成第二轮审计收据（r2）——重读标准（新 sha）+ 累积 findings + 本轮新增 finding。

append-only：不改首轮 audit-2026-10-24/；只新增 r2 目录 + 追加 team/steward/findings.jsonl。
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
AUDIT_DIR = repo / "team/steward/audit-2026-10-24-r2"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

cumulative = repo / "team/steward/findings.jsonl"
existing = [json.loads(line) for line in cumulative.read_text(encoding="utf-8").splitlines() if line.strip()]
existing_ids = {row["finding_id"] for row in existing}


def F(fid, severity, check, rule_ref, claim, evidence, disposition, task_id=None,
      mechanized_as=None, note=None, proposal_gap=None):
    assert fid not in existing_ids, f"重复 finding_id: {fid}"
    return {
        "finding_id": fid, "audit_ts": AUDIT_TS, "severity": severity, "check": check,
        "rule_ref": rule_ref, "claim": claim, "evidence": evidence, "task_id": task_id,
        "disposition": disposition, "mechanized_as": mechanized_as,
        "disposition_by": "steward2", "disposition_at": AUDIT_TS,
        "note": note, "proposal_gap": proposal_gap,
    }


new = [
    F("SF-20261024-017", "WARN", "audit_determinism", "docs/guides/lead-dispatch-rules.md#5.4",
      "§5.4「机检工具必须确定性」已落地：`team_audit.py --determinism` 连跑两次、归一化 generatedAt 后"
      "逐字节一致（本轮实测 PASS）",
      ["scripts/agent/team_audit.py --determinism", "rules §5.4", "run sha 126140b4d05ab25a…"],
      "mechanized", mechanized_as="team_audit.py --determinism（§5.4，CLI 模式而非 run_checks 检查类）"),
    F("SF-20261024-018", "WARN", "write_scope", "docs/guides/lead-dispatch-rules.md#1.2b",
      "§1.2b「写域到产物级」已落地：write_scope 分级后，共享产出根 vs 子路径降为 INFO；"
      "WARN 从 11 条降到 6 条（2 同文件 + 1 services 子树 + **3 条两个任务都直接声明同一个共享根**）",
      ["scripts/agent/team_audit.py::check_write_scopes", "rules §1.2b",
       "artifacts/agent/verify/steward/task-109/audit-after.txt"],
      "mechanized", mechanized_as="team_audit.py::write_scope（§1.2b 分级）"),
    F("SF-20261024-019", "WARN", "mode_policy", "docs/guides/lead-dispatch-rules.md#1.3b",
      "§1.3b「显式未决定」语义已落地：mode_policy 把 `modeExplicit=false` 单列 WARN，"
      "不再与「历史缺 mode」混为一谈（历史 14 条仍如实报不可判定）",
      ["scripts/agent/team_audit.py::check_mode_policy", "rules §1.3b",
       "scripts/agent/dispatch_log.py --mode-explicit"],
      "mechanized", mechanized_as="team_audit.py::mode_policy（§1.3b 显式未决定分离）"),
    F("SF-20261024-020", "WARN", "dead_path_edit", "docs/guides/agent-team-lessons.md#L0.3",
      "SF-002 处置完成：12 个无入口探针已归档到 `scripts/benchmark/archive/`（commit f5c3fcbb）；"
      "历史报告引用旧路径产生的 artifact_refs WARN 属历史不可逆（append-only 产物），不需修复",
      ["git:f5c3fcbb", "scripts/benchmark/archive/", "artifacts/agent/verify/steward/task-100/dead-paths-full.txt"],
      "fixed", note="归档决策已由 Lead 记入 decisions.jsonl（dec-20261024-d7a3e0eb）"),
    F("SF-20261024-021", "WARN", "proposal", "docs/guides/lead-dispatch-rules.md#6",
      "SF-011 闭环：`lead-dispatch-rules.md` 重复 §6（机检对应表 + 决策义务）已修复"
      "（机检表改 §7、决策保持 §6），依据正是我提的 proposal",
      ["git:4bbd7685", "docs/guides/lead-dispatch-rules.md#7", "SF-20261024-011"],
      "fixed", note="proposal → 条款 → 修复 的完整闭环证据"),
    F("SF-20261024-022", "WARN", "decision_trail", "AGENTS.md#0.5 L10",
      "决策层 D2 通道首次真实使用：Lead 用 `decide.py` 记录 12 探针归档决策"
      "（dec-20261024-d7a3e0eb，A2 强制 reconstructed:true，evidence=commit:f5c3fcbb）",
      ["team/decisions.jsonl:dec-20261024-d7a3e0eb", "git:f5c3fcbb", "scripts/agent/decide.py check"],
      "fixed", note="证明 D1/D2 + A2 时效校验在真实决策上工作"),
    F("SF-20261024-023", "WARN", "steward_self_audit", "docs/guides/agent-team-org.md#2.6 B3",
      "「标准变更 ⇒ 收据过期 ⇒ 必须重读标准再审计」机制自证：r2 重读后 FAIL=3 转 INFO，"
      "全程未修改首轮收据（append-only）",
      ["team/steward/audit-2026-10-24-r2/standards_read.json",
       "team/steward/audit-2026-10-24/standards_read.json（未改动）"],
      "fixed", note="B3 收据机制按设计工作，不是靠改数据把红变绿"),
    F("SF-20261024-024", "WARN", "write_scope", "docs/guides/lead-dispatch-rules.md#1.2b",
      "3 条 WARN 是**两个任务都直接声明同一个共享产出根**（task-86/94/107 均以 "
      "`artifacts/agent/verify` 根作 writeScope）——按 §1.2b 应收到任务专属子目录或写明理由",
      ["team/team-board-snapshot.json:tasks[task-86,task-94,task-107].writeScopes",
       "scripts/agent/team_audit.py::write_scope"],
      "open", note="属 Lead 既有任务写域（task-86/94/107），建议下次建/改任务时收窄；本角色不改任务板"),
]

for finding in new:
    if finding["disposition"] != "proposal":
        assert finding["rule_ref"], f"缺 rule_ref: {finding['finding_id']}"
        ok, detail = decide.validate_rule_ref(repo, finding["rule_ref"])
        assert ok, f"{finding['finding_id']} rule_ref 不可解析: {detail}"

all_rows = existing + new
body = "\n".join(json.dumps(row, ensure_ascii=False) for row in all_rows) + "\n"
(AUDIT_DIR / "findings.jsonl").write_text(body, encoding="utf-8", newline="\n")
with cumulative.open("a", encoding="utf-8", newline="\n") as fh:
    for row in new:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")

standards = []
for path_rel, sections in (
    ("AGENTS.md", "§0.5"),
    ("docs/guides/lead-dispatch-rules.md", "全部（重点 §1.2b/§1.3b/§5.4/§6）"),
    ("docs/guides/agent-team-lessons.md", "全部（重点 L9.6/L9.7）"),
    ("scripts/agent/team_audit.py", "检查清单 + --determinism"),
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
    "round": "r2",
    "tool": "team_audit.py@" + hashlib.sha256(
        (repo / "scripts/agent/team_audit.py").read_bytes()).hexdigest()[:12],
    "standards": standards,
    "determinism": {
        "checked": True,
        "command": "python scripts/agent/team_audit.py --determinism",
        "result": "PASS（除 generatedAt 外逐字节一致）",
    },
    "not_read": [
        "docs/guides/agent-team-org.md#§13（本轮只读 §2.3/§2.6/§2.1，未逐条复核 §13 台账）",
        "src/**（产品代码质量/性能不在 steward 审计范围）",
        "session 正文（按设计不读，只作证据引用）",
    ],
}
(AUDIT_DIR / "standards_read.json").write_text(
    json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(f"r2 findings: {len(all_rows)}（累计 {len(existing)}+{len(new)}）")
for item in standards:
    print(item["path"], item["sha256"][:16])
print("determinism:", receipt["determinism"]["result"])
