#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务定性检查（comp.task-classifier，task-262）。

规则源：`artifacts/agent/plugin-design/META-PROTOCOL-v0.1.md §2/§5`（分类映射 + 判定优先级）。
只读检查：读取任务板快照，校验任务 description 首行是否含 `定性: cls.<x>`、分类是否合法；
**不改 team_preflight、不做工具级强制**（M-3 另裁）。

用法：
    python scripts/agent/comp_task_classifier.py --board team/team-board-snapshot.json
    python scripts/agent/comp_task_classifier.py --classify "请发版 v0.4.8 并打包资产"
    python scripts/agent/comp_task_classifier.py --selftest

输出（stdout JSON）：
    {"ok": bool, "checked_count": int,
     "summary": {"classified": int, "missing": int, "illegal": int},
     "rows": [{"taskId", "hasClassification", "classification", "flowValid", "violations": []}]}
退出码：0=全过；1=有缺失/非法/空输入；2=无输入/用法错误。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

def _configure_utf8_stdio() -> None:
    """管道/重定向下 stdout 可能是 cp1252 等非 UTF-8 编码：统一转 UTF-8，避免全角字符 traceback。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _utf8_stdio_probe() -> bool:
    """selftest 内部断言：对自身输出做 UTF-8 写入不抛异常（防回归）。"""
    try:
        sys.stdout.write("UTF-8 探针：✓\n")
        sys.stdout.flush()
    except (UnicodeEncodeError, UnicodeDecodeError):
        return False
    return (sys.stdout.encoding or "").lower().replace("-", "") == "utf8"


_configure_utf8_stdio()

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BOARD = "team/team-board-snapshot.json"
RULE_SOURCE = "artifacts/agent/plugin-design/META-PROTOCOL-v0.1.md §2/§5"

CLASSES = {"cls.defect-fix", "cls.release", "cls.team-work-design",
           "cls.infra-change", "cls.research-forensics"}

# §2 判定表 + §5 伪代码（优先级：release > infra-change > defect-fix > team-work-design > research-forensics）
RULE_TABLE = (
    ("cls.release", ("发版", "发布", "tag", "打包", "上线", "release", "版本号", "资产")),
    ("cls.infra-change", ("跨仓", "跨域", "依赖", "ci", "构建", "插件契约", "目录结构",
                          "重构基础设施", "脚本", "目录")),
    ("cls.defect-fix", ("bug", "异常", "回归", "坏了", "修复", "不通过")),
    ("cls.team-work-design", ("开团队", "研讨", "设计", "工作流", "组件", "落地", "方案")),
    ("cls.research-forensics", ("取证", "调研", "评估", "对比", "查清楚")),
)

CLASSIFICATION_RE = __import__("re").compile(r"^\s*定性\s*[:：]\s*(cls\.[a-z0-9-]+)\s*$")


def classify_text(raw: str, context: dict | None = None) -> str:
    """§5 伪代码：返回 cls.* 或 UNCLASSIFIED（空请求同样 UNCLASSIFIED，不是默认通过）。"""
    text = str(raw or "").strip().lower()
    context = context or {}
    if not text:
        return "UNCLASSIFIED"
    if context.get("has_version"):
        return "cls.release"
    for class_id, keywords in RULE_TABLE:
        if any(keyword.lower() in text for keyword in keywords):
            return class_id
    return "UNCLASSIFIED"


def _task_description(task: dict) -> str | None:
    for key in ("description", "desc", "details"):
        value = task.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _first_meaningful_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line
    return ""


def check_board(board: dict) -> dict:
    tasks = board.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("board.tasks 不是数组")
    rows = []
    summary = {"classified": 0, "missing": 0, "illegal": 0}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = task.get("id")
        violations: list[str] = []
        description = _task_description(task)
        classification = None
        if description is None:
            violations.append("MISSING_DESCRIPTION：任务无 description/desc 字段，无法机检定性地")
        else:
            first_line = _first_meaningful_line(description)
            match = CLASSIFICATION_RE.match(first_line)
            if not match:
                violations.append("MISSING_CLASSIFICATION：description 首行无 `定性: cls.<x>`")
            else:
                classification = match.group(1)
                if classification not in CLASSES:
                    violations.append(f"ILLEGAL_CLASSIFICATION：{classification} 不在五类内")
        has_classification = classification is not None
        flow_valid = has_classification and classification in CLASSES and not any(
            v.startswith("ILLEGAL_") for v in violations)
        if flow_valid and not violations:
            summary["classified"] += 1
        elif not has_classification:
            summary["missing"] += 1
        else:
            summary["illegal"] += 1
        rows.append({
            "taskId": task_id,
            "hasClassification": has_classification,
            "classification": classification,
            "flowValid": flow_valid,
            "violations": violations,
        })
    checked_count = len(rows)
    violations_count = sum(1 for row in rows if row["violations"])
    if checked_count == 0:
        # 空输入不得判过（防"没输入=通过"）
        summary["missing"] = 0
        return {"ok": False, "checked_count": 0, "summary": summary,
                "rows": [], "error": "EMPTY_INPUT：board.tasks 为空，空输入不得判过"}
    # Lead 2026-10-31 裁定：当前 board snapshot 早于 v0.1 元协议（任务对象无 description），
    # 此时 MISSING_DESCRIPTION 仅作 audit 提示、不判红；有 description 但缺 `定性:` 仍判红。
    violation_kinds = {v.split("：", 1)[0] for row in rows for v in row["violations"]}
    advisory_reason = None
    if violations_count and violation_kinds == {"MISSING_DESCRIPTION"}:
        advisory_reason = ("board snapshot 早于 v0.1 元协议（任务对象无 description 字段）⇒ "
                           "MISSING_DESCRIPTION 仅作 audit 提示，本轮不判红；board schema 升级另开票")
    result = {"ok": violations_count == 0 or advisory_reason is not None,
              "checked_count": checked_count, "summary": summary, "rows": rows,
              "violations_count": violations_count}
    if advisory_reason:
        result["advisory"] = True
        result["advisoryReason"] = advisory_reason
    return result


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def selftest() -> int:
    failures: list[str] = []
    if not _utf8_stdio_probe():
        failures.append("UTF-8 输出探针失败：管道下 stdout 不是 UTF-8（全角字符会 traceback）")

    # ① 5 条反例集（§2 每类 1 条）→ 分类映射 5/5
    cases = [
        ("请发版 v0.4.8 并打 tag、打包资产", "cls.release"),
        ("改 CI 构建脚本并跨仓同步插件契约、调整目录结构", "cls.infra-change"),
        ("修复回归：按钮坏了不通过", "cls.defect-fix"),
        ("开团队研讨组件化设计并落地工作流方案", "cls.team-work-design"),
        ("只做取证调研，对比两份评估并查清楚", "cls.research-forensics"),
    ]
    for text, expected in cases:
        actual = classify_text(text)
        if actual != expected:
            failures.append(f"映射错误：{text!r} → {actual}，期望 {expected}")
    if classify_text("请发版 v0.4.8 并修复 bug") != "cls.release":
        failures.append("优先级错误：release 应优先于 defect-fix")
    if classify_text("") != "UNCLASSIFIED":
        failures.append("空请求应 UNCLASSIFIED，不得默认通过")

    # ② 板级 fixture：5 类合法任务必绿；删掉某任务定性行必红且 taskId 命中
    with __import__("tempfile").TemporaryDirectory(prefix="task-classifier-selftest-") as tmp_s:
        tmp = Path(tmp_s)
        tasks = [
            {"id": f"t-{i}", "description": f"定性: {cls}\n正文"}
            for i, (_, cls) in enumerate(cases, 1)
        ]
        board = tmp / "board-ok.json"
        _write(board, json.dumps({"tasks": tasks}, ensure_ascii=False))
        result = check_board(json.loads(board.read_text(encoding="utf-8")))
        if not result["ok"] or result["checked_count"] != 5:
            failures.append(f"绿 fixture 应 ok=true/checked=5，实际 {result['ok']}/{result['checked_count']}")
        if result["summary"]["classified"] != 5:
            failures.append(f"绿 fixture classified 应为 5，实际 {result['summary']['classified']}")

        # 删掉 t-3 的定性行 ⇒ exit 1（ok=false）且 t-3 出现在 violations
        tasks_bad = json.loads(json.dumps(tasks, ensure_ascii=False))
        tasks_bad[2]["description"] = "正文（定性行被删）"
        board_bad = tmp / "board-missing.json"
        _write(board_bad, json.dumps({"tasks": tasks_bad}, ensure_ascii=False))
        result_bad = check_board(json.loads(board_bad.read_text(encoding="utf-8")))
        if result_bad["ok"]:
            failures.append("删掉定性行后应 ok=false（exit 1）")
        bad_rows = [row for row in result_bad["rows"] if row["violations"]]
        if not any(row["taskId"] == "t-3" for row in bad_rows):
            failures.append("删掉定性行后 t-3 应出现在 violations 行中")
        # 非法分类 ⇒ 违规
        tasks_illegal = json.loads(json.dumps(tasks, ensure_ascii=False))
        tasks_illegal[0]["description"] = "定性: cls.not-a-class\n正文"
        board_illegal = tmp / "board-illegal.json"
        _write(board_illegal, json.dumps({"tasks": tasks_illegal}, ensure_ascii=False))
        result_illegal = check_board(json.loads(board_illegal.read_text(encoding="utf-8")))
        if result_illegal["ok"]:
            failures.append("非法分类应 ok=false")
        # 空输入 ⇒ ok=false + EMPTY_INPUT
        result_empty = check_board({"tasks": []})
        if result_empty["ok"] or "EMPTY_INPUT" not in (result_empty.get("error") or ""):
            failures.append("空输入应 ok=false 且带 EMPTY_INPUT（不得空过）")
        # Lead 裁定：board 无 description（早于 v0.1）⇒ advisory（exit 0，不判红）
        result_advisory = check_board({"tasks": [{"id": "t-a"}, {"id": "t-b"}]})
        if not result_advisory["ok"] or result_advisory.get("advisory") is not True:
            failures.append("无 description 的 board 应 ok=true + advisory=true（audit-only，不判红）")
        if result_advisory["summary"]["missing"] != 2 or "board snapshot" not in (
                result_advisory.get("advisoryReason") or ""):
            failures.append("advisory 输出应含 summary.missing=2 与 advisoryReason 原因说明")

    if failures:
        print("SELFTEST FAIL")
        for item in failures:
            print(" -", item)
        return 1
    print("SELFTEST PASS：5 类反例映射 5/5（含优先级 release>defect-fix）；空请求 UNCLASSIFIED；"
          "板级绿 fixture 5/5 classified；删定性行 ⇒ ok=false 且对应 taskId 出现；非法分类必红；空输入 EMPTY_INPUT 不空过。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="任务定性检查（comp.task-classifier，只读）")
    parser.add_argument("--board", default=DEFAULT_BOARD, help="任务板快照 JSON")
    parser.add_argument("--classify", dest="raw_text", help="按 §5 伪代码对文本做定性（输出 JSON）")
    parser.add_argument("--json", action="store_true", help="输出 JSON（默认即 JSON）")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.raw_text is not None:
        print(json.dumps({"ok": True, "ruleSource": RULE_SOURCE,
                          "classification": classify_text(args.raw_text)}, ensure_ascii=False, indent=2))
        return 0
    board_path = Path(args.board)
    if not board_path.is_absolute():
        board_path = ROOT / board_path
    if not board_path.is_file():
        print(json.dumps({"ok": False, "error": "no-input-or-invalid",
                          "detail": f"board 不存在：{board_path}"}, ensure_ascii=False, indent=2))
        return 2
    try:
        board = json.loads(board_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(json.dumps({"ok": False, "error": "no-input-or-invalid", "detail": str(exc)},
                         ensure_ascii=False, indent=2))
        return 2
    try:
        result = check_board(board)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": "no-input-or-invalid", "detail": str(exc)},
                         ensure_ascii=False, indent=2))
        return 2
    if "error" in result:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
