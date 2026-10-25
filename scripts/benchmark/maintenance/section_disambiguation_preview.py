#!/usr/bin/env python
"""R-S1B-5 / task-132：`AMBIGUOUS_SECTION` 候选加内容预览的必红 fixture（`section_disambiguation_preview`）。

## 缺陷（由 task-131 的完成率度量暴露，不是凭空冒出来的）
同名标题的两个候选**除 `line_no` 外完全相同**，`how_to_disambiguate` 让模型"传 near_line=<行号>"
⇒ 等于让模型**猜 3 还是 7**。所谓"可消歧"没给用于消歧的信息。

## 本夹具钉的是**全部消费者**（缺任何一层都只是"库层修了、模型看不到"）
- **库层** `section_index.resolve_section()`：候选带 `preview`，形状稳定，预算有界；
- **进程内工具层** `tools/kb.py` 的 `section` / `outline`：`ToolOutput.text` 是模型**唯一可见**通道；
- **MCP 跨进程层** `mcp_server.py` 的 `_tool_section` / `_tool_outline`：过去只拼 `L行号`（连父级都丢）；
- **写路径** `plan.py::replace_section`：同名歧义错误同样必须带 preview（改错节比读错节更贵）。
S1 的接缝缺陷正是"库层算了 preview、消费者只拼 L行号 ⇒ 模型看不到"。

## 断言（每条构造真实路径）
| 断言 | 构造 | 期望 |
|---|---|---|
| `candidates_have_distinct_preview` | 两个同名 `## 7. 总结`、正文不同 | 每个候选都带 `preview`，且两个 preview **不同** |
| `select_by_preview_then_resolve` | 按 preview 选中候选 → `near_line=<该 line_no>` | `section` 成功且正文含目标内容 |
| `empty_section_preview_is_empty_string` | 空节 | `preview == ""`（**字段不省略**） |
| `budget_10_candidates` | 10 个同名标题 | 返回 ≤4,000 tok，每个 preview ≤61 字符（截断） |
| `budget_cap_200_candidates` | 200 个同名标题 | 候选**截断到上限**并标注 `candidate_count/omitted_count`，载荷 ≤4,000 tok |
| `outline_dup_titles_carry_preview` | outline 同名标题 | 同名标题带 `preview`、唯一标题**不带** |
| `outline_preview_counts_into_budget` | 有/无 preview 两次渲染 | 含 preview 的 `tokens` **严格更大**（不是"没算进去"） |
| `tool_section_message_carries_preview` | 真实 `section` 工具 | 错误文本含两个候选 preview + `how_to_disambiguate` |
| `tool_section_near_line_hits_target` | 真实 `section` 工具 + near_line | 命中目标节正文 |
| `tool_outline_renders_preview` | 真实 `outline` 工具 | 同名行带 `∥ preview`，唯一标题行不带 |
| `tool_cap_message_states_omitted` | 真实 `section` 工具 + 200 同名 | 文本如实标注"共 200 个 / 其余 180 个未列出" |
| `mcp_*_carries_preview` | 真实 `McpServer.handle_message` tools/call | MCP 的 section/outline 文本同样带 preview |
| `plan_replace_section_error_carries_preview` | 真实 `preview_plan` 同名歧义 | 写路径错误文本带 preview（消歧信息一致） |
| **`red_preview_removed_no_discrimination`** | 把 `_section_preview` 换成恒 ""（模拟修复前） | 按 preview **选不中**（2 个候选全同）⇒ 必红 |
| **`red_old_tool_renderer_has_no_preview`** | 复刻修复前的工具文本拼法 | 旧拼法**不含**任何 preview ⇒ 证明接缝缺陷真实存在 |
| `c3_semantics_unchanged` | 仍多候选 | 仍报 `AMBIGUOUS_SECTION`，**绝不取首个** |

## 用法
    python scripts/benchmark/maintenance/section_disambiguation_preview.py [--json out.json]
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
os.environ.setdefault("MEMORIA_CONFIG_DIR", tempfile.mkdtemp(prefix="memoria-cfg-"))

# Windows 控制台默认 cp1252/GBK ⇒ 中文 print 会 UnicodeEncodeError，夹具自己先崩就等于没断言。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from memoria.services.agent import section_index as si  # noqa: E402
from memoria.services.agent.tools.kb import build_kb_tools  # noqa: E402

RESULTS: list[dict] = []

DUP_BODY = "# 标题\n\n## 7. 总结\n这是内容 A 的第一行。\n\n## 7. 总结\n这是内容 B 的第一行。\n"

# ── sha 只对**稳定事实**求值（task-132 夹具自身踩到的坑）────────────────────────
# MCP 路径的文本里带 `read_handle: rh-<随机>`；若原样进 detail，同一个 PASS 每次 sha 都不同
# ⇒ "连跑 3 次单一 sha" 永远不成立，而人会把"每次都绿"误当稳定。随机值必须先归一。
_HANDLE_RE = re.compile(r"rh-[A-Za-z0-9_-]{8,}")
_TMP_RE = re.compile(r"memoria[-_][A-Za-z0-9_-]{6,}")


def _stable(value):
    """把非确定性 token / 临时目录路径替换成占位符（递归）。"""
    if isinstance(value, str):
        return _TMP_RE.sub("<TMPDIR>", _HANDLE_RE.sub("<HANDLE>", value))
    if isinstance(value, dict):
        return {key: _stable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_stable(item) for item in value]
    return value


def check(name: str, ok: bool, detail, falsifier: str = "") -> None:
    RESULTS.append(
        {
            "name": name,
            "ok": bool(ok),
            "detail": _stable(str(detail)),
            "falsifier": _stable(str(falsifier)),
        }
    )


def _select_by_preview(candidates: list[dict], target_preview: str) -> list[dict]:
    """模拟模型"按 preview 辨认目标"的最小判别器：返回 preview 完全等于目标的候选。"""
    return [c for c in candidates if c.get("preview") == target_preview]


def _make_kb(files: dict[str, str]) -> str:
    root = tempfile.mkdtemp(prefix="memoria-s1b2-kb-")
    for rel, text in files.items():
        full = os.path.join(root, rel)
        os.makedirs(os.path.dirname(full) or root, exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(text)
    return root


def _tool(root: str, name: str):
    return {t.name: t for t in build_kb_tools(root)}[name]


def _call(root: str, name: str, **arguments) -> str:
    return _tool(root, name).handler(arguments).text


def _without_preview(fn):
    """模拟 task-132 修复前的库层状态：候选**没有任何可区分内容**（preview 恒 ""）。"""

    original = si._section_preview
    si._section_preview = lambda sec, max_chars=si.PREVIEW_MAX_CHARS: ""  # type: ignore[assignment]
    try:
        return fn()
    finally:
        si._section_preview = original  # type: ignore[assignment]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    body = DUP_BODY
    _sec, err = si.resolve_section(body, heading="7. 总结")
    assert err is not None and err.code == si.AMBIGUOUS_SECTION
    cands = err.extra["candidates"]

    # ── ① 库层：候选带可区分 preview ──
    check(
        "同名候选都带 preview 且两个 preview 不同（能区分）",
        len(cands) == 2
        and all("preview" in c for c in cands)
        and cands[0]["preview"] != cands[1]["preview"]
        and cands[0]["preview"] == "这是内容 A 的第一行。"
        and cands[1]["preview"] == "这是内容 B 的第一行。",
        json.dumps(cands, ensure_ascii=False),
        "preview 相同/缺失 ⇒ 消歧仍靠猜",
    )

    # ── ② 库层：凭 preview 唯一选中 → near_line 定位成功 ──
    target = "这是内容 A 的第一行。"
    picked = _select_by_preview(cands, target)
    check(
        "凭 preview 能唯一选中候选（不是猜）",
        len(picked) == 1 and picked[0]["line_no"] == 3,
        f"picked={[c['line_no'] for c in picked]}",
        "按 preview 选不唯一 ⇒ preview 不构成消歧信息",
    )
    sec_ok, err2 = si.resolve_section(body, heading="7. 总结", near_line=picked[0]["line_no"])
    check(
        "选中后 near_line 定位成功且内容正确",
        sec_ok is not None and "内容 A" in sec_ok.text,
        f"text={(sec_ok.text if sec_ok else '')[:60]}",
    )

    # ── ③ 必红（库层）：去掉 preview 信息 ⇒ 按 preview 选不中 ──
    def _red_lib() -> tuple[list[dict], list[dict]]:
        _s, e = si.resolve_section(body, heading="7. 总结")
        assert e is not None
        stripped = e.extra["candidates"]
        return stripped, _select_by_preview(stripped, target)

    red_cands, picked_stripped = _without_preview(_red_lib)
    check(
        "必红（库层）：preview 信息缺失 ⇒ 凭 preview 选中不唯一（2 个候选全同）",
        all(c.get("preview") == "" for c in red_cands) and len(picked_stripped) != 1,
        f"previews={[c.get('preview') for c in red_cands]}, picked={[c['line_no'] for c in picked_stripped]}",
        "去掉 preview 仍能唯一选 ⇒ preview 是装饰，消歧其实不靠它",
    )

    # ── ④ 空节 ⇒ preview == ""（字段不省略） ──
    empty = "# 甲\n\n## 空节\n\n## 空节\n\n## 尾\n"
    _s2, e2 = si.resolve_section(empty, heading="空节")
    ecands = e2.extra["candidates"] if e2 else []
    check(
        "空节 ⇒ preview 为空字符串（字段不省略，形状稳定）",
        all(c.get("preview") == "" for c in ecands) and len(ecands) == 2,
        json.dumps(ecands, ensure_ascii=False),
        "字段被省略 ⇒ 形状不稳定（又一次'声明≠事实'）",
    )

    # ── ⑤ 预算：10 个同名标题 ──
    big = "# 大\n"
    for i in range(10):
        big += f"\n## 总结\n这是第 {i} 节的正文，足够长的一句话，用来验证预览截断逻辑正常工作。\n"
    _s3, e3 = si.resolve_section(big, heading="总结")
    bcands = e3.extra["candidates"] if e3 else []
    payload_tokens = si.estimate_tokens(json.dumps(bcands, ensure_ascii=False))
    check(
        "预算不爆：10 个同名候选 ⇒ 每个 preview ≤61 字符且 payload ≤4,000 tok",
        len(bcands) == 10
        and all(len(c.get("preview") or "") <= si.PREVIEW_MAX_CHARS + 1 for c in bcands)
        and payload_tokens <= 4000,
        f"candidates={len(bcands)}, payload_tokens={payload_tokens}",
        "超预算 ⇒ preview 截断逻辑失效",
    )

    # ── ⑥ 预算硬上限：200 个同名候选必须截断并标注 ──
    huge = "# 巨\n"
    for i in range(200):
        huge += f"\n## 同名\n第 {i} 节正文。\n"
    _s4, e4 = si.resolve_section(huge, heading="同名")
    hcands = (e4.extra.get("candidates") if e4 else []) or []
    h_extra_tokens = si.estimate_tokens(json.dumps(e4.extra if e4 else {}, ensure_ascii=False))
    check(
        "预算硬上限：200 个同名候选 ⇒ 截断到上限并标注 candidate_count/omitted_count，载荷 ≤4,000 tok",
        len(hcands) == si.AMBIGUOUS_MAX_CANDIDATES
        and e4 is not None
        and e4.extra.get("candidate_count") == 200
        and e4.extra.get("candidates_truncated") is True
        and e4.extra.get("omitted_count") == 200 - si.AMBIGUOUS_MAX_CANDIDATES
        and h_extra_tokens <= 4000,
        f"shown={len(hcands)}, count={e4.extra.get('candidate_count') if e4 else None}, "
        f"truncated={e4.extra.get('candidates_truncated') if e4 else None}, tokens={h_extra_tokens}",
        "候选无上限 ⇒ 载荷随同名数线性膨胀直到爆预算",
    )

    # ── ⑦ outline（库层）：同名带 preview、唯一不带；且 preview 计入预算 ──
    outline = si.build_outline(body)
    nodes = {n["title"]: n for n in outline["headings"]}
    check(
        "outline：同名标题带 preview、唯一标题不带（省预算且计入 budget）",
        "preview" in nodes["7. 总结"] and "preview" not in nodes["标题"],
        f"同名预览={nodes['7. 总结'].get('preview')!r}, 唯一标题keys={sorted(nodes['标题'].keys())}",
        "同名不带 preview ⇒ outline 里同名标题同样只能靠行号猜",
    )
    outline_no_preview = _without_preview(lambda: si.build_outline(body))
    check(
        "outline：preview **计入** OUTLINE 预算（不是'没算进去'）",
        si.estimate_tokens(json.dumps(outline_no_preview["headings"], ensure_ascii=False))
        < si.estimate_tokens(json.dumps(outline["headings"], ensure_ascii=False))
        and outline_no_preview["tokens"] < outline["tokens"],
        f"tokens with={outline['tokens']}, without={outline_no_preview['tokens']}",
        "两次 token 相等 ⇒ preview 被漏算进预算",
    )

    # ── ⑧ 工具层（模型唯一可见通道）：section 错误文本必须带 preview ──
    root = _make_kb({"dup.md": body})
    section_text = _call(root, "section", file="dup.md", heading="7. 总结")
    check(
        "工具层 section：AMBIGUOUS 文本带每个候选的 preview（模型能看到）",
        section_text.startswith("Error: ")
        and "(AMBIGUOUS_SECTION)" in section_text
        and "这是内容 A 的第一行。" in section_text
        and "这是内容 B 的第一行。" in section_text
        and "near_line" in section_text,
        section_text.replace("\n", " ⏎ ")[:400],
        "工具文本不带 preview ⇒ 模型仍只能猜（库层修了等于没修）",
    )

    near = _call(root, "section", file="dup.md", heading="7. 总结", near_line=7)
    check(
        "工具层 section：凭 preview 选中后按 near_line（内容行）命中内容 B",
        "内容 B 的第一行" in near and "内容 A" not in near,
        near.replace("\n", " ⏎ ")[:200],
        "near_line 命中错节 ⇒ 消歧链路断裂",
    )

    # ── ⑨ 必红（工具层）：复刻修复前的渲染拼法 ⇒ 无任何 preview ──
    old_render = "；候选=" + ", ".join(
        f"L{c['line_no']}[{'/'.join(c['parent_path']) or '根'}]" for c in cands
    )
    check(
        "必红（工具层）：修复前的渲染复刻不含 preview ⇒ 接缝缺陷真实存在",
        "这是内容 A" not in old_render and "这是内容 B" not in old_render,
        f"旧拼法={old_render}",
        "旧拼法已含 preview ⇒ 本接缝修复是多余的",
    )

    def _red_tool() -> tuple[str, list[dict]]:
        text = _call(root, "section", file="dup.md", heading="7. 总结")
        _s, e = si.resolve_section(body, heading="7. 总结")
        assert e is not None
        return text, e.extra["candidates"]

    red_tool_text, red_tool_cands = _without_preview(_red_tool)
    check(
        "必红（工具层）：preview 信息缺失 ⇒ 工具文本不含可区分内容，按 preview 选不中",
        "这是内容 A" not in red_tool_text
        and "这是内容 B" not in red_tool_text
        and len(_select_by_preview(red_tool_cands, target)) != 1,
        red_tool_text.replace("\n", " ⏎ ")[:300],
        "信息缺失仍能消歧 ⇒ preview 不必要",
    )

    # ── ⑩ 工具层 outline：同名行带 ∥ preview，唯一标题行不带 ──
    outline_text = _call(root, "outline", file="dup.md")
    dup_rows = [row for row in outline_text.splitlines() if "7. 总结" in row]
    title_row = [row for row in outline_text.splitlines() if row.strip().startswith("标题")]
    check(
        "工具层 outline：同名标题行带 ∥ preview，唯一标题行不带",
        len(dup_rows) == 2
        and "∥ 这是内容 A 的第一行。" in dup_rows[0]
        and "∥ 这是内容 B 的第一行。" in dup_rows[1]
        and len(title_row) == 1
        and "∥" not in title_row[0],
        f"dup_rows={dup_rows}, title_row={title_row}",
        "outline 工具不渲染 preview ⇒ 同名节在概要层仍只能靠行号猜",
    )

    # ── ⑪ 工具层：200 候选时如实标注省略数 ──
    huge_root = _make_kb({"huge.md": huge})
    huge_text = _call(huge_root, "section", file="huge.md", heading="同名")
    check(
        "工具层 section：候选截断时如实标注『共 200 个 / 其余 180 个未列出』",
        "共 200 个候选" in huge_text and "其余 180 个未列出" in huge_text,
        huge_text.replace("\n", " ⏎ ")[:400],
        "截断却不标注 ⇒ 候选列表变成不完整的事实声明",
    )

    # ── ⑫ 第二个消费者：MCP 路径（`mcp_server.py`）同样必须带 preview ──
    from memoria.services.agent.mcp_server import PROTOCOL_VERSION, McpServer  # noqa: E402

    mcp_meta = {
        "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
        "io.modelcontextprotocol/clientCapabilities": {},
    }

    def _mcp_call(server: McpServer, name: str, arguments: dict) -> str:
        reply = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": "x",
                "method": "tools/call",
                "params": {"_meta": mcp_meta, "name": name, "arguments": arguments},
            }
        )
        result = (reply or {}).get("result") or {}
        return "".join(
            str(block.get("text") or "")
            for block in (result.get("content") or [])
            if isinstance(block, dict)
        )

    mcp_server = McpServer(root)
    mcp_section_text = _mcp_call(mcp_server, "section", {"file": "dup.md", "heading": "7. 总结"})
    check(
        "MCP 路径 section：AMBIGUOUS 文本带每个候选的 preview（跨进程同样能消歧）",
        "AMBIGUOUS_SECTION" in mcp_section_text
        and "这是内容 A 的第一行。" in mcp_section_text
        and "这是内容 B 的第一行。" in mcp_section_text
        and "near_line" in mcp_section_text,
        mcp_section_text.replace("\n", " ⏎ ")[:400],
        "MCP 文本不带 preview ⇒ 跨进程调用仍只能猜（第二个消费者漏修）",
    )
    mcp_outline_text = _mcp_call(mcp_server, "outline", {"file": "dup.md"})
    check(
        "MCP 路径 outline：同名标题行带 ∥ preview",
        "∥ 这是内容 A 的第一行。" in mcp_outline_text
        and "∥ 这是内容 B 的第一行。" in mcp_outline_text,
        mcp_outline_text.replace("\n", " ⏎ ")[:300],
        "MCP outline 不渲染 preview ⇒ 跨进程概要层仍只能靠行号猜",
    )

    def _red_mcp() -> str:
        return _mcp_call(McpServer(root), "section", {"file": "dup.md", "heading": "7. 总结"})

    red_mcp_text = _without_preview(_red_mcp)
    check(
        "必红（MCP 路径）：preview 信息缺失 ⇒ MCP 文本不含可区分内容",
        "这是内容 A" not in red_mcp_text and "这是内容 B" not in red_mcp_text,
        red_mcp_text.replace("\n", " ⏎ ")[:300],
        "信息缺失仍有 preview ⇒ 本修复不必要",
    )

    # ── ⑬ 第三个消费者：写路径 `replace_section`（`plan.py`）──
    from memoria.services.agent.plan import OP_REPLACE_SECTION, preview_plan  # noqa: E402

    def _plan() -> dict:
        return {
            "v": 1,
            "intent": "s1b2 disambiguation preview 验收",
            "txid": "20260101T000000Z-01",
            "ops": [
                {
                    "op": OP_REPLACE_SECTION,
                    "op_id": "s1",
                    "file": "dup.md",
                    "heading": "7. 总结",
                    "text": "改写后的正文。\n",
                }
            ],
        }

    pv = preview_plan(root, _plan())
    plan_errs = pv.get("errors") or []
    plan_blob = json.dumps(plan_errs, ensure_ascii=False)
    check(
        "写路径 replace_section：同名歧义错误带 preview（改错节比读错节更贵）",
        any(str(e.get("code")) == "ambiguous_section" for e in plan_errs)
        and "这是内容 A 的第一行。" in plan_blob
        and "这是内容 B 的第一行。" in plan_blob,
        plan_blob[:600],
        "写路径歧义错误不带 preview ⇒ 模型只能猜着改具体哪一节",
    )

    red_plan_blob = _without_preview(lambda: json.dumps(preview_plan(root, _plan()).get("errors") or [], ensure_ascii=False))
    check(
        "必红（写路径）：preview 信息缺失 ⇒ 写路径错误文本不含可区分内容",
        "这是内容 A" not in red_plan_blob and "这是内容 B" not in red_plan_blob,
        red_plan_blob[:600],
        "信息缺失仍有 preview ⇒ 写路径修复不必要",
    )

    # ── ⑭ C3 语义未改 ──
    check(
        "C3 语义未改：仍报 AMBIGUOUS_SECTION，绝不取首个",
        err is not None and err.code == si.AMBIGUOUS_SECTION and not isinstance(err, si.Section),
        f"code={err.code if err else None}",
        "静默取首个 ⇒ C3 被破坏",
    )

    payload = {
        "schema": "section-disambiguation-preview/v2",
        "defect_origin": "task-131 完成率度量暴露：同名候选除 line_no 外完全相同，near_line 提示等于让模型猜",
        "seam_defect": "库层 section_index 已有 preview，但 tools/kb.py 只渲染 L行号 ⇒ 模型唯一可见通道看不到 preview",
        "preview_max_chars": si.PREVIEW_MAX_CHARS,
        "ambiguous_max_candidates": si.AMBIGUOUS_MAX_CANDIDATES,
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
