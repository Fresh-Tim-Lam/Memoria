/**
 * Memoria 前端作业调度内核（M5，见 docs/design/maintenance-jobs.md §3）。
 *
 * 目标：把“保存后的派生维护”以 OS 任务视角统一排队执行——
 *  - 去重合并：同 kind+key 的待执行作业被新参数顶替（replace）或忽略；
 *  - 优先级：P0 一致性 > P1 交互 > P2 派生视图 > P3 后台重活（数字小者优先）；
 *  - 帧预算（M5.1）：每帧默认 12ms，P0/P1 可用满预算（借用 P2 份额），
 *    P2/P3 在高优先级排队时只拿到扣除保留额后的预算；预算用尽必须让出一帧；
 *  - 长任务切片：`maxSliceMs` + `ctx.shouldYield()/ctx.yield()` 协作切片；
 *    async generator 形式的 run/steps 由内核自动按切片预算推进；
 *  - 陈旧丢弃：携带 gen 的作业若在入队后被 bumpEpoch 越过则丢弃；
 *  - flush：同步点（文件切换/关库）前等待关键作业完成；
 *  - 可观测：[job] 前缀日志 + status/queue 查询 + 预算/帧/切片计数。
 *
 * 用法（旧调用方无需改动）：
 *   window.MemoriaScheduler.schedule({
 *     kind: 'kp_panel', key: state.currentPath,          // 去重键
 *     priority: 2,                                        // 0..N，越小越优先
 *     run: async (ctx) => { ... },                        // 必须幂等、可重入
 *     replace: true,                                      // 同键新作业是否顶替旧作业
 *     gen: window.MemoriaScheduler.epoch(),               // 可选陈旧标记
 *     dropStale: true,                                    // 执行前 gen<epoch 则丢弃
 *   });
 *
 * 长任务（可选，向后兼容）：
 *   // 1) 协作切片：声明 maxSliceMs，在循环里让出
 *   run: async (ctx) => {
 *     for (const item of items) {
 *       doOne(item);
 *       if (ctx.shouldYield()) await ctx.yield();   // 本帧让出，rAF 续跑
 *     }
 *   }
 *   // 2) 自动切片：async generator，每次 yield 是一个切片单元
 *   run: async function* (ctx) { for (const x of xs) { doOne(x); yield; } }
 *   // 3) 自动切片：steps 数组，每个函数是一个切片单元
 *   steps: [() => part1(), () => part2(), ...]
 */
(function (g) {
  "use strict";

  var QUEUE = [];
  var SUSPENDED = [];
  var _running = false;
  var _frameScheduled = false;
  var _frameHandle = null;
  var _seq = 0;
  var _epoch = 0;
  var _flushWaiters = [];
  var _estimates = Object.create(null);
  var _counters = {
    scheduled: 0,
    executed: 0,
    merged: 0,
    dropped: 0,
    queue_max: 0,
    budget_exceeded: 0,
    frames_used: 0,
    slice_count: 0,
    max_frame_ms: 0,
  };

  // ── 帧预算参数（可经 configure 调整） ──────────────────────────────────────
  var _config = {
    frameBudgetMs: 12,      // 每帧默认可用的作业预算
    criticalReserveMs: 4,   // P0/P1 专用保留额；P2/P3 在关键作业排队时不得占用
    maxSlices: 1000,        // 单作业切片上限（防止调用方永远 yield 导致活锁）
    maxUnitsPerFrame: 1000, // 单帧作业单元上限（防止零耗时 generator 单元饿死渲染）
  };

  function now() {
    try {
      if (g.performance && typeof g.performance.now === "function") return g.performance.now();
    } catch (_) {
      /* noop */
    }
    return Date.now();
  }

  function deferred() {
    var resolve;
    var promise = new Promise(function (res) {
      resolve = res;
    });
    return { promise: promise, resolve: resolve };
  }

  function trackQueue() {
    var n = QUEUE.length + SUSPENDED.length;
    if (n > _counters.queue_max) _counters.queue_max = n;
  }

  function isBypass() {
    return !!(g.__BENCH_DISABLE_SCHEDULER);
  }

  function tag(j) {
    return j.kind + (j.key ? ":" + j.key : "");
  }

  // ── 真机验收追踪（G5.1）：window.__jobTrace=true 开启；200ms 批量写 logs/job-trace.log ──
  var _traceBuf = [];
  var _traceTimer = null;
  var _traceSeq = 0;

  function _pad(n, w) {
    var s = String(n);
    while (s.length < w) s = "0" + s;
    return s;
  }

  function traceFlush() {
    if (_traceTimer) {
      clearTimeout(_traceTimer);
      _traceTimer = null;
    }
    if (!_traceBuf.length) return;
    var body = _traceBuf.join("\n") + "\n";
    _traceBuf = [];
    try {
      var api =
        (g.MemoriaBridge && g.MemoriaBridge.api && g.MemoriaBridge.api()) ||
        (g.memoria && g.memoria.api);
      if (api && api.write_debug_log) api.write_debug_log("job-trace.log", body);
    } catch (_) {
      /* noop */
    }
  }

  function trace(msg) {
    if (!g.__jobTrace) return;
    var d = new Date();
    var ts =
      _pad(d.getHours(), 2) + ":" + _pad(d.getMinutes(), 2) + ":" +
      _pad(d.getSeconds(), 2) + "." + _pad(d.getMilliseconds(), 3);
    _traceBuf.push(ts + " #" + ++_traceSeq + " " + msg);
    if (_traceTimer) clearTimeout(_traceTimer);
    _traceTimer = setTimeout(traceFlush, 200);
  }

  function log(msg) {
    try {
      if (g.console) g.console.log("[job] " + msg);
    } catch (_) {
      /* noop */
    }
    trace(msg);
  }

  /** 供作业实现方补记观测（如“忙时跳过”），统一带 [job] 前缀与追踪落盘。 */
  function note(msg) {
    log(msg);
  }

  if (g && typeof g.addEventListener === "function") {
    g.addEventListener("beforeunload", traceFlush);
  }

  function idle(fn) {
    if (typeof g.requestIdleCallback === "function") {
      return g.requestIdleCallback(fn, { timeout: 800 });
    }
    return setTimeout(fn, 0);
  }
  function cancelIdle(handle) {
    if (handle == null) return;
    if (typeof g.cancelIdleCallback === "function") g.cancelIdleCallback(handle);
    else clearTimeout(handle);
  }

  /** 帧续跑：优先 requestAnimationFrame（切片与渲染对齐），否则 idle/setTimeout 兜底。
   *  另挂 50ms 定时兜底：后台标签页 rAF 会被节流/暂停，纯 rAF 会让 P3 永久饿死。 */
  function requestFrame(fn) {
    if (typeof g.requestAnimationFrame === "function") {
      var fired = false;
      var timer = setTimeout(function () {
        if (fired) return;
        fired = true;
        fn(now());
      }, 50);
      return g.requestAnimationFrame(function () {
        if (fired) return;
        fired = true;
        clearTimeout(timer);
        fn(now());
      });
    }
    if (typeof g.requestIdleCallback === "function") {
      return g.requestIdleCallback(function () { fn(now()); }, { timeout: 100 });
    }
    return setTimeout(function () { fn(now()); }, 0);
  }

  function epoch() {
    return _epoch;
  }
  function bumpEpoch() {
    _epoch += 1;
    return _epoch;
  }

  function configure(opts) {
    if (opts && typeof opts === "object") {
      if (Number.isFinite(opts.frameBudgetMs) && opts.frameBudgetMs > 0) {
        _config.frameBudgetMs = opts.frameBudgetMs;
        if (_config.criticalReserveMs > _config.frameBudgetMs) {
          _config.criticalReserveMs = _config.frameBudgetMs;
        }
      }
      if (Number.isFinite(opts.criticalReserveMs) && opts.criticalReserveMs >= 0) {
        _config.criticalReserveMs = Math.min(opts.criticalReserveMs, _config.frameBudgetMs);
      }
      if (Number.isFinite(opts.maxSlices) && opts.maxSlices >= 1) {
        _config.maxSlices = Math.floor(opts.maxSlices);
      }
      if (Number.isFinite(opts.maxUnitsPerFrame) && opts.maxUnitsPerFrame >= 1) {
        _config.maxUnitsPerFrame = Math.floor(opts.maxUnitsPerFrame);
      }
    }
    return {
      frameBudgetMs: _config.frameBudgetMs,
      criticalReserveMs: _config.criticalReserveMs,
      maxSlices: _config.maxSlices,
      maxUnitsPerFrame: _config.maxUnitsPerFrame,
    };
  }

  function _isAsyncGenerator(fn) {
    return Object.prototype.toString.call(fn) === "[object AsyncGeneratorFunction]";
  }

  /** 入队；同 kind+key 待执行作业按 replace 语义合并。 */
  function schedule(spec) {
    spec = spec || {};
    var steps = Array.isArray(spec.steps)
      ? spec.steps.filter(function (s) { return typeof s === "function"; })
      : null;
    var run = typeof spec.run === "function" ? spec.run : null;
    var j = {
      id: ++_seq,
      kind: String(spec.kind || "job"),
      key: spec.key != null ? String(spec.key) : "",
      priority: Number.isFinite(spec.priority) ? spec.priority : 3,
      run: run,
      steps: steps && steps.length ? steps : null,
      mode: run ? (_isAsyncGenerator(run) ? "generator" : "promise") : "steps",
      gen: spec.gen !== undefined ? spec.gen : _epoch,
      dropStale: !!spec.dropStale,
      replace: spec.replace !== false, // 默认 true：同键新作业顶替旧作业
      maxSliceMs: Number.isFinite(spec.maxSliceMs) && spec.maxSliceMs > 0 ? spec.maxSliceMs : 0,
      estimateMs: Number.isFinite(spec.estimateMs) ? spec.estimateMs : null,
      created: Date.now(),
      status: "queued",
      slices: 0,
      _stepIndex: 0,
      _started: false,
      _finished: false,
      _unitMs: null,
      _frame: null,
      _sliceStart: 0,
    };
    if (!j.run && !j.steps) {
      log("schedule 忽略（无 run/steps）: " + tag(j));
      return null;
    }
    // 基准旁路（__BENCH_DISABLE_SCHEDULER=1）：退化回“立即同步执行”，用于 A/B 对照“没有调度”的路径
    if (isBypass()) {
      _counters.scheduled += 1;
      _counters.executed += 1;
      log("旁路执行 " + tag(j) + " #" + j.id);
      try {
        var ctx = { kind: j.kind, key: j.key, id: j.id };
        var pr = j.steps ? _runStepsBypass(j, ctx) : j.run(ctx);
        if (pr && typeof pr.then === "function") pr.catch(function () { /* noop */ });
      } catch (err) {
        log("旁路失败 " + tag(j) + ": " + (err && err.message ? err.message : err));
      }
      return j.id;
    }
    var dk = tag(j);
    // 合并语义：replace=true → 顶替同键 queued 旧作业；replace=false → 同键已在队则忽略新作业
    if (j.replace) {
      for (var i = QUEUE.length - 1; i >= 0; i--) {
        if (QUEUE[i].status === "queued" && tag(QUEUE[i]) === dk) {
          QUEUE[i].status = "dropped";
          QUEUE.splice(i, 1);
          _counters.merged += 1;
          log("合并(顶替) " + dk);
        }
      }
    } else {
      var exists = QUEUE.some(function (q) {
        return q.status === "queued" && tag(q) === dk;
      });
      if (exists) {
        _counters.merged += 1;
        log("合并(忽略新) " + dk + " #" + j.id);
        return QUEUE.filter(function (q) {
          return q.status === "queued" && tag(q) === dk;
        })[0].id;
      }
    }
    QUEUE.push(j);
    _counters.scheduled += 1;
    trackQueue();
    log("入队 " + dk + " #" + j.id + " prio=" + j.priority + " queue=" + (QUEUE.length + SUSPENDED.length));
    pump();
    return j.id;
  }

  async function _runStepsBypass(j, ctx) {
    for (var i = 0; i < j.steps.length; i++) {
      await j.steps[i](ctx);
    }
  }

  function _allPending() {
    return QUEUE.concat(SUSPENDED);
  }

  function _pick() {
    // 按优先级升序（小=高优先），同优先级按入队序；挂起作业一并参与，保证 P0/P1 不被 P2 饿死。
    var all = _allPending();
    if (!all.length) return null;
    all.sort(function (a, b) {
      return a.priority - b.priority || a.id - b.id;
    });
    return all[0];
  }

  function _take(j) {
    var i = QUEUE.indexOf(j);
    if (i >= 0) {
      QUEUE.splice(i, 1);
      return;
    }
    i = SUSPENDED.indexOf(j);
    if (i >= 0) SUSPENDED.splice(i, 1);
  }

  function _hold(j, status) {
    j.status = status;
    if (SUSPENDED.indexOf(j) < 0) SUSPENDED.push(j);
    trackQueue();
  }

  function _hasWork() {
    return QUEUE.length > 0 || SUSPENDED.length > 0;
  }

  function _hasCriticalPending() {
    return _allPending().some(function (j) { return j.priority <= 1; });
  }

  function _higherPriorityQueued(priority) {
    return _allPending().some(function (j) { return j.priority < priority; });
  }

  function _frameLimit(j) {
    var b = _config.frameBudgetMs;
    if (j.priority <= 1) return b; // P0/P1 可借用整帧（含 P2/P3 份额）
    return _hasCriticalPending()
      ? Math.max(1, b - _config.criticalReserveMs)
      : b;
  }

  function _estimate(j) {
    if (j.estimateMs != null) return j.estimateMs;
    var e = _estimates[j.kind];
    return e == null ? 1 : e;
  }

  function _learn(j, elapsed) {
    if (!(elapsed > 0)) return;
    var old = _estimates[j.kind];
    _estimates[j.kind] = old == null ? elapsed : old * 0.7 + elapsed * 0.3;
  }

  function _ensureCtx(j) {
    if (j._ctx) return j._ctx;
    j._ctx = {
      kind: j.kind,
      key: j.key,
      id: j.id,
      priority: j.priority,
      maxSliceMs: j.maxSliceMs,
      now: now,
      frameUsedMs: function () {
        if (!j._frame) return 0;
        return now() - j._frame.start;
      },
      shouldYield: function () {
        return _shouldYield(j);
      },
      yield: function () {
        return _requestYield(j);
      },
    };
    return j._ctx;
  }

  function _requestYield(j) {
    if (j._finished) return Promise.resolve();
    if (!j._wait) {
      j._wait = deferred();
      if (j._yieldSignal) j._yieldSignal.resolve();
    }
    return j._wait.promise;
  }

  function _shouldYield(j) {
    if (!j._frame) return false;
    if (j._frame.units >= _config.maxUnitsPerFrame) return true;
    if (j.maxSliceMs > 0 && now() - j._sliceStart >= j.maxSliceMs) return true;
    if (now() - j._frame.start >= _frameLimit(j)) return true;
    return _higherPriorityQueued(j.priority);
  }

  function _raceYield(promise, j) {
    if (!j._yieldSignal) return promise;
    return Promise.race([
      promise,
      j._yieldSignal.promise.then(function () { return { type: "yielded" }; }),
    ]);
  }

  /** 执行一个切片单元；返回 endframe | continue。 */
  async function _runUnit(j, frame) {
    var t0 = now();
    var isNew = !j._started;
    j._frame = frame;
    // 切片时钟只在“新作业/跨帧恢复”时重置；同一帧内 generator/steps 的连续单元共享切片预算
    if (isNew || j.status === "yielded") j._sliceStart = t0;
    j._yieldSignal = deferred();
    if (j._wait) {
      // 恢复上一帧 ctx.yield() 挂起的同一个 run 调用（不是重跑）
      var wait = j._wait;
      j._wait = null;
      wait.resolve();
    }
    var ctx = _ensureCtx(j);
    if (isNew) {
      j._started = true;
      j.status = "running";
      _counters.executed += 1;
      log("执行 " + tag(j) + " #" + j.id + " prio=" + j.priority);
    } else {
      j.status = "running";
    }

    var outcome;
    try {
      if (j.mode === "generator") {
        outcome = await _generatorUnit(j, ctx);
      } else if (j.mode === "steps") {
        outcome = await _stepUnit(j, ctx);
      } else {
        outcome = await _promiseUnit(j, ctx);
      }
    } catch (err) {
      _finish(j, "error");
      log("失败 " + tag(j) + ": " + (err && err.message ? err.message : err));
      return "continue";
    }

    var wall = Math.max(0, now() - t0);
    // 帧预算只计“同步执行”时间：初始调用/next()/step 的同步前缀；
    // promise 作业跨帧恢复时无法再切分同步前缀，退化为本切片的墙钟（不含初始 await）。
    var elapsed = j._unitMs != null ? j._unitMs : wall;
    j._unitMs = null;
    frame.used += elapsed;
    frame.jobs += 1;
    frame.units += 1;
    _learn(j, elapsed);
    if (!frame.over && frame.used > _config.frameBudgetMs) {
      frame.over = true;
    }

    if (outcome.type === "error") {
      _finish(j, "error");
      log("失败 " + tag(j) + ": " + (outcome.error && outcome.error.message ? outcome.error.message : outcome.error));
      return "continue";
    }
    if (outcome.type === "done") {
      _finish(j, "done");
      log("完成 " + tag(j) + " #" + j.id);
      return "continue";
    }
    if (outcome.type === "yielded") {
      if (j._wait) {
        // 调用方已经 await ctx.yield()，本切片到此为止，下一帧续跑
        j.slices += 1;
        _counters.slice_count += 1;
        if (j.slices > _config.maxSlices) {
          _finish(j, "error");
          log("切片超限中止 " + tag(j) + " #" + j.id + " slices=" + j.slices);
          return "endframe";
        }
        _hold(j, "yielded");
        log("切片让出 " + tag(j) + " #" + j.id + " slice=" + j.slices + " used=" + Math.round(frame.used));
        return "endframe";
      }
      // 自动切片：generator/step 单元结束，按预算决定本帧是否继续
      if (_shouldYield(j)) {
        j.slices += 1;
        _counters.slice_count += 1;
        if (j.slices > _config.maxSlices) {
          _finish(j, "error");
          log("切片超限中止 " + tag(j) + " #" + j.id);
          return "endframe";
        }
        _hold(j, "yielded");
        return "endframe";
      }
      _hold(j, "running");
      return "continue";
    }
    // continue：generator/steps 仍有后续单元；若预算已尽则留到下一帧
    if (_shouldYield(j)) {
      j.slices += 1;
      _counters.slice_count += 1;
      if (j.slices > _config.maxSlices) {
        _finish(j, "error");
        log("切片超限中止 " + tag(j) + " #" + j.id);
        return "endframe";
      }
      _hold(j, "yielded");
      return "endframe";
    }
    _hold(j, "running");
    return "continue";
  }

  async function _promiseUnit(j, ctx) {
    if (!j._runPromise) {
      // 同步调用 run：async 函数会同步执行到第一个 await；只把这部分算作帧占用，
      // 之后的 RPC/定时器等待不消耗帧预算（否则一次 50ms RPC 会被误判为长任务）。
      var s0 = now();
      var p = j.run(ctx);
      j._unitMs = Math.max(0, now() - s0);
      j._runPromise = Promise.resolve(p);
    }
    var done = j._runPromise.then(
      function (v) { return { type: "done", value: v }; },
      function (e) { return { type: "error", error: e }; }
    );
    return _raceYield(done, j);
  }

  async function _generatorUnit(j, ctx) {
    if (!j._gen) j._gen = j.run(ctx);
    // 若 generator 内部 await ctx.yield()，恢复时必须复用同一个 next() Promise，
    // 不能对运行中的 async generator 再次 next()（会抛 "Generator is already running"）。
    if (j._genNextP) {
      j._unitMs = null;
    } else {
      var s0 = now();
      j._genNextP = j._gen.next();
      j._unitMs = Math.max(0, now() - s0);
    }
    var step = Promise.resolve(j._genNextP).then(
      function (r) {
        j._genNextP = null;
        return r.done ? { type: "done", value: r.value } : { type: "unit" };
      },
      function (e) {
        j._genNextP = null;
        return { type: "error", error: e };
      }
    );
    var out = await _raceYield(step, j);
    if (out.type === "error" || out.type === "done" || out.type === "yielded") return out;
    return { type: "continue" };
  }

  async function _stepUnit(j, ctx) {
    if (!j._stepP && j._stepIndex >= j.steps.length) return { type: "done" };
    if (j._stepP) {
      // 同 generator：step 内部 await ctx.yield() 时复用未完成的 step Promise
      j._unitMs = null;
    } else {
      var fn = j.steps[j._stepIndex];
      j._stepIndex += 1;
      var s0 = now();
      j._stepP = Promise.resolve(fn(ctx));
      j._unitMs = Math.max(0, now() - s0);
    }
    var step = Promise.resolve(j._stepP).then(
      function () {
        j._stepP = null;
        return { type: "unit" };
      },
      function (e) {
        j._stepP = null;
        return { type: "error", error: e };
      }
    );
    var out = await _raceYield(step, j);
    if (out.type === "error" || out.type === "yielded") return out;
    if (!j._stepP && j._stepIndex >= j.steps.length) return { type: "done" };
    return { type: "continue" };
  }

  function _finish(j, status) {
    if (j._finished) return;
    j._finished = true;
    j.status = status;
    if (j._wait) {
      j._wait.resolve();
      j._wait = null;
    }
    j._yieldSignal = null;
  }

  function _resolveFlush() {
    if (_hasWork() || _running || _frameScheduled) return;
    var ws = _flushWaiters;
    _flushWaiters = [];
    for (var i = 0; i < ws.length; i++) ws[i]();
  }

  function pump() {
    if (_running || _frameScheduled || !_hasWork()) return;
    _frameScheduled = true;
    _frameHandle = requestFrame(runFrame);
  }

  async function runFrame() {
    _frameScheduled = false;
    _frameHandle = null;
    if (!_hasWork()) {
      _running = false;
      _resolveFlush();
      return;
    }
    _running = true;
    var frame = { start: now(), used: 0, jobs: 0, units: 0, over: false };
    try {
      while (_hasWork()) {
        var j = _pick();
        if (!j) break;
        var limit = _frameLimit(j);
        if (frame.jobs > 0) {
          if (frame.units >= _config.maxUnitsPerFrame) break;
          // 启动前保守判断：剩余预算不足“预估耗时”就不塞进这一帧
          if (frame.used >= limit) {
            if (!frame.over && frame.used > _config.frameBudgetMs) frame.over = true;
            break;
          }
          if (frame.used + _estimate(j) > limit) break;
        }
        _take(j);
        // 陈旧丢弃只针对尚未启动的作业；已开始切片的作业不中途丢弃，避免半完成副作用
        if (j.dropStale && !j._started && j.gen < _epoch) {
          _finish(j, "dropped");
          _counters.dropped += 1;
          log("陈旧丢弃 " + tag(j) + " (gen " + j.gen + " < " + _epoch + ")");
          continue;
        }
        var res = await _runUnit(j, frame);
        if (res === "endframe") break;
        if (frame.jobs > 0) {
          limit = _frameLimit(j);
          if (frame.used >= limit && _hasWork()) break;
        }
      }
    } catch (err) {
      log("帧循环异常: " + (err && err.message ? err.message : err));
    } finally {
      if (frame.jobs > 0) {
        _counters.frames_used += 1;
        if (frame.used > _counters.max_frame_ms) _counters.max_frame_ms = frame.used;
        if (!frame.over && frame.used > _config.frameBudgetMs) frame.over = true;
        if (frame.over) {
          _counters.budget_exceeded += 1;
          log("帧预算耗尽 used=" + Math.round(frame.used) + "ms budget=" + _config.frameBudgetMs + "ms");
        }
      }
      _running = false;
      if (_hasWork()) {
        _frameScheduled = true;
        _frameHandle = requestFrame(runFrame);
      } else {
        _resolveFlush();
      }
    }
  }

  /** 同步点：等待当前及已入队作业执行完（关键路径使用）。预算内可能跨多帧完成。 */
  function flush() {
    if (!_hasWork() && !_running && !_frameScheduled) return Promise.resolve();
    var p = new Promise(function (res) { _flushWaiters.push(res); });
    if (!_running && !_frameScheduled) {
      // 显式同步点：首帧立即在微任务执行（保留旧版 flush 的低延迟），超额部分再走 rAF
      _frameScheduled = true;
      Promise.resolve().then(runFrame);
    } else {
      pump();
    }
    return p;
  }

  function status() {
    return {
      queued: QUEUE.filter(function (j) { return j.status === "queued"; }).length + SUSPENDED.length,
      running: _running,
      epoch: _epoch,
    };
  }
  function counters() {
    return {
      scheduled: _counters.scheduled,
      executed: _counters.executed,
      merged: _counters.merged,
      dropped: _counters.dropped,
      queue_max: _counters.queue_max,
      budget_exceeded: _counters.budget_exceeded,
      frames_used: _counters.frames_used,
      slice_count: _counters.slice_count,
      max_frame_ms: _counters.max_frame_ms,
    };
  }
  function resetCounters() {
    _counters = {
      scheduled: 0,
      executed: 0,
      merged: 0,
      dropped: 0,
      queue_max: 0,
      budget_exceeded: 0,
      frames_used: 0,
      slice_count: 0,
      max_frame_ms: 0,
    };
  }

  g.MemoriaScheduler = {
    schedule: schedule,
    flush: flush,
    epoch: epoch,
    bumpEpoch: bumpEpoch,
    status: status,
    counters: counters,
    resetCounters: resetCounters,
    configure: configure,
    isBypass: isBypass,
    note: note,
    traceFlush: traceFlush,
  };
})(typeof window !== "undefined" ? window : globalThis);
