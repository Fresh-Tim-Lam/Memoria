#!/usr/bin/env python
"""W4 审批：**两级保护、等级不同**：必红 fixture（`contract_w4`）。

## 判别力
| 断言 | 构造的路径 | 期望 |
|---|---|---|
| `core_write_auto_rejected` | 核心写能力 + `approval=auto` | `ContractViolation(APPROVAL_REQUIRED)`（**运行时**，分发前） |
| `core_write_confirm_ok` | 核心写能力 + `approval=confirm` | 不抛（判别力：规则是条件性的，不是"一律拒"） |
| `plugin_write_auto_rejected_at_load` | 插件声明 `permissions.write` 非空 + `approval.write=auto` | **装载期** errors 命中该规则（`plugins.parse_declaration`） |
| `plugin_write_confirm_ok` | 同上但 `approval.write=confirm` | 不出现该 error（判别力） |

## 等级差异（R-S2-10，必须写进契约文档 §3.4）
插件侧 = **装载期硬拒**（装不进来）；核心写 = **运行时策略判定**（每次调用前问）。**不是同一等级。**
并且**不把** `replace_lines` / `insert_lines` / `replace_section` 加进 `RISKY_OPS`
（那会让 agent 每改一行都停下问人 ⇒ 功能不可用，R-S1A-2 同款裁决）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))
os.environ.setdefault("MEMORIA_CONFIG_DIR", tempfile.mkdtemp(prefix="memoria-cfg-"))

from memoria.services.agent import approvals, plugins  # noqa: E402

RESULTS: list[dict] = []


def check(name: str, ok: bool, detail: str, falsifier: str = "") -> None:
    RESULTS.append({"name": name, "ok": bool(ok), "detail": detail, "falsifier": falsifier})


def _plugin_raw(write_approval: str) -> dict:
    return {
        "v": 1,
        "id": "unit-test-plugin",
        "name": "单测插件",
        "permissions": {"read": ["**"], "write": ["notes/**"]},
        "approval": {"read": "auto", "write": write_approval},
        "provides": {"tools": []},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    # ── ① 核心写能力 + auto ⇒ 分发前拒 ──
    raised = None
    try:
        approvals.WRITE_CAPABILITY.require_approval("auto")
    except approvals.ContractViolation as exc:
        raised = exc
    check(
        "W4 核心写能力 + approval=auto ⇒ APPROVAL_REQUIRED（运行时/分发前）",
        raised is not None and raised.code == approvals.CODE_APPROVAL_REQUIRED,
        f"raised={raised and raised.code}, capability={approvals.WRITE_CAPABILITY.name}, "
        f"permissions.write={list(approvals.WRITE_CAPABILITY.permissions_write)}",
        "auto 放过 ⇒ 核心写能力没有声明位，与插件的不对称仍在",
    )

    # ── ② confirm 不抛（判别力：不是一律拒）──
    ok = True
    try:
        approvals.WRITE_CAPABILITY.require_approval("confirm")
    except approvals.ContractViolation:
        ok = False
    check("W4 核心写能力 + approval=confirm ⇒ 放行（条件性规则）", ok, f"raised={not ok}")

    # ── ③ 插件声明 write 非空 + approval.write=auto ⇒ 装载期拒 ──
    # 注意：`parse_declaration()` 的返回顺序是 `(decl, warnings, errors)`（`plugins.py:305`），
    # 不是 (decl, errors, warnings) —— 搞反会把 warning 当 error 判，正是本轮反复抓的"看错事实源"。
    _decl, _warn, errors = plugins.parse_declaration(_plugin_raw("auto"), source="unit-test")
    hit = [e for e in errors if e.get("kind") == "approval_too_loose"]  # _issue() 的键是 kind
    check(
        "W4 插件 permissions.write 非空 + approval.write=auto ⇒ 装载期 errors",
        bool(hit),
        f"kinds={[e.get('kind') for e in errors]}, hit={[e.get('message') for e in hit][:1]}",
        "装载期放过 ⇒ 插件可以自行降档",
    )

    # ── ④ 同插件 confirm ⇒ 该 error 消失（判别力）──
    _decl2, _warn2, errors2 = plugins.parse_declaration(_plugin_raw("confirm"), source="unit-test")
    hit2 = [e for e in errors2 if e.get("kind") == "approval_too_loose"]
    check(
        "W4 同插件 approval.write=confirm ⇒ 不触发该规则（证明是条件判定）",
        not hit2,
        f"kinds={[e.get('kind') for e in errors2]}",
    )

    payload = {
        "schema": "contract-w4/v1",
        "levels": {
            "plugin": "装载期硬拒（plugins.parse_declaration）",
            "core_write": "运行时判定（approvals.WRITE_CAPABILITY.require_approval）",
        },
        "not_in_risky_ops": sorted(approvals.RISKY_OPS),
        "assertions": RESULTS,
        "passed": all(r["ok"] for r in RESULTS),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    payload["artifactSha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    for r in RESULTS:
        print(f"  [{'OK' if r['ok'] else 'FAIL'}] {r['name']}: {r['detail']}")
        if not r["ok"] and r["falsifier"]:
            print(f"        falsifier: {r['falsifier']}")
    print(f"\n== RESULT: {'PASS' if payload['passed'] else 'FAIL'} ==  (sha256 {payload['artifactSha256'][:16]}…)")

    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(REPO, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        print(f"wrote: {args.json}")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
