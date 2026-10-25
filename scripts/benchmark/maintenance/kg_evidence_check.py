#!/usr/bin/env python
"""KG 证据三元组机检（D-KG-01：任何边/节点量化必须写 (语料 sha, 测量源, 时间)）。

## 裁决依据

`docs/design/kg-ontology-v0.md` §5.1：
```
强制格式   (语料 sha, 测量源, 时间) 三元组 —— 缺一即 E1 无效
```

## 这个脚本查什么

扫描指定文档里**看起来像 KG 量化**的行（出现 `edges=` / `nodes=` / `N 条边` / `N 节点`
等数字断言），检查该行或**同一小节内**是否出现三元组的三个成分：

1. **语料 sha**：`sha256` / `语料 sha` / `archive_sha` / 64 位十六进制串
2. **测量源**：`collect_graph_data` / `kb_build` / `measurement_source` / `测量源`
3. **时间**：ISO 时间戳 / `measured_at` / `T` + 时分

缺任一项 ⇒ 该断言按 E1 **无效**，脚本非零退出。

## 为什么需要它（不是形式主义）

本轮 KG 辩论里，四家对**同一个库**报出 479 / 454 / 408 / 404 / 429 五个数字，
其中至少一个是"旧 cache 当事实源"、一个是"links 数当边数"。
没有三元组，这类数字**无法复核、无法相减、无法裁决**（E4.3 跨口径不可相减）。

## 用法

    python scripts/benchmark/maintenance/kg_evidence_check.py <file> [<file>...]
    python scripts/benchmark/maintenance/kg_evidence_check.py --json out.json <file>...
    python scripts/benchmark/maintenance/kg_evidence_check.py --self-test   # 证红/证绿

退出码：0 = 全部断言都带三元组（或无量化断言）；1 = 有断言缺三元组。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

#: 看起来像 KG 量化断言的行（保守匹配：宁可漏报，不可误报到无法使用）
QUANT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b\d+\s*(?:条)?\s*(?:边|edges)\b", re.IGNORECASE),
    re.compile(r"\b\d+\s*(?:个)?\s*(?:节点|nodes?)\b", re.IGNORECASE),
    re.compile(r"\b(?:edges|nodes)\s*=\s*\d+", re.IGNORECASE),
    re.compile(r"\b\d+\s*/\s*\d+\s*(?:reference|contain|extend)", re.IGNORECASE),
]

#: 三元组成分的识别（任一命中即视为该成分存在）
CORPUS_SHA_PATTERNS = [
    re.compile(r"语料\s*sha", re.IGNORECASE),
    re.compile(r"corpus_sha", re.IGNORECASE),
    re.compile(r"archive_sha", re.IGNORECASE),
    re.compile(r"manifest_sha", re.IGNORECASE),
    re.compile(r"\b[0-9a-f]{16,64}\b"),  # 十六进制哈希串
]
SOURCE_PATTERNS = [
    re.compile(r"测量源", re.IGNORECASE),
    re.compile(r"measurement_source", re.IGNORECASE),
    re.compile(r"collect_graph_data", re.IGNORECASE),
    re.compile(r"build_knowledge_base", re.IGNORECASE),
    re.compile(r"kb_build", re.IGNORECASE),
]
TIME_PATTERNS = [
    re.compile(r"measured_at", re.IGNORECASE),
    re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}"),
    re.compile(r"测量时间", re.IGNORECASE),
]


def _has(patterns: list[re.Pattern[str]], text: str) -> bool:
    return any(p.search(text) for p in patterns)


def _display_path(path: str) -> str:
    """仓库内文件用相对路径；仓库外（如临时目录自证）用绝对路径 —— 跨盘符时 relpath 会抛。"""
    try:
        rel = os.path.relpath(path, REPO)
    except ValueError:
        return path.replace("\\", "/")
    if rel.startswith(".."):
        return path.replace("\\", "/")
    return rel.replace("\\", "/")


def check_file(path: str, window: int = 12) -> dict:
    """检查一个文件。`window` = 断言行往前后各看多少行找三元组成分。

    用"邻近窗口"而不是"严格同一行"，因为三元组通常写成表格头/小节说明，
    要求同行会让规范写法也被判红（那是尺子坏了，不是证据坏了）。
    """
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()

    findings: list[dict] = []
    for idx, line in enumerate(lines):
        if not any(p.search(line) for p in QUANT_PATTERNS):
            continue
        # 跳过纯注释/代码块里的实现细节（只查叙述性断言）
        stripped = line.strip()
        if stripped.startswith(("//", "#!", "```")):
            continue
        lo = max(0, idx - window)
        hi = min(len(lines), idx + window + 1)
        context = "".join(lines[lo:hi])
        missing = []
        if not _has(CORPUS_SHA_PATTERNS, context):
            missing.append("corpus_sha")
        if not _has(SOURCE_PATTERNS, context):
            missing.append("measurement_source")
        if not _has(TIME_PATTERNS, context):
            missing.append("measured_at")
        findings.append(
            {
                "line": idx + 1,
                "text": stripped[:160],
                "missing": missing,
                "ok": not missing,
            }
        )
    return {
        "path": _display_path(path),
        "assertions": findings,
        "total": len(findings),
        "failing": sum(1 for f in findings if not f["ok"]),
    }


def self_test() -> int:
    """证红/证绿：证明本检查器有判别力（不是"永远绿"）。"""
    import tempfile

    good = (
        "# 测量\n"
        "语料 sha d2c9c54c616f8e01b07e2f272e6aba36922a3b434786a5621bf8ae1f59247d39\n"
        "测量源 collect_graph_data() 现场调用\n"
        "时间 2026-10-26T00:30:00\n"
        "结果：edges=454 nodes=133\n"
    )
    bad = "# 测量\n结果：edges=454 nodes=133\n"
    tmpd = tempfile.mkdtemp(prefix="kg-evidence-selftest-")
    gp = os.path.join(tmpd, "good.md")
    bp = os.path.join(tmpd, "bad.md")
    with open(gp, "w", encoding="utf-8") as fh:
        fh.write(good)
    with open(bp, "w", encoding="utf-8") as fh:
        fh.write(bad)

    g = check_file(gp)
    b = check_file(bp)
    ok = g["failing"] == 0 and b["failing"] > 0
    print(f"[{'OK' if g['failing'] == 0 else 'FAIL'}] 带三元组的断言 ⇒ 通过 (failing={g['failing']})")
    print(f"[{'OK' if b['failing'] > 0 else 'FAIL'}] 缺三元组的断言 ⇒ 判红 (failing={b['failing']})")
    print(f"\n== SELF-TEST: {'PASS' if ok else 'FAIL'} ==")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="KG 证据三元组机检（D-KG-01）")
    ap.add_argument("files", nargs="*")
    ap.add_argument("--json", default="")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--window", type=int, default=12)
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not args.files:
        ap.error("需要至少一个文件路径（或用 --self-test）")

    results = [check_file(f, window=args.window) for f in args.files]
    total = sum(r["total"] for r in results)
    failing = sum(r["failing"] for r in results)
    payload = {
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "schema": "kg-evidence-check/v1",
        "results": results,
        "total_assertions": total,
        "failing": failing,
        "passed": failing == 0,
    }
    for r in results:
        print(f"{r['path']}: {r['total']} 条量化断言, {r['failing']} 条缺三元组")
        for a in r["assertions"]:
            if not a["ok"]:
                print(f"  L{a['line']} 缺 {a['missing']}: {a['text']}")
    print(f"\n== RESULT: {'PASS' if failing == 0 else 'FAIL'} ==  ({total} 断言 / {failing} 缺三元组)")
    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(REPO, args.json)
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        print(f"wrote: {args.json}")
    return 0 if failing == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
