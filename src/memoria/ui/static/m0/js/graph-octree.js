/**
 * 3D 八叉树：3D 图谱射线拾取候选筛选
 */
(function (global) {
  "use strict";

  const MIN_OCTREE_NODES = 40;

  function boundsEmpty() {
    return {
      minX: Infinity,
      minY: Infinity,
      minZ: Infinity,
      maxX: -Infinity,
      maxY: -Infinity,
      maxZ: -Infinity,
    };
  }

  function boundsExpand(b, x, y, z, r) {
    b.minX = Math.min(b.minX, x - r);
    b.minY = Math.min(b.minY, y - r);
    b.minZ = Math.min(b.minZ, z - r);
    b.maxX = Math.max(b.maxX, x + r);
    b.maxY = Math.max(b.maxY, y + r);
    b.maxZ = Math.max(b.maxZ, z + r);
  }

  function boundsFromEntries(entries, pad) {
    const b = boundsEmpty();
    for (const e of entries) boundsExpand(b, e.x, e.y, e.z, e.radius);
    if (!Number.isFinite(b.minX)) {
      return { minX: -1, minY: -1, minZ: -1, maxX: 1, maxY: 1, maxZ: 1 };
    }
    const p = pad || 0;
    b.minX -= p;
    b.minY -= p;
    b.minZ -= p;
    b.maxX += p;
    b.maxY += p;
    b.maxZ += p;
    return b;
  }

  function rayHitsAabb(ox, oy, oz, invDx, invDy, invDz, b) {
    let t1 = (b.minX - ox) * invDx;
    let t2 = (b.maxX - ox) * invDx;
    let t3 = (b.minY - oy) * invDy;
    let t4 = (b.maxY - oy) * invDy;
    let t5 = (b.minZ - oz) * invDz;
    let t6 = (b.maxZ - oz) * invDz;
    let tmin = Math.max(
      Math.max(Math.min(t1, t2), Math.min(t3, t4)),
      Math.min(t5, t6)
    );
    let tmax = Math.min(
      Math.min(Math.max(t1, t2), Math.max(t3, t4)),
      Math.max(t5, t6)
    );
    return tmax >= Math.max(tmin, 0);
  }

  function raySphereT(ox, oy, oz, dx, dy, dz, x, y, z, r) {
    const lx = x - ox;
    const ly = y - oy;
    const lz = z - oz;
    const tca = lx * dx + ly * dy + lz * dz;
    if (tca < 0) return null;
    const d2 = lx * lx + ly * ly + lz * lz - tca * tca;
    const r2 = r * r;
    if (d2 > r2) return null;
    const thc = Math.sqrt(r2 - d2);
    return tca - thc;
  }

  class MemoriaGraphOctree {
    constructor(options = {}) {
      this.maxDepth = options.maxDepth ?? 8;
      this.maxObjects = options.maxObjects ?? 10;
      this.minCell = options.minCell ?? 6;
      this.root = null;
    }

    build(entries) {
      if (!entries.length) {
        this.root = null;
        return;
      }
      const bounds = boundsFromEntries(entries, this.minCell);
      this.root = { bounds, depth: 0, objects: [], children: null };
      for (const e of entries) this._insert(this.root, e);
    }

    _insert(node, obj) {
      if (!this._objInBounds(obj, node.bounds)) return;
      if (!node.children && (node.objects.length < this.maxObjects || node.depth >= this.maxDepth)) {
        node.objects.push(obj);
        return;
      }
      if (!node.children) this._split(node);
      for (const child of node.children) this._insert(child, obj);
    }

    _objInBounds(obj, b) {
      return (
        obj.x + obj.radius >= b.minX &&
        obj.x - obj.radius <= b.maxX &&
        obj.y + obj.radius >= b.minY &&
        obj.y - obj.radius <= b.maxY &&
        obj.z + obj.radius >= b.minZ &&
        obj.z - obj.radius <= b.maxZ
      );
    }

    _split(node) {
      const b = node.bounds;
      const mx = (b.minX + b.maxX) * 0.5;
      const my = (b.minY + b.maxY) * 0.5;
      const mz = (b.minZ + b.maxZ) * 0.5;
      const d = node.depth + 1;
      node.children = [
        { bounds: { minX: b.minX, minY: b.minY, minZ: b.minZ, maxX: mx, maxY: my, maxZ: mz }, depth: d, objects: [], children: null },
        { bounds: { minX: mx, minY: b.minY, minZ: b.minZ, maxX: b.maxX, maxY: my, maxZ: mz }, depth: d, objects: [], children: null },
        { bounds: { minX: b.minX, minY: my, minZ: b.minZ, maxX: mx, maxY: b.maxY, maxZ: mz }, depth: d, objects: [], children: null },
        { bounds: { minX: mx, minY: my, minZ: b.minZ, maxX: b.maxX, maxY: b.maxY, maxZ: mz }, depth: d, objects: [], children: null },
        { bounds: { minX: b.minX, minY: b.minY, minZ: mz, maxX: mx, maxY: my, maxZ: b.maxZ }, depth: d, objects: [], children: null },
        { bounds: { minX: mx, minY: b.minY, minZ: mz, maxX: b.maxX, maxY: my, maxZ: b.maxZ }, depth: d, objects: [], children: null },
        { bounds: { minX: b.minX, minY: my, minZ: mz, maxX: mx, maxY: b.maxY, maxZ: b.maxZ }, depth: d, objects: [], children: null },
        { bounds: { minX: mx, minY: my, minZ: mz, maxX: b.maxX, maxY: b.maxY, maxZ: b.maxZ }, depth: d, objects: [], children: null },
      ];
      const objs = node.objects;
      node.objects = [];
      for (const o of objs) {
        for (const child of node.children) this._insert(child, o);
      }
    }

    queryRay(origin, direction, out) {
      if (!this.root) return out;
      const ox = origin.x;
      const oy = origin.y;
      const oz = origin.z;
      const dx = direction.x;
      const dy = direction.y;
      const dz = direction.z;
      const len = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
      const ndx = dx / len;
      const ndy = dy / len;
      const ndz = dz / len;
      const invDx = ndx !== 0 ? 1 / ndx : Infinity;
      const invDy = ndy !== 0 ? 1 / ndy : Infinity;
      const invDz = ndz !== 0 ? 1 / ndz : Infinity;
      const hits = [];
      this._queryRayNode(this.root, ox, oy, oz, ndx, ndy, ndz, invDx, invDy, invDz, hits);
      hits.sort((a, b) => a.t - b.t);
      for (const h of hits) out.push(h.id);
      return out;
    }

    _queryRayNode(node, ox, oy, oz, dx, dy, dz, invDx, invDy, invDz, hits) {
      if (!rayHitsAabb(ox, oy, oz, invDx, invDy, invDz, node.bounds)) return;
      for (const obj of node.objects) {
        const t = raySphereT(ox, oy, oz, dx, dy, dz, obj.x, obj.y, obj.z, obj.radius);
        if (t != null) hits.push({ id: obj.id, t });
      }
      if (node.children) {
        for (const child of node.children) {
          this._queryRayNode(child, ox, oy, oz, dx, dy, dz, invDx, invDy, invDz, hits);
        }
      }
    }
  }

  global.MemoriaGraphOctree = MemoriaGraphOctree;
  global.MemoriaGraphOctree.MIN_NODES = MIN_OCTREE_NODES;
})(typeof window !== "undefined" ? window : globalThis);
