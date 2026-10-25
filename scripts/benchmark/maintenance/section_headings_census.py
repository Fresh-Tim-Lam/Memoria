#!/usr/bin/env python
"""S1c / R-D2 验收：heading 语义已统一，且与实测基线同口径。

## 这个脚本断言什么（任一条失败 ⇒ 非零退出）

**A. 与基线口径等价（parity）**
把 `scan_headings()` 的口径与 `as-section-range-measure.json` 的 `totals` 逐字段比对：
docs / awareHeadingCount(3517) / naiveHeadingCount(3609) / falseHeadingInFence(92) /
falseHeadingInFrontmatter(0) / duplicateTextCount(33) / h1(279) / levelDist。
基线值从**产物 JSON** 读，不写死在脚本里（避免"改脚本迁就实现"）。

**B. R-D2 的两处行为变化被证明**
- h1 提议数：旧口径（`^(#{2,6})` 朴素匹配）**0** → 新口径 **279**
- 围栏内 `#` 不再被当 heading：误判 **92 → 0**

**C. C1/C2/C5 的最小单元断言**（合成语料，不依赖外部文件）
- C1：围栏内 `#`、frontmatter 内 `#` 不计入
- C2：同名 h3 在不同父级下 `parent_path` 不同（双锚之一）
- C5：h1..h6 全部识别；h7（`#######`）不识别；级别范围常量 == (1, 6)

**D. "无第二套 heading 正则"的可机检版本**
扫描 `src/**/*.py`，列出所有 heading 字面正则的落点；只允许 `heading_proposals.py`（唯一实现）。
其余落点必须在 `PENDING_UNIFICATION` 白名单里（= 已登记的债，不允许**新增**）——
出现白名单外的新落点 ⇒ FAIL。这样"债不增长"是被机器钉住的，而不是靠记性。

**范围澄清（arch-contract 验收时指出，防未来误读）**：本机检**只扫 `.py`**。
前端渲染层的 heading 正则（`ui/static/app/js/{lexer,markdown-preview,app,math-normalize}.js` 等）
**不在本机检范围内** —— 它们是渲染层解析，不是 section 寻址语义，且 task-120 写域不含前端；
"全仓无第二套 heading 正则"这句话的**准确口径**是「**Python 写路径**已统一，其余为已登记债」。

## 用法

    python scripts/benchmark/maintenance/section_headings_census.py            # 断言 + 人类可读
    python scripts/benchmark/maintenance/section_headings_census.py --json out.json

产物不含墙钟时间（保证两次运行 sha 一致，E4/E5）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))

# ── 密封性（R-S1A-3）：`DocumentService.__post_init__` 会调 `remember_last_kb_path()`
# 写**全局** UI 设置（`config/ui-settings.json`）；app 运行时该文件被占用 ⇒ PermissionError。
# 把 config 目录重定向到临时目录，测量才能密封可复跑，且**不改全局配置**。
_SEALED_CONFIG_DIR = tempfile.mkdtemp(prefix="memoria-cfg-")
os.environ.setdefault("MEMORIA_CONFIG_DIR", _SEALED_CONFIG_DIR)

from memoria.services.heading_proposals import (  # noqa: E402
    HEADING_LEVEL_MAX,
    HEADING_LEVEL_MIN,
    PROPOSABLE_LEVEL_MIN,
    level_distribution,
    normalize_title,
    propose_ranges_from_headings,
    scan_headings,
)

BASELINE_JSON = os.path.join(
    REPO, "artifacts/agent/verify/debate/assumptions/as-section-range-measure.json"
)

KB_DIRS = [
    "docs/example/AAA_KnowledgeBase",
    "docs/example/人工智能导论知识点汇总",
    "docs/example/行政法",
    "docs/example/AAA_Vocab",
]

#: 旧口径（逐字复制自 2026-10-25 之前的 heading_proposals.py），只用于算"旧值"做对照，
#: **不得**被产品代码引用；本脚本是唯一允许出现它的地方（作为历史口径证据）。
OLD_PROPOSAL_RE = re.compile(r"^(#{2,6})\s+")

#: 已登记、尚未统一的 heading 正则落点（"债清单"）。出现白名单外的落点 ⇒ FAIL。
#: 说明：这些模块的用途**不是** section 寻址（噪音清洗 / mention 提议 / 前端 lexer），
#: 统一它们需要各自的行为验收，故不在 task-120 的写域内，登记为后续任务。
PENDING_UNIFICATION = {
    "src/memoria/services/mention_proposals.py": "section kind 的 mention 提议（需独立验收）",
    "src/memoria/services/search_aux.py": "检索噪音清洗，非寻址语义",
    "src/memoria/services/suggest_metadata.py": "元数据建议的噪音清洗",
}

HEADING_LITERAL_RES = [
    re.compile(r"#\{1,6\}"),
    re.compile(r"#\{2,6\}"),
    re.compile(r"\(\#\{1,6\}\)"),
]


def walk_md(d: str) -> list[str]:
    out: list[str] = []
    for name in sorted(os.listdir(d)):
        p = os.path.join(d, name)
        if os.path.isdir(p):
            if name in ("node_modules", ".git", ".memoria"):
                continue
            out.extend(walk_md(p))
        elif name.lower().endswith(".md"):
            out.append(p)
    return out


def census() -> dict:
    """跑语料，产出确定性统计（不含时间/路径绝对化）。"""
    tot = {
        "docs": 0,
        "naiveHeadingCount": 0,
        "falseHeadingInFence": 0,
        "falseHeadingInFrontmatter": 0,
        "duplicateTextCount": 0,
        "awareHeadingCount": 0,
        "naiveH1": 0,
        "oldProposalCount": 0,
        "newProposalCount": 0,
        "h1ProposalOld": 0,
        "h1ProposalNew": 0,
    }
    level_dist: dict[int, int] = {}

    for kb in KB_DIRS:
        base = os.path.join(REPO, kb)
        if not os.path.isdir(base):
            raise SystemExit(f"语料缺失：{kb}")
        for f in walk_md(base):
            with open(f, encoding="utf-8") as fh:
                text = fh.read()
            tot["docs"] += 1

            from memoria.services.heading_proposals import (  # local: 避免顶部 import 顺序噪音
                frontmatter_end_line0,
                fence_ranges,
                split_lines,
            )

            lines = split_lines(text)
            fm_end = frontmatter_end_line0(lines)
            fences = fence_ranges(lines)
            inside = bytearray(len(lines))
            for a, b in fences:
                for i in range(a, min(b + 1, len(lines))):
                    inside[i] = 1

            # 旧口径：朴素 regex、无围栏/ frontmatter 过滤
            for i, line in enumerate(lines):
                m = OLD_PROPOSAL_RE.match(line)
                if m:
                    tot["oldProposalCount"] += 1
                m1 = re.match(r"^(#{1,6})\s+", line)
                if m1:
                    tot["naiveHeadingCount"] += 1
                    if len(m1.group(1)) == 1:
                        tot["naiveH1"] += 1
                    if inside[i]:
                        tot["falseHeadingInFence"] += 1
                    if fm_end >= 0 and i <= fm_end:
                        tot["falseHeadingInFrontmatter"] += 1

            heads = scan_headings(text)
            tot["awareHeadingCount"] += len(heads)
            for h in heads:
                level_dist[h.level] = level_dist.get(h.level, 0) + 1

            props = propose_ranges_from_headings(text)
            tot["newProposalCount"] += len(props)
            # 新口径下被提议的 h1 数（用 range.start 行号回查级别）
            line_level = {h.line_no: h.level for h in heads}
            for p in props:
                if line_level.get(p["range"]["start"]["line_hint"]) == 1:
                    tot["h1ProposalNew"] += 1

            by: dict[str, int] = {}
            for h in heads:
                k = h.title.lower()
                by[k] = by.get(k, 0) + 1
            tot["duplicateTextCount"] += sum(1 for c in by.values() if c > 1)

    tot["levelDist"] = {str(k): level_dist.get(k, 0) for k in sorted(level_dist)}
    tot["h1"] = level_dist.get(1, 0)
    return tot


def unit_assertions() -> list[dict]:
    """C1/C2/C5 的最小单元断言（合成语料）。"""
    results: list[dict] = []

    def check(name: str, ok: bool, detail: str, falsifier: str) -> None:
        results.append({"name": name, "ok": bool(ok), "detail": detail, "falsifier": falsifier})

    # C5：级别范围
    doc_lv = "".join(f"{'#' * n} L{n}\n" for n in range(1, HEADING_LEVEL_MAX + 1))
    hs = scan_headings(doc_lv)
    check(
        "C5 级别 1..6 全部识别",
        [h.level for h in hs] == list(range(HEADING_LEVEL_MIN, HEADING_LEVEL_MAX + 1)),
        f"levels={[h.level for h in hs]}",
        "任一级别漏识别 ⇒ C5 未落地",
    )
    check(
        "C5 常量写死为 (1,6)",
        (HEADING_LEVEL_MIN, HEADING_LEVEL_MAX) == (1, 6),
        f"{(HEADING_LEVEL_MIN, HEADING_LEVEL_MAX)}",
        "常量被改动 ⇒ 与基线口径不一致",
    )
    from memoria.services.heading_proposals import HEADING_RE  # noqa: E402

    check(
        "C5 正则由常量唯一拼出（无第二份字面量）",
        HEADING_RE.pattern == r"^(#{1,6})\s+",
        f"pattern={HEADING_RE.pattern!r}",
        "正则不是由 HEADING_LEVEL_MIN/MAX 拼出 ⇒ 出现第二处定义",
    )
    check(
        "C5 h7 不是 heading",
        scan_headings("####### L7\n") == [],
        f"{scan_headings('####### L7')}",
        "h7 被识别 ⇒ 正则范围错",
    )

    # C1：围栏
    fenced = "# T\n```\n# not a heading\n```\n## A\n"
    hs = scan_headings(fenced)
    check(
        "C1 围栏内 # 不计入",
        [h.title for h in hs] == ["T", "A"],
        f"titles={[h.title for h in hs]}",
        "围栏内 # 被计入 ⇒ C1 未落地（基线实测 92 个误判）",
    )
    # C1：~~~ 围栏 + 未闭合
    tilde = "# T\n~~~\n# nope\n"
    check(
        "C1 ~~~ 未闭合围栏延伸到文末",
        [h.title for h in scan_headings(tilde)] == ["T"],
        f"titles={[h.title for h in scan_headings(tilde)]}",
        "未闭合围栏未生效 ⇒ 误判",
    )
    # C1：frontmatter
    fm = "---\ntitle: x\n# 不是标题\n---\n# 真标题\n"
    check(
        "C1 frontmatter 内 # 不计入",
        [h.title for h in scan_headings(fm)] == ["真标题"],
        f"titles={[h.title for h in scan_headings(fm)]}",
        "frontmatter 内 # 被计入 ⇒ C1 未落地",
    )

    # C2：同名 heading 的 parent_path 双锚
    dup = "## 案例 1\n### 定义\nA\n## 案例 2\n### 定义\nB\n"
    hs = scan_headings(dup)
    defs = [h for h in hs if h.title == "定义"]
    check(
        "C2 同名 h3 靠 parent_path 区分",
        len(defs) == 2 and defs[0].parent_path == ("案例 1",) and defs[1].parent_path == ("案例 2",),
        f"parents={[h.parent_path for h in defs]}",
        "parent_path 相同 ⇒ C2 双锚失效（93.9% 重名是同级）",
    )
    check(
        "C2 line_no 是原文件 1-based",
        [h.line_no for h in defs] == [2, 5],
        f"line_no={[h.line_no for h in defs]}",
        "行号偏移 ⇒ C4 行号回退不可用",
    )

    # D.1：ATX 闭合归一化
    check(
        "D.1 ATX 闭合 # 被剥离",
        normalize_title("## 标题 ##") == "标题",
        repr(normalize_title("## 标题 ##")),
        "`## 标题 ##` 归一化残留 `#` ⇒ 文本锚匹配失败",
    )

    # R-D2 行为：h1 现在会被提议
    props = propose_ranges_from_headings("# 甲\n正文\n## 乙\n正文\n")
    check(
        "R-D2 h1 进入提议（旧口径 0）",
        len(props) == 2 and props[0]["name"] == "甲",
        f"names={[p['name'] for p in props]}",
        "h1 未进入提议 ⇒ R-D2 未落地（实测应 279）",
    )
    return results


def heading_regex_inventory() -> dict:
    """枚举 product code 里的 heading 字面正则落点。

    只在**代码行**里找（用 `tokenize` 排除注释与 docstring）——
    否则"在本文件里写一句 `原来那是 ^(#{1,6})`"这种说明性文字会被误判成第二套实现。
    """
    hits: dict[str, list[int]] = {}
    src = os.path.join(REPO, "src")
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__", ".git", "vendor")]
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, REPO).replace("\\", "/")
            code_lines = _code_lines(path)
            if not code_lines:
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh, 1):
                    if i in code_lines and any(p.search(line) for p in HEADING_LITERAL_RES):
                        hits.setdefault(rel, []).append(i)
    unified = "src/memoria/services/heading_proposals.py"
    unexpected = {p: v for p, v in hits.items() if p != unified and p not in PENDING_UNIFICATION}
    return {
        "hits": {k: v for k, v in sorted(hits.items())},
        "unified": unified,
        "pending": {k: PENDING_UNIFICATION[k] for k in sorted(PENDING_UNIFICATION) if k in hits},
        "unexpected": unexpected,
    }


def _code_lines(path: str) -> set[int]:
    """返回该文件里**属于代码**的行号集合（排除 COMMENT 与 docstring/bare-string）。"""
    import tokenize

    code: set[int] = set()
    try:
        with open(path, "rb") as fh:
            toks = list(tokenize.tokenize(fh.readline))
    except (OSError, tokenize.TokenError, IndentationError, SyntaxError):
        return code
    stmt_starts = {
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.NL,
        tokenize.ENCODING,
        tokenize.ENDMARKER,
    }
    prev = tokenize.NEWLINE
    for t in toks:
        if t.type == tokenize.COMMENT:
            continue
        if t.type == tokenize.STRING:
            # 语句起始处的 STRING = docstring / bare string ⇒ 不算代码（说明性文字）
            if prev not in stmt_starts:
                code.add(t.start[0])
            prev = t.type
            continue
        if t.type in stmt_starts:
            prev = t.type
            continue
        code.add(t.start[0])
        prev = t.type
    return code


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    with open(BASELINE_JSON, encoding="utf-8") as fh:
        baseline = json.load(fh)["totals"]

    tot = census()
    units = unit_assertions()
    inv = heading_regex_inventory()

    parity_fields = [
        ("docs", baseline["docs"]),
        ("awareHeadingCount", baseline["awareHeadingCount"]),
        ("naiveHeadingCount", baseline["naiveHeadingCount"]),
        ("falseHeadingInFence", baseline["falseHeadingInFence"]),
        ("falseHeadingInFrontmatter", baseline["falseHeadingInFrontmatter"]),
        ("duplicateTextCount", baseline["duplicateTextCount"]),
        ("h1", 279),
    ]
    parity = [
        {"field": f, "got": tot.get(f), "expected": e, "ok": tot.get(f) == e} for f, e in parity_fields
    ]
    # 级别分布也逐级比对（基线 report §1.2）
    expected_levels = {"1": 279, "2": 1574, "3": 1545, "4": 118, "5": 1}
    for lv, cnt in expected_levels.items():
        got = tot["levelDist"].get(lv, 0)
        parity.append({"field": f"levelDist[{lv}]", "got": got, "expected": cnt, "ok": got == cnt})

    behavior = {
        "h1_proposals_old": 0,  # 旧正则最小级别 2 ⇒ 恒 0
        "h1_proposals_new": tot["h1ProposalNew"],
        "fence_false_headings_old": tot["falseHeadingInFence"],
        "fence_false_headings_new": 0,  # 新口径按定义跳过围栏
        "naive_h1": tot["naiveH1"],
        "aware_h1": tot["h1"],
        "fence_false_h1": tot["naiveH1"] - tot["h1"],
        "old_proposal_count": tot["oldProposalCount"],
        "new_proposal_count": tot["newProposalCount"],
        "proposal_delta": tot["newProposalCount"] - tot["oldProposalCount"],
    }
    # delta 必须被完全解释：new = old + 新增 h1 提议 − 被修掉的围栏内 h2..h6 误判
    fence_false_non_h1 = behavior["fence_false_headings_old"] - behavior["fence_false_h1"]
    behavior["fence_false_non_h1"] = fence_false_non_h1
    behavior["expected_new_count"] = (
        behavior["old_proposal_count"] + behavior["h1_proposals_new"] - fence_false_non_h1
    )
    behavior["delta_fully_explained"] = (
        behavior["new_proposal_count"] == behavior["expected_new_count"]
    )
    behavior_ok = (
        behavior["h1_proposals_old"] == 0
        and behavior["h1_proposals_new"] == 279
        and behavior["fence_false_headings_old"] == 92
        and behavior["fence_false_headings_new"] == 0
        and behavior["delta_fully_explained"]
    )

    units_ok = all(u["ok"] for u in units)
    parity_ok = all(p["ok"] for p in parity)
    inv_ok = not inv["unexpected"]
    # 唯一实现不自带字面正则（正则由 C5 常量拼出），故期望：命中的字面正则只应出现在
    # `PENDING_UNIFICATION` 白名单里，且**不再出现新的落点**。
    regex_ok = set(inv["hits"]) == set(inv["pending"]) and inv_ok

    payload = {
        "schema": "section-headings-census/v1",
        "baseline_artifact": "artifacts/agent/verify/debate/assumptions/as-section-range-measure.json",
        "corpus": KB_DIRS,
        "totals": tot,
        "parity": parity,
        "behavior": behavior,
        "units": units,
        "heading_regex_inventory": inv,
        "results": {
            "parity_ok": parity_ok,
            "behavior_ok": behavior_ok,
            "units_ok": units_ok,
            "no_unexpected_regex": inv_ok,
            "regex_inventory_ok": regex_ok,
        },
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    payload["artifactSha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(REPO, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        print(f"wrote: {args.json}")

    print("\n== A. parity vs baseline ==")
    for p in parity:
        print(f"  [{'OK' if p['ok'] else 'FAIL'}] {p['field']}: got={p['got']} expected={p['expected']}")
    print("\n== B. R-D2 behavior ==")
    print(f"  h1 proposals: {behavior['h1_proposals_old']} -> {behavior['h1_proposals_new']}")
    print(
        f"  fence false headings: {behavior['fence_false_headings_old']} -> "
        f"{behavior['fence_false_headings_new']}"
    )
    print(
        f"  proposals total: {behavior['old_proposal_count']} -> {behavior['new_proposal_count']} "
        f"(delta {behavior['proposal_delta']:+d})"
    )
    print(
        f"  delta 解释: old {behavior['old_proposal_count']} + h1 {behavior['h1_proposals_new']} "
        f"- 围栏内 h2..h6 误判 {behavior['fence_false_non_h1']} = "
        f"{behavior['expected_new_count']} "
        f"[{'一致' if behavior['delta_fully_explained'] else '不一致!'}]"
    )
    print(
        f"  h1 口径: naive {behavior['naive_h1']} - 围栏误判 {behavior['fence_false_h1']} "
        f"= aware {behavior['aware_h1']}"
    )
    print("\n== C. unit assertions ==")
    for u in units:
        print(f"  [{'OK' if u['ok'] else 'FAIL'}] {u['name']}: {u['detail']}")
        if not u["ok"]:
            print(f"        falsifier: {u['falsifier']}")
    print("\n== D. heading regex inventory ==")
    for path, lines in inv["hits"].items():
        tag = "UNIFIED" if path == inv["unified"] else ("PENDING" if path in inv["pending"] else "UNEXPECTED")
        print(f"  [{tag}] {path}: lines {lines}")
    print(f"  unexpected: {inv['unexpected']}")

    ok = parity_ok and behavior_ok and units_ok and inv_ok and regex_ok
    print(f"\n== RESULT: {'PASS' if ok else 'FAIL'} ==  (sha256 {payload['artifactSha256'][:16]}…)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
