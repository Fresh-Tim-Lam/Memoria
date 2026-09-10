/**
 * Memoria 前端作业调度内核（M5，见 docs/design/maintenance-jobs.md §3）。
 *
 * 目标：把“保存后的派生维护”以 OS 任务视角统一排队执行——
 *  - 去重合并：同 kind+key 的待执行作业被新参数顶替（replace）或忽略；
 *  - 优先级：P0 一致性 > P1 交互 > P2 派生视图 > P3 后台重活（数字小者优先）；
 *  - 空闲执行：默认在 requestIdleCallback（不可用时 setTimeout 兜底）执行，不抢占交互；
 *  - 陈旧丢弃：携带 gen 的作业若在入队后被 bumpEpoch 越过则丢弃；
 *  - flush：同步点（文件切换/关库）前等待关键作业完成；
 *  - 可观测：[job] 前缀日志 + status/queue 查询。
 *
 * 用法：
 *   window.MemoriaScheduler.schedule({
 *     kind: 'kp_panel', key: state.currentPath,          // 去重键
 *     priority: 2,                                        // 0..N，越小越优先
 *     run: async (ctx) => { ... },                        // 必须幂等、可重入
 *     replace: true,                                      // 同键新作业是否顶替旧作业
 *     gen: window.MemoriaScheduler.epoch(),               // 可选陈旧标记
 *     dropStale: true,                                    // 执行前 gen<epoch 则丢弃
 *   });
 */
(function (g) {
  "use strict";

  var QUEUE = [];
  var _running = false;
  var _seq = 0;
  var _epoch = 0;
  var _counters = { scheduled: 0, executed: 0, merged: 0, dropped: 0, queue_max: 0 };

  function trackQueue() {
    if (QUEUE.length > _counters.queue_max) _counters.queue_max = QUEUE.length;
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

  function epoch() {
    return _epoch;
  }
  function bumpEpoch() {
    _epoch += 1;
    return _epoch;
  }

  /** 入队；同 kind+key 待执行作业按 replace 语义合并。 */
  function schedule(spec) {
    var j = {
      id: ++_seq,
      kind: String(spec.kind || "job"),
      key: spec.key != null ? String(spec.key) : "",
      priority: Number.isFinite(spec.priority) ? spec.priority : 3,
      run: typeof spec.run === "function" ? spec.run : null,
      gen: spec.gen !== undefined ? spec.gen : _epoch,
      dropStale: !!spec.dropStale,
      replace: spec.replace !== false, // 默认 true：同键新作业顶替旧作业
      created: Date.now(),
      status: "queued",
    };
    if (!j.run) {
      log("schedule 忽略（无 run）: " + tag(j));
      return null;
    }
    // 基准旁路（__BENCH_DISABLE_SCHEDULER=1）：退化回“立即同步执行”，用于 A/B 对照“没有调度”的路径
    if (isBypass()) {
      _counters.scheduled += 1;
      _counters.executed += 1;
      log("旁路执行 " + tag(j) + " #" + j.id);
      try {
        var pr = j.run({ kind: j.kind, key: j.key, id: j.id });
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
    log("入队 " + dk + " #" + j.id + " prio=" + j.priority + " queue=" + QUEUE.length);
    pump();
    return j.id;
  }

  function _pick() {
    // 按优先级升序（小=高优先），同优先级按入队序
    QUEUE.sort(function (a, b) {
      return a.priority - b.priority || a.id - b.id;
    });
    return QUEUE.length ? QUEUE[0] : null;
  }

  function pump() {
    if (_running) return;
    _running = true;
    idle(asyncPump);
  }

  async function asyncPump() {
    try {
      // eslint-disable-next-line no-constant-condition
      while (true) {
        var j = _pick();
        if (!j) break;
        QUEUE.shift();
        trackQueue();
        if (j.dropStale && j.gen < _epoch) {
          j.status = "dropped";
          _counters.dropped += 1;
          log("陈旧丢弃 " + tag(j) + " (gen " + j.gen + " < " + _epoch + ")");
          continue;
        }
        j.status = "running";
        _counters.executed += 1;
        log("执行 " + tag(j) + " #" + j.id);
        try {
          await j.run({ kind: j.kind, key: j.key, id: j.id });
          j.status = "done";
        } catch (err) {
          j.status = "error";
          log("失败 " + tag(j) + ": " + (err && err.message ? err.message : err));
        }
      }
    } finally {
      _running = false;
    }
  }

  /** 同步点：等待当前及已入队作业执行完（关键路径使用）。 */
  function flush() {
    if (!QUEUE.length && !_running) return Promise.resolve();
    var p = asyncPump();
    // 若没有排队的空闲 handle 正在等，直接跑一轮
    return p;
  }

  function status() {
    return {
      queued: QUEUE.filter(function (j) { return j.status === "queued"; }).length,
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
    };
  }
  function resetCounters() {
    _counters = { scheduled: 0, executed: 0, merged: 0, dropped: 0, queue_max: 0 };
  }

  g.MemoriaScheduler = {
    schedule: schedule,
    flush: flush,
    epoch: epoch,
    bumpEpoch: bumpEpoch,
    status: status,
    counters: counters,
    resetCounters: resetCounters,
    isBypass: isBypass,
    note: note,
    traceFlush: traceFlush,
  };
})(typeof window !== "undefined" ? window : globalThis);
