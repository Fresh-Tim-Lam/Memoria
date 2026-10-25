#!/usr/bin/env python
"""S5（task-124）夹具：调用级 trace 成本 / 容量淘汰 / 派生索引 / MCP `_meta` OTel 透传。

## 它证明什么（每条都构造真实路径，不用"字符串里出现某词"冒充）

| 断言 | 构造 | 期望 |
|---|---|---|
| `real_session_has_all_cost_fields` | 真实 `ask()` 一轮 4 次工具调用 | 每个 `trace/call` 带全部成本字段 |
| `privacy_preview_only_first_256` | 正文秘密标记放在第 256 字符之后 | trace 条目与索引**都不含**该标记；`result_preview == 正文[:256]` |
| `truncated_flag_is_truthful` | `section(max_tokens=120)` 强制切片 | `truncated=true` 且 `truncated_known=true` |
| `error_entry_has_code` | 读不存在的文件 | `error_code=NOT_FOUND` |
| `write_entry_has_write_block` | 真实 `propose_write` 改一行 | `write{files,±lines,backup_txid,undo_available}` + `plan_txid` |
| `aggregate_matches_raw_entries` | 从索引原始条目逐项重算 | 与 `aggregate_cost()` **误差 0** |
| `index_is_rebuildable_cache` | 删除整个 trace 目录后重建 | 条目字节 sha 一致；`rebuilt=True`；≤5s/会话 |
| `capacity_6000` | 6000 条（5900 普通 + 50 写 + 50 错误） | 淘汰后 ==5000；写/错误条目 **100% 保留** |
| `entry_size_cap_2kb` | 200 个写文件的写条目 | 单条 ≤2048 字节，且 `files_total/files_truncated` 如实标注 |
| `mcp_otel_roundtrip` | `McpServer.handle_message` 带 traceparent/tracestate/baggage | 响应 `_meta` 回执同值；`trace/call.transport=mcp` 带 otel |
| `cross_boundary_same_trace` | MCP 写调用（同一 traceparent） | MCP 侧 `trace/call` 与进程内 `capability/apply` **同 trace_id** |
| `trace_cost_summary_tool` | 真实工具包装 | 文本含调用数/截断率/失败率 |

## 用法
    python scripts/benchmark/maintenance/trace_cost_s5.py [--json out.json]
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

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from memoria.services.agent import compaction, trace_index as tr  # noqa: E402
from memoria.services.agent.ask import ask  # noqa: E402
from memoria.services.agent.llm import (  # noqa: E402
    FinishEvent,
    FinishReason,
    LlmRequest,
    TextDelta,
    ToolCall,
    Usage,
    UsageEvent,
)
from memoria.services.agent.mcp_server import PROTOCOL_VERSION, McpServer  # noqa: E402
from memoria.services.agent.section_index import estimate_tokens  # noqa: E402
from memoria.services.agent.session.store import SessionStore, read_session  # noqa: E402
from memoria.services.agent.tools import build_kb_tools  # noqa: E402

RESULTS: list[dict] = []
_SECRET = "SECRET-MARKER-9F3A"
_HANDLE_RE = re.compile(r"rh-[A-Za-z0-9_-]{8,}")
_TXID_RE = re.compile(r"\d{8}T\d{6}Z-\d{2,}")
_TMP_RE = re.compile(r"memoria[-_][A-Za-z0-9_-]{6,}")


_VOLATILE_KEYS = frozenset({"ts", "duration_ms", "elapsed_ms", "rebuilt_at"})
_VOLATILE_FIELD_RE = re.compile(
    r"""(["'])(ts|duration_ms|elapsed_ms|rebuilt_at)\1\s*:\s*[0-9]+"""
)


def _stable(value):
    """非确定性值（handle / txid / 时间戳 / 耗时 / 临时目录）归一，保证产物单一 sha。"""
    if isinstance(value, str):
        text = _HANDLE_RE.sub("<HANDLE>", value)
        text = _TXID_RE.sub("<TXID>", text)
        text = _VOLATILE_FIELD_RE.sub(lambda m: f'{m.group(1)}{m.group(2)}{m.group(1)}: "<T>"', text)
        return _TMP_RE.sub("<TMPDIR>", text)
    if isinstance(value, dict):
        return {
            str(key): ("<T>" if str(key) in _VOLATILE_KEYS else _stable(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_stable(item) for item in value]
    return value


def check(name: str, ok: bool, detail, falsifier: str = "") -> None:
    RESULTS.append(
        {
            "name": name,
            "ok": bool(ok),
            "detail": str(_stable(detail))[:1200],
            "falsifier": str(_stable(falsifier)),
        }
    )


# ── 假 provider（真实 loop 路径；脚本化两轮）──────────────────────────────────
class FakeProvider:
    name = "fake"

    def __init__(self, script) -> None:
        self.script = [list(step) for step in script]
        self.requests: list[LlmRequest] = []

    def stream(self, request: LlmRequest):
        self.requests.append(request)
        step = self.script.pop(0) if self.script else [
            TextDelta("（脚本耗尽）"),
            FinishEvent(reason=FinishReason.STOP),
        ]
        yield from step


def tool_step(*calls: ToolCall) -> list:
    return [FinishEvent(reason=FinishReason.TOOL_CALLS, tool_calls=calls)]


def text_step(text: str) -> list:
    return [
        TextDelta(text),
        UsageEvent(Usage(prompt_tokens=10, completion_tokens=5)),
        FinishEvent(reason=FinishReason.STOP),
    ]


def _mk_kb(files: dict[str, str]) -> str:
    root = tempfile.mkdtemp(prefix="memoria-s5-kb-")
    for rel, text in files.items():
        full = os.path.join(root, rel)
        os.makedirs(os.path.dirname(full) or root, exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    return root


def _long_doc() -> str:
    # 设计（隐私判据需要）：目标节正文 >500 字符，且 `_SECRET` 落在**结果内容第 256 字符之后**；
    # 同时其它节足够长，使目标节占比 <50% ⇒ 不触发 `whole_document` 回退（否则"首 256"会包含秘密）。
    long_body = "填充文本用于把关键信息推到第 256 字符之后。" * 18
    tail_section = "尾节填充。" * 220
    return (
        "# 长文档\n\n## 短节\n\n短节正文。\n\n## 长节\n\n"
        + long_body
        + _SECRET
        + "出现在很后面。"
        + "尾部正文。" * 30
        + "\n\n## 尾节\n\n"
        + tail_section
        + "\n"
    )


def _mcp_call(server: McpServer, name: str, arguments: dict, *, otel: dict | None = None) -> dict:
    meta = {
        "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
        "io.modelcontextprotocol/clientCapabilities": {},
    }
    if otel:
        meta.update(otel)
    reply = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": "x",
            "method": "tools/call",
            "params": {"_meta": meta, "name": name, "arguments": arguments},
        }
    )
    return reply or {}


def _mcp_text(result: dict) -> str:
    return "".join(
        str(block.get("text") or "")
        for block in (result.get("result", {}).get("content") or [])
        if isinstance(block, dict)
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    kb = _mk_kb(
        {
            "long.md": _long_doc(),
            "w.md": "第一行\n第二行\n",
            "w2.md": "甲行\n乙行\n",
        }
    )
    sid = "s5-fixture"  # 固定 id：产物 sha 不随随机 id 漂移（真实生产仍用 new_session_id）

    # ── 构造真实的一轮：4 次工具调用 ──────────────────────────────────────
    section_args = json.dumps({"file": "long.md", "heading": "长节"}, ensure_ascii=False)
    trunc_args = json.dumps({"file": "long.md", "heading": "长节", "max_tokens": 200}, ensure_ascii=False)
    missing_args = json.dumps({"path": "nope.md"}, ensure_ascii=False)
    write_args = json.dumps(
        {
            "intent": "S5 写回执",
            "ops": [
                {
                    "op": "replace_lines",
                    "op_id": "o1",
                    "file": "w.md",
                    "range": {"start": {"line": 2}, "end": {"line": 2}},
                    "expect": "第二行",
                    "text": "改后的第二行",
                }
            ],
        },
        ensure_ascii=False,
    )
    provider = FakeProvider(
        [
            tool_step(
                ToolCall(id="c1", name="section", arguments=section_args),
                ToolCall(id="c2", name="section", arguments=trunc_args),
                ToolCall(id="c3", name="read_document", arguments=missing_args),
                ToolCall(id="c4", name="read_document", arguments=json.dumps({"path": "w.md"})),
                ToolCall(id="c5", name="propose_write", arguments=write_args),
            ),
            text_step("完成。"),
        ]
    )
    ask(str(kb), "做一次 S5 采样", provider=provider, session_id=sid)

    records = read_session(str(kb), sid)
    traces = [row["data"] for row in records if row["type"] == tr.EVENT_TRACE_CALL]
    results = [row["data"] for row in records if row["type"] == "tool/result"]
    tool_results_by_id = {row.get("id"): row for row in results}

    # ── A. 字段完整性 ────────────────────────────────────────────────────
    by_id = {index: entry for index, entry in enumerate(traces)}
    check(
        "真实会话：每次工具调用都落一条 trace/call（5 次调用 → 5 条）",
        len(traces) == 5 and len(results) == 5,
        f"traces={len(traces)}, tool_results={len(results)}",
        "条数不匹配 ⇒ 成本记录漏调用",
    )
    required = {
        "ts", "tool_id", "turn", "args_digest", "result_chars", "result_digest", "result_preview",
        "est_tokens", "truncated", "truncated_known", "approval", "error_code", "write", "transport",
    }
    first = traces[0]
    first_result = tool_results_by_id.get("c1") or {}
    check(
        "成本字段齐全且口径正确（长度/digest/tokens/审批/turn/session_id）",
        required <= set(first)
        and first["session_id"] == sid
        and first["tool_id"] == "section"
        and first["turn"] == 1
        and first["transport"] == "inprocess"
        and isinstance(first["ts"], int)
        and re.fullmatch(r"[0-9a-f]{16}", str(first["args_digest"])) is not None
        and re.fullmatch(r"[0-9a-f]{16}", str(first["result_digest"])) is not None
        and first["result_chars"] == len(str(first_result.get("content") or ""))
        and first["result_digest"] == hashlib.sha256(str(first_result.get("content") or "").encode()).hexdigest()[:16]
        and first["result_preview"] == str(first_result.get("content") or "")[: tr.RESULT_PREVIEW_CHARS]
        and first["est_tokens"] == estimate_tokens(str(first_result.get("content") or ""))
        and first["approval"].get("asked") is True
        and first["approval"].get("decided") == "allowed-once",
        json.dumps(first, ensure_ascii=False, sort_keys=True)[:800],
        "字段缺失/口径不一致 ⇒ 成本不可复算",
    )

    # ── B. 隐私边界：正文只留首 256 字符 ────────────────────────────────
    full_result = str((tool_results_by_id.get("c1") or {}).get("content") or "")
    privacy_ok = (
        _SECRET in full_result  # 工具结果全文确实含敏感标记
        and len(full_result) > tr.RESULT_PREVIEW_CHARS
        and all(_SECRET not in json.dumps(entry, ensure_ascii=False) for entry in traces)
        and first["result_preview"] == full_result[: tr.RESULT_PREVIEW_CHARS]
        and "content" not in first  # trace 不得复制全文
    )
    check(
        "隐私硬边界：trace 条目不含正文全文，只留首 256 字符 + digest + 长度（有真实秘密标记做判据）",
        privacy_ok,
        f"content_len={len(full_result)}, secret_in_result={_SECRET in full_result}, "
        f"preview_len={len(first['result_preview'])}",
        "trace 里出现第 256 字符之后的正文 ⇒ 隐私边界是假的",
    )

    # ── C. 截断 / 错误 / 写回执 三个语义标志 ─────────────────────────────
    trunc_entry = traces[1]
    check(
        "截断标志真实：强制切片 ⇒ truncated=true 且 truncated_known=true",
        trunc_entry["truncated"] is True and trunc_entry["truncated_known"] is True,
        f"truncated={trunc_entry['truncated']}, known={trunc_entry['truncated_known']}",
        "切片了却报未截断 ⇒ 聚合截断率失真",
    )
    error_entry = traces[2]
    check(
        "错误条目：error_code=NOT_FOUND（并因此受容量保护）",
        error_entry["error_code"] == "NOT_FOUND" and error_entry["truncated"] is False,
        f"error_code={error_entry['error_code']}",
        "错误码丢失 ⇒ 失败率无法统计",
    )
    write_entry = traces[4]
    write_block = write_entry.get("write") or {}
    write_display = {key: write_entry.get(key) for key in ("tool_id", "approval", "write", "plan_txid")}
    check(
        "写回执块：files/±lines/backup_txid/undo_available + plan_txid",
        write_entry["tool_id"] == "propose_write"
        and write_block.get("files") == ["w.md"]
        and int(write_block.get("lines_added") or 0) == 1
        and int(write_block.get("lines_removed") or 0) == 1
        and bool(write_block.get("backup_txid"))
        and write_block.get("undo_available") is True
        and bool(write_entry.get("plan_txid")),
        json.dumps(write_display, ensure_ascii=False, sort_keys=True)[:800],
        "写回执缺失 ⇒ 无法回答'这次改了哪批/能不能撤销'",
    )

    # ── D. 聚合数字与索引原始条目逐项复算一致（误差 0）──────────────────
    summary = tr.aggregate_cost(kb, {"session_id": sid})
    entries = tr.read_index_entries(kb, sid)
    recomputed = {
        "calls": len(entries),
        "result_chars": sum(int(e.get("result_chars") or 0) for e in entries),
        "est_tokens": sum(int(e.get("est_tokens") or 0) for e in entries),
        "truncated_count": sum(1 for e in entries if e.get("truncated_known") and e.get("truncated")),
        "truncated_known": sum(1 for e in entries if e.get("truncated_known")),
        "error_count": sum(1 for e in entries if e.get("error_code")),
        "approval_asked": sum(1 for e in entries if (e.get("approval") or {}).get("asked")),
        "approval_denied": sum(
            1
            for e in entries
            if (e.get("approval") or {}).get("asked")
            and str((e.get("approval") or {}).get("decided")) != "allowed-once"
        ),
        "write_calls": sum(1 for e in entries if e.get("write")),
    }
    check(
        "聚合数字与索引原始条目逐项复算一致（误差 0）",
        summary["calls"] == recomputed["calls"]
        and summary["result_chars"] == recomputed["result_chars"]
        and summary["est_tokens"] == recomputed["est_tokens"]
        and summary["truncated"]["count"] == recomputed["truncated_count"]
        and summary["truncated"]["known"] == recomputed["truncated_known"]
        and summary["errors"]["count"] == recomputed["error_count"]
        and summary["approval"]["asked"] == recomputed["approval_asked"]
        and summary["approval"]["denied"] == recomputed["approval_denied"]
        and summary["write"]["calls"] == recomputed["write_calls"],
        f"summary={json.dumps({k: summary[k] for k in ('calls','result_chars','est_tokens','errors','approval','write')}, ensure_ascii=False, sort_keys=True)}; recomputed={json.dumps(recomputed, sort_keys=True)}",
        "聚合与原始条目不一致 ⇒ 报告数字不可信",
    )
    expected_trunc_rate = (
        round(recomputed["truncated_count"] / recomputed["truncated_known"], 6)
        if recomputed["truncated_known"]
        else None
    )
    expected_err_rate = round(recomputed["error_count"] / recomputed["calls"], 6) if recomputed["calls"] else None
    check(
        "聚合失败率/截断率分母口径正确（截断只对 known 计；失败率对全部调用计）",
        recomputed["truncated_known"] < recomputed["calls"]
        and summary["truncated"]["rate"] == expected_trunc_rate
        and summary["errors"]["rate"] == expected_err_rate
        and summary["truncated"]["unknown"] == recomputed["calls"] - recomputed["truncated_known"],
        f"calls={summary['calls']}, known={summary['truncated']['known']}, "
        f"trunc_rate={summary['truncated']['rate']} (expect {expected_trunc_rate}), "
        f"err_rate={summary['errors']['rate']} (expect {expected_err_rate})",
        "把'未声明'算进截断分母 ⇒ 截断率被稀释",
    )

    # ── E. 派生索引是 cache：删掉可重建、字节确定、≤5s ────────────────
    shard = tr.index_path(kb, sid)
    first_entries_blob = b"".join(
        line for line in open(shard, "rb").read().splitlines(keepends=True)[1:]
    )
    first_sha = hashlib.sha256(first_entries_blob).hexdigest()
    import shutil

    shutil.rmtree(os.path.join(kb, ".memoria", "agent", "trace"))
    check(
        "索引可删（cache 语义）：删除 trace/ 目录后 aggregate 仍能出数",
        not os.path.isdir(os.path.join(kb, ".memoria", "agent", "trace")),
        f"trace_dir_exists={os.path.isdir(os.path.join(kb, '.memoria', 'agent', 'trace'))}",
        "trace dir 未删掉 ⇒ 删除后重建这一步没被真正验证",
    )
    rebuilt = tr.aggregate_cost(kb, {"session_id": sid})
    rebuilt_info = rebuilt["index"]["shards"][0]
    rebuilt_blob = b"".join(line for line in open(shard, "rb").read().splitlines(keepends=True)[1:])
    check(
        "索引重建：从会话 JSONL 重建同一条目序列（字节 sha 一致）且耗时 ≤5s/会话",
        rebuilt["calls"] == summary["calls"]
        and hashlib.sha256(rebuilt_blob).hexdigest() == first_sha
        and rebuilt_info["rebuilt"] is True
        and rebuilt_info["elapsed_ms"] <= int(tr.REBUILD_BUDGET_S * 1000)
        and rebuilt_info["degraded"] is False,
        f"rebuilt={rebuilt_info}, calls={rebuilt['calls']}, sha_same={hashlib.sha256(rebuilt_blob).hexdigest() == first_sha}",
        "重建结果与首次不一致/超预算 ⇒ '可重建 cache' 是空话",
    )

    # ── F. 容量：6000 条 → ≤5000，写路径/错误 100% 保留 ─────────────────
    cap_sid = "s5-cap-6000"
    store = SessionStore(kb, cap_sid)
    for index in range(5900):
        store.append(
            tr.EVENT_TRACE_CALL,
            tr.build_entry(
                tool_id="section",
                turn=0,
                arguments={"file": "long.md", "i": index},
                content="普通条目" * 5,
                truncated=False,
                now_ms=1_000_000 + index,
            ),
        )
    for index in range(50):
        store.append(
            tr.EVENT_TRACE_CALL,
            tr.build_entry(
                tool_id="propose_write",
                turn=0,
                arguments={"i": index},
                content="写条目",
                meta={
                    "plan_txid": f"20260101T000000Z-{index:02d}",
                    "write": {
                        "files": [f"f{index}.md"],
                        "lines_added": 1,
                        "lines_removed": 0,
                        "backup_txid": f"20260101T000000Z-{index:02d}",
                        "undo_available": True,
                    },
                },
                now_ms=2_000_000 + index,
            ),
        )
    for index in range(50):
        store.append(
            tr.EVENT_TRACE_CALL,
            tr.build_entry(
                tool_id="read_document",
                turn=0,
                arguments={"i": index},
                content="错误条目",
                error_code="NOT_FOUND",
                now_ms=3_000_000 + index,
            ),
        )
    store.flush()
    cap_info = tr.rebuild_index(kb, cap_sid)
    cap_entries = tr.read_index_entries(kb, cap_sid)
    kept_write = [e for e in cap_entries if e.get("tool_id") == "propose_write"]
    kept_error = [e for e in cap_entries if e.get("error_code") == "NOT_FOUND"]
    sizes = [len(json.dumps(e, ensure_ascii=False).encode("utf-8")) for e in cap_entries]
    check(
        "容量：6000 条 ⇒ 淘汰后 ≤5000，且写路径 50 条与错误 50 条 100% 保留",
        len(cap_entries) == tr.MAX_ENTRIES_PER_SESSION
        and cap_info["dropped"] == 1000
        and len(kept_write) == 50
        and len(kept_error) == 50
        and cap_info["over_capacity"] is False,
        f"entries={len(cap_entries)}, dropped={cap_info['dropped']}, write={len(kept_write)}, error={len(kept_error)}",
        "写/错误条目被淘汰 ⇒ 审计线索丢失",
    )
    check(
        "容量：每条索引条目 ≤2KB（硬上限，被保护条目同样受限）",
        max(sizes) <= tr.MAX_ENTRY_BYTES,
        f"max_entry_bytes={max(sizes)}, cap={tr.MAX_ENTRY_BYTES}",
        "条目可无限大 ⇒ 索引体积失控",
    )
    oversized = tr.apply_capacity(
        [
            tr.build_entry(
                tool_id="propose_write",
                turn=0,
                arguments={},
                content="x",
                meta={
                    "plan_txid": "20260101T000000Z-99",
                    "write": {
                        "files": [f"very-long-directory-name/{index:03d}-{'y' * 30}.md" for index in range(200)],
                        "lines_added": 1,
                        "lines_removed": 0,
                        "backup_txid": "20260101T000000Z-99",
                        "undo_available": True,
                    },
                },
            )
        ]
    )[0][0]
    oversized_bytes = len(json.dumps(oversized, ensure_ascii=False).encode("utf-8"))
    check(
        "单条 ≤2KB：200 文件写条目被压缩且如实标注 files_total/files_truncated",
        oversized_bytes <= tr.MAX_ENTRY_BYTES
        and (oversized.get("write") or {}).get("files_truncated") is True
        and (oversized.get("write") or {}).get("files_total") == 200,
        f"bytes={oversized_bytes}, files={len((oversized.get('write') or {}).get('files') or [])}, "
        f"total={(oversized.get('write') or {}).get('files_total')}",
        "截断写回执却不标注 ⇒ 又一次'声明≠事实'",
    )

    # ── G. MCP `_meta` OTel 透传 + 跨边界同一 trace_id ──────────────────
    tp = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    otel = {
        "traceparent": tp,
        "tracestate": "memoria=test",
        "baggage": "tenant=kb,phase=s5",
    }
    server = McpServer(kb)
    outline_result = _mcp_call(server, "outline", {"file": "w2.md"}, otel=otel)
    outline_meta = (outline_result.get("result") or {}).get("_meta") or {}
    check(
        "MCP OTel 透传：响应 `_meta` 回执同一 traceparent/tracestate/baggage",
        outline_meta.get("traceparent") == tp
        and outline_meta.get("tracestate") == "memoria=test"
        and outline_meta.get("baggage") == "tenant=kb,phase=s5",
        json.dumps(outline_meta, ensure_ascii=False, sort_keys=True),
        "响应不回执 OTel 头 ⇒ 透传只做了一半",
    )
    handle = ""
    for token in re.findall(r"rh-[A-Za-z0-9_-]{8,}", _mcp_text(outline_result)):
        handle = token
    write_result = _mcp_call(
        server,
        "propose_write",
        {
            "intent": "S5 MCP 写",
            "approval": "confirm",
            "handles": {"w2.md": handle},
            "ops": [
                {
                    "op": "replace_lines",
                    "op_id": "o1",
                    "file": "w2.md",
                    "range": {"start": {"line": 2}, "end": {"line": 2}},
                    "expect": "乙行",
                    "text": "MCP 改后的乙行",
                }
            ],
        },
        otel=otel,
    )
    mcp_records = read_session(kb, "mcp-stdio")
    mcp_traces = [row["data"] for row in mcp_records if row["type"] == tr.EVENT_TRACE_CALL]
    applied = [row["data"] for row in mcp_records if row["type"] == "capability/apply"]
    trace_ids_mcp = {e.get("trace_id") for e in mcp_traces}
    trace_ids_apply = {row.get("trace_id") for row in applied if row.get("trace_id")}
    check(
        "MCP 侧 trace/call：transport=mcp + otel 三键 + 32-hex trace_id",
        len(mcp_traces) == 2
        and all(e.get("transport") == "mcp" for e in mcp_traces)
        and all((e.get("otel") or {}).get("traceparent") == tp for e in mcp_traces)
        and {e.get("trace_id") for e in mcp_traces} == {"4bf92f3577b34da6a3ce929d0e0e4736"},
        json.dumps([{k: e.get(k) for k in ("tool_id", "transport", "trace_id", "error_code")} for e in mcp_traces], ensure_ascii=False),
        "MCP trace 缺 transport/otel/trace_id ⇒ 跨进程侧不可关联",
    )
    check(
        "跨边界串起两侧：MCP `trace/call` 与进程内写路径 `capability/apply` 共享同一 trace_id",
        len(applied) >= 1
        and trace_ids_apply == {"4bf92f3577b34da6a3ce929d0e0e4736"}
        and trace_ids_apply <= (trace_ids_mcp | trace_ids_apply)
        and (applied[0].get("otel") or {}).get("traceparent") == tp,
        f"mcp_trace_ids={sorted(trace_ids_mcp)}, apply_trace_ids={sorted(trace_ids_apply)}, applied={len(applied)}",
        "两侧 trace_id 不同 ⇒ '串起进程内/跨进程' 只是口号",
    )

    # ── H. 聚合工具（模型可见的 1 把只读工具）──────────────────────────
    tools = {tool.name: tool for tool in build_kb_tools(str(kb), session_id=sid)}
    summary_text = tools["trace_cost_summary"].handler({"session_id": sid}).text
    check(
        "`trace_cost_summary` 工具：文本含调用数/截断率/失败率/审批拒绝率（只读聚合）",
        "调用数" in summary_text
        and "截断" in summary_text
        and "失败" in summary_text
        and "审批" in summary_text
        and tools["trace_cost_summary"].read_only is True,
        summary_text[:500],
        "聚合工具缺席 ⇒ 成本字段没有消费者",
    )

    # ── I. 不破坏既有回放/压缩口径（未知事件类型对它们零影响）──────────
    trace_event = next(row for row in records if row["type"] == tr.EVENT_TRACE_CALL)
    check(
        "不回归：`trace/call` 在压缩成本口径中计 0（回放/压缩/抽取对未知 type 零影响）",
        compaction.event_chars(trace_event) == 0,
        f"event_chars={compaction.event_chars(trace_event)}",
        "trace 事件挤占压缩预算 ⇒ 改变了既有行为",
    )

    payload = {
        "schema": "trace-cost-s5/v1",
        "task": "task-124",
        "max_entries_per_session": tr.MAX_ENTRIES_PER_SESSION,
        "max_entry_bytes": tr.MAX_ENTRY_BYTES,
        "result_preview_chars": tr.RESULT_PREVIEW_CHARS,
        "assertions": RESULTS,
        "passed": all(row["ok"] for row in RESULTS),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    payload["artifactSha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    for row in RESULTS:
        print(f"  [{'OK' if row['ok'] else 'FAIL'}] {row['name']}: {row['detail']}")
        if not row["ok"] and row["falsifier"]:
            print(f"        falsifier: {row['falsifier']}")
    print(f"\n== RESULT: {'PASS' if payload['passed'] else 'FAIL'} ==  (sha256 {payload['artifactSha256'][:16]}…)")

    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(REPO, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        print(f"wrote: {args.json}")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
