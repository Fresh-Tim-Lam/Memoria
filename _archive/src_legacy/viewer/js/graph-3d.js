// ========== 3D 知识图谱 (Three.js + OrbitControls) ==========

let graph3D = false;
let _g3dScene, _g3dCamera, _g3dRenderer, _g3dControls;
let _g3dAnimId = null;
const _g3dNodes = {};
const _g3dEdges = [];
let _hoveredNodeId = null;
const _raycaster = new THREE.Raycaster();
const _pointer = new THREE.Vector2(-999, -999);

// ---------- 公开入口 ----------

function initGraph3D(graphData) {
    if (graph3D) _destroyGraph3D();
    if (graphData) fullGraphData = graphData;
    _initScene();
}

function _destroyGraph3D() {
    _clearGraph3D();
    if (_g3dRenderer) {
        const c = document.getElementById('graph-3d');
        if (c && _g3dRenderer.domElement.parentNode === c) c.removeChild(_g3dRenderer.domElement);
        _g3dRenderer.dispose();
        _g3dRenderer = null;
    }
    if (_g3dControls) { _g3dControls.dispose(); _g3dControls = null; }
    if (_g3dAnimId) { cancelAnimationFrame(_g3dAnimId); _g3dAnimId = null; }
    graph3D = false;
}

// ---------- 场景初始化 ----------

function _initScene() {
    const container = document.getElementById('graph-3d');
    if (!container) return;
    container.innerHTML = '';

    const w = container.clientWidth || 600;
    const h = container.clientHeight || 400;

    // 场景
    _g3dScene = new THREE.Scene();
    _g3dScene.background = new THREE.Color(0x1e1e1e);

    // 相机
    _g3dCamera = new THREE.PerspectiveCamera(50, w / h, 0.1, 500);
    _g3dCamera.position.set(0, 0, 30);

    // 渲染器
    _g3dRenderer = new THREE.WebGLRenderer({ antialias: true });
    _g3dRenderer.setSize(w, h);
    _g3dRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(_g3dRenderer.domElement);

    // OrbitControls — 来自 OrbitControls.js，挂载在 THREE.OrbitControls
    if (THREE.OrbitControls) {
        _g3dControls = new THREE.OrbitControls(_g3dCamera, _g3dRenderer.domElement);
        _g3dControls.enableDamping = true;
        _g3dControls.dampingFactor = 0.08;
        _g3dControls.autoRotate = true;
        _g3dControls.autoRotateSpeed = 0.3;
        _g3dControls.minDistance = 5;
        _g3dControls.maxDistance = 100;
        _g3dControls.enablePan = true;
        // 左键旋转，滚轮缩放，右键平移
    } else {
        console.warn('OrbitControls not found — 3D 相机控制不可用');
    }

    // 灯光
    _g3dScene.add(new THREE.AmbientLight(0xffffff, 0.8));
    const dir = new THREE.DirectionalLight(0xffffff, 0.4);
    dir.position.set(10, 20, 10);
    _g3dScene.add(dir);

    graph3D = true;
    _buildGraph();
    _setupPointerEvents();
    _animate();
}

// ---------- 构建图 ----------

function _buildGraph() {
    if (!fullGraphData || !fullGraphData.nodes) return;
    _clearGraph3D();

    const { nodes, links } = fullGraphData;
    if (!nodes.length) return;

    const positions = _computePositions(nodes, links);
    const idxById = {};
    nodes.forEach((n, i) => idxById[n.id] = i);

    // 计算群中心并设置相机目标
    let cx = 0, cy = 0, cz = 0;
    positions.forEach(p => { cx += p.x; cy += p.y; cz += p.z; });
    cx /= positions.length; cy /= positions.length; cz /= positions.length;
    if (_g3dControls) _g3dControls.target.set(cx, cy, cz);
    // 根据图大小调整相机距离
    let maxDist = 0;
    positions.forEach(p => { const d = Math.sqrt((p.x-cx)**2 + (p.y-cy)**2 + (p.z-cz)**2); if (d > maxDist) maxDist = d; });
    const camDist = Math.max(12, maxDist * 2.5);
    _g3dCamera.position.set(cx, cy + camDist * 0.2, cz + camDist);
    _g3dCamera.lookAt(cx, cy, cz);

    // ---- 边 ----
    const edgeColors = {
        reference: 0x007acc,
        prerequisite: 0xce9178,
        extend: 0x4ec9b0,
        analogy: 0xc586c0,
        contain: 0x5cb85c,
    };
    (links || []).forEach(l => {
        const si = idxById[l.source], ti = idxById[l.target];
        if (si === undefined || ti === undefined) return;
        const sp = positions[si], tp = positions[ti];
        if (!sp || !tp) return;

        const isWeak = l.strength === 'weak';
        const color = edgeColors[l.type] || 0x007acc;

        // 直线
        const geo = new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(sp.x, sp.y, sp.z),
            new THREE.Vector3(tp.x, tp.y, tp.z),
        ]);
        const mat = new THREE.LineBasicMaterial({
            color, transparent: true, opacity: isWeak ? 0.4 : 0.7,
        });
        const line = new THREE.Line(geo, mat);
        line.userData = {
            _edgeData: { sourceId: l.source, targetId: l.target, type: l.type, isWeak },
            _origColor: color,
            _origOpacity: isWeak ? 0.4 : 0.7,
        };
        _g3dScene.add(line);
        _g3dEdges.push(line);
    });

    // ---- 节点 ----
    nodes.forEach((n, i) => {
        const pos = positions[i];
        if (!pos) return;
        const color = _nodeColor3D(n.file);

        const group = new THREE.Group();
        group.position.set(pos.x, pos.y, pos.z);
        group.userData = { nodeId: n.id, node: n, origColor: color };

        // 深色圆盘
        const disc = new THREE.Mesh(
            new THREE.CircleGeometry(1.2, 32),
            new THREE.MeshBasicMaterial({ color: 0x2d2d2d, side: THREE.DoubleSide })
        );
        disc.userData._isDisc = true;
        group.add(disc);

        // 彩色圆环
        const ring = new THREE.Mesh(
            new THREE.RingGeometry(1.15, 1.35, 32),
            new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide })
        );
        ring.userData._isRing = true;
        group.add(ring);

        // 缩写文字
        const abbr = makeAbbr(n.title);
        const tex = _makeLabelTexture(abbr);
        const label = new THREE.Mesh(
            new THREE.PlaneGeometry(1.3, 0.9),
            new THREE.MeshBasicMaterial({ map: tex, transparent: true, side: THREE.DoubleSide, depthWrite: false })
        );
        label.position.z = 0.01;
        label.userData._isLabel = true;
        group.add(label);

        // 悬停光圈（默认不可见）
        const hover = new THREE.Mesh(
            new THREE.RingGeometry(1.4, 1.6, 32),
            new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0, side: THREE.DoubleSide })
        );
        hover.userData._isHoverRing = true;
        group.add(hover);

        _g3dScene.add(group);
        _g3dNodes[n.id] = group;
    });
}

// ---------- 颜色 ----------

function _nodeColor3D(file) {
    const palette = [0x3a6ea5, 0x3d8b7a, 0x9b7a65, 0x8a6b8a, 0x4a7ab5, 0x5a8a5a, 0x9a9a6a, 0x7a9a8a];
    let h = 0;
    for (let i = 0; i < (file || '').length; i++) h = ((h << 5) - h) + file.charCodeAt(i) | 0;
    return palette[Math.abs(h) % palette.length];
}

// ---------- 文字贴图 ----------

function _makeLabelTexture(text) {
    const c = document.createElement('canvas');
    c.width = 256; c.height = 128;
    const ctx = c.getContext('2d');
    ctx.clearRect(0, 0, 256, 128);
    ctx.fillStyle = '#cccccc';
    ctx.font = 'bold 48px -apple-system, "Segoe UI", sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, 128, 64);
    const t = new THREE.CanvasTexture(c);
    t.minFilter = THREE.LinearFilter;
    t.magFilter = THREE.LinearFilter;
    return t;
}

// ---------- 力导向布局 ----------

function _computePositions(nodes, links) {
    const n = nodes.length;
    if (!n) return [];
    const pos = [];
    // 随机初始位置（紧凑范围）
    for (let i = 0; i < n; i++) {
        pos.push({
            x: (Math.random() - 0.5) * 4,
            y: (Math.random() - 0.5) * 4,
            z: (Math.random() - 0.5) * 2,
        });
    }
    const idxMap = {};
    nodes.forEach((nd, i) => idxMap[nd.id] = i);

    // 紧凑力模拟
    for (let iter = 0; iter < 200; iter++) {
        const F = pos.map(() => ({ x: 0, y: 0, z: 0 }));

        // 斥力（弱化，短距离截止）
        for (let i = 0; i < n; i++) {
            for (let j = i + 1; j < n; j++) {
                const dx = pos[j].x - pos[i].x;
                const dy = pos[j].y - pos[i].y;
                const dz = pos[j].z - pos[i].z;
                const d2 = dx * dx + dy * dy + dz * dz || 0.01;
                const d = Math.sqrt(d2);
                if (d > 15) continue;
                const rep = 20 / d2;
                const fx = dx / d * rep, fy = dy / d * rep, fz = dz / d * rep;
                F[i].x -= fx; F[i].y -= fy; F[i].z -= fz;
                F[j].x += fx; F[j].y += fy; F[j].z += fz;
            }
        }

        // 引力（边）- 短距离强吸引
        (links || []).forEach(l => {
            const si = idxMap[l.source], ti = idxMap[l.target];
            if (si === undefined || ti === undefined) return;
            const s = pos[si], t = pos[ti];
            const dx = t.x - s.x, dy = t.y - s.y, dz = t.z - s.z;
            const d = Math.sqrt(dx * dx + dy * dy + dz * dz) || 0.01;
            const rest = l.strength === 'weak' ? 4 : 2.5;
            const diff = d - rest;
            const str = l.strength === 'weak' ? 0.08 : 0.2;
            const fx = dx / d * diff * str, fy = dy / d * diff * str, fz = dz / d * diff * str;
            F[si].x += fx; F[si].y += fy; F[si].z += fz;
            F[ti].x -= fx; F[ti].y -= fy; F[ti].z -= fz;
        });

        // 中心引力（增强）
        for (let i = 0; i < n; i++) {
            F[i].x -= pos[i].x * 0.03;
            F[i].y -= pos[i].y * 0.03;
            F[i].z -= pos[i].z * 0.01;
        }

        // 更新位置
        const damp = Math.max(0.01, 1 - iter / 200) * 0.4;
        for (let i = 0; i < n; i++) {
            pos[i].x += F[i].x * damp;
            pos[i].y += F[i].y * damp;
            pos[i].z += F[i].z * damp;
        }
    }
    return pos;
}

// ---------- 动画循环 ----------

function _animate() {
    _g3dAnimId = requestAnimationFrame(_animate);
    if (_g3dControls) _g3dControls.update();

    // billboard: 节点面向相机
    if (_g3dCamera) {
        Object.values(_g3dNodes).forEach(g => {
            g.children.forEach(c => {
                if (c.userData._isDisc || c.userData._isRing || c.userData._isLabel || c.userData._isHoverRing) {
                    c.lookAt(_g3dCamera.position);
                }
            });
        });
    }

    _updateHover();
    _g3dRenderer.render(_g3dScene, _g3dCamera);
}

// ---------- 悬停检测 ----------

function _updateHover() {
    if (!_g3dRenderer || !_g3dCamera) return;

    const discs = [];
    Object.values(_g3dNodes).forEach(g => g.children.forEach(c => {
        if (c.userData._isDisc) discs.push(c);
    }));

    _raycaster.setFromCamera(_pointer, _g3dCamera);
    const hits = _raycaster.intersectObjects(discs);
    let hitId = null;
    if (hits.length) {
        let p = hits[0].object.parent;
        while (p && !p.userData?.nodeId) p = p.parent;
        if (p?.userData?.nodeId) hitId = p.userData.nodeId;
    }

    if (_hoveredNodeId !== hitId) {
        if (_hoveredNodeId) _clearHighlight3D();
        _hoveredNodeId = hitId;
        if (hitId) {
            _primaryHighlight3D(hitId);
            _g3dRenderer.domElement.style.cursor = 'pointer';
        } else {
            _g3dRenderer.domElement.style.cursor = 'default';
        }
    }
}

// ---- 3D 主高亮：节点环变白，相连边变亮（双向箭头效果通过线变亮体现） ----
function _primaryHighlight3D(nodeId) {
    const g = _g3dNodes[nodeId];
    if (!g) return;
    // 节点环变白 + 放大
    g.children.forEach(c => {
        if (c.userData?._isHoverRing) c.material.opacity = 0.8;
        if (c.userData?._isRing) c.material.color.setHex(0xffffff);
    });
    g.scale.set(1.2, 1.2, 1.2);

    // 相连边变亮
    _g3dEdges.forEach(e => {
        const ed = e.userData._edgeData;
        if (ed.sourceId === nodeId || ed.targetId === nodeId) {
            e.material.opacity = 1.0;
            // 边变浅：混入白色
            const c = ed._origColor || e.material.color.getHex();
            e.material.color.setHex(_lightenColor3D(c, 0.5));
        } else {
            e.material.opacity = 0.08;
        }
    });
}

// ---- 恢复默认 ----
function _clearHighlight3D() {
    if (_hoveredNodeId) {
        const prev = _g3dNodes[_hoveredNodeId];
        if (prev) {
            prev.children.forEach(c => {
                if (c.userData?._isHoverRing) c.material.opacity = 0;
                if (c.userData?._isRing) c.material.color.setHex(prev.userData.origColor);
            });
            prev.scale.set(1, 1, 1);
        }
    }
    _g3dEdges.forEach(e => {
        e.material.opacity = e.userData._origOpacity;
        e.material.color.setHex(e.userData._origColor);
    });
}

// 混入白色使颜色变浅
function _lightenColor3D(hex, factor) {
    let r = (hex >> 16) & 0xff, g = (hex >> 8) & 0xff, b = hex & 0xff;
    r = Math.min(255, Math.round(r + (255 - r) * factor));
    g = Math.min(255, Math.round(g + (255 - g) * factor));
    b = Math.min(255, Math.round(b + (255 - b) * factor));
    return (r << 16) | (g << 8) | b;
}

// ---------- 指针事件 ----------

function _setupPointerEvents() {
    const canvas = _g3dRenderer.domElement;

    canvas.addEventListener('pointermove', e => {
        const r = canvas.getBoundingClientRect();
        _pointer.x = ((e.clientX - r.left) / r.width) * 2 - 1;
        _pointer.y = -((e.clientY - r.top) / r.height) * 2 + 1;
    });

    canvas.addEventListener('pointerleave', () => {
        _pointer.set(-999, -999);
    });

    // 点击节点：打开文件
    canvas.addEventListener('click', () => {
        if (_hoveredNodeId) {
            openGraphNode(_hoveredNodeId);
        }
    });
}

// ---- 恢复默认（对外暴露，可用于应用层清除高亮） ----
function clearHighlight3D() { _clearHighlight3D(); _hoveredNodeId = null; }

// ---------- 清除 ----------

function _clearGraph3D() {
    clearHighlight3D();
    Object.keys(_g3dNodes).forEach(id => {
        const g = _g3dNodes[id];
        _g3dScene.remove(g);
        g.traverse(c => {
            if (c.geometry) c.geometry.dispose();
            if (c.material) {
                if (c.material.map) c.material.map.dispose();
                c.material.dispose();
            }
        });
        delete _g3dNodes[id];
    });
    _g3dEdges.forEach(e => {
        _g3dScene.remove(e);
        if (e.geometry) e.geometry.dispose();
        if (e.material) e.material.dispose();
    });
    _g3dEdges.length = 0;
    _hoveredNodeId = null;
}

// ---------- Resize ----------

window.addEventListener('resize', () => {
    if (!_g3dCamera || !_g3dRenderer) return;
    const c = document.getElementById('graph-3d');
    if (!c) return;
    const w = c.clientWidth, h = c.clientHeight;
    if (!w || !h) return;
    _g3dCamera.aspect = w / h;
    _g3dCamera.updateProjectionMatrix();
    _g3dRenderer.setSize(w, h);
});
