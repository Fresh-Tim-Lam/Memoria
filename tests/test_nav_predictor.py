"""导航预测器的契约钉子：算法（`js/nav-model.js`）、记录与落盘（`js/nav-predictor.js` + RPC）、接线。

来源 = 人（2026-09-24）：「我们有**双重预渲染设计**，一个是显示区域的页签里面的文件，我们为他们设计了
一个缓存池（如果文件从这关闭，直接从缓存池删掉），一个是**基于知识节点的智能预渲染预测**」，并在同日
提出用**马尔可夫链**记录"以文件为粒度的跳转行为"（设计见 `docs/design/preview-render-pipeline.md`
§3.5 / §3.6）。本文件钉住四件事：

1. **算法可单跑**：`nav-model.js` 是纯函数（无 DOM / 无 IO）⇒ 用 `node` **真跑**一遍数值；
2. **记录的接入点零漂移**：`nav-stack.js` **一行未改**，由 `nav-predictor.js` 在它导出**之后**包装
   它的五个出口（`push` / `openFileFromTree` / `navBack` / `navForward` / `clear`）；
3. **反污染是结构性的**：`nav-stack` 的这几个出口本来就只在**用户发起**时被调（`skipNav:true` 的
   编程式重开、预渲染自身都不走它们）⇒ 不会学成自己的尾巴；
4. **落点与上限**：`<kb>/.memoria/cache/nav/transitions.jsonl`（**可再生缓存**，`AGENTS.md §1`），
   前端不直接碰盘、路径写死（无穿越面）、超限明确报 `nav_log_too_large`。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from memoria.presentation.api import ui as ui_mod

_ROOT = Path(__file__).resolve().parents[1]
_APP = _ROOT / "src" / "memoria" / "ui" / "static" / "app"
_NAVMODEL = _APP / "js" / "nav-model.js"
_PREDICTOR = _APP / "js" / "nav-predictor.js"
_STACK = _APP / "js" / "nav-stack.js"
_APPJS = _APP / "js" / "app.js"
_DISPLAY = _APP / "js" / "display-settings.js"
_INDEX = _APP / "index.html"
_UIPY = _ROOT / "src" / "memoria" / "presentation" / "api" / "ui.py"
_LOCALES = {"zh-CN": _APP / "i18n" / "zh-CN.js", "en": _APP / "i18n" / "en.js"}

DAY = 86400000

#: 在 `node` 里把纯函数模块当浏览器全局加载，输出一份 JSON 供 Python 侧断言（数值一目了然）。
_PROBE = r"""
const fs = require("fs");
const code = fs.readFileSync(process.argv[1], "utf-8");
new Function("window", "globalThis", code)(globalThis, globalThis);
const M = globalThis.MemoriaNavModel;
const D = M.DEFAULTS;
const now = 1700000000000;
function seed() {
  const m = M.create();
  for (let i = 0; i < 50; i += 1) M.record(m, "a.md", "b.md", now - i * 1000, D);
  for (let i = 0; i < 6; i += 1) M.record(m, "a.md", "c.md", now - i * 1000, D);
  M.record(m, "b.md", "d.md", now, D);
  return m;
}
const cold = M.create();
for (let i = 0; i < 10; i += 1) M.record(cold, "a.md", "b.md", now, D);
const m = seed();
const top = M.predict(m, { start: "a.md", now: now, policy: D });
// KP 两级：同一文件的两个知识点 ⇒ 投影到文件时相加
const kp = M.create();
for (let i = 0; i < 30; i += 1) M.record(kp, M.nodeKey("cur.md", "k1"), M.nodeKey("big.md", "k1"), now, D);
for (let i = 0; i < 30; i += 1) M.record(kp, M.nodeKey("cur.md", "k2"), M.nodeKey("big.md", "k2"), now, D);
M.record(kp, M.nodeKey("cur.md", "k1"), "small.md", now, D);
// 自环：同一节点重复"跳转"不计边
const self = M.create();
for (let i = 0; i < 60; i += 1) M.record(self, "a.md", "a.md", now, D);
console.log(JSON.stringify({
  defaults: D,
  modes: M.MODES,
  minSamples: M.MIN_SAMPLES,
  deep: M.STEPS,
  restart: M.RESTART,
  stats: M.stats(m),
  top: top.map((x) => [x.file, Math.round(x.score * 1000) / 1000]),
  coldTop: M.predict(cold, { start: "a.md", now: now, policy: D }),
  offTop: M.predict(m, { start: "a.md", now: now, policy: { navPredictor: "off", navHalfLifeDays: 14 } }),
  unknownStart: M.predict(m, { start: "zzz.md", now: now, policy: D }),
  kpTop: M.predict(kp, { start: M.nodeKey("cur.md", "k1"), now: now, policy: D }).map((x) => [x.file, Math.round(x.score * 1000) / 1000]),
  kpNodes: M.stats(kp).nodes,
  selfEdges: M.stats(self).edges,
  selfSamples: M.stats(self).samples,
  fromLines: M.fromLines("garbage\n{\"a\":1,\"f\":\"a.md\",\"t\":\"b.md\"}\n{\"bad\":true}\n\n", D).samples,
  line: M.toLine({ at: 5, from: "a.md", to: "b.md" }),
  selfLine: M.toLine({ at: 5, from: "a.md", to: "a.md", self: true }),
  compacted: M.compact(m, 1).jsonl.split("\n").filter(Boolean).length,
  sanitize: M.sanitize({ navPredictor: "bogus", navHalfLifeDays: 9999 }),
  sanitizeKeep: M.sanitize({ navPredictor: "off", navHalfLifeDays: 3 }),
}, null, 0));
"""


@pytest.fixture(scope="module")
def probe() -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("本机没有 node，跳过算法数值断言")
    done = subprocess.run([node, "-e", _PROBE, str(_NAVMODEL)], capture_output=True, text=True, timeout=60, check=False)
    assert done.returncode == 0, f"nav-model.js 跑不起来：{done.stderr}"
    return json.loads(done.stdout)


def _predictor() -> str:
    return _PREDICTOR.read_text(encoding="utf-8")


def _stack() -> str:
    return _STACK.read_text(encoding="utf-8")


def _app() -> str:
    return _APPJS.read_text(encoding="utf-8")


# ── ① 算法（node 真跑） ───────────────────────────────────────────────────────


def test_model_defaults_and_shape(probe: dict) -> None:
    assert probe["defaults"] == {"navPredictor": "markov", "navHalfLifeDays": 14}
    assert probe["modes"] == ["off", "markov"]
    assert probe["minSamples"] == 50 and probe["deep"] == 3
    assert 0 < probe["restart"] < 1, "重启概率 α 必须在 (0,1)"
    assert probe["stats"]["ready"] is True and probe["stats"]["samples"] == 57


def test_prediction_is_ranked_and_never_the_current_file(probe: dict) -> None:
    """预测 = 「接下来几跳最可能打开谁」：排第一的必须**不是**当前文件（α 的重启质量留在起点）。"""
    files = [row[0] for row in probe["top"]]
    assert files[0] == "b.md", f"a→b 走了 50 次，b 应排第一，实得 {files}"
    assert "a.md" not in files, "当前文件必须被排除（否则 top-1 恒为'你正在看的这份'）"
    assert probe["top"][0][1] > probe["top"][-1][1], "按分降序"


def test_cold_start_and_explicit_off_return_nothing(probe: dict) -> None:
    """样本不足 `MIN_SAMPLES` ⇒ 回空数组（调用方回退启发式）；显式 `off` ⇒ 同样不回预测。"""
    assert probe["coldTop"] == []
    assert probe["offTop"] == []
    assert probe["unknownStart"] == [], "起点不在模型里 ⇒ 不回预测（回退启发式，而不是瞎猜）"


def test_kp_level_nodes_project_onto_files(probe: dict) -> None:
    """§3.6：**预测在 KP 层、渲染在文件层** —— 同一文件的两个知识点在投影时相加。"""
    assert probe["kpNodes"] == 5, "cur 的两个 KP + big 的两个 KP + small（无 KP 的整文件节点）⇒ 5 个节点"
    files = [row[0] for row in probe["kpTop"]]
    assert files[0] == "big.md", f"big.md 拿到 k1+k2 两份投影，应压过 small.md，实得 {files}"
    assert "cur.md" not in files


def test_self_jump_is_not_an_edge(probe: dict) -> None:
    """同一节点内反复"跳转"不计边（§3.5：同文件内锚点不计跨文件边），只算活跃度。"""
    assert probe["selfEdges"] == 0 and probe["selfSamples"] == 0
    assert probe["selfLine"] == "", "自环不该产出可落盘的行"


def test_log_roundtrip_compaction_and_sanitize(probe: dict) -> None:
    assert probe["line"] == '{"a":5,"f":"a.md","t":"b.md"}'
    assert probe["fromLines"] == 1, "坏行 / 空行必须被丢弃，合法行留下"
    assert probe["compacted"] == 2, "compact(keep=1) ⇒ **每个来源行**只留最强的一条边（该模型有 a.md / b.md 两行）"
    assert probe["sanitize"] == {"navPredictor": "markov", "navHalfLifeDays": 365}, "坏枚举回落默认、超界夹住"
    assert probe["sanitizeKeep"] == {"navPredictor": "off", "navHalfLifeDays": 3}, "合法值原样保留"


def test_model_module_is_pure() -> None:
    src = _NAVMODEL.read_text(encoding="utf-8")
    assert "})(window);" in src and "global.MemoriaNavModel = {" in src
    for forbidden in ("document.", "addEventListener", "call(", "fetch("):
        assert forbidden not in src, f"算法模块不该出现 {forbidden}（要能被 node 单独跑）"


# ── ② 记录：包装 nav-stack（**不改它一行**） ──────────────────────────────────


def test_stack_module_is_untouched() -> None:
    """`nav-stack.js` 保持"纯内存栈"：记录逻辑全在包装层 ⇒ 它零漂移。"""
    src = _stack()
    for forbidden in ("MemoriaNavPredictor", "MemoriaNavModel", "nav_model_", "transitions.jsonl"):
        assert forbidden not in src, f"nav-stack.js 不该出现 {forbidden}"
    assert "window.MemoriaNavStack = (function () {" in src, "导出形状不变"


def test_predictor_wraps_every_user_navigation_exit() -> None:
    src = _predictor()
    assert "const base = { push: STACK.push, openFileFromTree: STACK.openFileFromTree, navBack: STACK.navBack, navForward: STACK.navForward, clear: STACK.clear };" in src, (
        "必须先留下原始引用再包装"
    )
    for name in ("push", "openFileFromTree", "navBack", "navForward", "clear"):
        assert f"STACK.{name} = function" in src, f"{name} 未包装 ⇒ 那条用户导航不会被记录"
    assert "_previewCacheDrop" not in src and "document." not in src, "预测器不碰预览池、不碰 DOM"


def test_anti_pollution_is_structural() -> None:
    """反污染不靠过滤、靠**接入点**：`nav-stack` 的出口只在用户导航时被调（`skipNav` 的编程式重开不走它）。"""
    app = _app()
    assert "if (!opts.skipNav && !opts.fromNav && window.MemoriaNavStack) {" in app, "用户入口的判据（这条就是反污染的上游保证）"
    src = _predictor()
    assert "opts.skipNav" not in src and "frame.skipNav" not in src, "预测器自己不判 skipNav —— 它只认 nav-stack 的出口"


def test_switch_kb_drops_pending_instead_of_polluting(probe=None) -> None:
    """换库：`clear()` 里**不 flush**（换库后 RPC 指向新库，写过去就是污染）⇒ 只丢一个去抖窗口。"""
    src = _predictor()
    clear_body = src[src.index("STACK.clear = function") : src.index("function setPolicy")]
    assert "flushNow()" not in clear_body, "clear() 里不许 flush（否则旧库模型会写进新库）"
    assert "model = MODEL.create();" in clear_body
    assert "loaded = false;" in clear_body, "换库后必须重新载入"


# ── ③ 落盘：RPC 真跑（临时库目录，不碰真库） ─────────────────────────────────


def _fake(kb: Path | None) -> SimpleNamespace:
    return SimpleNamespace(_svc=SimpleNamespace(kb_path=str(kb) if kb else ""))


def test_rpc_read_write_roundtrip(tmp_path: Path) -> None:
    fake = _fake(tmp_path)
    assert ui_mod._nav_model_read(fake) == {"status": "ok", "text": "", "bytes": 0}, "首次使用 ⇒ 空串，不报错"
    assert ui_mod._nav_model_write(fake, '{"a":1,"f":"a.md","t":"b.md"}\n', True)["status"] == "ok"
    assert ui_mod._nav_model_write(fake, '{"a":2,"f":"b.md","t":"c.md"}\n', True)["status"] == "ok"
    read = ui_mod._nav_model_read(fake)
    assert read["status"] == "ok" and read["text"].count("\n") == 2, "两次追加 ⇒ 两行"
    assert ui_mod._nav_model_write(fake, "", False)["status"] == "ok"
    assert ui_mod._nav_model_read(fake)["text"] == "", "重写模式（紧凑化）能把文件清空"
    log = tmp_path / ".memoria" / "cache" / "nav" / "transitions.jsonl"
    assert log.is_file(), "落点必须是 .memoria/cache/nav/（可再生缓存）"


def test_rpc_refuses_without_kb_and_over_limit(tmp_path: Path) -> None:
    none = ui_mod._nav_model_read(_fake(None))
    assert none["status"] == "error" and none["code"] == "no_kb"
    fake = _fake(tmp_path)
    too_big = "x" * (ui_mod._NAV_LOG_MAX_WRITE_BYTES + 1)
    res = ui_mod._nav_model_write(fake, too_big, True)
    assert res["status"] == "error" and res["code"] == "nav_log_too_large", "超限要明确报错，不许偷偷截断"


def test_rpc_takes_no_path_argument() -> None:
    """两条 RPC **路径写死**（不收路径参数）⇒ 没有目录穿越面。"""
    src = _UIPY.read_text(encoding="utf-8")
    assert '_NAV_LOG_REL = ".memoria/cache/nav/transitions.jsonl"' in src
    assert "def _nav_model_read(self) -> dict:" in src, "读：无参数"
    assert "def _nav_model_write(self, text: str, append: bool = True) -> dict:" in src, "写：只有 text + append"
    assert "UIAPI.nav_model_read = _nav_model_read" in src and "UIAPI.nav_model_write = _nav_model_write" in src
    assert "_NAV_LOG_MAX_BYTES = 8 * 1024 * 1024" in src


def test_predictor_only_uses_the_two_rpcs() -> None:
    src = _predictor()
    methods = set(re.findall(r'call\("([a-z_]+)"', src))
    assert methods == {"nav_model_read", "nav_model_write"}, f"只许这两条 RPC，实得 {sorted(methods)}"


# ── ④ 接线：app.js 用预测排序、设置面板给开关 ────────────────────────────────


def test_candidate_is_picked_by_gain_not_by_tab_order() -> None:
    app = _app()
    assert "return _preloadRanked(pool)[0] || pool[0];" in app, "候选池不变，只改顺序；排不出分则保持原顺序"
    assert "gain: _preloadGain(path, scoreOf[path] || 0)" in app, "马尔可夫分 × T̂"
    assert "gain: _preloadGain(path, _preloadAdjacency(path, state.currentPath) + recent)" in app, "启发式回退也乘 T̂"
    assert "if (gap === 1) return 1;" in app and "if (gap === 2) return 0.4;" in app, "相邻档位"
    assert "const exclude = new Set(_previewDomCache.keys());" in app, "预测要排除已在池的"


def test_policy_is_forwarded_and_hit_rate_is_measured() -> None:
    app = _app()
    assert "window.MemoriaNavPredictor.setPolicy(next || {});" in app
    assert "if (kind === \"preload\" && _previewDomCache.has(path) && window.MemoriaNavPredictor" in app, "只有**留在池里**的预渲染才算分母"
    assert "nav: (window.MemoriaNavPredictor && typeof window.MemoriaNavPredictor.stats === \"function\")" in app, "读数带导航模型"


def test_prerender_requires_an_open_document() -> None:
    """规则（人 2026-09-24）：「**预渲染要在文件（预览或者源码或者分栏模式）打开之后**」。"""
    app = _app()
    assert "function _preloadDocumentOpen() {" in app
    assert 'return mode === "preview" || mode === "source" || mode === "split";' in app, "三种视图都算「打开」"
    assert "if (!doc || doc.path !== state.currentPath) return false;" in app, "必须是当前文档、且已加载完"
    assert "if (!_preloadEnabled || _preloadIdle != null || _preloadRunning || !_preloadDocumentOpen()) return;" in app, "调度入口要拦"
    assert "if (_dirty || _renderingPreview || document.hidden || !_preloadDocumentOpen()) return;" in app, (
        "执行入口也要拦（空闲回调可能晚到，那时文件可能已被换掉）"
    )


def test_stale_speculative_prerenders_are_pruned_after_a_switch() -> None:
    """规则（人 2026-09-24）：切换文件后，把**投机**的预渲染产物与**新候选集**比对并删除，避免滞留。"""
    app = _app()
    assert "function _preloadPruneStale() {" in app
    assert "if (!entry || !entry.prerendered) continue;   // 只清投机产物，绝不碰人看过的那条" in app, (
        "人**真正打开过**的条目一律保留（那是第一层的正经缓存）"
    )
    assert "for (const item of _preloadPredictedFiles()) keep.add(item.path);" in app, "保留集 = 打开着的页签 ∪ 仍被预测的"
    assert "_notifyRenderSettled(); _preloadPruneStale(); _preloadSchedule(); _markPreviewDomCurrent(doc);" in app, (
        "**先清滞留、再排新的**（顺序反了会把还要用的也当成过期删掉）"
    )
    assert "prerendered: false," in app, "`_previewCacheStash` 写的是 false ⇒ 切走过（人看过）的条目不再是投机产物"
    assert "stalePruned: _preloadPrunedStale," in app, "读数要能看见清了多少"


def test_prediction_may_target_files_that_are_not_open_tabs() -> None:
    """第二层要能提前渲染「你还没打开的下一章」—— 否则它只是重排页签、没有意义；上限与守卫都要在。"""
    app = _app()
    assert "var PRELOAD_PREDICT_MAX = 2;" in app, "只做收益最高的几个（再多就是烧 CPU 赌运气）"
    assert "for (const item of _preloadPredictedFiles().slice(0, PRELOAD_PREDICT_MAX)) {" in app
    assert ".filter(function (item) { return item.gain > 0 && !open.has(item.path) && item.path !== state.currentPath; })" in app, (
        "预测目标自己排除已打开的（那一路归页签来源）"
    )
    assert "if (!_preloadStillWanted(path)) return false;" in app, "`_preloadOne` 的守卫放宽到「打开的页签 **或** 仍在预测目标里」"
    assert "function _preloadStillWanted(path) {" in app and "return _preloadPredictedFiles().some(" in app


def test_settings_expose_the_predictor() -> None:
    src = _DISPLAY.read_text(encoding="utf-8")
    assert 'navPredictor: "markov",' in src and "navHalfLifeDays: 14," in src
    assert "navHalfLifeDays: [0.5, 365]," in src
    assert 'if (key === "navPredictor") {' in src, "枚举键要单独归一（不许被当数字解析）"
    assert 'data-display-setting="navPredictor"' in src and "<select" in src
    assert "data-nav-reset" in src and "function resetNavModel()" in src
    assert "nav.clearModel()" in src
    assert 'navReset.addEventListener("click", function () { resetNavModel(); refreshPerfLive(root); });' in src


def test_index_loads_nav_modules_after_tab_order() -> None:
    html = _INDEX.read_text(encoding="utf-8")
    scripts = re.findall(r"<script src=\"([^\"]+)\"></script>", html.split("</body>")[0])
    assert scripts.index("/app/js/nav-stack.js") < scripts.index("/app/js/nav-model.js")
    assert scripts.index("/app/js/nav-model.js") < scripts.index("/app/js/nav-predictor.js")
    assert scripts[-1] == "/app/js/nav-predictor.js", f"最后一个 script 是 {scripts[-1]}"


def test_copy_exists_in_both_locales() -> None:
    top = ("perfNavNote", "perfLiveNav", "perfLiveStale", "perfNavReset", "perfNavResetDone")
    for locale, path in _LOCALES.items():
        text = path.read_text(encoding="utf-8")
        for key in top:
            assert f"{key}:" in text, f"{locale} 缺 {key}"
        for source in ("off", "markov"):
            assert f"{source}:" in text, f"{locale} 缺 perfNavMode.{source}"
        assert "perfNavMode: {" in text
        assert "navPredictor:" in text and "navHalfLifeDays:" in text, f"{locale} 缺 perfField 的两个新键"
        assert 'T("settings.display.perfNavMode." + mode)' in _DISPLAY.read_text(encoding="utf-8")
