/**
 * Barnes-Hut 近似排斥（2D 四叉树 / 3D 八叉树）
 *
 * 为什么需要：排斥是全对全 O(N²)，实测占单 tick 的 **98.4–99.9%**
 * （见 docs/design/graph-benchmark.md §5.4：计算一对 ≈51–70ns、单连通 5000 节点单 tick 640ms）。
 * BH 把"远处的节点团用一个质心近似"，使每个节点的受力计算降到 O(log N)。
 *
 * 分组语义**必须与 exact 路径的 `skipPairRepulsion` 一致**，否则会改动既有布局：
 *   · 不跨群排斥时（`groupMode === "all"` 且非 scatter）→ **每个群各建一棵树**，跨群对被自然排除；
 *   · 跨群排斥时（scatter / 单群视图）→ 建一棵全局树；
 *   · 拖拽中的节点与**任意**节点互斥（含跨群）：额外建"拖拽节点"单体树让其它节点遍历，
 *     并让拖拽节点遍历别的树 —— 与 exact 语义等价（O(N) 额外开销）。
 *
 * 与 exact 路径的一处**有意差异**：命中"两节点几乎重合"时，这里用 `distanceMin` 下限夹住距离，
 * 不再像旧版那样注入 `Math.random()` 抖动 —— 目的①消掉数值爆炸（实测曾出现边长 2.13e9），
 * ②让布局**确定性可复现**。代价是重合点之间不再自行分离（剖面实测该情形 ≈5 次 / 15 亿次迭代，可忽略；
 * 真出现"崩成一坨"由基准里的 minNodeDist 哨兵兜住）。
 *
 * θ 默认 0.9（标准值，力误差 <1%）。
 */
(function (global) {
  "use strict";

  /** 深度上限：坐标完全重合的点无法再细分，到此退化为"按质心聚合" */
  const MAX_DEPTH = 24;
  const DEFAULT_THETA = 0.9;
  const DEFAULT_DISTANCE_MIN = 1;

  function makeCell(x, y, z, half) {
    return { x, y, z, half, mass: 0, mx: 0, my: 0, mz: 0, child: null, index: -1 };
  }

  function buildRoot(nodes, list, dim) {
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const i of list) {
      const n = nodes[i];
      if (n.x < minX) minX = n.x;
      if (n.x > maxX) maxX = n.x;
      if (n.y < minY) minY = n.y;
      if (n.y > maxY) maxY = n.y;
    }
    const half = Math.max(maxX - minX, maxY - minY) / 2 || 1;
    // 半边长再放大一点点，保证边界上的点落在树内；z 中心取 0（2D 恒为 0）
    return makeCell((minX + maxX) / 2, (minY + maxY) / 2, 0, half * 1.0001);
  }

  function childIndexFor(nodes, i, cell, dim) {
    const n = nodes[i];
    let idx = 0;
    if (n.x >= cell.x) idx |= 1;
    if (n.y >= cell.y) idx |= 2;
    if (dim === 3 && (n.z || 0) >= cell.z) idx |= 4;
    return idx;
  }

  function split(cell, dim) {
    const h = cell.half / 2;
    const count = dim === 3 ? 8 : 4;
    const kids = new Array(count);
    for (let k = 0; k < count; k++) {
      const cz = dim === 3 && (k & 4) ? cell.z + h : cell.z - h;
      kids[k] = makeCell(
        cell.x + (k & 1 ? h : -h),
        cell.y + (k & 2 ? h : -h),
        dim === 3 ? cz : 0,
        h
      );
    }
    cell.child = kids;
  }

  function insert(cell, nodes, i, depth, dim, counter) {
    const n = nodes[i];
    const nx = n.x;
    const ny = n.y;
    const nz = dim === 3 ? n.z || 0 : 0;
    const m = cell.mass;
    cell.mass = m + 1;
    cell.mx = (cell.mx * m + nx) / (m + 1);
    cell.my = (cell.my * m + ny) / (m + 1);
    cell.mz = (cell.mz * m + nz) / (m + 1);

    if (cell.child === null && cell.index === -1 && m === 0) {
      cell.index = i; // 空叶：直接挂上
      return;
    }
    if (cell.child === null) {
      if (depth >= MAX_DEPTH) {
        cell.index = -1; // 深度上限：不再细分，当作聚合体
        return;
      }
      split(cell, dim);
      if (counter) counter.cells += cell.child.length;
      const prev = cell.index;
      cell.index = -1;
      if (prev >= 0) {
        insert(cell.child[childIndexFor(nodes, prev, cell, dim)], nodes, prev, depth + 1, dim, counter);
      }
    }
    insert(cell.child[childIndexFor(nodes, i, cell, dim)], nodes, i, depth + 1, dim, counter);
  }

  function buildTree(nodes, list, dim, counter) {
    const root = buildRoot(nodes, list, dim);
    if (counter) counter.cells += 1;
    for (const i of list) insert(root, nodes, i, 0, dim, counter);
    return root;
  }

  function applyAggregate(node, mass, dx, dy, dz, dist2, dim, rep, dMin2, stat) {
    if (stat) stat.interactions += 1;
    const d2 = dist2 < dMin2 ? dMin2 : dist2;
    const d = Math.sqrt(d2);
    const f = (rep * mass) / d2;
    // d2 被下限夹住、而 dx 恰为 0 时方向未定义 → 该方向不施力（确定性；旧的随机抖动已移除）
    node.vx -= (dx / d) * f;
    node.vy -= (dy / d) * f;
    if (dim === 3) node.vz -= (dz / d) * f;
  }

  /**
   * 把 tree 对节点 i 的排斥力累加到 i 的速度上。
   * `inside`（i 落在该格内）时必须继续下钻 —— 否则会把 i 自己也当作"远处的质量"算进去。
   */
  function applyOn(cell, nodes, i, dim, rep, theta2, dMin2, stat) {
    if (cell.mass === 0) return;
    if (cell.child === null && cell.index === i) return; // 自己

    const n = nodes[i];
    const nx = n.x;
    const ny = n.y;
    const nz = dim === 3 ? n.z || 0 : 0;
    const inside =
      Math.abs(nx - cell.x) <= cell.half &&
      Math.abs(ny - cell.y) <= cell.half &&
      (dim !== 3 || Math.abs(nz - cell.z) <= cell.half);

    const dx = cell.mx - nx;
    const dy = cell.my - ny;
    const dz = dim === 3 ? cell.mz - nz : 0;
    const dist2 = dx * dx + dy * dy + (dim === 3 ? dz * dz : 0);
    const size = cell.half * 2;

    if (!inside && (cell.child === null || size * size < theta2 * dist2)) {
      applyAggregate(n, cell.mass, dx, dy, dz, dist2, dim, rep, dMin2, stat);
      return;
    }
    if (cell.child !== null) {
      const kids = cell.child;
      for (let k = 0; k < kids.length; k++) {
        applyOn(kids[k], nodes, i, dim, rep, theta2, dMin2, stat);
      }
      return;
    }
    // 退化叶（深度上限处多体共格）且 i 在里面：扣掉自身那一份质量近似
    if (cell.mass > 1) {
      applyAggregate(n, cell.mass - 1, dx, dy, dz, dist2, dim, rep, dMin2, stat);
    }
  }

  function rangeOf(n) {
    const out = new Array(n);
    for (let i = 0; i < n; i++) out[i] = i;
    return out;
  }

  /**
   * 主入口：把近似排斥力累加到各节点的 vx/vy(/vz)。
   *
   * @param {Array} nodes 节点（需 x/y(/z) 与可选 groupId）
   * @param {2|3} dim 维度
   * @param {number} rep 本 tick 的排斥强度（与 exact 路径同口径）
   * @param {number[][]|null} buckets 分桶的节点下标；null/空 = 全部节点一棵树
   * @param {{theta?:number, dragIndex?:number, dragId?:string, distanceMin?:number, collectStats?:boolean}} opts
   * @returns {{cells:number, interactions:number}|null} 诊断计数（仅 collectStats 时非空）
   */
  function applyRepulsion(nodes, dim, rep, buckets, opts) {
    const o = opts || {};
    const theta = o.theta > 0 ? o.theta : DEFAULT_THETA;
    const theta2 = theta * theta;
    const dMin = o.distanceMin > 0 ? o.distanceMin : DEFAULT_DISTANCE_MIN;
    const dMin2 = dMin * dMin;
    const stat = o.collectStats ? { cells: 0, interactions: 0 } : null;
    if (!nodes.length) return stat;

    const lists = buckets && buckets.length ? buckets : [rangeOf(nodes.length)];
    const dragIndex =
      typeof o.dragIndex === "number"
        ? o.dragIndex
        : o.dragId
          ? nodes.findIndex((x) => x.id === o.dragId)
          : -1;

    const trees = [];
    let dragBucket = -1;
    for (let b = 0; b < lists.length; b++) {
      const list = lists[b];
      if (!list.length) continue;
      if (dragIndex >= 0 && list.indexOf(dragIndex) >= 0) dragBucket = trees.length;
      const root = buildTree(nodes, list, dim, stat);
      trees.push({ list, root });
      for (const i of list) applyOn(root, nodes, i, dim, rep, theta2, dMin2, stat);
    }

    // 拖拽：拖拽节点 ↔ 任意节点（含跨群），与 exact 的 skipPairRepulsion 语义对齐
    if (dragIndex >= 0 && dragIndex < nodes.length) {
      const dragTree = buildTree(nodes, [dragIndex], dim, stat);
      for (let b = 0; b < trees.length; b++) {
        if (b === dragBucket) continue; // 本群那一份已在上面对称算过
        for (const i of trees[b].list) {
          if (i === dragIndex) continue;
          applyOn(dragTree.root, nodes, i, dim, rep, theta2, dMin2, stat);
        }
        applyOn(trees[b].root, nodes, dragIndex, dim, rep, theta2, dMin2, stat);
      }
    }
    return stat;
  }

  global.MemoriaGraphBH = {
    DEFAULT_THETA,
    DEFAULT_DISTANCE_MIN,
    applyRepulsion,
    buildTree,
  };
})(typeof self !== "undefined" ? self : typeof window !== "undefined" ? window : globalThis);
