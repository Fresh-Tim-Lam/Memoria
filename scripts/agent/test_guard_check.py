#!/usr/bin/env python
"""测试结构守卫机检（B-test-literal-4 落地 · task-162）

## 它治什么病（B-test-literal-3 的执行前提）

仓库里有约 560 处「把源码当字符串做 `in` 断言」的结构守卫（24 个测试文件）。
它们**本身是有价值的**（钉住"这个入口不能删"、"这类事件必须触发缓存失效"），
但它们的维护是**分散的、靠人手动同步的** ⇒ task-164 改了 `state.currentPath → savePath`，
守卫没全跟上 ⇒ 合法重构被挡，而真回归与它长得一模一样。

Lead 的裁断（我采纳）：
> **不靠人记得同步，靠机检发现"守卫指的东西没了"。**

⇒ 本脚本给两类信号，**级别不同**（这是关键设计）：

| 检查 | 级别 | 为什么 |
|---|---|---|
| **守卫引用的符号在 src 里已不存在** | **FAIL** | 符号被重命名/删除 ⇒ 该守卫已经**测不到任何东西**了（它永远绿）。这是"守卫失效"，必须修 |
| **源码字面量断言过长**（押整行而非契约点） | **WARN** | 长 ≠ 错；`function wrapTurn` 这类是合理的防删除守卫。一次全改成 FAIL 会逼出"为过门禁而改断言" |

## 用法

    python scripts/agent/test_guard_check.py                 # 全量：WARN + FAIL 报告
    python scripts/agent/test_guard_check.py --strict        # WARN 也算失败（清债用）
    python scripts/agent/test_guard_check.py --symbols-only  # 只跑 FAIL 级（符号失效）
    python scripts/agent/test_guard_check.py --json out.json
    python scripts/agent/test_guard_check.py --selftest      # 证红/证绿（临时 fixture）

退出码（B3-e 退出码契约）：
    0 = 已执行且无 FAIL（WARN 允许）
    1 = 已执行且有 FAIL（符号失效）
    2 = 参数/自检错误（不是"检查通过"）
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TESTS = REPO / "tests"
SRC = REPO / "src"

#: 判定"这是源码/locale/css 断言"的接收变量名（`in src` / `in js` / `in css` / `in text` …）
SOURCE_VARS = frozenset({"src", "js", "css", "text", "html", "block", "code", "content_raw"})

#: 默认的"过长"阈值（WARN）。
#:
#: ## 为什么这个数只是【辅助】判据，不是主判据（2026-10-26 实测推翻了初版）
#
#: 初版我打算用"字面量 ≥40 字符"作判据。**实测全仓 404 条源码断言后否掉了它**：
#:
#: | 判据 | 命中 | 问题 |
#: |---|---|---|
#: | 长度 ≥40 | 224 条（55%） | **严重误伤** |
#: | 长度 ≥100 | 13 条 | 仍误伤 |
#: | **符号数 > 2** | **6 条** | **精准** |
#:
#: 决定性反例（同一份数据里同时存在）：
#: - `331 字符 / 1 符号`：`if (window.MathJax?.typesetPromise) { ... }` ——
#:   字符极长但只有 1 个本项目符号，它是**合理的"函数存在"守卫**，长度判据会误伤它；
#: - `58 字符 / 4 符号`：`return { line: line, col: off + 1, lineStart: off === 0 };` ——
#:   字符很短但押了 4 个字段/变量，它**才真该收窄**，长度判据会放过它。
#:
#: ⇒ **长度是错的代理指标；符号数才是**（这也正是 B-test-literal-1 的原文："≤2 符号"）。
#: 长度保留作**辅助**信号（只用来在报告里排序、帮人快速定位长断言），不单独判违规。
DEFAULT_LEN_THRESHOLD = 100

#: **主判据**：一条源码字面量断言里含的【本项目符号】数 > 此值 ⇒ 押了超过"契约点"的细节。
MAX_CONTRACT_SYMBOLS = 2

#: 常量枚举（这些是**契约点**，长一点也合理：它们是稳定公开名字）
_ENUM_HINTS = re.compile(r"^[A-Z][A-Z0-9_]{3,}$")

#: 从断言里提取"被守卫的符号"——只认 **JS 标识符/函数名/方法调用**，不认整行
_SYMBOL_PATTERNS = [
    re.compile(r"function\s+([A-Za-z_$][\w$]*)\s*\("),          # function foo(
    re.compile(r"([A-Za-z_$][\w$]*)\s*=\s*function\b"),          # foo = function
    re.compile(r"([A-Za-z_$][\w$]*)\s*\("),                       # foo(  （调用/定义）
    re.compile(r"([A-Za-z_$][\w$]*)\s*[:=]"),                     # foo: / foo =
]

#: 太通用的名字，不作为"符号失效"判据（会大量误报）
#:
#: 判别原则：**不由本项目定义的**（语言内建 / 宿主全局 / 常见库）都不判 ——
#: 它们"不存在于 src"是正常的（比如 `console` 是宿主全局），不是守卫失效。
_GENERIC = frozenset(
    {
        # 语言关键字 / 内建
        "if", "for", "while", "return", "function", "var", "let", "const", "new", "typeof",
        "true", "false", "null", "undefined", "this", "that", "else", "switch", "case",
        "catch", "try", "throw", "await", "async", "in", "of", "do", "break", "continue",
        # 语言内建对象
        "String", "Number", "Boolean", "Array", "Object", "JSON", "Math", "Date", "Map",
        "Set", "Promise", "RegExp", "Error", "Symbol", "BigInt", "WeakMap", "WeakSet",
        # 宿主全局（浏览器 / Node）—— 本仓不定义它们
        "document", "window", "console", "navigator", "localStorage", "sessionStorage",
        "setTimeout", "setInterval", "clearTimeout", "clearInterval", "fetch",
        "requestAnimationFrame", "cancelAnimationFrame", "getComputedStyle",
        "parseFloat", "parseInt", "isNaN", "encodeURIComponent", "decodeURIComponent",
        "require", "module", "exports", "process", "global", "globalThis",
        # 测试自身常用
        "assert", "print", "len", "str", "int", "dict", "list", "range", "enumerate",
    }
)


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _display_rel(path: Path, root: Path) -> str:
    """仓库内路径用相对形式；仓库外（自检临时目录/跨盘符）用绝对路径。"""
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _src_corpus() -> tuple[str, str]:
    """整仓 src 的文本语料（JS + CSS + PY）。

    符号存在性判定用"**全仓 src 任一文件含该标识符**"，而不是"某个特定文件含" ——
    因为守卫移动文件位置（合法重构）不该算失效。
    """
    parts: list[str] = []
    for p in SRC.rglob("*"):
        if p.suffix.lower() in {".js", ".css", ".py", ".mjs", ".html"} and p.is_file():
            parts.append(_read(p))
    joined = "\n".join(parts)
    return joined, joined


def _extract_assert_strings(path: Path) -> list[dict]:
    """从测试文件里提取 `assert <literal> in <source_var>` 形式的断言。

    用 AST 而非正则，避免把 `in body` / `in result`（运行期数据断言）误判成源码断言。
    """
    text = _read(path)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    out: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        test = node.test
        # 形式 A：`"literal" in src`
        if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.In):
            lit = test.left
            right = test.comparators[0]
            if isinstance(lit, ast.Constant) and isinstance(lit.value, str):
                var = right.id if isinstance(right, ast.Name) else None
                if var in SOURCE_VARS:
                    out.append(
                        {
                            "line": node.lineno,
                            "literal": lit.value,
                            "var": var,
                        }
                    )
    return out


def _symbols_in_literal(literal: str) -> list[str]:
    """从一个"源码字面量"里提取**被守卫的【本项目】符号名**。

    ## 只认"本仓定义的名字"，不认成员访问

    `console.log(...)` / `el.appendChild(...)` 里的 `log` / `appendChild` 是**方法名**，
    它们"不在 src 里定义"是完全正常的（宿主/内建 API）——把它们当"守卫失效"会大面积误报。
    （实测：不排除成员访问时，一条 `console.log` 就能造出假 FAIL。）

    ⇒ 做法：先把 `.方法名(` 这类**成员方法调用**从候选里剔除，再提取。
    """
    found: list[str] = []
    # 先收集"成员访问的方法名"，这些一律跳过
    member_names = {m.group(1) for m in re.finditer(r"\.\s*([A-Za-z_$][\w$]*)\s*\(", literal)}
    member_names |= {m.group(1) for m in re.finditer(r"\.\s*([A-Za-z_$][\w$]*)", literal)}

    for pat in _SYMBOL_PATTERNS:
        for m in pat.finditer(literal):
            name = m.group(1)
            if name in _GENERIC or name in member_names or name in found:
                continue
            if len(name) <= 2:
                continue
            found.append(name)
        if found:
            break  # 取到最贴合的那一类即可
    return found


def check_tests(
    len_threshold: int = DEFAULT_LEN_THRESHOLD,
    max_symbols: int = MAX_CONTRACT_SYMBOLS,
) -> dict:
    corpus, _ = _src_corpus()
    over_symbol_asserts: list[dict] = []  # 主判据：符号数超标
    long_asserts: list[dict] = []  # 辅助：长度超阈值（只用于报告排序）
    broken_guards: list[dict] = []
    total_source_asserts = 0

    for path in sorted(TESTS.rglob("test_*.py")):
        items = _extract_assert_strings(path)
        total_source_asserts += len(items)
        for item in items:
            lit = item["literal"]
            rel = _display_rel(path, REPO)

            # ── WARN 主判据：符号数 > max_symbols（押了超过契约点的细节）──
            syms = _symbols_in_literal(lit)
            if len(syms) > max_symbols and not _ENUM_HINTS.match(lit):
                over_symbol_asserts.append(
                    {
                        "file": rel,
                        "line": item["line"],
                        "symbols": syms,
                        "symbol_count": len(syms),
                        "length": len(lit),
                        "literal": lit[:160],
                    }
                )

            # ── WARN 辅助信号：长度（不单独判违规，只帮定位）────────────
            if len(lit) >= len_threshold and not _ENUM_HINTS.match(lit):
                long_asserts.append(
                    {
                        "file": rel,
                        "line": item["line"],
                        "length": len(lit),
                        "literal": lit[:120],
                    }
                )

            # ── FAIL 级：符号已失效（守卫指的东西没了）──────────────────
            # 只在"字面量足够短（像单个符号）"或"能提取到明确符号"时判，
            # 避免把整行中文文案里的词当成符号去 src 里找（必然找不到）。
            for sym in syms:
                if sym not in corpus:
                    broken_guards.append(
                        {
                            "file": rel,
                            "line": item["line"],
                            "symbol": sym,
                            "literal": lit[:120],
                        }
                    )
                    break  # 一条断言只报一个最主要失效符号

    over_symbol_asserts.sort(key=lambda x: (-x["symbol_count"], -x["length"]))
    long_asserts.sort(key=lambda x: -x["length"])
    return {
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "schema": "test-guard-check/v2",
        "criteria": {
            "primary": f"symbol_count > {max_symbols}（押了超过契约点的细节）",
            "auxiliary": f"literal length >= {len_threshold}（仅用于报告排序，不单独判违规）",
        },
        "max_symbols": max_symbols,
        "len_threshold": len_threshold,
        "total_source_asserts": total_source_asserts,
        "over_symbol_asserts": over_symbol_asserts,
        "over_symbol_count": len(over_symbol_asserts),
        "long_asserts": long_asserts,
        "long_count": len(long_asserts),
        "broken_guards": broken_guards,
        "broken_count": len(broken_guards),
    }


def _self_test() -> int:
    """证红/证绿：证明本检查器有判别力（不是"永远绿"）。"""
    global TESTS, SRC
    tmp = Path(tempfile.mkdtemp(prefix="test-guard-selftest-"))
    fake_tests = tmp / "tests"
    fake_src = tmp / "src"
    fake_tests.mkdir(parents=True)
    fake_src.mkdir(parents=True)

    # src 里只定义 realSymbol
    (fake_src / "app.js").write_text(
        "function realSymbol(x) { return x; }\nvar KEEP_ME_ALIVE = 1;\n", encoding="utf-8"
    )

    # 绿的守卫：引用真实存在的符号 + 短
    (fake_tests / "test_green.py").write_text(
        "def test_ok():\n"
        "    src = ''\n"
        "    assert 'function realSymbol' in src\n"
        "    assert 'KEEP_ME_ALIVE' in src\n",
        encoding="utf-8",
    )
    # 红的守卫：符号在 src 里不存在
    (fake_tests / "test_red_symbol.py").write_text(
        "def test_broken():\n"
        "    src = ''\n"
        "    assert 'renamedAwayForever(alpha, beta)' in src\n",
        encoding="utf-8",
    )
    # WARN 守卫：**符号数超标**（押了好几个本项目符号 —— 这才是主判据要抓的）
    (fake_tests / "test_warn_symbols.py").write_text(
        "def test_too_many_symbols():\n"
        "    src = ''\n"
        "    assert 'realSymbol(1); KEEP_ME_ALIVE = 2; var wrapTurn = function () { return 3; };' in src\n"
        "    assert 'noSuchSymbolA(1) and noSuchSymbolB(2) and noSuchSymbolC(3)' in src\n",
        encoding="utf-8",
    )

    old_tests, old_src = TESTS, SRC
    try:
        TESTS, SRC = fake_tests, fake_src
        r = check_tests(len_threshold=DEFAULT_LEN_THRESHOLD, max_symbols=MAX_CONTRACT_SYMBOLS)
    finally:
        TESTS, SRC = old_tests, old_src

    ok_sym = r["broken_count"] >= 1, f"符号失效 ⇒ FAIL (broken={r['broken_count']})"
    ok_long = r["over_symbol_count"] >= 1, f"符号数超标 ⇒ WARN (over_symbol={r['over_symbol_count']})"
    green_clean = not any(g["file"].endswith("test_green.py") for g in r["broken_guards"]), (
        "绿守卫（引用真实符号）不得被判 FAIL"
    )
    all_ok = ok_sym[0] and ok_long[0] and green_clean
    print(f"[{'OK' if ok_sym[0] else 'FAIL'}] {ok_sym[1]}")
    print(f"[{'OK' if ok_long[0] else 'FAIL'}] {ok_long[1]}")
    print(f"[{'OK' if green_clean else 'FAIL'}] 合法守卫不误报")
    print(f"\n== SELF-TEST: {'PASS' if all_ok else 'FAIL'} ==")
    return 0 if all_ok else 2


def main() -> int:
    ap = argparse.ArgumentParser(description="测试结构守卫机检（B-test-literal-4）")
    ap.add_argument("--json", default="")
    ap.add_argument("--strict", action="store_true", help="WARN 也算失败（清债模式）")
    ap.add_argument("--symbols-only", action="store_true", help="只跑 FAIL 级（符号失效）")
    ap.add_argument("--len-threshold", type=int, default=DEFAULT_LEN_THRESHOLD)
    ap.add_argument("--max-symbols", type=int, default=MAX_CONTRACT_SYMBOLS)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return _self_test()

    r = check_tests(len_threshold=args.len_threshold, max_symbols=args.max_symbols)

    print("== 测试结构守卫机检（B-test-literal-4）==")
    print(f"源码字面量断言总数: {r['total_source_asserts']}")
    print(f"主判据 {r['criteria']['primary']}: {r['over_symbol_count']} 条")
    print(f"辅助信号 {r['criteria']['auxiliary']}: {r['long_count']} 条")
    print(f"符号已失效（FAIL）: {r['broken_count']}")
    print()

    if not args.symbols_only and r["over_symbol_asserts"]:
        print("── WARN：符号数超标（押了超过契约点的细节，建议收窄到 ≤2 符号）──")
        for a in r["over_symbol_asserts"][:25]:
            print(f"  {a['file']}:{a['line']}  [{a['symbol_count']}符号/{a['length']}字符]")
            print(f"      符号: {a['symbols']}")
            print(f"      原文: {a['literal'][:120]}")
        if r["over_symbol_count"] > 25:
            print(f"  … 其余 {r['over_symbol_count'] - 25} 条见 --json")

    if r["broken_guards"]:
        print()
        print("── FAIL：守卫引用的符号在 src 中已不存在（该守卫已测不到任何东西）──")
        for b in r["broken_guards"]:
            print(f"  {b['file']}:{b['line']}  符号 {b['symbol']!r}  ← {b['literal'][:80]}")

    failed = r["broken_count"] > 0 or (args.strict and r["over_symbol_count"] > 0)
    print()
    status = "FAIL" if failed else "PASS"
    print(
        f"== RESULT: {status} ==  "
        f"(FAIL={r['broken_count']}  WARN={r['over_symbol_count']}  "
        f"辅助长度信号={r['long_count']})"
    )

    if args.json:
        out = Path(args.json) if os.path.isabs(args.json) else REPO / args.json
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote: {out}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
