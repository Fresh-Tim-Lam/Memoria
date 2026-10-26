#!/usr/bin/env python3
"""追加 SF-054/055：B-danger-1 细化提案 + 工具层拦截草案（proposal）。"""
import json
from datetime import datetime, timezone
from pathlib import Path

p = Path("team/steward/findings.jsonl")
rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
ids = {row["finding_id"] for row in rows}
now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
items = [
    {
        "finding_id": "SF-20261026-054",
        "severity": "WARN", "check": "proposal", "rule_ref": None,
        "claim": "B-danger-1 v2 细化提案（Lead 已认 5 条问题）：给出可直接替换的条款正文——"
                 "共享/独占定义（默认共享；独占仅(a)无未提交改动+Lead 显式授予、(b)独立 worktree）、"
                 "禁止命令清单（checkout --/checkout ./restore/reset --hard|--merge/clean -f*/stash drop|clear/"
                 "apply -R/update-index --assume-unchanged|--skip-worktree/worktree remove --force）、"
                 "对照实验一律 worktree/%TEMP%、留证格式（worktree list 输出或文件 sha256 清单，落 artifacts/verify 或 dispatch-log phase=experiment）、"
                 "R1 例外流程（dispatch-log phase=risk + sha 快照 + 事后差集核对）、"
                 "以及**强制力诚实标注**（checkout -- 不写 reflog，工具拦截落地前属靠自觉，不得宣称已机检保护）。",
        "evidence": ["artifacts/agent/verify/steward/PROPOSAL-b-danger-1-refinement.md",
                     "docs/guides/lead-dispatch-rules.md:250-270"],
        "task_id": None, "disposition": "proposal", "mechanized_as": None,
        "disposition_by": "steward", "disposition_at": now,
        "note": "Lead 落盘后 rules sha 变 ⇒ 按 B3 通知我重签 r8。",
        "proposal_gap": "B-danger-1 v1 无共享/独占定义、无留证格式、无强制力说明；本提案给出可替换文本。",
    },
    {
        "finding_id": "SF-20261026-055",
        "severity": "WARN", "check": "proposal", "rule_ref": None,
        "claim": "共享工作区破坏性 git 命令的**工具层拦截方案草案**：拦截点=DSH shell 工具执行前静态解析（不改命令语义）、"
                 "判定=是否目标主工作树；危险清单与 B-danger-1 v2 对齐；deny 返回结构化错误+替代方案+append-only 审计；"
                 "不提供模型自批 flag。分两期：v1 shell 层 deny+审计（fixtures 1-6/9/10），"
                 "v2 工作区完整性哨兵（每次 shell 前后采集 git status + dirty 文件 sha256，检测'改动消失且无合法来源'）覆盖残余绕过。"
                 "明确残余风险：python/node subprocess、git alias 注入、其他执行通道；工具拦截不是物理不可绕过，只能防无意/让绕过留痕。",
        "evidence": ["artifacts/agent/verify/steward/PROPOSAL-workspace-destructive-guard.md"],
        "task_id": None, "disposition": "proposal", "mechanized_as": None,
        "disposition_by": "steward", "disposition_at": now,
        "note": "排期建议：P0 Lead 落条款 → P1 方案评审 → P2 v1(plugin-creator, 0.5–1d) → P3 v2 哨兵；SF-052 可并行。",
        "proposal_gap": "现行条款（L6/L10/B-danger-1）要求工具强制，但没有'拦截语义/证据/豁免'的实现规范；本草案补之。",
    },
]
added = 0
with p.open("a", encoding="utf-8", newline="\n") as fh:
    for item in items:
        if item["finding_id"] in ids:
            continue
        row = {"audit_ts": now, "evidence": [], "task_id": None, "mechanized_as": None,
               "disposition_by": "steward", "disposition_at": now, "note": None,
               "proposal_gap": None, **item}
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        added += 1
print(f"appended {added}; total rows: {len(rows) + added}")
