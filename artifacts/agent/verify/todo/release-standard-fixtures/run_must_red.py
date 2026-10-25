#!/usr/bin/env python3
"""必红证明：用**真实已发布 release 的 body** 反向复现历史违规，证明 release_preflight 真的会 exit 1。

为什么不用编造 fixture：规范连续三版违反（v0.4.7/0.4.8/0.5.0 标题带副标题），
所以这里直接把「Lead 记录的真实违规标题」与「从已修复 body 反推的违规形态」喂给检查器：

  改坏（真实 body 副本） → 必须 exit 1 + 命中预期检查项
  还原（原始 body）     → 必须 exit 0
  仓库文件哈希           → 前后完全一致（fixture 只动临时副本，不写工作区）

用法：
  python artifacts/agent/verify/todo/release-standard-fixtures/run_must_red.py

退出码：0 = 全部必红/必绿符合预期；1 = 有 fixture 不符（检查器漏检或误报）。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCRIPT = ROOT / "scripts" / "agent" / "release_preflight.py"
REL_DIR = ROOT / "artifacts" / "agent" / "verify" / "todo" / "release-standard-releases"
WATCHED = [
    ROOT / "src" / "memoria" / "__version__.py",
    ROOT / "docs" / "conventions" / "version.md",
    ROOT / "Package" / "VERSION",
]

# Lead 记录的真实违规标题（2026-10-25 修复前）
HISTORICAL_TITLES = {
    "v0.4.7": "Memoria v0.4.7 —— 收摊",
    "v0.4.8": "Memoria v0.4.8 —— 修 P1 + 知识图谱调研",
    "v0.5.0": "Memoria v0.5.0 —— agent 能力架构（S1–S5…）",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.is_file() else "MISSING"


def snapshot() -> dict[str, str]:
    return {str(p.relative_to(ROOT)): sha(p) for p in WATCHED}


def run_check(tag: str, meta: dict, tmp: Path) -> tuple[int, dict]:
    rel = tmp / f"{tag}-mutated.json"
    rel.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--tag", tag, "--verify-published",
         "--offline", "--release-json", str(rel), "--json"],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
        encoding="utf-8", errors="replace",
    )
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = {"raw": proc.stdout + proc.stderr}
    return proc.returncode, out


def must_red(tag: str, base: dict, mutate, expected_id: str, tmp: Path,
             label: str, results: list) -> None:
    meta = json.loads(json.dumps(base))  # deep copy
    meta = mutate(meta) or meta
    code, out = run_check(tag, meta, tmp)
    failed = out.get("failed", [])
    ok = code == 1 and expected_id in failed
    results.append((f"{tag} {label}", ok,
                    f"exit={code} failed={failed}（期望 exit=1 且含 {expected_id}）"))


def swap_blocks(body: str) -> str:
    lines = body.split("\n")
    ie = lines.index("## English")
    iz = lines.index("## 中文")
    head, en, zh = lines[:ie], lines[ie:iz], lines[iz:]
    return "\n".join(head + zh + [""] + en)


def main() -> int:
    before = snapshot()

    def git_diff_src() -> str:
        proc = subprocess.run(["git", "diff", "--stat", "--", "src/"], cwd=ROOT,
                              capture_output=True, text=True, timeout=30,
                              encoding="utf-8", errors="replace")
        return proc.stdout.strip()

    before_diff = git_diff_src()
    results: list[tuple[str, bool, str]] = []
    tmp = Path(tempfile.mkdtemp(prefix="release-must-red-"))
    try:
        for tag in ("v0.4.7", "v0.4.8", "v0.5.0"):
            base = json.loads((REL_DIR / f"{tag}.json").read_text(encoding="utf-8"))

            # 0) 基线：已修复的真实 body 必须 PASS（绿）
            code, out = run_check(tag, base, tmp)
            results.append((f"{tag} 已修复真实 body 基线", code == 0,
                            f"exit={code} failed={out.get('failed')}"))

            # 1) 真实历史违规标题（三版各自记录的原标题）⇒ TITLE-EXACT 必红
            must_red(tag, base,
                     lambda m, t=tag: m.update(name=HISTORICAL_TITLES[t]),
                     "TITLE-EXACT", tmp, "真实历史副标题必红", results)

            # 2) title 正确前缀 + 任意后缀 ⇒ 必红（防 startswith 宽松实现）
            must_red(tag, base,
                     lambda m: m.update(name=m["name"] + " (hotfix)"),
                     "TITLE-EXACT", tmp, "标题后缀必红", results)

            # 3) 英文段挪到中文段之后 ⇒ BODY-BILINGUAL 必红
            def en_after_zh(m):
                m["body"] = swap_blocks(m["body"])

            must_red(tag, base, en_after_zh, "BODY-BILINGUAL", tmp,
                     "中文在前必红", results)

            # 4) 英文段变 stub（≤200 字符，不含造价段）⇒ BODY-BILINGUAL 必红
            def stub_en(m):
                lines = m["body"].split("\n")
                ie = lines.index("## English")
                # 英文标题后到下一个二级标题之间的正文整段换成一句
                j = next(i for i in range(ie + 1, len(lines)) if lines[i].startswith("## "))
                m["body"] = "\n".join(lines[:ie + 1] + ["", "Short stub.", ""] + lines[j:])

            must_red(tag, base, stub_en, "BODY-BILINGUAL", tmp,
                     "英文 stub 必红", results)

            # 5) 删掉中文造价段标题 ⇒ COST-SECTION 必红
            def drop_cost_zh(m):
                m["body"] = m["body"].replace("## 造价（Agent 算力）", "## 造价说明")

            must_red(tag, base, drop_cost_zh, "COST-SECTION", tmp,
                     "缺中文造价段必红", results)

            # 6) 造价段去量级（元/人民币/CNY/USD/RMB/花费 全删）⇒ COST-SECTION 必红
            def drop_magnitude(m):
                b = m["body"]
                for token in ("元人民币", "元", "人民币", "CNY", "USD", "RMB", "花费"):
                    b = b.replace(token, "")
                m["body"] = b

            must_red(tag, base, drop_magnitude, "COST-SECTION", tmp,
                     "造价无量级必红", results)

            # 7) 造价段去统计口径 ⇒ COST-SECTION 必红
            def drop_basis(m):
                m["body"] = m["body"].replace("统计口径", "统计说明").replace("合并统计", "合并记账")

            must_red(tag, base, drop_basis, "COST-SECTION", tmp,
                     "造价无统计口径必红", results)

            # 8) 资产只剩 1 个 ⇒ ASSETS-COUNT 必红
            must_red(tag, base,
                     lambda m: m.update(assets=m["assets"][:1]),
                     "ASSETS-COUNT", tmp, "资产数量=1 必红", results)

            # 9) 还原：真实 body 重新跑必须绿（证明不是一次性的）
            code, out = run_check(tag, base, tmp)
            results.append((f"{tag} 还原后必绿", code == 0,
                            f"exit={code} failed={out.get('failed')}"))
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    after = snapshot()
    files_unchanged = before == after
    results.append(("仓库文件哈希前后一致（fixture 未写工作区）", files_unchanged,
                    f"before={before} after={after}"))

    # git diff -- src/ 前后必须一致（本 runner 只读真实 body，不写 src；
    # 仓库里可能已有其他 agent 的未提交改动，所以断言「前后一致」而非「为空」）
    after_diff = git_diff_src()
    results.append(("git diff -- src/ 前后一致（本 runner 不写 src）",
                    before_diff == after_diff,
                    after_diff if after_diff else "(empty)"))

    ok = all(passed for _, passed, _ in results)
    print("MUST-RED PROOF" + (" PASS" if ok else " FAIL"))
    for name, passed, detail in results:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}: {detail}")
    print(f"合计 {len(results)} 项：{sum(1 for _, p, _ in results if p)} PASS / "
          f"{sum(1 for _, p, _ in results if not p)} FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
