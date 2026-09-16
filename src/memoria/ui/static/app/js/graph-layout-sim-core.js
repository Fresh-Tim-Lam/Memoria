/**
 * 力导向 tick 核心（主线程 / Worker 共用）
 */
(function (global) {
  "use strict";

  const DEFAULTS = {
    linkDistance: 108,
    linkStrength: 0.28,
    repulsion: 5200,
    centerStrength: 0.006,
    velocityDecay: 0.8,
    alphaMin: 0.012,
    alphaDecay: 0.045,
    alphaTarget: 0.12,
    dragReheat: 0.28,
    dragReleaseReheat: 0.2,
    maxTicksPerFrame: 6,
    frameBudgetMs: 8,
    warmupTicks: 160,
    // 排斥核：默认走 Barnes-Hut 近似（O(N log N)）；false = 精确全对全（A/B 与正确性参照）
    bh: true,
    bhTheta: 0.9,
    // 两节点几乎重合时的距离下限（替掉旧版的 Math.random() 抖动）：① 消数值爆炸 ② 布局可复现
    distanceMin: 1,
    // 每 tick 位移上限 = linkDistance × 该系数（0 = 不限）：兜住任何残余的数值爆炸
    maxVelocityRatio: 1,
    groupMode: "single",
    distMode: "grid",
  };

  /**
   * 帧预算：最多跑 `maxTicksPerFrame` 个 tick，但累计耗时达到 `frameBudgetMs` 就提前收手。
   *
   * 为什么需要：原先是"每帧固定 6 个 tick"，图一大单帧就无上界（实测 5000 节点单 tick 658ms、
   * 单帧 3958ms ≈ 0.25fps）。改成预算后**帧时间有上界**：大图自动少跑 tick（收敛慢一点，但不掉帧）。
   *
   * 语义（有意为之，别"优化"掉）：
   *   · **至少跑 1 个 tick** —— 否则大图上仿真会彻底冻结（alpha 不衰减、进度为零）；
   *   · 单个 tick 自身可能超预算（如 5000 节点一 tick 658ms），此时本帧只有这 1 个 tick；
   *   · `frameBudgetMs <= 0` 视为关闭预算，退回"固定 maxTicksPerFrame 个"（供 A/B 对照用）。
   *
   * @returns {number} 本帧实际执行的 tick 数
   */
  function runTicksWithBudget(tickFn, opts, now) {
    const clock = now || (() => performance.now());
    const maxTicks = Math.max(1, opts?.maxTicksPerFrame ?? DEFAULTS.maxTicksPerFrame);
    const budget = opts?.frameBudgetMs ?? DEFAULTS.frameBudgetMs;
    if (!(budget > 0)) {
      for (let i = 0; i < maxTicks; i++) tickFn();
      return maxTicks;
    }
    const t0 = clock();
    let done = 0;
    while (done < maxTicks) {
      tickFn();
      done++;
      if (clock() - t0 >= budget) break;
    }
    return done;
  }

  /**
   * 全部群视图下默认跳过跨群排斥（旧「群组网格」分布靠 groupOx/Oy 锚点摆位，不靠排斥）。
   * 拖拽节点与任意节点之间始终参与排斥；「散落」分布也不跳过 —— 群必须互相推开才不叠成一坨。
   */
  function skipPairRepulsion(a, b, dragId, groupMode, distMode) {
    if (!a.groupId || !b.groupId || a.groupId === b.groupId) return false;
    if (dragId && (a.id === dragId || b.id === dragId)) return false;
    if (distMode === "scatter") return false;
    return groupMode === "all";
  }

  /**
   * 分桶（仅"不跨群排斥"时才需要）：与 `skipPairRepulsion` 的分组语义一致 —— 每个群一棵树，
   * 跨群对被自然排除。返回 null = 用单棵全局树（= 全部跨群对都参与排斥）。
   *
   * 有节点缺 `groupId` 时退回单桶：宁可多算排斥（更"物理"），也不要少算 —— 该混合态理论上不出现。
   */
  function groupBucketsIfNeeded(nodes, groupMode, distMode) {
    if (groupMode !== "all" || distMode === "scatter") return null;
    const map = new Map();
    for (let i = 0; i < nodes.length; i++) {
      const gid = nodes[i].groupId;
      if (!gid) return null;
      let bucket = map.get(gid);
      if (!bucket) map.set(gid, (bucket = []));
      bucket.push(i);
    }
    return [...map.values()];
  }

  /**
   * 尝试用 Barnes-Hut 处理本 tick 的排斥（默认路径）。
   * @returns {boolean} true = 已处理，调用方**不要**再跑精确的 O(N²) 循环
   */
  function tryBHRepulsion(nodes, dim, rep, opts, ctx) {
    const BH = global.MemoriaGraphBH;
    if (!BH || opts.bh === false) return false;
    const stat = BH.applyRepulsion(
      nodes,
      dim,
      rep,
      groupBucketsIfNeeded(nodes, ctx.groupMode, ctx.distMode),
      {
        theta: opts.bhTheta,
        dragId: ctx.dragId,
        distanceMin: opts.distanceMin,
        collectStats: !!ctx.prof,
      }
    );
    if (stat && ctx.prof) {
      ctx.prof.bhInteractions += stat.interactions;
      ctx.prof.bhCells += stat.cells;
    }
    return true;
  }

  /** 每 tick 位移上限（= linkDistance × maxVelocityRatio）；返回平方值，0 = 不限 */
  function maxVelocitySq(opts) {
    const ratio = opts.maxVelocityRatio ?? DEFAULTS.maxVelocityRatio;
    const d = opts.linkDistance ?? DEFAULTS.linkDistance;
    const v = ratio > 0 ? ratio * d : 0;
    return v > 0 ? v * v : 0;
  }

  /**
   * 可选分项剖面（仅 `opts.profile === true` 时填充）。
   *
   * 目的：回答"单 tick 到底花在哪" —— 尤其是 `dist2 < 1` 守卫分支（近重合节点触发 `Math.random()`）
   * 被命中的频率。实测线索：star 5000 在"跑满 160 tick 后"单 tick 1515ms，而只跑 6 tick 时约 700ms
   * （节点还没聚拢、守卫很少触发）—— 2.2× 的差与此吻合，需用计数器确认（见 design/graph-benchmark.md §5.2 结论 3）。
   *
   * 成本：默认关闭；关闭时热循环只多一个可预测的布尔判断，不做任何计时。
   */
  function ensureProfile(state) {
    if (!state.profile) {
      state.profile = {
        ticks: 0,
        // 不逐对累加（那是千万级的内层循环，会自己变成热点并污染 repulsion 分项）；
        // 改为每 tick 记一次"槽位数"，再减去跳过的对数 ⇒ 实际参与计算的对数。
        pairSlots: 0,
        skipped: 0,
        distGuardHits: 0,
        // Barnes-Hut 路径的诊断计数（替代 pairSlots/skipped 口径）
        bhInteractions: 0,
        bhCells: 0,
        centerMs: 0,
        repulsionMs: 0,
        linksMs: 0,
        integrateMs: 0,
      };
    }
    return state.profile;
  }

  function tick2D(state, opts, alphaOverride) {
    const nodes = state.nodes;
    const links = state.simLinks;
    const n = nodes.length;
    const alpha = alphaOverride != null ? alphaOverride : state.alpha;
    const repBase = opts.repulsion * (1 + Math.sqrt(n) * 0.15);
    const rep = repBase * alpha;
    const center = opts.centerStrength * alpha;
    const dragId = state.dragId;
    const groupMode = opts.groupMode || "single";
    const distMode = opts.distMode || "grid";
    const prof = opts.profile ? ensureProfile(state) : null;
    let mark = prof ? performance.now() : 0;
    if (prof) {
      prof.ticks += 1;
      prof.pairSlots += (n * (n - 1)) / 2;
    }

    for (let i = 0; i < n; i++) {
      const anchorX = nodes[i].groupOx != null ? nodes[i].groupOx : 0;
      const anchorY = nodes[i].groupOy != null ? nodes[i].groupOy : 0;
      nodes[i].vx += (anchorX - nodes[i].x) * center;
      nodes[i].vy += (anchorY - nodes[i].y) * center;
    }
    if (prof) {
      const now = performance.now();
      prof.centerMs += now - mark;
      mark = now;
    }

    if (!tryBHRepulsion(nodes, 2, rep, opts, { groupMode, distMode, dragId, prof })) {
      // 精确路径（`bh: false`）：A/B 对照与正确性参照用
      const dMin = opts.distanceMin ?? DEFAULTS.distanceMin;
      const dMin2 = dMin * dMin;
      for (let i = 0; i < n; i++) {
        for (let j = i + 1; j < n; j++) {
          if (skipPairRepulsion(nodes[i], nodes[j], dragId, groupMode, distMode)) {
            if (prof) prof.skipped += 1;
            continue;
          }
          let dx = nodes[j].x - nodes[i].x;
          let dy = nodes[j].y - nodes[i].y;
          let dist2 = dx * dx + dy * dy;
          if (dist2 < dMin2) {
            if (prof) prof.distGuardHits += 1;
            dist2 = dMin2; // 距离下限，替掉旧版的 Math.random() 抖动（见 graph-bh-tree.js 头注）
          }
          const dist = Math.sqrt(dist2);
          const f = rep / dist2;
          const fx = (dx / dist) * f;
          const fy = (dy / dist) * f;
          nodes[i].vx -= fx;
          nodes[i].vy -= fy;
          nodes[j].vx += fx;
          nodes[j].vy += fy;
        }
      }
    }
    if (prof) {
      const now = performance.now();
      prof.repulsionMs += now - mark;
      mark = now;
    }

    for (const link of links) {
      const s = nodes[link.sourceIndex];
      const t = nodes[link.targetIndex];
      let dx = t.x - s.x;
      let dy = t.y - s.y;
      let dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const str = opts.linkStrength * alpha * (link.strengthScale || 1);
      const force = ((dist - opts.linkDistance) / dist) * str;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      s.vx += fx;
      s.vy += fy;
      t.vx -= fx;
      t.vy -= fy;
    }
    if (prof) {
      const now = performance.now();
      prof.linksMs += now - mark;
      mark = now;
    }

    const maxV2 = maxVelocitySq(opts);
    for (const node of nodes) {
      if (node.id === dragId) continue;
      let vx = node.vx * opts.velocityDecay;
      let vy = node.vy * opts.velocityDecay;
      const v2 = vx * vx + vy * vy;
      if (maxV2 > 0 && v2 > maxV2) {
        const k = Math.sqrt(maxV2 / v2); // 位移上限：兜住任何残余的数值爆炸
        vx *= k;
        vy *= k;
      }
      node.vx = vx;
      node.vy = vy;
      node.x += vx;
      node.y += vy;
    }
    if (prof) prof.integrateMs += performance.now() - mark;

    if (alphaOverride == null) {
      const decay = opts.alphaDecay ?? 0.045;
      state.alpha += (opts.alphaMin - state.alpha) * decay;
    }
  }

  function tick3D(state, opts, alphaOverride) {
    const nodes = state.nodes;
    const links = state.simLinks;
    const n = nodes.length;
    const alpha = alphaOverride != null ? alphaOverride : state.alpha;
    const repBase = opts.repulsion * (1 + Math.sqrt(n) * 0.15);
    const rep = repBase * alpha;
    const center = opts.centerStrength * alpha;
    const dragId = state.dragId;
    const groupMode = opts.groupMode || "single";
    const distMode = opts.distMode || "grid";
    const prof = opts.profile ? ensureProfile(state) : null;
    let mark = prof ? performance.now() : 0;
    if (prof) {
      prof.ticks += 1;
      prof.pairSlots += (n * (n - 1)) / 2;
    }

    for (let i = 0; i < n; i++) {
      const anchorX = nodes[i].groupOx != null ? nodes[i].groupOx : 0;
      const anchorY = nodes[i].groupOy != null ? nodes[i].groupOy : 0;
      const anchorZ = nodes[i].groupOz != null ? nodes[i].groupOz : 0;
      nodes[i].vx += (anchorX - nodes[i].x) * center;
      nodes[i].vy += (anchorY - nodes[i].y) * center;
      nodes[i].vz += (anchorZ - nodes[i].z) * center;
    }
    if (prof) {
      const now = performance.now();
      prof.centerMs += now - mark;
      mark = now;
    }

    if (!tryBHRepulsion(nodes, 3, rep, opts, { groupMode, distMode, dragId, prof })) {
      // 精确路径（`bh: false`）：A/B 对照与正确性参照用
      const dMin = opts.distanceMin ?? DEFAULTS.distanceMin;
      const dMin2 = dMin * dMin;
      for (let i = 0; i < n; i++) {
        for (let j = i + 1; j < n; j++) {
          if (skipPairRepulsion(nodes[i], nodes[j], dragId, groupMode, distMode)) {
            if (prof) prof.skipped += 1;
            continue;
          }
          let dx = nodes[j].x - nodes[i].x;
          let dy = nodes[j].y - nodes[i].y;
          let dz = nodes[j].z - nodes[i].z;
          let dist2 = dx * dx + dy * dy + dz * dz;
          if (dist2 < dMin2) {
            if (prof) prof.distGuardHits += 1;
            dist2 = dMin2; // 距离下限，替掉旧版的 Math.random() 抖动（见 graph-bh-tree.js 头注）
          }
          const dist = Math.sqrt(dist2);
          const f = rep / dist2;
          const fx = (dx / dist) * f;
          const fy = (dy / dist) * f;
          const fz = (dz / dist) * f;
          nodes[i].vx -= fx;
          nodes[i].vy -= fy;
          nodes[i].vz -= fz;
          nodes[j].vx += fx;
          nodes[j].vy += fy;
          nodes[j].vz += fz;
        }
      }
    }
    if (prof) {
      const now = performance.now();
      prof.repulsionMs += now - mark;
      mark = now;
    }

    for (const link of links) {
      const s = nodes[link.sourceIndex];
      const t = nodes[link.targetIndex];
      let dx = t.x - s.x;
      let dy = t.y - s.y;
      let dz = t.z - s.z;
      let dist = Math.sqrt(dx * dx + dy * dy + dz * dz) || 0.01;
      const str = opts.linkStrength * alpha * (link.strengthScale || 1);
      const force = ((dist - opts.linkDistance) / dist) * str;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      const fz = (dz / dist) * force;
      s.vx += fx;
      s.vy += fy;
      s.vz += fz;
      t.vx -= fx;
      t.vy -= fy;
      t.vz -= fz;
    }
    if (prof) {
      const now = performance.now();
      prof.linksMs += now - mark;
      mark = now;
    }

    const maxV2 = maxVelocitySq(opts);
    for (const node of nodes) {
      if (node.id === dragId) continue;
      let vx = node.vx * opts.velocityDecay;
      let vy = node.vy * opts.velocityDecay;
      let vz = node.vz * opts.velocityDecay;
      const v2 = vx * vx + vy * vy + vz * vz;
      if (maxV2 > 0 && v2 > maxV2) {
        const k = Math.sqrt(maxV2 / v2); // 位移上限：兜住任何残余的数值爆炸
        vx *= k;
        vy *= k;
        vz *= k;
      }
      node.vx = vx;
      node.vy = vy;
      node.vz = vz;
      node.x += vx;
      node.y += vy;
      node.z += vz;
    }
    if (prof) prof.integrateMs += performance.now() - mark;

    if (alphaOverride == null) {
      const decay = opts.alphaDecay ?? 0.045;
      state.alpha += (opts.alphaMin - state.alpha) * decay;
    }
  }

  /**
   * warmup（装载时的初始松弛）工作量上限：`pair 迭代数 × tick 数`。
   *
   * 为什么需要：`warmupTicks` 是固定 160，而每个 tick 是 O(N²) —— 大图上装载会变成**无界的同步工作**：
   * 实测 5000 节点 136s、3000 节点 47~51s（1000 节点 4.6s）。它一旦落在主线程就是"开图界面卡死 2 分钟"
   * （worker 就绪超时回退也会走到主线程，见 graph-layout-worker-bridge.js）。
   *
   * 取值 8e7 ≈ **1000 节点 × 160 tick** 的现状（实测 4.6s ⇒ 约 57ns/对·tick），
   * 于是 N ≤ 1000 完全不变，更大的图则按 (1000/N)² 等比缩减 —— 装载耗时被压到同一个量级。
   * 用**工作量**而非计时做上限：布局结果与机器速度无关，可复现（基准口径才不会漂）。
   */
  const WARMUP_PAIR_TICK_CAP = 8e7;
  /** warmup 下限：至少让初始摆位略微松弛，别停在原始摆环上 */
  const WARMUP_MIN_TICKS = 4;

  /** 给定规模下实际执行的 warmup tick 数（≤ 请求值） */
  function effectiveWarmupTicks(nodeCount, warmupTicks) {
    const want = Math.max(1, Math.trunc(warmupTicks ?? DEFAULTS.warmupTicks));
    const n = Math.max(0, Math.trunc(nodeCount) || 0);
    const pairs = (n * (n - 1)) / 2;
    if (pairs <= 0) return want;
    return Math.max(WARMUP_MIN_TICKS, Math.min(want, Math.floor(WARMUP_PAIR_TICK_CAP / pairs)));
  }

  function warmup(state, opts, dim) {
    const tick = dim === "3d" ? tick3D : tick2D;
    const ticks = effectiveWarmupTicks(state.nodes?.length, opts.warmupTicks);
    state.alpha = 1;
    for (let i = 0; i < ticks; i++) {
      tick(state, opts, 1 - i / ticks);
    }
    return ticks;
  }

  function packNodes(nodes, dim) {
    return nodes.map((n) => ({
      id: n.id,
      x: n.x,
      y: n.y,
      z: dim === "3d" ? n.z || 0 : 0,
      vx: n.vx || 0,
      vy: n.vy || 0,
      vz: dim === "3d" ? n.vz || 0 : 0,
      groupId: n.groupId || null,
      groupOx: n.groupOx != null ? n.groupOx : null,
      groupOy: n.groupOy != null ? n.groupOy : null,
      groupOz: dim === "3d" && n.groupOz != null ? n.groupOz : null,
    }));
  }

  function applyPackedPositions(nodes, packed, dim) {
    const byId = new Map((packed || []).map((p) => [p.id, p]));
    for (let i = 0; i < nodes.length; i++) {
      const node = nodes[i];
      const p = byId.get(node.id) ?? packed[i];
      if (!p) continue;
      node.x = p.x;
      node.y = p.y;
      node.vx = p.vx;
      node.vy = p.vy;
      if (dim === "3d") {
        node.z = p.z;
        node.vz = p.vz;
      }
    }
  }

  function layoutOptsForWorker(layout) {
    return {
      ...(layout.opts || {}),
      groupMode: layout._groupMode || "single",
      distMode: layout._distMode || layout.opts?.distMode || "grid",
    };
  }

  global.MemoriaGraphLayoutSim = {
    DEFAULTS,
    WARMUP_PAIR_TICK_CAP,
    effectiveWarmupTicks,
    tick2D,
    tick3D,
    warmup,
    runTicksWithBudget,
    packNodes,
    applyPackedPositions,
    layoutOptsForWorker,
    skipPairRepulsion,
  };
})(typeof self !== "undefined" ? self : typeof window !== "undefined" ? window : globalThis);
