"""task-183 回归守卫：本会话「缓存命中率」从状态条移到输入框下方（与上下文圆环同一行）。

人原话：「为什么上下文占用『cached』还是显示在底栏而不是做到会话栏的底部」。
归类：缓存命中率 + 上下文占用圆环 = 「本次会话资源状况」⇒ 同一行、输入框下方。

真机 DOM 证据（行为层）：
  artifacts/agent/verify/todo/agent-panel-cache-indicator/verify.json
  · T1 状态条区域查不到命中率文本；T2 命中率在输入框下方且与圆环包围盒不相交；
  · T3 悬停明细含 hit/miss/rate 口径；T4 状态条无空槽/多余分隔符；
  · T5 输入框调高/调低后两者跟随；T6 260/520px 两种面板宽度不换行错乱。

本文件是**结构 + 纯函数回归**（锁不变量，替代会过期字面量的弱断言）：
  ① 状态条数组 4→3 项、无空槽、无命中率键；
  ② 缓存格挂在 `#agent-ctx-ring-row`（task-169 的圆环行）内，圆环渲染器一行未改；
  ③ `cacheHitDetailLines()` 的命中/未命中/命中率口径（node 实跑，含未知≠0%）；
  ④ i18n 键复用既有键（中英均有），CSS 布局规则存在。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "src" / "memoria" / "ui" / "static" / "app" / "js" / "agent-panel.js"
CSS = ROOT / "src" / "memoria" / "ui" / "static" / "app" / "css" / "app.css"
ZH = ROOT / "src" / "memoria" / "ui" / "static" / "app" / "i18n" / "zh-CN.js"
EN = ROOT / "src" / "memoria" / "ui" / "static" / "app" / "i18n" / "en.js"


def panel_source() -> str:
    return PANEL.read_text(encoding="utf-8")


def extract_function(src: str, name: str) -> str:
    """按花括号配平抽取 `function name(...) {...}` 整段（与 test_agent_panel_token.py 同款）。"""
    match = re.search(r"\n  function " + re.escape(name) + r"\(", src)
    assert match is not None, f"未在 agent-panel.js 找到函数 {name}"
    start = src.index("{", match.end() - 1)
    depth = 0
    for index in range(start, len(src)):
        if src[index] == "{":
            depth += 1
        elif src[index] == "}":
            depth -= 1
            if depth == 0:
                return src[match.start() + 1: index + 1]
    raise AssertionError(f"函数 {name} 花括号不平衡")


def node_eval(script: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("node 不在 PATH —— 前端纯函数单测跳过")
    proc = subprocess.run([node, "-e", script], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


T_STUB = (
    "const T = (key, vars) => key + '(' + JSON.stringify(vars || {}) + ')';\n"
    "const isFiniteStub = (v) => typeof v === 'number' && isFinite(v);\n"
)


def detail_lines_script() -> str:
    src = panel_source()
    return (
        T_STUB
        + extract_function(src, "hitRateText")
        + "\n"
        + extract_function(src, "usageInt")
        + "\n"
        + extract_function(src, "cacheHitDetailLines")
        + "\n"
        + "const out = ["
        + "cacheHitDetailLines({prompt_tokens:100, completion_tokens:10, total_tokens:110,"
        + " cache_read_tokens:60, cache_miss_tokens:40}, null, '60%'),"
        + "cacheHitDetailLines(null, {hit_known:2, cache_hit:90, cache_miss:110, hit_denom:200,"
        + " miss_known:2, turns:2}, '45%'),"
        + "cacheHitDetailLines(null, null, '')"
        + "];"
        + "console.log(JSON.stringify(out));"
    )


# ── ① 状态条：4→3 项、无空槽、无命中率 ────────────────────────────────────────


def test_status_bar_no_longer_contains_cache_hit_rate():
    src = panel_source()
    body = extract_function(src, "renderStatusBar")
    assert "agent.statusBar.hitRate" not in body, (
        "task-183 回归：状态条里又出现了缓存命中率（应只在输入框下方渲染）"
    )
    # 命中率不再占槽 ⇒ 数组从 4 项减到 3 项（model / net / balance），join 不留尾巴
    start = body.index("facts.innerHTML = [") + len("facts.innerHTML = [")
    array = body[start: body.index("].join(")]
    items = [
        line for line in array.splitlines()
        if line.strip() and not line.strip().startswith("//")
    ]
    assert len(items) == 3, f"状态条事实串应只剩 3 项（模型/网络/余额），实际 {len(items)} 项：{items}"
    assert all(line.strip() for line in items), "状态条事实串里出现空项（会渲染出多余分隔符）"
    assert '" · "' in body or "' · '" in body, "事实串拼接符被改坏"


# ── ② 缓存格挂进圆环行；圆环渲染器未被改动 ───────────────────────────────────


def test_cache_hit_is_mounted_in_the_ctx_ring_row_under_the_input():
    src = panel_source()
    tail = src[src.index("task-183（2026-10-26）：本会话「缓存命中率」移到输入框下方"):]
    assert 'el.id = "agent-cache-hit";' in tail
    assert 'el.className = "-agent-cache-hit";' in tail
    assert 'document.getElementById("agent-ctx-ring-row")' in tail
    assert 'composer.insertBefore(row, actions)' in tail, "缓存格必须进圆环同一行（输入框下方）"
    assert "renderCacheHit();" in tail, "初次挂载缺失"
    # 圆环语义一行未改：仍是同一个渲染器/行容器
    ring = extract_function(src, "renderContextRing")
    assert 'document.getElementById("agent-ctx-ring-row")' in ring
    assert "compactRingUnknown" in ring and "view.percent" in ring


# ── ③ 明细口径（纯函数，node 实跑）────────────────────────────────────────────


def test_cache_detail_lines_carry_full_hit_miss_rate():
    out = node_eval(detail_lines_script())
    known, session, unknown = out
    # 本轮明细 + 会话级命中率（同一浮层里两行）
    assert len(known) == 2 and known[0].startswith("agent.statusBar.cache("), known
    payload = json.loads(known[0][known[0].index("(") + 1: -1])
    assert payload == {"hit": 60, "miss": 40, "rate": "60%"}, payload
    assert known[1].startswith("agent.statusBar.hitRate("), known
    # 会话累计一条 + 会话级命中率一条（本轮无 usage ⇒ 另有"未知"一条）
    assert len(session) == 3, session
    assert session[0].startswith("agent.statusBar.cacheUnknown("), session
    assert session[1].startswith("agent.statusBar.sessionCache("), session
    sp = json.loads(session[1][session[1].index("(") + 1: -1])
    assert sp["hit"] == 90 and sp["miss"] == 110 and sp["rate"] == "45%", sp
    assert session[2].startswith("agent.statusBar.hitRate("), session
    assert json.loads(session[2][session[2].index("(") + 1: -1])["rate"] == "45%"


def test_cache_unknown_is_never_reported_as_zero_percent():
    unknown = node_eval(detail_lines_script())[2]
    text = " ".join(unknown)
    assert "agent.statusBar.cacheUnknown" in text, "未知缓存必须明说未知"
    assert "0%" not in text, "未知缓存绝不瞎报 0%"
    assert "hitRate" in text and "—" in text


# ── ④ i18n 键复用 + CSS 布局 ──────────────────────────────────────────────────


def test_cache_hit_reuses_existing_i18n_keys_in_both_languages():
    for path in (ZH, EN):
        text = path.read_text(encoding="utf-8")
        for key in ("hitRate:", "cache:", "cacheUnknown:", "sessionCache:"):
            assert key in text, f"{path.name} 缺 statusBar.{key[:-1]}（命中率明细口径键）"


def test_css_places_cache_hit_in_the_same_row_as_the_ring():
    css = CSS.read_text(encoding="utf-8")
    assert ".-agent-cache-hit {" in css
    assert "order: 1;" in css and "#agent-ctx-ring { order: 0; }" in css
    assert ".-agent-ctx-ring-row { gap: 0.5rem; }" in css
    # 不换行 + 窄宽度走省略号
    block = css[css.index(".-agent-cache-hit {"): css.index(".-agent-cache-hit:hover")]
    assert "white-space: nowrap" in block
    assert "text-overflow: ellipsis" in block
    assert "min-width: 0" in block
