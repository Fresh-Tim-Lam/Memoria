#!/usr/bin/env python
"""S4 扩展层验收（`s4_sample_plugin/check.py`）：第三方声明式加工具 + 内置工具面零变化 + 清障回归。

## 断言（每条都构造真实路径）
| 组 | 断言 |
|---|---|
| **A 扩展生效** | 声明式插件（**不改 `registry.py` 本体**）⇒ 工具面多 3 把；`ext.kb_stats` 真能跑出统计 |
| **B 内置零变化** | 前 39 把**名字 + 顺序 + `read_only` 逐项等于**无插件基线；总数 = 39 + 3 |
| **C 默认关闭** | 没有库级注册表 ⇒ 扩展工具**不出现**（39 把，与无插件一致） |
| **D 超时真强制** | `ext.slow`（timeout_s=1，脚本睡 30s）⇒ `EXT_TOOL_TIMEOUT`，且**实测耗时 < 5s**（子进程被终止） |
| **E 输出上限真强制** | `ext.big`（输出 512KiB）⇒ text ≤ 256KiB+标记，含"已截断" |
| **F 适配器是通用的** | `registry.py` 源码里**不含**任何具体工具名（`ext.` / `kb_stats`） |
| **G 移出字段响亮失败** | `gate` / `constrain` / `tool_schema_ref` / `budget` / 顶层 `lifecycle` ⇒ `removed_field` **错误** |
| **H gate/constrain 已从代码消失** | `plugins.GATE_VALUES` 不存在；`ToolDeclaration` 无 `gate`/`constrain` 属性 |
| **I sha 稳定** | 产物 sha 只对稳定事实求值（临时路径/耗时/句柄占位化）⇒ 连跑 3 次同 sha |

## 用法
    python artifacts/agent/verify/todo/s4_sample_plugin/check.py [--json out.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time

SAMPLE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(SAMPLE, "..", "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))
os.environ.setdefault("MEMORIA_CONFIG_DIR", tempfile.mkdtemp(prefix="memoria-cfg-"))

from memoria.services.agent import plugins  # noqa: E402
from memoria.services.agent.tools import registry as registry_mod  # noqa: E402
from memoria.services.agent.tools.kb import build_kb_tools  # noqa: E402

RESULTS: list[dict] = []
_TMP_RE = re.compile(r"(?:memoria|tmp)[-_a-zA-Z0-9]{6,}")
_ELAPSED_RE = re.compile(r"\d+\.\d+s")


def _stable(value):
    if isinstance(value, str):
        text = _TMP_RE.sub("<TMPDIR>", value)
        return _ELAPSED_RE.sub("<ELAPSED>", text)
    if isinstance(value, dict):
        return {k: _stable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_stable(v) for v in value]
    return value


def check(name: str, ok: bool, detail: str, falsifier: str = "") -> None:
    RESULTS.append({"name": name, "ok": bool(ok), "detail": detail, "falsifier": falsifier})


def _mk_kb(with_registry: bool) -> str:
    kb = tempfile.mkdtemp(prefix="memoria-s4-")
    with open(os.path.join(kb, "d.md"), "w", encoding="utf-8", newline="") as fh:
        fh.write("# 甲\n甲第一行\n\n## 小节\n小节正文\n")
    if with_registry:
        path = os.path.join(kb, ".memoria", "agent", "capabilities.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            json.dump({"enabled": [{"id": "kb-stats", "on": True}]}, fh, ensure_ascii=False)
    return kb


def _materialize_plugins() -> str:
    """把样例声明落地成真实插件目录（`plugin.json` + 绝对命令路径）。"""
    root = tempfile.mkdtemp(prefix="memoria-s4-plugins-")
    tool_dir = os.path.join(root, "kb-stats")
    os.makedirs(tool_dir, exist_ok=True)
    for name in ("kb_stats_tool.py", "slow_tool.py", "big_tool.py"):
        shutil.copyfile(os.path.join(SAMPLE, name), os.path.join(tool_dir, name))
    with open(os.path.join(SAMPLE, "plugin.json.template"), encoding="utf-8") as fh:
        template = fh.read()
    declaration = (
        template.replace("__PYTHON__", sys.executable.replace("\\", "/"))
        .replace("__TOOL_DIR__", tool_dir.replace("\\", "/"))
    )
    with open(os.path.join(tool_dir, "plugin.json"), "w", encoding="utf-8", newline="") as fh:
        fh.write(declaration)
    return root


def _tools_with(kb: str, plugin_dir: str | None):
    """在"指定插件目录 / 空目录"两种环境下构建工具面（不改任何全局状态，事后还原）。"""
    empty = tempfile.mkdtemp(prefix="memoria-s4-empty-")
    orig = (plugins.builtin_dir, plugins.user_dir)
    plugins.builtin_dir = lambda: empty  # type: ignore[assignment]
    plugins.user_dir = lambda: (plugin_dir or empty)  # type: ignore[assignment]
    try:
        return tuple(build_kb_tools(kb))
    finally:
        plugins.builtin_dir, plugins.user_dir = orig  # type: ignore[assignment]


def _check_removed(field: str, where: str) -> list[str]:
    base = {
        "v": 1,
        "id": "demo",
        "name": "Demo",
        "permissions": {"read": ["**"], "write": []},
        "approval": {"read": "auto", "write": "confirm"},
    }
    if where == "top":
        raw = {**base, field: {"x": 1}, "provides": {"tools": [{"tool_id": "kb.kp.create"}]}}
    else:
        raw = {**base, "provides": {"tools": [{"tool_id": "kb.kp.create", field: "x"}]}}
    _decl, _warn, errors = plugins.parse_declaration(raw, source="t")
    return [str(e.get("kind") or "") for e in errors]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    plugin_root = _materialize_plugins()

    # ── 基线：无插件（空目录）──
    kb_plain = _mk_kb(with_registry=False)
    baseline = _tools_with(kb_plain, None)
    base_names = [t.name for t in baseline]
    base_ro = {t.name: t.read_only for t in baseline}
    check(
        "基线：无插件时工具面 = 39 把（与 KB_TOOL_NAMES 一致）",
        len(baseline) == 39,
        f"count={len(baseline)}",
        "基线变了 ⇒ 后续对比无意义",
    )

    # ── C 默认关闭：有插件目录但无库级注册表 ⇒ 仍是 39 把 ──
    off = _tools_with(_mk_kb(with_registry=False), plugin_root)
    check(
        "扩展层默认关闭：声明存在但库级未启用 ⇒ 扩展工具不出现（39 把）",
        len(off) == 39,
        f"count={len(off)}, names_tail={[t.name for t in off[36:]]}",
        "未启用就出现 ⇒ 违背启用位语义",
    )

    # ── A/B 启用后：39 + 3，且前 39 逐项不变 ──
    kb_on = _mk_kb(with_registry=True)
    on = _tools_with(kb_on, plugin_root)
    names_on = [t.name for t in on]
    ext_names = [n for n in names_on if n not in base_ro]
    ro_on = {t.name: t.read_only for t in on}
    check(
        "A 第三方声明式加工具生效：+3 把（不改 registry.py 本体）",
        len(on) == 39 + 3 and ext_names == ["ext.kb_stats", "ext.slow", "ext.big"],
        f"count={len(on)}, ext={ext_names}",
        "扩展工具没出现 ⇒ 扩展点没落地",
    )
    check(
        "B 内置 39 把：名字 + 顺序 + read_only 逐项等于基线",
        names_on[:39] == base_names and all(ro_on[n] == base_ro[n] for n in base_names),
        f"前39一致={names_on[:39] == base_names}, read_only一致={all(ro_on[n] == base_ro[n] for n in base_names)}",
        "内置工具面被扩展层污染 ⇒ 行为回归",
    )
    check(
        "B2 扩展工具 read_only 也参与审批档（继承声明的 true）",
        all(ro_on[n] is True for n in ext_names),
        f"ext read_only={ {n: ro_on[n] for n in ext_names} }",
    )

    # ── A2 扩展工具真能跑 ──
    stats_tool = next(t for t in on if t.name == "ext.kb_stats")
    out = stats_tool.handler({})
    check(
        "A2 扩展工具真执行（plugin 自己的代码）：返回 mp 统计",
        (not out.error) and "篇 md" in out.text and "扩展工具 ext.kb_stats" in out.text,
        f"error={out.error}, text={(out.text or '')[:80]}",
        "扩展工具跑不起来 ⇒ 声明只是装饰",
    )

    # ── D 超时真强制 ──
    slow_tool = next(t for t in on if t.name == "ext.slow")
    started = time.time()
    slow_out = slow_tool.handler({})
    elapsed = time.time() - started
    check(
        "D 超时真强制：ext.slow（脚本睡 30s，timeout=1s）⇒ EXT_TOOL_TIMEOUT 且实测 <5s",
        slow_out.error and slow_out.code == registry_mod.EXT_TOOL_TIMEOUT_CODE and elapsed < 5.0,
        f"code={slow_out.code}, elapsed={elapsed:.2f}s",
        "只写进 schema 不真强制 ⇒ 子进程会挂 30s",
    )

    # ── E 输出上限真强制 ──
    big_tool = next(t for t in on if t.name == "ext.big")
    big_out = big_tool.handler({})
    big_len = len((big_out.text or "").encode("utf-8"))
    check(
        "E 输出上限真强制：ext.big 输出 512KiB ⇒ 截断到 ≤256KiB 且带标记",
        big_len <= registry_mod.EXT_TOOL_OUTPUT_MAX_BYTES + 256 and "已截断" in (big_out.text or ""),
        f"bytes={big_len}, marker={'已截断' in (big_out.text or '')}",
        "不截断 ⇒ 一次工具调用可把上下文灌爆",
    )

    # ── F 适配器通用：registry.py 不含具体工具名 ──
    with open(os.path.join(REPO, "src", "memoria", "services", "agent", "tools", "registry.py"), encoding="utf-8") as fh:
        reg_src = fh.read()
    check(
        "F 适配器是通用的：registry.py 源码不含任何具体扩展工具名",
        "kb_stats" not in reg_src and 'ext.' not in reg_src,
        f"contains_kb_stats={'kb_stats' in reg_src}, contains_ext={('ext.' in reg_src)}",
        "核心文件里出现具体工具名 ⇒ 第三方加工具仍需改核心",
    )

    # ── G 移出字段：响亮失败 ──
    g_ok = True
    g_detail = {}
    for field, where in (("gate", "tool"), ("constrain", "tool"), ("tool_schema_ref", "tool"), ("budget", "tool"), ("lifecycle", "top")):
        kinds = _check_removed(field, where)
        g_detail[f"{where}.{field}"] = kinds
        if "removed_field" not in kinds:
            g_ok = False
    check("G 移出字段（gate/constrain/tool_schema_ref/budget/lifecycle）⇒ removed_field 错误", g_ok, json.dumps(g_detail, ensure_ascii=False))

    # ── H 代码层已消失 ──
    _decl2, _w, _e = plugins.parse_declaration(
        {
            "v": 1,
            "id": "demo",
            "name": "Demo",
            "provides": {"tools": [{"tool_id": "kb.kp.create"}]},
            "permissions": {"read": ["**"], "write": []},
            "approval": {"read": "auto", "write": "confirm"},
        },
        source="t",
    )
    has_gate = hasattr(plugins, "GATE_VALUES")
    decl_fields = {f.name for f in plugins.ToolDeclaration.__dataclass_fields__.values()}
    check(
        "H gate/constrain 已从代码消失（GATE_VALUES 不存在；ToolDeclaration 无 gate/constrain）",
        (not has_gate) and "gate" not in decl_fields and "constrain" not in decl_fields,
        f"GATE_VALUES存在={has_gate}, ToolDeclaration字段={sorted(decl_fields)}",
        "字段还在 ⇒ 死字段仍在契约里",
    )

    # ── I sha 稳定（稳定投影）──
    payload = {
        "schema": "s4-extension-acceptance/v1",
        "baseline_names": base_names,
        "ext_names": ext_names,
        "removed_field_kinds": g_detail,
        "assertions": _stable(RESULTS),
        "passed": all(r["ok"] for r in RESULTS),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    payload["artifactSha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    for r in RESULTS:
        print(f"  [{'OK' if r['ok'] else 'FAIL'}] {r['name']}: {r['detail']}")
        if not r["ok"] and r["falsifier"]:
            print(f"        falsifier: {r['falsifier']}")
    print(f"\n== RESULT: {'PASS' if payload['passed'] else 'FAIL'} ==  (sha256 {payload['artifactSha256'][:16]}…")

    if args.json:
        out_path = args.json if os.path.isabs(args.json) else os.path.join(REPO, args.json)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        print(f"wrote: {args.json}")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
