/**
 * ForceEngine Worker - Barnes-Hut 高性能版
 * 
 * 核心优化：
 * 1. Barnes-Hut 四叉树加速多体斥力（O(n²) → O(n log n)）
 * 2. D3-force 积分顺序：vx += fx * alpha → x += vx → vx *= decay
 * 3. alphaTarget 模式处理拖拽
 * 4. 每边独立劲度系数接口
 */

import { calculateRepulsions } from './barnes-hut.js';

// ========== 状态 ==========
let nodes = [];
let links = [];
let positions = new Map();

let alpha = 1.0;
let alphaTarget = 0;
let alphaDecay = 0.0228;
let alphaMin = 0.001;
let velocityDecay = 0.4;

let params = {
    linkStrength: 0.1,
    linkDistance: 150,
    repulsionStrength: -50,
    centerStrength: 0.02,
    collisionRadius: 30,
    theta: 0.5,
};

let running = false;
let tickInterval = null;

// ========== 力计算 ==========

function forceLink(alpha) {
    for (const link of links) {
        const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
        const targetId = typeof link.target === 'object' ? link.target.id : link.target;

        const sourcePos = positions.get(sourceId);
        const targetPos = positions.get(targetId);
        if (!sourcePos || !targetPos) continue;

        const dx = targetPos.x - sourcePos.x;
        const dy = targetPos.y - sourcePos.y;
        const distance = Math.sqrt(dx * dx + dy * dy) || 1;

        const strength = (link.strength !== undefined && link.strength !== null)
            ? link.strength
            : params.linkStrength;

        const force = strength * (distance - params.linkDistance) / distance;
        const fx = dx * force * alpha;
        const fy = dy * force * alpha;

        if (sourcePos.fx === null) {
            sourcePos.vx += fx;
            sourcePos.vy += fy;
        }
        if (targetPos.fx === null) {
            targetPos.vx -= fx;
            targetPos.vy -= fy;
        }
    }
}

function forceManyBody(alpha) {
    if (params.repulsionStrength === 0) return;

    const nodeArray = Array.from(positions.values());
    
    for (const pos of nodeArray) {
        if (!isFinite(pos.x) || !isFinite(pos.y)) {
            pos.x = (Math.random() - 0.5) * 400;
            pos.y = (Math.random() - 0.5) * 400;
            pos.vx = 0;
            pos.vy = 0;
        }
    }

    const forces = calculateRepulsions(nodeArray, params.repulsionStrength, params.theta);

    for (const pos of nodeArray) {
        if (pos.fx === null) {
            const f = forces.get(pos);
            if (f) {
                pos.vx += f.fx * alpha;
                pos.vy += f.fy * alpha;
            }
        }
    }
}

function forceCenter(alpha) {
    let cx = 0, cy = 0, count = 0;
    for (const pos of positions.values()) {
        if (pos.fx === null && pos.fy === null && isFinite(pos.x) && isFinite(pos.y)) {
            cx += pos.x;
            cy += pos.y;
            count++;
        }
    }
    if (count > 0) {
        cx /= count;
        cy /= count;
    }

    const strength = params.centerStrength * alpha;
    for (const pos of positions.values()) {
        if (pos.fx === null) pos.vx -= (pos.x - cx) * strength;
        if (pos.fy === null) pos.vy -= (pos.y - cy) * strength;
    }
}

function forceCollide(alpha) {
    const radius = params.collisionRadius;
    const strength = 0.05;

    const nodeArray = Array.from(positions.values());
    
    for (let i = 0; i < nodeArray.length; i++) {
        const posA = nodeArray[i];
        if (!posA || posA.fx !== null) continue;

        for (let j = i + 1; j < nodeArray.length; j++) {
            const posB = nodeArray[j];
            if (!posB || posB.fx !== null) continue;

            const dx = posA.x - posB.x;
            const dy = posA.y - posB.y;
            const distance = Math.sqrt(dx * dx + dy * dy) || 1;

            if (distance < radius * 2) {
                const overlap = radius * 2 - distance;
                const force = strength * overlap / distance * alpha;

                const fx = dx * force;
                const fy = dy * force;

                posA.vx += fx;
                posA.vy += fy;
                posB.vx -= fx;
                posB.vy -= fy;
            }
        }
    }
}

// ========== 积分循环 ==========
function tick() {
    if (nodes.length === 0) return;

    alpha += (alphaTarget - alpha) * alphaDecay;

    if (alpha < alphaMin) {
        running = false;
        self.postMessage({ type: 'done' });
        return;
    }

    forceLink(alpha);
    forceManyBody(alpha);
    forceCenter(alpha);
    forceCollide(alpha);

    for (const pos of positions.values()) {
        if (pos.fx !== null) {
            pos.x = pos.fx;
            pos.vx = 0;
        } else {
            pos.x += pos.vx;
            pos.x = Math.max(-500, Math.min(500, pos.x));
        }

        if (pos.fy !== null) {
            pos.y = pos.fy;
            pos.vy = 0;
        } else {
            pos.y += pos.vy;
            pos.y = Math.max(-500, Math.min(500, pos.y));
        }

        pos.vx *= velocityDecay;
        pos.vy *= velocityDecay;

        if (!isFinite(pos.vx)) pos.vx = 0;
        if (!isFinite(pos.vy)) pos.vy = 0;
    }

    sendTick();
}

// ========== 消息处理 ==========
self.onmessage = function(event) {
    const { type, data } = event.data;

    switch (type) {
        case 'init':
            handleInit(data);
            break;
        case 'start':
            handleStart();
            break;
        case 'stop':
            handleStop();
            break;
        case 'drag-start':
            handleDragStart(data);
            break;
        case 'drag-move':
            handleDragMove(data);
            break;
        case 'drag-end':
            handleDragEnd(data);
            break;
        case 'params':
            handleParams(data);
            break;
        case 'restart':
            handleRestart();
            break;
    }
};

function handleInit(data) {
    nodes = data.nodes || [];
    links = data.links || [];
    positions.clear();

    const spread = Math.max(400, nodes.length * 10);
    for (const node of nodes) {
        positions.set(node.id, {
            id: node.id,
            x: data.positions?.[node.id]?.x || (Math.random() - 0.5) * spread,
            y: data.positions?.[node.id]?.y || (Math.random() - 0.5) * spread,
            vx: 0,
            vy: 0,
            fx: null,
            fy: null,
        });
    }

    alpha = 1.0;
    alphaTarget = 0;
    sendTick();
}

function handleStart() {
    running = true;
    alpha = 1.0;
    alphaTarget = 0;

    if (tickInterval) clearInterval(tickInterval);
    tickInterval = setInterval(() => {
        if (running) tick();
    }, 16);
}

function handleStop() {
    running = false;
    if (tickInterval) {
        clearInterval(tickInterval);
        tickInterval = null;
    }
}

function handleRestart() {
    alpha = 1.0;
    if (!running) handleStart();
}

function handleDragStart(data) {
    const pos = positions.get(data.nodeId);
    if (pos) {
        pos.fx = pos.x;
        pos.fy = pos.y;
        alphaTarget = 0.3;
    }
}

function handleDragMove(data) {
    const pos = positions.get(data.nodeId);
    if (pos) {
        pos.fx = data.position.x;
        pos.fy = data.position.y;
    }
}

function handleDragEnd(data) {
    const pos = positions.get(data.nodeId);
    if (pos) {
        if (!data.fixed) {
            pos.fx = null;
            pos.fy = null;
        }
        alphaTarget = 0;
    }
}

function handleParams(data) {
    Object.assign(params, data);
}

function sendTick() {
    const result = {};
    for (const [id, pos] of positions) {
        const x = isFinite(pos.x) ? pos.x : 0;
        const y = isFinite(pos.y) ? pos.y : 0;
        result[id] = { x, y };
    }

    self.postMessage({
        type: 'tick',
        data: {
            positions: result,
            alpha: alpha,
        },
    });
}