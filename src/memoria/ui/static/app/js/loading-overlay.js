/**
 * 应用级加载蒙层（2026-11-11，人反馈：加载机制要模块化，窗口加载期间蒙版不能提前撤）。
 *
 * 设计约束：
 *   · 唯一遮挡层：`#memoria-loading`；所有加载任务通过 `begin()/end()` 引用计数，
 *     **只有引用计数归零才隐藏**，不设“到点自动撤”的计时器。
 *   · 可嵌套：boot / 新窗口 / 最小化恢复 / 未来的大块异步加载共用同一层；
 *     子任务结束后若仍有父任务，蒙层保持。
 *   · 失败可见：模块自身异常只记录到 `__memoriaLoadingStats.errors`，不阻塞应用；
 *     但任何调用方都必须 end 自己的 token（用 `track()` 可自动 finally）。
 *   · 样式只依赖主题 token（`--bg-primary/--text-primary/--theme-color`），
 *     不引入图片、字体或网络请求。
 *
 * 对外 API（window.MemoriaLoading）：
 *   begin(label?, detail?) -> token
 *   end(token)
 *   setLabel(token, label, detail?)
 *   track(promise, label?, detail?) -> promise
 *   isBusy() / count() / labels()
 */
(function (global) {
  "use strict";
  var DOC = global.document;
  if (!DOC) return;

  var tasks = new Map();
  var seq = 0;
  var root = null;
  var labelEl = null;
  var detailEl = null;
  var sky = null;
  var skyCtx = null;
  var skyRaf = 0;
  var skyStars = [];
  var skyMeteors = [];
  var skyNebulae = [];
  var skyW = 0;
  var skyH = 0;
  var skyLast = 0;
  var skyNextMeteor = 0;
  var skyResizeBound = false;
  var skyProfile = { files: 0, kps: 0, groups: 0, traces: 0 };
  /** 视觉名：星穹帷幕（Astral Veil）——程序生成的星场 + 随知识库积累变化的星云。 */
  var VISUAL_NAME = "星穹帷幕 / Astral Veil";
  var stats = (global.__memoriaLoadingStats = {
    shown: 0,
    hidden: 0,
    maxConcurrent: 0,
    visual: VISUAL_NAME,
    starfieldFrames: 0,
    profile: skyProfile,
    errors: [],
  });

  function recordError(where, err) {
    try {
      stats.errors.push(String(where) + ": " + String((err && err.message) || err));
      if (stats.errors.length > 20) stats.errors.shift();
    } catch (_) { /* noop */ }
  }

  function reducedMotion() {
    try {
      return !!(global.matchMedia && global.matchMedia("(prefers-reduced-motion: reduce)").matches);
    } catch (_) { return false; }
  }

  function themeStarColor(alpha) {
    var light = false;
    try { light = DOC.documentElement.getAttribute("data-theme") === "light"; } catch (_) { /* noop */ }
    return light
      ? "rgba(44, 62, 90, " + alpha.toFixed(3) + ")"
      : "rgba(232, 240, 255, " + alpha.toFixed(3) + ")";
  }

  // ── 知识库星云：文件越多、知识点越多、子图越多，星场越密、星云层数/色相越丰富 ──
  function readTraceCount() {
    try {
      var raw = global.localStorage && global.localStorage.getItem("memoria.splash.stars.v1");
      var obj = raw ? JSON.parse(raw) : null;
      return obj && Array.isArray(obj.stars) ? obj.stars.length : 0;
    } catch (_) { return 0; }
  }

  function normalizeProfile(p) {
    p = p || {};
    return {
      files: Math.max(0, Number(p.files) || 0),
      kps: Math.max(0, Number(p.kps) || 0),
      groups: Math.max(0, Number(p.groups) || 0),
      traces: Math.max(0, Number(p.traces) || readTraceCount()),
    };
  }

  function profileSeed() {
    return (skyProfile.files * 17 + skyProfile.kps * 31 + skyProfile.groups * 7 + skyProfile.traces * 3) >>> 0;
  }

  function lcg(seed) {
    var s = seed >>> 0;
    return function () {
      s = (s * 1664525 + 1013904223) >>> 0;
      return s / 4294967296;
    };
  }

  function seedNebulae() {
    if (!skyW || !skyH) { skyNebulae = []; return; }
    var rnd = lcg(profileSeed() || 1);
    var n = 2 + Math.min(5, Math.floor(skyProfile.groups / 2));
    var palette = [
      [88, 142, 255],
      [160, 108, 255],
      [68, 212, 198],
      [255, 172, 92],
      [255, 112, 184],
      [118, 206, 255],
    ];
    var richness = Math.min(1, skyProfile.files / 500 + skyProfile.kps / 1600);
    skyNebulae = [];
    for (var i = 0; i < n; i += 1) {
      var color = palette[(i + skyProfile.groups) % palette.length];
      skyNebulae.push({
        x: 0.12 + rnd() * 0.76,
        y: 0.15 + rnd() * 0.70,
        r: 0.22 + rnd() * 0.22 + richness * 0.08,
        color: color,
        alpha: 0.055 + richness * 0.045 + rnd() * 0.025,
        phase: rnd() * Math.PI * 2,
      });
    }
  }

  function drawNebulae(now) {
    if (!skyNebulae.length) return;
    skyCtx.save();
    skyCtx.globalCompositeOperation = "lighter";
    var light = false;
    try { light = DOC.documentElement.getAttribute("data-theme") === "light"; } catch (_) { /* noop */ }
    for (var i = 0; i < skyNebulae.length; i += 1) {
      var n = skyNebulae[i];
      var pulse = 0.82 + 0.18 * Math.sin(now * 0.00035 + n.phase);
      var a = n.alpha * pulse * (light ? 0.62 : 1);
      var r = Math.max(120, Math.min(skyW, skyH) * n.r);
      var g = skyCtx.createRadialGradient(n.x * skyW, n.y * skyH, 0, n.x * skyW, n.y * skyH, r);
      g.addColorStop(0, "rgba(" + n.color[0] + "," + n.color[1] + "," + n.color[2] + "," + a.toFixed(3) + ")");
      g.addColorStop(0.45, "rgba(" + n.color[0] + "," + n.color[1] + "," + n.color[2] + "," + (a * 0.42).toFixed(3) + ")");
      g.addColorStop(1, "rgba(" + n.color[0] + "," + n.color[1] + "," + n.color[2] + ",0)");
      skyCtx.fillStyle = g;
      skyCtx.beginPath();
      skyCtx.arc(n.x * skyW, n.y * skyH, r, 0, Math.PI * 2);
      skyCtx.fill();
    }
    skyCtx.restore();
  }

  function profileDetailText() {
    var t = global.MemoriaI18n && global.MemoriaI18n.t;
    function tr(key, fallback, params) {
      try {
        var v = t ? t(key, params) : "";
        return v && v !== key ? v : fallback;
      } catch (_e) { return fallback; }
    }
    var bits = [];
    if (skyProfile.files) bits.push(tr("app.loadingStage.files", skyProfile.files + " files", { n: skyProfile.files }));
    if (skyProfile.kps) bits.push(tr("app.loadingStage.knowledgePoints", skyProfile.kps + " knowledge points", { n: skyProfile.kps }));
    if (skyProfile.groups) bits.push(tr("app.loadingStage.subgraphs", skyProfile.groups + " subgraphs", { n: skyProfile.groups }));
    return bits.join(" · ");
  }

  function setKnowledgeProfile(profile) {
    skyProfile = normalizeProfile(profile);
    stats.profile = skyProfile;
    if (detailEl) {
      detailEl.textContent = profileDetailText();
      detailEl.hidden = !detailEl.textContent;
    }
    if (sky) {
      seedStars();
      if (!root.hidden) startSky();
    }
  }

  function skySize() {
    if (!sky || !skyCtx || !root) return false;
    var rect = root.getBoundingClientRect();
    var dpr = Math.min(2, Math.max(1, global.devicePixelRatio || 1));
    var w = Math.max(1, Math.round(rect.width));
    var h = Math.max(1, Math.round(rect.height));
    if (w === skyW && h === skyH && sky.width === Math.round(w * dpr)) return false;
    skyW = w;
    skyH = h;
    sky.width = Math.round(w * dpr);
    sky.height = Math.round(h * dpr);
    sky.style.width = w + "px";
    sky.style.height = h + "px";
    skyCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return true;
  }

  function seedStars() {
    var base = Math.round((skyW * skyH) / 12000);
    var density = 1
      + Math.min(1.4, skyProfile.kps / 900)
      + Math.min(0.6, skyProfile.files / 600)
      + Math.min(0.35, skyProfile.traces / 240);
    var count = Math.max(90, Math.min(420, Math.round(base * density)));
    skyStars = [];
    for (var i = 0; i < count; i += 1) {
      var depth = 0.35 + Math.random() * 0.65;
      skyStars.push({
        x: Math.random() * skyW,
        y: Math.random() * skyH,
        depth: depth,
        r: 0.35 + Math.random() * 1.05 * depth,
        phase: Math.random() * Math.PI * 2,
        speed: 0.35 + Math.random() * 0.9,
        drift: 2 + Math.random() * 8,
      });
    }
    seedNebulae();
    skyNextMeteor = performance.now() + 1800 + Math.random() * 2600;
  }

  function drawSky(now) {
    if (!skyCtx || !skyW || !skyH) return;
    var dt = Math.min(0.05, Math.max(0.001, (now - skyLast) / 1000));
    skyLast = now;
    skyCtx.clearRect(0, 0, skyW, skyH);
    // 星云先铺底：文件/知识点/子图越多，色相层数与亮度越高。
    drawNebulae(now);
    // 星点：深度视差 + 呼吸式明暗；不是固定 CSS 关键帧。
    for (var i = 0; i < skyStars.length; i += 1) {
      var s = skyStars[i];
      s.x -= s.drift * s.depth * dt;
      if (s.x < -4) s.x = skyW + 4;
      s.phase += dt * s.speed;
      var twinkle = 0.48 + 0.52 * (0.5 + 0.5 * Math.sin(s.phase));
      var alpha = Math.min(0.95, (0.22 + 0.72 * s.depth) * twinkle);
      skyCtx.beginPath();
      skyCtx.fillStyle = themeStarColor(alpha);
      skyCtx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      skyCtx.fill();
      if (s.depth > 0.82) {
        skyCtx.globalAlpha = alpha * 0.22;
        skyCtx.beginPath();
        skyCtx.arc(s.x, s.y, s.r * 3.2, 0, Math.PI * 2);
        skyCtx.fill();
        skyCtx.globalAlpha = 1;
      }
    }
    // 偶发流星：程序生成，生命周期短，避免"预制动画"的呆板感。
    if (now > skyNextMeteor) {
      skyMeteors.push({
        x: skyW * (0.35 + Math.random() * 0.7),
        y: -10,
        vx: -160 - Math.random() * 160,
        vy: 220 + Math.random() * 180,
        life: 1,
        len: 80 + Math.random() * 90,
      });
      skyNextMeteor = now + 5000 + Math.random() * 7000;
    }
    for (var m = skyMeteors.length - 1; m >= 0; m -= 1) {
      var meteor = skyMeteors[m];
      meteor.x += meteor.vx * dt;
      meteor.y += meteor.vy * dt;
      meteor.life -= dt * 0.9;
      if (meteor.life <= 0 || meteor.y > skyH + 120) {
        skyMeteors.splice(m, 1);
        continue;
      }
      var tailX = meteor.x - meteor.vx * 0.25;
      var tailY = meteor.y - meteor.vy * 0.25;
      var grad = skyCtx.createLinearGradient(meteor.x, meteor.y, tailX, tailY);
      grad.addColorStop(0, themeStarColor(0.85 * meteor.life));
      grad.addColorStop(1, themeStarColor(0));
      skyCtx.strokeStyle = grad;
      skyCtx.lineWidth = 1.2;
      skyCtx.beginPath();
      skyCtx.moveTo(meteor.x, meteor.y);
      skyCtx.lineTo(tailX, tailY);
      skyCtx.stroke();
    }
    stats.starfieldFrames += 1;
  }

  function skyLoop(now) {
    if (!sky || root.hidden) {
      skyRaf = 0;
      return;
    }
    drawSky(now);
    skyRaf = global.requestAnimationFrame(skyLoop);
  }

  function startSky() {
    if (!sky) return;
    if (skyRaf) return;
    var resized = skySize();
    if (resized || !skyStars.length) seedStars();
    skyLast = performance.now();
    if (reducedMotion()) {
      drawSky(skyLast);
      return;
    }
    skyRaf = global.requestAnimationFrame(skyLoop);
  }

  function stopSky() {
    if (skyRaf) {
      global.cancelAnimationFrame(skyRaf);
      skyRaf = 0;
    }
  }

  function ensure() {
    if (root) return root;
    try {
      root = DOC.createElement("div");
      root.id = "memoria-loading";
      root.className = "-memoria-loading";
      root.hidden = true;
      root.setAttribute("role", "status");
      root.setAttribute("aria-live", "polite");
      root.setAttribute("aria-atomic", "true");
      sky = DOC.createElement("canvas");
      sky.className = "-memoria-loading__sky";
      sky.setAttribute("aria-hidden", "true");
      skyCtx = sky.getContext("2d");
      root.appendChild(sky);
      var stage = DOC.createElement("div");
      stage.className = "-memoria-loading__stage";
      var logo = DOC.createElement("img");
      logo.className = "-memoria-loading__logo";
      logo.src = "/icons/Memoria.png";
      logo.alt = "";
      logo.decoding = "async";
      logo.draggable = false;
      logo.setAttribute("aria-hidden", "true");
      var word = DOC.createElement("div");
      word.className = "-memoria-loading__word";
      word.textContent = "Memoria";
      labelEl = DOC.createElement("span");
      labelEl.className = "-memoria-loading__label";
      detailEl = DOC.createElement("span");
      detailEl.className = "-memoria-loading__detail";
      stage.appendChild(logo);
      stage.appendChild(word);
      stage.appendChild(labelEl);
      stage.appendChild(detailEl);
      root.appendChild(stage);
      (DOC.body || DOC.documentElement).appendChild(root);
      if (!skyResizeBound) {
        skyResizeBound = true;
        global.addEventListener("resize", function () {
          if (!root.hidden && skySize()) seedStars();
        });
      }
    } catch (err) {
      recordError("ensure", err);
      root = null;
    }
    return root;
  }

  function firstTask() {
    var it = tasks.values().next();
    return it && !it.done ? it.value : null;
  }

  function render() {
    var busy = tasks.size > 0;
    if (root) {
      root.hidden = !busy;
      root.setAttribute("aria-busy", busy ? "true" : "false");
    }
    try {
      DOC.documentElement.classList.toggle("-app-loading", busy);
    } catch (_) { /* noop */ }
    if (busy) startSky();
    else stopSky();
    if (busy && labelEl) {
      var task = firstTask();
      labelEl.textContent = (task && task.label) || "";
      var detail = (task && task.detail) || profileDetailText();
      detailEl.textContent = detail;
      detailEl.hidden = !detail;
    }
    if (busy) stats.shown += 1;
    else if (root) stats.hidden += 1;
  }

  function begin(label, detail) {
    ensure();
    var token = "ld" + (++seq);
    tasks.set(token, { label: String(label || ""), detail: String(detail || "") });
    if (tasks.size > stats.maxConcurrent) stats.maxConcurrent = tasks.size;
    render();
    return token;
  }

  function end(token) {
    if (!token) return false;
    var had = tasks.delete(token);
    if (had) render();
    return had;
  }

  function setLabel(token, label, detail) {
    var task = tasks.get(token);
    if (!task) return false;
    task.label = String(label || "");
    if (detail !== undefined) task.detail = String(detail || "");
    render();
    return true;
  }

  function track(promise, label, detail) {
    var token = begin(label, detail);
    try {
      return Promise.resolve(promise).finally(function () { end(token); });
    } catch (err) {
      end(token);
      return Promise.reject(err);
    }
  }

  global.MemoriaLoading = {
    begin: begin,
    end: end,
    setLabel: setLabel,
    track: track,
    visualName: VISUAL_NAME,
    setKnowledgeProfile: setKnowledgeProfile,
    isBusy: function () { return tasks.size > 0; },
    count: function () { return tasks.size; },
    labels: function () { return Array.from(tasks.values()).map(function (t) { return t.label; }); },
    _internals: { tasks: tasks, stats: stats, stars: function () { return skyStars; } },
  };
})(typeof window !== "undefined" ? window : globalThis);
