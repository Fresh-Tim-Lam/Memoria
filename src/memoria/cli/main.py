"""Memoria 命令行工具（M3 P4）。"""

from __future__ import annotations

import argparse
import json
import sys

from memoria.services.document import DocumentService
from memoria.storage.path_cascade import reconcile_path_cascade


def _print_validate(report: dict, *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = report.get("status", "error")
        err = report.get("errors", 0)
        warn = report.get("warnings", 0)
        n = report.get("files_checked", 0)
        print(f"状态: {status}")
        print(f"已检查 {n} 个 Markdown 文件 · {err} 错误 · {warn} 警告")

        moves = report.get("path_moves") or []
        if moves:
            print(f"\n检测到 {len(moves)} 处路径变更（可运行 repair-paths --apply）：")
            for m in moves:
                print(f"  {m.get('from')} → {m.get('to')} ({m.get('kind', '')})")

        for block, title in (
            ("kb_integrity", "全库"),
            ("manifest_diff", "文件清单"),
        ):
            data = report.get(block) or {}
            for issue in (data.get("errors") or []) + (data.get("warnings") or []):
                sev = issue.get("severity", "warning")
                paths = issue.get("paths") or []
                path = paths[0] if paths else ""
                prefix = f"[{title}] " if title != "全库" else ""
                print(f"  [{sev}] {prefix}{issue.get('message', '')}" + (f" ({path})" if path else ""))

        for fr in report.get("files") or []:
            path = fr.get("path", "")
            for e in fr.get("errors") or []:
                print(f"  [error] {path}: {e}")
            for w in fr.get("warnings") or []:
                print(f"  [warning] {path}: {w}")

    if report.get("status") != "ok":
        return 1
    return 0


def _print_repair(result: dict, *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result.get("status") == "error":
            print(result.get("message", "失败"), file=sys.stderr)
            return 1
        moves = result.get("moves") or []
        if result.get("dry_run"):
            print(f"检测到 {len(moves)} 处路径变更（预览，未写入）：")
            for m in moves:
                print(f"  {m.get('from')} → {m.get('to')}")
            if moves:
                print("\n使用 repair-paths --apply 执行修复。")
        else:
            print(f"已应用 {result.get('applied_count', 0)}/{result.get('move_count', 0)} 处路径变更")
            for row in result.get("applied") or []:
                print(f"  ✓ {row.get('from')} → {row.get('to')}")
            for row in result.get("errors") or []:
                print(f"  ✗ {row.get('from')} → {row.get('to')}: {row.get('error')}", file=sys.stderr)
    if result.get("status") == "partial":
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(prog="memoria", description="Memoria 知识库 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="校验知识库完整性")
    p_val.add_argument("kb_path", help="知识库根目录")
    p_val.add_argument("--json", action="store_true", help="JSON 输出")

    p_rep = sub.add_parser("repair-paths", help="检测/修复文件移动导致的路径级联")
    p_rep.add_argument("kb_path", help="知识库根目录")
    p_rep.add_argument("--apply", action="store_true", help="写入修复（默认仅预览）")
    p_rep.add_argument("--json", action="store_true", help="JSON 输出")

    args = parser.parse_args(argv)

    if args.command == "validate":
        svc = DocumentService(kb_path=args.kb_path)
        report = svc.validate_kb()
        return _print_validate(report, as_json=args.json)

    if args.command == "repair-paths":
        result = reconcile_path_cascade(args.kb_path, apply=args.apply)
        return _print_repair(result, as_json=args.json)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
