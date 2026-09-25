/**
 * 导航模型：**以跳转行为训练、用马尔可夫链预测下一个该预渲染的文件**（2026-09-24 追加）。
 *
 * 设计见 `docs/design/preview-render-pipeline.md` §3.5（马尔可夫链）/ §3.6（KP 层）。本文件是**纯函数内核**
 * —— 无 DOM、无 IO、无全局状态 ⇒ 可以 `node` 单独跑分数（有数值断言），`app.js` / `nav-stack.js` 只负责喂数据。
 *
 * ## 模型
 *
 * - **节点**：`(file, kpId)` 两级 —— 有 `kpId` 时用 `file + "\u0000" + kpId` 作键（KP 级），否则只用 `file`。
 *   两级**同一张图**：KP 级的行在**投影到文件**时按文件求和（`projectFiles`）⇒ §3.6 要的"预测在 KP 层、
 *   渲染在文件层"一次成立。**不解析键**：每个节点另存 `nodeFiles[node]`（文件路径里可能含 `#` 等字符）。
 * - **计数带时间衰减**：记一条 `a → b` 时，先把 a 那一行按半衰期惰性衰减再 +1（不衰减 ⇒ 早年习惯永久统治）。
 * - **预测** = **带重启的随机游走（PPR）截断 K 步**，重启点 = 当前节点：
 *     `q₀ = e_c`；`q_{k+1} = α·e_c + (1−α)·q_k·P`
 *   再叠一档**全局 PageRank 稳态 `π`** 兜住"从 c 出发走不到但整体重要"的节点（冷启动/新文件）。
 * - **收益**（由调用方与成本相乘）：`S(node) = q_K(node) + μ·π(node)`，投影 `S_file(f) = Σ_{node∈f} S(node)`。
 *   ⇒ 一份 4000 行的大文件只命中一个弱 KP，仍可能不值得渲染整份（成本在 `app.js` 侧乘 `T̂(loadMs)`）。
 *
 * ## 反污染（关键）
 *
 * 本模块**只认喂进来的东西**；调用方（`nav-stack.js`）只在**用户发起**的导航上喂 ——
 * `skipNav:true` 的编程式重开（refresh 四连 / 写面同步）、预渲染自身、agent 写面重开**都不喂**，
 * 否则模型学的是自己的尾巴（自激回路）。
 *
 * ## 落点
 *
 * 调用方把 `record` 出的**一行 JSON**（`toLine`）追加进 `<kb>/.memoria/cache/nav/transitions.jsonl`；
 * 载入时用 `fromLines` 逐行重放（**只认合法行、坏行丢弃**），超过 `MAX_RECOMPACT_LINES` 就 `compact()` 重写。
 * 该目录属 `.memoria/cache/**` = **可再生缓存**（`AGENTS.md §1`）⇒ 丢了不影响正确性，只损失一点预测质量。
 */
(function (global) {
  "use strict";

  /** 默认策略（**与 `display-settings.js` 的 `PERF_DEFAULTS` 逐字相等** —— 有跨文件一致性钉子）。 */
  const DEFAULTS = Object.freeze({
    navPredictor: "markov",
    navHalfLifeDays: 14,
  });

  /** 每个键的合法区间（设置页传进来的坏值不该让算法崩，也不该静默变成怪值）。 */
  const RANGES = {
    navHalfLifeDays: [0.5, 365],
  };
  const MODES = ["off", "markov"];

  /** 随机游走的重启概率 `α`（越大越偏"只看下一步"）。 */
  const RESTART = 0.35;
  /** 截断步数 `K`（＝"看接下来几跳内谁最可能被打开"）。 */
  const STEPS = 3;
  /** 全局先验 `π` 的权重 `μ`。 */
  const PRIOR = 0.15;
  /** PageRank 阻尼。 */
  const DAMPING = 0.85;
  /** 冷启动阈值：全库样本不足它 ⇒ `predict` 只回启发式（由调用方决定回退到目录相邻）。 */
  const MIN_SAMPLES = 50;
  /** 规模上限（超出按 `visits` 截断；图越大越慢，而收益递减）。 */
  const MAX_NODES = 5000;
  const MAX_EDGES = 20000;
  const MAX_DEGREE = 64;
  /** 日志行数超过它就让调用方 `compact()` 重写（避免无限追加）。 */
  const MAX_RECOMPACT_LINES = 20000;
  /** 节点键的分隔符（`\u0000` 不会出现在文件路径里）。 */
  const SEP = "\u0000";

  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }

  function num(value, fallback) {
    const n = typeof value === "number" ? value : parseFloat(String(value == null ? "" : value));
    return Number.isFinite(n) ? n : fallback;
  }

  /** 策略归一（坏值 ⇒ 回落默认；模式串只认 `MODES`）。 */
  function sanitize(raw) {
    const p = Object.assign({}, DEFAULTS);
    if (raw && typeof raw === "object") {
      if (raw.navPredictor !== undefined) {
        p.navPredictor = MODES.indexOf(String(raw.navPredictor)) >= 0 ? String(raw.navPredictor) : DEFAULTS.navPredictor;
      }
      if (raw.navHalfLifeDays !== undefined) p.navHalfLifeDays = clamp(num(raw.navHalfLifeDays, DEFAULTS.navHalfLifeDays), RANGES.navHalfLifeDays[0], RANGES.navHalfLifeDays[1]);
    }
    return p;
  }

  /** 空模型。 */
  function create() {
    return { edges: Object.create(null), visits: Object.create(null), nodeFiles: Object.create(null), samples: 0, startedAt: 0 };
  }

  /** 节点键：有 KP 用两级键，否则只到文件（见文件头"不解析键"那条）。 */
  function nodeKey(file, kpId) {
    const f = String(file == null ? "" : file);
    if (!f) return "";
    const k = kpId == null || kpId === "" ? "" : String(kpId);
    return k ? f + SEP + k : f;
  }

  function fileOf(model, node) {
    const map = model && model.nodeFiles ? model.nodeFiles : null;
    if (map && map[node]) return map[node];
    return String(node || "").split(SEP)[0];
  }

  function isModel(model) {
    return !!(model && typeof model === "object" && model.edges && model.nodeFiles);
  }

  function ensure(model, file, node) {
    if (!model.nodeFiles[node]) model.nodeFiles[node] = String(file || fileOf(model, node));
    if (!model.visits[node]) model.visits[node] = 0;
  }

  /** 惰性衰减：把 `from` 那一行按半衰期缩到"现在"（`halfLifeDays <= 0` 视为不衰减）。 */
  function decayRow(model, from, now, halfLifeDays) {
    const row = model.edges[from];
    if (!row) return;
    const stamp = row.__at || 0;
    if (!stamp || !(halfLifeDays > 0) || !(now > stamp)) return;
    const factor = Math.pow(2, -(now - stamp) / (halfLifeDays * 86400000));
    if (factor >= 0.999) return;
    for (const key of Object.keys(row)) {
      if (key === "__at") continue;
      row[key] *= factor;
    }
    row.__at = now;
  }

  /** 行内按度截断（丢最小项）⇒ 稀疏、上限可控。 */
  function trimRow(row) {
    const keys = Object.keys(row).filter((k) => k !== "__at");
    if (keys.length <= MAX_DEGREE) return;
    keys.sort((a, b) => row[a] - row[b]);
    for (const key of keys.slice(0, keys.length - MAX_DEGREE)) delete row[key];
  }

  /** 规模收口：节点/边超限时丢"访问最少"的节点。 */
  function trimModel(model) {
    const nodes = Object.keys(model.visits);
    if (nodes.length <= MAX_NODES) return;
    nodes.sort((a, b) => (model.visits[a] || 0) - (model.visits[b] || 0));
    for (const node of nodes.slice(0, nodes.length - MAX_NODES)) deleteNode(model, node);
  }

  function deleteNode(model, node) {
    delete model.visits[node];
    delete model.nodeFiles[node];
    delete model.edges[node];
    for (const key of Object.keys(model.edges)) {
      const row = model.edges[key];
      if (row && row[node] !== undefined) delete row[node];
      if (row && Object.keys(row).length <= 1) delete model.edges[key];
    }
  }

  function edgeCount(model) {
    let n = 0;
    for (const key of Object.keys(model.edges)) n += Object.keys(model.edges[key]).filter((k) => k !== "__at").length;
    return n;
  }

  /**
   * 记一条**用户发起**的跳转 `from → to`（见文件头"反污染"）。返回记录（供调用方追加成一行日志）。
   * 自我跳转（同一节点）**不计边**，只算活跃度 —— 与 §3.5 "同文件内锚点跳转不计跨文件边"一致。
   */
  function record(model, from, to, now, policy) {
    const t = Number.isFinite(now) ? now : Date.now();
    const p = policy || DEFAULTS;
    const half = num(p.navHalfLifeDays, DEFAULTS.navHalfLifeDays);
    const a = String(from == null ? "" : from);
    const b = String(to == null ? "" : to);
    if (!isModel(model) || !b) return null;
    if (!model.startedAt) model.startedAt = t;
    ensure(model, fileOf(model, b), b);
    model.visits[b] = (model.visits[b] || 0) + 1;
    if (!a || a === b) return { at: t, from: a, to: b, self: true };
    ensure(model, fileOf(model, a), a);
    model.visits[a] = (model.visits[a] || 0) + 1;
    const row = model.edges[a] || (model.edges[a] = Object.create(null));
    decayRow(model, a, t, half);
    row[b] = (row[b] || 0) + 1;
    row.__at = t;
    trimRow(row);
    model.samples += 1;
    trimModel(model);
    return { at: t, from: a, to: b };
  }

  /** 归一化的转移行（含衰减；空行 ⇒ 空对象）。 */
  function rowOf(model, node, now, policy) {
    const row = model.edges[node];
    if (!row) return {};
    decayRow(model, node, now || Date.now(), num((policy || DEFAULTS).navHalfLifeDays, DEFAULTS.navHalfLifeDays));
    const out = {};
    let total = 0;
    for (const key of Object.keys(row)) {
      if (key === "__at") continue;
      const w = row[key];
      if (w > 0) { out[key] = w; total += w; }
    }
    if (!total) return {};
    for (const key of Object.keys(out)) out[key] /= total;
    return out;
  }

  /** 全局 PageRank 稳态 `π`（在**文件级**聚合图上做幂迭代；按 `samples` 记忆化）。 */
  const _rankCache = { key: "", value: null };

  function rank(model) {
    if (!isModel(model)) return {};
    const key = String(model.samples) + "/" + String(edgeCount(model));
    if (_rankCache.key === key && _rankCache.value) return _rankCache.value;
    const nodes = Object.keys(model.visits);
    const files = [];
    const fileIndex = Object.create(null);
    for (const node of nodes) {
      const f = fileOf(model, node);
      if (fileIndex[f] === undefined) { fileIndex[f] = files.length; files.push(f); }
    }
    const n = files.length;
    const out = Object.create(null);
    if (!n) { _rankCache.key = key; _rankCache.value = out; return out; }
    const adj = files.map(() => Object.create(null));
    for (const node of nodes) {
      const row = rowOf(model, node, Date.now(), DEFAULTS);
      const i = fileIndex[fileOf(model, node)];
      for (const target of Object.keys(row)) {
        const j = fileIndex[fileOf(model, target)];
        adj[i][j] = (adj[i][j] || 0) + row[target];
      }
    }
    let cur = files.map(() => 1 / n);
    for (let iter = 0; iter < 20; iter += 1) {
      const next = files.map(() => (1 - DAMPING) / n);
      for (let i = 0; i < n; i += 1) {
        const row = adj[i];
        let total = 0;
        for (const j of Object.keys(row)) total += row[j];
        if (!total) { for (let j = 0; j < n; j += 1) next[j] += (DAMPING * cur[i]) / n; continue; }
        for (const j of Object.keys(row)) next[Number(j)] += (DAMPING * cur[i] * row[j]) / total;
      }
      cur = next;
    }
    let max = 0;
    for (const v of cur) max = Math.max(max, v);
    for (let i = 0; i < n; i += 1) out[files[i]] = max > 0 ? cur[i] / max : 0;
    _rankCache.key = key;
    _rankCache.value = out;
    return out;
  }

  /**
   * PPR 截断 K 步：返回 `{ node: 概率 }`（**未含先验**）。
   * 实现即 `q_{k+1} = α·e_c + (1−α)·q_k·P`，`P` 行按需归一（稀疏展开）。
   */
  function diffuse(model, start, now, policy) {
    const p = policy || DEFAULTS;
    let q = Object.create(null);
    if (!start || !model.visits[start]) return q;
    q[start] = 1;
    for (let step = 0; step < STEPS; step += 1) {
      const next = Object.create(null);
      next[start] = RESTART;
      for (const node of Object.keys(q)) {
        const weight = q[node];
        if (!(weight > 0)) continue;
        const row = rowOf(model, node, now, p);
        const keys = Object.keys(row);
        if (!keys.length) { next[start] += (1 - RESTART) * weight; continue; }
        for (const target of keys) next[target] = (next[target] || 0) + (1 - RESTART) * weight * row[target];
      }
      q = next;
    }
    return q;
  }

  /** 把节点分投影到文件（`S_file = Σ S(node)`；同一文件多个 KP ⇒ 相加）。 */
  function projectFiles(model, nodeScores) {
    const out = Object.create(null);
    for (const node of Object.keys(nodeScores)) {
      const f = fileOf(model, node);
      if (!f) continue;
      out[f] = (out[f] || 0) + nodeScores[node];
    }
    return out;
  }

  /**
   * 预测：`{ start, files, exclude }` → **按分降序的文件数组** `[{file, score}]`。
   * `start` 为 "" 或不在模型里 ⇒ 返回空数组（调用方回退启发式）。样本不足 `MIN_SAMPLES` ⇒ 也回空数组。
   */
  function predict(model, options) {
    const opts = options || {};
    const now = Number.isFinite(opts.now) ? opts.now : Date.now();
    const policy = opts.policy || DEFAULTS;
    if (!isModel(model) || model.samples < MIN_SAMPLES) return [];
    if (String(policy.navPredictor || DEFAULTS.navPredictor) === "off") return [];
    const start = String(opts.start == null ? "" : opts.start);
    if (!start || !model.visits[start]) return [];
    const nodeScores = diffuse(model, start, now, policy);
    const pi = rank(model);
    const combined = Object.create(null);
    for (const node of Object.keys(nodeScores)) combined[node] = (combined[node] || 0) + nodeScores[node];
    for (const file of Object.keys(pi)) {
      // 先验落在**文件**上 ⇒ 摊到该文件下所有已知节点（没有节点的就建一个纯先验项）
      const nodes = Object.keys(model.nodeFiles).filter((n) => model.nodeFiles[n] === file);
      if (!nodes.length) { combined[file + SEP + "\u0000file"] = (combined[file + SEP + "\u0000file"] || 0) + PRIOR * pi[file]; continue; }
      for (const n of nodes) combined[n] = (combined[n] || 0) + (PRIOR * pi[file]) / nodes.length;
    }
    const byFile = projectFiles(model, combined);
    const exclude = opts.exclude && typeof opts.exclude.has === "function" ? opts.exclude : null;
    const startFile = fileOf(model, start);
    return Object.keys(byFile)
      .filter((f) => f && f !== startFile && !(exclude && exclude.has(f)))   // **永远排除当前文件本身**：重启质量 α 会留在起点，不排掉的话 top-1 恒为"你正在看的这份"，毫无预测意义
      .map((f) => ({ file: f, score: byFile[f] }))
      .sort((a, b) => b.score - a.score);
  }

  /** 读数（面板展示与排查用）。 */
  function stats(model) {
    if (!isModel(model)) return { nodes: 0, edges: 0, samples: 0, files: 0, ready: false };
    return {
      nodes: Object.keys(model.visits).length,
      edges: edgeCount(model),
      samples: model.samples || 0,
      files: Object.keys(model.nodeFiles).reduce(function (acc, node) {
        const f = model.nodeFiles[node];
        if (f && acc.indexOf(f) < 0) acc.push(f);
        return acc;
      }, []).length,
      ready: (model.samples || 0) >= MIN_SAMPLES,
    };
  }

  /** 一条转移 → 一行 JSONL（落盘用；只有必要字段）。 */
  function toLine(rec) {
    if (!rec || rec.self) return "";
    return JSON.stringify({ a: rec.at, f: rec.from, t: rec.to });
  }

  /** 逐行重放（**坏行丢弃**，不抛）。用于载入 `.memoria/cache/nav/transitions.jsonl`。 */
  function fromLines(text, policy) {
    const model = create();
    const lines = String(text == null ? "" : text).split("\n");
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      let rec = null;
      try { rec = JSON.parse(trimmed); } catch (_) { continue; }
      if (!rec || typeof rec !== "object") continue;
      const from = String(rec.f == null ? "" : rec.f);
      const to = String(rec.t == null ? "" : rec.t);
      if (!to) continue;
      record(model, from, to, Number(rec.a) || model.startedAt || Date.now(), policy);
    }
    return model;
  }

  /** 紧凑化（返回 `{jsonl, dropped}`：只保留最近的 `keep` 条边；丢掉的记在 `dropped`）。 */
  function compact(model, keep) {
    const limit = Math.max(1, Math.round(num(keep, MAX_DEGREE)));
    const lines = [];
    for (const from of Object.keys(model.edges)) {
      const row = model.edges[from];
      const pairs = Object.keys(row).filter((k) => k !== "__at").map((k) => ({ to: k, w: row[k] })).sort((x, y) => y.w - x.w);
      const kept = pairs.slice(0, limit);
      const dropped = pairs.slice(limit).reduce((acc, item) => acc + item.w, 0);
      for (const item of kept) lines.push(JSON.stringify({ a: Date.now(), f: from, t: item.to, w: Math.round(item.w * 1000) / 1000, d: Math.round(dropped * 1000) / 1000 }));
    }
    return { jsonl: lines.join("\n") + (lines.length ? "\n" : ""), dropped: lines.length };
  }

  global.MemoriaNavModel = {
    DEFAULTS: DEFAULTS,
    MAX_RECOMPACT_LINES: MAX_RECOMPACT_LINES,
    MIN_SAMPLES: MIN_SAMPLES,
    MODES: MODES,
    PRIOR: PRIOR,
    RANGES: RANGES,
    RESTART: RESTART,
    SEP: SEP,
    STEPS: STEPS,
    compact: compact,
    create: create,
    fileOf: fileOf,
    fromLines: fromLines,
    nodeKey: nodeKey,
    predict: predict,
    rank: rank,
    record: record,
    sanitize: sanitize,
    stats: stats,
    toLine: toLine,
  };
})(window);
