#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""需求→证据矩阵检查（comp.requirement-verifier，task-269；只读）。

输入：
  --trace <json>     Requirements trace（rows: [{reqId, criterion, evidencePath?, declaredStatus?}]）
  --manifest <json>   可选：evidence manifest（{reqId: {evidencePath, declaredStatus}}），覆盖 trace 里的空值
输出：
  {ok, rows:[{reqId, criterion, evidencePath, status: pass|fail|unknown}], summary{...}}
规则：
  - evidencePath 缺失或文件不存在 ⇒ unknown（unknown 不算 pass）；
  - evidencePath 存在 ⇒ 用 declaredStatus（pass|fail|unknown），缺省 pass；
  - 全 unknown / 空输入 ⇒ exit 1；trace 文件不存在 ⇒ exit 2（不许空过）。
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATUSES = {"pass", "fail", "unknown"}


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _resolve(path_arg: str) -> Path:
    path = Path(path_arg)
    return path if path.is_absolute() else ROOT / path


def check(trace: dict, manifest: dict | None = None, repo: Path = ROOT) -> dict:
    rows_in = trace.get("rows") if isinstance(trace, dict) else None
    if not isinstance(rows_in, list):
        raise ValueError("trace.rows 必须是数组")
    if not rows_in:
        return {"ok": False, "rows": [], "summary": {"total": 0, "pass": 0, "fail": 0, "unknown": 0},
                "violations": [{"rule": "EMPTY_INPUT", "detail": "trace.rows 为空：空输入不得判过"}]}
    manifest = manifest or {}
    rows = []
    for index, row in enumerate(rows_in):
        if not isinstance(row, dict):
            rows.append({"reqId": f"row-{index}",
                         "criterion": "", "evidencePath": "", "status": "unknown",
                         "violations": ["BAD_ROW：不是对象"]})
            continue
        req_id = str(row.get("reqId") or "").strip()
        criterion = str(row.get("criterion") or "").strip()
        evidence_path = str(row.get("evidencePath") or "").strip()
        declared = row.get("declaredStatus")
        extra = manifest.get(req_id) if isinstance(manifest, dict) else None
        if not evidence_path and isinstance(extra, dict):
            evidence_path = str(extra.get("evidencePath") or "").strip()
        if declared is None and isinstance(extra, dict):
            declared = extra.get("declaredStatus")
        if not evidence_path:
            status = "unknown"
        else:
            target = (Path(evidence_path) if Path(evidence_path).is_absolute()
                      else repo / evidence_path.replace("\\", "/"))
            if not target.is_file():
                status = "unknown"
            else:
                status = declared if declared in STATUSES else "pass"
        rows.append({"reqId": req_id, "criterion": criterion,
                     "evidencePath": evidence_path, "status": status})
    summary = {"total": len(rows), "pass": 0, "fail": 0, "unknown": 0}
    for row in rows:
        summary[row["status"]] += 1
    all_unknown = summary["unknown"] == summary["total"]
    violations = []
    if all_unknown:
        violations.append({"rule": "ALL_UNKNOWN",
                           "detail": "全部条目 unknown（unknown 不算 pass，需补证据）"})
    return {"ok": not violations, "rows": rows, "summary": summary, "violations": violations}


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def selftest() -> int:
    failures: list[str] = []
    with __import__("tempfile").TemporaryDirectory(prefix="req-matrix-selftest-") as tmp_s:
        tmp = Path(tmp_s)
        # 证据文件
        good = tmp / "evidence/pass.json"
        good.parent.mkdir(parents=True, exist_ok=True)
        good.write_text('{"ok": true}', encoding="utf-8")
        red = tmp / "evidence/fail-red.json"
        red.write_text('{"ok": false}', encoding="utf-8")
        trace = {"rows": [
            {"reqId": "R-09-a", "criterion": "crit-a", "evidencePath": str(good), "declaredStatus": "pass"},
            {"reqId": "R-09-b", "criterion": "crit-b", "evidencePath": str(red), "declaredStatus": "fail"},
            {"reqId": "R-09-c", "criterion": "crit-c", "evidencePath": str(tmp / "evidence/missing.json")},
        ]}
        result = check(trace, repo=ROOT)
        if not result["ok"]:
            failures.append("绿 fixture 应 ok=true")
        statuses = {r["reqId"]: r["status"] for r in result["rows"]}
        if statuses != {"R-09-a": "pass", "R-09-b": "fail", "R-09-c": "unknown"}:
            failures.append(f"status 映射错误：{statuses}")
        if result["summary"]["unknown"] != 1:
            failures.append("summary.unknown 应为 1")

        # 全 unknown ⇒ exit 1
        all_unknown = {"rows": [
            {"reqId": "U-1", "criterion": "x", "evidencePath": str(tmp / "evidence/no1.json")},
            {"reqId": "U-2", "criterion": "y", "evidencePath": ""},
        ]}
        result_unknown = check(all_unknown, repo=ROOT)
        if result_unknown["ok"] or not any(v["rule"] == "ALL_UNKNOWN" for v in result_unknown["violations"]):
            failures.append("全 unknown 应 ok=false + ALL_UNKNOWN")
        # 空输入
        result_empty = check({"rows": []}, repo=ROOT)
        if result_empty["ok"]:
            failures.append("空输入应 ok=false（EMPTY_INPUT）")
        # manifest 补证据路径
        trace_manifest = {"rows": [{"reqId": "M-1", "criterion": "c"}]}
        manifest = {"M-1": {"evidencePath": str(good), "declaredStatus": "pass"}}
        result_manifest = check(trace_manifest, manifest, repo=ROOT)
        if result_manifest["rows"][0]["status"] != "pass":
            failures.append("manifest 补充 evidencePath 后应 pass")

    if failures:
        print("SELFTEST FAIL")
        for item in failures:
            print(" -", item)
        return 1
    print("SELFTEST PASS：3 行矩阵 pass/fail/unknown 映射正确（fail 行带红证且判 fail）；"
          "缺证据文件 ⇒ unknown；全 unknown ⇒ exit 1（ALL_UNKNOWN）；空输入 ⇒ EMPTY_INPUT；manifest 可补 evidencePath。")
    return 0


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="需求→证据矩阵检查（comp.requirement-verifier，只读）")
    parser.add_argument("--trace", help="requirements trace JSON（rows: reqId/criterion/evidencePath/declaredStatus）")
    parser.add_argument("--manifest", help="evidence manifest JSON（可选）")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.trace:
        print(json.dumps({"ok": False, "error": "no-input", "detail": "需要 --trace（空输入不得判过）"},
                         ensure_ascii=False, indent=2))
        return 2
    try:
        trace = json.loads(_resolve(args.trace).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": "no-input-or-invalid", "detail": str(exc)},
                         ensure_ascii=False, indent=2))
        return 2
    manifest = None
    if args.manifest:
        try:
            manifest = json.loads(_resolve(args.manifest).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(json.dumps({"ok": False, "error": "no-input-or-invalid", "detail": str(exc)},
                             ensure_ascii=False, indent=2))
            return 2
    try:
        result = check(trace, manifest, ROOT)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": "no-input-or-invalid", "detail": str(exc)},
                         ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
