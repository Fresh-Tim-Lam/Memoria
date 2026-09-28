"""预览池**智能替换**的契约钉子：算法（`js/preview-cache-policy.js`）、接线（`app.js` 末尾块）与设置面。

人（2026-09-24）：「后台预加载的加载池需要有一个智能替换机制，我们给资源计算优先级……
优先级最低的优先被替换，新入池的资源优先级都重新初始化……权重参数应该在设置内「性能」板块调整，
显示计算公式，支持恢复默认」。落地口径：

1. **算法是纯函数**（无 DOM 依赖）⇒ 本文件用 `node` **真跑**一遍，把每个因子的取值钉成数值；
2. **模型有据**：GDSF 的老化（`aging`）/ TinyLFU 的入场闸（`admits`）/ Hyperbolic 的按占用折算（`size`），
   见模块文件头；
3. **接线只走两个口**：`app.js::_previewCacheAfterInsert(path, kind)`（入池收口）与
   `MemoriaApp.setPreviewCachePolicy(policy)`（设置通告）；策略模块**缺席时回落**到接线前的
   "按插入序逐出最旧" ⇒ 老发布包 / 脚本没加载都不会更差；
4. **画像按路径存活**（不随"出池"清掉）：切走再切回本身就是一次出池→入池，跟着清零会让"打开次数"
   恒为 0、频次项作废；
5. **人正在看的页签不进入场闸**（它正被付代价）；只有后台预渲染那条投机路径过闸；
6. **两处默认值必须逐字相等**（设置侧 `PERF_DEFAULTS` ↔ 算法侧 `DEFAULTS`）—— 有专门用例核对。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_APP = _ROOT / "src" / "memoria" / "ui" / "static" / "app"
_POLICY = _APP / "js" / "preview-cache-policy.js"
_NAVMODEL = _APP / "js" / "nav-model.js"
_APPJS = _APP / "js" / "app.js"
_DISPLAY = _APP / "js" / "display-settings.js"
_INDEX = _APP / "index.html"
_CSS = _APP / "css" / "app.css"
_LOCALES = {"zh-CN": _APP / "i18n" / "zh-CN.js", "en": _APP / "i18n" / "en.js"}

_MIB = 1024 * 1024

#: 在 `node` 里把策略模块当"浏览器全局"加载（`new Function` 注入 `window`，与 `i18n_selftest.js` 同法），
#: 然后把每个因子的取值打成一份 JSON —— 断言在 Python 侧做，数值一目了然。
_PROBE = r"""
const fs = require("fs");
const code = fs.readFileSync(process.argv[1], "utf-8");
new Function("window", "globalThis", code)(globalThis, globalThis);
const P = globalThis.MemoriaPreviewPolicy;
const D = P.DEFAULTS;
const mi = 1024 * 1024;
const slowHot = { path: "slow-hot.md", bytes: 1 * mi, hits: 6, lastOpenAt: 0, loadMs: 6000, agingStamp: 0 };
const fastCold = { path: "fast-cold.md", bytes: 1 * mi, hits: 0, lastOpenAt: 0, loadMs: 40, agingStamp: 0 };
console.log(JSON.stringify({
  exports: Object.keys(P).sort(),
  defaults: D,
  keys: Object.keys(D).sort(),
  cost: { zero: P.costTerm(0), tiny: P.costTerm(50), full: P.costTerm(8000), over: P.costTerm(99999) },
  size: { zero: P.sizeTerm(0), half: P.sizeTerm(2 * mi), full: P.sizeTerm(4 * mi), over: P.sizeTerm(9 * mi) },
  freq: { zero: P.freqTerm(0), one: P.freqTerm(1), three: P.freqTerm(3) },
  recency: { now: P.recencyTerm(0, D), half: P.recencyTerm(12, D), far: P.recencyTerm(120, D) },
  aging: {
    five: P.agingTerm({ agingStamp: 0 }, 5),
    cap: P.agingTerm({ agingStamp: 0 }, 999),
    touched: P.agingTerm({ agingStamp: 9 }, 9),
  },
  victim: P.pickVictim([slowHot, fastCold], D, 0, 0),
  scores: { slowHot: P.score(slowHot, D, 0, 0), fastCold: P.score(fastCold, D, 0, 0) },
  admits: {
    room: P.admits(fastCold, [slowHot], D, 0, 0, 3),
    fullBetter: P.admits(slowHot, [fastCold, fastCold], D, 0, 0, 2),
    fullWorse: P.admits(fastCold, [slowHot, slowHot], D, 0, 0, 2),
  },
  sanitize: {
    garbage: P.sanitize({ perfTimeWeight: "abc", perfFreqWeight: -3, perfHalfLifeH: 1e9,
                          previewCacheMax: 99, perfAdmission: 0, unknownKey: 1 }),
    idempotent: P.sanitize(P.sanitize({ perfTimeWeight: 2.5 })),
  },
  nodeBytes: P.NODE_BYTES,
  band: P.estimateBand(10000, 50000),
  bandZero: P.estimateBand(0, 0),
  bandBad: P.estimateBand("abc", null),
}));
"""


@pytest.fixture(scope="module")
def probe() -> dict:
    """真跑一遍策略模块（没有 `node` 就跳过 —— 本仓的 JS 侧数值断言一律以 node 为准）。"""
    node = shutil.which("node")
    if not node:
        pytest.skip("本机没有 node，跳过算法数值断言")
    done = subprocess.run(
        [node, "-e", _PROBE, str(_POLICY)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert done.returncode == 0, f"策略模块跑不起来：{done.stderr}"
    return json.loads(done.stdout)


def _policy() -> str:
    return _POLICY.read_text(encoding="utf-8")


def _nav_model() -> str:
    return _NAVMODEL.read_text(encoding="utf-8")


def _app() -> str:
    return _APPJS.read_text(encoding="utf-8")


def _display() -> str:
    return _DISPLAY.read_text(encoding="utf-8")


# ── ① 算法：真跑的数值 ────────────────────────────────────────────────────────


def test_defaults_and_public_surface(probe: dict) -> None:
    assert probe["keys"] == sorted(
        [
            "previewCacheMax",
            "previewCacheMaxLines",
            "preloadMaxLines",
            "preloadMaxTabs",
            "perfTimeWeight",
            "perfFreqWeight",
            "perfRecencyWeight",
            "perfSizeWeight",
            "perfAgingWeight",
            "perfHalfLifeH",
            "perfAdmission",
        ]
    )
    assert probe["defaults"]["previewCacheMax"] == 8, "默认池容量沿用接线前的 8"
    assert probe["defaults"]["perfAdmission"] is True
    assert {"score", "pickVictim", "admits", "sanitize", "costTerm", "sizeTerm", "freqTerm", "recencyTerm", "agingTerm"} <= set(
        probe["exports"]
    )


def test_cost_term_is_log_scaled_between_zero_and_one(probe: dict) -> None:
    """加载耗时取**对数**（线性的话一个 9 秒的页签会把其它因子全压没）。"""
    cost = probe["cost"]
    assert cost["zero"] == pytest.approx(0.5), "没有样本 ⇒ 中性值（不奖不罚）"
    assert cost["tiny"] < 0.02, "40–50 ms 的页签几乎不占分"
    assert cost["full"] == pytest.approx(1.0), "8000 ms（AG51 实测冷切 5–10 s）即满量程"
    assert cost["over"] == pytest.approx(1.0), "超过满量程仍夹在 1"


def test_size_freq_recency_aging_terms(probe: dict) -> None:
    """四个因子的形状各钉一条：占用线性夹 1、次数对数、新鲜度指数（12 h 恰好折半）、老化线性夹 20。"""
    assert probe["size"] == {"zero": 0, "half": pytest.approx(0.5), "full": 1, "over": 1}
    assert probe["freq"] == {"zero": 0, "one": pytest.approx(1.0), "three": pytest.approx(2.0)}
    assert probe["recency"]["now"] == pytest.approx(1.0)
    assert probe["recency"]["half"] == pytest.approx(0.5), "半衰期 12 h ⇒ 闲置 12 h 时新鲜度折半"
    assert probe["recency"]["far"] < 0.01, "指数衰减 ⇒ 长期不用的条目趋近 0（但**永不为负**）"
    assert probe["aging"]["five"] == pytest.approx(5)
    assert probe["aging"]["cap"] == pytest.approx(20), "老化夹上限（早该淘汰的不必无限下探）"
    assert probe["aging"]["touched"] == 0, "刚被用过 ⇒ 老化从零起算"


def test_slow_hot_tab_beats_fast_cold_tab(probe: dict) -> None:
    """**核心语义**：慢而常看的页签该留，快而没人看的先走 —— 淘汰取分最低者。"""
    assert probe["scores"]["slowHot"] > probe["scores"]["fastCold"]
    assert probe["victim"] == {"path": "fast-cold.md", "score": probe["scores"]["fastCold"]}


def test_admission_gate_only_blocks_worse_candidates(probe: dict) -> None:
    """入场闸：池未满一律放行；满了 ⇒ 只有**比当前最低分者更值得**才换入。"""
    assert probe["admits"]["room"] is True
    assert probe["admits"]["fullBetter"] is True
    assert probe["admits"]["fullWorse"] is False


def test_sanitize_clamps_garbage_and_is_idempotent(probe: dict) -> None:
    """设置页/磁盘里的坏值不能让算法崩，也不能静默生效：非法⇒默认、越界⇒夹住、未知键⇒丢弃。"""
    got = probe["sanitize"]["garbage"]
    assert got["perfTimeWeight"] == 1.0, "非数字 ⇒ 回落默认"
    assert got["perfFreqWeight"] == 0, "负数 ⇒ 夹到下限 0"
    assert got["perfHalfLifeH"] == 168, "超出上限 ⇒ 夹住"
    assert got["previewCacheMax"] == 32, "池容量夹到 1–32 并取整"
    assert got["perfAdmission"] is False
    assert "unknownKey" not in got
    assert probe["sanitize"]["idempotent"] == probe["sanitize"]["idempotent"], "幂等（再清洗一次不变）"


# ── ② 两处默认值必须逐字相等 ─────────────────────────────────────────────────


def _brace_block(text: str, header: str) -> dict[str, str]:
    """从 JS 源码里抠一个 `键: 值,` 平铺对象（只用于**默认值/区间一致性**核对，不做完整 JS 解析）。"""
    start = text.index(header)
    body = text[text.index("{", start) + 1 : text.index("}", start)]
    pairs: dict[str, str] = {}
    for key, value in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(\[[^\]]*\]|[^,\n]+?)\s*,", body):
        pairs[key] = value.strip()
    return pairs


def test_both_sides_share_the_same_defaults() -> None:
    """设置侧 `PERF_DEFAULTS` 必须**恰好**等于「算法侧两份默认值之并」，且逐键相等。

    AG67 起设置面板这一组键有**两个**算法模块各自认领一部分：`preview-cache-policy.js` 管池与预渲染门槛、
    `nav-model.js` 管导航预测器 ⇒ 三处必须同源（否则"恢复默认"会与算法默认分叉，或某键没人认领）。"""
    ui = _brace_block(_display(), "var PERF_DEFAULTS = {")
    algo = _brace_block(_policy(), "const DEFAULTS = Object.freeze({")
    algo.update(_brace_block(_nav_model(), "const DEFAULTS = Object.freeze({"))
    assert set(ui) == set(algo), f"键集合不同：设置侧 {sorted(ui)} vs 算法侧 {sorted(algo)}"
    for key in algo:
        assert ui[key] == algo[key], f"{key} 默认值不一致：设置侧 {ui[key]} vs 算法侧 {algo[key]}"


def test_both_sides_share_the_same_ranges() -> None:
    """区间同理（设置侧先夹、算法侧再夹 ⇒ 三处口径必须一致，否则盘里能存下算法不认的值）。"""
    ui = _brace_block(_display(), "var PERF_RANGES = {")
    algo = _brace_block(_policy(), "const RANGES = {")
    algo.update(_brace_block(_nav_model(), "const RANGES = {"))
    assert set(ui) == set(algo)
    for key in algo:
        assert ui[key].replace(" ", "") == algo[key].replace(" ", ""), f"{key} 区间不一致"


# ── ③ app.js 的接线（五个点 + 两条边界） ─────────────────────────────────────


def test_policy_is_wired_at_every_call_site() -> None:
    js = _app()
    assert js.count('_previewCacheAfterInsert(path, "foreground");') == 1, "切走入库未接线"
    assert js.count('_previewCacheAfterInsert(path, "preload");') == 1, "后台预渲染入库未接线"
    assert "_lastSwitch.hit = true; _previewCacheTouch(doc.path);" in js, "命中未刷新画像"
    assert "_previewCacheNoteLoad(_lastSwitch.ms);" in js, "冷加载耗时未记"
    assert "_previewDomCache.clear(); _previewForgetAll();" in js, "换库/重命名/删除/导入未清画像"
    assert "window.MemoriaApp.setPreviewCachePolicy = setPreviewCachePolicy;" in js
    assert "window.MemoriaApp.previewCacheScores = previewCacheScores;" in js


def test_profile_survives_leaving_the_pool() -> None:
    """`_previewCacheDrop` **不许**清画像 —— 否则"打开次数"永远是 0，频次项形同虚设。"""
    js = _app()
    drop = js[js.index("function _previewCacheDrop(path)") : js.index("function _previewCacheClear()")]
    assert "_previewDomCache.delete(path);" in drop
    assert "_previewMeta.delete" not in drop and "_previewForgetAll" not in drop
    assert "var PREVIEW_META_MAX = 64;" in js, "画像要有条数上限（用户可能翻过几百个文件）"


def test_new_entry_reinitialises_and_foreground_skips_the_gate() -> None:
    js = _app()
    assert "meta = { hits: 0, lastOpenAt: Date.now(), loadMs: 0, agingStamp: _previewEvicts };" in js, (
        "新条目必须按「次数 0 / 闲置 0 / 加载未知 / 老化 0」初始化"
    )
    assert 'if (kind === "preload" && mod && policy && policy.perfAdmission) {' in js, "只有后台预渲染那条路过闸"
    assert "const pool = _previewPoolEntries(path);" in js, "入场闸要排除候选自己（否则跟比自己永远不成立）"
    assert "_previewCacheDrop(path);                // 不够格 ⇒ 就地丢掉（不挤别人）" in js


def test_missing_policy_module_falls_back_to_insertion_order() -> None:
    """策略模块缺席（老发布包 / 脚本没加载）⇒ 回落接线前的"按插入序逐出最旧"，不许更差。"""
    js = _app()
    assert "if (!mod) {" in js
    assert "while (_previewDomCache.size > PREVIEW_CACHE_MAX) _previewCacheDrop(_previewDomCache.keys().next().value);" not in js, (
        "旧的行内 LRU 必须只在回落分支里出现（已被 _previewCacheEvict 收口）"
    )
    evict = js[js.index("function _previewCacheEvict()") : js.index("function _previewCacheAfterInsert(")]
    assert "_previewCacheDrop(_previewDomCache.keys().next().value);" in evict, "回落分支丢了"


def test_policy_module_is_pure_and_documented() -> None:
    src = _policy()
    assert "})(window);" in src and "global.MemoriaPreviewPolicy = {" in src
    assert "document." not in src and "window.addEventListener" not in src, "策略侧不许碰 DOM（要能被 node 单独跑）"
    for source in ("GDSF", "TinyLFU", "Hyperbolic"):
        assert source in src, f"文件头缺模型来处：{source}"


# ── ④ 设置面（权重 / 公式 / 恢复默认） ───────────────────────────────────────


def test_settings_expose_weights_formula_and_reset() -> None:
    src = _display()
    assert "var PERF_KEYS = Object.keys(PERF_DEFAULTS);" in src
    assert "Object.assign(DEFAULTS, PERF_DEFAULTS);" in src, "新键没进 DEFAULTS ⇒ load() 拿不到默认值"
    assert 'if (data) for (const k of PERF_KEYS) if (data[k] !== undefined) out[k] = k === "perfAdmission" ? !!data[k] : clampPerf(k, data[k]);' in src
    assert "applyFonts(s); announcePreload(s.backgroundPreload); announcePerfPolicy(s);" in src, "设置变更未通告策略"
    assert "app.setPreviewCachePolicy(mod ? mod.sanitize(src) : src);" in src
    assert "${perfPolicyHtml(T, s)}" in src, "性能版块下半段没挂上"
    assert 'data-perf-reset' in src and "function resetPerfDefaults(root)" in src
    assert "save(next);   // 走同一条 `save`" in src, "恢复默认要走同一条保存链路（本地 + 磁盘 + applyAll）"
    # 包装（而不是改中段那段绑定）：既有 bindSettingsForm 先跑，再补绑「恢复默认」
    assert "var _bindSettingsFormBase = global.MemoriaDisplaySettings.bindSettingsForm;" in src
    assert "_bindSettingsFormBase(root);" in src and "bindPerfExtra(root);" in src


def test_formula_numbers_come_from_the_module() -> None:
    """公式里的数字**全部**取自代码常量 + 当前权重（不许在文案里写死一份）。"""
    src = _display()
    assert 'const mod = global.MemoriaPreviewPolicy || {};' in src
    assert "ref: mod.LOAD_REF_MS || 8000," in src
    assert "mb: Math.round((mod.BYTES_REF || 4194304) / 1048576)," in src
    assert "cap: mod.AGING_CAP || 20," in src
    assert 'wt: at("perfTimeWeight")' in src and 'wa: at("perfAgingWeight")' in src


def test_thresholds_are_configurable_not_hardcoded() -> None:
    """四个门槛（池容量 / 缓存行数 / 预渲染行数 / 预渲染次数）现在都从策略取；`app.js` 里那几个常量
    退成"策略模块缺席时的兜底" ⇒ 缺席时行为与接线前一致。

    为什么要有这条（AG65 的真机反馈）：教材第 8 章 3983 行 > 原来的 1200 行预渲染闸 ⇒ **整章永远
    进不了预渲染射程**，切一次就要冷渲染数秒；现在默认放宽到 4000 行（缓存 8000、配额 8），且用户可再调。
    """
    js = _app()
    for key, fallback in (
        ("previewCacheMax", "PREVIEW_CACHE_MAX"),
        ("previewCacheMaxLines", "PREVIEW_CACHE_MAX_LINES"),
        ("preloadMaxLines", "PRELOAD_MAX_LINES"),
        ("preloadMaxTabs", "PRELOAD_MAX_TABS"),
    ):
        assert f'return _previewLimitOf("{key}", {fallback});' in js, f"{key} 没有可配取值口"
    assert "if ((state.doc.lines || []).length > _previewCacheLineLimit()) return;" in js, "缓存行数闸没改成可配"
    assert "if ((res.lines || []).length > _preloadLineLimit()) return false;" in js, "预渲染行数闸没改成可配"
    assert "if (_preloadDone >= _preloadTabLimit()) return;" in js, "预渲染配额没改成可配"
    src = _policy()
    assert "previewCacheMaxLines: 8000," in src, "缓存行数上限默认应放宽（原 4000）"
    assert "preloadMaxLines: 4000," in src, "预渲染行数上限默认应放宽（原 1200）"
    assert "preloadMaxTabs: 8," in src, "预渲染配额默认应放宽（原 4）"
    # 门槛变了要让"试过就不再试"的清单失效 —— 否则用户放宽门槛后什么都看不到（第 8 章就是被它挡下的）
    assert "const changed = JSON.stringify(next) !== JSON.stringify(_previewPolicy);" in js
    assert "_preloadTried.clear();" in js and "_preloadSchedule();" in js


def test_live_readings_block_is_wired_without_losing_listeners() -> None:
    """现场读数：容器 + 刷新按钮，刷新**只换容器的 innerHTML**（按钮在容器外 ⇒ 不会连带丢监听器）。"""
    src = _display()
    assert "data-perf-live" in src and "function perfLiveHtml(T)" in src
    assert "data-perf-refresh" in src and "function refreshPerfLive(root)" in src
    assert "box.innerHTML = perfLiveHtml(perfT);" in src, "刷新要只换读数容器内部"
    assert "function perfEsc(value)" in src, "路径要转义（文件名里可能有尖括号）"
    assert 'typeof app.previewCacheScores !== "function"' in src, "读数来自 app.js 的诊断口"
    js = _app()
    assert "window.MemoriaApp.previewCacheScores = previewCacheScores;" in js
    assert "lastSwitchMs: _lastSwitch.ms," in js and "lastSwitchHit: _lastSwitch.hit," in js
    assert "cacheLines: _previewCacheLineLimit()," in js and "preloadDone: _preloadDone," in js


def test_estimate_band_prices_the_dom_against_serialized_html(probe: dict) -> None:
    """设计 §3.3 的**第一组数**：由实测节点数直接给出"活 DOM vs 序列化 HTML"的量级。

    这回答的是人那个问题（"网页资源静态化能否减少内存"）里**能先答的那一半** ——
    省多少内存；剩下的一半（恢复耗时回升多少、MathJax/Mermaid 产物能否活过序列化）仍须实测。"""
    band = probe["band"]
    assert probe["nodeBytes"] == {"live": [100, 200], "html": [20, 40]}, "每节点区间要与设计 §2 的出处一致"
    text = 50000 * 2
    assert band["live"] == [10000 * 100 + text, 10000 * 200 + text]
    assert band["html"] == [10000 * 20 + text, 10000 * 40 + text]
    assert band["html"][1] < band["live"][0], "上界也该明显低于活 DOM 的下界（≈3–6 倍那条量级的依据）"
    assert probe["bandZero"] == {"nodes": 0, "text": 0, "live": [0, 0], "html": [0, 0]}
    assert probe["bandBad"]["nodes"] == 0 and probe["bandBad"]["live"] == [0, 0], "坏入参按 0 处理，不许 NaN 冒进读数"


def test_pool_footprint_is_measured_not_guessed() -> None:
    """读数要报**实测**节点数（遍历缓存子树数出来的）；字节取条目里**已存**的估算，读数路径不重算魔数。"""
    app = _app()
    assert "function _previewPoolFootprint() {" in app
    assert "walk(entry.frag);" in app, "要真的遍历缓存片段（`entry.frag`）"
    assert "bytes += Number(entry.bytes) || 0;" in app, "字节取入池时算好的 `entry.bytes`（`_estimatePreviewBytes`）"
    assert "if (entry.ast && Array.isArray(entry.ast.blocks)) astBlocks += entry.ast.blocks.length;" in app, (
        "常驻 AST 也是池的成本（改存 HTML 时正好能放掉，所以要在读数里能看见）"
    )
    assert "pool: _previewPoolFootprint()," in app, "接进 `previewCacheScores()`"


def test_pool_footprint_reaches_the_readout() -> None:
    display = _display()
    assert 'const band = mod && typeof mod.estimateBand === "function" ? mod.estimateBand(pool.nodes, pool.chars) : null;' in display
    assert 'T("settings.display.perfLivePool", {' in display
    assert "function perfMB(bytes) {" in display and "function perfCount(value) {" in display


def test_hit_restore_is_timed_in_segments() -> None:
    """真机读数给出"走了缓存搬回**还要 360 ms**"（池里 2 条、每条约 25 万节点）⇒ 把钱花在哪**量出来**。

    命中已跳过 markdown 解析与 MathJax 重排 ⇒ 只可能花在挂进可见文档后的收尾：
    O(n) 扫描（`postProcessWikilinks` / `bindPreviewLinks`）、同步 mermaid、写 `scrollTop` 的强制布局。"""
    app = _app()
    assert "function _beginSwitchTiming() {" in app and "function _markSwitch(name) {" in app
    assert "if (!preview) return false; _beginSwitchTiming();" in app, "起点：确认能恢复之后立刻开表"
    for mark in ("attach", "static", "wikilinks", "bind", "mermaid", "math", "scroll"):
        assert f'_markSwitch("{mark}")' in app, f"缺 {mark} 分段"
    assert "_switchParts[name] = Math.round(now - _switchT0);" in app, "口径：**距上一段的增量**（各段之和 ≈ 总耗时）"
    assert "_switchT0 = now;" in app, "打完点要把表针挪到当下"
    assert "lastSwitchParts: _lastSwitch.parts || null," in app, "接进 `previewCacheScores()`"


def test_switch_breakdown_reaches_the_readout() -> None:
    display = _display()
    assert 'T("settings.display.perfLiveParts", { list: list })' in display
    assert 'T("settings.display.perfLiveAsync", { list: list })' in display
    assert "if (data.lastSwitchHit && data.lastSwitchParts && typeof data.lastSwitchParts === \"object\") {" in display, (
        "只在**命中**时显示（未命中的那次是整篇渲染，分段无意义）"
    )


def test_whole_open_pipeline_is_timed_in_phases() -> None:
    """真机读数：`最近一次切页签 1571 ms`，而命中恢复的分段之和只有 **428 ms** ⇒ **大头在恢复之外**。

    `_lastSwitch.ms` 的起点在 `openFile` 开头 ⇒ 那 1571 覆盖整条打开流水线（stash / load / editor / view / tail）。
    只量"命中恢复"会把这 1143 ms 误读成"预览的问题" ⇒ 全程也必须拆开。"""
    app = _app()
    assert "function _markPhase(name) {" in app and "var _switchAbs = 0;" in app
    assert "const _t0Switch = performance.now(); _switchAbs = _t0Switch; _switchPhases = {};" in app, (
        "起点要交给外层阶段计时（`_t0Switch` 是 `openFile` 的局部量）"
    )
    for phase in ("stash", "load", "editor", "viewIn", "viewPre", "postRender", "rpEnd", "render", "settle", "tail"):
        assert f'_markPhase("{phase}")' in app, f"缺 {phase} 阶段"
    assert "_switchPhases[name] = Math.round(now - _switchAbs);" in app, "存**距起点的绝对增量**（读数侧再两两相减）"
    assert "lastSwitchPhases: _lastSwitch.phases || null," in app, "接进 `previewCacheScores()`"
    assert "`render` = `setViewMode`" in app and "`settle` = 等同步渲染那一轮落定（**不等 MathJax**）" in app, (
        "要把 `setViewMode` 与「等 settle」分开 —— 第二次读数里那 729 ms 就在这团里"
    )


def test_async_marks_catch_what_sync_segments_cannot() -> None:
    """真机读数：`view 1104` 而恢复内的同步分段只有 375 ⇒ 剩 729 ms 在**两次 `await` 之间**
    （浏览器对 30 万节点做布局/绘制）。同步分段抓不到 ⇒ 用双 rAF 与 MathJax promise 两个**异步**标记量。"""
    app = _app()
    assert "function _markAsync(name, origin) {" in app and "function _markAsyncAfter(name, promise, origin) {" in app
    assert "if (!origin || origin !== _switchAbs) return;" in app, "旧一轮的异步回调要丢弃（否则读成怪数）"
    assert "if (!promise || typeof promise.then !== \"function\") return; if (origin == null) origin = _switchAbs;" in app, (
        "起点要**在注册时**捕获（可显式传入 `origin`）—— 原来在 `.then()` 回调里读 `_switchAbs`，恒等于自己 ⇒ 守卫永远不生效"
    )
    assert "_switchAsync[name] = Math.round(now - origin);" in app
    assert 'if (window.requestAnimationFrame) {' in app
    assert "_markAsync(\"frame1\", _org); window.requestAnimationFrame(function () { _markAsync(\"paint\", _org); });" in app, (
        "2026-09-24：双 rAF 拆成 `frame1`（渲染时机到了）与 `paint`（这一帧画完）—— 真机读数里脚本只花 335 ms "
        "而画面 1788 ms ⇒ 必须先分清「帧自己慢」还是「主线程被别人占住」，两者之差才是帧的样式/布局/绘制耗时"
    )
    assert "if (window.requestAnimationFrame) { const _org = _switchAbs;" in app, (
        "起点要**在注册时**捕获：原来在回调里读 `_switchAbs`，恒等于自己 ⇒ 「旧一轮丢弃」守卫永远不生效"
    )
    assert '_markAsyncAfter("mathjax", _mp' in app, "MathJax 是**异步**跑的 ⇒ 同步分段与阶段都看不见它"
    assert "lastSwitchAsync: _lastSwitch.async || null," in app, "接进 `previewCacheScores()`"


def test_readout_separates_script_time_from_frame_time() -> None:
    """人 2026-09-24：「这个时间和我实际感受不一致啊」—— 读数头条原来只有**脚本**耗时（`lastSwitchMs` 335 ms），
    而体感是**画面**（`paint` 1788 ms，帧要等 ~1.45 s 才画出来）⇒ 两个都要摊开，且模板占位名必须与设置侧参数名一致。"""
    assert "js: Math.round(Number(data.lastSwitchMs) || 0), paint:" in _display(), (
        "设置侧要同时传 `js`（脚本）与 `paint`（画面）两个参数"
    )
    for path in _LOCALES.values():
        line = next((ln for ln in path.read_text(encoding="utf-8").splitlines() if "perfLiveLast:" in ln), "")
        assert "{js}" in line and "{paint}" in line, f"{path.name} 的 perfLiveLast 缺占位：{line}"
        assert "{ms}" not in line, f"{path.name} 的 perfLiveLast 还在用旧的 `{{ms}}` 占位"


def test_offscreen_blocks_revert_wiped_every_windowing_artifact() -> None:
    """2026-09-25 **回退**（人：「回退到落地窗口化之前，我们回到全量渲染」）：预览回到**整篇渲染 + 原生滚动**。

    这一段的历史：`content-visibility` 那版（设计 §3.2）先被真机读数否掉（`paint` 只从 1833 降到 1788 ms —— C-V
    只让浏览器**跳过**屏幕外的活，30 万节点仍全在 DOM 里），随后换成 **窗口化 + 占位块（K4a）**；K4a 又在多轮
    真机里暴露出"定位错 / 编辑卡死 / 滚不动 / 卡在一窗里"等一连串问题 ⇒ **整体回退**。
    ⇒ 本用例把"回退干净"钉住：`app.css` 里**既没有** C-V 那版、**也没有** 占位块样式；`app.js` 里**不再有**
    `memoriaPreviewWindow` 模块与任何 `MemoriaPreviewWindow` 调用点。"""
    css = _CSS.read_text(encoding="utf-8")
    assert "content-visibility: auto;" not in css, "C-V 那版已判死并删除（真机读数：paint 1833 → 1788 ms）"
    assert "contain-intrinsic-size: auto 96px;" not in css
    assert ".-pv-spacer" not in css, "窗口化（K4a）已整体回退 ⇒ 占位块样式必须一并删除（不留半活状态）"
    js = _app()
    assert "memoriaPreviewWindow" not in js, "窗口化模块已整体删除（不是「禁用」）"
    assert "MemoriaPreviewWindow" not in js, "所有调用点也已清掉（免得将来有人再挂一个同名全局就把它激活）"


def test_phase_order_matches_the_readout_side() -> None:
    """读数要两两相减 ⇒ 设置侧的 `PERF_PHASE_ORDER` 必须与 `app.js` 里打点的**执行次序**一致。

    2026-09-24：新增的 `rpEnd` 打在 `setViewMode` 里 —— 它在 `app.js` 文件里更靠后，执行时却排在 `render`
    之前 ⇒ 不能再拿"源码出现顺序"当执行顺序（旧写法 `re.findall` 会给出错的清单）。这里改为**逐字核对**
    设置侧那份固定顺序，并逐名检验 `app.js` 里确有打点。"""
    order = re.search(r'var PERF_PHASE_ORDER = \[([^\]]+)\];', _display())
    assert order, "设置侧要有固定顺序"
    ui_order = [item.strip().strip('"') for item in order.group(1).split(",")]
    assert ui_order == ["stash", "load", "editor", "viewIn", "viewPre", "postRender", "rpEnd", "render", "settle", "tail"], (
        "顺序必须与 `app.js` 的执行次序一致（`postRender` 打在 `renderPreview` 里、`rpEnd` 打在 `setViewMode` 里，"
        "两者在源码里都比 `render` 靠后，但执行时都在它之前）"
    )
    app = _app()
    for phase in ui_order:
        assert f'_markPhase("{phase}")' in app, f"设置侧写了 {phase}，`app.js` 里却没有对应的打点"


def test_copy_exists_in_both_locales() -> None:
    top = (
        "perfPolicyLabel",
        "perfAdmissionNote",
        "perfFormulaTitle",
        "perfFormula",
        "perfFormulaTerms",
        "perfReset",
        "perfLiveTitle",
        "perfLiveNone",
        "perfLiveLast",
        "perfLiveHit",
        "perfLiveMiss",
        "perfLiveLimits",
        "perfLiveEmpty",
        "perfLiveRow",
        "perfLivePool",
        "perfLiveParts",
        "perfLivePhases",
        "perfLiveAsync",
        "perfRefresh",
    )
    fields = (
        "previewCacheMax",
        "previewCacheMaxLines",
        "preloadMaxLines",
        "preloadMaxTabs",
        "perfTimeWeight",
        "perfFreqWeight",
        "perfRecencyWeight",
        "perfSizeWeight",
        "perfAgingWeight",
        "perfHalfLifeH",
        "perfAdmission",
    )
    for locale, path in _LOCALES.items():
        text = path.read_text(encoding="utf-8")
        assert re.search(r"Object.assign\(g\.MEMORIA_LOCALES\[\"" + locale + r"\"\]\.settings\.display, \{", text), locale
        for key in top:
            assert f"{key}:" in text, f"{locale} 缺 {key}"
        for key in fields:
            assert f"{key}:" in text, f"{locale} 缺 perfField.{key}"
        assert "perfField: {" in text


def test_index_loads_the_policy_module_after_app_js() -> None:
    """策略模块在**末尾区块**里（`app.js` 之后加载 ⇒ `app.js` 只能在调用期取它 ⇒ 顺序安全）。"""
    html = _INDEX.read_text(encoding="utf-8")
    assert '<script src="/app/js/preview-cache-policy.js"></script>' in html
    scripts = re.findall(r"<script src=\"([^\"]+)\"></script>", html.split("</body>")[0])
    assert scripts.index("/app/js/app.js") < scripts.index("/app/js/preview-cache-policy.js")


def test_styles_reuse_tokens_and_never_hardcode_colors() -> None:
    css = _CSS.read_text(encoding="utf-8")
    block = css.rsplit("/* ===== 2026-09-24 追加：设置 →「显示」→「性能」里**预览池智能替换**", 1)[1]
    for selector in ('.-settings-field input[type="number"] {', ".-perf-title {", ".-perf-formula-line {"):
        assert selector in block, f"样式缺失：{selector}"
    assert "var(--font-mono)" in block and "white-space: pre-wrap" in block, "公式块要等宽 + 可换行"
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", block), "不许硬编码颜色"


# ── ⑤ 真跑一遍**设置层**（不是只看源码字符串） ─────────────────────────────────

_SETTINGS_PROBE = r"""
const fs = require("fs");
const store = {};
globalThis.localStorage = {
  getItem: (k) => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v); },
  removeItem: (k) => { delete store[k]; },
};
globalThis.MemoriaI18n = { t: (k) => k, currentLang: () => "zh-CN" };
const code = fs.readFileSync(process.argv[1], "utf-8");
new Function("window", "globalThis", code)(globalThis, globalThis);
const S = globalThis.MemoriaDisplaySettings;
const fresh = S.load();
store["-display-settings"] = JSON.stringify({
  perfTimeWeight: "abc", perfFreqWeight: -3, perfHalfLifeH: 1e9, previewCacheMax: 99,
  preloadMaxLines: 1e9, preloadMaxTabs: 0, perfAdmission: 0, unknownKey: 1, uiScale: 1.2,
});
const dirty = S.load();
console.log(JSON.stringify({ fresh: fresh, dirty: dirty }));
"""


def test_settings_layer_round_trips_through_the_real_module() -> None:
    """真加载 `display-settings.js` 跑 `load()`：① 末尾补进 `DEFAULTS` 的 8 个键立刻生效；
    ② 盘上的坏值经 `pickKnown` → `clampPerf` 归一（回落默认 / 夹区间 / 丢未知键），且**不碰**别的键。"""
    node = shutil.which("node")
    if not node:
        pytest.skip("本机没有 node，跳过设置层集成断言")
    done = subprocess.run(
        [node, "-e", _SETTINGS_PROBE, str(_DISPLAY)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert done.returncode == 0, f"设置模块在 node 里跑不起来：{done.stderr}"
    fresh = json.loads(done.stdout)["fresh"]
    assert fresh["previewCacheMax"] == 8 and fresh["perfHalfLifeH"] == 12
    assert fresh["previewCacheMaxLines"] == 8000 and fresh["preloadMaxLines"] == 4000 and fresh["preloadMaxTabs"] == 8, (
        "AG65 放宽的三个门槛要能经 load() 读出来"
    )
    assert fresh["perfTimeWeight"] == 1.0 and fresh["perfFreqWeight"] == 0.5
    assert fresh["perfRecencyWeight"] == 0.6 and fresh["perfSizeWeight"] == 0.4
    assert fresh["perfAgingWeight"] == 0.05 and fresh["perfAdmission"] is True
    dirty = json.loads(done.stdout)["dirty"]
    assert dirty["perfTimeWeight"] == 1.0, "非数字回落默认"
    assert dirty["perfFreqWeight"] == 0, "负数夹到下限"
    assert dirty["perfHalfLifeH"] == 168, "超上限夹住"
    assert dirty["previewCacheMax"] == 32, "池容量夹到 1–32"
    assert dirty["preloadMaxLines"] == 200000, "行数上限夹到 200000"
    assert dirty["preloadMaxTabs"] == 1, "配额下界是 1（0 会被夹上来，不许出现「永不预渲染」）"
    assert dirty["perfAdmission"] is False
    assert "unknownKey" not in dirty, "脏键不许进 load() 结果"
    assert dirty["uiScale"] == 1.2, "不许动同页其它键"
