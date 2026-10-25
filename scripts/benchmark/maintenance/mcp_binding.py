#!/usr/bin/env python
"""MCP 边界安全验收（`mcp_binding`）：W1–W4 在**进程边界**复跑 + `read_handle` 三条约束 + 端到端 + 重启。

## 断言分组

**A. 写安全在 MCP 边界（每条都构造违规路径）**
| 断言 | 构造 | 期望 |
|---|---|---|
| `W1_no_direct_write_tool` | 列工具 | 只有 4 把；`propose_write` 是唯一写入口 |
| `W1_plan_only` | 写必须带 plan 的 ops（无 `write_file` 之类） | 只能走 `propose_write` |
| `W2_no_handle` | 未读就写（不带 `handles`） | `FS_NOT_OBSERVED` |
| `W2_snippet_no_handle`（Lead ④） | 先 `snippet` 再 `propose_write` | **仍** `FS_NOT_OBSERVED`（片段≠看过） |
| `W2_bogus_handle` | 伪造 token | `WRITE_GATE_BYPASS` |
| `W2_stale_sha` | 读后被外部改 | `FS_STALE_VERSION` |
| `W3_backup_failure_zero_write` | 注入备份失败 | 错误 + **文件 sha 不变** |
| `W4_approval_auto_rejected` | `approval=auto` | `APPROVAL_REQUIRED` |

**B. `read_handle` 三条约束（Lead ④⑤⑥）**
| 断言 | 构造 | 期望 |
|---|---|---|
| `handle_unpredictable`（⑥） | 两次读同一文件 | token **不同**、长度≥40、char 集 urlsafe |
| `handle_capacity_lru`（⑤） | `HandleStore(max_entries=3)` 签 4 个 | 第 1 个被淘汰；MCP 层用它 ⇒ `WRITE_GATE_BYPASS` |
| `handle_ttl_expiry`（⑤） | `HandleStore(ttl_s=0.01)` 后 sleep | 过期 ⇒ `WRITE_GATE_BYPASS` |

**C. 端到端（真实跨进程 stdio）**
`outline → section → propose_write`：写入生效、`txid` 可查（备份批次目录存在）、`preview` 可见、
`undo`（`restore_batch`）逐字节复原。

**D. 无状态（重启）**
进程 1 拿到的 handle，进程 2（新 server）**必须无效** ⇒ `WRITE_GATE_BYPASS`；重读后可写。

## 用法
    python scripts/benchmark/maintenance/mcp_binding.py [--json out.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))
os.environ.setdefault("MEMORIA_CONFIG_DIR", tempfile.mkdtemp(prefix="memoria-cfg-"))

from memoria.services.agent import backup  # noqa: E402
from memoria.services.agent import section_index as si  # noqa: E402
from memoria.services.agent.mcp_server import (  # noqa: E402
    PROTOCOL_VERSION,
    HandleStore,
    McpServer,
)

RESULTS: list[dict] = []

# ── sha 只对**稳定事实**求值（2026-10-25，Lead 抓到的 flaky）──────────────────
# 教训：`read_handle`（secrets 随机）与 `txid`（含时间戳）被算进 sha ⇒ 每次产物 sha 都不同。
# 同一原则 S1 就修过（隔离 maxFileMs）——这里把随机值换成占位符后再算。
_HANDLE_RE = re.compile(r"rh-[A-Za-z0-9_-]{8,}")
_TXID_RE = re.compile(r"\d{8}T\d{6}Z-\d{2,}")
_TMP_RE = re.compile(r"memoria[-_][a-zA-Z0-9_-]{6,}")


def _stable(value):
    """把非确定性 token / txid / 临时目录路径替换成占位符（递归）。"""
    if isinstance(value, str):
        text = _HANDLE_RE.sub("<HANDLE>", value)
        text = _TXID_RE.sub("<TXID>", text)
        return _TMP_RE.sub("<TMPDIR>", text)
    if isinstance(value, dict):
        return {key: _stable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_stable(item) for item in value]
    return value

META = {
    "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
    "io.modelcontextprotocol/clientCapabilities": {},
}
DOC = "# 甲\n甲第一行\n\n## 小节\n小节正文\n更多正文一行。\n"


def check(name: str, ok: bool, detail: str, falsifier: str = "") -> None:
    RESULTS.append({"name": name, "ok": bool(ok), "detail": detail, "falsifier": falsifier})


def _mk_kb() -> str:
    kb = tempfile.mkdtemp(prefix="memoria-mcpb-")
    with open(os.path.join(kb, "d.md"), "w", encoding="utf-8", newline="") as fh:
        fh.write(DOC)
    with open(os.path.join(kb, "e.md"), "w", encoding="utf-8", newline="") as fh:
        fh.write("# 乙\n乙第一行\n")
    return kb


def _sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _call(server: McpServer, name: str, arguments: dict) -> dict:
    reply = server.handle_message(
        {"jsonrpc": "2.0", "id": "x", "method": "tools/call", "params": {"_meta": META, "name": name, "arguments": arguments}}
    )
    return (reply or {}).get("result") or {}


def _err_code(result: dict) -> str:
    text = "".join(
        str(block.get("text") or "") for block in (result.get("content") or []) if isinstance(block, dict)
    )
    return text.split(":", 1)[0].strip() if text else ""


def _write_args(handle: str | None, rel: str = "d.md") -> dict:
    args: dict = {
        "intent": "契约测试：改一行",
        "ops": [
            {"op": "replace_lines", "op_id": "o1", "file": rel,
             "range": {"start": 5, "end": 5}, "text": "改后的正文", "expect": "小节正文"}
        ],
    }
    if handle is not None:
        args["handles"] = {rel: handle}
    return args


def _run_inprocess() -> None:
    kb = _mk_kb()
    server = McpServer(kb)

    # W1：工具面（无直写）
    listed = server.handle_message(
        {"jsonrpc": "2.0", "id": "l", "method": "tools/list", "params": {"_meta": META}}
    )["result"]["tools"]
    names = [t["name"] for t in listed]
    check(
        "W1 MCP 边界只有 4 把工具，无任何直写工具",
        names == ["outline", "section", "snippet", "propose_write"],
        f"tools={names}",
        "出现直写工具 ⇒ 绕过唯一写者链",
    )

    # W2：未读就写
    res = _call(server, "propose_write", _write_args(None))
    check(
        "W2 未读就写（无 handle）⇒ FS_NOT_OBSERVED",
        res.get("isError") and _err_code(res) == "FS_NOT_OBSERVED",
        f"isError={res.get('isError')}, code={_err_code(res)}",
        "未读也放行 ⇒ W2 在边界失效",
    )

    # ④ snippet 不签发 handle ⇒ 写完仍被拒
    sn = _call(server, "snippet", {"file": "d.md", "query": "小节正文"})
    sn_handle = (sn.get("structuredContent") or {}).get("read_handle")
    res = _call(server, "propose_write", _write_args(sn_handle))
    check(
        "W2(④) snippet 不签发 handle ⇒ 之后写入仍 FS_NOT_OBSERVED",
        sn_handle is None and res.get("isError") and _err_code(res) == "FS_NOT_OBSERVED",
        f"snippet_handle={sn_handle}, code={_err_code(res)}",
        "snippet 给了 handle ⇒ 模型可靠 grep 获得写权限，W2 直接失效",
    )

    # W2：伪造 handle
    res = _call(server, "propose_write", _write_args("rh-forged-token-not-issued"))
    check(
        "W2 伪造 handle ⇒ WRITE_GATE_BYPASS",
        res.get("isError") and _err_code(res) == "WRITE_GATE_BYPASS",
        f"code={_err_code(res)}",
    )

    # ⑥ 随机性：两次读同一文件得到不同 handle，且都可查
    sec1 = _call(server, "section", {"file": "d.md", "heading": "小节"})
    sec2 = _call(server, "section", {"file": "d.md", "heading": "小节"})
    h1 = (sec1.get("structuredContent") or {}).get("read_handle")
    h2 = (sec2.get("structuredContent") or {}).get("read_handle")
    urlsafe = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    check(
        "W2(⑥) read_handle 不可猜测：两次读同一文件 token 不同、长度足够、urlsafe",
        bool(h1) and bool(h2) and h1 != h2 and len(h1) >= 40 and set(h1[3:]) <= urlsafe,
        f"h1={str(h1)[:12]}… h2={str(h2)[:12]}… len={len(h1 or '')}, 不同={h1 != h2}",
        "两次同值 ⇒ 是确定性哈希/递增 id，可预测",
    )
    check(
        "W2(⑥) 两个 handle 同时有效（不是单次即焚）",
        server.handles.lookup(h1) is not None and server.handles.lookup(h2) is not None,
        f"lookup1={server.handles.lookup(h1) is not None}, lookup2={server.handles.lookup(h2) is not None}",
    )

    # W2：读后被外部改 ⇒ FS_STALE_VERSION
    with open(os.path.join(kb, "d.md"), "a", encoding="utf-8", newline="") as fh:
        fh.write("\n外部追加一行。\n")
    res = _call(server, "propose_write", _write_args(h1))
    check(
        "W2 读后被外部改 ⇒ FS_STALE_VERSION",
        res.get("isError") and _err_code(res) == "FS_STALE_VERSION",
        f"code={_err_code(res)}",
        "sha 变了还放行 ⇒ 写到旧内容上",
    )
    # 复原文档（重新读 + 写）
    with open(os.path.join(kb, "d.md"), "w", encoding="utf-8", newline="") as fh:
        fh.write(DOC)
    sec3 = _call(server, "section", {"file": "d.md", "heading": "小节"})
    h3 = (sec3.get("structuredContent") or {}).get("read_handle")

    # W3：备份失败 ⇒ 零写入
    before = _sha(os.path.join(kb, "d.md"))
    orig = backup.snapshot_pre_images

    def _failing(*a, **k):
        return {"status": "error", "code": "backup_failed", "message": "注入：备份失败（fixture）", "files": []}

    backup.snapshot_pre_images = _failing  # type: ignore[assignment]
    try:
        res = _call(server, "propose_write", _write_args(h3))
    finally:
        backup.snapshot_pre_images = orig  # type: ignore[assignment]
    after = _sha(os.path.join(kb, "d.md"))
    check(
        "W3 备份失败 ⇒ 零写入（MCP 边界）",
        res.get("isError") and _err_code(res) == "backup_failed" and after == before,
        f"code={_err_code(res)}, sha不变={after == before}",
        "备份失败仍写入 ⇒ W3 在边界失效",
    )

    # W4：外部调用 approval=auto ⇒ 拒
    args = _write_args(h3)
    args["approval"] = "auto"
    res = _call(server, "propose_write", args)
    check(
        "W4 外部调用 approval=auto 且能力有写权限 ⇒ APPROVAL_REQUIRED",
        res.get("isError") and _err_code(res) == "APPROVAL_REQUIRED",
        f"code={_err_code(res)}",
        "auto 放过 ⇒ 外部可自行降档",
    )

    # ⑤ 容量上限 + LRU 淘汰
    store = HandleStore(ttl_s=600, max_entries=3)
    toks = [store.mint(kb, "d.md", "sha-x") for _ in range(4)]
    check(
        "W2(⑤) handle 表有容量上限（1024 默认 / 测试用 3）：第 1 个被 LRU 淘汰",
        len(store) == 3 and store.lookup(toks[0]) is None and store.lookup(toks[3]) is not None,
        f"len={len(store)}, first_evicted={store.lookup(toks[0]) is None}",
        "无上限 ⇒ 长期运行内存泄漏",
    )
    # 淘汰后再用 ⇒ MCP 层必须响亮失败
    server2 = McpServer(kb, handle_store=HandleStore(ttl_s=600, max_entries=2))
    _call(server2, "section", {"file": "d.md", "heading": "小节"})
    h_a = _call(server2, "section", {"file": "e.md"})  # e.md 没标题 → 可能报错，改用 outline
    _call(server2, "outline", {"file": "e.md"})
    stale_token = server2.handles.mint(kb, "d.md", "deadbeef")
    server2.handles._items.pop(stale_token, None)  # 模拟被淘汰
    res = _call(server2, "propose_write", _write_args(stale_token))
    check(
        "W2(⑤) 被淘汰的 handle 再用 ⇒ WRITE_GATE_BYPASS（不静默）",
        res.get("isError") and _err_code(res) == "WRITE_GATE_BYPASS",
        f"code={_err_code(res)}",
    )
    # TTL 过期
    short = HandleStore(ttl_s=0.01, max_entries=10)
    tok = short.mint(kb, "d.md", "sha-y")
    time.sleep(0.05)
    check(
        "W2(⑤) handle 有 TTL：过期后 lookup 为 None",
        short.lookup(tok) is None,
        f"ttl=0.01s, expired={short.lookup(tok) is None}",
        "永不过期 ⇒ 长时间运行可被重放",
    )


class _Stdio:
    def __init__(self, kb: str) -> None:
        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.join(REPO, "src")
        env["PYTHONIOENCODING"] = "utf-8"
        env.setdefault("MEMORIA_CONFIG_DIR", tempfile.mkdtemp(prefix="memoria-cfg-"))
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "memoria.services.agent.mcp_server", "--kb", kb],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", env=env,
        )
        self._n = 0

    def call(self, method: str, params: dict) -> dict:
        self._n += 1
        assert self.proc.stdin and self.proc.stdout
        msg = {"jsonrpc": "2.0", "id": f"b{self._n}", "method": method, "params": params}
        self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def tool(self, name: str, arguments: dict) -> dict:
        return (self.call("tools/call", {"_meta": META, "name": name, "arguments": arguments}) or {}).get("result") or {}

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            self.proc.kill()


def _run_cross_process() -> None:
    kb = _mk_kb()
    host = os.path.join(kb, "d.md")
    before = _sha(host)
    client = _Stdio(kb)
    try:
        out = client.tool("outline", {"file": "d.md"})
        check("E2E outline（跨进程）返回 handle", bool((out.get("structuredContent") or {}).get("read_handle")),
              f"keys={sorted((out.get('structuredContent') or {}).keys())}")
        sec = client.tool("section", {"file": "d.md", "heading": "小节"})
        handle = (sec.get("structuredContent") or {}).get("read_handle")
        w = client.tool("propose_write", _write_args(handle))
        mid = _sha(host)
        struct = w.get("structuredContent") or {}
        txid = struct.get("txid") or ""
        backup_dir = os.path.join(kb, ".memoria", "agent", "backups", "mcp-stdio", txid)
        check(
            "E2E 跨进程 outline→section→propose_write：写入生效 + txid + preview + undo_available",
            not w.get("isError")
            and mid != before
            and bool(txid)
            and os.path.isdir(backup_dir)
            and bool(struct.get("preview"))
            and struct.get("undo_available") is True,
            f"isError={w.get('isError')}, txid={txid}, 备份目录={os.path.isdir(backup_dir)}, "
            f"preview_rows={len(struct.get('preview') or []) if False else len(struct.get('preview') or [])}",
            "没有 preview/txid/备份 ⇒ 跨进程客户端无法给人看、也无法撤销",
        )
        undo = backup.restore_batch(kb, "mcp-stdio", txid, rel_paths=["d.md"])
        restored = _sha(host)
        check(
            "E2E 撤销：restore_batch 逐字节回 pre-image",
            undo.get("status") == "ok" and restored == before,
            f"undo={undo.get('status')}, 逐字节={restored == before}",
        )
    finally:
        client.close()

    # D. 重启 ⇒ handle 表空 ⇒ 旧 handle 无效
    c1 = _Stdio(kb)
    try:
        h_old = (c1.tool("section", {"file": "d.md", "heading": "小节"}).get("structuredContent") or {}).get("read_handle")
    finally:
        c1.close()
    c2 = _Stdio(kb)
    try:
        res = c2.tool("propose_write", _write_args(h_old))
        code = _err_code(res)
        h_new = (c2.tool("section", {"file": "d.md", "heading": "小节"}).get("structuredContent") or {}).get("read_handle")
        res2 = c2.tool("propose_write", _write_args(h_new))
        check(
            "无状态：重启后旧 handle 无效 ⇒ WRITE_GATE_BYPASS；重读后可写",
            res.get("isError") and code == "WRITE_GATE_BYPASS" and not res2.get("isError"),
            f"旧handle={code}, 重读后写={('ok' if not res2.get('isError') else _err_code(res2))}",
            "旧 handle 仍可用 ⇒ 跨进程状态被错误地持久化",
        )
    finally:
        c2.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    _run_inprocess()
    _run_cross_process()

    payload = {
        "schema": "mcp-binding-acceptance/v1",
        "protocol_version": PROTOCOL_VERSION,
        "w2_handle_design": "server-minted read_handle (SEP-2567) bound to (kb, rel, sha256); TTL+LRU; secrets token",
        "assertions": RESULTS,
        "passed": all(r["ok"] for r in RESULTS),
    }
    # sha 与落盘内容都用**稳定投影**（随机 token/txid/临时路径 → 占位符）
    payload["assertions"] = _stable(payload["assertions"])
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
