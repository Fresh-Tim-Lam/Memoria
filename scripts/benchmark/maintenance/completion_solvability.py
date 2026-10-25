#!/usr/bin/env python
"""task-131｜S1 遗留债：粒度读的「任务可完成性」机判（B 级）

## 为什么是 B 级而不是 A 级（先说清，不许含糊）
A 级 = 真实任务完成率（要调真实 LLM 跑任务、判答案对错）。
**当前环境不具备**：`src/memoria/services/agent/llm/` 有完整 provider 基础设施，
但无 API key（env 无 `*_API_KEY`），且既有 benchmark 脚本全为 `nature: PROXY`（不调模型）。
⇒ 无法在此环境产出 A 级数据。**本脚本只做 B 级。**

## B 级测什么（严格命名，不冒充完成率）
**测的是「任务在给定读面下的可完成性（solvability）」，不是「模型完成率」。**

对每个有确定答案的任务，机判两件事：
1. **结构可完成性**：只允许该读面提供的工具时，是否存在能拿到全部必需信息的调用序列？
2. **必需调用数 / 消歧次数**：完成它最少需要几次工具调用、几次消歧。

**这个东西能机判的原因是**：`section` 只返回"一节"，而任务的答案依赖"哪些节" ——
这是**读面的结构性属性**，不依赖模型强弱。模型再强也变不出 `section` 没返回的节。

## 任务类别（每类都有确定答案 + 可机判）
- **T1 节内改**：把某 h2 节内某行的说法 X 改成 Y。
  答案 = (file, heading, line)。判据：`section(file,heading)` 是否覆盖该行。
- **T2 跨节枚举**：找出全文所有提到关键词 W 的节（W 出现在 ≥2 个 h2 节）。
  答案 = 节标题集合。判据：`section` 单次只能给 1 节 ⇒ 若答案集大小 >1，**单次 section 结构上不可能**。
- **T3 同名消歧**：改第 k 个同名标题的节内某行。
  答案 = (file, heading, 第 k 个)。判据：`section(heading)` 是否返回 AMBIGUOUS_SECTION。
- **T4 全文统计**：统计某模式在全文出现次数。
  答案 = 整数。判据：`section` 只能看到一节 ⇒ 结构上不可能。

## 两臂
- **A（整篇）**：`read_document`（含 offset/limit 续读），一次拿到全文窗口
- **B（粒度）**：`outline` + `section`

## 判分口径（机判，不含主观）
对每个任务，判定 `solvable_via` 列表：
- `read_document` 能拿到答案所需全部行的位置 ⇒ A 可完成
- 存在 section 调用序列能拿到 ⇒ B 可完成
- 记 `B_min_calls`、`B_needs_disambiguation`、`A_min_calls`

## 用法

    python scripts/benchmark/maintenance/completion_solvability.py [--json out.json] [--repeat 3]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
import tempfile
from collections import Counter

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))
# ⚠️ 必须先设（DocumentService.__post_init__ 会写全局 ui_settings）
os.environ.setdefault("MEMORIA_CONFIG_DIR", tempfile.mkdtemp(prefix="memoria-cfg-"))

from memoria.services.agent.tools.kb import build_kb_tools  # noqa: E402
from memoria.services.heading_proposals import scan_headings  # noqa: E402

KB_DIRS = [
    "docs/example/AAA_KnowledgeBase",
    "docs/example/人工智能导论知识点汇总",
    "docs/example/行政法",
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


def split_lines(text: str) -> list[str]:
    return text.split("\n")


def sections_of(text: str) -> list[dict]:
    """切出 h2 节：{title, start_line(1-based), end_line(1-based), body}"""
    lines = split_lines(text)
    heads = [h for h in scan_headings(text) if h.level == 2]
    out = []
    for i, h in enumerate(heads):
        start = h.index0 + 1                       # 1-based 行号（标题行）
        end = (heads[i + 1].index0) if i + 1 < len(heads) else len(lines)
        out.append({"title": h.title, "start_line": start, "end_line": end,
                    "body": "\n".join(lines[start - 1:end])})
    return out


def build_tasks() -> list[dict]:
    """确定性构造四类任务。每类都带确定答案。"""
    docs = []
    for kb in KB_DIRS:
        base = os.path.join(REPO, kb)
        if not os.path.isdir(base):
            continue
        for f in walk_md(base):
            try:
                text = open(f, encoding="utf-8").read()
            except Exception:
                continue
            docs.append((kb, f, text))
    docs.sort(key=lambda x: (x[0], x[1]))

    tasks: list[dict] = []
    for kb, path, text in docs:
        if len(text) < 500:
            continue
        secs = sections_of(text)
        if len(secs) < 2:
            continue
        lines = split_lines(text)
        rel = os.path.relpath(path, os.path.join(REPO, kb)).replace("\\", "/")
        base = {"kb": kb, "src": path, "rel": rel, "doc_bytes": len(text.encode("utf-8"))}

        # ── T1 节内改：选第一个节里第一个够长的正文行 ──
        s0 = secs[0]
        t1_line = None
        for idx in range(s0["start_line"] + 1, s0["end_line"]):
            s = lines[idx - 1].strip()
            if len(s) >= 12 and not s.startswith("#"):
                t1_line = idx
                break
        if t1_line:
            tasks.append({**base, "type": "T1_in_section_edit",
                          "answer": {"heading": s0["title"], "line": t1_line},
                          "anchor_text": lines[t1_line - 1]})

        # ── T2 跨节枚举：找出现在 ≥2 个 h2 节的中文词 ──
        words = re.findall(r"[\u4e00-\u9fa5]{2,6}", text)
        cnt = Counter(words)
        for w, n in cnt.most_common(40):
            if n < 3:
                continue
            hit_secs = [s["title"] for s in secs if w in s["body"]]
            if len(hit_secs) >= 2:
                tasks.append({**base, "type": "T2_cross_section_enum",
                              "answer": {"word": w, "sections": sorted(hit_secs)},
                              "answer_size": len(hit_secs)})
                break

        # ── T3 同名消歧：找同名 h2 ──
        titles = [s["title"] for s in secs]
        dup = [t for t, c in Counter(titles).items() if c >= 2]
        if dup:
            tasks.append({**base, "type": "T3_duplicate_heading",
                          "answer": {"heading": dup[0], "occurrences": Counter(titles)[dup[0]]}})

        # ── T4 全文统计：某个模式在全文出现次数 ──
        m = re.search(r"[\u4e00-\u9fa5]{3,5}", text)
        if m:
            pat = m.group(0)
            tasks.append({**base, "type": "T4_fulltext_count",
                          "answer": {"pattern": pat, "count": text.count(pat)}})

    # 每类取前 N 个，保证覆盖
    out: list[dict] = []
    per_type = {"T1_in_section_edit": 4, "T2_cross_section_enum": 4,
                "T3_duplicate_heading": 3, "T4_fulltext_count": 3}
    for t, limit in per_type.items():
        got = [x for x in tasks if x["type"] == t][:limit]
        out.extend(got)
    return out


def judge(task: dict, tools: dict) -> dict:
    """机判：该任务在 A（整篇）/ B（粒度）读面下的可完成性。"""
    rel = task["rel"]
    ttype = task["type"]
    rec = {"id": f"{task['kb']}/{rel}:{ttype}", "type": ttype,
           "doc_bytes": task["doc_bytes"], "answer": task["answer"]}

    # ── 公共：读该文档全文（用于确认真实行号/节） ──
    rd = tools["read_document"].handler({"path": rel, "limit": 2000})
    rd_text = rd.text
    # read_document 是否截断（2000 行上限）
    truncated = ("续读" in rd_text or "offset" in rd_text[:600])

    if ttype == "T1_in_section_edit":
        heading, line = task["answer"]["heading"], task["answer"]["line"]
        anchor = task["anchor_text"]
        # A：整篇读是否覆盖该行
        a_ok = (line <= 2000) or truncated is False
        rec["A_solvable"] = a_ok
        rec["A_min_calls"] = 1
        # B 臂（不窄化）：粒度路径 = outline + section(heading)，验证它覆盖该行
        sec = tools["section"].handler({"file": rel, "heading": heading})
        m = re.search(r"L(\d+)-(\d+)", sec.text[:120])
        section_covers = False
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            section_covers = (lo <= line <= hi) and ("AMBIGUOUS" not in sec.text)
        # 若 section 覆盖 ⇒ B 可完成（2 次调用）；否则 B 仍可用 read_document/grep 兜底
        rec["B_solvable"] = bool(section_covers) or a_ok
        if section_covers:
            rec["B_min_calls"] = 2          # outline + section
            rec["B_via"] = "outline+section"
        else:
            rec["B_min_calls"] = 1          # 兜底 read_document（但那就不是粒度读了）
            rec["B_via"] = "fallback:read_document"
        rec["B_section_covers"] = section_covers
        rec["B_needs_disambiguation"] = "AMBIGUOUS" in sec.text
        rec["B_section_header"] = sec.text[:100]
        rec["anchor_text"] = anchor[:60]

    elif ttype == "T2_cross_section_enum":
        want = set(task["answer"]["sections"])
        # A：read_document 全文 ⇒ 能枚举（若未截断）
        rec["A_solvable"] = not truncated
        rec["A_min_calls"] = 1
        # ★ B 臂：不窄化。真实 agent 有 grep：grep(W) 一次就列出全部命中位置 ⇒ 能枚举，且只需 1 次
        word = task["answer"]["word"]
        g = tools["grep"].handler({"pattern": word})
        grep_ok = ("命中" in g.text or "处" in g.text) and "错误" not in g.text[:80]
        # 也记录「若只用 outline+section」的路径与次数（诚实披露成本）
        out = tools["outline"].handler({"file": rel})
        listed = sum(1 for w in want if w in out.text)
        section_path_calls = 1 + len(want)   # outline + 每节一次 section
        rec["B_solvable"] = bool(grep_ok) or (listed == len(want))
        # 取更省的那条路径
        if grep_ok:
            rec["B_min_calls"] = 1
            rec["B_via"] = "grep"
        else:
            rec["B_min_calls"] = section_path_calls
            rec["B_via"] = "outline+section×N"
        rec["B_needs_disambiguation"] = False
        rec["answer_size"] = len(want)
        rec["B_outline_covers"] = f"{listed}/{len(want)}"
        rec["B_section_only_calls"] = section_path_calls
        rec["B_grep_head"] = g.text[:120]

    elif ttype == "T3_duplicate_heading":
        heading = task["answer"]["heading"]
        # A：整篇读能区分（靠行号）
        rec["A_solvable"] = True
        rec["A_min_calls"] = 1
        # B 臂（不窄化）：section(heading) 单给标题 ⇒ 应回 AMBIGUOUS，需消歧
        sec = tools["section"].handler({"file": rel, "heading": heading})
        ambiguous = "AMBIGUOUS" in sec.text
        rec["B_needs_disambiguation"] = ambiguous
        # 兜底路径：read_document/grep 可绕开消歧 ⇒ B 仍可完成
        rec["B_solvable"] = True
        if ambiguous:
            rec["B_min_calls"] = 3            # outline + section(失败) + section(消歧)
            rec["B_via"] = "outline+section×2(消歧)"
            rec["B_needs_outline"] = True
            rec["B_requires_extra_info"] = "需 near_line/path 才能消歧（模型必须先知道目标在第几处）"
        else:
            rec["B_min_calls"] = 2
            rec["B_via"] = "outline+section"
        rec["B_section_header"] = sec.text[:120]

    elif ttype == "T4_fulltext_count":
        # A：整篇读可数（若未截断）
        rec["A_solvable"] = not truncated
        rec["A_min_calls"] = 1
        # ★ 修正（2026-10-25）：B 臂不能窄化为"只用 outline+section"。
        #   真实 agent 有 grep 可用：grep(pattern=W) 返回命中数 + 前 N 处 ⇒ 能统计。
        #   若窄化 B 臂 ⇒ 必然得低分 ⇒ 构造成见偏向 A 臂（Lead 提醒的坑#3）。
        pat = task["answer"]["pattern"]
        g = tools["grep"].handler({"pattern": pat})
        # grep 输出含"命中"或"N 处"
        grep_ok = ("命中" in g.text or "处" in g.text) and "错误" not in g.text[:80]
        rec["B_solvable"] = bool(grep_ok)
        rec["B_min_calls"] = 1 if grep_ok else None
        rec["B_path"] = "grep(pattern) 一次统计" if grep_ok else "无可用路径"
        rec["B_via"] = "grep"
        rec["B_grep_head"] = g.text[:120]
        rec["B_needs_disambiguation"] = False
        # 同时记录「若只允许 section」的答案，用于诚实披露
        rec["B_if_section_only"] = False
        rec["B_if_section_only_why"] = "section 单次只返回一节，数全文需 outline+逐节 N 次调用"

    return rec


def run_once() -> dict:
    tasks = build_tasks()
    per_task = []
    for t in tasks:
        kb = os.path.join(REPO, t["kb"])
        tools = {x.name: x for x in build_kb_tools(kb, session_id="solvability")}
        per_task.append(judge(t, tools))
    return {"tasks": per_task}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--repeat", type=int, default=3)
    args = ap.parse_args()

    runs = [run_once() for _ in range(args.repeat)]

    # 稳定性：两次跑逐字节一致（除时间戳）
    sigs = [hashlib.sha256(json.dumps(r, ensure_ascii=False, sort_keys=True).encode()).hexdigest() for r in runs]
    stable = len(set(sigs)) == 1

    tasks = runs[0]["tasks"]
    by_type: dict[str, dict] = {}
    for t in tasks:
        d = by_type.setdefault(t["type"], {"n": 0, "A_ok": 0, "B_ok": 0})
        d["n"] += 1
        d["A_ok"] += 1 if t.get("A_solvable") else 0
        d["B_ok"] += 1 if t.get("B_solvable") else 0

    # 汇总
    n = len(tasks)
    a_ok = sum(1 for t in tasks if t.get("A_solvable"))
    b_ok = sum(1 for t in tasks if t.get("B_solvable"))
    b_disa = sum(1 for t in tasks if t.get("B_needs_disambiguation"))

    payload = {
        "schema": "completion-solvability/v1",
        "nature": "PROXY：不调用模型；机判「任务在该读面下是否结构可完成」。"
                  "**这是可完成性（solvability），不是完成率（completion rate）**",
        "why_not_A_level": "无 API key + 既有脚本全为 PROXY ⇒ 无法产真实完成率；"
                           "本报告降级为 B 级并明确标注",
        "sealed": {"MEMORIA_CONFIG_DIR": True, "repeats": args.repeat, "stable": stable, "sigs": sigs[:2]},
        "kb_dirs": [d for d in KB_DIRS if os.path.isdir(os.path.join(REPO, d))],
        "totals": {"n_tasks": n, "A_solvable": a_ok, "B_solvable": b_ok,
                   "A_rate": round(a_ok / n, 4) if n else None,
                   "B_rate": round(b_ok / n, 4) if n else None,
                   "B_needs_disambiguation": b_disa},
        "by_type": by_type,
        "per_task": tasks,
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    payload["artifactSha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    print(f"任务数: {n}  （重复 {args.repeat} 次，逐字节一致: {stable}）")
    print(f"  A（整篇）结构可完成: {a_ok}/{n} = {a_ok/n:.1%}" if n else "  无任务")
    print(f"  B（粒度）结构可完成: {b_ok}/{n} = {b_ok/n:.1%}" if n else "")
    print(f"  B 需要消歧的任务: {b_disa}/{n}")
    print()
    print("按类型：")
    for t, d in sorted(by_type.items()):
        print(f"  {t:26} n={d['n']}  A={d['A_ok']}  B={d['B_ok']}")
    print()
    print("⚠️ 这是「可完成性」不是「完成率」——见报告 naming 说明")
    print(f"sha256: {payload['artifactSha256'][:16]}…")

    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(REPO, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        print(f"wrote: {args.json}")
    return 0 if n else 1


if __name__ == "__main__":
    raise SystemExit(main())
