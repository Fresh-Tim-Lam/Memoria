/**
 * Memoria 多层次图谱 —— 统一呈现场景 `RenderScene` / `RenderNode`（task-391）。
 *
 * 人的裁决（背景）：旧实现在「双位置表」/「辅助位置表」/「组中心」/
 * `_pickNode` / `force extraBodies` / draw 分支里各写一套 KP、折叠簇、背景幽灵的
 * 位置、命中、力与绘制逻辑 —— 不是真正多态。本模块是**唯一节点与位置事实源**：
 *
 *   - 所有节点（KP / 折叠簇 / 背景幽灵）都是同一个 `RenderNode` 类；
 *   - 位置 / 速度 / pin 只存在 `RenderScene.nodes`（Map<id, RenderNode>）里；
 *   - 命中（pick）、拖拽（beginDrag/dragTo/endDrag）、力循环（stepForce）、
 *     绘制（draw）都只有**一个入口**，按 `drawKind` 选择绘制策略（策略注入）。
 *
 * 边界：本模块**不认识 VM 语义**（不校验 presence / 不算簇 / 不裁剪）。
 * VM 仍是 kp/cluster 纯净输入；presentation（组/名字/degree）与 background
 * 幽灵由 Renderer 投影成 spec 后交给 `sync()`。本模块也不依赖 DOM/Canvas 实现，
 * `draw(ctx, view)` 只调用注入的 painter。
 */
(function (global) {
  "use strict";

  const TAU = Math.PI * 2;

  /** 力的默认参数（Renderer 会传入自己的 FORCE，保证数值口径不漂移）。 */
  const DEFAULT_FORCE = Object.freeze({
    repulsion: 5200,
    linkDistance: 96,
    linkStrength: 0.22,
    centerStrength: 0.008,
    collisionPad: 10,
    velocityDecay: 0.82,
    alphaMin: 0.012,
    alphaDecay: 0.955,
    maxVelocity: 30,
    forceScale: 0.14,
  });

  const EMPTY_SET = Object.freeze(new Set());

  function num(value, fallback) {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  /**
   * 单个可渲染节点：几何/速度/pin/命中/受力/绘制都由自己承担。
   * `drawKind` 决定绘制策略（kp / cluster / group / ghost），策略由 Renderer 注入，
   * 因此绘制分支不再散落在 draw 里，而是节点多态的一部分。
   */
  class RenderNode {
    constructor(spec = {}) {
      this.id = String(spec.id || "");
      this.kind = spec.kind || "kp";
      this.drawKind = spec.drawKind || this.kind;
      this.shape = spec.shape || (this.kind === "kp" ? "circle" : "hexagon");
      this.layer = spec.layer || "foreground";
      this.hitPolicy = spec.hitPolicy || "select";
      this.x = num(spec.x, 0);
      this.y = num(spec.y, 0);
      this.vx = 0;
      this.vy = 0;
      this.radius = num(spec.radius, 6) > 0 ? num(spec.radius, 6) : 6;
      this.label = String(spec.label == null ? "" : spec.label);
      this.group = spec.group || null;
      this.data = spec.data || null;
      this.fixed = spec.fixed === true;
      this.anchor = this.fixed ? { x: this.x, y: this.y } : null;
      this._fx = 0;
      this._fy = 0;
    }

    get position() {
      return { x: this.x, y: this.y };
    }

    /** 唯一位置写入口（拖拽 / 布局 / 快照恢复都走这里）。 */
    moveTo(x, y) {
      if (Number.isFinite(Number(x))) this.x = Number(x);
      if (Number.isFinite(Number(y))) this.y = Number(y);
      return this;
    }

    /** 钉住（拖拽入口 / 谱系锚点）：固定后力循环不再移动它。 */
    pin(anchor) {
      if (anchor && Number.isFinite(Number(anchor.x)) && Number.isFinite(Number(anchor.y))) {
        this.moveTo(anchor.x, anchor.y);
      }
      this.fixed = true;
      this.anchor = { x: this.x, y: this.y };
      this.vx = 0;
      this.vy = 0;
      this._fx = 0;
      this._fy = 0;
      return this;
    }

    release() {
      this.fixed = false;
      this.anchor = null;
      return this;
    }

    /** 统一命中判定（所有节点同一策略；slack 默认 6px 与原实现一致）。 */
    hitTest(x, y, slack) {
      if (!Number.isFinite(this.x) || !Number.isFinite(this.y)) return false;
      const pad = slack == null ? 6 : Math.max(0, num(slack, 0));
      return Math.hypot(x - this.x, y - this.y) <= this.radius + pad;
    }

    /** 累积一帧外力（力循环里所有节点用同一入口）。 */
    applyForce(fx, fy) {
      this._fx += num(fx, 0);
      this._fy += num(fy, 0);
      return this;
    }

    clearForce() {
      this._fx = 0;
      this._fy = 0;
      return this;
    }

    /**
     * 把累积力积分为速度并移动；返回本帧位移（px）。
     * 数值口径与原 `stepForceState` 逐项一致（clamp 在 [pad, size-pad]）。
     */
    integrate(env = {}) {
      if (this.fixed) {
        this.vx = 0;
        this.vy = 0;
        this.clearForce();
        return 0;
      }
      const force = env.force || DEFAULT_FORCE;
      const alpha = num(env.alpha, 1);
      const scale = num(force.forceScale, DEFAULT_FORCE.forceScale);
      const decay = num(force.velocityDecay, DEFAULT_FORCE.velocityDecay);
      const maxV = num(force.maxVelocity, DEFAULT_FORCE.maxVelocity);
      const pad = Math.max(0, num(env.pad, 0));
      // task-391 rev29：顶部预留图谱 chrome（toolbar/drillbar）高度，避免节点被覆盖后不可点。
      const padTop = Math.max(pad, Math.max(0, num(env.padTop, pad)));
      const width = num(env.width, 0);
      const height = num(env.height, 0);
      let nvx = clamp((this.vx + this._fx * alpha * scale) * decay, -maxV, maxV);
      let nvy = clamp((this.vy + this._fy * alpha * scale) * decay, -maxV, maxV);
      this.vx = nvx;
      this.vy = nvy;
      this.clearForce();
      if (width > pad * 2) this.x = clamp(this.x + nvx, pad, width - pad);
      else this.x += nvx;
      if (height > pad + padTop) this.y = clamp(this.y + nvy, padTop, height - pad);
      else this.y += nvy;
      return Math.hypot(nvx, nvy);
    }

    /** 绘制唯一入口：按 drawKind 找注入策略（未注册策略不画，但由场景统计暴露）。 */
    draw(ctx, view) {
      const painters = view && view.painters;
      const paint = painters ? painters[this.drawKind] : null;
      if (typeof paint !== "function") return false;
      paint(ctx, this, view);
      return true;
    }

    snapshot() {
      return { x: this.x, y: this.y, vx: this.vx, vy: this.vy, fixed: this.fixed };
    }
  }

  /**
   * 唯一节点/位置事实源。`nodes` 是**唯一**存储；positions 只作为派生快照出现。
   */
  class RenderScene {
    constructor(options = {}) {
      this.nodes = new Map();
      this.painters = options.painters || {};
      this.force = Object.freeze({ ...DEFAULT_FORCE, ...(options.force || {}) });
      this._order = [];
      this._pendingPositions = new Map();
      this._syncStats = { created: 0, updated: 0, removed: 0, total: 0 };
    }

    setPainters(painters) {
      this.painters = painters || {};
      return this;
    }

    size() {
      return this.nodes.size;
    }

    get(id) {
      return this.nodes.get(String(id)) || null;
    }

    has(id) {
      return this.nodes.has(String(id));
    }

    /** 按绘制顺序（底→顶）返回节点数组；对外是快照副本。 */
    values() {
      return this._order.map((id) => this.nodes.get(id)).filter(Boolean);
    }

    clear() {
      this.nodes.clear();
      this._order = [];
      this._pendingPositions.clear();
      return this;
    }

    /** 未建节点前先登记的布局位置（app.js 首屏网格 / 快照恢复共享同一入口）。 */
    applyPositions(positions) {
      const entries = positions instanceof Map ? positions : new Map(Object.entries(positions || {}));
      for (const [id, p] of entries) {
        const key = String(id);
        const node = this.nodes.get(key);
        if (node) node.moveTo(p && p.x, p && p.y);
        else this._pendingPositions.set(key, { x: num(p && p.x, 0), y: num(p && p.y, 0) });
      }
      return this;
    }

    snapshotPositions() {
      const out = [];
      for (const node of this.nodes.values()) out.push([node.id, { x: node.x, y: node.y }]);
      return out;
    }

    restorePositions(positions) {
      for (const [id, p] of positions || []) {
        const key = String(id);
        const node = this.nodes.get(key);
        if (node) node.moveTo(p && p.x, p && p.y);
        else this._pendingPositions.set(key, { x: num(p && p.x, 0), y: num(p && p.y, 0) });
      }
      return this;
    }

    /** 组成员几何中心（折叠簇初始位置；仅读 RenderScene，不读别的 map）。 */
    groupCenter(memberIds) {
      let sx = 0;
      let sy = 0;
      let n = 0;
      for (const id of memberIds || []) {
        const node = this.nodes.get(String(id));
        if (!node) continue;
        sx += node.x;
        sy += node.y;
        n += 1;
      }
      return n ? { x: sx / n, y: sy / n } : null;
    }

    /** 首同步时成员节点尚未落 Map：成员位置可从「已有节点 → layout → 待建位置」解析。 */
    _resolvePosition(id) {
      const key = String(id);
      const node = this.nodes.get(key);
      if (node) return node;
      const layout = this._syncLayoutPositions;
      if (layout && layout.has(key)) return layout.get(key);
      return this._pendingPositions.get(key) || null;
    }

    /**
     * 同步呈现节点集合。所有节点来自同一 spec 列表，经同一处 reconcile 进 `nodes`；
     * 已存在的节点保留位置/速度/pin（会话内保位），消失的节点被移除。
     *
     * input:
     *   vm                 VM（只读；只取 nodes[].id 与 presence）
     *   groups             Presentation-only 组（文件/section）
     *   collapsedGroups    Set<group_id>（折叠组投影成 cluster 节点）
     *   hiddenIds          Set<node_id>（折叠组成员不建节点）
     *   layout             { positions: Map<id,{x,y}>, radiusById: Map<id,number> }
     *   background         背景幽灵 { targetId, x, y, radius, label }
     *   labelOf/radiusOf   Renderer 注入的视觉映射
     *   hasCollapsedAncestor(groupId) 多级组支持
     */
    sync(input = {}) {
      const vm = input.vm || { nodes: [] };
      const groups = Array.isArray(input.groups) ? input.groups : [];
      const collapsed = input.collapsedGroups instanceof Set
        ? input.collapsedGroups
        : new Set(input.collapsedGroups || []);
      const hidden = input.hiddenIds instanceof Set ? input.hiddenIds : new Set(input.hiddenIds || []);
      const layout = input.layout || null;
      const layoutPositions = layout && layout.positions instanceof Map ? layout.positions : null;
      const layoutRadii = layout && layout.radiusById instanceof Map ? layout.radiusById : null;
      const labelOf = typeof input.labelOf === "function" ? input.labelOf : (node) => node.label || node.id;
      const radiusOf = typeof input.radiusOf === "function" ? input.radiusOf : () => 6;
      this._syncLayoutPositions = layoutPositions;
      const specs = [];

      for (const node of vm.nodes || []) {
        if (node.presence && node.presence !== "shown") continue;
        const id = String(node.id);
        if (hidden.has(id)) continue;
        specs.push({
          id, kind: node.kind || "kp", drawKind: node.kind === "cluster" ? "cluster" : "kp",
          shape: node.kind === "cluster" ? "hexagon" : "circle",
          layer: "foreground", hitPolicy: "select",
          label: labelOf(node), radius: num(radiusOf(node), 6), data: node,
        });
      }

      for (const group of groups) {
        const groupId = String(group.group_id || "");
        if (!groupId || !collapsed.has(groupId)) continue;
        if (typeof input.hasCollapsedAncestor === "function" && input.hasCollapsedAncestor(groupId)) continue;
        const id = `group:${groupId}`;
        const members = (group.member_ids || []).map(String);
        let center = this.groupCenter(members);
        if (!center) {
          let sx = 0;
          let sy = 0;
          let n = 0;
          for (const memberId of members) {
            const p = this._resolvePosition(memberId);
            if (!p) continue;
            sx += num(p.x, 0);
            sy += num(p.y, 0);
            n += 1;
          }
          if (n) center = { x: sx / n, y: sy / n };
        }
        // task-391 rev26：空容器（无成员）或固定排布组可用 presentation 初值 x/y；
        // 首帧落位后仍进入同一力循环，可被力/拖拽移动（仅作为初始 anchor，不是第二份位置存储）。
        if (!center) {
          const gx = num(group.x, NaN);
          const gy = num(group.y, NaN);
          if (Number.isFinite(gx) && Number.isFinite(gy)) center = { x: gx, y: gy };
        }
        if (!center && !this.nodes.has(id)) continue;
        specs.push({
          id, kind: "cluster", drawKind: "group", shape: "hexagon", layer: "foreground",
          hitPolicy: "drill", label: input.groupLabelOf ? input.groupLabelOf(group) : groupId,
          radius: num(radiusOf({ kind: "cluster", group }), 12), group,
          x: center ? center.x : undefined, y: center ? center.y : undefined,
        });
      }

      const bg = input.background;
      if (bg) {
        const ghostId = "ghost:A";
        const target = bg.targetId ? this.nodes.get(String(bg.targetId)) : null;
        let gx = num(bg.x, NaN);
        let gy = num(bg.y, NaN);
        if (!Number.isFinite(gx) || !Number.isFinite(gy)) {
          if (!target) { gx = NaN; gy = NaN; }
          else { gx = target.x - 120; gy = target.y - 100; }
        }
        if (Number.isFinite(gx) && Number.isFinite(gy)) {
          if (target && !this.nodes.has(ghostId)) {
            const radius = num(bg.radius, 20);
            const minDist = radius + (target.radius || 8) + 36;
            if (Math.hypot(gx - target.x, gy - target.y) < minDist) {
              gx = target.x - 120;
              gy = target.y - 100;
            }
          }
          specs.push({
            id: ghostId, kind: "ghost", drawKind: "ghost", shape: "hexagon", layer: "background",
            hitPolicy: "return", label: bg.label, radius: num(bg.radius, 20), data: bg,
            x: gx, y: gy,
          });
        }
      }

      // task-391 rev29：上一站全视图背景化快照（presentation-only layer）。
      // 每项建成 RenderScene 的 background 层节点：不可命中/不参与力；位置/标签/形状随快照冻结。
      const backgroundNodes = input.backgroundNodes;
      if (Array.isArray(backgroundNodes)) {
        for (const item of backgroundNodes) {
          if (!item) continue;
          const rawId = String(item.id || "");
          const bx = num(item.x, NaN);
          const by = num(item.y, NaN);
          if (!rawId || !Number.isFinite(bx) || !Number.isFinite(by)) continue;
          const kind = item.kind === "cluster" ? "cluster" : "kp";
          specs.push({
            id: `bg:${rawId}`, kind, drawKind: "bgGhost",
            shape: item.shape === "hexagon" || kind === "cluster" ? "hexagon" : "circle",
            layer: "background", hitPolicy: "none",
            label: String(item.label || ""), radius: num(item.radius, kind === "cluster" ? 14 : 7),
            data: item, x: bx, y: by,
          });
        }
      }

      const keep = new Set(specs.map((s) => s.id));
      let created = 0;
      let updated = 0;
      let removed = 0;
      for (const id of [...this.nodes.keys()]) {
        if (keep.has(id)) continue;
        this.nodes.delete(id);
        removed += 1;
      }
      const order = [];
      for (const spec of specs) {
        let node = this.nodes.get(spec.id);
        if (node) {
          node.kind = spec.kind;
          node.drawKind = spec.drawKind;
          node.shape = spec.shape;
          node.layer = spec.layer;
          node.hitPolicy = spec.hitPolicy;
          node.radius = spec.radius;
          node.label = spec.label;
          node.group = spec.group || null;
          node.data = spec.data || null;
          updated += 1;
        } else {
          const pending = this._pendingPositions.get(spec.id);
          const fromLayout = layoutPositions ? layoutPositions.get(spec.id) : null;
          const x = pending ? pending.x : (fromLayout ? fromLayout.x : spec.x);
          const y = pending ? pending.y : (fromLayout ? fromLayout.y : spec.y);
          const radius = layoutRadii && layoutRadii.has(spec.id) ? num(layoutRadii.get(spec.id), spec.radius) : spec.radius;
          node = new RenderNode({ ...spec, x, y, radius });
          this.nodes.set(spec.id, node);
          this._pendingPositions.delete(spec.id);
          created += 1;
        }
        order.push(spec.id);
      }
      this._order = order;
      this._syncStats = { created, updated, removed, total: this.nodes.size };
      this._syncLayoutPositions = null;
      return { ...this._syncStats, order: order.slice() };
    }

    /**
     * 唯一命中入口：所有节点同一 hitTest；按绘制顺序逆序（顶层优先）返回节点。
     * 返回 RenderNode（不是裸 position），调用方再用 `hitPolicy` 分派语义。
     */
    pick(x, y) {
      for (let i = this._order.length - 1; i >= 0; i -= 1) {
        const node = this.nodes.get(this._order[i]);
        if (!node) continue;
        // task-391 rev29：背景快照层只是展示（hitPolicy=none，不可选中/不可拖），不参与命中；
        // 入口幽灵 A（background 层 + hitPolicy=return）仍可点击返回/拖拽，保持旧回归。
        if (node.hitPolicy === "none") continue;
        if (node.hitTest(x, y)) return node;
      }
      return null;
    }

    /** 拖拽唯一入口：pin 节点（任何 kind 走同一条路）。 */
    beginDrag(nodeOrId) {
      const node = nodeOrId instanceof RenderNode ? nodeOrId : this.get(nodeOrId);
      if (!node) return null;
      node.pin();
      return node;
    }

    dragTo(id, x, y) {
      const node = this.get(id);
      if (!node) return null;
      node.moveTo(x, y);
      return node;
    }

    endDrag(id) {
      const node = this.get(id);
      if (!node) return null;
      node.release();
      return node;
    }

    /** 力的默认状态（warmup / rAF 动画共用同一份状态结构）。 */
    buildForceState(options = {}) {
      const width = num(options.width, 0);
      const height = num(options.height, 0);
      const pinned = new Set(options.pinned || []);
      const focusId = options.focusId ? String(options.focusId) : null;
      const pinFocusCenter = options.pinFocusCenter === true;
      if (focusId && pinFocusCenter) {
        const focus = this.get(focusId);
        if (focus) {
          focus.moveTo(width / 2, height / 2);
          pinned.add(focusId);
        }
      }
      let maxRadius = 0;
      for (const node of this.nodes.values()) maxRadius = Math.max(maxRadius, node.radius);
      return {
        alpha: num(options.alpha, 1),
        links: options.links || [],
        pinned,
        focusId: focusId && this.has(focusId) && !pinned.has(focusId) ? focusId : null,
        width,
        height,
        pad: Math.max(24, maxRadius + 8),
        // 顶部 chrome（toolbar/drillbar ~48px）——节点不得漂到其下不可点
        padTop: Math.max(52, maxRadius + 8),
        ticks: 0,
        maxDisp: 0,
      };
    }

    /**
     * 唯一力循环（每帧一次）：排斥 + 碰撞 + 边吸引 + 向心 + focus 回中，
     * 对所有节点（KP / 折叠簇 / 背景幽灵）一视同仁、双向作用。
     * 返回本帧最大位移（px），用于 teleport/收敛证据。
     */
    stepForce(state = {}) {
      const force = this.force;
      // task-391 rev38：background 快照层与前景节点/ghost A 同池参与力（互相推挤、随拖拽响应），
      // 但仍不可 pick/拖拽（hitPolicy=none 只影响命中，不再排除力）。
      const ids = [...this.nodes.keys()].sort();
      const count = ids.length;
      if (!count) return 0;
      const alpha = num(state.alpha, 1);
      const pinned = state.pinned instanceof Set ? state.pinned : EMPTY_SET;
      const width = num(state.width, 0);
      const height = num(state.height, 0);
      const pad = num(state.pad, 24);
      const cx = width / 2;
      const cy = height / 2;
      const nodes = ids.map((id) => this.nodes.get(id));
      const isPinned = (node) => node.fixed || pinned.has(node.id);

      // ① 两两排斥 + 圆碰撞（所有节点同池）
      for (let i = 0; i < count; i += 1) {
        const a = nodes[i];
        for (let j = i + 1; j < count; j += 1) {
          const b = nodes[j];
          let dx = b.x - a.x;
          let dy = b.y - a.y;
          let dist = Math.hypot(dx, dy);
          if (dist < 1e-6) {
            dx = (a.id < b.id ? 1 : -1) * 0.5;
            dy = 0.5;
            dist = Math.hypot(dx, dy);
          }
          const ux = dx / dist;
          const uy = dy / dist;
          const minDist = a.radius + b.radius + force.collisionPad;
          if (dist < minDist) {
            const push = (minDist - dist) * 0.5;
            if (!isPinned(a)) a.applyForce(-ux * push, -uy * push);
            if (!isPinned(b)) b.applyForce(ux * push, uy * push);
          }
          const rep = force.repulsion / Math.max(64, dist * dist);
          if (!isPinned(a)) a.applyForce(-ux * rep, -uy * rep);
          if (!isPinned(b)) b.applyForce(ux * rep, uy * rep);
        }
      }

      // ② 边吸引（只作用于 kp 边端点；簇/幽灵没有 VM 边）
      for (const link of state.links || []) {
        const a = this.nodes.get(String(link.source));
        const b = this.nodes.get(String(link.target));
        if (!a || !b) continue;
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let dist = Math.hypot(dx, dy);
        if (dist < 1e-6) { dx = 1; dy = 0; dist = 1; }
        const ux = dx / dist;
        const uy = dy / dist;
        const target = num(link.distance, force.linkDistance);
        const strength = num(link.strength, force.linkStrength);
        const f = (dist - target) * strength * alpha;
        if (!isPinned(a)) a.applyForce(ux * f, uy * f);
        if (!isPinned(b)) b.applyForce(-ux * f, -uy * f);
      }

      // ③ 向心 / focus 回中 + 积分（同一循环，无第二套力实现）
      let maxDisp = 0;
      for (const id of ids) {
        const node = this.nodes.get(id);
        if (isPinned(node)) {
          node.vx = 0;
          node.vy = 0;
          node.clearForce();
          continue;
        }
        node.applyForce((cx - node.x) * force.centerStrength * alpha, (cy - node.y) * force.centerStrength * alpha);
        if (state.focusId === id) {
          node.applyForce((cx - node.x) * 0.22 * alpha, (cy - node.y) * 0.22 * alpha);
        }
        const step = node.integrate({
          alpha, force, width, height, pad,
        });
        if (step > maxDisp) maxDisp = step;
      }
      state.alpha = Math.max(force.alphaMin, alpha * force.alphaDecay);
      state.ticks = num(state.ticks, 0) + 1;
      state.maxDisp = maxDisp;
      return maxDisp;
    }

    /** 同步 warmup（无 rAF 环境/初始布局）；复用同一 stepForce。 */
    relax(links, ticks, options = {}) {
      const state = this.buildForceState({ ...options, links: links || [] });
      const total = Math.max(1, num(ticks, 140));
      for (let i = 0; i < total; i += 1) this.stepForce(state);
      return state;
    }

    /** 唯一节点绘制入口：按绘制顺序、按 layer 过滤，逐个节点多态绘制。 */
    draw(ctx, view, layer) {
      const v = view || {};
      let painted = 0;
      for (const id of this._order) {
        const node = this.nodes.get(id);
        if (!node) continue;
        if (layer && node.layer !== layer) continue;
        if (node.draw(ctx, v)) painted += 1;
      }
      return painted;
    }
  }

  const api = { RenderNode, RenderScene, DEFAULT_FORCE, TAU };
  global.MemoriaGraphRenderScene = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
