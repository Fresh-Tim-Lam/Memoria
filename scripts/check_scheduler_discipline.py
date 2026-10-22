#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调度纪律守卫（M5.1 收尾，2026-10-22 Lead 批准）。

断言 `src/memoria/ui/static/app/js/**/*.js` 中不再新增「手写调度」：
  1. `setTimeout(fn, 0)` —— 用零延时宏任务充当调度队列；
  2. `requestIdleCallback(...)` —— 绕过 `MemoriaScheduler` 的空闲调度；
  3. `requestAnimationFrame` **驱动的批次循环** —— 回调里再排 rAF，或回调/其命名函数
     在推进 batch/queue/pending/materialize/evict/typeset 这类批次工作。

设计（与 scripts/check_todo_size.py 同风格）：
  - 白名单是**显式的**：每条 = 文件 + 规则 + 代码锚点 + 理由；锚点按代码行匹配，
    行号漂移不影响，但锚点消失会判「陈旧白名单」失败（强制收口）。
  - 同一锚点允许 max 次（默认 1），防止在白名单函数里悄悄多塞一处调度。
  - 只扫代码，注释里的示例不算命中。

允许的例外与理由见本文件 WHITELIST，以及 docs/design/maintenance-jobs.md §3.6。
新增调度需求的正规做法：`MemoriaScheduler.schedule({kind, key, priority, run})`，
不要在本文件里加白名单（白名单只收「不适用调度器」的结构性例外）。

用法：python scripts/check_scheduler_discipline.py [--dir <js 目录>]
退出码：0 通过；1 失败（打印全部违规项/陈旧白名单）。
"""
import argparse
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DIR = os.path.join(ROOT, "src", "memoria", "ui", "static", "app", "js")

# ── 白名单：只允许「结构上不该进调度器」的例外 ───────────────────────────────
# anchor 必须在**去掉注释后的代码行**里逐字出现；max 为该锚点允许的最大命中数。
WHITELIST = [
    # ── 调度器自身的降级/续跑实现（它就是调度器，不能再调度自己） ──────────────
    dict(file="scheduler.js", rule="timeout0", anchor="return setTimeout(fn, 0);", max=1,
         reason="调度器空闲兜底：无 requestIdleCallback 时退化为零延时宏任务"),
    dict(file="scheduler.js", rule="timeout0", anchor="return setTimeout(function () { fn(now()); }, 0);", max=1,
         reason="调度器续帧兜底：无 rAF/idle 时退化为零延时宏任务"),
    dict(file="scheduler.js", rule="idle", anchor="return g.requestIdleCallback(fn, { timeout: 800 });", max=1,
         reason="调度器空闲调度实现本体"),
    dict(file="scheduler.js", rule="idle", anchor="return g.requestIdleCallback(function () { fn(now()); }, { timeout: 100 });", max=1,
         reason="调度器续帧兜底（无 rAF 时）"),

    # ── DOM 落定 / 布局同步：让浏览器先完成重排，再做一次同步读取或选择区恢复 ──
    dict(file="agent-panel.js", rule="timeout0", anchor="setTimeout(syncComposerChips, 0);", max=2,
         reason="输入框尺寸落定后同步 chip 位置（DOM 布局同步，不是队列调度）"),
    dict(file="edit-handler.js", rule="raf", anchor="if (window.requestAnimationFrame) window.requestAnimationFrame(apply);", max=1,
         reason="选区在 DOM 更新后再应用一次（光标稳定性），非队列"),
    dict(file="edit-handler.js", rule="timeout0", anchor='setTimeout(function () { syncFromSelection("click:image"); }, 0);', max=1,
         reason="点击后等 DOM 落定再同步选择区（布局同步）"),
    dict(file="edit-handler.js", rule="timeout0", anchor='setTimeout(function () { syncFromSelection("click"); }, 0);', max=1,
         reason="点击后等 DOM 落定再同步选择区（布局同步）"),
    dict(file="edit-handler.js", rule="timeout0", anchor='setTimeout(function () { syncFromSelection("arrow:" + key); }, 0);', max=1,
         reason="方向键后等 DOM 落定再同步选择区（布局同步）"),
    dict(file="edit-handler.js", rule="timeout0", anchor='setTimeout(function () { syncFromSelection("caption-submit"); }, 0);', max=1,
         reason="题注提交后等 DOM 落定再同步选择区（布局同步）"),
    dict(file="edit-handler.js", rule="timeout0", anchor="var newBlk = getBlockIndexFromSelection();", max=1,
         reason="浏览器处理方向键后等 DOM 落定再校准光标/选择区（布局同步，非队列）"),

    # ── 渲染耗时打点：双 rAF 只用于标记 frame1/paint，不推进任何作业 ────────────
    dict(file="app.js", rule="raf", anchor='window.requestAnimationFrame(function () { _markAsync("frame1", _o);', max=2,
         reason="渲染耗时双 rAF 打点（frame1/paint），非作业调度"),
    dict(file="app.js", rule="raf", anchor="window.requestAnimationFrame(function () {", max=1,
         reason="渲染耗时双 rAF 打点（frame1/paint），非作业调度"),

    # ── 惰性渲染管线内的显式例外 ───────────────────────────────────────────────
    dict(file="app.js", rule="raf",
         anchor="_lazySyncRAF = (window.requestAnimationFrame) ? window.requestAnimationFrame(tick) : setTimeout(tick, 16);", max=1,
         reason="滚动帧内小步补齐视口块（单次、≤LAZY_SYNC_MAX=50 块/帧）；与滚动同帧才能避免空白，故不经 Scheduler"),
    dict(file="app.js", rule="timeout0", anchor='setTimeout(function () { _lazyFlushMathNow("timer"); }, 0);', max=1,
         reason="Scheduler 缺席（旧壳/裁剪构建）时的防御回退；正常生产路径不达"),
    dict(file="app.js", rule="timeout0",
         anchor='_lazyFlushNow(); } catch (e) { log("lazy", "flush THREW (no scheduler): "', max=1,
         reason="lazy_materialize 的 Scheduler 缺席防御回退（与 lazy_typeset 回退同源；生产路径不达）"),
    dict(file="app.js", rule="timeout0",
         anchor='return new Promise(function (r) { setTimeout(r, 0); }).then(function () {', max=1,
         reason="typeset 串行链的单个宏任务边界（与物化分帧；单次边界，不形成队列）"),
    dict(file="app.js", rule="raf",
         anchor="window.requestAnimationFrame(function () { window.requestAnimationFrame(_runMathH); })", max=2,
         reason="缓存命中恢复路径等两帧后补 MathJax 标记（单次时序，非队列）"),
    dict(file="app.js", rule="idle",
         anchor="_preloadIdle = window.requestIdleCallback(fire, { timeout: 4000 });", max=1,
         reason="投机预渲染：可取消、双 rAF 门槛 + 4s 空闲 deadline；整篇 parse+render 不可切片，不属 M5 派生维护作业"),
    dict(file="app.js", rule="raf",
         anchor="window.requestAnimationFrame(function () { window.requestAnimationFrame(arm); }); else arm();", max=2,
         reason="预渲染调度前的双帧等待（与上一条同一机制，避免抢用户当前帧）"),
    dict(file="app.js", rule="timeout0",
         anchor="return new Promise(function (r) { setTimeout(r, 0); }).then(function () { return runBatch(to); });", max=1,
         reason="MATERIALIZE_ALL 门禁测试 API 的批间让出（每批 200 块；宏任务边界），非生产调度路径"),

    # ── 动画 / 布局引擎循环（每帧只做布局与绘制，不是作业队列） ────────────────
    dict(file="graph-layout-2d.js", rule="raf", anchor="this.raf = requestAnimationFrame(frame);", max=2,
         reason="2D 力导向布局动画自续帧循环（每帧 tick+emit）"),
    dict(file="graph-layout-3d.js", rule="raf", anchor="this.raf = requestAnimationFrame(frame);", max=2,
         reason="3D 力导向布局动画自续帧循环（每帧 tick+emit）"),
    dict(file="graph-view-3d.js", rule="raf", anchor="this._raf = requestAnimationFrame(loop);", max=2,
         reason="3D 视图渲染循环（每帧同步位置/渲染）"),
    dict(file="graph-settings.js", rule="raf", anchor="requestAnimationFrame(tryBoot);", max=2,
         reason="面板可见尺寸轮询（≤30 次）以启动预览，属 UI 依赖等待"),

    # ── 调试探针 / 第三方资源就绪重试 ─────────────────────────────────────────
    dict(file="keys-debug.js", rule="raf", anchor="requestAnimationFrame(function () {", max=1,
         reason="键盘/选区调试探针的 rAF 合并采样（仅调试载入）"),
    dict(file="markdown-preview.js", rule="raf", anchor="setTimeout(function () { requestAnimationFrame(retry); }, 80);", max=1,
         reason="Mermaid 异步就绪重试（有 MAX_TRIES 上限）"),
    dict(file="markdown-preview.js", rule="raf", anchor="requestAnimationFrame(function () { requestAnimationFrame(retry); });", max=2,
         reason="Mermaid 异步就绪重试的首次双帧等待（有界）"),
]

# ── 代码抽取：去掉 // 与 /* */ 注释，字符串内容保留（锚点按代码匹配） ─────────
def strip_comments(text):
    """返回与原文等长的字符串，注释字符替换为空格（保留换行）。"""
    out = []
    i, n = 0, len(text)
    state = "code"  # code | line | block | sq | dq | tpl
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if state == "code":
            if c == "/" and nxt == "/":
                state = "line"
                out.append("  ")
                i += 2
                continue
            if c == "/" and nxt == "*":
                state = "block"
                out.append("  ")
                i += 2
                continue
            if c in ("'", '"', "`"):
                state = {"'": "sq", '"': "dq", "`": "tpl"}[c]
            out.append(c)
            i += 1
        elif state == "line":
            if c == "\n":
                state = "code"
                out.append(c)
            else:
                out.append(" ")
            i += 1
        elif state == "block":
            if c == "*" and nxt == "/":
                state = "code"
                out.append("  ")
                i += 2
                continue
            out.append("\n" if c == "\n" else " ")
            i += 1
        else:  # 字符串
            if c == "\\" and i + 1 < n:
                out.append(c + text[i + 1])
                i += 2
                continue
            closing = {"sq": "'", "dq": '"', "tpl": "`"}[state]
            if c == closing:
                state = "code"
                out.append(c)
                i += 1
            elif c == "\n" and state != "tpl":
                # 未闭合的普通字符串：按行结束回退到 code，避免整文件误吞
                state = "code"
                out.append(c)
                i += 1
            else:
                out.append(c)
                i += 1
    return "".join(out)


TIMEOUT_CALL = re.compile(r"\bsetTimeout\s*\(")
IDLE = re.compile(r"\brequestIdleCallback\s*\(")
RAF = re.compile(r"\brequestAnimationFrame\s*\(")
# 批次类词汇：出现在 rAF 回调/其命名函数定义窗口里 ⇒ 该 rAF 在推进批次
BATCH_WORDS = re.compile(
    r"(batch|queue|pending|backlog|drain|flush|materializ\w*|evict\w*|typeset\w*|schedule\w*)",
    re.I,
)
CALLBACK_ID = re.compile(r"requestAnimationFrame\s*\(\s*([A-Za-z_$][\w$]*)\s*\)")


def _balanced_call(text, start):
    """从 text[start] 的 '(' 起取到配对的 ')'，返回 (inside, end)。跨行。"""
    depth = 0
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i
        i += 1
    return text[start + 1:], n


def _named_fn_window(code, name):
    """在文件里找 `var tick = function` / `function tick(` 定义，返回其后 1500 字符。"""
    pat = re.compile(
        r"(?:var|let|const)\s+" + re.escape(name) + r"\s*=\s*(?:async\s+)?(?:function|\()"
        r"|function\s+" + re.escape(name) + r"\s*\("
    )
    m = pat.search(code)
    if not m:
        return ""
    return code[m.start():m.start() + 1500]


def _iter_timeout0(code):
    """产出 (起始下标, 规范化后的完整调用文本)；支持跨行调用（按配对括号取实参，再按顶层逗号拆分）。"""
    for m in TIMEOUT_CALL.finditer(code):
        inside, end = _balanced_call(code, m.end() - 1)
        args, depth, cur = [], 0, []
        for ch in inside:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            if ch == "," and depth == 0:
                args.append("".join(cur))
                cur = []
            else:
                cur.append(ch)
        args.append("".join(cur))
        if len(args) >= 2 and args[-1].strip() in ("0", "0.0"):
            call = re.sub(r"\s+", " ", code[m.start():end + 1]).strip()
            yield m.start(), call


def scan_file(path):
    text = io.open(path, encoding="utf-8", errors="replace").read()
    if text.startswith("\ufeff"):
        text = text[1:]
    code = strip_comments(text)
    lines = code.split("\n")
    hits = []
    timeout_hits = {}
    for start, call in _iter_timeout0(code):
        ln0 = code.count("\n", 0, start) + 1
        timeout_hits.setdefault(ln0, []).append(call)
    line_start = 0
    for idx, line in enumerate(lines):
        ln = idx + 1
        text_line = line.strip()
        for call in timeout_hits.get(ln, []):
            hits.append(dict(rule="timeout0", line=ln, text=text_line, call=call, snippet=text_line[:160]))
        for m in IDLE.finditer(line):
            hits.append(dict(rule="idle", line=ln, text=text_line, snippet=text_line[:160]))
        for m in RAF.finditer(line):
            # 判定「rAF 驱动的批次循环」：
            #   A) 回调内部/命名函数定义窗口里再次出现 requestAnimationFrame（自续帧循环）；
            #   B) 回调实参（取到配对括号）含批次词汇；
            #   C) 命名回调的函数体窗口含批次词汇。
            inside, end = _balanced_call(code, line_start + m.end() - 1)
            reason = None
            if "requestAnimationFrame" in inside:
                reason = "self-loop"
            elif BATCH_WORDS.search(inside):
                reason = "inline-batch"
            else:
                mid = CALLBACK_ID.search(line)
                if mid:
                    body = _named_fn_window(code, mid.group(1))
                    if BATCH_WORDS.search(body) or "requestAnimationFrame" in body:
                        reason = "named-batch-loop"
            if reason:
                hits.append(dict(rule="raf", line=ln, text=line.strip(), snippet=line.strip()[:160], why=reason))
        line_start += len(line) + 1
    return hits


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=DEFAULT_DIR)
    args = ap.parse_args()
    base = os.path.abspath(args.dir)
    files = []
    for dirpath, _dirnames, filenames in os.walk(base):
        for fn in sorted(filenames):
            if fn.endswith(".js"):
                files.append(os.path.join(dirpath, fn))

    # 白名单按 (file, rule) 建索引；同一行可命中多条（如双 rAF），按最长锚点取一条。
    wl = {}
    for w in WHITELIST:
        wl.setdefault((w["file"], w["rule"]), []).append(dict(w, used=0))
    if not files:
        print("FAIL: 目录下没有 JS 文件（检查 --dir）：%s" % base)
        return 1

    findings = []
    for path in files:
        rel = os.path.relpath(path, base).replace("\\", "/")
        for h in scan_file(path):
            # 同规则多条白名单可命中同一行（如双 rAF）⇒ 取最长锚点，避免前缀互相抢占
            cands = [w for w in wl.get((rel, h["rule"]), [])
                     if (w["anchor"] in h["text"] or w["anchor"] in h.get("call", ""))
                     and w["used"] < w["max"]]
            matched = max(cands, key=lambda w: len(w["anchor"])) if cands else None
            if matched:
                matched["used"] += 1
                continue
            findings.append((rel, h))

    stale = []
    for rows in wl.values():
        for w in rows:
            if w["used"] == 0:
                stale.append(w)

    if findings or stale:
        print("FAIL: 调度纪律守卫未通过（%d 处新增手写调度，%d 条白名单陈旧）" % (len(findings), len(stale)))
        for rel, h in findings:
            print("  - %s:%d [%s] %s" % (rel, h["line"], h["rule"], h["snippet"]))
        for w in stale:
            print("  - 白名单陈旧 %s [%s] anchor=%r（%s）" % (w["file"], w["rule"], w["anchor"], w["reason"]))
        print("\n正规做法：改用 MemoriaScheduler.schedule({kind,key,priority,run})；"
              "结构性例外才进 scripts/check_scheduler_discipline.py 的 WHITELIST 并同步文档 §3.6。")
        return 1
    total = sum(w["used"] for rows in wl.values() for w in rows)
    by_rule = {}
    for (_f, r), rows in wl.items():
        by_rule[r] = by_rule.get(r, 0) + sum(w["used"] for w in rows)
    detail = " / ".join("%s=%d" % (k, by_rule[k]) for k in ("timeout0", "idle", "raf") if k in by_rule)
    print("PASS: 扫描 %d 个 JS 文件；无新增手写调度；白名单 %d 条全部命中（共 %d 处：%s）。"
          % (len(files), len(WHITELIST), total, detail))
    return 0


if __name__ == "__main__":
    sys.exit(main())
