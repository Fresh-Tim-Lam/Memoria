"""task-134 只读审计：找出 JS 文件里「IIFE 顶层 return 之后」的代码块并分类。

分类（对齐 task-134）：
  A  = function 声明（hoist ⇒ 活）
  A' = 活函数（hoist）但引用了死区 const/let（TDZ 崩溃风险）—— 含死区内与死区外的函数
  B  = 顶层 const/let/var/赋值/表达式/IIFE 语句 ⇒ 死代码

只读：不修改任何源码。输出 JSON 供报告与清单使用。

用法：python audit_deadcode.py --json out.json [file ...]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

APP = Path(r"D:\AAA_Jupyter\Memoria\src\memoria\ui\static\app\js")

PUNCT = set("{}()[];,.=:+-*/%<>!&|?~^")
REGEX_PREV = set("(,=:[!&|?{};+-*%<>~^")
KEYWORDS_BEFORE_REGEX = {
    "return", "typeof", "instanceof", "in", "of", "new", "delete", "void", "case",
    "do", "else", "yield", "await", "throw",
}
DECL_KINDS = {"const", "let", "var"}


class Tok:
    __slots__ = ("kind", "value", "line", "depth")

    def __init__(self, kind, value, line, depth):
        self.kind = kind
        self.value = value
        self.line = line
        self.depth = depth

    def __repr__(self):
        return f"{self.kind}:{self.value!r}@L{self.line}/d{self.depth}"


def tokenize(text: str) -> list[Tok]:
    toks: list[Tok] = []
    i, n, line, depth = 0, len(text), 1, 0
    prev: Tok | None = None
    while i < n:
        ch = text[i]
        if ch in "\r\n":
            line += 1
            i += 1
            continue
        if ch in " \t":
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] not in "\r\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                if text[i] == "\n":
                    line += 1
                i += 1
            i += 2
            continue
        if ch in "\"'`":
            quote = ch
            j = i + 1
            start_line = line
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == quote:
                    j += 1
                    break
                if text[j] == "\n":
                    line += 1
                j += 1
            tok = Tok("str", text[i:j], start_line, depth)
            toks.append(tok)
            prev = tok
            i = j
            continue
        if ch == "/" and (
            prev is None
            or (prev.kind == "punct" and prev.value in REGEX_PREV)
            or (prev.kind == "word" and prev.value in KEYWORDS_BEFORE_REGEX)
        ):
            j = i + 1
            in_class = False
            while j < n:
                c = text[j]
                if c == "\\":
                    j += 2
                    continue
                if c == "[":
                    in_class = True
                elif c == "]":
                    in_class = False
                elif c == "/" and not in_class:
                    j += 1
                    break
                elif c == "\n":
                    break
                j += 1
            tok = Tok("regex", text[i:j], line, depth)
            toks.append(tok)
            prev = tok
            i = j
            continue
        if ch.isalpha() or ch in "$_":
            j = i
            while j < n and (text[j].isalnum() or text[j] in "$_"):
                j += 1
            tok = Tok("word", text[i:j], line, depth)
            toks.append(tok)
            prev = tok
            i = j
            continue
        if ch.isdigit():
            j = i
            while j < n and (text[j].isalnum() or text[j] in "._"):
                j += 1
            tok = Tok("num", text[i:j], line, depth)
            toks.append(tok)
            prev = tok
            i = j
            continue
        if ch == "{":
            toks.append(Tok("punct", "{", line, depth))
            depth += 1
            prev = toks[-1]
            i += 1
            continue
        if ch == "}":
            depth = max(0, depth - 1)
            toks.append(Tok("punct", "}", line, depth))
            prev = toks[-1]
            i += 1
            continue
        toks.append(Tok("punct", ch, line, depth))
        prev = toks[-1]
        i += 1
    return toks


def match_brace(toks: list[Tok], idx: int) -> int:
    """idx 指向 `{`，返回配对 `}` 的下标。"""
    depth = 0
    for j in range(idx, len(toks)):
        t = toks[j]
        if t.kind == "punct" and t.value == "{":
            depth += 1
        elif t.kind == "punct" and t.value == "}":
            depth -= 1
            if depth == 0:
                return j
    raise ValueError("unbalanced braces")


def find_iifes(toks: list[Tok]) -> list[dict]:
    """找形如 `= (function (...) { ... })` / 文件首 `(function (...) {` 的 IIFE。"""
    out = []
    for i, t in enumerate(toks):
        if not (t.kind == "word" and t.value == "function"):
            continue
        if i < 1 or not (toks[i - 1].kind == "punct" and toks[i - 1].value == "("):
            continue
        # function 之后必须是 (参数) 或 直接 {
        j = i + 1
        if j < len(toks) and toks[j].kind == "punct" and toks[j].value == "(":
            # 跳过参数表
            depth = 0
            while j < len(toks):
                if toks[j].kind == "punct" and toks[j].value == "(":
                    depth += 1
                elif toks[j].kind == "punct" and toks[j].value == ")":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
        if j >= len(toks) or not (toks[j].kind == "punct" and toks[j].value == "{"):
            continue
        body_start = j
        body_end = match_brace(toks, body_start)
        body_depth = toks[body_start].depth + 1
        # 只当它是「模块级」IIFE：body 必须在 depth 0/1 且不是函数体嵌套过深
        if toks[body_start].depth > 1:
            continue
        out.append(
            {
                "start_line": t.line,
                "body_start_idx": body_start,
                "body_end_idx": body_end,
                "end_line": toks[body_end].line,
                "body_depth": body_depth,
            }
        )
    return out


def statement_start_after(toks: list[Tok], ret_idx: int) -> int:
    """返回 return 语句结束后的下一个 token 下标（跳过到同深度的 `;` 之后）。"""
    depth = toks[ret_idx].depth
    j = ret_idx + 1
    while j < len(toks):
        t = toks[j]
        if t.kind == "punct" and t.value == ";" and t.depth == depth:
            return j + 1
        if t.depth < depth:
            return j
        j += 1
    return j


def top_level_statements(toks: list[Tok], start: int, end: int, body_depth: int) -> list[dict]:
    """把 [start,end) 内 body_depth 的顶层语句切块（function 声明整块 / 到同层 `;` 为止）。"""
    stmts = []
    i = start
    while i < end:
        t = toks[i]
        if t.depth < body_depth:
            break
        if t.depth > body_depth:
            i += 1
            continue
        # 语句开始
        first = toks[i]
        j = i
        if first.kind == "word" and first.value == "function":
            fn_idx = i
        elif (
            first.kind == "word"
            and first.value == "async"
            and i + 1 < end
            and toks[i + 1].kind == "word"
            and toks[i + 1].value == "function"
        ):
            fn_idx = i + 1
        else:
            fn_idx = None
        if fn_idx is not None:
            # 函数声明：找到函数体 { 并跳过整块
            k = fn_idx
            while k < end and not (toks[k].kind == "punct" and toks[k].value == "{"):
                k += 1
            if k < end:
                close = match_brace(toks, k)
                j = close + 1
            else:
                j = end
            kind = "function-decl"
        elif first.kind == "punct" and first.value == ";":
            i += 1
            continue
        elif first.kind == "word" and first.value in DECL_KINDS:
            # 跳过声明到同层分号
            j = i + 1
            while j < end and not (toks[j].kind == "punct" and toks[j].value == ";" and toks[j].depth == body_depth):
                j += 1
            j += 1
            kind = "decl"
        else:
            # 表达式/赋值/IIFE 调用：找同层分号
            j = i + 1
            while j < end and not (toks[j].kind == "punct" and toks[j].value == ";" and toks[j].depth == body_depth):
                j += 1
            j += 1
            kind = "stmt"
        stmts.append(
            {
                "kind": kind,
                "start_idx": i,
                "end_idx": min(j, end),
                "start_line": first.line,
                "end_line": toks[min(j - 1, end - 1)].line,
                "first_words": " ".join(x.value for x in toks[i : min(i + 8, len(toks))] if x.kind in ("word", "punct"))[:160],
            }
        )
        i = max(j, i + 1)
    return stmts


def function_name(toks: list[Tok], start_idx: int) -> str:
    # start_idx 可能是 `async`（此时函数名在 `function` 之后），也可能是 `function`
    begin = start_idx
    if toks[begin].kind == "word" and toks[begin].value == "async":
        begin += 1
    for j in range(begin + 1, min(begin + 5, len(toks))):
        t = toks[j]
        if t.kind == "punct" and t.value == "(":
            break
        if t.kind == "word":
            return t.value
    return "<anonymous>"


def preceding_comments(lines: list[str], start_line: int, max_lines: int = 14) -> list[str]:
    """语句上方紧邻的注释块（最多 max_lines 行，遇到非注释非空行即停）。"""
    out: list[str] = []
    i = start_line - 2  # 0-based 上一行
    while i >= 0 and len(out) < max_lines:
        s = lines[i].strip()
        if s.startswith("//"):
            out.append(s)
            i -= 1
            continue
        if not s:
            # 允许注释块之前的空行（只跳过已收集注释之间的空行）
            if out:
                break
            i -= 1
            continue
        break
    return list(reversed(out))


def declared_names(stmts: list[dict], toks: list[Tok]) -> dict[str, int]:
    names: dict[str, int] = {}
    for s in stmts:
        if s["kind"] != "decl":
            continue
        seg = toks[s["start_idx"] : s["end_idx"]]
        words = [t for t in seg if t.kind == "word"]
        # 取声明关键字后的第一个标识符；同时扫 `, name =` 形式
        for k, t in enumerate(words):
            if t.value in DECL_KINDS and k + 1 < len(words):
                names.setdefault(words[k + 1].value, s["start_line"])
                break
    return names


def function_refs(toks: list[Tok], start_idx: int, end_idx: int) -> set[str]:
    return {t.value for t in toks[start_idx:end_idx] if t.kind == "word"}


def analyze_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    toks = tokenize(text)
    lines = text.splitlines()
    iifes = find_iifes(toks)
    result = {"file": path.name, "iifes": [], "issues": []}
    for iface in iifes:
        # 找 IIFE 体内「同层、无条件」return
        returns = []
        for idx in range(iface["body_start_idx"] + 1, iface["body_end_idx"]):
            t = toks[idx]
            if t.kind == "word" and t.value == "return" and t.depth == iface["body_depth"]:
                line_text = lines[t.line - 1].strip() if t.line - 1 < len(lines) else ""
                conditional = bool(re.search(r"\bif\s*\(", line_text)) or line_text.startswith("else")
                returns.append({"idx": idx, "line": t.line, "conditional": conditional, "line_text": line_text[:120]})
        if not returns:
            result["iifes"].append({"start_line": iface["start_line"], "end_line": iface["end_line"], "returns": []})
            continue
        # 只对「最后一个无条件 return」之后的区域做死代码分析
        last = [r for r in returns if not r["conditional"]]
        info = {"start_line": iface["start_line"], "end_line": iface["end_line"], "returns": returns, "dead_zone": None}
        if last:
            ret = last[-1]
            zone_start = statement_start_after(toks, ret["idx"])
            stmts = top_level_statements(toks, zone_start, iface["body_end_idx"], iface["body_depth"])
            if stmts:
                names = declared_names(stmts, toks)
                alive_fns = []
                dead_stmts = []
                for s in stmts:
                    if s["kind"] == "function-decl":
                        s["name"] = function_name(toks, s["start_idx"])
                        s["refs"] = sorted(function_refs(toks, s["start_idx"], s["end_idx"]))
                        s["tdz"] = sorted(names.keys() & set(s["refs"]))
                        alive_fns.append(s)
                    else:
                        dead_stmts.append(s)
                # 死区外的函数若引用死区 const ⇒ 也 A'（同一 TDZ 风险）
                external_tdz = []
                for idx in range(0, len(toks)):
                    if idx >= zone_start and idx < iface["body_end_idx"]:
                        continue
                    t = toks[idx]
                    if t.kind == "word" and t.value in names and t.depth >= 1:
                        # 引用点所在行（排除声明本身）
                        external_tdz.append({"name": t.value, "line": t.line, "decl_line": names[t.value]})
                info["dead_zone"] = {
                    "return_line": ret["line"],
                    "return_line_text": ret["line_text"],
                    "start_line": toks[zone_start].line if zone_start < len(toks) else None,
                    "end_line": toks[iface["body_end_idx"]].line,
                    "dead_stmts": [
                        {
                            "type": s["kind"],
                            "lines": f"{s['start_line']}-{s['end_line']}",
                            "first": s["first_words"],
                            "comments": preceding_comments(lines, s["start_line"]),
                        }
                        for s in dead_stmts
                    ],
                    "alive_fn_decls": [
                        {"name": s["name"], "lines": f"{s['start_line']}-{s['end_line']}", "tdz_refs": s["tdz"]}
                        for s in alive_fns
                    ],
                    "dead_declared_names": names,
                    "external_refs_to_dead_names": external_tdz,
                }
                if dead_stmts or any(s["tdz"] for s in alive_fns):
                    result["issues"].append(
                        {
                            "type": "iife-return-dead-code",
                            "return_line": ret["line"],
                            "dead_zone_lines": f"{toks[zone_start].line}-{toks[iface['body_end_idx']].line}",
                            "dead_stmt_count": len(dead_stmts),
                            "tdz_alive_fns": [s["name"] for s in alive_fns if s["tdz"]],
                        }
                    )
        result["iifes"].append(info)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("files", nargs="*")
    args = ap.parse_args()
    files = [Path(f) for f in args.files] if args.files else sorted(APP.glob("*.js"))
    out = {"files": []}
    for f in files:
        try:
            out["files"].append(analyze_file(f))
        except Exception as exc:  # noqa: BLE001
            out["files"].append({"file": f.name, "error": str(exc)})
    Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in out["files"]:
        issues = row.get("issues") or []
        if issues:
            print(f"[DEAD] {row['file']}: {issues}")
        elif row.get("error"):
            print(f"[ERR ] {row['file']}: {row['error']}")
        else:
            print(f"[ok  ] {row['file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
