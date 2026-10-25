#!/usr/bin/env python
"""MCP 协议层验收（`mcp_protocol`）：**真实跨进程 stdio** + schema 自校验（含必红）+ schema 预算。

## 断言
| 断言 | 构造 | 期望 |
|---|---|---|
| `discover_required` | `server/discover` | 结果含官方 schema 的 **全部 required**：`cacheScope/capabilities/resultType/supportedVersions/ttlMs` |
| `tools_list_required` | `tools/list` | required：`cacheScope/resultType/tools/ttlMs`；tools 里每项含 `name/description/inputSchema` |
| `call_required` | `tools/call` outline | required：`content/resultType` |
| **`schema_selfcheck_red`** | **故意删掉 `ttlMs`** 再跑同一校验器 | 校验器必须**失败**（证明自校验有判别力，不是永远绿） |
| `unknown_method` | 发未知 method | `-32601` |
| `missing_meta_version` | 不带 `_meta.protocolVersion` | `-32022` |
| `bad_version` | `2025-11-25` | `-32022`（**不做 initialize 回退**） |
| `parse_error` | 发非 JSON 一行 | `-32700` |
| `schema_budget` | 量 4 把工具 schema 的 token | ≤ **1,450**（N1：35 工具 ≈4,349 tok 的 1/3） |
| `no_direct_write_tool` | 列工具名 | 只有 outline/section/snippet/propose_write；**无** write/edit/apply 直写工具 |

## 用法
    python scripts/benchmark/maintenance/mcp_protocol.py [--json out.json]
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

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))
os.environ.setdefault("MEMORIA_CONFIG_DIR", tempfile.mkdtemp(prefix="memoria-cfg-"))

from memoria.services.agent.section_index import estimate_tokens  # noqa: E402

PROTOCOL_VERSION = "2026-07-28"
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CAPS = "io.modelcontextprotocol/clientCapabilities"
SCHEMA_BUDGET_TOKENS = 1450

#: 官方 2026-07-28 schema 的 required（逐字取自 schema.json 的 $defs）
REQUIRED = {
    "DiscoverResult": ("cacheScope", "capabilities", "resultType", "supportedVersions", "ttlMs"),
    "ListToolsResult": ("cacheScope", "resultType", "tools", "ttlMs"),
    "CallToolResult": ("content", "resultType"),
}
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



def check(name: str, ok: bool, detail: str, falsifier: str = "") -> None:
    RESULTS.append({"name": name, "ok": bool(ok), "detail": detail, "falsifier": falsifier})


def validate_required(kind: str, payload: dict) -> list[str]:
    """schema 自校验：返回**缺失的 required 字段**列表（空 = 合规）。"""
    return [key for key in REQUIRED[kind] if key not in payload]


class StdioClient:
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

    def send_raw(self, line: str) -> dict:
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        reply = self.proc.stdout.readline()
        return json.loads(reply)

    def call(self, method: str, params: dict) -> dict:
        self._n += 1
        return self.send_raw(json.dumps({"jsonrpc": "2.0", "id": f"t{self._n}", "method": method, "params": params}, ensure_ascii=False))

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            self.proc.kill()


def _meta() -> dict:
    return {META_VERSION: PROTOCOL_VERSION, META_CAPS: {}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    kb = tempfile.mkdtemp(prefix="memoria-mcp-")
    with open(os.path.join(kb, "d.md"), "w", encoding="utf-8", newline="") as fh:
        fh.write("# 甲\n甲第一行\n\n## 小节\n小节正文\n")

    client = StdioClient(kb)
    transcript: list[dict] = []
    try:
        disc = client.call("server/discover", {"_meta": _meta()})
        transcript.append({"method": "server/discover", "ok": "result" in disc})
        missing = validate_required("DiscoverResult", disc.get("result") or {})
        check(
            "MCP server/discover 结果含全部 required 字段",
            not missing and disc["result"]["resultType"] == "complete",
            f"missing={missing}, resultType={(disc.get('result') or {}).get('resultType')}",
            "缺 required ⇒ 本 server 会判不合规（DiscoverResult 是 spec MUST）",
        )

        lst = client.call("tools/list", {"_meta": _meta()})
        transcript.append({"method": "tools/list", "ok": "result" in lst})
        missing = validate_required("ListToolsResult", lst.get("result") or {})
        tools = (lst.get("result") or {}).get("tools") or []
        bad_tools = [t.get("name") for t in tools if not all(k in t for k in ("name", "description", "inputSchema"))]
        check(
            "MCP tools/list 结果含 required 且每个 tool 有 name/description/inputSchema",
            not missing and not bad_tools and len(tools) == 4,
            f"missing={missing}, tools={[t.get('name') for t in tools]}, bad={bad_tools}",
        )

        call_res = client.call(
            "tools/call", {"_meta": _meta(), "name": "outline", "arguments": {"file": "d.md"}}
        )
        transcript.append({"method": "tools/call", "ok": "result" in call_res})
        missing = validate_required("CallToolResult", call_res.get("result") or {})
        check(
            "MCP tools/call 结果含 required（content/resultType）",
            not missing,
            f"missing={missing}, keys={sorted((call_res.get('result') or {}).keys())}",
        )

        # ── schema 自校验的判别力：删掉一个 required 必须判失败 ──
        broken = dict(lst.get("result") or {})
        broken.pop("ttlMs", None)
        broken_missing = validate_required("ListToolsResult", broken)
        broken2 = dict(disc.get("result") or {})
        broken2.pop("resultType", None)
        broken2_missing = validate_required("DiscoverResult", broken2)
        check(
            "schema 自校验有判别力（删 ttlMs / resultType ⇒ 必须判缺失）",
            broken_missing == ["ttlMs"] and broken2_missing == ["resultType"],
            f"删 ttlMs→{broken_missing}, 删 resultType→{broken2_missing}",
            "删了还判合规 ⇒ 自校验是装饰（永远绿）",
        )

        unknown = client.call("resources/list", {"_meta": _meta()})
        check(
            "未实现的方法 ⇒ -32601（不假装支持）",
            (unknown.get("error") or {}).get("code") == -32601,
            f"error={(unknown.get('error') or {}).get('code')}",
        )
        no_meta = client.call("tools/list", {})
        check(
            "缺 _meta.protocolVersion ⇒ -32022",
            (no_meta.get("error") or {}).get("code") == -32022,
            f"error={(no_meta.get('error') or {}).get('code')}",
        )
        bad_ver = client.call("tools/list", {"_meta": {META_VERSION: "2025-11-25"}})
        check(
            "旧协议版本 ⇒ -32022（不做 initialize 静默降级）",
            (bad_ver.get("error") or {}).get("code") == -32022,
            f"error={(bad_ver.get('error') or {}).get('code')}, "
            f"msg={((bad_ver.get('error') or {}).get('message') or '')[:60]}",
            "旧版本被接受 ⇒ 两套握手语义并存",
        )
        parse = client.send_raw("{not json")
        check(
            "非 JSON 一行 ⇒ -32700（newline-delimited 时分帧不崩）",
            (parse.get("error") or {}).get("code") == -32700,
            f"error={(parse.get('error') or {}).get('code')}",
        )

        names = [t.get("name") for t in tools]
        check(
            "工具面只有 4 把且**无直写工具**",
            names == ["outline", "section", "snippet", "propose_write"]
            and not any(n in ("write", "edit", "apply", "write_file", "edit_file") for n in names),
            f"names={names}",
            "出现直写工具 ⇒ W1 入口唯一在 MCP 边界失效",
        )

        schema_tokens = estimate_tokens(json.dumps(tools, ensure_ascii=False))
        check(
            f"schema 预算 ≤{SCHEMA_BUDGET_TOKENS} tok（N1：35 工具≈4,349 的 1/3）",
            schema_tokens <= SCHEMA_BUDGET_TOKENS,
            f"tokens_estimated={schema_tokens}（budget {SCHEMA_BUDGET_TOKENS}）",
            "超预算 ⇒ 违背'最小工具集'的立项前提",
        )
    finally:
        client.close()

    payload = {
        "schema": "mcp-protocol-acceptance/v1",
        "protocol_version": PROTOCOL_VERSION,
        "transport": "stdio / newline-delimited JSON-RPC 2.0",
        "required_from_official_schema": REQUIRED,
        "schema_tokens_estimated": schema_tokens if RESULTS else 0,
        "schema_budget_tokens": SCHEMA_BUDGET_TOKENS,
        "transcript": transcript,
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
