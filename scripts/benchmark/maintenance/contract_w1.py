#!/usr/bin/env python
"""W1 入口唯一 + `origin` 必填参数：必红 fixture（`contract_w1`）。

## 判别力：每条都构造违规路径，错误实现上会红

| 断言 | 构造的路径 | 期望 |
|---|---|---|
| `origin_omitted_type_error` | 完全不传 `origin` | **`TypeError`**（签名级 fail-closed；不是"默认成 human"） |
| `origin_empty_rejected` | `origin=""` | `WRITE_ORIGIN_REQUIRED` |
| `origin_unknown_rejected` | `origin="robot"` | `WRITE_ORIGIN_REQUIRED` |
| `human_path_no_token` | `origin="human"` 无令牌（= 确认卡点应用） | **允许**（R-S2-5：安全措施不得弄坏主路径） |
| `agent_without_token` | `origin="agent"` 无令牌（模拟绕过 propose_write） | `WRITE_GATE_BYPASS`，且 **`snapshot_pre_images` 未被调用**、文件未变 |
| `agent_with_token` | 读后 → `issue_clearance` → `origin="agent"` | 成功落盘 |
| `token_single_use` | 同一令牌再用一次 | `WRITE_GATE_BYPASS` |
| `txid_missing` | 计划缺 `txid` | 计划层拒（`missing_field`） |

## 诚实边界（R-S2-16，写进契约文档 §3.2）
`origin` 是**调用点自述**，不是可信身份：进程内无法区分"真正的人类 UI 调用"与"显式传 human 的恶意调用"。
W1 解决的是**漏传静默**，不解决**撒谎**；真正的强制边界在进程边界（S3 MCP）。
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

from memoria.services.agent import apply as apply_mod  # noqa: E402
from memoria.services.agent import backup, observation  # noqa: E402
from memoria.services.agent.apply import apply_plan  # noqa: E402
from memoria.services.agent.tools.kb import build_kb_tools  # noqa: E402

RESULTS: list[dict] = []


def check(name: str, ok: bool, detail: str, falsifier: str = "") -> None:
    RESULTS.append({"name": name, "ok": bool(ok), "detail": detail, "falsifier": falsifier})


def _mk(kb: str) -> None:
    with open(os.path.join(kb, "d.md"), "w", encoding="utf-8", newline="") as fh:
        fh.write("# 甲\n甲第一行\n\n## 小节\n小节正文\n")


def _plan(txid: str = "20261025T090000Z-01") -> dict:
    return {
        "v": 1,
        "txid": txid,
        "intent": "契约测试：改一行",
        "ops": [
            {"op": "replace_lines", "op_id": "o1", "file": "d.md",
             "range": {"start": 5, "end": 5}, "text": "改后的正文", "expect": "小节正文"}
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()
    sid = "sess-w1"

    # ── ① 漏传 origin ⇒ TypeError（签名级 fail-closed）──
    kb = tempfile.mkdtemp(prefix="memoria-w1-omit-")
    _mk(kb)
    raised = None
    try:
        apply_plan(kb, _plan(), session_id=sid)  # type: ignore[call-arg]
    except TypeError as exc:
        raised = exc
    check(
        "W1 漏传 origin ⇒ TypeError（不是默认成 human）",
        raised is not None and "origin" in str(raised),
        f"raised={raised}",
        "漏传被默认接受 ⇒ fail-open 仍在",
    )

    # ── ② 空 / 未知 origin ⇒ 拒 ──
    for bad in ("", "robot"):
        res = apply_plan(kb, _plan(), session_id=sid, origin=bad)
        check(
            f"W1 origin={bad!r} ⇒ WRITE_ORIGIN_REQUIRED",
            res.get("status") == "error" and res.get("code") == apply_mod.CODE_WRITE_ORIGIN_REQUIRED,
            f"status={res.get('status')}, code={res.get('code')}",
            "空/未知 origin 被接受 ⇒ 等于没声明",
        )

    # ── ③ 人类路径：无令牌也允许（R-S2-5：不得弄坏确认卡）──
    kb_human = tempfile.mkdtemp(prefix="memoria-w1-human-")
    _mk(kb_human)
    res = apply_plan(kb_human, _plan(), session_id="ui-plan", origin="human")
    body = open(os.path.join(kb_human, "d.md"), encoding="utf-8").read()
    check(
        "W1 人类路径（origin=human，无令牌）⇒ 允许且真落盘",
        res.get("status") == "ok" and "改后的正文" in body,
        f"status={res.get('status')}, code={res.get('code')}, 落盘={('改后的正文' in body)}",
        "拒了人类确认卡路径 ⇒ R-S2-5 教训重演",
    )

    # ── ④ agent 无令牌 ⇒ 拒，且**备份前**拒 ──
    kb_agent = tempfile.mkdtemp(prefix="memoria-w1-agent-")
    _mk(kb_agent)
    calls: list[int] = []
    orig = backup.snapshot_pre_images

    def _spy(*a, **k):
        calls.append(1)
        return orig(*a, **k)

    backup.snapshot_pre_images = _spy  # type: ignore[assignment]
    try:
        res = apply_plan(kb_agent, _plan(), session_id=sid, origin="agent")
    finally:
        backup.snapshot_pre_images = orig  # type: ignore[assignment]
    body_agent = open(os.path.join(kb_agent, "d.md"), encoding="utf-8").read()
    check(
        "W1 agent 无令牌 ⇒ WRITE_GATE_BYPASS，且备份未创建、未落盘",
        res.get("status") == "error"
        and res.get("code") == observation.CODE_GATE_BYPASS
        and calls == []
        and "改后的正文" not in body_agent,
        f"status={res.get('status')}, code={res.get('code')}, snapshot_calls={len(calls)}, "
        f"落盘={('改后的正文' in body_agent)}",
        "放行 / 已建备份 / 已落盘 ⇒ W1 形同虚设",
    )

    # ── ⑤ 正门：读后 + 令牌 ⇒ 成功；令牌一次性 ──
    kb_ok = tempfile.mkdtemp(prefix="memoria-w1-ok-")
    _mk(kb_ok)
    tools = {t.name: t for t in build_kb_tools(kb_ok, session_id=sid)}
    tools["read_document"].handler({"path": "d.md"})
    token = observation.issue_clearance(kb_ok, sid, _plan()["ops"])
    res = apply_plan(kb_ok, _plan(), session_id=sid, origin="agent", gate_token=token)
    body_ok = open(os.path.join(kb_ok, "d.md"), encoding="utf-8").read()
    check(
        "W1 正门（读后 + 有效令牌 + origin=agent）⇒ 成功落盘",
        res.get("status") == "ok" and "改后的正文" in body_ok,
        f"status={res.get('status')}, code={res.get('code')}, token={bool(token)}",
    )
    res2 = apply_plan(kb_ok, _plan("20261025T090001Z-02"), session_id=sid, origin="agent", gate_token=token)
    check(
        "W1 令牌一次性（重放同令牌 ⇒ WRITE_GATE_BYPASS）",
        res2.get("status") == "error" and res2.get("code") == observation.CODE_GATE_BYPASS,
        f"status={res2.get('status')}, code={res2.get('code')}",
        "重放成功 ⇒ 令牌不是一次性",
    )

    # ── ⑥ 缺 txid ⇒ 计划层拒（防回退；不需改 40 处调用方）──
    kb_tx = tempfile.mkdtemp(prefix="memoria-w1-txid-")
    _mk(kb_tx)
    no_txid = _plan()
    no_txid.pop("txid")
    res = apply_plan(kb_tx, no_txid, session_id=sid, origin="human")
    codes = [row.get("code") for row in (res.get("errors") or [])]
    check(
        "W1(R-S2-4) 计划缺 txid ⇒ 计划层拒（missing_field）",
        res.get("status") == "error" and "missing_field" in codes,
        f"status={res.get('status')}, codes={codes}",
        "缺 txid 仍写入 ⇒ 审计/撤销键失锚",
    )

    payload = {
        "schema": "contract-w1/v2",
        "mechanism": "apply_plan(origin: str) 必填 + agent 路径一次性清关令牌（observation.issue_clearance）",
        "honest_boundary": "origin 是调用点自述，不是可信身份；进程内无法区分 human 与撒谎的 human",
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
