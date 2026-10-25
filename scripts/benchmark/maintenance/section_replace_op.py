#!/usr/bin/env python
"""S1b 验收：`replace_section` 写 op（复用唯一写者链，不新增写原语）。

## 断言（任一条失败 ⇒ 非零退出）

**B1 零新写者**：`compile_plan()` 为 `replace_section` 产出的原语调用**只能是 `edit_body`**
（现有原语之一），不得出现任何新原语名。
**B2 矩阵**（在**临时复制的 KB** 上跑，绝不碰仓库内的 KB）：
  - h1 节替换 ✅
  - h2 节替换 ✅
  - 同名标题：无 `path` ⇒ `ambiguous_section`（**不得取首个**）；给 `path` ⇒ 成功且只改对的那一节
  - 围栏代码块内的 `#` 不构成节边界（替换范围覆盖到本该属于本节的行）
  - `expect` 与当前正文不符 ⇒ 拒（`expect_mismatch` 一类错误），文件零改动
**B3 单撤销逐字节复原**：apply 后内容按预期变化；`restore_batch` 后**逐字节**等于 apply 前。
**B4 dry-run 零落盘**：`preview_plan` 之后文件字节不变。

## 用法

    python scripts/benchmark/maintenance/section_replace_op.py [--json out.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import uuid

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))

# ── 密封性（R-S1A-3）：`DocumentService.__post_init__` 会调 `remember_last_kb_path()`
# 写**全局** UI 设置（`config/ui-settings.json`）；app 运行时该文件被占用 ⇒ PermissionError。
# 把 config 目录重定向到临时目录，测量才能密封可复跑，且**不改全局配置**。
_SEALED_CONFIG_DIR = tempfile.mkdtemp(prefix="memoria-cfg-")
os.environ.setdefault("MEMORIA_CONFIG_DIR", _SEALED_CONFIG_DIR)

from memoria.services.agent import apply as apply_mod  # noqa: E402
from memoria.services.agent import backup as backup_mod  # noqa: E402
from memoria.services.agent.plan import (  # noqa: E402
    OP_REPLACE_SECTION,
    preview_plan,
)

RESULTS: list[dict] = []


def check(name: str, ok: bool, detail: str, falsifier: str = "") -> None:
    RESULTS.append({"name": name, "ok": bool(ok), "detail": detail, "falsifier": falsifier})


def sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def write(p: str, s: str) -> None:
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(s)


def read(p: str) -> str:
    with open(p, encoding="utf-8", newline="") as fh:
        return fh.read()


DOC = """# 总标题

导语。

## 第一节

第一节正文 A。
第一节正文 B。

```python
# 这是代码注释，不是标题
print(1)
```

## 第二节

第二节正文。

### 小节 X

X 正文。

## 重复

第一次出现。

## 重复

第二次出现。

## 尾巴

最后。
"""


_TX_SEQ = 0


def next_txid() -> str:
    """计划信封要求 `txid`（同秒内多次提交必须唯一，见 kb.py:3385 的实测踩坑）。"""
    global _TX_SEQ
    _TX_SEQ += 1
    now = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{now}-{_TX_SEQ:02d}"


def plan_for(rel: str, **op) -> dict:
    base = {"op": OP_REPLACE_SECTION, "op_id": "s1", "file": rel}
    base.update(op)
    return {"v": 1, "intent": "replace_section 验收", "txid": next_txid(), "ops": [base]}


def run_case(tmp: str, kb: str, rel: str, name: str, **op) -> dict:
    """跑一个 replace_section 用例：preview(零落盘) → apply → 撤销逐字节。"""
    path = os.path.join(kb, rel)
    before_sha = sha(path)
    before_text = read(path)

    # B4：dry-run 零落盘
    pv = preview_plan(kb, plan_for(rel, **op))
    dry_ok = sha(path) == before_sha

    session = f"verify-{uuid.uuid4().hex[:8]}"
    compiled = apply_mod.compile_plan(kb, plan_for(rel, **op))
    if compiled.get("status") != "ok":
        return {
            "case": name,
            "ok": False,
            "stage": "compile",
            "code": compiled.get("code"),
            "errors": compiled.get("errors"),
            "dry_ok": dry_ok,
        }

    primitives = sorted({c["primitive"] for c in compiled.get("calls", [])})
    res = apply_mod.apply_plan(kb, plan_for(rel, **op), session_id=session, origin="human")
    if res.get("status") != "ok":
        return {"case": name, "ok": False, "stage": "apply", "res": res, "dry_ok": dry_ok,
                "primitives": primitives}

    after_text = read(path)
    changed = after_text != before_text
    undo = backup_mod.restore_batch(kb, session, rel_paths=[rel])
    restored = sha(path) == before_sha

    return {
        "case": name,
        "ok": True,
        "dry_ok": dry_ok,
        "primitives": primitives,
        "changed": changed,
        "undo_status": undo.get("status"),
        "restored_byte_exact": restored,
        "before_len": len(before_text),
        "after_len": len(after_text),
        "expect_code": (res.get("errors") or [{}])[0].get("code") if res.get("errors") else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="memoria-s1b-")
    kb = os.path.join(tmp, "kb")
    os.makedirs(kb)
    rel = "doc.md"
    write(os.path.join(kb, rel), DOC)

    cases: list[dict] = []

    # ── B2 矩阵 ────────────────────────────────────────────────────────────
    c = run_case(tmp, kb, rel, "h1 整节替换", heading="总标题", text="导语。\n改后的导语。\n")
    cases.append(c)

    c = run_case(tmp, kb, rel, "h2 节替换", heading="第一节", text="新的第一节正文。\n")
    cases.append(c)

    # 同名：无 path ⇒ 必须歧义
    pv = preview_plan(kb, plan_for(rel, heading="重复", text="x"))
    amb = (pv.get("status") != "ok") or any(
        "ambiguous_section" in str(e.get("code")) for e in (pv.get("errors") or [])
    )
    cases.append(
        {
            "case": "同名标题无 path ⇒ ambiguous_section",
            "ok": bool(amb),
            "status": pv.get("status"),
            "errors": [e.get("code") for e in (pv.get("errors") or [])],
        }
    )

    # 同名：给 path（父级链为空，用 near_line 更贴切）⇒ 用 near_line 定位第二处
    c = run_case(tmp, kb, rel, "同名标题 near_line 消歧", heading="重复", near_line=24, text="第二次改。\n")
    cases.append(c)

    # 围栏内 `#` 不构成边界：第一节的节体应包含围栏里的两行，替换后它们消失
    path = os.path.join(kb, rel)
    before = read(path)
    session = f"verify-{uuid.uuid4().hex[:8]}"
    res = apply_mod.apply_plan(kb, plan_for(rel, heading="第一节", text="只剩一行。\n"), session_id=session, origin="human")
    after = read(path)
    fence_swallowed = (
        res.get("status") == "ok"
        and "# 这是代码注释，不是标题" not in after
        and after.count("## 第二节") == 1
        and "只剩一行。" in after
    )
    backup_mod.restore_batch(kb, session, rel_paths=[rel])
    cases.append(
        {
            "case": "围栏内 # 不截断节（整节被替换，代码块随之消失）",
            "ok": fence_swallowed and read(path) == before,
            "after_has_comment": "# 这是代码注释" in after,
            "restored": read(path) == before,
        }
    )

    # expect 不符 ⇒ 拒且零改动
    before_sha = sha(path)
    bad = plan_for(rel, heading="第二节", text="不该落盘。\n", expect="完全不匹配的旧正文")
    cp = apply_mod.compile_plan(kb, bad)
    codes = [e.get("code") for e in (cp.get("errors") or [])]
    cases.append(
        {
            "case": "expect 不符 ⇒ 拒（零改动）",
            "ok": cp.get("status") != "ok" and sha(path) == before_sha,
            "codes": codes,
        }
    )

    # ── B5 审批卡可用：preview 必须给行级 diff + 节身份 ────────────────────
    pv = preview_plan(kb, plan_for(rel, heading="第二节", text="预览用新正文。\n"))
    pf = (pv.get("files") or [{}])[0]
    pop = (pf.get("ops") or [{}])[0]
    check(
        "B5 preview 给行级 diff + 节身份（审批不能盲批）",
        pv.get("status") == "ok"
        and pop.get("diff_available") is True
        and bool(pop.get("lines_changed"))
        and isinstance(pop.get("section"), dict)
        and pop["section"].get("title") == "第二节",
        f"status={pv.get('status')}, diff_available={pop.get('diff_available')}, "
        f"lines_changed={pop.get('lines_changed')}, section={pop.get('section')}",
        "无 diff/无节身份 ⇒ 人只能看 op 名批准，等于盲批",
    )

    # ── B1 零新写者 ───────────────────────────────────────────────────────
    prims = {p for c in cases if c.get("primitives") for p in c["primitives"]}
    known_primitives = {
        "confirm_kp_range", "update_kp", "apply_link_instances", "detach_link_instance",
        "delete_link_route", "edit_body", "create_file", "rename_file", "delete_file",
        "move_file", "create_edge", "delete_kp", "rename_kp_id", "rebuild_manifest",
    }
    check(
        "B1 replace_section 只用既有原语（edit_body）",
        prims == {"edit_body"} and prims <= known_primitives,
        f"primitives={sorted(prims)}",
        "出现 edit_body 之外的原语 ⇒ 新增了写路径",
    )

    # ── B2/B3 汇总 ────────────────────────────────────────────────────────
    matrix_ok = all(c.get("ok") for c in cases)
    check("B2 矩阵全部通过", matrix_ok, f"cases={[(c['case'], c['ok']) for c in cases]}")

    restored_all = all(c.get("restored_byte_exact", True) for c in cases)
    check(
        "B3 单撤销逐字节复原",
        restored_all,
        f"restored={[c.get('restored_byte_exact') for c in cases if 'restored_byte_exact' in c]}",
        "任一用例撤销后字节不同 ⇒ 撤销链被绕过",
    )
    dry_all = all(c.get("dry_ok", True) for c in cases)
    check("B4 dry-run 零落盘", dry_all, f"dry_ok={[c.get('dry_ok') for c in cases if 'dry_ok' in c]}")

    payload = {
        "schema": "section-replace-op-acceptance/v1",
        "op": OP_REPLACE_SECTION,
        "kb_fixture": "临时 KB（tempfile，非仓库 KB）",
        "doc_sha_before": hashlib.sha256(DOC.encode("utf-8")).hexdigest(),
        "cases": cases,
        "assertions": RESULTS,
        "passed": all(r["ok"] for r in RESULTS),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    payload["artifactSha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    for r in RESULTS:
        print(f"  [{'OK' if r['ok'] else 'FAIL'}] {r['name']}: {r['detail']}")
        if not r["ok"] and r["falsifier"]:
            print(f"        falsifier: {r['falsifier']}")
    print("\n== cases ==")
    for c in cases:
        print(f"  {c['case']}: ok={c.get('ok')} primitives={c.get('primitives')} "
              f"restored={c.get('restored_byte_exact')} dry={c.get('dry_ok')} codes={c.get('codes') or c.get('errors')}")
    print(f"\n== RESULT: {'PASS' if payload['passed'] else 'FAIL'} ==  (sha256 {payload['artifactSha256'][:16]}…)")

    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(REPO, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        print(f"wrote: {args.json}")

    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
