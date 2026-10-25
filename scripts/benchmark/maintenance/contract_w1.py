#!/usr/bin/env python
"""W1 入口唯一 + 清关令牌 / R-S2-3 核心写能力声明：可测 fixture（`contract_w1`）。

## 每条都在"构造违规路径"，判别力来自"错误实现上会红"

| 断言 | 构造的路径 | 期望 |
|---|---|---|
| `human_path_unaffected` | 不带 `origin` 的计划直接 `apply_plan`（= 人类 UI `agent_plan_apply` 的形态） | **允许**（R-S2-5 的教训：安全措施不能弄坏确认卡主路径） |
| `agent_origin_without_token` | 声称 `origin=agent` 但不给令牌（模拟"绕过 propose_write 直接调 apply_plan"） | 拒 `WRITE_GATE_BYPASS`，且 **`snapshot_pre_images` 未被调用**（备份前就拒） |
| `agent_origin_with_token` | 走正门：读后 → 令牌 → `origin=agent` | 成功落盘 |
| `facade_unread_write` | `submit_write` 未读就写 | 拒 `FS_NOT_OBSERVED`（W2 在 facade 生效） |
| `facade_read_then_write` | 先 `read_document` 再 `submit_write` | 成功 + 回执粒度 `{txid, files, lines_changed, undo_available}` |
| `core_write_capability_auto` | `submit_write(approval="auto")`（R-S2-3：核心写能力） | 分发前抛 `APPROVAL_REQUIRED`（不是运行时才拒） |
| `txid_missing_rejected` | 计划缺 `txid`（R-S2-4 钉住防回退） | `INVALID_PLAN`（信封层已强制，不需改 40 处调用方） |

## 诚实边界（R-S2-6②）
令牌强度上限 = 「`gate_ops` 曾通过」，**不是**「agent 真的读过」：
`observation.record_read()` 是公开函数，恶意模块可伪造。W2 防的是**无意绕过**（漏调闸），
不是恶意模块；真正的强制边界在**进程边界**（S3 MCP）。

## 用法

    python scripts/benchmark/maintenance/contract_w1.py [--json out.json]
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

from memoria.services.agent import backup, observation  # noqa: E402
from memoria.services.agent import service_contract as sc  # noqa: E402
from memoria.services.agent.apply import apply_plan  # noqa: E402
from memoria.services.agent.tools.kb import build_kb_tools  # noqa: E402

RESULTS: list[dict] = []


def check(name: str, ok: bool, detail: str, falsifier: str = "") -> None:
    RESULTS.append({"name": name, "ok": bool(ok), "detail": detail, "falsifier": falsifier})


def _mk(kb: str, rel: str = "d.md") -> None:
    with open(os.path.join(kb, rel), "w", encoding="utf-8", newline="") as fh:
        fh.write("# 甲\n甲第一行\n\n## 小节\n小节正文\n")


def _plan(txid: str = "20261025T020000Z-01", *, origin: str | None = None) -> dict:
    plan = {
        "v": 1,
        "txid": txid,
        "intent": "契约测试：改一行",
        "ops": [
            {"op": "replace_lines", "op_id": "o1", "file": "d.md",
             "range": {"start": 5, "end": 5}, "text": "改后的正文", "expect": "小节正文"}
        ],
    }
    if origin:
        plan["origin"] = origin
    return plan


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()
    sid = "sess-w1"

    # ── ① 人类路径不受影响（必须先证：不能把确认卡主路径弄坏）──
    kb = tempfile.mkdtemp(prefix="memoria-w1-human-")
    _mk(kb)
    res = apply_plan(kb, _plan(), session_id="ui-plan", txid="20261025T020000Z-01")
    body = open(os.path.join(kb, "d.md"), encoding="utf-8").read()
    check(
        "W1 人类路径（无 origin）⇒ 允许且真落盘",
        res.get("status") == "ok" and "改后的正文" in body,
        f"status={res.get('status')}, code={res.get('code')}, 落盘={('改后的正文' in body)}",
        "拒了人类确认卡路径 ⇒ R-S2-5 的教训重演（安全措施弄坏主路径）",
    )

    # ── ② 声称 agent 却无令牌 ⇒ 拒，且**备份前**拒 ──
    kb2 = tempfile.mkdtemp(prefix="memoria-w1-bypass-")
    _mk(kb2)
    calls: list[int] = []
    orig_snapshot = backup.snapshot_pre_images

    def _spy(*a, **k):
        calls.append(1)
        return orig_snapshot(*a, **k)

    backup.snapshot_pre_images = _spy  # type: ignore[assignment]
    try:
        res = apply_plan(kb2, _plan(origin="agent"), session_id=sid, txid="20261025T020000Z-01")
    finally:
        backup.snapshot_pre_images = orig_snapshot  # type: ignore[assignment]
    body2 = open(os.path.join(kb2, "d.md"), encoding="utf-8").read()
    check(
        "W1 agent 声称绕过（origin=agent 无令牌）⇒ WRITE_GATE_BYPASS 且备份前拒",
        res.get("status") == "error"
        and res.get("code") == observation.CODE_GATE_BYPASS
        and calls == []
        and "改后的正文" not in body2,
        f"status={res.get('status')}, code={res.get('code')}, snapshot_calls={len(calls)}, 落盘={('改后的正文' in body2)}",
        "放行 或 已建备份 或 已落盘 ⇒ W1 令牌形同虚设",
    )

    # ── ③ 正门：读后 → 令牌 → origin=agent ⇒ 成功 ──
    kb3 = tempfile.mkdtemp(prefix="memoria-w1-main-")
    _mk(kb3)
    tools = {t.name: t for t in build_kb_tools(kb3, session_id=sid)}
    tools["read_document"].handler({"path": "d.md"})
    token = observation.issue_clearance(kb3, sid, _plan()["ops"])
    res = apply_plan(
        kb3, _plan(origin="agent"), session_id=sid, txid="20261025T020000Z-01", gate_token=token
    )
    body3 = open(os.path.join(kb3, "d.md"), encoding="utf-8").read()
    check(
        "W1 正门（读后 + 有效令牌）⇒ 成功落盘",
        res.get("status") == "ok" and "改后的正文" in body3,
        f"status={res.get('status')}, code={res.get('code')}, token={bool(token)}",
    )
    # 令牌单次使用：同一令牌再用一次必须失效
    res2 = apply_plan(
        kb3, _plan(txid="20261025T020001Z-02", origin="agent"), session_id=sid,
        txid="20261025T020001Z-02", gate_token=token,
    )
    check(
        "W1 令牌一次性（重放同令牌 ⇒ 拒）",
        res2.get("status") == "error" and res2.get("code") == observation.CODE_GATE_BYPASS,
        f"status={res2.get('status')}, code={res2.get('code')}",
        "重放仍成功 ⇒ 令牌不是一次性",
    )

    # ── ④ facade：未读就写 ⇒ FS_NOT_OBSERVED ──
    kb4 = tempfile.mkdtemp(prefix="memoria-w1-facade-")
    _mk(kb4)
    out = sc.submit_write(kb4, _plan(), session_id="sess-fresh", approval="confirm")
    check(
        "W1 facade 未读就写 ⇒ FS_NOT_OBSERVED",
        out.get("status") == "error" and out.get("code") == observation.CODE_NOT_OBSERVED,
        f"status={out.get('status')}, code={out.get('code')}",
        "facade 放行未读写入 ⇒ W2 被 facade 绕过",
    )

    # ── ⑤ facade：先读后写 ⇒ 成功 + 回执粒度 ──
    tools4 = {t.name: t for t in build_kb_tools(kb4, session_id="sess-fresh")}
    tools4["read_document"].handler({"path": "d.md"})
    out = sc.submit_write(kb4, _plan(), session_id="sess-fresh", approval="confirm")
    check(
        "W1 facade 先读后写 ⇒ 成功 + 回执粒度 {txid,files,lines_changed,undo_available}",
        out.get("status") == "ok"
        and bool(out.get("txid"))
        and out.get("files") == ["d.md"]
        and out.get("undo_available") is True
        and "text" not in out,
        f"receipt={out}",
        "回执带全文 diff 或字段缺失 ⇒ 违背 S1b 的粒度契约",
    )

    # ── ⑥ R-S2-3：核心写能力 approval=auto ⇒ 分发前拒 ──
    raised = None
    try:
        sc.submit_write(kb4, _plan(txid="20261025T020002Z-03"), session_id="sess-fresh", approval="auto")
    except sc.ContractViolation as exc:
        raised = exc
    check(
        "W1(R-S2-3) 核心写能力 approval=auto ⇒ APPROVAL_REQUIRED（分发前）",
        raised is not None and raised.code == sc.CODE_APPROVAL_REQUIRED,
        f"raised={raised and raised.code}",
        "auto 放过 ⇒ 核心写能力没有声明位，与插件的不对称仍在",
    )

    # ── ⑦ R-S2-4 钉住：缺 txid ⇒ 计划层拒（不改 40 处调用方）──
    no_txid = _plan()
    no_txid.pop("txid")
    out = sc.submit_write(kb4, no_txid, session_id="sess-fresh", approval="confirm")
    check(
        "W1(R-S2-4) 计划缺 txid ⇒ INVALID_PLAN（信封层强制，防回退）",
        out.get("status") == "error" and out.get("code") == sc.CODE_INVALID_PLAN,
        f"status={out.get('status')}, code={out.get('code')}",
        "缺 txid 仍写入 ⇒ 审计/撤销键失锚",
    )

    payload = {
        "schema": "contract-w1/v1",
        "w1": "唯一写入口 + origin=agent 的一次性清关令牌；apply_plan 在备份前校验",
        "r_s2_3": "核心写能力声明位：permissions.write 非空 ⇒ approval 不得 auto",
        "r_s2_4": "txid 已在信封层强制（plan.py:314-315），本 fixture 只钉住防回退",
        "honest_boundary": "令牌强度上限 = gate_ops 曾通过，不是 agent 真的读过；恶意模块拦截属进程边界（S3）",
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
        out_path = args.json if os.path.isabs(args.json) else os.path.join(REPO, args.json)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        print(f"wrote: {args.json}")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
