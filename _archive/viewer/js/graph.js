// ========== 知识图谱可视化 (D3.js) ==========

let graphSimulation = null;
let graphSvgGroup = null;
let graphZoom = null;
let fullGraphData = null;       // 完整图数据
let graphGroups = [];           // 连通分量分组
let currentGroupId = -1;        // 当前显示的群组 id，-1 表示全部
let currentGraphMode = 'free-force'; // free-force | radial | top-down
let currentGraphDim = '2d';         // 2d | 3d

// ---------- 缩写生成 ----------

function makeAbbreviation(name) {
    if (!name) return '?';
    // 取每个"词"的首字母/首汉字
    const parts = name.split(/[\s_\-]+/);
    if (parts.length >= 2) {
        return parts.map(p => p[0] || '').join('').toUpperCase().slice(0, 4);
    }
    // 单字词：截取前 1-2 个字符
    const clean = name.replace(/[^a-zA-Z\u4e00-\u9fff0-9]/g, '');
    return clean.slice(0, 2).toUpperCase();
}

// ---------- 边强度辅助 ----------

function edgeStrengthClass(d) {
    const s = d.strength || 'strong';
    return s === 'weak' ? 'weak' : 'strong';
}

function edgeDistance(d) {
    const s = d.strength || 'strong';
    return s === 'weak' ? 160 : 80;
}

function edgeStrength(d) {
    const s = d.strength || 'strong';
    return s === 'weak' ? 0.2 : 0.9;
}

function renderGraph(graphData) {
    if (!graphData || !window.d3) return;

    // 过滤掉指向不存在节点的 link（断裂引用）
    const nodeIds = new Set(graphData.nodes.map(n => n.id));
    const validLinks = graphData.links.filter(
        l => nodeIds.has(l.source) && nodeIds.has(l.target)
    );
    fullGraphData = { nodes: graphData.nodes, links: validLinks };

    // 计算连通分量（群组）
    graphGroups = computeConnectedComponents(fullGraphData);

    // 渲染群组选择栏
    renderGroupTabs();

    // 默认显示最大的群组（如果只有一个则显示全部）
    if (graphGroups.length > 1) {
        // 找最大群组
        let maxIdx = 0;
        for (let i = 1; i < graphGroups.length; i++) {
            if (graphGroups[i].nodes.length > graphGroups[maxIdx].nodes.length) {
                maxIdx = i;
            }
        }
        currentGroupId = maxIdx;
    } else {
        currentGroupId = -1;
    }

    renderGraphFiltered();
}

function computeConnectedComponents(data) {
    // Union-Find 算法
    const parent = {};
    data.nodes.forEach(n => { parent[n.id] = n.id; });

    function find(x) {
        if (parent[x] !== x) parent[x] = find(parent[x]);
        return parent[x];
    }
    function union(a, b) {
        const ra = find(a), rb = find(b);
        if (ra !== rb) parent[ra] = rb;
    }

    // 节点间的 citation 关系也作为连边（[[id]] 引用视为连接）
    data.nodes.forEach(n => {
        if (n.citations) {
            n.citations.forEach(c => {
                if (parent[c] !== undefined) union(n.id, c);
            });
        }
    });
    // 图谱中的 link 关系
    data.links.forEach(l => union(l.source, l.target));

    // 按 root 分组
    const groupsMap = {};
    data.nodes.forEach(n => {
        const root = find(n.id);
        if (!groupsMap[root]) groupsMap[root] = [];
        groupsMap[root].push(n);
    });

    // 转换为数组
    const groups = Object.values(groupsMap).map(groupNodes => {
        const groupNodeIds = new Set(groupNodes.map(n => n.id));
        const groupLinks = data.links.filter(l =>
            groupNodeIds.has(l.source) && groupNodeIds.has(l.target)
        );
        // 群组代表名：取被引用最多的节点 title，或第一个节点
        let representative = groupNodes[0];
        let maxRefCount = -1;
        groupNodes.forEach(n => {
            const refCount = data.links.filter(l => l.target === n.id).length;
            if (refCount > maxRefCount) {
                maxRefCount = refCount;
                representative = n;
            }
        });
        return {
            nodes: groupNodes,
            links: groupLinks,
            name: representative.title || representative.id,
            isOrphan: groupNodes.length === 1 && groupLinks.length === 0,
        };
    });

    // 按节点数降序排列（大群组在前，孤立节点在后）
    groups.sort((a, b) => b.nodes.length - a.nodes.length);
    return groups;
}

function renderGroupTabs() {
    const container = document.getElementById('group-tabs');
    if (!container) return;
    container.innerHTML = '';

    if (graphGroups.length <= 1) {
        // 只有一个群组，不显示选择栏
        document.getElementById('group-bar').style.display = 'none';
        return;
    }
    document.getElementById('group-bar').style.display = 'block';

    // "全部" 标签
    const allTab = document.createElement('div');
    allTab.className = 'group-tab' + (currentGroupId === -1 ? ' active' : '');
    allTab.textContent = `全部 (${fullGraphData.nodes.length})`;
    allTab.title = '显示所有节点';
    allTab.addEventListener('click', () => {
        currentGroupId = -1;
        renderGroupTabs();
        renderGraphFiltered();
    });
    container.appendChild(allTab);

    // 各群组标签
    graphGroups.forEach((g, idx) => {
        const tab = document.createElement('div');
        tab.className = 'group-tab' + (currentGroupId === idx ? ' active' : '') + (g.isOrphan ? ' orphan' : '');
        const name = g.name.length > 10 ? g.name.substring(0, 10) + '...' : g.name;
        tab.textContent = `${name} (${g.nodes.length})`;
        tab.title = g.isOrphan ? `孤立节点: ${g.name}` : `群组: ${g.name} (${g.nodes.length} 节点)`;
        tab.addEventListener('click', () => {
            currentGroupId = idx;
            renderGroupTabs();
            renderGraphFiltered();
        });
        container.appendChild(tab);
    });
}

function renderGraphFiltered() {
    if (!fullGraphData) return;

    let dataToShow;
    if (currentGroupId === -1) {
        dataToShow = fullGraphData;
    } else {
        const g = graphGroups[currentGroupId];
        dataToShow = { nodes: g.nodes, links: g.links };
    }

    drawGraph(dataToShow);
}

function drawGraph(filteredData) {
    const svg = d3.select('#graph-svg');
    svg.selectAll('*').remove();

    const container = document.getElementById('graph-container');
    const width = container.clientWidth;
    const height = container.clientHeight;

    if (width === 0 || height === 0) return;

    // 缩放
    graphZoom = d3.zoom()
        .scaleExtent([0.2, 4])
        .on('zoom', (event) => {
            graphSvgGroup.attr('transform', event.transform);
        });

    svg.call(graphZoom);

    graphSvgGroup = svg.append('g');

    // 力导向模拟 — 根据布局模式
    const forces = [];
    forces.push(d3.forceLink(filteredData.links)
        .id(d => d.id)
        .distance(d => edgeDistance(d))
        .strength(d => edgeStrength(d)));

    if (currentGraphMode === 'radial') {
        // 径向：找"根"节点（被引用最多或 degree 最大），其他节点围绕
        const degrees = {};
        filteredData.nodes.forEach(n => {
            degrees[n.id] = 0;
            // 查找引用入度
        });
        filteredData.links.forEach(l => {
            if (degrees[l.target] !== undefined) degrees[l.target]++;
        });
        let rootId = filteredData.nodes[0].id;
        let maxDeg = -1;
        Object.entries(degrees).forEach(([id, deg]) => {
            if (deg > maxDeg) { maxDeg = deg; rootId = id; }
        });
        const r = Math.min(width, height) * 0.35;
        forces.push(d3.forceRadial(d => d.id === rootId ? 0 : r, width / 2, height / 2).strength(0.3));
    } else if (currentGraphMode === 'top-down') {
        // 自上而下：按 depth 分层
        forces.push(d3.forceY(d => (d.depth || 0) * 80 + 40, height * 0.1).strength(0.6));
        forces.push(d3.forceX(width / 2).strength(0.1));
    }
    // free-force: 不加额外约束力

    const simulation = d3.forceSimulation(filteredData.nodes);
    forces.forEach(f => simulation.force('link' === f.constructor.name ? 'link' : `custom_${Math.random()}`, f));
    simulation
        .force('charge', d3.forceManyBody().strength(-400))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(35));
    if (currentGraphMode === 'top-down') {
        simulation.force('x', d3.forceX(width / 2).strength(0.05));
    }
    graphSimulation = simulation;

    // 绘制边 — 应用 strength 类
    const link = graphSvgGroup.append('g')
        .selectAll('line')
        .data(filteredData.links)
        .enter().append('line')
        .attr('class', d => `graph-link ${d.type || ''} ${edgeStrengthClass(d)}`)
        .attr('stroke-width', d => d.strength === 'weak' ? 1 : 2);

    // 绘制节点 — 缩写 + 全称 tooltip
    const node = graphSvgGroup.append('g')
        .selectAll('g')
        .data(filteredData.nodes)
        .enter().append('g')
        .attr('class', 'graph-node')
        .call(d3.drag()
            .on('start', dragStarted)
            .on('drag', dragging)
            .on('end', dragEnded));

    node.append('circle')
        .attr('r', 12);

    node.append('text')
        .attr('dy', -16)
        .text(d => d.title.length > 12 ? d.title.substring(0, 12) + '...' : d.title);

    // 节点中心显示缩写
    node.append('text')
        .attr('class', 'graph-abbr')
        .attr('dy', 4)
        .attr('text-anchor', 'middle')
        .attr('font-size', 9)
        .text(d => makeAbbreviation(d.title));

    // 点击节点 → 打开文件并锚定到知识点
    node.on('click', (event, d) => {
        event.stopPropagation();
        openGraphNode(d.id);
    });

    // tick 更新位置
    graphSimulation.on('tick', () => {
        link
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);

        node.attr('transform', d => `translate(${d.x},${d.y})`);
    });
}

function dragStarted(event, d) {
    if (!event.active) graphSimulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
}

function dragging(event, d) {
    d.fx = event.x;
    d.fy = event.y;
}

function dragEnded(event, d) {
    if (!event.active) graphSimulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
}

// ---------- 侧边栏拖动调整 ----------

function initSidebarResize() {
    const resizer = document.getElementById('sidebar-resizer');
    const sidebar = document.getElementById('sidebar');
    let startX, startW;

    function onMouseDown(e) {
        startX = e.clientX;
        startW = sidebar.offsetWidth;
        resizer.classList.add('active');
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
        e.preventDefault();
    }

    function onMouseMove(e) {
        const dx = e.clientX - startX;
        let newW = startW + dx;
        newW = Math.max(200, Math.min(800, newW));
        sidebar.style.width = newW + 'px';
    }

    function onMouseUp() {
        resizer.classList.remove('active');
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        // 重新渲染图谱（尺寸变了）
        if (fullGraphData) renderGraphFiltered();
    }

    resizer.addEventListener('mousedown', onMouseDown);
}

// ---------- 布局模式切换 ----------

function initGraphModeButtons() {
    document.querySelectorAll('.graph-mode-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.graph-mode-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentGraphMode = btn.dataset.mode;
            if (fullGraphData) renderGraphFiltered();
        });
    });
}

// ---------- 2D / 3D 切换 ----------

function initGraphDimButtons() {
    document.querySelectorAll('.graph-dim-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.graph-dim-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentGraphDim = btn.dataset.dim;

            const svg = document.getElementById('graph-svg');
            const container3d = document.getElementById('graph-3d-container');
            if (currentGraphDim === '3d') {
                svg.classList.remove('active');
                container3d.classList.add('active');
                initGraph3D();
            } else {
                svg.classList.add('active');
                container3d.classList.remove('active');
                if (fullGraphData) renderGraphFiltered();
            }
        });
    });
}

// ---------- 跳转到知识点 ----------

function openGraphNode(nodeId) {
    if (!window.memoria || !window.memoria.state.index) return;
    const index = window.memoria.state.index;
    // 从 index 的 concepts 或 nodes 列表中查找
    let concept = (index.concepts || []).find(c => c.id === nodeId);
    if (!concept) {
        const node = (index.nodes || []).find(n => n.id === nodeId);
        if (node) concept = { id: node.id, name: node.title };
    }
    if (!concept) return;
    // 复用 app.js 的 openConcept 来跳转到文件 + anchor
    if (typeof openConcept === 'function') {
        openConcept(concept);
    }
}

// ---------- 初始化 ----------

document.addEventListener('DOMContentLoaded', () => {
    const svg = d3.select('#graph-svg');
    document.getElementById('btn-graph-zoom-in')?.addEventListener('click', () => {
        svg.transition().call(graphZoom.scaleBy, 1.3);
    });
    document.getElementById('btn-graph-zoom-out')?.addEventListener('click', () => {
        svg.transition().call(graphZoom.scaleBy, 1 / 1.3);
    });
    document.getElementById('btn-graph-reset')?.addEventListener('click', () => {
        svg.transition().call(graphZoom.transform, d3.zoomIdentity);
    });

    initSidebarResize();
    initGraphModeButtons();
    initGraphDimButtons();
});
