/**
 * Web Worker 布局桥接：增强 MemoriaGraphLayout2D / 3D
 */
(function (global) {
  "use strict";

  const DEFAULT_WORKER_MIN_NODES = 60;
  const WORKER_READY_TIMEOUT_MS = 3000;

  function resolveWorkerUrl() {
    if (typeof window !== "undefined" && window.location?.href) {
      try {
        return new URL("/m0/js/graph-layout-worker.js", window.location.href).href;
      } catch (_) {
        /* fall through */
      }
    }
    return "/m0/js/graph-layout-worker.js";
  }

  const WORKER_URL = resolveWorkerUrl();

  function workerSupported(useWorker) {
    return useWorker !== false && typeof Worker !== "undefined";
  }

  function enhanceLayoutPrototype(proto, dim) {
    const origTick = proto.tick;
    const origWarmup = proto._warmup;
    const origStart = proto.start;
    const origStop = proto.stop;
    const origLoad = proto.loadFromEngine;
    const origSetDrag = proto.setDragNode;
    const origReheat = proto.reheat;

    proto._workerDim = dim;
    proto._worker = null;
    proto._workerActive = false;
    proto._workerWaitingReady = false;
    proto._workerReadyTimer = null;

    proto._clearWorkerReadyTimer = function () {
      if (this._workerReadyTimer) {
        clearTimeout(this._workerReadyTimer);
        this._workerReadyTimer = null;
      }
    };

    proto._terminateWorker = function () {
      this._clearWorkerReadyTimer();
      if (this._worker) {
        this._worker.postMessage({ type: "stop" });
        this._worker.terminate();
        this._worker = null;
      }
      this._workerActive = false;
      this._workerWaitingReady = false;
    };

    proto._recoverMainThreadSimulation = function (reason) {
      const hadWorker = this._workerActive || this._workerWaitingReady;
      this._terminateWorker();
      if (!this.nodes?.length) return;
      if (!hadWorker) return;
      console.warn("[GraphLayoutWorker] fallback to main thread", reason);
      origWarmup.call(this);
      this.alpha = this.opts.alphaTarget ?? 0.12;
      this._emit("reset", { nodes: this.nodes, links: this.simLinks });
      if (this.running) {
        origStart.call(this);
      }
    };

    proto._shouldUseWorker = function () {
      return (
        workerSupported(this.opts.useWorker) &&
        (this.nodes?.length || 0) >=
          (this.opts.workerMinNodes ?? DEFAULT_WORKER_MIN_NODES)
      );
    };

    proto._ensureWorker = function () {
      if (!workerSupported(this.opts.useWorker)) return null;
      if (!this._worker) {
        try {
          this._worker = new Worker(WORKER_URL);
          this._worker.onmessage = (e) => this._onWorkerMessage(e.data);
          this._worker.onerror = (err) => {
            console.error("[GraphLayoutWorker]", err);
            this._recoverMainThreadSimulation(err);
          };
        } catch (err) {
          console.warn("[GraphLayoutWorker] unavailable", err);
          this._worker = null;
        }
      }
      return this._worker;
    };

    proto._ensureSimulationRunning = function () {
      if (!this.running) return;
      if (this._workerWaitingReady) return;
      if (this._workerActive && this._worker) {
        this._worker.postMessage({ type: "start" });
      } else if (!this.raf) {
        this.running = false;
        origStart.call(this);
      }
    };

    proto._onWorkerMessage = function (msg) {
      if (!msg) return;
      if (this._workerWaitingReady && msg.type !== "ready") return;
      if (!this._workerActive && msg.type !== "ready") return;
      const Sim = global.MemoriaGraphLayoutSim;
      if (msg.type === "ready" || msg.type === "tick") {
        if (msg.nodes && Sim) {
          Sim.applyPackedPositions(this.nodes, msg.nodes, this._workerDim);
        }
        if (msg.alpha != null) this.alpha = msg.alpha;
        if (msg.type === "ready") {
          this._clearWorkerReadyTimer();
          this._workerWaitingReady = false;
          this._workerActive = true;
          this._emit("reset", { nodes: this.nodes, links: this.simLinks });
          this._ensureSimulationRunning();
        } else {
          this._emit("tick", { nodes: this.nodes, alpha: this.alpha });
        }
      }
    };

    proto._syncWorkerLoad = function () {
      const w = this._ensureWorker();
      if (!w) return false;
      const Sim = global.MemoriaGraphLayoutSim;
      this._workerWaitingReady = true;
      this._clearWorkerReadyTimer();
      this._workerReadyTimer = setTimeout(() => {
        if (this._workerWaitingReady) {
          this._recoverMainThreadSimulation("ready timeout");
        }
      }, WORKER_READY_TIMEOUT_MS);
      w.postMessage({
        type: "load",
        dim: this._workerDim,
        opts: Sim.layoutOptsForWorker(this),
        nodes: Sim.packNodes(this.nodes, this._workerDim),
        simLinks: this.simLinks.map((l) => ({
          sourceIndex: l.sourceIndex,
          targetIndex: l.targetIndex,
          strengthScale: l.strengthScale,
        })),
      });
      return true;
    };

    proto.loadFromEngine = function (...args) {
      this._terminateWorker();
      origLoad.apply(this, args);
      if (!this._workerWaitingReady && !this._workerActive) {
        this._ensureSimulationRunning();
      }
      return this;
    };

    proto._warmup = function () {
      if (this._workerActive || this._workerWaitingReady) return;
      origWarmup.call(this);
    };

    proto.tick = function (alphaOverride) {
      if (this._workerActive || this._workerWaitingReady) return;
      origTick.call(this, alphaOverride);
    };

    proto.start = function () {
      if (this.running) {
        this._ensureSimulationRunning();
        return;
      }
      this.running = true;
      if (this._workerWaitingReady) return;
      if (this._workerActive && this._worker) {
        this._worker.postMessage({ type: "start" });
        return;
      }
      origStart.call(this);
    };

    proto.stop = function () {
      if (this._dragId) {
        this._dragId = null;
        if (this._workerActive && this._worker) {
          this._worker.postMessage({ type: "setDrag", id: null, reheat: 0 });
        }
      }
      if (this._workerActive && this._worker) {
        this._worker.postMessage({ type: "stop" });
      }
      origStop.call(this);
    };

    proto.setDragNode = function (id) {
      const prev = this._dragId;
      origSetDrag.call(this, id);
      if (this._workerActive && this._worker) {
        const dragReheat = this.opts.dragReheat ?? 0.28;
        const releaseReheat = this.opts.dragReleaseReheat ?? 0.2;
        this._worker.postMessage({
          type: "setDrag",
          id: id || null,
          reheat: id ? dragReheat : prev ? releaseReheat : 0,
        });
      }
    };

    proto.reheat = function (amount) {
      origReheat.call(this, amount);
      if (this._workerActive && this._worker) {
        this._worker.postMessage({ type: "reheat", amount });
      }
    };

    if (dim === "2d") {
      const origMove2d = proto.moveDragNode2D;
      proto.moveDragNode2D = function (x, y) {
        origMove2d.call(this, x, y);
        if (this._workerActive && this._worker && this._dragId) {
          this._worker.postMessage({ type: "moveDrag", x, y });
        }
      };
    } else {
      const origMove3d = proto.moveDragNode3D;
      proto.moveDragNode3D = function (x, y, z) {
        origMove3d.call(this, x, y, z);
        if (this._workerActive && this._worker && this._dragId) {
          this._worker.postMessage({ type: "moveDrag", x, y, z });
        }
      };
    }

    const origApply = proto.applyOptions;
    proto.applyOptions = function (partial, opts) {
      origApply.call(this, partial, opts);
      if (this._workerActive && this._worker) {
        const Sim = global.MemoriaGraphLayoutSim;
        this._worker.postMessage({
          type: "setOpts",
          opts: Sim.layoutOptsForWorker(this),
        });
      }
    };
  }

  global.MemoriaGraphLayoutWorker = {
    enhanceLayoutPrototype,
    DEFAULT_WORKER_MIN_NODES,
    resolveWorkerUrl,
  };

  if (global.MemoriaGraphLayout2D) {
    enhanceLayoutPrototype(global.MemoriaGraphLayout2D.prototype, "2d");
  }
  if (global.MemoriaGraphLayout3D) {
    enhanceLayoutPrototype(global.MemoriaGraphLayout3D.prototype, "3d");
  }
})(typeof window !== "undefined" ? window : globalThis);
