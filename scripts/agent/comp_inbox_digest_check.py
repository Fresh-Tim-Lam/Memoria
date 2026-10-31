#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TODO-INBOX 消化检查（comp.inbox-digester，task-267；只读）。

检查每个 `INBOX-*` 条目：
  - 是否有「消化回执」（`## 消化回执 · INBOX-<id>` 或含 id 的回执段）；
  - 5 项消化验收清单是否齐全（`- [x]/[ ]` 行）；
  - 回执里引用的 linkedFiles（反引号路径）是否存在。
缺回执 / 缺清单项 / 条目数为 0 ⇒ exit 1；文件不存在 ⇒ exit 2（不许"没输入=通过"）。

用法：
    python scripts/agent/comp_inbox_digest_check.py [--inbox <path>] [--json]
    python scripts/agent/comp_inbox_digest_check.py --selftest
输出：{ok, entries:[{id,state,receiptPresent,checklist:{item1:pass|fail|na,...},linkedFiles[]}]}
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INBOX = "artifacts/agent/plugin-design/TODO-INBOX.md"
ENTRY_RE = re.compile(r"^##\s+(INBOX-[A-Za-z0-9-]+)\b", re.M)
RECEIPT_RE = re.compile(r"^##+\s+消化回执\s*[·:：]\s*(INBOX-[A-Za-z0-9-]+)", re.M)
STATE_RE = re.compile(r"状态\s*[：:]\s*`?([^`\n]+)`?")
CHECK_RE = re.compile(r"^-\s+\[( |x|X)\]\s+(.+)$", re.M)
PATH_RE = re.compile(r"`((?:docs|artifacts|team|scripts)/[^`]+)`")


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _split_sections(text: str) -> list[tuple[str, str]]:
    """按 `## ` 二级标题切块；返回 [(heading, body)]。"""
    sections: list[tuple[str, str]] = []
    matches = list(re.finditer(r"^##\s+(.+)$", text, re.M))
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append((match.group(1).strip(), text[start:end]))
    return sections


def _checklist_from(receipt_body: str, entry_body: str) -> list[tuple[str, str]]:
    """优先回执 block 里的验收对照，其次条目 block 里的消化验收（5 项）。"""
    for body in (receipt_body, entry_body):
        if "验收对照" not in body and "消化验收" not in body:
            continue
        lines = [line for line in body.splitlines() if CHECK_RE.match(line.strip())]
        if lines:
            result = []
            for line in lines[:5]:
                match = CHECK_RE.match(line.strip())
                if not match:
                    continue
                mark = match.group(1).strip().lower()
                status = "pass" if mark == "x" else "fail"
                result.append((match.group(2).strip(), status))
            if result:
                return result
    return []


def check(text: str, repo: Path = ROOT) -> dict:
    sections = _split_sections(text)
    receipts: dict[str, str] = {}
    entries: dict[str, dict] = {}
    for heading, body in sections:
        receipt_match = RECEIPT_RE.match("## " + heading)
        if receipt_match:
            entry_id = receipt_match.group(1)
            receipts[entry_id] = body
            continue
        entry_match = re.match(r"(INBOX-[A-Za-z0-9-]+)", heading)
        if entry_match:
            entries[entry_match.group(1)] = {"body": body}
    results: list[dict] = []
    violations: list[dict] = []
    for entry_id, info in entries.items():
        body = info["body"]
        state_match = STATE_RE.search(body)
        state = state_match.group(1).strip() if state_match else "unknown"
        receipt_body = receipts.get(entry_id)
        receipt_present = receipt_body is not None
        checklist = _checklist_from(receipt_body or "", body)
        checklist_map = {f"item{i+1}": status for i, (_, status) in enumerate(checklist)}
        linked: list[str] = []
        if receipt_body:
            for match in PATH_RE.finditer(receipt_body):
                rel = match.group(1).strip()
                if rel not in linked and (repo / rel.replace("\\", "/")).exists():
                    linked.append(rel)
        if not receipt_present:
            violations.append({"id": entry_id, "rule": "MISSING_RECEIPT",
                               "detail": "无「消化回执」段"})
        if len(checklist) < 5:
            violations.append({"id": entry_id, "rule": "MISSING_CHECKLIST",
                               "detail": f"消化验收清单应有 5 项，实际 {len(checklist)}"})
        results.append({"id": entry_id, "state": state, "receiptPresent": receipt_present,
                        "checklist": checklist_map, "checklistCount": len(checklist),
                        "linkedFiles": linked})
    if not results:
        violations.append({"id": None, "rule": "EMPTY_INPUT",
                           "detail": "未找到任何 INBOX-* 条目（空输入不得判过）"})
    return {"ok": not violations, "entries": results, "violations": violations}


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _fixture(tmp: Path, name: str, text: str) -> Path:
    path = tmp / f"{name}.md"
    _write(path, text)
    return path


def selftest() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="inbox-digest-selftest-") as tmp_s:
        tmp = Path(tmp_s)

        good = """# INBOX
## INBOX-TEST-001 · 测试条目
- 状态：`digested`

### 消化验收
- [x] 项1
- [x] 项2
- [ ] 项3
- [x] 项4
- [x] 项5

## 消化回执 · INBOX-TEST-001
- **状态**：`digested`
### 验收对照
- [x] 项1
- [x] 项2
- [ ] 项3
- [x] 项4
- [x] 项5
"""
        result = check(good, tmp)
        if not result["ok"] or len(result["entries"]) != 1:
            failures.append("绿 fixture 应 ok=true 且 1 条目")
        entry = result["entries"][0]
        if entry["checklistCount"] != 5 or entry["checklist"].get("item3") != "fail":
            failures.append(f"绿 fixture 清单应有 5 项且 item3=fail，实际 {entry['checklist']}")
        if not entry["receiptPresent"]:
            failures.append("绿 fixture receiptPresent 应为 true")

        # 红：raw 条目无回执
        raw = "# INBOX\n## INBOX-TEST-002 · 未消化\n- 状态：`raw`\n\n### 消化验收\n- [ ] 项1\n- [ ] 项2\n- [ ] 项3\n- [ ] 项4\n- [ ] 项5\n"
        result_raw = check(raw, tmp)
        if result_raw["ok"] or not any(v["id"] == "INBOX-TEST-002" for v in result_raw["violations"]):
            failures.append("raw 无回执应 ok=false 且该 id 出现在 violations（先证红）")

        # 红：回执清单只有 4 项
        short = """# INBOX
## INBOX-TEST-003 · 条目
- 状态：`digested`

## 消化回执 · INBOX-TEST-003
### 验收对照
- [x] 项1
- [x] 项2
- [x] 项3
- [x] 项4
"""
        result_short = check(short, tmp)
        if result_short["ok"] or not any(v["rule"] == "MISSING_CHECKLIST" for v in result_short["violations"]):
            failures.append("回执缺第 5 项应 ok=false + MISSING_CHECKLIST")

        # 红：空输入
        empty = check("# INBOX\n\n没有任何条目\n", tmp)
        if empty["ok"]:
            failures.append("空输入应 ok=false（EMPTY_INPUT）")

    if failures:
        print("SELFTEST FAIL")
        for item in failures:
            print(" -", item)
        return 1
    print("SELFTEST PASS：绿 fixture（回执+5 项，含 fail 状态）ok=true；raw 无回执 ⇒ ok=false 且 id 命中；"
          "回执缺第 5 项 ⇒ MISSING_CHECKLIST；空输入 ⇒ EMPTY_INPUT（不空过）。")
    return 0


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="TODO-INBOX 消化检查（comp.inbox-digester，只读）")
    parser.add_argument("--inbox", default=DEFAULT_INBOX)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    path = Path(args.inbox)
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        print(json.dumps({"ok": False, "error": "no-input-or-invalid",
                          "detail": f"TODO-INBOX 文件不存在：{path}"}, ensure_ascii=False, indent=2))
        return 2
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        print(json.dumps({"ok": False, "error": "no-input-or-invalid", "detail": str(exc)},
                         ensure_ascii=False, indent=2))
        return 2
    result = check(text, ROOT)
    result["inboxPath"] = str(path.relative_to(ROOT)).replace("\\", "/") if path.is_relative_to(ROOT) else str(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
