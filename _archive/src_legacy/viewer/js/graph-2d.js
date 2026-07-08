// ========== 2D 知识图谱 (D3.js) ==========
// VSCode Dark+ 风格，边类型颜色区分，交互增强

let graph2DInited = false;
let gSvg = null;
let gSim = null;
let gZoom = null;
let gG = null;  // main group
let gLinkSel = null;  // link selection
let gNodeSel = null;  // node selection

// ---- 拖拽调试计数器 ----
let _dragDebug = {
    initCount: 0,
    dragStartCount: 0,
    dragMoveCount: 0,
    dragEndCount: 0,
    tickCount: 0,
    restartCount: 0,
    lastLog: '',
};
function _dragLog(label, data) {
    const msg = `[DRAG-DBG] ${label} | ` + Object.entries(data || {}).map(([k,v]) => `${k}=${v}`).join(' ');
    _dragDebug.lastLog = msg;
    console.log(msg);
}

function initGraph2D(graphData) {
    _dragDebug.initCount++;
    _dragLog('initGraph2D #'+_dragDebug.initCount, { nodes: graphData?.nodes?.length, links: graphData?.links?.length });
    const container = document.getElementById('graph-2d');
    if (!container) return;
    container.innerHTML = '';

    const data = graphData || M.graph;
    if (!data || !data.nodes || data.nodes.length === 0) {
        container.innerHTML = '<p class="empty">暂无图谱数据</p>';
        return;
    }

    fullGraphData = data;

    const w = container.clientWidth || 400;
    const h = container.clientHeight || 400;

    gSvg = d3.select(container)
        .append('svg')
        .attr('width', w)
        .attr('height', h)
        .style('background', 'var(--bg-primary)');

    gZoom = d3.zoom()
        .scaleExtent([0.2, 5])
        .filter(event => {
            if (event.button) return false;
            const target = event.target;
            const isNode = target && (target.closest('.graph-node') || target.classList.contains('graph-node'));
            if (isNode) {
                _dragLog('zoom-filter BLOCKED by .graph-node', { type: event.type });
                return false;
            }
            return true;
        })
        .on('start', (event) => {
            _dragLog('zoom START', { transform: event.transform?.toString() });
        })
        .on('zoom', (event) => {
            gG.attr('transform', event.transform);
        })
        .on('end', (event) => {
            _dragLog('zoom END', { transform: event.transform?.toString() });
        });

    gSvg.call(gZoom);

    gG = gSvg.append('g');

    // 力模拟
    gSim = d3.forceSimulation(data.nodes)
        .force('link', d3.forceLink(data.links).id(d => d.id).distance(70).strength(0.4))
        .force('charge', d3.forceManyBody().strength(-400))
        .force('center', d3.forceCenter(w / 2, h / 2))
        .force('collision', d3.forceCollide().radius(28));

    // ---- 边 ----
    // 定义箭头标记
    const defs = gG.append('defs');
    const edgeColors = {
        reference: '#007acc',
        prerequisite: '#ce9178',
        extend: '#4ec9b0',
        analogy: '#c586c0',
        contain: '#5cb85c',
    };
    // 高亮用的浅色箭头
    const edgeLightColors = {
        reference: '#4da8e8',
        prerequisite: '#e8b8a0',
        extend: '#7ee0cc',
        analogy: '#dca8d8',
        contain: '#7ed47e',
    };
    Object.entries(edgeColors).forEach(([type, color]) => {
        defs.append('marker')
            .attr('id', `arrow-${type}`)
            .attr('viewBox', '0 -5 10 10')
            .attr('refX', 18)
            .attr('refY', 0)
            .attr('markerWidth', 4)
            .attr('markerHeight', 4)
            .attr('orient', 'auto')
            .append('path')
            .attr('d', 'M0,-4L8,0L0,4')
            .attr('fill', color);
    });
    Object.entries(edgeLightColors).forEach(([type, color]) => {
        defs.append('marker')
            .attr('id', `arrow-hl-${type}`)
            .attr('viewBox', '0 -5 10 10')
            .attr('refX', 18)
            .attr('refY', 0)
            .attr('markerWidth', 5)
            .attr('markerHeight', 5)
            .attr('orient', 'auto')
            .append('path')
            .attr('d', 'M0,-4L8,0L0,4')
            .attr('fill', color);
    });

    gLinkSel = gG.append('g')
        .selectAll('line')
        .data(data.links)
        .enter().append('line')
        .attr('class', d => `graph-link ${d.type || 'reference'} ${d.strength === 'weak' ? 'weak' : ''}`)
        .attr('stroke-width', d => d.strength === 'weak' ? 1 : 1.5)
        .attr('marker-end', d => `url(#arrow-${d.type || 'reference'})`);

    // ---- 节点 ----
    gNodeSel = gG.append('g')
        .selectAll('g')
        .data(data.nodes)
        .enter().append('g')
        .attr('class', 'graph-node')
        .call(d3.drag()
            .on('start', (e, d) => {
                e.sourceEvent.stopPropagation();
                _dragDebug.dragStartCount++;
                d._dragMoved = false;
                d._dragStartX = d.x;
                d._dragStartY = d.y;
                d._dragStartFx = d.fx;
                d._dragStartFy = d.fy;
                d.fx = d.x; d.fy = d.y;
                _dragLog('START #'+_dragDebug.dragStartCount, {
                    node: d.id,
                    x: +d.x.toFixed(2),
                    y: +d.y.toFixed(2),
                    fx: +d.fx.toFixed(2),
                    fy: +d.fy.toFixed(2),
                    alpha: +gSim.alpha().toFixed(4),
                    simActive: gSim.alpha() > 0 ? 'yes' : 'no',
                    sourceEvent: e.sourceEvent?.type,
                });
            })
            .on('drag', (e, d) => {
                _dragDebug.dragMoveCount++;
                if (!d._dragMoved) {
                    d._dragMoved = true;
                }
                // 每次拖拽都确保模拟器活跃 —— 修复模拟器熄火后 dx 不更新的问题
                if (gSim.alpha() < 0.05) {
                    _dragDebug.restartCount++;
                    _dragLog('SIM RESTART #'+_dragDebug.restartCount, { node: d.id, oldAlpha: +gSim.alpha().toFixed(4) });
                    gSim.alphaTarget(0.3).restart();
                }
                d.fx = e.x; d.fy = e.y;
                _dragLog('MOVE #'+_dragDebug.dragMoveCount, {
                    node: d.id,
                    e_x: +e.x.toFixed(2),
                    e_y: +e.y.toFixed(2),
                    fx: +d.fx.toFixed(2),
                    fy: +d.fy.toFixed(2),
                    x: +d.x.toFixed(2),
                    y: +d.y.toFixed(2),
                    alpha: +gSim.alpha().toFixed(4),
                });
            })
            .on('end', (e, d) => {
                _dragDebug.dragEndCount++;
                d._lastDragTime = e.sourceEvent ? e.sourceEvent.timeStamp : Date.now();
                // 拖拽后固定节点位置，不让力模拟拉回
                if (d._dragMoved) {
                    if (!e.active) gSim.alphaTarget(0);
                }
                _dragLog('END #'+_dragDebug.dragEndCount, {
                    node: d.id,
                    x: +d.x.toFixed(2),
                    y: +d.y.toFixed(2),
                    fx: +d.fx.toFixed(2),
                    fy: +d.fy.toFixed(2),
                    alpha: +gSim.alpha().toFixed(4),
                    _dragMoved: d._dragMoved,
                    startX: +d._dragStartX.toFixed(2),
                    startY: +d._dragStartY.toFixed(2),
                });
            })
        );

    // 深色圆环节点：外圈有颜色环，内部深色
    gNodeSel.append('circle')
        .attr('r', 14)
        .attr('fill', '#2d2d2d')
        .attr('stroke', d => nodeColor(d.file))
        .attr('stroke-width', 2.5);

    // 缩写标签
    gNodeSel.append('text')
        .attr('class', 'graph-abbr')
        .attr('dy', 4)
        .attr('text-anchor', 'middle')
        .attr('font-size', 9)
        .text(d => makeAbbr(d.title));

    // 名称标签
    gNodeSel.append('text')
        .attr('class', 'graph-label')
        .attr('dy', -20)
        .attr('text-anchor', 'middle')
        .attr('font-size', 10)
        .text(d => d.title.length > 14 ? d.title.substring(0, 14) + '...' : d.title);

    // 点击打开（拖拽时不触发）
    gNodeSel.on('click', (e, d) => {
        if (d._dragMoved) return; // 拖拽过则不打开
        e.stopPropagation();
        openGraphNode(d.id);
    });

    // 悬停高亮：主高亮当前节点 + 次高亮出边目标节点
    gNodeSel.on('mouseenter', (e, d) => {
        primaryHighlight2D(d.id);
    }).on('mouseleave', () => {
        _resetGraphStyle();
    });

    gSim.on('tick', () => {
        _dragDebug.tickCount++;
        const alpha = gSim.alpha();
        if (_dragDebug.tickCount <= 5 || _dragDebug.tickCount % 20 === 0 || alpha > 0.01) {
            let sample = null;
            if (data.nodes.length > 0) {
                const d = data.nodes[Math.floor(Math.random() * data.nodes.length)];
                sample = { id: d.id, x: +d.x.toFixed(2), y: +d.y.toFixed(2), fx: d.fx !== null ? +d.fx.toFixed(2) : null, fy: d.fy !== null ? +d.fy.toFixed(2) : null };
            }
            _dragLog('TICK #'+_dragDebug.tickCount, { alpha: +alpha.toFixed(4), sample: sample ? JSON.stringify(sample) : 'none', nodeCount: data.nodes.length });
        }
        gLinkSel
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);
        gNodeSel.attr('transform', d => `translate(${d.x},${d.y})`);
    });
    gSim.on('end', () => {
        _dragLog('SIM END (alpha=0)');
    });

    graph2DInited = true;
}

// ---- 重置图谱样式 ----
function _resetGraphStyle() {
    if (gLinkSel) {
        gLinkSel
            .attr('stroke-opacity', l => l.strength === 'weak' ? 0.35 : 0.5)
            .attr('stroke-width', l => l.strength === 'weak' ? 1 : 1.5)
            .attr('marker-end', l => `url(#arrow-${l.type || 'reference'})`);
    }
    if (gNodeSel) {
        gNodeSel.select('circle')
            .attr('stroke', d => nodeColor(d.file))
            .attr('stroke-width', 2.5)
            .attr('fill', '#2d2d2d');
    }
}

// ---- 节点颜色（按文件哈希） ----
function nodeColor(file) {
    const palette = ['#3a6ea5', '#3d8b7a', '#9b7a65', '#8a6b8a', '#4a7ab5', '#5a8a5a', '#9a9a6a', '#7a9a8a'];
    let h = 0;
    for (let i = 0; i < (file || '').length; i++) h = ((h << 5) - h) + file.charCodeAt(i) | 0;
    return palette[Math.abs(h) % palette.length];
}

// ---- 缩写 ----
function makeAbbr(title) {
    if (!title) return '?';
    if (/[\u4e00-\u9fff]/.test(title)) return title.substring(0, 2);
    const words = title.split(/[\s_-]+/).filter(Boolean);
    if (words.length === 1) return words[0].substring(0, 3).toUpperCase();
    return words.map(w => w[0]).join('').toUpperCase().substring(0, 3);
}

// ---- 缩放控制 ----
function graph2DZoom(factor) {
    if (!gSvg || !gZoom) return;
    gSvg.transition().duration(300).call(gZoom.scaleBy, factor);
}
function graph2DZoomReset() {
    if (!gSvg || !gZoom) return;
    gSvg.transition().duration(500).call(gZoom.transform, d3.zoomIdentity);
}

// ========== 主/次高亮系统 ==========

// ---- 主高亮：节点环变白+加宽，所有相连边变浅加宽（双向箭头），出边目标节点次高亮 ----
function primaryHighlight2D(nodeId) {
    if (!gG || !fullGraphData) return;
    const links = fullGraphData.links || [];
    // 收集所有相连节点（出边目标 + 入边来源）— 仅一级
    const allConnectedIds = new Set([nodeId]);
    links.forEach(l => {
        const sId = typeof l.source === 'object' ? l.source.id : l.source;
        const tId = typeof l.target === 'object' ? l.target.id : l.target;
        if (sId === nodeId) allConnectedIds.add(tId);
        if (tId === nodeId) allConnectedIds.add(sId);
    });

    // 连线：相连边变浅加宽，非相连边不变（保持默认）
    if (gLinkSel) {
        // 先重置所有连线到默认
        gLinkSel
            .attr('stroke-opacity', l => l.strength === 'weak' ? 0.35 : 0.5)
            .attr('stroke-width', l => l.strength === 'weak' ? 1 : 1.5)
            .attr('marker-end', l => `url(#arrow-${l.type || 'reference'})`);
        // 再高亮相邻边
        gLinkSel.filter(l => {
            const sId = l.source.id || l.source;
            const tId = l.target.id || l.target;
            return sId === nodeId || tId === nodeId;
        })
            .attr('stroke-opacity', 0.9)
            .attr('stroke-width', 2.5)
            .attr('marker-end', l => `url(#arrow-hl-${l.type || 'reference'})`);
    }

    // 节点：只改主高亮 + 次高亮节点，非高亮节点不动
    if (gNodeSel) {
        // 先重置所有节点环到默认
        gNodeSel.select('circle')
            .attr('stroke', d => nodeColor(d.file))
            .attr('stroke-width', 2.5)
            .attr('fill', '#2d2d2d');
        // 再高亮：主节点和次节点亮度一致（#fff），仅宽度区分
        gNodeSel.filter(d => allConnectedIds.has(d.id)).select('circle')
            .attr('stroke', '#fff')
            .attr('stroke-width', d => d.id === nodeId ? 3.5 : 2.5)
            .attr('fill', '#3a3a4a');
    }
}

// ---- 次高亮：只高亮指定节点的环颜色（不改变连线） ----
function secondaryHighlight2D(nodeIds) {
    if (!gG) return;
    const idSet = new Set(nodeIds || []);
    if (idSet.size === 0) { _resetGraphStyle(); return; }
    if (gNodeSel) {
        // 先重置所有节点环到默认
        gNodeSel.select('circle')
            .attr('stroke', d => nodeColor(d.file))
            .attr('stroke-width', 2.5)
            .attr('fill', '#2d2d2d');
        // 再高亮目标节点
        gNodeSel.filter(d => idSet.has(d.id)).select('circle')
            .attr('stroke', '#fff')
            .attr('stroke-width', 3.5)
            .attr('fill', '#3a3a4a');
    }
}

// ---- 搜索/高亮一组节点（含连线变浅加宽） ----
function highlightNodes2D(ids) {
    if (!gG) return;
    const idSet = new Set(ids);
    if (idSet.size === 0) { _resetGraphStyle(); return; }
    // 连线：与高亮节点相关的边变浅加宽，非相关边不动
    if (gLinkSel) {
        gLinkSel
            .attr('stroke-opacity', l => l.strength === 'weak' ? 0.35 : 0.5)
            .attr('stroke-width', l => l.strength === 'weak' ? 1 : 1.5)
            .attr('marker-end', l => `url(#arrow-${l.type || 'reference'})`);
        gLinkSel.filter(l => {
            const sId = l.source.id || l.source;
            const tId = l.target.id || l.target;
            return idSet.has(sId) || idSet.has(tId);
        })
            .attr('stroke-opacity', 0.85)
            .attr('stroke-width', 2.5)
            .attr('marker-end', l => `url(#arrow-hl-${l.type || 'reference'})`);
    }
    // 节点：只改高亮节点，非高亮不动
    if (gNodeSel) {
        gNodeSel.select('circle')
            .attr('stroke', d => nodeColor(d.file))
            .attr('stroke-width', 2.5)
            .attr('fill', '#2d2d2d');
        gNodeSel.filter(d => idSet.has(d.id)).select('circle')
            .attr('stroke', '#fff')
            .attr('stroke-width', 3.5)
            .attr('fill', '#3a3a4a');
    }
}

// ---- 高亮单个节点及其出边目标（用于点击跳转后主高亮） ----
function highlightNodeAndOutgoing2D(nodeId) {
    if (!gG || !fullGraphData) return;
    primaryHighlight2D(nodeId);
}

// ---- 文本链接悬停次高亮（仅环颜色，不改连线） ----
function hoverHighlightNode2D(nodeId) {
    secondaryHighlight2D([nodeId]);
}
