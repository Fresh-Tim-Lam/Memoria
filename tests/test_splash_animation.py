"""task-186 回归守卫：启动蒙层 + 星河动画 + 空灵音效（默认静音 / reduced-motion / 可降级）。

人的要求（原话）：「试试点上蒙层，添加播放酷炫的加载动画，比如星河啥的，最好还要空灵的音效」。

四条硬约束（Lead 加的，全部在这里钉住）：
  ① 不得延长真实启动时间：上限 CAP_MS ≤ 1200、淡出 ≤ 400ms、就绪即淡出、不设最短停留；
  ② 音效默认【关】：DEFAULT_PREFS.sound === false，且没有任何自动开声路径；
  ③ 尊重 prefers-reduced-motion：不跑 rAF + CSS 动画禁用；
  ④ 失败可降级：无 Canvas ⇒ 静态；音频被拒 ⇒ 静默 + 计数；异常也必须淡出。

真机证据（行为层）：artifacts/agent/verify/todo/splash-animation/verify.json
  · T-splash-1 冷启动出现/刷新不出现（真实应用 DOM + 时间戳）
  · T-splash-3 reduced-motion 静态、T-splash-4 音效默认关/可开/持久化
  · T-splash-5 音频被拒静默、T-splash-6 无 Canvas 静态降级、T-splash-7 零外部请求
  · T-splash-2 冷启动时长对照：measures-before/summary.json vs measures-after/summary.json
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "memoria" / "ui" / "static" / "app"
SPLASH = APP / "js" / "splash.js"
INDEX = APP / "index.html"
CSS = APP / "css" / "app.css"
ZH = APP / "i18n" / "zh-CN.js"
EN = APP / "i18n" / "en.js"
ART = ROOT / "artifacts" / "agent" / "verify" / "todo" / "splash-animation"


def splash_src() -> str:
    return SPLASH.read_text(encoding="utf-8")


def extract_function(src: str, name: str) -> str:
    """按花括号配平抽 `function name(...) {...}`（与 tests/test_agent_panel_token.py 同款）。"""
    match = re.search(r"\n\s*function " + re.escape(name) + r"\(", src)
    assert match is not None, f"未在 splash.js 找到函数 {name}"
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


def const_number(src: str, name: str) -> float:
    m = re.search(r"\bvar\s+" + re.escape(name) + r"\s*=\s*(\d+)", src)
    assert m, f"缺常量 {name}"
    return float(m.group(1))


# ── 接线：模块确实被加载，且早于应用主脚本 ────────────────────────────────────


def test_splash_module_is_wired_before_the_app_bundle():
    html = INDEX.read_text(encoding="utf-8")
    assert html.count('<script src="/app/js/splash.js"></script>') == 1, "splash.js 必须且只能被加载一次"
    assert html.index("/app/js/splash.js") < html.index("/app/js/app.js"), (
        "splash.js 必须在 app.js 之前执行（蒙层先于应用首帧出现）"
    )
    assert SPLASH.is_file() and SPLASH.stat().st_size > 10_000


# ── ① 不延长启动时间 ──────────────────────────────────────────────────────────


def test_timing_budget_does_not_extend_startup():
    src = splash_src()
    cap = const_number(src, "CAP_MS")
    fade = const_number(src, "FADE_MS")
    assert cap <= 1200, f"最长遮挡上限必须 ≤1200ms，实际 {cap}"
    assert fade <= 400, f"淡出必须 ≤400ms，实际 {fade}"
    # 就绪即淡出：观察既有 -booting 结束标记（不引入额外等待/最短停留）
    assert 'classList.contains("-booting")' in src
    assert 'fadeOut("ready")' in src
    # 上限与绝对兜底都存在（任何情况下蒙层都要消失，不卡在动画上）
    assert 'fadeOut("cap")' in src and 'fadeOut("safety")' in src
    safety = const_number(src, "SAFETY_MS")
    assert safety >= cap, "绝对兜底必须晚于上限"
    # 淡出开始即不挡输入
    assert 'style.pointerEvents = "none"' in src
    # 初始化不能 await 任何网络/动画（start() 同步返回）
    body = extract_function(src, "start")
    assert "await " not in body, "start() 不得 await（音频/设置都是旁路异步）"


# ── ② 音效默认静音；设置持久化走既有 ui_settings ──────────────────────────────


def test_sound_is_muted_by_default():
    src = splash_src()
    m = re.search(r"var DEFAULT_PREFS = \{([^}]*)\}", src)
    assert m, "缺 DEFAULT_PREFS"
    assert re.search(r"sound\s*:\s*false", m.group(1)), "★ 硬约束：音效默认必须是 false"
    # 没有任何"自动打开"路径：设置只在用户改动时写盘
    assert "save_ui_settings" in src
    assert re.search(r'payload|save_ui_settings', src)
    assert "{ splash: { sound: !!state.prefs.sound, volume: Number(state.prefs.volume) } }" in src, (
        "持久化必须走既有 ui_settings 的 splash 段（不新增文件/路径）"
    )


def test_settings_section_reuses_existing_display_tab_without_new_page():
    src = splash_src()
    assert "MemoriaDisplaySettings" in src and "renderSettingsBody" in src, (
        "设置项挂到既有「显示」页签（包装 renderSettingsBody），不新增页签/不新增 index.html 结构"
    )
    assert 'id="splash-sound"' in src and 'id="splash-volume"' in src
    # 打开开关 ⇒ 立即试播（用户手势 = 自动播放策略允许的时刻）
    assert "playChime({ volume: state.prefs.volume });" in src
    # 音量/开关变更会落盘
    assert "writePrefsToDisk()" in extract_function(src, "onSettingsChanged")


# ── ③ 尊重 prefers-reduced-motion ────────────────────────────────────────────


def test_reduced_motion_disables_animation_and_keeps_static_overlay():
    src = splash_src()
    assert "prefers-reduced-motion: reduce" in src
    css = CSS.read_text(encoding="utf-8")
    block = css[css.index(".-memoria-splash {"):]
    assert "@media (prefers-reduced-motion: reduce)" in block, "CSS 必须有 reduced-motion 兜底"
    rm = block[block.index("@media (prefers-reduced-motion: reduce)"):]
    rm_code = re.sub(r"/\*.*?\*/", "", rm, flags=re.S)
    # ★ 仓库样式纪律：不允许 !important（靠更高特异性覆盖）——见 tests/test_checkbox_dot_style.py
    assert "!important" not in rm_code, "splash 的 reduced-motion 兜底不许用 !important"
    assert "animation: none" in rm_code and "transition: none" in rm_code
    assert "html .-memoria-splash" in rm_code, "用 html 前缀提高特异性来压过基础类（(0,1,1) > (0,1,0)）"
    assert ".-memoria-splash__canvas" in rm_code and "display: none" in rm_code
    # JS 侧：reduced-motion 时 mode=static 且不 startStarfield
    assert "reducedMotion()" in src and "staticMode" in src
    assert 'if (!staticMode) {' in src


# ── ④ 失败可降级 ──────────────────────────────────────────────────────────────


def test_canvas_failure_falls_back_to_static_not_blank():
    src = splash_src()
    assert "canvasUsable" in src
    assert 'state.overlay.classList.add("-memoria-splash--static")' in src
    css = CSS.read_text(encoding="utf-8")
    block = css[css.index(".-memoria-splash {"):]
    assert ".-memoria-splash--static .-memoria-splash__canvas { display: none; }" in block
    assert ".-memoria-splash--static .-memoria-splash__sky::before" in block, "静态降级要有 CSS 星点（不白屏）"


def test_audio_failure_is_silent_and_counted():
    src = splash_src()
    assert "audioBlocked" in src and "stats.audioBlocked += 1" in src
    # 自动播放被拒 ⇒ 静默 settle(false) + 计数，不 throw
    assert 'settle(false, "autoplay-blocked")' in src
    assert 'settle(false, "resume-rejected")' in src
    play = extract_function(src, "playChime")
    assert "try {" in play and "catch" in play
    # start() 的兜底：任何异常都要走 fadeOut（绝不留一个永远盖住界面的层）
    start = extract_function(src, "start")
    assert 'fadeOut("error")' in start or "removeOverlay()" in start


def test_splash_css_never_uses_important():
    """整块 splash 样式（文件末尾追加区）**代码里**不许出现 `!important`（注释里讲反例不算）。"""
    css = CSS.read_text(encoding="utf-8")
    region = css[css.index("2026-10-27 task-186 追加"):]
    region = region[region.index("*/") + 2:]  # 从注释块之后开始，避免把块头注释算进来
    code = re.sub(r"/\*.*?\*/", "", region, flags=re.S)
    assert "!important" not in code, "splash 样式里出现 !important（请用特异性/层级/CSS 变量解决）"


def test_theme_aware_background_uses_theme_color_not_fixed_blue_space():
    """背景跟随应用主题：暗色中性深灰 + 亮色中性浅灰，主色光晕/星点用 `--theme-color`（人反馈）。"""
    css = CSS.read_text(encoding="utf-8")
    region = css[css.index("2026-10-27 task-186 追加"):]
    assert 'html[data-theme="light"] .-memoria-splash {' in region, "亮色主题缺蒙层底色"
    assert "var(--theme-color)" in region, "主色调必须取主题色 token"
    assert "color-mix(in srgb, var(--theme-color)" in region, "主题色光晕应基于 token 混合"
    # 不再有固定"蓝色太空"色：旧实现的深蓝底/蓝紫星云不应残留
    for legacy in ("#0b1026", "#070a18", "rgba(84, 124, 255", "rgba(176, 92, 255", "rgba(36, 204, 222"):
        assert legacy not in region, f"仍残留固定蓝色调：{legacy}"
    assert "--splash-star" in region, "静态星点颜色应可随主题切换"

    src = splash_src()
    assert "splashTheme" in src and "data-theme" in src, "JS 应读取应用主题"
    assert 'light ? "#0066bf" : "#007acc"' in src, "读不到 token 时的主题色兜底也要跟随深/浅主题"


def test_star_points_are_animated_not_static():
    """星点不是静态：漂移 + 闪烁 + 流星是常驻 CSS 动画（reduced-motion 时由媒体查询关掉）。"""
    css = CSS.read_text(encoding="utf-8")
    region = css[css.index("2026-10-27 task-186 追加"):]
    assert "@keyframes memoria-splash-drift" in region
    assert "@keyframes memoria-splash-twinkle" in region
    assert "@keyframes memoria-splash-meteor" in region
    canvas = region[region.index(".-memoria-splash__canvas {"):]
    canvas = canvas[: canvas.index("}")]
    assert "memoria-splash-drift" in canvas and "memoria-splash-twinkle" in canvas, "画布必须挂漂移+闪烁动画"
    # 动画周期要"看得出来"（旧实现 26s 太慢，冷启动只展示 <1s 时看起来是静态）
    assert "8.5s" in canvas and "3.6s" in canvas


def test_usage_traces_are_recorded_and_drawn():
    """星点体现"使用痕迹"：打开/编辑过的笔记 → localStorage 星图 → 蒙层按哈希位置点亮。"""
    src = splash_src()
    assert 'var TRACES_LS_KEY = "memoria.splash.stars.v1"' in src
    assert "function traceRecord(" in src and "function traceLoad(" in src
    assert "global.MemoriaSplashTrace" in src and "noteOpen:" in src and "noteSave:" in src
    assert "function tracePoint(" in src and "function traceTier(" in src
    assert "TRACES_MAX = 240" in src
    # 画布确实画了使用痕迹星 + 星轨
    paint = extract_function(src, "paintStars")
    assert "tracePoint" in paint and "traceTier" in paint and "star.p" in paint
    assert "ordered" in paint and "strokeStyle" in paint, "应画出星轨连线"
    # app.js 在"打开成功/保存成功"处同线埋点（零行漂移）
    app = (ROOT / "src" / "memoria" / "ui" / "static" / "app" / "js" / "app.js").read_text(encoding="utf-8")
    assert "MemoriaSplashTrace?.noteOpen?.(relPath)" in app
    assert "MemoriaSplashTrace?.noteSave?.(savePath)" in app
    # 文案（中英）
    for path in (ZH, EN):
        text = path.read_text(encoding="utf-8")
        assert "traces:" in text and "tracesEmpty:" in text, f"{path.name} 缺星图文案"


def test_trace_helpers_are_pure_and_stable():
    """星位稳定（同路径每次同处）+ 亮度按"最近程度"分层 + 容量/得分可测（node 实跑）。"""
    src = splash_src()
    script = (
        "var TRACES_MAX = 240;\nvar now = 1700000000000;\n"
        + extract_function(src, "hash32")
        + "\n" + extract_function(src, "tracePoint")
        + "\n" + extract_function(src, "traceScore")
        + "\n" + extract_function(src, "traceTier")
        + """
const p1 = tracePoint("docs/a.md", 0, 1000, 800);
const p2 = tracePoint("docs/a.md", 0, 1000, 800);
const p3 = tracePoint("docs/b.md", 0, 1000, 800);
const tier = (ageDays) => traceTier({p:"x", n:1, t: now - ageDays*86400000}, now);
const out = {
  stable: p1.x === p2.x && p1.y === p2.y,
  different: p1.x !== p3.x || p1.y !== p3.y,
  inBounds: p1.x >= 0 && p1.x <= 1000 && p1.y >= 0 && p1.y <= 800,
  tiers: [tier(0.1), tier(3), tier(10), tier(100)],
  scoreRecentHigh: traceScore({p:"a", n:2, t: now - 86400000}, now) > traceScore({p:"b", n:2, t: now - 90*86400000}, now),
  scoreFreqWins: traceScore({p:"a", n:10, t: now - 90*86400000}, now) > traceScore({p:"b", n:2, t: now - 90*86400000}, now),
};
console.log(JSON.stringify(out));"""
    )
    out = node_eval(script)
    assert out["stable"] is True and out["different"] is True and out["inBounds"] is True
    assert out["tiers"] == [3, 2, 1, 0], out["tiers"]
    assert out["scoreRecentHigh"] is True and out["scoreFreqWins"] is True


def test_no_external_assets_or_network_in_splash():
    src = splash_src()
    assert "fetch(" not in src and "XMLHttpRequest" not in src
    assert "new Audio(" not in src, "音效必须是 Web Audio 现场合成（没有音频文件/请求）"
    assert "createOscillator" in src and "createConvolver" in src
    assert "http://" not in src and "https://" not in src
    # 不加载外部字体/图片：不出现 url( 与 <img
    assert "url(" not in src
    assert not re.search(r"""["'][^"'\s]+\.(png|ogg|wav|mp3|jpg|jpeg|webp|woff2?)["']""", src, re.I), (
        "splash 不得引用任何图片/音频/字体资源文件"
    )


# ── 冷启动语义 & 纯函数 ───────────────────────────────────────────────────────


def test_splash_is_cold_start_only():
    src = splash_src()
    assert 'var SESSION_KEY = "memoria.splash.seen"' in src
    fn = extract_function(src, "splashShouldShow")
    assert "sessionStorage" in fn and "SESSION_KEY" in fn
    assert "markSeen()" in extract_function(src, "start")


def test_pure_helpers_for_prefs_and_fade_plan():
    src = splash_src()
    cap = int(const_number(src, "CAP_MS"))
    script = (
        "var CAP_MS = " + str(cap) + ";\n"
        + "var DEFAULT_PREFS = { sound: false, volume: 0.35 };\n"
        + extract_function(src, "mergePrefs")
        + "\n" + extract_function(src, "splashFadeDelay")
        + "\nconst out = {"
        + "defaults: mergePrefs(null),"
        + "clampHi: mergePrefs({sound: true, volume: 9}),"
        + "clampLo: mergePrefs({sound: false, volume: -3}),"
        + "junk: mergePrefs({sound: 'yes', volume: 'loud'}),"
        + "readyNow: splashFadeDelay(1000, 1200, 1200),"
        + "readyLater: splashFadeDelay(1000, 1800, 1000),"
        + "notReady: splashFadeDelay(1000, 0, 1000),"
        + "pastCap: splashFadeDelay(1000, 0, 5000)"
        + "}; console.log(JSON.stringify(out));"
    )
    out = node_eval(script)
    assert out["defaults"] == {"sound": False, "volume": 0.35}
    assert out["clampHi"] == {"sound": True, "volume": 1}
    assert out["clampLo"] == {"sound": False, "volume": 0}
    assert out["junk"] == {"sound": False, "volume": 0.35}, "坏类型必须回落到默认（默认静音）"
    assert out["readyNow"] == 0, "就绪 ⇒ 立即淡出"
    assert out["readyLater"] > 0, "未就绪 ⇒ 等就绪"
    assert out["notReady"] == cap, "未就绪且刚到 ⇒ 到上限"
    assert out["pastCap"] == 0, "超过上限 ⇒ 立即淡出（不额外等待）"


# ── i18n 键（中英都有；末尾 Object.assign 追加，不推位锚点）────────────────────


def test_splash_i18n_keys_present_in_both_languages():
    for path in (ZH, EN):
        text = path.read_text(encoding="utf-8")
        assert "splash: {" in text, f"{path.name} 缺 splash 段"
        for key in ("loading:", "subtle:", "a11y:", "title:", "sound:", "volume:", "note:"):
            assert key in text.split("splash: {", 1)[1][:1200], f"{path.name} 的 splash 段缺 {key}"


# ── 真机证据存在（防"只写代码没验收"）────────────────────────────────────────


def test_real_app_evidence_exists():
    verify = ART / "verify.json"
    assert verify.is_file(), f"缺真机 DOM 证据：{verify}"
    data = json.loads(verify.read_text(encoding="utf-8"))
    assert data.get("failed") == 0, f"真机探针有失败项：{data.get('failed')}"
    ids = " ".join(c["id"] for c in data.get("checks", []))
    for tag in ("T-splash-1", "T-splash-3", "T-splash-4", "T-splash-5", "T-splash-6", "T-splash-7",
                "T-splash-9", "T-splash-10"):
        assert tag in ids, f"真机证据缺 {tag}"
    before = ART / "measures-before" / "summary.json"
    after = ART / "measures-after" / "summary.json"
    assert before.is_file() and after.is_file(), "T-splash-2 需要改前/改后各 5 次冷启动对照"
    b = json.loads(before.read_text(encoding="utf-8-sig"))
    a = json.loads(after.read_text(encoding="utf-8-sig"))
    assert b["valid_count"] >= 3 and a["valid_count"] >= 3
    # 公平对照：交错 A/B（同一时间窗内交替 on/off，抵消系统漂移）—— 报告以此为准
    ab = ART / "ab-interleaved.json"
    assert ab.is_file(), "缺交错 A/B 对照（ab-interleaved.json）"
    abj = json.loads(ab.read_text(encoding="utf-8"))
    assert abj["on"]["n"] >= 3 and abj["off"]["n"] >= 3, "交错 A/B 两臂各需 ≥3 次"
    assert abj["delta_ms"] is not None
