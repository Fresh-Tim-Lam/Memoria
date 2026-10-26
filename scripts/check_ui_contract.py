#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UI 契约机检（ui-designer，2026-10-26）。

把 `docs/conventions/ui-contract.md` 里的**机器可读登记块**当作单一事实源，
对照样式层（`src/memoria/ui/static/{app/css,theme}/**` 与前端 JS）检查硬约束。

约束（每条都有必红 fixture，见 `--selftest`）：
  C1 `!important`         —— 只允许契约里登记过豁免的用法（每条带理由）
  C2 硬编码颜色           —— 必须 `var(--token)`；token 定义文件豁免
  C3 魔法 px              —— 字号/行高必须 rem；圆角/间距必须落在既有栅格档
  C4 双源范围常量          —— JS 里同一 min/max 只许一处事实源；外部守卫必须同口径
  C5 z-index              —— CSS 里的每个 z-index 都必须在契约层表里登记
  C6 内联 SVG 图标规格     —— viewBox / 尺寸 / currentColor / 13px 结构 / 状态差异 / 可发现性
  C7 主题 token 一致性     —— 未定义且无兜底 / 仅浅色定义 / 颜色 token 浅色未覆盖

用法：
  python scripts/check_ui_contract.py                    # 对基线跑（新增 FAIL ⇒ 退出码 1）
  python scripts/check_ui_contract.py --selftest         # 内置 fixture 自测（每条约束必红 + 正例必绿）
  python scripts/check_ui_contract.py --json out.json     # 机器可读输出
  python scripts/check_ui_contract.py --update-baseline  # 重落基线（只允许"变小"，变大需 --force）
  python scripts/check_ui_contract.py --strict           # 基线项也算 FAIL（清零目标）
  python scripts/check_ui_contract.py --token-table      # 打印主题 token 清单（markdown）
  python scripts/check_ui_contract.py --suggest          # 打印契约登记块的初始骨架（JSON）

退出码：0 通过（WARN 不阻断）；1 有新增 FAIL / --strict 下有残留；2 契约文件不可解析。
"""
from __future__ import annotations

import argparse
import bisect
import io
import json
import os
import re
import sys
import tempfile
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACT_DEFAULT = os.path.join(ROOT, "docs", "conventions", "ui-contract.md")
BASELINE_DEFAULT = os.path.join(ROOT, "artifacts", "agent", "verify", "ui", "ui-contract-baseline.json")
STATIC = os.path.join(ROOT, "src", "memoria", "ui", "static")
CSS_FILES = [
    "app/css/app.css",
    "theme/memoria.css",
    "theme/light.css",
    "theme/mermaid.css",
]
TOKEN_FILES = ["theme/memoria.css", "theme/light.css"]

RULES = {
    "C1": "禁止 !important（除登记豁免）",
    "C2": "禁止硬编码颜色",
    "C3": "禁止魔法数字 px",
    "C4": "禁止双源范围常量",
    "C5": "z-index 必须登记",
    "C6": "内联 SVG 图标规格",
    "C7": "主题 token 一致性",
}

# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------


class LineIndex:
    """偏移量 → 行号（1-based），bisect 实现，避免逐次 count 的 O(n²)。"""

    def __init__(self, text: str) -> None:
        self.starts = [0]
        for m in re.finditer("\n", text):
            self.starts.append(m.end())

    def line(self, pos: int) -> int:
        return bisect.bisect_right(self.starts, pos)


def _read(path: str) -> str:
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def strip_comments(text: str) -> str:
    """把 /* … */ 换成等长空白（保留换行与偏移），避免注释里的示例被当成违规。"""

    def repl(m: re.Match) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    return re.sub(r"/\*.*?\*/", repl, text, flags=re.S)


def strip_js_comments(text: str) -> str:
    """剥 JS 注释（先块注释再行注释；保留换行/偏移）—— 用于 C4 这类"按代码字面量"检查。

    必须剥：注释里会**提到**常量名与数字（如 `保底 CONTENT_MIN_PX=360` 的说明），
    不剥会把注释误报成第二个事实源。
    """
    clean = strip_comments(text)

    def repl_line(m: re.Match) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    return re.sub(r"//[^\n]*", repl_line, clean)


def norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def rel_of(path: str) -> str:
    return os.path.relpath(path, STATIC).replace("\\", "/")


def parse_css(text: str) -> dict:
    """返回 {"decls": [...], "rules": [{selector, line, decls:[...]}]}。

    支持 `@media` / `@supports` / `@keyframes` 嵌套；注释先剥掉（保留偏移）。
    实现为线性扫描（按 `{};` 切段），避免 `buf += ch` 的二次复杂度。
    """
    clean = strip_comments(text)
    idx = LineIndex(clean)
    decls: list = []
    rules: list = []
    stack: list = []  # [{"kind", "text", "rule"}]
    seg_start = 0
    for m in re.finditer(r"[{};]", clean):
        seg = clean[seg_start:m.start()]
        seg_pos = seg_start + (len(seg) - len(seg.lstrip()))
        ch = m.group(0)
        if ch == "{":
            head = seg.strip()
            kind = "atrule" if head.startswith("@") else "rule"
            rule_obj = None
            if kind == "rule":
                rule_obj = {"selector": head, "line": idx.line(seg_pos), "decls": []}
                rules.append(rule_obj)
            stack.append({"kind": kind, "text": head, "rule": rule_obj})
        elif ch == "}":
            if stack:
                stack.pop()
        else:  # ';'
            d = seg.strip()
            if ":" in d:
                prop, val = d.split(":", 1)
                prop = prop.strip().lower()
                val = val.strip()
                owner = None
                for node in reversed(stack):
                    if node["kind"] == "rule":
                        owner = node["rule"]
                        break
                if prop and val and owner is not None:
                    decl = {"prop": prop, "value": val, "line": idx.line(seg_pos), "selector": owner["selector"]}
                    decls.append(decl)
                    owner["decls"].append(decl)
        seg_start = m.end()
    return {"decls": decls, "rules": rules}


def parse_color_literals(value: str) -> list:
    """提取声明值里的颜色字面量（排除 url(...) 内部、var() 名称）。"""
    v = re.sub(r"url\([^)]*\)", " ", value)
    v = re.sub(r"var\([^)]*\)", " ", v)
    out = []
    for m in re.finditer(r"#[0-9a-fA-F]{3,8}\b", v):
        out.append(("#", m.group(0).lower()))
    for m in re.finditer(r"\b((?:rgba?|hsla?)\s*\([^)]*\))", v):
        out.append(("fn", norm_ws(m.group(1)).lower()))
    return out


def is_neutral_alpha(literal: str) -> bool:
    return bool(re.match(r"(?:rgba?|hsla?)\s*\(\s*(?:0\s*,\s*0\s*,\s*0|255\s*,\s*255\s*,\s*255)\s*[,/]", literal))


PX_RE = re.compile(r"(?<![\w.-])(-?\d+(?:\.\d+)?)px\b")


# ---------------------------------------------------------------------------
# 契约解析
# ---------------------------------------------------------------------------

BLOCK_RE = re.compile(r"```json[ \t]+ui-contract:([a-z0-9-]+)[ \t]*\r?\n(.*?)```", re.S)


def load_contract(path: str) -> dict:
    text = _read(path)
    blocks = {}
    for m in BLOCK_RE.finditer(text):
        key = m.group(1)
        raw = m.group(2).strip()
        try:
            blocks[key] = json.loads(raw)
        except ValueError as exc:
            raise SystemExit("契约块 `%s` 不是合法 JSON：%s" % (key, exc))
    return blocks


# ---------------------------------------------------------------------------
# findings
# ---------------------------------------------------------------------------


class Finding(dict):
    def __init__(self, rule, severity, file, line, selector, detail, prop="", value="", extra=""):
        super().__init__(
            rule=rule,
            severity=severity,
            file=file,
            line=line,
            selector=norm_ws(selector),
            prop=prop,
            value=norm_ws(value),
            detail=detail,
            fp="|".join([rule, file, norm_ws(selector), prop, norm_ws(value), extra]),
        )


# ---------------------------------------------------------------------------
# C1 !important
# ---------------------------------------------------------------------------


def check_c1(css_map: dict, contract: dict) -> list:
    exemptions = (contract.get("important-exemptions") or {}).get("exemptions", [])
    out = []
    for rel, parsed in css_map.items():
        for d in parsed["decls"]:
            if "!important" not in d["value"].lower():
                continue
            if re.search(r"\bdata:", d["value"]):
                continue  # data-URI 里的字面量不是 CSS 优先级用途
            hit = None
            sel_norm = norm_ws(d["selector"])
            for ex in exemptions:
                if not re.search(ex.get("file", ""), rel):
                    continue
                needles = ex.get("selector_contains")
                if needles and not any(norm_ws(k) in sel_norm for k in needles):
                    continue
                props = ex.get("prop_in")
                if props and d["prop"] not in props:
                    continue
                hit = ex
                break
            if hit:
                continue
            out.append(
                Finding(
                    "C1",
                    "FAIL",
                    rel,
                    d["line"],
                    d["selector"],
                    "未登记的 !important（需要在契约 important-exemptions 登记理由，或改用特异性/同名覆盖）",
                    d["prop"],
                    d["value"],
                )
            )
    return out


# ---------------------------------------------------------------------------
# C2 硬编码颜色
# ---------------------------------------------------------------------------


def check_c2(css_map: dict, contract: dict) -> list:
    policy = (contract.get("style-policy") or {}).get("colors", {})
    neutral_props = policy.get("neutral_alpha_allowed_props", ["box-shadow", "text-shadow"])
    out = []
    for rel, parsed in css_map.items():
        for d in parsed["decls"]:
            for kind, literal in parse_color_literals(d["value"]):
                if d["prop"].startswith("--"):
                    # 自定义属性定义 = token 定义（theme/*.css 是主题 token 表；app.css 局部 token 如
                    # --shadow-* / --scrollbar-* / --motion-* 也在这里定义）。值里的字面量合法。
                    continue
                if is_neutral_alpha(literal) and d["prop"] in neutral_props:
                    out.append(
                        Finding(
                            "C2", "WARN", rel, d["line"], d["selector"],
                            "中性黑/白 alpha 只允许出现在阴影且应优先走 --shadow-* 令牌",
                            d["prop"], literal,
                        )
                    )
                    continue
                out.append(
                    Finding(
                        "C2", "FAIL", rel, d["line"], d["selector"],
                        "硬编码颜色；应改为 var(--token)（新 token 需先进 theme/*.css 并深浅成对）",
                        d["prop"], literal,
                    )
                )
    return out


# ---------------------------------------------------------------------------
# C3 魔法 px
# ---------------------------------------------------------------------------


def check_c3(css_map: dict, contract: dict) -> list:
    policy = (contract.get("style-policy") or {}).get("px", {})
    rem_only = set(policy.get("rem_only_props", ["font-size", "line-height"]))
    radius_tiers = set(policy.get("radius_tiers_px", [4, 6, 8, 12, 999]))
    spacing_grid = set(policy.get("spacing_grid_px", [0, 2, 4, 6, 8, 10, 12, 14, 16, 20, 24, 32, 40, 48, 64]))
    spacing_props = set(
        policy.get(
            "spacing_props",
            [
                "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
                "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
                "gap", "row-gap", "column-gap",
            ],
        )
    )
    out = []
    for rel, parsed in css_map.items():
        for d in parsed["decls"]:
            prop = d["prop"]
            vals = [float(m.group(1)) for m in PX_RE.finditer(d["value"])]
            if not vals:
                continue
            if prop in rem_only:
                for v in vals:
                    out.append(
                        Finding("C3", "FAIL", rel, d["line"], d["selector"],
                                "字号/行高必须用 rem（跟随“界面缩放/字号”设置），禁止 px",
                                prop, "%spx" % _fmt_num(v))
                    )
            elif prop == "border-radius":
                if not set(vals) <= radius_tiers:
                    bad = sorted(set(vals) - radius_tiers)
                    out.append(
                        Finding("C3", "FAIL", rel, d["line"], d["selector"],
                                "圆角不在档位 %s 内（档位来自 ui-visual-language B-6）" % sorted(radius_tiers),
                                prop, ",".join("%spx" % _fmt_num(v) for v in bad))
                    )
            elif prop in spacing_props:
                bad = sorted(set(vals) - spacing_grid)
                if bad:
                    out.append(
                        Finding("C3", "WARN", rel, d["line"], d["selector"],
                                "间距 px 不在既有栅格 %s 内（越格值会与相邻块对不齐）" % sorted(spacing_grid),
                                prop, ",".join("%spx" % _fmt_num(v) for v in bad))
                    )
    return out


def _fmt_num(v: float) -> str:
    return str(int(v)) if abs(v - int(v)) < 1e-9 else ("%g" % v)


# ---------------------------------------------------------------------------
# C4 双源范围常量
# ---------------------------------------------------------------------------


def check_c4(contract: dict, js_texts: dict) -> list:
    ranges = (contract.get("range-ssot") or {}).get("ranges", [])
    out = []
    for entry in ranges:
        rid = entry["id"]
        ssot_file = entry["ssot_file"]
        ssot_text = js_texts.get(ssot_file)
        if ssot_text is None:
            out.append(Finding("C4", "FAIL", ssot_file, 0, rid,
                               "契约登记了事实源文件，但它不在扫描集里（或不存在）", "", rid))
            continue
        m = re.search(entry["ssot_regex"], strip_js_comments(ssot_text), re.S)
        if not m:
            out.append(Finding("C4", "FAIL", ssot_file, 0, rid,
                               "事实源里找不到登记的 `%s` 定义（正则可能已过期）" % rid, "", rid))
            continue
        ssot_map = _named_nums(m)
        ssot_pair = tuple(ssot_map[k] for k in ssot_map) if ssot_map else _groups_to_nums(m)
        for guard in entry.get("guards", []):
            gfile = guard["file"]
            gtext = js_texts.get(gfile)
            if gtext is None:
                out.append(Finding("C4", "FAIL", gfile, 0, rid, "契约登记的守卫文件不存在", "", rid))
                continue
            gclean = strip_js_comments(gtext)
            gidx = LineIndex(gclean)
            found_any = False
            for gm in re.finditer(guard["regex"], gclean, re.S):
                found_any = True
                gmap = _named_nums(gm)
                line = gidx.line(gm.start())
                if gmap and ssot_map:
                    # 命名组口径：逐字段比对（min/max/def/step…），只比守卫声明了的字段
                    diffs = {k: (ssot_map.get(k), v) for k, v in gmap.items()
                             if k in ssot_map and ssot_map.get(k) != v}
                    shown = ", ".join("%s(事实源 %s / 此处 %s)" % (k, ssot_map.get(k), v)
                                      for k, (_, v) in diffs.items()) or "一致"
                    if diffs:
                        out.append(
                            Finding("C4", "FAIL", gfile, line, rid,
                                    "双源字段已漂移：%s 与事实源 %s 不一致：%s ⇒ 只改一处会静默失效"
                                    % (rid, ssot_file, shown),
                                    rid, repr(diffs), extra="drift." + ".".join(sorted(diffs)))
                        )
                    else:
                        out.append(
                            Finding("C4", "WARN", gfile, line, rid,
                                    "同一范围/默认值在 %s 之外又写了一份（当前一致，但迟早漂移；应收口到单一导出）"
                                    % ssot_file,
                                    rid, repr(gmap), extra="duplicate")
                        )
                else:
                    pair = _groups_to_nums(gm)
                    if pair != ssot_pair:
                        out.append(
                            Finding("C4", "FAIL", gfile, line, rid,
                                    "双源范围已漂移：事实源 %s=%s，此处=%s ⇒ 只改一处会静默失效"
                                    % (ssot_file, ssot_pair, pair),
                                    rid, repr(pair), extra="drift")
                        )
                    else:
                        out.append(
                            Finding("C4", "WARN", gfile, line, rid,
                                    "同一范围在 %s 之外又写了一份（当前一致，但迟早漂移；应收口到单一导出）"
                                    % ssot_file,
                                    rid, repr(pair), extra="duplicate")
                        )
            if not found_any and guard.get("required", True):
                out.append(Finding("C4", "WARN", gfile, 0, rid,
                                   "契约登记的守卫写法已不存在（实现可能已改，需同步契约）", "", rid))
    return out


def _named_nums(m: re.Match) -> dict:
    """取命名捕获组里的数值（int/float）。没有命名组则返回 {}（回退到位置元组比较）。"""
    out = {}
    try:
        groups = m.groupdict()
    except (AttributeError, IndexError):
        return out
    for k, v in groups.items():
        if v is None:
            continue
        try:
            out[k] = float(v) if "." in v else int(v)
        except ValueError:
            continue
    return out


def _groups_to_nums(m: re.Match) -> tuple:
    vals = []
    for g in m.groups():
        if g is None:
            continue
        try:
            vals.append(float(g) if "." in g else int(g))
        except ValueError:
            pass
    return tuple(vals)


# ---------------------------------------------------------------------------
# C5 z-index
# ---------------------------------------------------------------------------


def check_c5(css_map: dict, contract: dict) -> list:
    reg = contract.get("z-index-registry") or {}
    layers = reg.get("layers", [])
    out = []
    seen_layer_ids = set()
    for rel, parsed in css_map.items():
        for d in parsed["decls"]:
            if d["prop"] != "z-index":
                continue
            try:
                z = int(d["value"].strip())
            except ValueError:
                out.append(Finding("C5", "WARN", rel, d["line"], d["selector"],
                                   "z-index 不是整数（无法登记/对账）", d["prop"], d["value"]))
                continue
            sel = norm_ws(d["selector"])
            candidates = [
                l for l in layers
                if int(l.get("z", -999)) == z
                and any(norm_ws(k) in sel for k in l.get("selector_contains", []))
            ]
            if not candidates:
                out.append(
                    Finding("C5", "FAIL", rel, d["line"], d["selector"],
                            "z-index=%d 没有在契约 z-index-registry 登记（登记表是唯一层级事实源）" % z,
                            d["prop"], str(z))
                )
                continue
            seen_layer_ids.add(candidates[0]["id"])
    for layer in layers:
        if layer["id"] not in seen_layer_ids:
            out.append(Finding("C5", "WARN", layer.get("file", ""), 0, layer["id"],
                               "契约登记的层 `%s` 在 CSS 里找不到对应 z-index（登记表可能已过期）" % layer["id"],
                               "", str(layer.get("z"))))
    zmap = {l["id"]: int(l["z"]) for l in layers}
    for rel_entry in reg.get("relations", []):
        upper, lower = rel_entry["upper"], rel_entry["lower"]
        if upper not in zmap or lower not in zmap:
            out.append(Finding("C5", "FAIL", "", 0, rel_entry["id"],
                               "层级关系引用了未登记的层：%s" % rel_entry["id"], "", ""))
            continue
        ok = zmap[upper] > zmap[lower]
        if rel_entry.get("status") == "known-issue":
            out.append(Finding("C5", "WARN", "", 0, rel_entry["id"],
                               "登记在案的层级债务（%s → %s）：%s" % (upper, lower, rel_entry.get("note", "")),
                               "", "%d>%d" % (zmap[upper], zmap[lower]), extra="known-issue"))
        elif not ok:
            out.append(Finding("C5", "FAIL", "", 0, rel_entry["id"],
                               "层级关系被破坏：要求 %s 高于 %s，实际 %d <= %d"
                               % (upper, lower, zmap[upper], zmap[lower]), "", ""))
    return out


# ---------------------------------------------------------------------------
# C6 内联 SVG 图标
# ---------------------------------------------------------------------------

CONCAT_RE = re.compile(r"""["']\s*\+\s*["']""")
SVG_RE = re.compile(r"<svg\b([^>]*)>(.*?)</svg>", re.S)
ATTR_RE = re.compile(r"""([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*("([^"]*)"|'([^']*)')""")


def parse_attrs(text: str) -> dict:
    out = {}
    for m in ATTR_RE.finditer(text):
        out[m.group(1).lower()] = m.group(3) if m.group(3) is not None else m.group(4)
    return out


def scan_icons(js_files: dict) -> list:
    """从 JS/HTML 源里找内联 SVG 图标。返回 [{file,line,dynamic,attrs,children,raw}]。"""
    icons = []
    for rel, text in js_files.items():
        if not rel.endswith((".js", ".html")):
            continue
        flat = CONCAT_RE.sub("", text)
        idx = LineIndex(text)  # 行号按原文（concat 只删引号不删换行 ⇒ 行号一致）
        for m in SVG_RE.finditer(flat):
            attrs_raw, children = m.group(1), m.group(2)
            seg = flat[m.start():m.end()]
            # 动态构建：模板插值 / 三元 / 字符串拼接 / 紧跟 JS 语句（builders 用变量拼 svg）
            dynamic = bool(
                re.search(r"\$\{|\?\s|\+\s*['\"]|;\s*\n\s*(?:if|const|let|var|host|btn|el)\b|classList|innerHTML", seg)
            )
            attrs = parse_attrs(attrs_raw)
            children_info = []
            for cm in re.finditer(r"<(path|rect|line|circle|ellipse|polyline|polygon)\b([^>]*)/?>", children):
                cattrs = parse_attrs(cm.group(2))
                closed = False
                if cm.group(1) == "path":
                    d = cattrs.get("d", "")
                    closed = bool(re.search(r"[zZ]\s*$", d.strip()))
                children_info.append(
                    {
                        "tag": cm.group(1),
                        "attrs": cattrs,
                        "closed": closed,
                        "has_stroke": ("stroke" in cattrs and cattrs["stroke"] != "none")
                        or ("stroke-width" in cattrs and cattrs.get("fill") == "none"),
                        "fill": cattrs.get("fill"),
                    }
                )
            icons.append(
                {"file": rel, "line": idx.line(m.start()), "attrs": attrs,
                 "children": children_info, "dynamic": dynamic, "raw": flat[m.start():m.end()]}
            )
    return icons


def _css_rules_for(parsed_css: dict, selector_contains: str) -> list:
    return [r for r in parsed_css["rules"] if norm_ws(selector_contains) in norm_ws(r["selector"])]


def check_c6(contract: dict, js_files: dict, css_map: dict) -> list:
    reg = (contract.get("icons") or {}).get("icons", [])
    out = []
    icons = scan_icons(js_files)
    matched = set()
    for icon in icons:
        sel = icon["file"]
        hit = None
        for entry in reg:
            if not re.search(entry["file"], sel):
                continue
            needle = entry.get("marker")
            if needle and needle not in icon["raw"]:
                continue
            if not needle and entry.get("dynamic_expected") and not icon["dynamic"]:
                continue
            hit = entry
            break
        if not hit:
            out.append(
                Finding("C6", "FAIL", icon["file"], icon["line"], "inline-svg",
                        "内联 SVG 图标未在契约 icons 登记（新图标必须登记 viewBox/尺寸/颜色/13px 结构/可发现性）",
                        "", "", extra=str(icon["line"]))
            )
            continue
        matched.add(hit["id"])
        ident = hit["id"]
        if hit.get("dynamic_expected"):
            continue  # 动态拼装的构建器只做登记核对
        attrs = icon["attrs"]
        vb = attrs.get("viewbox", "")
        if norm_ws(vb) != norm_ws(hit.get("viewBox", "")):
            out.append(Finding("C6", "FAIL", icon["file"], icon["line"], ident,
                               "viewBox=%r 与契约 %r 不符" % (vb, hit.get("viewBox")),
                               "viewBox", vb, extra=ident))
        size = attrs.get("width")
        want_sizes = [str(s) for s in hit.get("sizes", [])]
        if size and want_sizes and size not in want_sizes:
            out.append(Finding("C6", "FAIL", icon["file"], icon["line"], ident,
                               "渲染尺寸 %r 不在契约档位 %s 内" % (size, want_sizes),
                               "width", size, extra=ident))
        for key in ("fill", "stroke"):
            val = attrs.get(key)
            if val and val != "currentColor" and not (hit.get("allow_fill_values") and val in hit["allow_fill_values"]):
                out.append(Finding("C6", "FAIL", icon["file"], icon["line"], ident,
                                   "%s=%r 不允许（图标颜色必须 currentColor，才能跟随主题/状态色）" % (key, val),
                                   key, val, extra=ident))
        # 13px 结构判据（Lead 2026-10-26 案例：多段细描边会视觉坍缩）
        if size and want_sizes and int(size) <= 13 and not icon["dynamic"]:
            stroke_only = [
                c for c in icon["children"]
                if c["fill"] in (None, "none") and c["has_stroke"] and c["tag"] == "path" and not c["closed"]
            ]
            if len(stroke_only) > 1:
                out.append(Finding("C6", "FAIL", icon["file"], icon["line"], ident,
                                   "图标 `%s`：13px 档用了 %d 条不闭合细描边拼形状 ⇒ 会视觉坍缩；"
                                   "应改为单个闭合轮廓（可配 fill+fill-opacity≥.15）"
                                   % (ident, len(stroke_only)),
                                   "", "", extra=ident))
            filled = [c for c in icon["children"] if c["fill"] not in (None, "none")]
            states = hit.get("states") or []
            # 从契约登记的 CSS 规则核对「浅填充支撑」与「状态差异」
            css_file = hit.get("css_file")
            if css_file and css_file in css_map:
                parsed = css_map[css_file]
                supports = []
                for st in states:
                    rule_sel = st.get("selector_contains")
                    if not rule_sel:
                        continue
                    rules = [r for r in parsed["rules"] if norm_ws(rule_sel) in norm_ws(r["selector"])]
                    got = None
                    for r in rules:
                        for dd in r["decls"]:
                            if dd["prop"] in ("fill-opacity", "opacity"):
                                got = dd["value"].strip()
                    if got is None:
                        out.append(Finding("C6", "FAIL", icon["file"], icon["line"], ident,
                                           "契约声明的状态 `%s` 在 CSS 里找不到 opacity 赋值" % st.get("name", rule_sel),
                                           "", "", extra=ident))
                    else:
                        supports.append((st.get("name", rule_sel), got))
                if len(supports) >= 2:
                    vals = []
                    for _, got in supports:
                        try:
                            vals.append(float(got.replace("!", "").strip()))
                        except ValueError:
                            vals.append(None)
                    nums = [v for v in vals if v is not None]
                    if len(nums) >= 2 and max(nums) - min(nums) < 0.3:
                        out.append(Finding("C6", "FAIL", icon["file"], icon["line"], ident,
                                           "状态间 opacity 差 %s 太小，13px 下状态差异不一眼可分"
                                           % (max(nums) - min(nums)), "", "", extra=ident))
                light = [v for _, v in supports if _float_or_none(v) is not None and _float_or_none(v) >= 0.15]
                if filled and not light:
                    out.append(Finding("C6", "WARN", icon["file"], icon["line"], ident,
                                       "13px 单闭合轮廓未登记任何 fill 支撑（契约建议浅填充 ≥.15 让轮廓立住）",
                                       "", "", extra=ident))
        disc = hit.get("discoverability") or {}
        if disc.get("aria_label") or disc.get("title"):
            symbol = disc.get("symbol")
            body = _symbol_body(js_files.get(icon["file"], ""), symbol) if symbol else ""
            if disc.get("aria_label") and "aria-label" not in body:
                out.append(Finding("C6", "FAIL", icon["file"], icon["line"], ident,
                                   "契约要求图标按钮提供 aria-label，但 `%s` 里找不到" % symbol,
                                   "", "", extra=ident))
            if disc.get("title") and "title" not in body:
                out.append(Finding("C6", "FAIL", icon["file"], icon["line"], ident,
                                   "契约要求图标提供 title（悬停提示），但 `%s` 里找不到" % symbol,
                                   "", "", extra=ident))
    for entry in reg:
        if entry["id"] not in matched and not entry.get("dynamic_expected"):
            out.append(Finding("C6", "WARN", entry.get("file", ""), 0, entry["id"],
                               "契约登记的图标 `%s` 在源码里没找到（登记表可能过期）" % entry["id"],
                               "", "", extra=entry["id"]))
    return out


def _float_or_none(v):
    try:
        return float(str(v).replace("!", "").strip())
    except (TypeError, ValueError):
        return None


def _symbol_body(text: str, symbol: str) -> str:
    """取 `function symbol(...) {...}` 或 `const symbol = ...` 的整段（括号配平）。"""
    m = re.search(r"(?:function\s+%s\s*\([^)]*\)\s*\{|(?:const|let|var)\s+%s\s*=)" % (re.escape(symbol), re.escape(symbol)), text)
    if not m:
        return ""
    start = m.start()
    brace = text.find("{", m.end() - 1)
    if brace == -1:
        return text[start:start + 400]
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return text[start:]


# ---------------------------------------------------------------------------
# C7 主题 token 一致性
# ---------------------------------------------------------------------------


TOKEN_DEF_RE = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;{}]+);")
VAR_USE_RE = re.compile(r"var\(\s*(--[a-z0-9-]+)\s*(,)?")
COLOR_VALUE_RE = re.compile(r"^(#|rgb|hsl)")


def scan_tokens(css_map: dict, js_files: dict) -> dict:
    root = {}
    light = {}
    local = {}
    for rel, parsed in css_map.items():
        for d in parsed["decls"]:
            if not d["prop"].startswith("--"):
                continue
            if rel == "theme/memoria.css":
                root.setdefault(d["prop"], d["value"].strip())
            elif rel == "theme/light.css":
                light.setdefault(d["prop"], d["value"].strip())
            elif rel == "app/css/app.css":
                local.setdefault(d["prop"], d["value"].strip())
    return {"root": root, "light": light, "local": local}


def check_c7(css_map: dict, contract: dict, js_files: dict) -> list:
    policy = (contract.get("token-policy") or {})
    js_written = set(policy.get("js_written_tokens", []))
    ignore = set(policy.get("ignore_undefined_tokens", []))
    tokens = scan_tokens(css_map, js_files)
    root, light, local = tokens["root"], tokens["light"], tokens["local"]
    out = []
    # 7a/7b：var() 引用检查（只看结构样式文件，token 定义文件里的 var 是别名）
    for rel, parsed in css_map.items():
        if rel in TOKEN_FILES:
            continue
        for d in parsed["decls"]:
            for m in VAR_USE_RE.finditer(d["value"]):
                name, has_fb = m.group(1), bool(m.group(2))
                if name in ignore:
                    continue
                defined_dark = name in root or name in local or name in js_written
                defined_light_only = (name in light) and (name not in root)
                if has_fb:
                    if not defined_dark:
                        out.append(Finding("C7", "WARN", rel, d["line"], d["selector"],
                                           "`%s` 未定义，仅靠兜底值（深浅主题下都走 fallback，属未收口）" % name,
                                           d["prop"], name, extra=name))
                    continue
                if defined_light_only:
                    out.append(Finding("C7", "FAIL", rel, d["line"], d["selector"],
                                       "`%s` 只在浅色主题定义、深色无定义且此处无兜底 ⇒ 深色下该声明失效"
                                       % name, d["prop"], name, extra=name))
                elif not defined_dark:
                    out.append(Finding("C7", "FAIL", rel, d["line"], d["selector"],
                                       "`%s` 未在 theme/memoria.css(:,local/JS) 定义且无兜底 ⇒ 该声明在运行期无效"
                                       % name, d["prop"], name, extra=name))
    # 7c：颜色 token 浅色未覆盖
    for name, val in sorted(root.items()):
        if not COLOR_VALUE_RE.match(val.strip()):
            continue
        if name in light:
            continue
        out.append(Finding("C7", "WARN", "theme/light.css", 0, "light-override",
                           "颜色 token `%s` 没有浅色覆盖 ⇒ 浅色主题沿用深色取值（%s）" % (name, val),
                           name, val, extra=name))
    return out


# ---------------------------------------------------------------------------
# 基线
# ---------------------------------------------------------------------------


def load_baseline(path: str) -> list:
    if not os.path.exists(path):
        return []
    data = json.loads(_read(path))
    return data.get("findings", [])


def apply_baseline(findings: list, baseline: list) -> dict:
    base_fps = {f["fp"]: f for f in baseline}
    cur_fps = set()
    rows = []
    for f in findings:
        status = "baseline" if f["fp"] in base_fps else "new"
        cur_fps.add(f["fp"])
        rows.append(dict(f, status=status))
    fixed = [f for f in baseline if f["fp"] not in cur_fps]
    return {"rows": rows, "fixed": fixed}


def summarize(rows: list) -> dict:
    out = {}
    for r in rows:
        key = (r["rule"], r["severity"], r["status"])
        out[key] = out.get(key, 0) + 1
    return out


# ---------------------------------------------------------------------------
# 渲染输出
# ---------------------------------------------------------------------------


def render_human(result: dict, baseline_path: str) -> str:
    rows, fixed = result["rows"], result["fixed"]
    lines = []
    lines.append("== UI 契约机检 ==")
    lines.append("契约：%s" % result["contract_path"])
    lines.append("基线：%s" % baseline_path)
    total = summarize(rows)
    new_fail = sum(1 for r in rows if r["status"] == "new" and r["severity"] == "FAIL")
    new_warn = sum(1 for r in rows if r["status"] == "new" and r["severity"] == "WARN")
    base_fail = sum(1 for r in rows if r["status"] == "baseline" and r["severity"] == "FAIL")
    base_warn = sum(1 for r in rows if r["status"] == "baseline" and r["severity"] == "WARN")
    lines.append(
        "现状：新增 FAIL=%d / 新增 WARN=%d ｜ 基线内 FAIL=%d / WARN=%d ｜ 已修复=%d"
        % (new_fail, new_warn, base_fail, base_warn, len(fixed))
    )
    for rule in sorted(RULES):
        parts = []
        for sev in ("FAIL", "WARN"):
            for status in ("new", "baseline"):
                n = total.get((rule, sev, status), 0)
                if n:
                    parts.append("%s%s=%d" % (sev, "·new" if status == "new" else "", n))
        if parts:
            lines.append("  %s %-14s %s" % (rule, RULES[rule], " ".join(parts)))
    show = [r for r in rows if r["status"] == "new"] + [r for r in rows if r["status"] == "baseline"]
    if show:
        lines.append("")
        lines.append("-- 明细（新增在前；基线条目完整清单见 --json 产物）--")
        for r in show[:400]:
            tag = "NEW " if r["status"] == "new" else "base"
            lines.append("  [%s][%s][%s] %s:%s  %s  %s%s" % (
                tag, r["severity"], r["rule"], r["file"], r["line"],
                (r["selector"] or "")[:38],
                r["detail"],
                ("  <%s:%s>" % (r["prop"], r["value"])) if r["prop"] else "",
            ))
        if len(show) > 400:
            lines.append("  … 其余 %d 条省略（--json 看全量）" % (len(show) - 400))
    if fixed:
        lines.append("")
        lines.append("-- 已修复（基线里有、本次没了）--")
        for f in fixed[:80]:
            lines.append("  [fixed][%s][%s] %s:%s %s" % (f["severity"], f["rule"], f["file"], f["line"], f["detail"][:90]))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def collect(contract_path: str = CONTRACT_DEFAULT) -> tuple:
    contract = load_contract(contract_path) if os.path.exists(contract_path) else {}
    css_map = {}
    for rel in CSS_FILES:
        path = os.path.join(STATIC, rel.replace("/", os.sep))
        if not os.path.exists(path):
            continue
        css_map[rel] = parse_css(_read(path))
    js_files = {}
    js_root = os.path.join(STATIC, "app", "js")
    if os.path.isdir(js_root):
        for fn in sorted(os.listdir(js_root)):
            if fn.endswith(".js"):
                rel = "app/js/" + fn
                js_files[rel] = _read(os.path.join(js_root, fn))
    index = os.path.join(STATIC, "app", "index.html")
    if os.path.exists(index):
        js_files["app/index.html"] = _read(index)
    findings = []
    findings += check_c1(css_map, contract)
    findings += check_c2(css_map, contract)
    findings += check_c3(css_map, contract)
    findings += check_c4(contract, js_files)
    findings += check_c5(css_map, contract)
    findings += check_c6(contract, js_files, css_map)
    findings += check_c7(css_map, contract, js_files)
    return contract, css_map, js_files, findings


def cmd_token_table(contract_path: str) -> str:
    contract, css_map, _, _ = collect(contract_path)
    tokens = scan_tokens(css_map, {})
    root, light, local = tokens["root"], tokens["light"], tokens["local"]
    uses = {}
    for rel, parsed in css_map.items():
        for d in parsed["decls"]:
            for m in VAR_USE_RE.finditer(d["value"]):
                uses[m.group(1)] = uses.get(m.group(1), 0) + 1
    lines = ["| token | 用途（按命名归类） | 深色 | 浅色 | 使用次数 |", "|---|---|---|---|---|"]
    for name in sorted(set(root) | set(light) | set(local)):
        if name in local and name not in root:
            continue
        dark = root.get(name, "（未定义，走兜底）" if name in light else "（未定义）")
        lite = light.get(name, "（沿用深色）")
        lines.append("| `%s` | %s | `%s` | `%s` | %d |" % (name, _token_purpose(name), dark, lite, uses.get(name, 0)))
    return "\n".join(lines)


def _token_purpose(name: str) -> str:
    n = name.lstrip("-")
    table = [
        ("bg-", "背景层"), ("bg-toolbar", "顶栏底"), ("text-", "文字"), ("accent", "强调/交互"),
        ("theme-color", "主题色（状态栏/焦点）"), ("border", "描边/分隔线"), ("success", "成功/正向"),
        ("error", "错误/危险"), ("warning", "警告"), ("tk-", "代码高亮"), ("mmd-", "Mermaid"),
        ("graph-", "知识图谱（canvas）"), ("shadow", "阴影档"), ("font", "字体族/字号"),
        ("scrollbar", "滚动条"), ("motion", "动效时长/缓动"), ("bar-h", "栏高"), ("checkbox", "勾选圆点"),
    ]
    for key, label in table:
        if n.startswith(key):
            return label
    return "—"


def cmd_suggest(contract_path: str) -> str:
    """给契约登记块生成初始骨架（从当前 CSS 现状自动汇总，供人审后再写入契约）。"""
    contract, css_map, js_files, _ = collect(contract_path)
    layers = []
    seen = set()
    for rel, parsed in css_map.items():
        for d in parsed["decls"]:
            if d["prop"] != "z-index":
                continue
            try:
                z = int(d["value"].strip())
            except ValueError:
                continue
            key = (rel, norm_ws(d["selector"]), z)
            if key in seen:
                continue
            seen.add(key)
            layers.append({"id": "L%d" % (len(layers) + 1), "z": z,
                           "selector_contains": [norm_ws(d["selector"])], "file": rel,
                           "note": "TODO 人审：这一层是什么"})
    return json.dumps({"layers": layers}, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# selftest：fixtures（每条约束至少一条必红 + 正例）
# ---------------------------------------------------------------------------


FIXTURE_CONTRACT = {
    "important-exemptions": {"exemptions": [
        {"id": "X1", "file": r"app/css/app\.css", "selector_contains": ["-fixture-ok"],
         "reason": "fixture：登记过的收口用途"},
    ]},
    "style-policy": {
        "colors": {"token_files": ["theme/memoria.css", "theme/light.css"],
                   "neutral_alpha_allowed_props": ["box-shadow", "text-shadow"]},
        "px": {"rem_only_props": ["font-size", "line-height"], "radius_tiers_px": [4, 6, 8, 12, 999],
               "spacing_grid_px": [0, 2, 4, 6, 8, 10, 12, 14, 16, 20, 24, 32, 40, 48, 64],
               "spacing_props": ["padding", "padding-top", "padding-right", "padding-bottom",
                                 "padding-left", "margin", "margin-top", "margin-right",
                                 "margin-bottom", "margin-left", "gap", "row-gap", "column-gap"]},
    },
    "range-ssot": {"ranges": [
        {"id": "R1", "ssot_file": "app/js/fixture-ssot.js",
         "ssot_regex": r"RANGE\s*=\s*\{[^}]*?\bmin:\s*(?P<min>\d+)[^}]*?\bmax:\s*(?P<max>\d+)[^}]*?\bdef:\s*(?P<def>\d+)",
         "guards": [
             {"file": "app/js/fixture-guard.js", "regex": r"v\s*>=\s*(?P<min>\d+)\s*&&\s*v\s*<=\s*(?P<max>\d+)"},
             {"file": "app/js/fixture-guard.js", "regex": r"CONTENT_MIN_PX\s*=\s*(?P<def>\d+)"},
         ]},
    ]},
    "z-index-registry": {"layers": [
        {"id": "base", "z": 1, "selector_contains": ["-fixture-z1"], "file": "app/css/app.css"},
        {"id": "top", "z": 9000, "selector_contains": ["-fixture-z9000"], "file": "app/css/app.css"},
    ], "relations": [
        {"id": "top-above-base", "upper": "top", "lower": "base", "status": "ok"},
    ]},
    "icons": {"icons": [
        {"id": "fixture-bad", "file": r"app/js/fixture-icon.js", "marker": '<path d="M4 2h8"',
         "viewBox": "0 0 16 16", "sizes": [13], "dynamic_expected": False},
        {"id": "fixture-good", "file": r"app/js/fixture-icon.js", "marker": "M4 2.4h8v1.6",
         "viewBox": "0 0 16 16", "sizes": [13], "css_file": "app/css/app.css",
         "states": [
             {"name": "off", "selector_contains": "-fixture-icon-off"},
             {"name": "on", "selector_contains": "-fixture-icon-on"},
         ],
         "discoverability": {"aria_label": True, "title": True, "symbol": "fixtureUpdateIcon"}},
    ]},
    "token-policy": {"js_written_tokens": ["--fixture-js-token"],
                     "ignore_undefined_tokens": ["--fixture-ignored"]},
}

FIXTURE_CSS = textwrap.dedent(
    """
    /* 注释里的 !important / #fff / 13px 都不该算违规 */
    .-fixture-base { z-index: 1; }
    .-fixture-z9000 { z-index: 9000; }
    .-fixture-z9999 { z-index: 9999; }              /* C5 必红：未登记 */
    .-fixture-important { color: red !important; }  /* C1 必红 */
    .-fixture-ok { color: red !important; }         /* C1 豁免：已登记 */
    .-fixture-color { color: #fff; }                /* C2 必红 */
    .-fixture-color-ok { color: var(--text-primary); }  /* C2 绿 */
    .-fixture-shadow { box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2); } /* C2 WARN */
    .-fixture-font { font-size: 13px; }             /* C3 必红（字号须 rem） */
    .-fixture-font-ok { font-size: 0.8125rem; }
    .-fixture-radius { border-radius: 5px; }        /* C3 必红（不在档位） */
    .-fixture-spacing { padding: 5px; }             /* C3 WARN（离栅格） */
    .-fixture-token-undefined { color: var(--fixture-missing); }        /* C7 必红 */
    .-fixture-token-lightonly { color: var(--fixture-light-only); }     /* C7 必红（仅浅色定义） */
    .-fixture-token-ok { color: var(--text-primary); }
    .-fixture-icon-off { fill-opacity: 0.22; }      /* C6 状态差异 */
    .-fixture-icon-on { fill-opacity: 1; }
    """
)

FIXTURE_THEME = textwrap.dedent(
    """
    :root {
        --text-primary: #cccccc;
        --fixture-color-only-dark: #123456;
    }
    """
)

FIXTURE_LIGHT = textwrap.dedent(
    """
    html[data-theme="light"] {
        --text-primary: #2f2f2f;
        --fixture-light-only: #abcdef;
    }
    """
)

FIXTURE_SSOT = "const RANGE = { min: 180, max: 560, def: 360 };\n"
FIXTURE_GUARD_BAD = "function f(v) { if (v >= 320 && v <= 560) return v; }\nconst CONTENT_MIN_PX = 360;\n"
FIXTURE_GUARD_OK = "function f(v) { if (v >= 180 && v <= 560) return v; }\nconst CONTENT_MIN_PX = 360;\n"
FIXTURE_GUARD_DEF_BAD = "function f(v) { if (v >= 180 && v <= 560) return v; }\nconst CONTENT_MIN_PX = 320;\n"
#: 注释里**提到**同一常量名与不同数字（真实仓里 agent-panel.js:67 就是这种说明注释）
FIXTURE_GUARD_WITH_COMMENT = (
    FIXTURE_GUARD_OK
    + "// 保底 CONTENT_MIN_PX=999，守卫写法 v >= 999 只是示意\n"
    + "/* 块注释：RANGE = { min: 1, max: 2 } 也只是示意 */\n"
)

FIXTURE_ICON = textwrap.dedent(
    """
    const FIXTURE_BAD = '<svg viewBox="0 0 16 16" width="13" height="13">' +
      '<path d="M4 2h8" fill="none" stroke="currentColor" stroke-width="1.4"/>' +
      '<path d="M8 3v10" fill="none" stroke="currentColor" stroke-width="1.4"/>' +
      '</svg>';
    const FIXTURE_GOOD = '<svg viewBox="0 0 16 16" width="13" height="13">' +
      '<path d="M4 2h8v1.6H9.6v3.4c0 1.3 1 2.3 2.3 2.3v1.5H9.1v3.2L8 15.8l-1.1-1.4v-3.2H4.1v-1.5c1.3 0 2.3-1 2.3-2.3V4H4z" ' +
      'fill="currentColor" stroke="currentColor" stroke-width="1.6"/></svg>';
    function fixtureUpdateIcon(btn, on) {
      btn.setAttribute("aria-label", on ? "off" : "on");
      btn.setAttribute("title", on ? "off" : "on");
    }
    """
)


def _fixture_files() -> dict:
    return {
        "app/css/app.css": FIXTURE_CSS,
        "theme/memoria.css": FIXTURE_THEME,
        "theme/light.css": FIXTURE_LIGHT,
        "app/js/fixture-ssot.js": FIXTURE_SSOT,
        "app/js/fixture-guard.js": FIXTURE_GUARD_BAD,
        "app/js/fixture-icon.js": FIXTURE_ICON,
    }


def _collect_fixture(contract: dict, files: dict) -> list:
    css_map = {rel: parse_css(text) for rel, text in files.items() if rel.endswith(".css")}
    js_files = {rel: text for rel, text in files.items() if rel.endswith(".js")}
    findings = []
    findings += check_c1(css_map, contract)
    findings += check_c2(css_map, contract)
    findings += check_c3(css_map, contract)
    findings += check_c4(contract, js_files)
    findings += check_c5(css_map, contract)
    findings += check_c6(contract, js_files, css_map)
    findings += check_c7(css_map, contract, js_files)
    return findings


def cmd_selftest() -> int:
    fails = []
    findings = _collect_fixture(FIXTURE_CONTRACT, _fixture_files())

    def has(rule, file_part, needle, severity="FAIL"):
        for f in findings:
            if f["rule"] != rule or f["severity"] != severity:
                continue
            if file_part and file_part not in f["file"]:
                continue
            if needle in (f["detail"] + " " + f["value"] + " " + f["selector"] + " " + f["prop"]):
                return True
        return False

    checks = [
        ("C1 必红：未登记 !important", has("C1", "app.css", "未登记")),
        ("C1 绿：登记豁免不报", not any(f["rule"] == "C1" and "-fixture-ok" in f["selector"] for f in findings)),
        ("C2 必红：硬编码 #fff", has("C2", "app.css", "#fff")),
        ("C2 绿：var(--token) 不报", not any(f["rule"] == "C2" and "-fixture-color-ok" in f["selector"] for f in findings)),
        ("C2 WARN：中性 alpha 阴影", has("C2", "app.css", "rgba(0, 0, 0", severity="WARN")),
        ("C3 必红：font-size px", has("C3", "app.css", "font-size")),
        ("C3 必红：圆角离档", has("C3", "app.css", "border-radius")),
        ("C3 WARN：间距离栅格", has("C3", "app.css", "padding", severity="WARN")),
        ("C4 必红：双源范围漂移", has("C4", "fixture-guard.js", "漂移")),
        ("C5 必红：未登记 z-index", has("C5", "app.css", "9999")),        ("C6 必红：13px 多段细描边", has("C6", "fixture-icon.js", "坍缩")),
        ("C6 绿：单闭合轮廓+浅填充不报", not any(f["rule"] == "C6" and f["severity"] == "FAIL" and "fixture-good" in f["detail"] for f in findings)),
        ("C6 状态差异可机检", not any(f["rule"] == "C6" and "状态间 opacity" in f["detail"] for f in findings)),
        ("C6 可发现性（aria/title）", not any(f["rule"] == "C6" and "aria-label" in f["detail"] for f in findings)),
        ("C7 必红：未定义且无兜底", has("C7", "app.css", "fixture-missing")),
        ("C7 必红：仅浅色定义", has("C7", "app.css", "fixture-light-only")),
        ("C7 WARN：颜色 token 浅色未覆盖", has("C7", "light.css", "fixture-color-only-dark", severity="WARN")),
    ]
    # 阳性对照：把"漂移"修好后，C4 应从红变绿（证明判据看得见差异）
    ok_files = dict(_fixture_files())
    ok_files["app/js/fixture-guard.js"] = FIXTURE_GUARD_OK
    ok_findings = _collect_fixture(FIXTURE_CONTRACT, ok_files)
    checks.append(
        ("C4 阳性对照：全字段同口径时不再红（只报双源 WARN）",
         not any(f["rule"] == "C4" and f["severity"] == "FAIL" for f in ok_findings))
    )
    # 字段级：默认值 def 单独漂移也必须红（C4 覆盖面补强）
    def_bad_files = dict(_fixture_files())
    def_bad_files["app/js/fixture-guard.js"] = FIXTURE_GUARD_DEF_BAD
    def_bad_findings = _collect_fixture(FIXTURE_CONTRACT, def_bad_files)
    checks.append(
        ("C4 必红：默认值 def 漂移（字段级）",
         any(f["rule"] == "C4" and f["severity"] == "FAIL" and "def" in f["detail"]
             for f in def_bad_findings))
    )
    checks.append(
        ("C4 阳性对照：def 漂移时 min/max 守卫仍报一致（不误报）",
         any(f["rule"] == "C4" and f["severity"] == "WARN" and f["prop"] == "R1"
             for f in def_bad_findings))
    )
    # 注释不误报（真实仓 agent-panel.js:67 的说明注释里就写了 CONTENT_MIN_PX=360）
    comment_files = dict(_fixture_files())
    comment_files["app/js/fixture-guard.js"] = FIXTURE_GUARD_WITH_COMMENT
    comment_findings = _collect_fixture(FIXTURE_CONTRACT, comment_files)
    checks.append(
        ("C4 阳性对照：注释里的常量名/数字不算第二事实源",
         not any(f["rule"] == "C4" and f["severity"] == "FAIL" for f in comment_findings)
         and len([f for f in comment_findings if f["rule"] == "C4"]) == 2)
    )
    # 负向对照：没有图标/marker 时不误报
    clean_icon = "const X = 1;\n"
    no_icon_files = dict(_fixture_files())
    no_icon_files["app/js/fixture-icon.js"] = clean_icon
    no_icon_findings = _collect_fixture(FIXTURE_CONTRACT, no_icon_files)
    checks.append(
        ("C6 阳性对照：图标消失时登记表报过期（不是静默通过）",
         any(f["rule"] == "C6" and "没找到" in f["detail"] for f in no_icon_findings))
    )
    bad = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(("  PASS  " if ok else "  FAIL  ") + name)
    print("-- selftest: %d/%d PASS --" % (len(checks) - len(bad), len(checks)))
    return 0 if not bad else 1


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="UI 契约机检（契约 = docs/conventions/ui-contract.md）")
    ap.add_argument("--contract", default=CONTRACT_DEFAULT)
    ap.add_argument("--baseline", default=BASELINE_DEFAULT)
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--force", action="store_true", help="--update-baseline 时允许基线变大（默认只允许变小）")
    ap.add_argument("--strict", action="store_true", help="基线项也算 FAIL（清零目标）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--token-table", action="store_true")
    ap.add_argument("--suggest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return cmd_selftest()
    if args.token_table:
        try:
            print(cmd_token_table(args.contract))
        except FileNotFoundError:
            raise SystemExit("契约文件不存在：%s" % args.contract)
        return 0
    if args.suggest:
        print(cmd_suggest(args.contract))
        return 0
    if not os.path.exists(args.contract):
        print("契约文件不存在：%s" % args.contract, file=sys.stderr)
        return 2
    _, css_map, js_files, findings = collect(args.contract)
    baseline = load_baseline(args.baseline)
    result = apply_baseline(findings, baseline)
    result["contract_path"] = args.contract

    if args.update_baseline:
        new_fail = sum(1 for r in result["rows"] if r["status"] == "new" and r["severity"] == "FAIL")
        old_fail = sum(1 for r in baseline if r.get("severity") == "FAIL")
        if new_fail > old_fail and not args.force:
            print("拒绝重落基线：新增 FAIL=%d > 旧基线 FAIL=%d（基线只许变小；确需放宽加 --force）"
                  % (new_fail, old_fail), file=sys.stderr)
            return 1
        payload = {
            "version": 1,
            "generated_by": "scripts/check_ui_contract.py",
            "contract": os.path.relpath(args.contract, ROOT).replace("\\", "/"),
            "counts": {
                "FAIL": sum(1 for r in result["rows"] if r["severity"] == "FAIL"),
                "WARN": sum(1 for r in result["rows"] if r["severity"] == "WARN"),
                "by_rule": _count_by_rule(result["rows"]),
            },
            "findings": sorted(
                [{"fp": r["fp"], "rule": r["rule"], "severity": r["severity"], "file": r["file"],
                  "line": r["line"], "selector": r["selector"], "detail": r["detail"],
                  "prop": r["prop"], "value": r["value"]} for r in result["rows"]],
                key=lambda x: (x["rule"], x["file"], x["line"]),
            ),
        }
        os.makedirs(os.path.dirname(args.baseline), exist_ok=True)
        with io.open(args.baseline, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print("基线已写入：%s（FAIL=%d / WARN=%d）"
              % (args.baseline, payload["counts"]["FAIL"], payload["counts"]["WARN"]))
        if args.json_out:
            with io.open(args.json_out, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
        return 0

    text = render_human(result, args.baseline)
    print(text)
    if args.json_out:
        payload = {
            "version": 1,
            "contract": os.path.relpath(args.contract, ROOT).replace("\\", "/"),
            "counts": {"new_fail": sum(1 for r in result["rows"] if r["status"] == "new" and r["severity"] == "FAIL"),
                       "new_warn": sum(1 for r in result["rows"] if r["status"] == "new" and r["severity"] == "WARN"),
                       "baseline_fail": sum(1 for r in result["rows"] if r["status"] == "baseline" and r["severity"] == "FAIL"),
                       "baseline_warn": sum(1 for r in result["rows"] if r["status"] == "baseline" and r["severity"] == "WARN"),
                       "fixed": len(result["fixed"]),
                       "by_rule": _count_by_rule(result["rows"])},
            "rows": result["rows"],
            "fixed": result["fixed"],
        }
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
        with io.open(args.json_out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print("\nJSON 明细：%s" % args.json_out)
    new_fail = sum(1 for r in result["rows"] if r["status"] == "new" and r["severity"] == "FAIL")
    if args.strict:
        residual = sum(1 for r in result["rows"] if r["severity"] == "FAIL")
        return 1 if residual else 0
    return 1 if new_fail else 0


def _count_by_rule(rows: list) -> dict:
    out = {}
    for r in rows:
        key = r["rule"] + "." + r["severity"]
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


if __name__ == "__main__":
    sys.exit(main())
