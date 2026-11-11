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
  var stats = (global.__memoriaLoadingStats = {
    shown: 0,
    hidden: 0,
    maxConcurrent: 0,
    errors: [],
  });

  function recordError(where, err) {
    try {
      stats.errors.push(String(where) + ": " + String((err && err.message) || err));
      if (stats.errors.length > 20) stats.errors.shift();
    } catch (_) { /* noop */ }
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
      var card = DOC.createElement("div");
      card.className = "-memoria-loading__card";
      var spinner = DOC.createElement("span");
      spinner.className = "-memoria-loading__spinner";
      spinner.setAttribute("aria-hidden", "true");
      labelEl = DOC.createElement("span");
      labelEl.className = "-memoria-loading__label";
      detailEl = DOC.createElement("span");
      detailEl.className = "-memoria-loading__detail";
      card.appendChild(spinner);
      card.appendChild(labelEl);
      card.appendChild(detailEl);
      root.appendChild(card);
      (DOC.body || DOC.documentElement).appendChild(root);
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
    if (busy && labelEl) {
      var task = firstTask();
      labelEl.textContent = (task && task.label) || "";
      detailEl.textContent = (task && task.detail) || "";
      detailEl.hidden = !(task && task.detail);
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
    isBusy: function () { return tasks.size > 0; },
    count: function () { return tasks.size; },
    labels: function () { return Array.from(tasks.values()).map(function (t) { return t.label; }); },
    _internals: { tasks: tasks, stats: stats },
  };
})(typeof window !== "undefined" ? window : globalThis);
