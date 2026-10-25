#!/usr/bin/env python
"""W3 写前备份：必红 fixture（`contract_w3`）。

## 判别力
| 断言 | 构造的路径 | 期望 |
|---|---|---|
| `backup_failure_zero_write` | 注入"备份失败"（`snapshot_pre_images` 返回 error） | `apply_plan` 返回错误、**文件字节未变**、未产生任何写入 |
| `undo_byte_exact` | 正常写入后 `restore_batch()` | 文件**逐字节**回到 apply 前（sha256 相同） |
| `pre_image_captured_before_write` | 正常写入 | 备份批次里含目标文件的 pre-image（能回滚才说明"写前"备份） |
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

from memoria.services.agent import backup  # noqa: E402
from memoria.services.agent.apply import apply_plan  # noqa: E402

RESULTS: list[dict] = []


def check(name: str, ok: bool, detail: str, falsifier: str = "") -> None:
    RESULTS.append({"name": name, "ok": bool(ok), "detail": detail, "falsifier": falsifier})


DOC = "# 甲\n甲第一行\n\n## 小节\n小节正文\n"


def _mk(kb: str) -> None:
    with open(os.path.join(kb, "d.md"), "w", encoding="utf-8", newline="") as fh:
        fh.write(DOC)


def _sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _plan(txid: str = "20261025T091000Z-01") -> dict:
    return {
        "v": 1,
        "txid": txid,
        "intent": "契约测试：改一行（W3）",
        "ops": [
            {"op": "replace_lines", "op_id": "o1", "file": "d.md",
             "range": {"start": 5, "end": 5}, "text": "改后的正文", "expect": "小节正文"}
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    # ── ① 备份失败 ⇒ 零写入 ──
    kb = tempfile.mkdtemp(prefix="memoria-w3-fail-")
    _mk(kb)
    before = _sha(os.path.join(kb, "d.md"))
    orig = backup.snapshot_pre_images

    def _failing(*a, **k):
        calls.append(1)
        return {"status": "error", "code": "backup_failed", "message": "注入：备份失败（fixture）", "files": []}

    calls: list[int] = []
    backup.snapshot_pre_images = _failing  # type: ignore[assignment]
    try:
        res = apply_plan(kb, _plan(), session_id="w3", origin="human")
    finally:
        backup.snapshot_pre_images = orig  # type: ignore[assignment]
    after = _sha(os.path.join(kb, "d.md"))
    check(
        "W3 备份失败 ⇒ 零写入（文件 sha 不变）",
        res.get("status") == "error" and len(calls) == 1 and after == before,
        f"status={res.get('status')}, code={res.get('code')}, 备份调用={len(calls)}, sha不变={after == before}",
        "备份失败仍写入 ⇒ W3 的'失败即整批不写'不成立",
    )

    # ── ② 正常写入 ⇒ 单次撤销逐字节复原 ──
    kb2 = tempfile.mkdtemp(prefix="memoria-w3-undo-")
    _mk(kb2)
    host = os.path.join(kb2, "d.md")
    before2 = _sha(host)
    txid = "20261025T091001Z-02"
    res = apply_plan(kb2, _plan(txid), session_id="w3-undo", origin="human")
    mid = _sha(host)
    undo = backup.restore_batch(kb2, "w3-undo", txid, rel_paths=["d.md"])
    restored = _sha(host)
    check(
        "W3 写后 restore_batch() ⇒ 逐字节回 pre-image",
        res.get("status") == "ok" and mid != before2 and restored == before2,
        f"apply={res.get('status')}, 写入生效={mid != before2}, undo={undo.get('status')}, 逐字节={restored == before2}",
        "撤销后 sha 不同 ⇒ 撤销链没有真正回到 pre-image",
    )

    # ── ③ pre-image 确实是"写前"拍的 ──
    pre = os.path.join(kb2, ".memoria", "agent", "backups", "w3-undo", txid, "files", "d.md")
    found = os.path.isfile(pre)
    check(
        "W3 备份批次里含写前 pre-image（证明备份在写之前）",
        found and (open(pre, encoding="utf-8").read() == DOC if found else False),
        f"pre-image 路径存在={found}",
        "没有 pre-image ⇒ 备份发生在写之后（无法回滚）",
    )

    payload = {
        "schema": "contract-w3/v1",
        "mechanism": "apply_plan 第一步 backup.snapshot_pre_images；失败零写入；restore_batch 逐字节回滚",
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
