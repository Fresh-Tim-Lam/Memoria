/**
 * 导航预测器：把用户的**文件级跳转**喂进 `nav-model`，按分给出"下一个该预渲染谁"（2026-09-24 追加）。
 *
 * 设计见 `docs/design/preview-render-pipeline.md` §3.5（马尔可夫链）/ §3.6（KP 层）。三层分工：
 *
 * | 模块 | 职责 | 是否碰 DOM/IO |
 * |---|---|---|
 * | `nav-stack.js` | **真源**：导航历史栈（文件 + kpId + 来源） | 否（**本模块不改它一行**） |
 * | `nav-model.js` | **纯算法**：转移计数（时间衰减）/ 截断 PPR / PageRank 先验 / 投影回文件 | 否 |
 * | **本模块** | 记录（包装 nav-stack）+ 落盘（RPC）+ 对外门面 | 走 RPC，不碰 DOM |
 *
 * **为什么包装而不是改 nav-stack.js**：`push` / `openFileFromTree` / `navBack` / `navForward` / `clear`
 * 这五个出口**本来就排除了** `skipNav:true` 的编程式重开（refresh 四连、写面同步、预渲染自身都不走它们）
 * ⇒ 在这里记录天然满足 §3.5 的**反污染**要求（不会学成自己的尾巴），且 `nav-stack.js` **零漂移**：
 * 包装发生在它导出**之后**（函数声明提升 + 闭包引用原函数）。
 *
 * **帧里已经带 `kpId`** ⇒ 顺便把 §3.6 的 KP 级边也记下了（节点键 = `file\0kpId`），
 * 投影回文件由 `nav-model.projectFiles` 一次完成 —— 预测在 KP 层、渲染在文件层。
 *
 * **落点**：`<kb>/.memoria/cache/nav/transitions.jsonl`（**可再生缓存**，`AGENTS.md §1`）。
 * 写是"追加一行"（`nav_model_write` 的 append 模式）；行数超 `MAX_RECOMPACT_LINES` 时紧凑化重写；
 * 前端**不直接碰盘**，全部经 RPC。读侧只认合法行（`fromLines` 坏行丢弃）。
 */
(function (global) {
  "use strict";

  const STACK = global.MemoriaNavStack;
  const MODEL = global.MemoriaNavModel;
  if (!STACK || !MODEL) return;   // 依赖缺席（老发布包 / 脚本没加载）⇒ 整个模块静默退场，app.js 自动回退启发式

  /** 追加去抖：一次会话里连续切页签不该每次都发 RPC。 */
  const FLUSH_MS = 1500;
  /** 读侧上限（后端也会夹）：超了就紧凑化重写。 */
  const MAX_LINES = MODEL.MAX_RECOMPACT_LINES;

  let policy = MODEL.DEFAULTS;
  let model = MODEL.create();
  let loaded = false;
  let loading = null;
  let pending = [];        // 待追加的 JSONL 行
  let buffered = [];       // **载入完成前**记下的行：`load()` 会用磁盘版**替换**内存版 ⇒ 这几条必须先攒着、载入后重放，否则被丢掉
  let appended = 0;        // 本会话已追加的行数（用于判断要不要紧凑化）
  let timer = null;
  let preloaded = Object.create(null);   // 本会话"被预渲染过的文件" ⇒ 用命中率回答"预测准不准"
  let hits = 0;
  let misses = 0;

  function call(method, ...args) {
    const app = global.MemoriaApp;
    if (!app || typeof app.call !== "function") return Promise.resolve({ status: "error", code: "no_bridge" });
    try { return Promise.resolve(app.call(method, ...args)); } catch (_) { return Promise.resolve({ status: "error" }); }
  }

  function flushNow() {
    if (timer) { clearTimeout(timer); timer = null; }
    if (!pending.length) return Promise.resolve(null);
    const body = pending.join("") ;
    pending = [];
    appended += body.split("\n").filter(Boolean).length;
    const tooBig = appended > MAX_LINES;
    return call("nav_model_write", tooBig ? MODEL.compact(model).jsonl : body, !tooBig).then(function (res) {
      if (res && res.status === "ok") { if (tooBig) appended = MODEL.compact(model).jsonl.split("\n").filter(Boolean).length; return res; }
      // 追加失败 / 后端说太大 ⇒ 紧凑化重写一次（再不成就放弃这一批，缓存丢了不影响正确性）
      appended = 0;
      return call("nav_model_write", MODEL.compact(model).jsonl, false).catch(function () { return null; });
    }).catch(function () { return null; });
  }

  function schedule() {
    if (timer) return;
    timer = setTimeout(function () { flushNow(); }, FLUSH_MS);
  }

  /** 载入当前库的模型（**懒加载**：第一次需要时或换库后）。 */
  function load() {
    if (loaded) return Promise.resolve(model);
    if (loading) return loading;
    loading = call("nav_model_read").then(function (res) {
      if (res && res.status === "ok" && typeof res.text === "string") model = MODEL.fromLines(res.text, policy);
      // 载入是用磁盘版**替换**内存版 ⇒ 把"载入期间记下的"重放进去，一条都不丢
      for (const line of buffered) {
        try { const rec = JSON.parse(line); MODEL.record(model, rec.f, rec.t, rec.a, policy); } catch (_) { /* 坏行丢弃 */ }
      }
      buffered = [];
      loaded = true;
      loading = null;
      return model;
    }).catch(function () { loaded = true; loading = null; return model; });
    return loading;
  }

  /** 记一条转移（`from` / `to` 都是 nav-stack 的帧）。 */
  function note(fromFrame, toFrame) {
    if (!toFrame || !toFrame.file) return;
    if (String(policy.navPredictor || MODEL.DEFAULTS.navPredictor) === "off") return;
    const from = fromFrame && fromFrame.file ? MODEL.nodeKey(fromFrame.file, fromFrame.kpId) : "";
    const to = MODEL.nodeKey(toFrame.file, toFrame.kpId);
    const rec = MODEL.record(model, from, to, Date.now(), policy);
    const line = MODEL.toLine(rec);
    if (line) {
      pending.push(line + "\n");
      if (!loaded) buffered.push(line + "\n");
      schedule();
    }
    // 预渲染命中率：这个文件此前**被我们预渲染过** ⇒ 预测命中一次
    if (preloaded[toFrame.file]) { hits += 1; delete preloaded[toFrame.file]; } else { misses += 1; }
  }

  const base = { push: STACK.push, openFileFromTree: STACK.openFileFromTree, navBack: STACK.navBack, navForward: STACK.navForward, clear: STACK.clear };

  STACK.push = function (frame) {
    load();
    const prev = STACK.current();
    const entry = base.push.apply(null, arguments);
    note(prev, entry);
    return entry;
  };

  STACK.openFileFromTree = function (file) {
    load();
    const prev = STACK.current();
    const entry = base.openFileFromTree.apply(null, arguments);
    // `openFileFromTree` 内部直接调**内层** push（绕过上面的包装）⇒ 这里补记一次，不会重复计数
    note(prev, entry || { file: file, kpId: null });
    return entry;
  };

  STACK.navBack = function () {
    const prev = STACK.current();
    const entry = base.navBack.apply(null, arguments);
    if (entry) note(prev, entry);
    return entry;
  };

  STACK.navForward = function () {
    const prev = STACK.current();
    const entry = base.navForward.apply(null, arguments);
    if (entry) note(prev, entry);
    return entry;
  };

  STACK.clear = function () {
    // `clear()` 只在**换库 / 关库**时被调（app.js 三处）⇒ 换库后 `nav_model_*` 这两条 RPC 指向的是**新库**，
    // 旧库那份模型此时**已写不回去**了 ⇒ 这里**不 flush、直接丢**最多一个去抖窗口（≤1.5 s）的转移。
    // 代价可接受：它是 `.memoria/cache/**` 的**可再生缓存**，丢几条只影响一点预测质量（不会错）。
    // 反过来（先 flush 再清）会把旧库的模型写进新库，那是**污染**，比丢几条更难收拾。
    const args = arguments;
    if (timer) { clearTimeout(timer); timer = null; }
    pending = [];
    buffered = [];
    appended = 0;
    model = MODEL.create();
    loaded = false;
    loading = null;
    preloaded = Object.create(null);
    hits = 0;
    misses = 0;
    return base.clear.apply(null, args);
  };

  /** 设置通告（`display-settings.js` 的 `applyAll` 调）。 */
  function setPolicy(next) { policy = MODEL.sanitize(next); }

  /** 预测：`{exclude: Set<file>}` ⇒ 按分降序的 `[{file, score}]`（**成本相乘由 app.js 做**）。 */
  function predictNext(options) {
    const opts = options || {};
    const cur = STACK.current();
    const start = cur && cur.file ? MODEL.nodeKey(cur.file, cur.kpId) : "";
    if (!loaded) { load(); return []; }   // 首次调用先把模型读进来，下一轮就有预测了
    return MODEL.predict(model, { start: start, now: Date.now(), policy: policy, exclude: opts.exclude });
  }

  /** 记"这个文件被预渲染进池了"（命中率的分母来自这里，分子在 `note` 里）。 */
  function notePreloaded(file) { if (file) preloaded[file] = true; }

  /** 清空模型（设置面板的「清空导航模型」）：内存清零 + 落盘重写为空。 */
  function clearModel() {
    model = MODEL.create();
    pending = [];
    appended = 0;
    preloaded = Object.create(null);
    hits = 0;
    misses = 0;
    if (timer) { clearTimeout(timer); timer = null; }
    loaded = true;
    return call("nav_model_write", "", false);
  }

  /** 读数（设置面板与人工排查）。 */
  function stats() {
    const s = MODEL.stats(model);
    const total = hits + misses;
    return {
      loaded: loaded,
      loading: !loaded && !!loading,
      pending: pending.length,
      preloaded: Object.keys(preloaded).length,
      hits: hits,
      misses: misses,
      hitRate: total > 0 ? hits / total : 0,
      predictor: policy.navPredictor,
      halfLifeDays: policy.navHalfLifeDays,
      minSamples: MODEL.MIN_SAMPLES,
      nodes: s.nodes,
      edges: s.edges,
      files: s.files,
      samples: s.samples,
      ready: s.ready,
    };
  }

  if (global.document) {
    global.addEventListener("beforeunload", function () { try { flushNow(); } catch (_) { /* ignore */ } });
  }

  global.MemoriaNavPredictor = {
    clearModel: clearModel,
    flushNow: flushNow,
    load: load,
    notePreloaded: notePreloaded,
    predictNext: predictNext,
    setPolicy: setPolicy,
    stats: stats,
  };
})(window);
