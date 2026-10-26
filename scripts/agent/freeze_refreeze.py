#!/usr/bin/env python3
"""冻结物更新检查（freeze `--refreeze` 的【只读】部分；task-158）。

## 为什么有这个脚本
`artifacts/agent/verify/debate/freeze-v2.json` 是辩论裁决的冻结收据（`standards[].sha256_lf`）。
现行流程只能人工改 sha + 手工追加 `standards_updated[]` —— 见 steward 提案
`artifacts/agent/verify/steward/PROPOSAL-freeze-refreeze.md`（SF-20261026-036）。

**本脚本只实现 `--check`（零风险、只读）**：
  - 与 `team_audit.py` 的 dq5 **共用同一个 `content_sha256` 实现**（直接 import），
    避免"refreeze 说匹配、dq5 说漂移"的新假象；
  - 输出逐项 MATCH/DRIFT + 漂移清单 + **建议的 `standards_updated` 条目**（不写盘）；
  - 区分 `role` 含「机检/实现/tooling」的条目（dq5 对它们只 WARN）与决策标准（dq5 FAIL）。

`--apply`（append-only 写入 + freeze-history 备份 + baseline_mutation 结论）**未实现**：
按 L10/steward 提案，需先补条款 **L12（冻结物更新）** 再实现；在 L12 批准前本命令明确报错退出 4，
**不会**偷偷改冻结物（否则就是 A3 违规的"自动改收据"）。

退出码：
  --check: 0 = 全部 MATCH；1 = 有 DRIFT；2 = 用法/schema 错误
  --apply: 4 = 待 L12 批准后实现（明确失败，不是静默不做）
用法：
  python scripts/agent/freeze_refreeze.py --check [--freeze PATH] [--json]
  python scripts/agent/freeze_refreeze.py --apply      # 明确报"待 L12"
  python scripts/agent/freeze_refreeze.py --selftest
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEBATE_DIR_REL = "artifacts/agent/verify/debate"
DEFAULT_FREEZE_REL = f"{DEBATE_DIR_REL}/freeze-v2.json"
TOOLING_ROLE_HINTS = ("机检", "实现", "tooling")

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_USAGE = 2
EXIT_PENDING_L12 = 4

TOOL_VERSION = "1.0.0"


def _team_audit():
    """取 team_audit 的 content_sha256（与 dq5 共用口径：不改写、不复制实现）。"""
    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    import team_audit  # noqa: PLC0415 —— 延迟 import，避免脚本自身被 team_audit 反向依赖

    return team_audit


def _is_tooling(role: str) -> bool:
    return any(hint in role for hint in TOOLING_ROLE_HINTS)


def load_freeze(path: Path) -> tuple[dict | None, str | None]:
    if not path.is_file():
        return None, f"freeze 文件不存在：{path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"freeze 文件无法解析：{exc}"
    if not isinstance(data, dict):
        return None, "freeze 顶层不是 JSON 对象"
    standards = data.get("standards")
    if not isinstance(standards, list) or not standards:
        return None, "freeze.standards 缺失或为空（无法核对任何冻结标准）"
    return data, None


def check_freeze(repo: Path, freeze_path: Path) -> tuple[int, dict]:
    """只读核对；返回 (exit_code, report)。"""
    content_sha256 = _team_audit().content_sha256
    data, error = load_freeze(freeze_path)
    report: dict = {
        "schema": "freeze-refreeze-check/v1",
        "tool": f"freeze_refreeze.py@{TOOL_VERSION}",
        "freeze": str(freeze_path),
        "sha_impl": "team_audit.content_sha256（LF 归一化，与 dq5 共用）",
        "standards": [],
        "changed": [],
    }
    if data is None:
        report["error"] = error
        return EXIT_USAGE, report
    matched = drifted_decision = drifted_tooling = 0
    for item in data.get("standards") or []:
        if not isinstance(item, dict):
            report["error"] = "freeze.standards 项不是对象"
            return EXIT_USAGE, report
        path_rel = str(item.get("path") or "")
        recorded = str(item.get("sha256_lf") or item.get("sha256") or "")
        role = str(item.get("role") or "")
        row = {"path": path_rel, "role": role, "recorded": recorded}
        target = repo / path_rel
        if not path_rel or not recorded:
            row["status"] = "INVALID"
            report["standards"].append(row)
            report["error"] = f"标准条目缺 path/sha：{item!r}"
            return EXIT_USAGE, report
        if not target.is_file():
            row["status"] = "MISSING"
            report["standards"].append(row)
            report["changed"].append({"path": path_rel, "from": recorded, "to": None, "role": role})
            drifted_decision += 1
            continue
        current = content_sha256(target)
        row["current"] = current
        if current == recorded:
            row["status"] = "MATCH"
            matched += 1
        else:
            tooling = _is_tooling(role)
            row["status"] = "DRIFT"
            row["tooling"] = tooling
            report["standards"].append(row)
            report["changed"].append(
                {"path": path_rel, "from": recorded, "to": current, "role": role, "tooling": tooling}
            )
            if tooling:
                drifted_tooling += 1
            else:
                drifted_decision += 1
            continue
        report["standards"].append(row)
    report["summary"] = {
        "standards": len(report["standards"]),
        "matched": matched,
        "drift": drifted_decision + drifted_tooling,
        "drift_decision": drifted_decision,
        "drift_tooling": drifted_tooling,
        "status": "drift" if (drifted_decision or drifted_tooling) else "match",
    }
    if report["changed"]:
        report["suggested_standards_updated"] = {
            "at": "<UTC ISO8601>",
            "by": "<lead>",
            "reason": "<≥10 字：为什么冻结标准变了>",
            "rule_ref": "<可解析条款，如 docs/guides/agent-team-org.md#2.6>",
            "commit": "<sha 或省略>",
            "changed": report["changed"],
            "baseline_mutation": {"reopen": [], "declared_by": "lead", "why_not_reopen": "<结论>"},
            "tool": f"freeze_refreeze.py@{TOOL_VERSION}",
        }
        return EXIT_DRIFT, report
    return EXIT_OK, report


def _print_report(report: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print(f"freeze 检查：{report['freeze']}")
    print(f"sha 口径：{report['sha_impl']}\n")
    if report.get("error"):
        print(f"ERROR：{report['error']}", file=sys.stderr)
        return
    for row in report["standards"]:
        role = f"  [{row['role']}]" if row.get("role") else ""
        if row["status"] == "MATCH":
            print(f"MATCH   {row['path']}{role}")
        else:
            extra = "（tooling：dq5 只 WARN）" if row.get("tooling") else "（决策标准：dq5 FAIL）"
            print(f"DRIFT   {row['path']}{role}  ← 记录 @{row['recorded'][:12]}… 当前 @{str(row.get('current'))[:12]}… {extra}")
    summary = report["summary"]
    print(
        f"\n汇总：{summary['standards']} 项；MATCH={summary['matched']}，"
        f"DRIFT={summary['drift']}（决策标准 {summary['drift_decision']} / tooling {summary['drift_tooling']}）"
    )
    if summary["status"] == "match":
        print("结论：冻结标准与磁盘一致（dq5 应可通过）")
        return
    print("结论：存在漂移，需 refreeze（append-only 记录）——")
    print("  1) 先补条款 L12（冻结物更新）并获人批准；")
    print("  2) 批准后用 --apply 追加 standards_updated[]（本脚本当前未实现，见文件头注释）；")
    print("  3) refreeze 后受影响的 steward 审计收据必须重读重签（B3），并记 baseline_mutation 结论。")
    print("\n建议的 standards_updated 条目（仅打印，不写盘）：")
    print(json.dumps(report.get("suggested_standards_updated"), ensure_ascii=False, indent=2))


def _selftest() -> int:
    """自证 --check 会绿也会红（临时 fixture；不碰真实 freeze）。"""
    failures: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="freeze-refreeze-selftest-"))
    try:
        content_sha256 = _team_audit().content_sha256

        def _make_freeze(root: Path, role: str = "决策标准") -> tuple[Path, Path]:
            standard = root / "docs" / "STANDARD.md"
            standard.parent.mkdir(parents=True, exist_ok=True)
            standard.write_text("# standard\nbody\n", encoding="utf-8")
            freeze = root / "freeze-v2.json"
            freeze.write_text(
                json.dumps(
                    {
                        "schema": "debate-freeze/v2",
                        "question": "Q",
                        "acceptance_criteria": ["AC1"],
                        "standards": [
                            {"path": "docs/STANDARD.md", "role": role, "sha256_lf": content_sha256(standard)}
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return freeze, standard

        # 绿：MATCH ⇒ exit 0
        root = tmp / "green"
        freeze, _std = _make_freeze(root)
        code, report = check_freeze(root, freeze)
        if code == EXIT_OK and report["summary"]["matched"] == 1:
            print("  PASS freeze:MATCH ⇒ exit 0")
        else:
            failures.append("freeze 绿 fixture 未通过")
            print("  FAIL freeze:MATCH")

        # 红：标准内容变了 ⇒ DRIFT ⇒ exit 1
        root = tmp / "red"
        freeze, std = _make_freeze(root)
        std.write_text("# standard\nbody changed\n", encoding="utf-8")
        code, report = check_freeze(root, freeze)
        if code == EXIT_DRIFT and report["summary"]["drift_decision"] == 1 and report.get("suggested_standards_updated"):
            print("  PASS freeze:决策标准漂移 ⇒ exit 1 + 建议条目")
        else:
            failures.append("freeze 漂移 fixture 未红")
            print("  FAIL freeze:决策标准漂移")

        # 红（tooling 分类）：role 含「机检实现」⇒ 标记 tooling
        root = tmp / "red-tooling"
        freeze, std = _make_freeze(root, role="机检实现")
        std.write_text("# standard\nbody changed\n", encoding="utf-8")
        code, report = check_freeze(root, freeze)
        if code == EXIT_DRIFT and report["summary"]["drift_tooling"] == 1:
            print("  PASS freeze:tooling 漂移单独分类")
        else:
            failures.append("freeze tooling 分类失败")
            print("  FAIL freeze:tooling 漂移分类")

        # 红：freeze 损坏 ⇒ exit 2
        root = tmp / "bad"
        root.mkdir(parents=True, exist_ok=True)
        bad = root / "freeze-v2.json"
        bad.write_text("{not json", encoding="utf-8")
        code, _report = check_freeze(root, bad)
        if code == EXIT_USAGE:
            print("  PASS freeze:损坏 freeze ⇒ exit 2")
        else:
            failures.append("freeze 损坏 fixture 未 exit 2")
            print("  FAIL freeze:损坏 freeze")

        # --apply：明确 exit 4（待 L12），不是静默不做
        code = apply_pending()
        if code == EXIT_PENDING_L12:
            print("  PASS freeze:--apply 明确待 L12（exit 4）")
        else:
            failures.append("freeze --apply 未明确待 L12")
            print("  FAIL freeze:--apply")
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
    print()
    if failures:
        for item in failures:
            print(f"FAIL: {item}")
        return 1
    print("selftest: PASS（--check 会红也会绿；--apply 明确待 L12）")
    return 0


def apply_pending() -> int:
    print(
        "未实现：--apply（append-only 写 freeze + freeze-history 备份 + baseline_mutation）\n"
        "原因：按 L10/steward 提案，需先补条款 L12（冻结物更新）并获得人批准；\n"
        "      在 L12 批准前自动改冻结物 = “自动改收据”（A3 违规）。\n"
        "提案：artifacts/agent/verify/steward/PROPOSAL-freeze-refreeze.md §2.2。",
        file=sys.stderr,
    )
    return EXIT_PENDING_L12


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, AttributeError):
            pass
    parser = argparse.ArgumentParser(
        description="冻结物更新检查（freeze --refreeze 的只读部分；--apply 待 L12）",
        epilog=(
            "退出码：--check 0=MATCH / 1=DRIFT / 2=用法或 schema 错误；"
            "--apply 4=待 L12 批准后实现。"
        ),
    )
    parser.add_argument("--repo", default=str(ROOT), help="仓库根（默认脚本上两级）")
    parser.add_argument("--freeze", default=None, help=f"freeze 路径（默认 {DEFAULT_FREEZE_REL}）")
    parser.add_argument("--check", action="store_true", help="只读核对 standards 与磁盘（默认动作）")
    parser.add_argument("--apply", action="store_true", help="（未实现，等 L12）append-only 写 freeze")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--selftest", action="store_true", help="自证红/绿（临时 fixture）")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()
    if args.apply:
        return apply_pending()
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"用法错误：仓库目录不存在：{repo}", file=sys.stderr)
        return EXIT_USAGE
    freeze_path = Path(args.freeze) if args.freeze else repo / DEFAULT_FREEZE_REL
    if not freeze_path.is_absolute():
        freeze_path = repo / freeze_path
    code, report = check_freeze(repo, freeze_path)
    _print_report(report, args.json)
    return code


if __name__ == "__main__":
    sys.exit(main())
