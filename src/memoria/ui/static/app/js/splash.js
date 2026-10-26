/**
 * task-186：启动蒙层 + 星河类加载动画 + 空灵音效（默认静音的 Web Audio 合成声）。
 *
 * ## 它是什么 / 不是什么
 *   · 是"**遮住加载过程**"的一层：真实就绪（既有 `html.-booting` 消失 = 首个文档已打开/8s 兜底）
 *     ⇒ **立即**开始淡出；**不设最短停留**；最长遮挡 **1200ms**（超过就淡出，绝不额外等待）。
 *   · 不是额外等待：淡出一开始就 `pointer-events:none`，用户输入不被这层挡住。
 *   · 只在**冷启动**出现：同一窗口会话里刷新/换库不再出现（sessionStorage 标记；窗口新开 = 冷启动）。
 *   · 不替换既有"外框跑马灯"（`html.-booting` 的 logo 脉冲 + 顶部进度条，app.css 既有块）——
 *     本层淡出时它该在就在、该没就没，两套加载指示平滑衔接。
 *
 * ## 四条硬约束（与任务书一一对应）
 *   ① 不延长启动：只加"一层 DOM + 一个 rAF"，不阻塞、不 await 任何网络；上限 1200ms。
 *   ② 音效默认**关**：默认 `sound:false`；开启需用户在设置里点（= 真实用户手势），状态存既有 ui_settings。
 *   ③ 尊重 `prefers-reduced-motion`：只显示静态蒙层 + 文字，不跑 rAF/不画流星。
 *   ④ 失败必须降级：无 Canvas ⇒ 纯 CSS 静态星空；音频被自动播放策略拒 ⇒ 静默跳过 + 计数，
 *      不抛错、不弹窗；任何异常都保证淡出（上限 + 绝对兜底 5s）。
 *
 * ## 零外部资源
 *   · 视觉：Canvas 2D + CSS 渐变，零图片/字体/网络请求。
 *   · 音效：Web Audio 现场合成（正弦泛音 + 程序生成混响脉冲），**没有音频文件**，
 *     因此没有 .ogg/.wav 的体积与许可问题，也不产生请求。
 *
 * ## 可观测性（测试/探针用，不参与 UI）
 *   · `window.__memoriaSplashStats`：{ shown, mode, reducedMotion, fadeReason, audioStarted, audioBlocked, errors }
 *   · `window.MemoriaSplash`：{ isShown, prefs, setSoundEnabled, setVolume, playPreview, _internals }
 *   · 测试钩子（仅探针使用，生产路径不设）：`__memoriaSplashForceStatic` / `__memoriaSplashForceAudioFail`
 */
(function (global) {
  "use strict";
  var DOC = global.document;
  if (!DOC) return;

  // ── 常量（测试按名字断言，改动需同步 tests/test_splash_animation.py）────────────────
  var CAP_MS = 1200;        // 最长遮挡上限（从蒙层出现起算；真实就绪更早则立即淡出）
  var FADE_MS = 320;        // 淡出时长（≤400ms）
  var SAFETY_MS = 5000;     // 绝对兜底：任何情况下蒙层都要消失
  var SESSION_KEY = "memoria.splash.seen";
  var PREFS_LS_KEY = "memoria.splash.prefs";
  var DEFAULT_PREFS = { sound: false, volume: 0.35 };  // ★ 默认静音（硬约束）
  var AUDIO_DURATION_MS = 2400;  // ≤3s
  var I18N_WAIT_MS = 2500;       // 等 i18n 引擎就绪的上限（超时用内置兜底文案）

  var stats = (global.__memoriaSplashStats = {
    shown: false,
    // 冷启动是否出现过（即使探针 attach 晚了，也能用时间戳证明"出现过"）
    everShown: false,
    firstShownAt: 0,         // Date.now()
    fadeStartAt: 0,
    removedAt: 0,
    mode: "idle",            // canvas | static | idle
    reducedMotion: false,
    fadeReason: "",          // ready | cap | safety | error
    audioStarted: false,
    audioBlocked: 0,
    errors: [],
  });

  var state = {
    overlay: null,
    canvas: null,
    ctx: null,
    raf: 0,
    shownAt: 0,
    readyTimer: 0,
    capTimer: 0,
    safetyTimer: 0,
    observer: null,
    pollTimer: 0,
    fading: false,
    audioCtx: null,
    prefs: mergePrefs(null),
    prefsLoaded: false,
    settingsInstalled: false,
    removed: false,
  };

  // ── 小工具 ──────────────────────────────────────────────────────────────────
  function mergePrefs(raw) {
    var out = { sound: DEFAULT_PREFS.sound, volume: DEFAULT_PREFS.volume };
    if (raw && typeof raw === "object") {
      if (typeof raw.sound === "boolean") out.sound = raw.sound;
      if (typeof raw.volume === "number" && isFinite(raw.volume)) {
        out.volume = Math.max(0, Math.min(1, raw.volume));
      }
    }
    return out;
  }

  function reducedMotion() {
    try {
      return !!(global.matchMedia && global.matchMedia("(prefers-reduced-motion: reduce)").matches);
    } catch (e) {
      return false;
    }
  }

  function T(key, vars) {
    try {
      if (global.MemoriaI18n && typeof global.MemoriaI18n.t === "function") {
        var v = global.MemoriaI18n.t(key, vars);
        if (v && v !== key) return v;
      }
    } catch (e) { /* i18n 失败绝不影响启动 */ }
    return "";
  }

  function recordError(where, err) {
    try {
      stats.errors.push(String(where) + ": " + String((err && err.message) || err));
      if (stats.errors.length > 20) stats.errors.shift();
    } catch (e) { /* noop */ }
  }

  /** 冷启动判定：同一窗口/标签页会话只出现一次（刷新、换库、二次打开都不再出现）。 */
  function splashShouldShow() {
    try {
      if (global.sessionStorage && global.sessionStorage.getItem(SESSION_KEY) === "1") return false;
    } catch (e) { /* 存储不可用 ⇒ 按冷启动处理（宁可见一次，也不静默残缺） */ }
    return true;
  }

  function markSeen() {
    try {
      if (global.sessionStorage) global.sessionStorage.setItem(SESSION_KEY, "1");
    } catch (e) { /* noop */ }
  }

  /** 淡出计划（纯函数，便于 node 单测）：就绪 ⇒ 立刻；否则到上限 ⇒ 也必须走。 */
  function splashFadeDelay(shownAt, readyAt, now) {
    if (readyAt && readyAt >= shownAt) return Math.max(0, readyAt - now);
    var left = CAP_MS - (now - shownAt);
    return left > 0 ? left : 0;
  }

  // ── 偏好：localStorage 快路径（首帧就能决定要不要试音）+ ui_settings 权威值 ───────────
  function loadPrefsFast() {
    try {
      var raw = global.localStorage && global.localStorage.getItem(PREFS_LS_KEY);
      if (raw) state.prefs = mergePrefs(JSON.parse(raw));
    } catch (e) { /* noop */ }
  }

  function savePrefsFast() {
    try {
      if (global.localStorage) {
        global.localStorage.setItem(PREFS_LS_KEY, JSON.stringify(state.prefs));
      }
    } catch (e) { /* noop */ }
  }

  function api() {
    try {
      return global.MemoriaBridge && global.MemoriaBridge.api ? global.MemoriaBridge.api() : null;
    } catch (e) {
      return null;
    }
  }

  /** 后端 RPC（pywebview 直回对象；Qt 通道回 JSON 串 ⇒ 两种都吃）。 */
  async function rpc(name, args) {
    var a = api();
    if (!a || typeof a[name] !== "function") throw new Error("api unavailable: " + name);
    var res = args === undefined ? await a[name]() : await a[name](args);
    if (typeof res === "string") {
      try { return JSON.parse(res); } catch (e) { return res; }
    }
    return res;
  }

  /** 等桌面 API 桥就绪（bridge.js 比本文件晚加载；最多等 5s，超时按默认值=静音）。 */
  function whenApiReady(timeoutMs) {
    return new Promise(function (resolve) {
      var deadline = Date.now() + (timeoutMs || 5000);
      (function poll() {
        if (api()) { resolve(true); return; }
        if (Date.now() > deadline) { resolve(false); return; }
        global.setTimeout(poll, 60);
      })();
    });
  }

  async function readPrefsFromDisk() {
    try {
      await whenApiReady(5000);
      var res = await rpc("get_ui_settings");
      var sec = res && res.settings && res.settings.splash;
      state.prefs = mergePrefs(sec);
      state.prefsLoaded = true;
      savePrefsFast();
    } catch (e) {
      state.prefsLoaded = true; // 读不到就用默认（默认静音，安全）
    }
    return state.prefs;
  }

  async function writePrefsToDisk() {
    savePrefsFast();
    try {
      await rpc("save_ui_settings", { splash: { sound: !!state.prefs.sound, volume: Number(state.prefs.volume) } });
      return true;
    } catch (e) {
      recordError("savePrefs", e);
      return false;
    }
  }

  // ── 蒙层 DOM ────────────────────────────────────────────────────────────────
  function buildOverlay(staticMode) {
    var root = DOC.createElement("div");
    root.id = "memoria-splash";
    root.className = "-memoria-splash" + (staticMode ? " -memoria-splash--static" : "");
    root.setAttribute("role", "status");
    root.setAttribute("aria-live", "polite");

    var sky = DOC.createElement("div");
    sky.className = "-memoria-splash__sky";
    var canvas = DOC.createElement("canvas");
    canvas.className = "-memoria-splash__canvas";
    canvas.setAttribute("aria-hidden", "true");
    sky.appendChild(canvas);

    var nebula = DOC.createElement("div");
    nebula.className = "-memoria-splash__nebula";
    nebula.setAttribute("aria-hidden", "true");
    sky.appendChild(nebula);

    var meteor = DOC.createElement("div");
    meteor.className = "-memoria-splash__meteor";
    meteor.setAttribute("aria-hidden", "true");

    var inner = DOC.createElement("div");
    inner.className = "-memoria-splash__inner";
    var brand = DOC.createElement("div");
    brand.className = "-memoria-splash__brand";
    brand.textContent = "Memoria";
    var hint = DOC.createElement("div");
    hint.className = "-memoria-splash__hint";
    hint.id = "memoria-splash-hint";
    hint.textContent = "Memoria";
    inner.appendChild(brand);
    inner.appendChild(hint);
    inner.appendChild(meteor);

    root.appendChild(sky);
    root.appendChild(inner);
    DOC.body.appendChild(root);
    return { root: root, canvas: canvas, hint: hint };
  }

  function setHintText() {
    var hint = state.overlay && state.overlay.querySelector("#memoria-splash-hint");
    if (!hint) return;
    var text = T("splash.loading") || T("app.loading") || "正在进入…";
    hint.textContent = text;
    var sub = T("splash.subtle");
    if (sub) hint.setAttribute("data-subtle", sub);
    state.overlay.setAttribute("aria-label", (T("splash.a11y") || "Memoria") + " " + text);
  }

  // ── 星河（Canvas 2D 一次性绘制 + CSS 动画；**零 rAF**）────────────────────────────
  // 为什么不用 requestAnimationFrame 逐帧画：启动蒙层与"应用首屏"抢同一个主线程 ——
  //   实测逐帧版让冷启动中位数 +193ms（1897→2090ms，T-splash-2 不合格）。
  //   ⇒ 改为"**画一次**（~几 ms）+ 用 CSS transform/opacity 动画制造流动与闪烁"：
  //     主线程在启动关键路径上零占用；视觉仍是"星河缓慢流动 + 星点闪烁 + 偶发流星"。
  //   无 Canvas / 无 GPU 时同样走纯 CSS 静态星空（见 app.css 的 `--static` 块），绝不白屏。
  function canvasUsable(canvas) {
    if (global.__memoriaSplashForceStatic) return false;
    try {
      return !!(canvas && canvas.getContext && canvas.getContext("2d"));
    } catch (e) {
      recordError("canvas", e);
      return false;
    }
  }

  var STARFIELD_DPR = 0.6;      // 蒙层星点是"氛围"不是内容：0.6 倍分辨率（省纹理上传/光栅化，星点略柔反而更像星云）
  var STARFIELD_WIDTH_RATIO = 1.16; // 画布比视口宽 16%（给 CSS 缓慢漂移留余量，不露边）

  /** 把星星画到给定 canvas（只画一次；窗口 resize 时重画一次，开销可忽略）。 */
  function paintStars(canvas, seedOffset) {
    var ctx = canvas.getContext("2d");
    if (!ctx) return false;
    var w = Math.round((global.innerWidth || 1280) * STARFIELD_WIDTH_RATIO);
    var h = Math.round(global.innerHeight || 860);
    canvas.width = Math.max(1, w * STARFIELD_DPR);
    canvas.height = Math.max(1, h * STARFIELD_DPR);
    ctx.setTransform(STARFIELD_DPR, 0, 0, STARFIELD_DPR, 0, 0);
    ctx.clearRect(0, 0, w, h);
    // 银河带：两条极淡的斜向渐变（比逐帧画便宜得多，观感接近）
    var band = ctx.createLinearGradient(0, h * 0.1, w, h * 0.8);
    band.addColorStop(0, "rgba(120,150,255,0.00)");
    band.addColorStop(0.35, "rgba(140,170,255,0.10)");
    band.addColorStop(0.55, "rgba(190,160,255,0.08)");
    band.addColorStop(0.8, "rgba(120,190,255,0.06)");
    band.addColorStop(1, "rgba(120,150,255,0.00)");
    ctx.fillStyle = band;
    ctx.fillRect(0, h * 0.08, w, h * 0.72);
    // 星点：随机但按深度分层（亮星少、暗星多）
    var count = Math.round(Math.min(220, Math.max(90, (w * h) / 12000)));
    for (var i = 0; i < count; i++) {
      var x = Math.random() * w;
      var y = Math.random() * h;
      var depth = Math.random();
      var r = depth > 0.93 ? 1.5 : depth > 0.72 ? 1.0 : 0.6;
      var alpha = 0.22 + depth * 0.72;
      var tint = depth > 0.8 ? "210,228,255" : depth > 0.4 ? "235,240,255" : "190,205,255";
      ctx.beginPath();
      ctx.fillStyle = "rgba(" + tint + "," + alpha.toFixed(3) + ")";
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
      if (depth > 0.96) {
        // 极少数亮星给一点柔光（一次性画，不影响后续帧）
        var glow = ctx.createRadialGradient(x, y, 0, x, y, 6);
        glow.addColorStop(0, "rgba(220,235,255,0.55)");
        glow.addColorStop(1, "rgba(220,235,255,0)");
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(x, y, 6, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    return true;
  }

  function startStarfield() {
    var canvas = state.canvas;
    if (!canvasUsable(canvas)) {
      stats.mode = "static";
      if (state.overlay) state.overlay.classList.add("-memoria-splash--static");
      return;
    }
    try {
      // 单层画布（双层版本纹理上传翻倍，实测冷启动 +124ms；闪烁改由 CSS 对同一画布做 opacity 呼吸）
      if (!paintStars(canvas)) throw new Error("2d context unavailable");
      stats.mode = "canvas";
      // 只在窗口尺寸变化时重画（启动路径上不会触发）
      var resizeTimer = 0;
      global.addEventListener("resize", function () {
        if (state.fading || state.removed) return;
        if (resizeTimer) global.clearTimeout(resizeTimer);
        resizeTimer = global.setTimeout(function () {
          resizeTimer = 0;
          if (state.fading || state.removed) return;
          try {
            paintStars(canvas);
          } catch (e) { recordError("resize-paint", e); }
        }, 250);
      }, { passive: true });
    } catch (e) {
      recordError("starfield", e);
      stats.mode = "static";
      if (state.overlay) state.overlay.classList.add("-memoria-splash--static");
    }
  }

  // ── 空灵音效（Web Audio 现场合成；默认关）────────────────────────────────────
  /** 程序生成混响脉冲（指数衰减的立体声噪声），避免任何音频文件。 */
  function makeImpulse(ctx, seconds, decay) {
    var rate = ctx.sampleRate;
    var len = Math.max(1, Math.floor(rate * seconds));
    var buf = ctx.createBuffer(2, len, rate);
    for (var ch = 0; ch < 2; ch++) {
      var data = buf.getChannelData(ch);
      for (var i = 0; i < len; i++) {
        data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, decay);
      }
    }
    return buf;
  }

  function audioBlocked(err) {
    stats.audioBlocked += 1;
    if (err) recordError("audio", err);
  }

  /**
   * 播一声"空灵"的和声垫（A 大三和弦 + 高八度泛音 + 合成混响，2.4s 自然衰减）。
   * 任何失败（无 Web Audio / 自动播放策略拒绝 / 设备不可用）⇒ 静默返回，绝不影响启动。
   */
  function playChime(opts) {
    return new Promise(function (resolve) {
      var Ctx = global.AudioContext || global.webkitAudioContext;
      if (!Ctx) { audioBlocked(null); resolve({ ok: false, reason: "no-webaudio" }); return; }
      if (global.__memoriaSplashForceAudioFail) {
        audioBlocked(null);
        resolve({ ok: false, reason: "forced-fail" });
        return;
      }
      var volume = opts && typeof opts.volume === "number" ? Math.max(0, Math.min(1, opts.volume)) : state.prefs.volume;
      var ctx;
      try { ctx = new Ctx(); } catch (e) { audioBlocked(e); resolve({ ok: false, reason: "ctx-fail" }); return; }
      state.audioCtx = ctx;
      var done = false;
      function settle(ok, reason) {
        if (done) return;
        done = true;
        if (ok) stats.audioStarted = true;
        resolve({ ok: ok, reason: reason || "" });
      }
      // 自动播放策略：没有用户手势时 resume 会被拒/停在 suspended ⇒ 静默跳过（T-splash-5）
      var resumeResult;
      try { resumeResult = ctx.resume && ctx.resume(); } catch (e) { /* 老实现可能抛 */ }
      var checkState = function () {
        if (ctx.state === "running") { schedule(); return; }
        audioBlocked(null);
        try { ctx.close && ctx.close(); } catch (e) { /* noop */ }
        settle(false, "autoplay-blocked");
      };
      if (resumeResult && typeof resumeResult.then === "function") {
        resumeResult.then(checkState).catch(function (e) { audioBlocked(e); settle(false, "resume-rejected"); });
      } else {
        global.setTimeout(checkState, 120);
      }
      function schedule() {
        try {
          var now = ctx.currentTime + 0.05;
          var master = ctx.createGain();
          master.gain.value = 0.0001;
          master.connect(ctx.destination);
          // 混响：干湿分路（湿 = 程序生成的星空气）
          var conv = ctx.createConvolver();
          conv.buffer = makeImpulse(ctx, 1.9, 2.6);
          var wet = ctx.createGain();
          wet.gain.value = 0.55;
          conv.connect(wet);
          wet.connect(master);
          var dry = ctx.createGain();
          dry.gain.value = 0.45;
          dry.connect(master);
          var lp = ctx.createBiquadFilter();
          lp.type = "lowpass";
          lp.frequency.value = 2600;
          lp.connect(dry);
          lp.connect(conv);
          var peak = Math.max(0.0001, volume * 0.16);
          // 和弦：A3 / C#4 / E4 / A4（加 9 度 B4 做"空灵"）
          var freqs = [220.0, 277.18, 329.63, 440.0, 493.88];
          for (var i = 0; i < freqs.length; i++) {
            var osc = ctx.createOscillator();
            var g = ctx.createGain();
            osc.type = i === 4 ? "triangle" : "sine";
            osc.frequency.value = freqs[i];
            osc.detune.value = (i % 2 ? 4 : -4); // 轻微失谐 ⇒ 有宽度
            var t0 = now + i * 0.06;
            g.gain.setValueAtTime(0.0001, t0);
            g.gain.exponentialRampToValueAtTime(peak / (1 + i * 0.35), t0 + 0.45);
            g.gain.exponentialRampToValueAtTime(0.0001, t0 + AUDIO_DURATION_MS / 1000);
            osc.connect(g);
            g.connect(lp);
            osc.start(t0);
            osc.stop(t0 + AUDIO_DURATION_MS / 1000 + 0.1);
          }
          // 一颗高音铃（1.76kHz）做"星尘"
          var bell = ctx.createOscillator();
          var bg = ctx.createGain();
          bell.type = "sine";
          bell.frequency.value = 1760;
          bg.gain.setValueAtTime(0.0001, now + 0.1);
          bg.gain.exponentialRampToValueAtTime(peak * 0.45, now + 0.16);
          bg.gain.exponentialRampToValueAtTime(0.0001, now + 1.4);
          bell.connect(bg);
          bg.connect(conv);
          bg.connect(dry);
          bell.start(now + 0.1);
          bell.stop(now + 1.5);
          master.gain.setValueAtTime(0.0001, now);
          master.gain.exponentialRampToValueAtTime(1, now + 0.35);
          master.gain.exponentialRampToValueAtTime(0.0001, now + AUDIO_DURATION_MS / 1000);
          global.setTimeout(function () {
            try { ctx.close(); } catch (e) { /* noop */ }
            state.audioCtx = null;
          }, AUDIO_DURATION_MS + 300);
          settle(true, "");
        } catch (e) {
          recordError("audio-schedule", e);
          try { ctx.close && ctx.close(); } catch (e2) { /* noop */ }
          settle(false, "schedule-error");
        }
      }
    });
  }

  // ── 生命周期 ────────────────────────────────────────────────────────────────
  function clearTimers() {
    if (state.capTimer) { global.clearTimeout(state.capTimer); state.capTimer = 0; }
    if (state.safetyTimer) { global.clearTimeout(state.safetyTimer); state.safetyTimer = 0; }
    if (state.pollTimer) { global.clearInterval(state.pollTimer); state.pollTimer = 0; }
    if (state.readyTimer) { global.clearTimeout(state.readyTimer); state.readyTimer = 0; }
    if (state.observer) {
      try { state.observer.disconnect(); } catch (e) { /* noop */ }
      state.observer = null;
    }
  }

  function stopAnimation() {
    if (state.raf) {
      try { global.cancelAnimationFrame(state.raf); } catch (e) { /* noop */ }
      state.raf = 0;
    }
  }

  /** 启动完成后再同步权威偏好（不占用启动关键路径；失败静默）。 */
  function syncPrefsAfterBoot() {
    global.setTimeout(function () {
      readPrefsFromDisk().then(function () {
        try { syncSettingsControls(); } catch (e) { /* noop */ }
      }).catch(function (e) { recordError("prefs-late", e); });
    }, 0);
  }

  function removeOverlay() {
    if (state.removed) return;
    state.removed = true;
    stats.shown = false;
    stats.removedAt = Date.now();
    stopAnimation();
    clearTimers();
    var node = state.overlay;
    if (node && node.parentNode) node.parentNode.removeChild(node);
    state.overlay = null;
    state.canvas = null;
    state.ctx = null;
    syncPrefsAfterBoot();
  }

  /** 淡出：就绪/超时/出错最终都走这里；一旦开始就不再挡输入。 */
  function fadeOut(reason) {
    if (state.fading || state.removed) return;
    state.fading = true;
    stats.fadeReason = reason;
    stats.fadeStartAt = Date.now();
    var node = state.overlay;
    if (node) {
      node.style.pointerEvents = "none";
      node.classList.add("-memoria-splash--leaving");
      node.setAttribute("aria-hidden", "true");
    }
    stopAnimation();
    clearTimers();
    if (stats.mode === "static" || stats.reducedMotion) {
      removeOverlay();
      return;
    }
    global.setTimeout(removeOverlay, FADE_MS);
  }

  function watchReady() {
    var html = DOC.documentElement;
    var sawBooting = false;   // ★ splash.js 先于 app.js 执行：初始没有 -booting，不能当"就绪"
    // 同步补一次（walkaround：若 app.js 恰已执行过）
    if (html.classList.contains("-booting")) sawBooting = true;
    function isReady() {
      if (html.classList.contains("-booting")) { sawBooting = true; return false; }
      return sawBooting;
    }
    function onReady() {
      if (state.fading || state.removed) return;
      fadeOut("ready");
    }
    try {
      state.observer = new global.MutationObserver(function () {
        if (isReady()) onReady();
      });
      state.observer.observe(html, { attributes: true, attributeFilter: ["class"] });
    } catch (e) {
      recordError("observer", e);
    }
    // 观察器之外的轮询兜底（MutationObserver 不可用/被节流时也要能就绪）
    state.pollTimer = global.setInterval(function () {
      if (isReady()) onReady();
    }, 80);
    // 上限：真实就绪更早则上面的 ready 先到；到点也必须走（不额外等待）
    state.capTimer = global.setTimeout(function () {
      if (!state.fading) fadeOut("cap");
    }, CAP_MS);
    // 绝对兜底：任何情况下蒙层都要消失
    state.safetyTimer = global.setTimeout(function () {
      if (!state.fading) fadeOut("safety");
    }, SAFETY_MS);
    if (isReady()) onReady();
  }

  function start() {
    try {
      if (global.__memoriaSplashDisable) { stats.mode = "disabled"; return false; }
      if (!splashShouldShow()) { stats.mode = "idle"; return false; }
      loadPrefsFast();
      stats.reducedMotion = reducedMotion();
      var staticMode = stats.reducedMotion;
      var built = buildOverlay(staticMode);
      state.overlay = built.root;
      state.canvas = built.canvas;
      state.shownAt = Date.now();
      stats.shown = true;
      stats.everShown = true;
      stats.firstShownAt = state.shownAt;
      markSeen();
      if (staticMode) stats.mode = "static";
      watchReady();
      // 文案：i18n 晚到时再补（不阻塞任何东西）
      setHintText();
      var i18nWait = 0;
      var i18nTimer = global.setInterval(function () {
        i18nWait += 60;
        setHintText();
        if (i18nWait >= I18N_WAIT_MS || (T("splash.loading") && !state.removed)) {
          global.clearInterval(i18nTimer);
        }
      }, 60);
      // 动画：reduced-motion ⇒ 不启动任何 rAF（硬约束 ③）
      if (!staticMode) {
        try { startStarfield(); } catch (e) { recordError("starfield", e); stats.mode = "static"; state.overlay.classList.add("-memoria-splash--static"); }
      }
      // 音效：默认静音；只有用户此前在设置里开启过才试（且失败静默）
      // ★ 启动关键路径上**不做后端 RPC**：只用 localStorage 快路径（设置变更时同步写过）。
      //   ui_settings 的权威值在蒙层淡出后再同步（那时启动已完成，慢一点无所谓）。
      //   实测：启动期插一个 get_ui_settings RPC 会让"就绪"晚 ~130ms（与首屏 RPC 高峰抢桥）。
      if (state.prefs && state.prefs.sound && state.prefs.volume > 0) {
        playChime({ volume: state.prefs.volume });
      }
      return true;
    } catch (e) {
      recordError("start", e);
      // 失败也必须能淡出：不留下永远盖住界面的层
      try { fadeOut("error"); } catch (e2) { try { removeOverlay(); } catch (e3) { /* noop */ } }
      return false;
    }
  }

  // ── 设置面板（挂到既有「显示」页签；模块晚于本文件加载 ⇒ 轮询等它出现再包装）────────
  function settingsSectionHtml() {
    var on = !!state.prefs.sound;
    var vol = Math.round(state.prefs.volume * 100);
    var tt = function (k, fb) { return T(k) || fb; };
    return (
      '<section class="-settings-section" id="memoria-splash-settings">' +
      '<h3 class="-settings-heading">' + tt("splash.settings.title", "启动动画") + "</h3>" +
      '<div class="-settings-row -splash-row">' +
      '<label class="-settings-row-label" for="splash-sound">' + tt("splash.settings.sound", "空灵音效") + "</label>" +
      '<input type="checkbox" id="splash-sound" class="-splash-toggle"' + (on ? " checked" : "") + ">" +
      "</div>" +
      '<div class="-settings-row -splash-row">' +
      '<label class="-settings-row-label" for="splash-volume">' + tt("splash.settings.volume", "音量") + "</label>" +
      '<input type="range" id="splash-volume" class="-splash-range" min="0" max="100" step="5" value="' + vol + '">' +
      '<output id="splash-volume-value" class="-splash-volume-value">' + vol + "%</output>" +
      "</div>" +
      '<p class="-settings-hint -muted">' + tt("splash.settings.note", "默认静音；开启后下次冷启动会播放一次约 2.4s 的合成和声。会尊重系统的「减少动态效果」设置。") + "</p>" +
      "</section>"
    );
  }

  function syncSettingsControls() {
    var cb = DOC.getElementById("splash-sound");
    if (cb) cb.checked = !!state.prefs.sound;
    var range = DOC.getElementById("splash-volume");
    if (range) range.value = String(Math.round(state.prefs.volume * 100));
    var out = DOC.getElementById("splash-volume-value");
    if (out) out.textContent = Math.round(state.prefs.volume * 100) + "%";
  }

  function onSettingsChanged() {
    var cb = DOC.getElementById("splash-sound");
    var range = DOC.getElementById("splash-volume");
    if (cb) state.prefs.sound = !!cb.checked;
    if (range) {
      var pct = Number(range.value);
      if (isFinite(pct)) state.prefs.volume = Math.max(0, Math.min(100, pct)) / 100;
    }
    syncSettingsControls();
    writePrefsToDisk();
    // 打开开关 ⇒ 立刻试播一声（用户手势 = 自动播放策略允许的时刻，也是"开启后有声音"的即时反馈）
    if (state.prefs.sound && state.prefs.volume > 0) {
      playChime({ volume: state.prefs.volume });
    }
  }

  function installSettingsSection() {
    var mod = global.MemoriaDisplaySettings;
    if (!mod || typeof mod.renderSettingsBody !== "function" || state.settingsInstalled) return false;
    var orig = mod.renderSettingsBody;
    mod.renderSettingsBody = function () {
      var html = orig.apply(this, arguments);
      try {
        return html + settingsSectionHtml();
      } catch (e) {
        recordError("settings-html", e);
        return html;
      }
    };
    state.settingsInstalled = true;
    // 事件用文档级委托：设置体每次切页签都会整体重绘，委托不受影响
    DOC.addEventListener("change", function (ev) {
      var t = ev.target;
      if (t && (t.id === "splash-sound" || t.id === "splash-volume")) onSettingsChanged();
    });
    DOC.addEventListener("input", function (ev) {
      var t = ev.target;
      if (t && t.id === "splash-volume") onSettingsChanged();
    });
    // 设置面板打开时同步一次控件状态（读权威值）
    readPrefsFromDisk().then(function () { syncSettingsControls(); }).catch(function () { /* noop */ });
    return true;
  }

  function ensureSettings() {
    if (installSettingsSection()) return;
    var tries = 0;
    var timer = global.setInterval(function () {
      tries += 1;
      if (installSettingsSection() || tries > 300) global.clearInterval(timer);
    }, 100);
  }

  // ── 对外小 API（设置/测试/探针）─────────────────────────────────────────────
  var MemoriaSplash = {
    isShown: function () { return !!stats.shown; },
    getStats: function () { return stats; },
    getPrefs: function () { return mergePrefs(state.prefs); },
    setSoundEnabled: function (on) { state.prefs.sound = !!on; savePrefsFast(); writePrefsToDisk(); if (on) playChime({ volume: state.prefs.volume }); },
    setVolume: function (v) { state.prefs.volume = Math.max(0, Math.min(1, Number(v) || 0)); savePrefsFast(); writePrefsToDisk(); },
    playPreview: function () { return playChime({ volume: state.prefs.volume }); },
    fade: function (reason) { fadeOut(reason || "manual"); },
    _internals: {
      CAP_MS: CAP_MS,
      FADE_MS: FADE_MS,
      SAFETY_MS: SAFETY_MS,
      DEFAULT_PREFS: DEFAULT_PREFS,
      mergePrefs: mergePrefs,
      splashShow: splashShouldShow,
      splashFadeDelay: splashFadeDelay,
      settingsSectionHtml: settingsSectionHtml,
    },
  };
  global.MemoriaSplash = MemoriaSplash;

  // ── 启动 ────────────────────────────────────────────────────────────────────
  // 脚本在 <body> 早期、app.js 之前加载 ⇒ 蒙层先于应用首帧出现（应用窗口只在 load 后显示）。
  loadPrefsFast();
  start();
  ensureSettings();
})(typeof window !== "undefined" ? window : globalThis);
