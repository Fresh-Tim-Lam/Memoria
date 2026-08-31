/**
 * GraphEngine 3D WebGL 视图：MemoriaGraphLayout3D (x,y,z)
 */
(function (global) {
  "use strict";

  const DEFAULTS = {
    labelMode: "name_short",
    labelMaxLen: 8,
    nodeRadius: 6,
  };

  const EDGE_COLORS = global.MemoriaGraphEdgeColors || {
    contain: "#3fb950",
    reference: "#58a6ff",
    extend: "#d29922",
  };

  function hexColor(type) {
    const h = EDGE_COLORS[type] || EDGE_COLORS.reference;
    return parseInt(String(h).replace("#", ""), 16);
  }

  function displayLabelForNode(n, opts) {
    if (window.MemoriaGraphLabels) {
      return MemoriaGraphLabels.resolveNodeDisplayLabel(n, {
        labelMode: opts.labelMode,
        labelMaxLen: opts.labelMaxLen,
      });
    }
    const s = String(n.name || n.label || n.id || "").trim();
    const max = opts.labelMaxLen || 8;
    if (s.length <= max) return s;
    return s.slice(0, Math.max(1, max - 1)) + "…";
  }

  function labelColorHex(isHover, isTarget, rangeOk) {
    if (isHover) return 0xf0f6fc;
    if (isTarget) return 0x79c0ff;
    if (rangeOk === false) return 0x6e7681;
    return 0xadbac7;
  }

  /** 银河样式：按度数在暗星(0x8b949e)与亮星(0xf0f6fc)之间插值 */
  function galaxyColor3D(ratio) {
    const dim = [139, 148, 158];
    const bright = [240, 246, 252];
    const k = Math.max(0, Math.min(1, ratio));
    const r = Math.round(dim[0] + (bright[0] - dim[0]) * k);
    const g = Math.round(dim[1] + (bright[1] - dim[1]) * k);
    const b = Math.round(dim[2] + (bright[2] - dim[2]) * k);
    return (r << 16) | (g << 8) | b;
  }

  let _haloTexture = null;
  /** 共享径向渐变纹理，用于节点光晕 sprite（白色，由 SpriteMaterial.color 着色） */
  function getHaloTexture(THREE) {
    if (_haloTexture) return _haloTexture;
    const size = 128;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d");
    const g = ctx.createRadialGradient(
      size / 2,
      size / 2,
      0,
      size / 2,
      size / 2,
      size / 2
    );
    g.addColorStop(0, "rgba(255,255,255,1)");
    g.addColorStop(0.35, "rgba(255,255,255,0.55)");
    g.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, size, size);
    _haloTexture = new THREE.CanvasTexture(canvas);
    return _haloTexture;
  }

  function hexToCss(hex) {
    const h = (hex >>> 0).toString(16).padStart(6, "0").slice(-6);
    return `#${h}`;
  }

  function fillRoundRect(ctx, x, y, w, h, radius) {
    const r = Math.min(radius, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function paintNodeLabelCanvas(ctx, w, h, text, fontSize, textColor) {
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "rgba(13, 17, 23, 0.85)";
    fillRoundRect(ctx, 0, 0, w, h, 6);
    ctx.fill();
    ctx.font = `${fontSize}px system-ui, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.lineWidth = 5;
    ctx.strokeStyle = "rgba(13, 17, 23, 0.92)";
    ctx.strokeText(text, w / 2, h / 2);
    ctx.fillStyle = textColor;
    ctx.fillText(text, w / 2, h / 2);
  }

  function createNodeLabelSprite(THREE, text, nodeRadius, textColor) {
    const fontSize = 32;
    const padX = 8;
    const padY = 5;
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    ctx.font = `${fontSize}px system-ui, sans-serif`;
    const metrics = ctx.measureText(text);
    const w = Math.max(16, Math.ceil(metrics.width + padX * 2));
    const h = fontSize + padY * 2;
    canvas.width = w;
    canvas.height = h;
    paintNodeLabelCanvas(ctx, w, h, text, fontSize, textColor || "#adbac7");

    const texture = new THREE.CanvasTexture(canvas);
    texture.minFilter = THREE.LinearFilter;
    texture.magFilter = THREE.LinearFilter;
    const material = new THREE.SpriteMaterial({
      map: texture,
      transparent: true,
      depthWrite: false,
      depthTest: true,
      color: 0xffffff,
    });
    const sprite = new THREE.Sprite(material);
    const r = nodeRadius || 6;
    const unit = Math.max(0.11, r * 0.021);
    sprite.scale.set(w * unit, h * unit, 1);
    sprite.userData = {
      canvas,
      texture,
      text,
      unit,
      w,
      h,
      nodeRadius: r,
      fontSize,
      textColor: textColor || "#adbac7",
    };
    return sprite;
  }

  function updateLabelSpriteAppearance(sprite, textColor, opacity) {
    const ud = sprite.userData;
    if (!ud?.canvas || !ud.texture) return;
    paintNodeLabelCanvas(
      ud.canvas.getContext("2d"),
      ud.w,
      ud.h,
      ud.text,
      ud.fontSize || 32,
      textColor
    );
    ud.texture.needsUpdate = true;
    ud.textColor = textColor;
    sprite.material.color.setHex(0xffffff);
    sprite.material.opacity = opacity;
  }

  class GraphView3D {
    constructor(container, engine, layout, options = {}) {
      if (!global.THREE) {
        throw new Error("THREE.js 未加载");
      }
      this.THREE = global.THREE;
      this.container = container;
      this.engine = engine;
      this.layout = layout;
      this.opts = { ...DEFAULTS, ...options };
      this.active = false;
      this.hoverId = null;
      this.remoteHoverId = null;
      this.externalFocus = null;
      this._nodeMeshes = new Map();
      this._pickMeshes = new Map();
      this._pickOctree = null;
      this._pickRadius = 10;
      this._labelSprites = new Map();
      this._haloSprites = new Map();
      this._edgeLines = [];
      this._raycaster = new this.THREE.Raycaster();
      this._pointer = new this.THREE.Vector2(-999, -999);
      this._pendingRelayout = false;
      this._pulse = 0;
      this._dragPlane = new this.THREE.Plane();
      this._dragIntersect = new this.THREE.Vector3();
      this._dragging = false;
      this._dragNodeId = null;
      this._dragPendingId = null;

      this._initScene();
      if (this._webglFailed) return;
      this._onEngineLoad = () => this.resetSimulation();
      this._onLayoutReset = () => {
        this._rebuildGraph();
        this._fitCamera();
      };
      engine.on("load", this._onEngineLoad);
      layout.on("reset", this._onLayoutReset);

      this._observeResize();
      this._bindPointer();
      this.resetSimulation();
    }

    destroy() {
      this.active = false;
      this.engine.off("load", this._onEngineLoad);
      this.layout.off("reset", this._onLayoutReset);
      if (this._raf) cancelAnimationFrame(this._raf);
      if (this._resizeObs) this._resizeObs.disconnect();
      if (this._controls) this._controls.dispose();
      this._clearGraph();
      this.renderer?.dispose();
      try {
        if (this.renderer?.domElement?.parentNode === this.container) {
          this.container.removeChild(this.renderer.domElement);
        }
      } catch (_) {}
    }

    _initScene() {
      const THREE = this.THREE;
      this.scene = new THREE.Scene();
      this._syncBackground();

      const w = Math.max(1, this.container.clientWidth || 320);
      const h = Math.max(1, this.container.clientHeight || 240);
      this.camera = new THREE.PerspectiveCamera(50, w / h, 0.1, 5000);
      this.camera.position.set(0, 0, 280);

      try {
        this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
      } catch (err) {
        console.error("[GraphView3D] WebGL unavailable", err);
        this._webglFailed = true;
        return;
      }
      this._webglFailed = false;
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      this.renderer.setSize(w, h);
      this.container.innerHTML = "";
      this.container.appendChild(this.renderer.domElement);

      this.scene.add(new THREE.AmbientLight(0xffffff, 0.75));
      const dir = new THREE.DirectionalLight(0xffffff, 0.45);
      dir.position.set(120, 180, 100);
      this.scene.add(dir);

      if (THREE.OrbitControls) {
        this._controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
        this._controls.enableDamping = true;
        this._controls.dampingFactor = 0.08;
        this._applyZoomSettings();
      }

      this._edgeGroup = new THREE.Group();
      this._nodeGroup = new THREE.Group();
      this._pickGroup = new THREE.Group();
      this._labelGroup = new THREE.Group();
      this._haloGroup = new THREE.Group();
      this.scene.add(this._edgeGroup);
      this.scene.add(this._nodeGroup);
      this.scene.add(this._pickGroup);
      this.scene.add(this._labelGroup);
      this.scene.add(this._haloGroup);
    }

    /** 银河样式使用深空底色，其余保持默认 */
    _syncBackground() {
      if (!this.scene || !this.THREE) return;
      this.scene.background = new this.THREE.Color(
        this.opts.graphStyle === "galaxy" ? 0x0a0d13 : 0x161b22
      );
    }

    _observeResize() {
      if (this._webglFailed || !this.renderer) return;
      this._lastFit = { w: 0, h: 0 };
      const ro = new ResizeObserver(() => {
        const w = this.container.clientWidth;
        const h = this.container.clientHeight;
        if (w === this._lastFit.w && h === this._lastFit.h) return;
        if (w <= 0 || h <= 0) return;
        this._lastFit = { w, h };
        this.renderer.setSize(w, h);
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
        if (this._pendingRelayout && this._isPanelVisible()) {
          this.resetSimulation();
        } else if (this.active) {
          this._render();
        }
      });
      ro.observe(this.container);
      this._resizeObs = ro;
    }

    _isPanelVisible() {
      return this.container.clientWidth > 10 && this.container.clientHeight > 10;
    }

    _clearGraph() {
      if (this._nodeGeo) {
        this._nodeGeo.dispose();
        this._nodeGeo = null;
      }
      for (const mesh of this._nodeMeshes.values()) {
        mesh.material?.dispose();
        this._nodeGroup.remove(mesh);
      }
      this._nodeMeshes.clear();
      if (this._pickGeo) {
        this._pickGeo.dispose();
        this._pickGeo = null;
      }
      for (const pick of this._pickMeshes.values()) {
        this._pickGroup.remove(pick);
      }
      this._pickMeshes.clear();
      this._pickOctree = null;
      for (const sprite of this._labelSprites.values()) {
        sprite.material?.map?.dispose();
        sprite.material?.dispose();
        this._labelGroup.remove(sprite);
      }
      this._labelSprites.clear();
      for (const halo of this._haloSprites.values()) {
        halo.material?.dispose();
        this._haloGroup.remove(halo);
      }
      this._haloSprites.clear();
      for (const line of this._edgeLines) {
        line.geometry?.dispose();
        line.material?.dispose();
        this._edgeGroup.remove(line);
      }
      this._edgeLines = [];
    }

    _galaxyStats() {
      const v = this.engine.links?.length || 0;
      if (!this._galaxyCache || this._galaxyCache.version !== v) {
        const deg = new Map();
        let max = 0;
        for (const l of this.engine.links || []) {
          if (l.source) deg.set(l.source, (deg.get(l.source) || 0) + 1);
          if (l.target) deg.set(l.target, (deg.get(l.target) || 0) + 1);
        }
        for (const d of deg.values()) if (d > max) max = d;
        this._galaxyCache = { deg, max, version: v };
      }
      return this._galaxyCache;
    }

    _rebuildGraph() {
      const THREE = this.THREE;
      this._clearGraph();
      const r = this.opts.nodeRadius * 0.85;
      const pickR = Math.max(r * 2.2, 10);
      this._pickRadius = pickR;
      this._nodeGeo = new THREE.SphereGeometry(r, 16, 12);
      this._pickGeo = new THREE.SphereGeometry(pickR, 8, 6);
      const pickMat = new THREE.MeshBasicMaterial({
        visible: false,
        depthWrite: false,
      });
      const galaxy = this.opts.graphStyle === "galaxy";
      const gStats = galaxy ? this._galaxyStats() : null;

      for (const n of this.layout.nodes) {
        let baseColor = n.range_ok === false ? 0x8b949e : 0xc9d1d9;
        let scale = 1;
        let ratio = 0;
        if (gStats) {
          ratio = gStats.max ? (gStats.deg.get(n.id) || 0) / gStats.max : 0;
          baseColor = galaxyColor3D(ratio);
          scale = 1 + ratio * 0.4;
        }
        const mat = new THREE.MeshStandardMaterial({
          color: baseColor,
          roughness: 0.55,
          metalness: 0.08,
          emissive: galaxy ? baseColor : 0x000000,
          emissiveIntensity: galaxy ? 0.25 + ratio * 0.45 : 0,
        });
        const mesh = new THREE.Mesh(this._nodeGeo, mat);
        mesh.position.set(n.x, n.y, n.z);
        mesh.scale.set(scale, scale, scale);
        mesh.userData.nodeId = n.id;
        mesh.userData.gRatio = ratio;
        this._nodeGroup.add(mesh);
        this._nodeMeshes.set(n.id, mesh);

        if (galaxy) {
          const glow = this.opts.galaxyGlow3d ?? 0.6;
          const hs = r * (4 + scale * 3 + glow * 2);
          const halo = new THREE.Sprite(
            new THREE.SpriteMaterial({
              map: getHaloTexture(THREE),
              color: baseColor,
              transparent: true,
              depthWrite: false,
              blending: THREE.AdditiveBlending,
              opacity: glow * (0.35 + ratio * 0.55),
            })
          );
          halo.scale.set(hs, hs, 1);
          halo.position.set(n.x, n.y, n.z);
          halo.userData.nodeId = n.id;
          halo.userData.baseOpacity = glow * (0.35 + ratio * 0.55);
          halo.userData.baseScale = hs;
          this._haloGroup.add(halo);
          this._haloSprites.set(n.id, halo);
        }

        const pick = new THREE.Mesh(this._pickGeo, pickMat);
        pick.position.set(n.x, n.y, n.z);
        pick.userData.nodeId = n.id;
        this._pickGroup.add(pick);
        this._pickMeshes.set(n.id, pick);
      }

      for (const n of this.layout.nodes) {
        const text = displayLabelForNode(n, this.opts);
        const sprite = createNodeLabelSprite(THREE, text, r);
        this._positionLabelSprite(sprite, n, r);
        sprite.userData.nodeId = n.id;
        this._labelGroup.add(sprite);
        this._labelSprites.set(n.id, sprite);
      }

      for (const link of this.layout.simLinks) {
        const s = this.layout.nodes[link.sourceIndex];
        const t = this.layout.nodes[link.targetIndex];
        if (!s || !t) continue;
        const points = [
          new THREE.Vector3(s.x, s.y, s.z),
          new THREE.Vector3(t.x, t.y, t.z),
        ];
        const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
        const lineMat = new THREE.LineBasicMaterial({
          color: hexColor(link.type),
          transparent: true,
          opacity: 0.55,
        });
        const line = new THREE.Line(lineGeo, lineMat);
        line.userData = { source: link.source, target: link.target, type: link.type };
        this._edgeGroup.add(line);
        this._edgeLines.push(line);
      }
      this._rebuildPickOctree();
    }

    _rebuildPickOctree() {
      const Oct = global.MemoriaGraphOctree;
      const minN = Oct?.MIN_NODES ?? 40;
      if (!Oct || this.layout.nodes.length < minN) {
        this._pickOctree = null;
        return;
      }
      const r = this._pickRadius;
      const entries = this.layout.nodes.map((n) => ({
        id: n.id,
        x: n.x,
        y: n.y,
        z: n.z,
        radius: r,
      }));
      if (!this._pickOctree) this._pickOctree = new Oct();
      this._pickOctree.build(entries);
    }

    _pickTargets() {
      const fallback = this._pickMeshes.size
        ? [...this._pickMeshes.values()]
        : [...this._nodeMeshes.values()];
      const oct = this._pickOctree;
      if (!oct) return fallback;
      const ids = oct.queryRay(this._raycaster.ray.origin, this._raycaster.ray.direction, []);
      if (!ids.length) return [];
      const out = [];
      for (const id of ids) {
        const mesh = this._pickMeshes.get(id);
        if (mesh) out.push(mesh);
      }
      return out.length ? out : fallback;
    }

    _positionLabelSprite(sprite, n, nodeR) {
      const r = nodeR ?? this.opts.nodeRadius * 0.85;
      const gap = Math.max(6, r * 0.35);
      const yOff = r + sprite.scale.y * 0.5 + gap;
      sprite.position.set(n.x, n.y - yOff, n.z);
    }

    _syncPositions() {
      const r = this.opts.nodeRadius * 0.85;
      for (const n of this.layout.nodes) {
        const mesh = this._nodeMeshes.get(n.id);
        if (mesh) mesh.position.set(n.x, n.y, n.z);
        const pick = this._pickMeshes.get(n.id);
        if (pick) pick.position.set(n.x, n.y, n.z);
        const label = this._labelSprites.get(n.id);
        if (label) this._positionLabelSprite(label, n, r);
        const halo = this._haloSprites.get(n.id);
        if (halo) halo.position.set(n.x, n.y, n.z);
      }
      for (let i = 0; i < this.layout.simLinks.length; i++) {
        const link = this.layout.simLinks[i];
        const line = this._edgeLines[i];
        if (!line) continue;
        const s = this.layout.nodes[link.sourceIndex];
        const t = this.layout.nodes[link.targetIndex];
        if (!s || !t) continue;
        const pos = line.geometry.attributes.position;
        pos.setXYZ(0, s.x, s.y, s.z);
        pos.setXYZ(1, t.x, t.y, t.z);
        pos.needsUpdate = true;
      }
      if (this._pickOctree) this._rebuildPickOctree();
    }

    _fitCamera() {
      const b = this.layout.bounds3D();
      if (!this.layout.nodes.length) return;
      const span = Math.max(b.maxX - b.minX, b.maxY - b.minY, b.maxZ - b.minZ, 80);
      const dist = span * 1.35;
      if (this._controls) {
        this._controls.target.set(b.cx, b.cy, b.cz);
        this._controls.update();
      }
      this.camera.position.set(b.cx, b.cy + dist * 0.15, b.cz + dist);
      this.camera.lookAt(b.cx, b.cy, b.cz);
    }

    resetSimulation() {
      if (!this._isPanelVisible()) {
        this._pendingRelayout = true;
        return;
      }
      this._pendingRelayout = false;
      const groupId =
        global.MemoriaGraphShell?.getGraphGroupId?.() ??
        global.MemoriaGraphGroups?.ALL_GROUP_ID ??
        "all";
      const loadOpts = global.MemoriaGraphGroups?.buildLayoutLoadOpts
        ? global.MemoriaGraphGroups.buildLayoutLoadOpts(this.engine, this.opts, groupId)
        : { spreadFactor: this.opts.spreadFactor };
      if (!this.layout.nodes.length && this.engine.nodes.length) {
        this.layout.loadFromEngine(this.engine, loadOpts);
      } else if (this.engine.nodes.length) {
        this.layout.loadFromEngine(this.engine, loadOpts);
      }
      this._rebuildGraph();
      this._fitCamera();
      this._applyHighlight();
      this._render();
    }

    applyOptions(partial, opts = {}) {
      const labelKeys = ["labelMode", "labelMaxLen", "nodeRadius"];
      const labelDirty = labelKeys.some((k) => partial && partial[k] !== undefined);
      const styleDirty =
        partial &&
        partial.graphStyle !== undefined &&
        partial.graphStyle !== this.opts.graphStyle;
      const glowDirty =
        partial &&
        partial.galaxyGlow3d !== undefined &&
        partial.galaxyGlow3d !== this.opts.galaxyGlow3d;
      Object.assign(this.opts, partial || {});
      this._applyZoomSettings();
      this._syncBackground();
      if (glowDirty && this.opts.graphStyle === "galaxy") {
        this._syncHaloGlow();
        this._applyHighlight();
        if (this.active) this._render();
      } else if (opts.relayout) this.resetSimulation();
      else if ((styleDirty || labelDirty) && this.layout.nodes.length) {
        this._rebuildGraph();
        this._applyHighlight();
        if (this.active) this._render();
      } else if (this.active) this._render();
    }

    /** 银河光晕强度变化时按当前 galaxyGlow3d 更新所有光晕 sprite（无需整体重建） */
    _syncHaloGlow() {
      const glow = this.opts.galaxyGlow3d ?? 0.6;
      const r = this.opts.nodeRadius * 0.85;
      for (const [id, halo] of this._haloSprites) {
        const mesh = this._nodeMeshes.get(id);
        const ratio = mesh?.userData?.gRatio || 0;
        const scale = 1 + ratio * 0.4;
        halo.userData.baseOpacity = glow * (0.35 + ratio * 0.55);
        halo.userData.baseScale = r * (4 + scale * 3 + glow * 2);
      }
    }

    _applyZoomSettings() {
      if (!this._controls) return;
      this._controls.minDistance = this.opts.zoomMinDistance3d ?? 5;
      this._controls.maxDistance = this.opts.zoomMaxDistance3d ?? 3000;
      this._controls.zoomSpeed = this.opts.zoomSensitivity3d ?? 1.0;
      if (this.camera) {
        const dist = this.camera.position.length();
        const clamped = Math.max(this._controls.minDistance, Math.min(this._controls.maxDistance, dist));
        if (dist !== clamped) {
          this.camera.position.normalize().multiplyScalar(clamped);
        }
      }
    }

    reflow() {
      if (this._webglFailed || !this.renderer) return;
      this._lastFit = { w: 0, h: 0 };
      const w = this.container.clientWidth;
      const h = this.container.clientHeight;
      if (w > 0 && h > 0) {
        this.renderer.setSize(w, h);
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
      }
      if (this.active) this._render();
    }

    onPanelShown() {
      if (this._pendingRelayout || !this.layout.nodes.length) {
        this.resetSimulation();
        return;
      }
      this._render();
    }

    start() {
      if (this._webglFailed || !this.renderer) return;
      if (this.active) {
        this.layout._ensureSimulationRunning?.();
        return;
      }
      this.active = true;
      const loop = () => {
        if (!this.active) return;
        this._syncPositions();
        if (this._controls) this._controls.update();
        this._updateHover();
        this._tickPulse();
        this._render();
        this._raf = requestAnimationFrame(loop);
      };
      this._raf = requestAnimationFrame(loop);
    }

    /** 银河样式：交互（悬停/焦点）期间焦点星点闪烁，空闲时静止 */
    _tickPulse() {
      if (this.opts.graphStyle !== "galaxy") return;
      const hover = this._focusHoverId();
      const ext = this.externalFocus;
      const interacting = !!(
        hover ||
        (ext && (ext.sourceIds.size || ext.targetIds.size))
      );
      if (!interacting) {
        if (this._pulse) {
          this._pulse = 0;
          this._applyHighlight();
        }
        return;
      }
      this._pulse = (this._pulse || 0) + 0.06;
      const pulse = 0.5 + 0.5 * Math.sin(this._pulse);
      const boost = 0.9 + 0.7 * pulse;
      const ids = new Set(hover ? [hover] : []);
      if (ext) {
        for (const id of ext.sourceIds || []) ids.add(id);
        for (const id of ext.targetIds || []) ids.add(id);
      }
      for (const id of ids) {
        const mesh = this._nodeMeshes.get(id);
        if (mesh?.material?.emissive) {
          mesh.material.emissiveIntensity = boost;
        }
        const halo = this._haloSprites.get(id);
        if (halo) {
          halo.material.opacity = 0.55 + 0.45 * pulse;
          halo.scale.setScalar(halo.userData.baseScale * (1.15 + 0.3 * pulse));
        }
      }
    }

    stop() {
      this.active = false;
      this._cancelDrag();
      if (this._raf) cancelAnimationFrame(this._raf);
      this._raf = null;
    }

    _dragMoved(e) {
      if (!this._dragStart) return false;
      return (
        Math.abs(e.clientX - this._dragStart.x) > 4 ||
        Math.abs(e.clientY - this._dragStart.y) > 4
      );
    }

    _cancelDrag() {
      if (this._dragNodeId || this._dragPendingId) {
        this.layout.setDragNode(null);
      }
      this._dragging = false;
      this._dragNodeId = null;
      this._dragPendingId = null;
      if (this._controls) this._controls.enabled = true;
    }

    _activateNodeDrag3D(nodeId, hitPoint) {
      if (!nodeId || this._dragNodeId) return;
      this._dragging = true;
      this._dragNodeId = nodeId;
      this.layout.setDragNode(nodeId);
      if (this._controls) this._controls.enabled = false;
      const normal = new this.THREE.Vector3();
      this.camera.getWorldDirection(normal);
      this._dragPlane.setFromNormalAndCoplanarPoint(normal, hitPoint);
    }

    setExternalFocus({ sourceIds = [], targetIds = [] } = {}) {
      const inLayout = new Set(this.layout.nodes.map((n) => n.id));
      const s = new Set((sourceIds || []).filter((id) => inLayout.has(id)));
      const t = new Set((targetIds || []).filter((id) => inLayout.has(id)));
      this.externalFocus = s.size || t.size ? { sourceIds: s, targetIds: t } : null;
      if (this.active) {
        this._applyHighlight();
        this._render();
      }
    }

    clearExternalFocus() {
      if (!this.externalFocus) return;
      this.externalFocus = null;
      if (this.active) {
        this._applyHighlight();
        this._render();
      }
    }

    _focusHoverId() {
      const remote = this.remoteHoverId;
      if (remote && !this.layout.nodes.some((n) => n.id === remote)) {
        return this.hoverId;
      }
      return remote || this.hoverId;
    }

    setRemoteHover(nodeId) {
      const id = nodeId || null;
      if (this.remoteHoverId === id) return;
      this.remoteHoverId = id;
      if (this.active) {
        this._applyHighlight();
        this._render();
      }
    }

    clearRemoteHover() {
      if (!this.remoteHoverId) return;
      this.remoteHoverId = null;
      if (this.active) {
        this._applyHighlight();
        this._render();
      }
    }

    _applyHighlight() {
      const hover = this._focusHoverId();
      const ext = this.externalFocus;
      const extActive = !!(ext && (ext.sourceIds.size || ext.targetIds.size));
      const outTargets = hover
        ? new Set(this.engine.getOutgoingLinks(hover).map((l) => l.target))
        : null;

      for (const [id, mesh] of this._nodeMeshes) {
        const isHover = id === hover;
        const isExtSource = extActive && ext.sourceIds.has(id);
        const isExtTarget = extActive && ext.targetIds.has(id);
        const isTarget = (outTargets && outTargets.has(id)) || isExtTarget;
        let color = 0xc9d1d9;
        if (this.opts.graphStyle === "galaxy") {
          const gStats = this._galaxyStats();
          color = galaxyColor3D(
            gStats.max ? (gStats.deg.get(id) || 0) / gStats.max : 0
          );
        }
        if (isHover || isExtSource) color = 0xf0f6fc;
        else if (isTarget) color = 0x79c0ff;
        else if (extActive || hover) color = 0x484f58;
        const node = this.engine.getNode(id);
        if (node?.range_ok === false && !isHover && !isExtSource && !isTarget) {
          color = 0x8b949e;
        }
        mesh.material.color.setHex(color);
        if (mesh.material.emissive) {
          if (this.opts.graphStyle === "galaxy") {
            const ratio = mesh.userData.gRatio || 0;
            mesh.material.emissive.setHex(color);
            if (isHover || isExtSource) mesh.material.emissiveIntensity = 0.9;
            else if (isTarget) mesh.material.emissiveIntensity = 0.55;
            else if (extActive || hover) mesh.material.emissiveIntensity = 0.08;
            else mesh.material.emissiveIntensity = 0.25 + ratio * 0.45;
          } else if (isHover || isExtSource) {
            mesh.material.emissive.setHex(0x2f4566);
            mesh.material.emissiveIntensity = 1;
          } else if (isTarget) {
            mesh.material.emissive.setHex(0x1a3a5c);
            mesh.material.emissiveIntensity = 1;
          } else {
            mesh.material.emissive.setHex(0x000000);
            mesh.material.emissiveIntensity = 0;
          }
        }
        const halo = this._haloSprites.get(id);
        if (halo) {
          halo.material.color.setHex(color);
          if (isHover || isExtSource) {
            halo.material.opacity = 0.95;
            halo.scale.setScalar(halo.userData.baseScale * 1.35);
          } else if (isTarget) {
            halo.material.opacity = 0.7;
            halo.scale.setScalar(halo.userData.baseScale * 1.15);
          } else if (extActive || hover) {
            halo.material.opacity = 0.08;
            halo.scale.setScalar(halo.userData.baseScale);
          } else {
            halo.material.opacity = halo.userData.baseOpacity;
            halo.scale.setScalar(halo.userData.baseScale);
          }
        }
        const label = this._labelSprites.get(id);
        if (label) {
          const node = this.engine.getNode(id);
          const colorHex = labelColorHex(isHover, isTarget, node?.range_ok);
          const opacity =
            extActive || hover
              ? isHover || isTarget || isExtSource
                ? 1
                : 0.35
              : 1;
          updateLabelSpriteAppearance(label, hexToCss(colorHex), opacity);
        }
      }

      for (const line of this._edgeLines) {
        const d = line.userData;
        let active = false;
        if (hover) active = d.source === hover || d.target === hover;
        else if (extActive) {
          active = ext.sourceIds.has(d.source) && ext.targetIds.has(d.target);
        }
        line.material.opacity = active ? 0.95 : extActive || hover ? 0.12 : 0.5;
        line.material.linewidth = 1;
      }
    }

    _updateHover() {
      if (this._dragging) return;
      if (this.remoteHoverId) {
        this._applyHighlight();
        return;
      }
      this._raycaster.setFromCamera(this._pointer, this.camera);
      const picks = this._pickTargets();
      const hits = picks.length ? this._raycaster.intersectObjects(picks, false) : [];
      const hitId = hits.length ? hits[0].object.userData.nodeId : null;
      if (hitId !== this.hoverId) {
        this.hoverId = hitId;
        this.engine._emit("hover", {
          node: hitId ? this.engine.getNode(hitId) : null,
        });
        this._applyHighlight();
      }
      this.renderer.domElement.style.cursor = hitId ? "pointer" : "grab";
    }

    _bindPointer() {
      const el = this.renderer?.domElement;
      if (!el) return;
      el.addEventListener("pointermove", (e) => {
        const rect = el.getBoundingClientRect();
        this._pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        this._pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
        if (this._dragPendingId && !this._dragNodeId && this._dragMoved(e)) {
          this._raycaster.setFromCamera(this._pointer, this.camera);
          const picks = this._pickTargets();
          const hits = picks.length
            ? this._raycaster.intersectObjects(picks, false)
            : [];
          const hit = hits.find((h) => h.object.userData.nodeId === this._dragPendingId);
          if (hit) this._activateNodeDrag3D(this._dragPendingId, hit.point);
        }
        if (this._dragging && this._dragNodeId) {
          this._raycaster.setFromCamera(this._pointer, this.camera);
          if (this._raycaster.ray.intersectPlane(this._dragPlane, this._dragIntersect)) {
            this.layout.moveDragNode3D(
              this._dragIntersect.x,
              this._dragIntersect.y,
              this._dragIntersect.z
            );
          }
        }
      });

      el.addEventListener("pointerdown", (e) => {
        if (e.button !== 0) return;
        const rect = el.getBoundingClientRect();
        this._pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        this._pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
        this._raycaster.setFromCamera(this._pointer, this.camera);
        const picks = this._pickTargets();
        const hits = picks.length ? this._raycaster.intersectObjects(picks, false) : [];
        if (!hits.length) return;
        e.preventDefault();
        const nodeId = hits[0].object.userData.nodeId;
        const n = this.layout.getNode(nodeId);
        if (!n) return;
        this._dragPendingId = nodeId;
        this._dragStart = { x: e.clientX, y: e.clientY };
        el.setPointerCapture(e.pointerId);
      });

      el.addEventListener("pointerup", (e) => {
        if (!this._dragPendingId && !this._dragging) return;
        const moved = this._dragMoved(e);
        const pendingId = this._dragPendingId;
        this._cancelDrag();
        try {
          el.releasePointerCapture(e.pointerId);
        } catch (_) {
          /* ignore */
        }
        if (pendingId && !moved) {
          this.engine._emit("nodeClick", { node: this.engine.getNode(pendingId) });
        }
        this._updateHover();
      });
    }

    _render() {
      if (!this.active || this._webglFailed || !this.renderer) return;
      this.renderer.render(this.scene, this.camera);
    }
  }

  global.MemoriaGraphView3D = GraphView3D;
})(typeof window !== "undefined" ? window : globalThis);
