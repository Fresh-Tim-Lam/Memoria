// ========== 3D 知识图谱 (Three.js) — EML Playground 扁平圆盘风格 ==========

let graph3D = false;
let _g3dScene, _g3dCamera, _g3dRenderer;
let _g3dControls;
const _g3dNodes = {};
const _g3dEdges = [];
let _g3dAnimId = null;

// ---------- 公开入口 ----------

function initGraph3D() {
    if (graph3D) {
        _clearGraph3D();
        if (_g3dRenderer) {
            const container = document.getElementById('graph-3d-container');
            if (container && _g3dRenderer.domElement.parentNode === container) {
                container.removeChild(_g3dRenderer.domElement);
            }
            _g3dRenderer.dispose();
            _g3dRenderer = null;
        }
        if (_g3dControls) {
            _g3dControls.dispose();
            _g3dControls = null;
        }
        if (_g3dAnimId) {
            cancelAnimationFrame(_g3dAnimId);
            _g3dAnimId = null;
        }
        graph3D = false;
    }
    _initScene();
}

// ---------- 场景初始化 ----------

function _initScene() {
    if (graph3D) return;
    const container = document.getElementById('graph-3d-container');
    if (!container) return;
    container.innerHTML = '';

    const w = container.clientWidth || 600;
    const h = container.clientHeight || 400;

    _g3dScene = new THREE.Scene();
    _g3dScene.background = new THREE.Color(0xfaf8f5);

    _g3dCamera = new THREE.PerspectiveCamera(45, w / h, 0.1, 500);
    _g3dCamera.position.set(0, 8, 40);
    _g3dCamera.lookAt(0, 0, 0);

    _g3dRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    _g3dRenderer.setSize(w, h);
    _g3dRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(_g3dRenderer.domElement);

    if (THREE.OrbitControls) {
        _g3dControls = new THREE.OrbitControls(_g3dCamera, _g3dRenderer.domElement);
        _g3dControls.enableDamping = true;
        _g3dControls.dampingFactor = 0.08;
        _g3dControls.rotateSpeed = 0.5;
        _g3dControls.zoomSpeed = 0.8;
        _g3dControls.minDistance = 10;
        _g3dControls.maxDistance = 150;
        _g3dControls.autoRotate = true;
        _g3dControls.autoRotateSpeed = 0.3;
    }

    const ambient = new THREE.AmbientLight(0xffffff, 1.0);
    _g3dScene.add(ambient);
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.25);
    dirLight.position.set(10, 20, 10);
    _g3dScene.add(dirLight);

    graph3D = true;
    _setupPointerEvents();
    _animate3D();
    buildGraph3D();
}

// ---------- 构建图 ----------

function buildGraph3D() {
    if (!fullGraphData) return;
    _clearGraph3D();

    const { nodes, links } = fullGraphData;
    if (!nodes || nodes.length === 0) return;

    const positions = _compute3DPositions(nodes, links);
    const idxById = {};
    nodes.forEach((n, i) => { idxById[n.id] = i; });

    // ---- 边 ----
    links.forEach(l => {
        const si = idxById[l.source];
        const ti = idxById[l.target];
        if (si === undefined || ti === undefined) return;
        const sp = positions[si], tp = positions[ti];
        if (!sp || !tp) return;

        const isWeak = l.strength === 'weak';
        const color = isWeak ? 0xd4a5b8 : 0x7a8fc8;

        const dx = tp.x - sp.x, dy = tp.y - sp.y, dz = tp.z - sp.z;
        const dist = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
        const bend = dist * 0.15;

        const midOffset = {
            x: _randCentered(bend * 0.5),
            y: bend,
            z: _randCentered(bend * 0.5),
        };

        const mid = {
            x: (sp.x + tp.x) / 2 + midOffset.x,
            y: (sp.y + tp.y) / 2 + midOffset.y,
            z: (sp.z + tp.z) / 2 + midOffset.z,
        };

        const curve = new THREE.QuadraticBezierCurve3(
            new THREE.Vector3(sp.x, sp.y, sp.z),
            new THREE.Vector3(mid.x, mid.y, mid.z),
            new THREE.Vector3(tp.x, tp.y, tp.z)
        );
        const points = curve.getPoints(24);

        const edgeGeo = new THREE.BufferGeometry().setFromPoints(points);
        const edgeMat = new THREE.LineBasicMaterial({
            color: color,
            transparent: true,
            opacity: isWeak ? 0.5 : 0.75,
        });
        const line = new THREE.Line(edgeGeo, edgeMat);
        line.userData._isEdge = true;
        line.userData._edgeData = {
            sourceId: l.source,
            targetId: l.target,
            originalMid: midOffset,
        };
        _g3dScene.add(line);
        _g3dEdges.push(line);
    });

    // ---- 节点：扁平圆盘 ----
    nodes.forEach((n, i) => {
        const pos = positions[i];
        if (!pos) return;
        const color = _nodeColor(n);

        const group = new THREE.Group();
        group.position.set(pos.x, pos.y, pos.z);
        group.userData = {
            nodeId: n.id,
            node: n,
            _basePos: { x: pos.x, y: pos.y, z: pos.z },
            _frozen: false,
            _vx: 0, _vy: 0, _vz: 0,
        };

        // 外圈
        const ringGeo = new THREE.RingGeometry(1.85, 2.05, 32);
        const ringMat = new THREE.MeshBasicMaterial({
            color: 0xffffff,
            transparent: true,
            opacity: 0.9,
            side: THREE.DoubleSide,
        });
        const ring = new THREE.Mesh(ringGeo, ringMat);
        ring.userData._isRing = true;
        group.add(ring);

        // 主圆盘
        const discGeo = new THREE.CircleGeometry(1.75, 32);
        const discMat = new THREE.MeshStandardMaterial({
            color: color,
            roughness: 0.5,
            metalness: 0.0,
            transparent: true,
            opacity: 0.95,
            side: THREE.DoubleSide,
        });
        const disc = new THREE.Mesh(discGeo, discMat);
        disc.userData._isDisc = true;
        group.add(disc);

        // 中心文字
        const abbr = makeAbbreviation(n.title);
        const labelTex = _makeLabelTexture(abbr);
        const labelMat = new THREE.MeshBasicMaterial({
            map: labelTex,
            transparent: true,
            side: THREE.DoubleSide,
            depthWrite: false,
        });
        const labelGeo = new THREE.PlaneGeometry(1.5, 0.9);
        const labelMesh = new THREE.Mesh(labelGeo, labelMat);
        labelMesh.position.z = 0.02;
        labelMesh.userData._isLabel = true;
        group.add(labelMesh);

        // 悬停高亮环
        const hoverGeo = new THREE.RingGeometry(2.15, 2.4, 32);
        const hoverMat = new THREE.MeshBasicMaterial({
            color: 0xffffff,
            transparent: true,
            opacity: 0,
            side: THREE.DoubleSide,
        });
        const hoverRing = new THREE.Mesh(hoverGeo, hoverMat);
        hoverRing.userData._isHoverRing = true;
        group.add(hoverRing);

        _g3dScene.add(group);
        _g3dNodes[n.id] = group;
    });
}

// ---------- 节点颜色 ----------

function _nodeColor(node) {
    if (!node) return 0x5a8fbf;
    const colors = [
        0x5a8fbf, 0x4a9e9e, 0x6b8ab0,
        0x3e8fa0, 0x7a8fc8, 0x5899a8,
    ];
    const accentColors = [
        0xd48c6a, 0xc47a8a,
    ];
    const id = node.id || '';
    const useAccent = _hashStr(id) % 10 === 0;
    if (useAccent) {
        return accentColors[Math.abs(_hashStr(id) >> 3) % accentColors.length];
    }
    return colors[Math.abs(_hashStr(id)) % colors.length];
}

function _hashStr(s) {
    let h = 0;
    for (let i = 0; i < s.length; i++) {
        h = ((h << 5) - h) + s.charCodeAt(i);
        h |= 0;
    }
    return h;
}

function _randCentered(scale) {
    return (Math.random() - 0.5) * scale * 2;
}

// ---------- 文字贴图 ----------

function _makeLabelTexture(text) {
    const canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 128;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, 256, 128);
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 52px -apple-system, "Segoe UI", sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.shadowColor = 'rgba(0,0,0,0.15)';
    ctx.shadowBlur = 2;
    ctx.fillText(text, 128, 64);
    const texture = new THREE.CanvasTexture(canvas);
    texture.minFilter = THREE.LinearFilter;
    texture.magFilter = THREE.LinearFilter;
    return texture;
}

// ---------- 3D 力导向布局 ----------

function _compute3DPositions(nodes, links) {
    const n = nodes.length;
    if (n === 0) return [];
    const pos = new Array(n);

    for (let i = 0; i < n; i++) {
        const r = 2 + Math.random() * 3;
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.acos(2 * Math.random() - 1);
        pos[i] = {
            x: r * Math.sin(phi) * Math.cos(theta),
            y: r * Math.cos(phi) * 0.7,
            z: r * Math.sin(phi) * Math.sin(theta),
        };
    }

    const idxMap = {};
    nodes.forEach((nd, i) => { idxMap[nd.id] = i; });

    const iterations = 200;
    for (let iter = 0; iter < iterations; iter++) {
        const forces = pos.map(() => ({ x: 0, y: 0, z: 0 }));

        // 节点排斥
        for (let i = 0; i < n; i++) {
            for (let j = i + 1; j < n; j++) {
                const dx = pos[j].x - pos[i].x;
                const dy = pos[j].y - pos[i].y;
                const dz = pos[j].z - pos[i].z;
                const dist2 = dx * dx + dy * dy + dz * dz;
                const dist = Math.sqrt(dist2) || 0.1;
                if (dist > 30) continue;
                const rep = 80 / dist2;
                const fx = dx / dist * rep;
                const fy = dy / dist * rep;
                const fz = dz / dist * rep;
                forces[i].x -= fx; forces[i].y -= fy; forces[i].z -= fz;
                forces[j].x += fx; forces[j].y += fy; forces[j].z += fz;
            }
        }

        // 连边吸引
        links.forEach(l => {
            const si = idxMap[l.source], ti = idxMap[l.target];
            if (si === undefined || ti === undefined) return;
            const s = pos[si], t = pos[ti];
            const dx = t.x - s.x, dy = t.y - s.y, dz = t.z - s.z;
            const dist = Math.sqrt(dx * dx + dy * dy + dz * dz) || 0.1;
            const rest = l.strength === 'weak' ? 12 : 7;
            const diff = dist - rest;
            const strength = l.strength === 'weak' ? 0.015 : 0.04;
            const fx = dx / dist * diff * strength;
            const fy = dy / dist * diff * strength;
            const fz = dz / dist * diff * strength;
            forces[si].x += fx; forces[si].y += fy; forces[si].z += fz;
            forces[ti].x -= fx; forces[ti].y -= fy; forces[ti].z -= fz;
        });

        // 中心吸引
        for (let i = 0; i < n; i++) {
            forces[i].x -= pos[i].x * 0.008;
            forces[i].y -= pos[i].y * 0.008;
            forces[i].z -= pos[i].z * 0.008;
        }

        const damp = Math.max(0.015, 1 - iter / iterations) * 0.4;
        for (let i = 0; i < n; i++) {
            pos[i].x += forces[i].x * damp;
            pos[i].y += forces[i].y * damp;
            pos[i].z += forces[i].z * damp;
        }
    }

    return pos;
}

// ---------- 动画循环 ----------

let _time = 0;

function _animate3D() {
    _g3dAnimId = requestAnimationFrame(_animate3D);
    _time += 0.016;

    if (_g3dControls) _g3dControls.update();

    if (_g3dCamera) {
        Object.keys(_g3dNodes).forEach(id => {
            const group = _g3dNodes[id];
            if (!group) return;
            group.children.forEach(child => {
                if (child.userData && (
                    child.userData._isRing ||
                    child.userData._isDisc ||
                    child.userData._isHoverRing ||
                    child.userData._isLabel
                )) {
                    child.lookAt(_g3dCamera.position);
                }
            });
        });
    }

    _updateHover();

    _g3dRenderer.render(_g3dScene, _g3dCamera);
}

// ---------- 悬停 / 点击 / 拖拽 ----------

let _hoveredNodeId = null;
let _draggingNodeId = null;
let _dragPlane = null;
const _raycaster = new THREE.Raycaster();
const _pointer = new THREE.Vector2(-999, -999);

function _updateHover() {
    if (!_g3dRenderer || !_g3dCamera || _draggingNodeId) return;

    const discs = [];
    Object.keys(_g3dNodes).forEach(id => {
        const group = _g3dNodes[id];
        group.children.forEach(c => {
            if (c.userData && c.userData._isDisc) discs.push(c);
        });
    });

    _raycaster.setFromCamera(_pointer, _g3dCamera);
    const intersects = _raycaster.intersectObjects(discs);

    let hitId = null;
    if (intersects.length > 0) {
        let parent = intersects[0].object.parent;
        while (parent && !parent.userData?.nodeId) {
            parent = parent.parent;
        }
        if (parent?.userData?.nodeId) {
            hitId = parent.userData.nodeId;
        }
    }

    if (_hoveredNodeId && _hoveredNodeId !== hitId) {
        const prevGroup = _g3dNodes[_hoveredNodeId];
        if (prevGroup) {
            prevGroup.children.forEach(c => {
                if (c.userData?._isHoverRing && c.material) c.material.opacity = 0;
            });
            prevGroup.scale.set(1, 1, 1);
        }
        _g3dRenderer.domElement.style.cursor = 'default';
    }

    _hoveredNodeId = hitId;

    if (hitId) {
        const group = _g3dNodes[hitId];
        if (group) {
            group.children.forEach(c => {
                if (c.userData?._isHoverRing && c.material) c.material.opacity = 0.7;
            });
            group.scale.set(1.12, 1.12, 1.12);
        }
        _g3dRenderer.domElement.style.cursor = 'pointer';
    }
}

function _setupPointerEvents() {
    const canvas = _g3dRenderer.domElement;

    canvas.addEventListener('pointerdown', (e) => {
        const rect = canvas.getBoundingClientRect();
        _pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        _pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

        if (_hoveredNodeId && _g3dControls) {
            _draggingNodeId = _hoveredNodeId;
            _g3dControls.enabled = false;
            _g3dControls.autoRotate = false;

            const group = _g3dNodes[_draggingNodeId];
            if (group) {
                _dragPlane = new THREE.Plane();
                const normal = new THREE.Vector3();
                _g3dCamera.getWorldDirection(normal);
                _dragPlane.setFromNormalAndCoplanarPoint(normal, group.position);
            }
        }
    });

    canvas.addEventListener('pointermove', (e) => {
        const rect = canvas.getBoundingClientRect();
        _pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        _pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

        if (_draggingNodeId && _dragPlane && _g3dCamera) {
            _raycaster.setFromCamera(_pointer, _g3dCamera);
            const hitPoint = new THREE.Vector3();
            if (_raycaster.ray.intersectPlane(_dragPlane, hitPoint)) {
                const group = _g3dNodes[_draggingNodeId];
                if (group) {
                    group.position.copy(hitPoint);
                    group.userData._basePos = { x: hitPoint.x, y: hitPoint.y, z: hitPoint.z };
                }
                _updateEdgePositions();
            }
        }
    });

    canvas.addEventListener('pointerup', (e) => {
        if (_draggingNodeId) {
            if (_g3dControls) {
                _g3dControls.enabled = true;
                setTimeout(() => {
                    if (_g3dControls) _g3dControls.autoRotate = true;
                }, 3000);
            }
            _draggingNodeId = null;
            _dragPlane = null;
        }
    });

    canvas.addEventListener('pointerleave', () => {
        _pointer.set(-999, -999);
        if (_draggingNodeId) {
            if (_g3dControls) _g3dControls.enabled = true;
            _draggingNodeId = null;
            _dragPlane = null;
        }
    });

    canvas.addEventListener('click', (e) => {
        if (_hoveredNodeId) {
            openGraphNode(_hoveredNodeId);
            const group = _g3dNodes[_hoveredNodeId];
            if (group) {
                group.scale.set(1.25, 1.25, 1.25);
                setTimeout(() => {
                    if (group && _hoveredNodeId) {
                        group.scale.set(1.12, 1.12, 1.12);
                    }
                }, 150);
            }
        }
    });
}

function _updateEdgePositions() {
    if (!_draggingNodeId) return;
    const draggedId = _draggingNodeId;

    _g3dEdges.forEach(edge => {
        if (!edge.userData || !edge.userData._edgeData) return;
        const { sourceId, targetId, originalMid } = edge.userData._edgeData;
        if (sourceId !== draggedId && targetId !== draggedId) return;

        const sourceGroup = _g3dNodes[sourceId];
        const targetGroup = _g3dNodes[targetId];
        if (!sourceGroup || !targetGroup) return;

        const sp = sourceGroup.position;
        const tp = targetGroup.position;

        const curve = new THREE.QuadraticBezierCurve3(
            sp.clone(),
            new THREE.Vector3(
                (sp.x + tp.x) / 2 + (originalMid ? originalMid.x : 0),
                (sp.y + tp.y) / 2 + (originalMid ? originalMid.y + 0 : 0),
                (sp.z + tp.z) / 2 + (originalMid ? originalMid.z : 0)
            ),
            tp.clone()
        );

        const points = curve.getPoints(24);
        edge.geometry.dispose();
        edge.geometry = new THREE.BufferGeometry().setFromPoints(points);
    });
}

// ---------- 清除 ----------

function _clearGraph3D() {
    Object.keys(_g3dNodes).forEach(id => {
        const group = _g3dNodes[id];
        _g3dScene.remove(group);
        group.traverse(child => {
            if (child.geometry) child.geometry.dispose();
            if (child.material) {
                if (child.material.map) child.material.map.dispose();
                child.material.dispose();
            }
        });
        delete _g3dNodes[id];
    });

    _g3dEdges.forEach(edge => {
        _g3dScene.remove(edge);
        if (edge.geometry) edge.geometry.dispose();
        if (edge.material) edge.material.dispose();
    });
    _g3dEdges.length = 0;

    _hoveredNodeId = null;
    _draggingNodeId = null;
}

// ---------- Resize ----------

function _onResize() {
    if (!_g3dCamera || !_g3dRenderer) return;
    const container = document.getElementById('graph-3d-container');
    if (!container) return;
    const w = container.clientWidth;
    const h = container.clientHeight;
    if (w === 0 || h === 0) return;
    _g3dCamera.aspect = w / h;
    _g3dCamera.updateProjectionMatrix();
    _g3dRenderer.setSize(w, h);
}

window.addEventListener('resize', _onResize);