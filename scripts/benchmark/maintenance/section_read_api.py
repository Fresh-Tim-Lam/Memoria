#!/usr/bin/env python
"""S1a 验收：`outline / section / snippet` 逐条对照 `as-section-range.md` D 节。

任一条失败 ⇒ 非零退出。仅读 `docs/example/**` 的真实语料 + 合成小语料，不改任何文件。

## 断言的来源（D 节逐项）

| 断言 | 依据 |
|---|---|
| A1 归一化：去 `#`、去 ATX 闭合、空白折叠、默认不折大小写、`ci=True` 才折 | D.1 |
| A2 唯一命中 | D.2 ② |
| A3 多候选 + `path` 父级链过滤命中正确那一节 | D.2 ③a / C2 |
| A4 多候选 + `near_line` 取之前最近同名 | D.2 ③b |
| A5 仍 >1 ⇒ `AMBIGUOUS_SECTION` 且带 `candidates[]`（**不得取首个**） | D.2 ③c / C3 |
| A6 无匹配 ⇒ `SECTION_NOT_FOUND` 且带 `suggestions[]` | D.2 ④ / D.3 |
| A7 `line=` 一等回退（C4），且与按标题解析到同一节 | D.3 / C4 |
| A8 `NO_HEADINGS` | D.3 |
| A9 `INVALID_LEVEL` | D.3 |
| A10 C1：围栏代码块内的 `#` 不进 outline | C1 |
| A11 预算：outline ≤800 / section ≤4000（超限有 part/cursor）/ snippet ≤600 | task-120 + D 节 |
| A12 C3 触发率的真实估计（同名标题占比） | Lead 关注项（>20% 才需改设计） |

## 用法

    python scripts/benchmark/maintenance/section_read_api.py [--json out.json]
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

# ── 密封性（R-S1A-3）：`DocumentService.__post_init__` 会调 `remember_last_kb_path()`
# 写**全局** UI 设置（`config/ui-settings.json`）；app 运行时该文件被占用 ⇒ PermissionError。
# 把 config 目录重定向到临时目录，测量才能密封可复跑，且**不改全局配置**。
_SEALED_CONFIG_DIR = tempfile.mkdtemp(prefix="memoria-cfg-")
os.environ.setdefault("MEMORIA_CONFIG_DIR", _SEALED_CONFIG_DIR)

from memoria.services.agent import section_index as si  # noqa: E402
from memoria.services.heading_proposals import scan_headings  # noqa: E402

KB_DIRS = [
    "docs/example/AAA_KnowledgeBase",
    "docs/example/人工智能导论知识点汇总",
    "docs/example/行政法",
    "docs/example/AAA_Vocab",
]

RESULTS: list[dict] = []


def check(name: str, ok: bool, detail: str, falsifier: str = "") -> None:
    RESULTS.append({"name": name, "ok": bool(ok), "detail": detail, "falsifier": falsifier})


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


def corpus() -> list[tuple[str, str]]:
    """[(rel_path, text)]，按路径排序（确定性）。"""
    out: list[tuple[str, str]] = []
    for kb in KB_DIRS:
        base = os.path.join(REPO, kb)
        if not os.path.isdir(base):
            continue
        for f in walk_md(base):
            with open(f, encoding="utf-8") as fh:
                out.append((os.path.relpath(f, REPO).replace("\\", "/"), fh.read()))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    docs = corpus()
    total_lines = sum(t.count("\n") + 1 for _, t in docs)
    total_bytes = sum(len(t.encode("utf-8")) for _, t in docs)

    # ── A1 归一化（D.1）───────────────────────────────────────────────────
    check("A1 去行首 # 与 ATX 闭合 #", si.normalize_title("## 标题 ##") == "标题", repr(si.normalize_title("## 标题 ##")))
    check(
        "A1 空白折叠",
        si.normalize_title("## a\t  b   c") == "a b c",
        repr(si.normalize_title("## a\t  b   c")),
    )
    check(
        "A1 默认不折大小写 / ci=True 才折",
        si.normalize_title("## Foo") == "Foo" and si.normalize_title("## Foo", ci=True) == "foo",
        f"{si.normalize_title('## Foo')!r} / {si.normalize_title('## Foo', ci=True)!r}",
    )

    # ── 合成语料上的 A2/A5/A6/A8/A9/A10/A11 ───────────────────────────────
    synth = (
        "# 文档\n"
        "前言\n"
        "## 案例 1\n"
        "### 定义\n"
        "第一处\n"
        "## 案例 2\n"
        "### 定义\n"
        "第二处\n"
        "```python\n"
        "# 这不是标题\n"
        "```\n"
        "## 结尾\n"
        "完\n"
    )
    heads = scan_headings(synth)
    check(
        "A10 C1 围栏内 # 不进 outline",
        [h.title for h in heads] == ["文档", "案例 1", "定义", "案例 2", "定义", "结尾"],
        f"titles={[h.title for h in heads]}",
        "围栏内 # 被计入 ⇒ C1 失效",
    )
    sec, err = si.resolve_section(synth, heading="结尾")
    check("A2 唯一命中", err is None and sec is not None and sec.heading.line_no == 12, f"err={err and err.code}, line={sec and sec.heading.line_no}")

    sec, err = si.resolve_section(synth, heading="定义")
    check(
        "A5 同名多候选 ⇒ AMBIGUOUS_SECTION（不取首个）",
        err is not None and err.code == si.AMBIGUOUS_SECTION and len(err.extra.get("candidates", [])) == 2,
        f"code={err and err.code}, n={len(err.extra.get('candidates', [])) if err else 0}",
        "返回了某个候选 ⇒ C3 红线破了",
    )
    sec, err = si.resolve_section(synth, heading="定义", path=["案例 2"])
    check(
        "A3 path 父级链消歧命中正确那一节",
        err is None and sec is not None and sec.heading.line_no == 7,
        f"err={err and err.code}, line={sec and sec.heading.line_no}",
        "命中案例 1 的节（line 4）⇒ C2 失效",
    )
    sec, err = si.resolve_section(synth, heading="定义", near_line=5)
    check(
        "A4 near_line 取之前最近同名",
        err is None and sec is not None and sec.heading.line_no == 4,
        f"line={sec and sec.heading.line_no}",
    )
    sec, err = si.resolve_section(synth, heading="不存在的节")
    check(
        "A6 无匹配 ⇒ SECTION_NOT_FOUND + suggestions",
        err is not None and err.code == si.SECTION_NOT_FOUND and "suggestions" in err.extra,
        f"code={err and err.code}, extra_keys={list(err.extra) if err else []}",
    )
    sec, err = si.resolve_section("只有正文\n没有标题\n", heading="x")
    check("A8 NO_HEADINGS", err is not None and err.code == si.NO_HEADINGS, f"code={err and err.code}")
    sec, err = si.resolve_section(synth, heading="定义", level=7)
    check("A9 INVALID_LEVEL", err is not None and err.code == si.INVALID_LEVEL, f"code={err and err.code}")
    sec3, err3 = si.resolve_section(synth, line=8)
    check(
        "A7 line= 一等回退（C4）命中包含该行的节",
        err3 is None and sec3 is not None and sec3.heading.line_no == 7 and sec3.heading.title == "定义",
        f"err={err3 and err3.code}, title={sec3 and sec3.heading.title}, line={sec3 and sec3.heading.line_no}",
    )

    # ── 真实语料：C2 重名双锚 + 预算 + snippet ────────────────────────────
    dup_docs = 0
    dup_groups = 0
    path_ok = 0
    path_checked = 0
    dup_heads = 0
    total_heads = 0
    worst_doc: dict | None = None

    budget_outline_max = 0
    budget_section_over = 0
    section_parts_max = 1
    snippet_max_tokens = 0
    outline_over_budget: list[str] = []

    for rel, text in docs:
        heads = scan_headings(text)
        total_heads += len(heads)
        # 同名分组
        by: dict[str, list] = {}
        for h in heads:
            by.setdefault(h.title, []).append(h)
        dups = {k: v for k, v in by.items() if len(v) > 1}
        if dups:
            dup_docs += 1
            dup_groups += len(dups)
            dup_heads += sum(len(v) for v in dups.values())
            rate = sum(len(v) for v in dups.values()) / max(1, len(heads))
            if worst_doc is None or rate > worst_doc["rate"]:
                worst_doc = {"doc": rel, "rate": round(rate, 4), "dup_heads": sum(len(v) for v in dups.values()), "heads": len(heads)}
            # C2：每个重名组，若父级路径不同 ⇒ 用父级链应能唯一命中
            for title, group in dups.items():
                parents = {tuple(h.parent_path) for h in group}
                if len(parents) == len(group) and len(parents) > 1:
                    path_checked += 1
                    target = group[0]
                    sec, err = si.resolve_section(text, heading=title, path=list(target.parent_path))
                    if err is None and sec is not None and sec.heading.line_no == target.line_no:
                        path_ok += 1

        # outline 预算
        ol = si.build_outline(text)
        budget_outline_max = max(budget_outline_max, ol.get("tokens", 0))
        if ol.get("tokens", 0) > si.OUTLINE_MAX_TOKENS and not ol.get("truncated") and not ol.get("degraded"):
            outline_over_budget.append(rel)

        # section 预算：对最长的节测超预算切片
        if heads:
            secs = []
            for i, h in enumerate(heads):
                s, e = si.resolve_section(text, line=h.line_no)
                if s is not None:
                    secs.append(s)
            if secs:
                biggest = max(secs, key=lambda s: s.line_count)
                payload = si.get_section(
                    text, heading=biggest.heading.title, path=list(biggest.heading.parent_path)
                )
                if payload.get("code") == si.AMBIGUOUS_SECTION:
                    payload = si.get_section(text, line=biggest.heading.line_no)
                if payload.get("ok") and payload.get("truncated"):
                    budget_section_over += 1
                    section_parts_max = max(section_parts_max, int(payload.get("parts", 1)))
                    if payload.get("tokens", 0) > si.SECTION_MAX_TOKENS and not payload.get("next_cursor"):
                        check(
                            f"A11 section 超预算必须有 cursor（{rel}）",
                            False,
                            f"tokens={payload.get('tokens')}, parts={payload.get('parts')}, cursor={payload.get('next_cursor')}",
                        )
                elif payload.get("ok"):
                    budget_section_over += 0
                    # 未超预算：正文 token 必须 ≤ 预算
                    if si.estimate_tokens(payload.get("text", "")) > si.SECTION_MAX_TOKENS:
                        check(
                            f"A11 section 未截断却超预算（{rel}）",
                            False,
                            f"tokens={si.estimate_tokens(payload.get('text', ''))}",
                        )

        # snippet 预算（取一个必然命中的词：文档里第一个非空词的片段）
        probe = None
        for ln in text.split("\n"):
            if len(ln.strip()) >= 2:
                probe = ln.strip()[:6]
                break
        if probe:
            sn = si.get_snippet(text, query=probe)
            if sn.get("ok") and sn.get("windows"):
                snippet_max_tokens = max(snippet_max_tokens, sn.get("tokens", 0))

    check(
        "A11 outline 全部 ≤ 预算或已降级",
        not outline_over_budget,
        f"over_budget={outline_over_budget[:3]}, max_tokens={budget_outline_max}",
        "超预算却没降级 ⇒ 预算形同虚设",
    )
    check(
        "A11 section 超预算的节都给了 part/cursor",
        section_parts_max >= 1,
        f"超预算节数={budget_section_over}, 最大分片={section_parts_max}",
    )
    check(
        "A11 snippet 窗口 ≤ 预算",
        snippet_max_tokens <= si.SNIPPET_MAX_TOKENS,
        f"max_snippet_tokens={snippet_max_tokens}",
        "单窗口就超预算 ⇒ ±ctx 默认值过大",
    )

    # ── C2 真实语料结论 ─────────────────────────────────────────────────
    check(
        "A3(C2) 真实语料：父级链消歧命中率",
        path_checked > 0 and path_ok == path_checked,
        f"{path_ok}/{path_checked} 组（父级路径互异的同名标题）",
        "任一失败 ⇒ 同级/异父重名会静默取错节",
    )

    # ── A13 R-S1B-1 自适应回退（目标节 >50% 全文 ⇒ 整篇 1 轮）────────────
    # ① 触发：h1 覆盖大半篇（且整篇在预算内）⇒ 回整篇、1 片、文本逐字等于全文
    dom_body = "# 甲\n" + "\n".join(f"甲的第 {i} 行正文内容" for i in range(30)) + "\n\n## 小\n小内容\n"
    pay = si.get_section(dom_body, heading="甲")
    check(
        "A13 回退触发：目标节 >50% 全文且整篇在预算内 ⇒ 整篇 1 片",
        bool(pay.get("ok"))
        and pay.get("fallback") == "whole_document"
        and pay.get("parts") == 1
        and pay.get("next_cursor") is None
        and pay.get("text") == dom_body,
        f"fallback={pay.get('fallback')}, parts={pay.get('parts')}, "
        f"share={(pay.get('section') or {}).get('doc_share')}, tok={pay.get('tokens')}",
        "未回退 ⇒ 目标节占大半篇时仍要多付一轮/多片",
    )
    # ② 不误伤：同一篇里的小节（占比远小于 50%）⇒ 只给该节
    pay = si.get_section(dom_body, heading="小")
    check(
        "A13 回退不误伤：目标节 ≤50% ⇒ 只给该节",
        bool(pay.get("ok"))
        and pay.get("fallback") is None
        and (pay.get("section") or {}).get("title") == "小",
        f"fallback={pay.get('fallback')}, title={(pay.get('section') or {}).get('title')}, "
        f"share={(pay.get('section') or {}).get('doc_share')}",
        "小节也被整篇替换 ⇒ 回退条件写错（会白送全文）",
    )
    # ③ 预算保护：整篇超预算 ⇒ 不回退（回整篇会被切成更多片，反而更贵）
    over_body = (
        "# 长文\n"
        + "\n".join(f"前言第 {i} 行，内容够长才会把 token 顶上去。" for i in range(150))
        + "\n\n## 大节\n"
        + "\n".join(f"大节第 {i} 行，内容够长才会把 token 顶上去。" for i in range(300))
        + "\n\n## 尾节\n末节。\n"
    )
    pay = si.get_section(over_body, heading="大节")
    check(
        "A13 预算保护：整篇超预算 ⇒ 不回退（标 fallback_skipped）",
        bool(pay.get("ok"))
        and pay.get("fallback") is None
        and pay.get("fallback_skipped") == "over_budget",
        f"fallback={pay.get('fallback')}, skipped={pay.get('fallback_skipped')}, "
        f"doc_tokens={pay.get('doc_tokens')}, share={(pay.get('section') or {}).get('doc_share')}",
        "超预算仍回整篇 ⇒ 会被切成更多片，反而更贵",
    )

    # ── A12 C3 触发率 ────────────────────────────────────────────────────
    dup_rate = dup_heads / max(1, total_heads)
    check(
        "A12 C3 触发率（同名标题占比）< 20%",
        dup_rate < 0.20,
        f"{dup_heads}/{total_heads} = {dup_rate:.4%}；最差文档 {worst_doc}",
        ">20% ⇒ 按 falsifier 需改显式 {#id} 锚（设计变更，须先报 Lead）",
    )

    payload = {
        "schema": "section-read-api-acceptance/v1",
        "contract": "artifacts/agent/verify/debate/assumptions/as-section-range.md#D",
        "corpus": {"kbs": KB_DIRS, "docs": len(docs), "lines": total_lines, "bytes": total_bytes},
        "metrics": {
            "outline_max_tokens": budget_outline_max,
            "section_budget_exceeded_docs": budget_section_over,
            "section_max_parts": section_parts_max,
            "snippet_max_tokens": snippet_max_tokens,
            "dup_heads": dup_heads,
            "total_heads": total_heads,
            "dup_rate": round(dup_rate, 6),
            "dup_docs": dup_docs,
            "dup_groups": dup_groups,
            "c2_path_checked": path_checked,
            "c2_path_ok": path_ok,
            "worst_dup_doc": worst_doc,
        },
        "assertions": RESULTS,
        "passed": all(r["ok"] for r in RESULTS),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    payload["artifactSha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    print(f"corpus: {len(docs)} docs / {total_lines} lines / {total_bytes} bytes")
    for r in RESULTS:
        print(f"  [{'OK' if r['ok'] else 'FAIL'}] {r['name']}: {r['detail']}")
        if not r["ok"] and r["falsifier"]:
            print(f"        falsifier: {r['falsifier']}")
    m = payload["metrics"]
    print(
        f"\nmetrics: outline_max={m['outline_max_tokens']}tok (budget {si.OUTLINE_MAX_TOKENS}) | "
        f"section_over_budget_docs={m['section_budget_exceeded_docs']} max_parts={m['section_max_parts']} | "
        f"snippet_max={m['snippet_max_tokens']}tok | dup_rate={m['dup_rate']:.4%}"
    )
    print(f"C3 触发率 {m['dup_rate']:.2%}（阈值 20%）；C2 双锚 {m['c2_path_ok']}/{m['c2_path_checked']}")
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
