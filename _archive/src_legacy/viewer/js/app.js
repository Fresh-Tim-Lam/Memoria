// ========== Memoria 前端主逻辑 ==========
// VSCode Dark+ 风格，标签页系统，图谱交互

// ---- 全局状态 ----
const M = {
    api: null,
    kbPath: null,
    index: null,
    graph: null,
    graphMode: '2d',
    tabs: [],          // [{id, title, type, data}]
    activeTabId: null,
    groups: [],        // [{id, label, nodeIds}]
    activeGroupId: null,
    filteredGraph: null,
    navStack: [],      // [{file, line}] 导航后退栈
    navForward: [],    // [{file, line}] 导航前进栈
};

// ---- 初始化 ----
window.addEventListener('pywebviewready', () => {
    M.api = window.pywebview.api;
    init();
});
setTimeout(() => {
    if (!window.pywebview && !M.api) {
        console.warn('pywebview not detected, mock mode');
        M.api = createMockApi();
        init();
    }
}, 3000);

function init() {
    if (window.marked) marked.setOptions({ breaks: true, gfm: true });
    bindEvents();
    initSidebarResize();
    updateNavButtons();
}

// ---- 侧边栏拖拽调整大小 ----
function initSidebarResize() {
    const resizer = $('sidebar-resizer');
    const sidebar = $('sidebar');
    if (!resizer || !sidebar) return;

    let isResizing = false;

    resizer.addEventListener('mousedown', e => {
        isResizing = true;
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        e.preventDefault();
    });

    document.addEventListener('mousemove', e => {
        if (!isResizing) return;
        const mainRect = $('main').getBoundingClientRect();
        const newWidth = e.clientX - mainRect.left;
        sidebar.style.width = Math.max(200, Math.min(newWidth, mainRect.width - 200)) + 'px';
    });

    document.addEventListener('mouseup', () => {
        if (!isResizing) return;
        isResizing = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        // 图谱需要重新适配大小
        if (M.graphMode === '2d' && typeof initGraph2D === 'function') {
            initGraph2D(M.filteredGraph || M.graph);
        }
    });
}

// ---- 事件绑定 ----
function bindEvents() {
    $('btn-open').addEventListener('click', openDirectory);
    $('btn-build').addEventListener('click', buildIndex);
    $('btn-search').addEventListener('click', doSearch);
    $('btn-nav-back').addEventListener('click', navBack);
    $('btn-nav-forward').addEventListener('click', navForward);
    $('search-box').addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });

    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            M.graphMode = btn.dataset.mode;
            toggleGraphMode();
        });
    });

    // 缩放控制
    $('btn-zoom-in').addEventListener('click', () => graphZoom(1.3));
    $('btn-zoom-out').addEventListener('click', () => graphZoom(0.7));
    $('btn-zoom-reset').addEventListener('click', () => graphZoomReset());

    // 导航快捷键 Alt+Left 后退, Alt+Right 前进
    document.addEventListener('keydown', e => {
        if (e.altKey && e.key === 'ArrowLeft') { e.preventDefault(); navBack(); }
        if (e.altKey && e.key === 'ArrowRight') { e.preventDefault(); navForward(); }
    });
}

// ---- 知识库操作 ----

async function openDirectory() {
    const path = await M.api.select_directory();
    console.log('select_directory returned:', path);
    if (!path) return;
    M.kbPath = path;
    const name = path.split(/[\\/]/).pop();
    $('kb-indicator').textContent = name;
    $('kb-indicator').classList.remove('hidden');
    setStatus(`知识库: ${path}`);
    await buildIndex();
}

async function buildIndex() {
    if (!M.kbPath) return;
    setStatus('构建中...');
    try {
        const result = await M.api.build_index();
        // pywebview 可能返回字符串，需解析
        const r = typeof result === 'string' ? JSON.parse(result) : result;
        console.log('build_index result:', JSON.stringify(r));
        if (!r || r.status === 'error') {
            setStatus('构建失败: ' + (r ? r.message : '返回为空'));
            return;
        }
        const idxRaw = await M.api.get_index();
        M.index = typeof idxRaw === 'string' ? JSON.parse(idxRaw) : idxRaw;
        const gRaw = await M.api.get_graph();
        M.graph = typeof gRaw === 'string' ? JSON.parse(gRaw) : gRaw;
        const s = r.stats || {};
        $('status-stats').textContent =
            `${s.files || 0} 文件 | ${s.concepts || 0} 知识点 | ${s.candidates || 0} 候选 | ${s.edges || 0} 边`;
        setStatus('构建完成');

        computeGroups();
        renderGraph();
        openTab('files', '文件列表', 'file-list');
    } catch (e) {
        setStatus('构建异常: ' + e.message);
        console.error('buildIndex error', e);
    }
}

// ---- 标签页系统 ----

function openTab(id, title, type, data) {
    // 已存在则更新数据并重新激活（处理跳转参数更新）
    const existing = M.tabs.find(t => t.id === id);
    if (existing) {
        // 合并新数据（如 highlightName/highlightNodeId）
        Object.assign(existing.data, data || {});
        activateTab(id);
        return;
    }
    M.tabs.push({ id, title, type, data: data || {} });
    renderTabs();
    activateTab(id);
}

function closeTab(id) {
    const idx = M.tabs.findIndex(t => t.id === id);
    if (idx === -1) return;
    M.tabs.splice(idx, 1);
    renderTabs();
    if (M.activeTabId === id) {
        if (M.tabs.length > 0) {
            const next = M.tabs[Math.min(idx, M.tabs.length - 1)];
            activateTab(next.id);
        } else {
            M.activeTabId = null;
            showWelcome();
        }
    }
}

function activateTab(id) {
    M.activeTabId = id;
    renderTabs();
    const tab = M.tabs.find(t => t.id === id);
    if (!tab) return;

    const viewer = $('viewer');
    if (tab.type === 'file-list') {
        renderFileList(viewer);
    } else if (tab.type === 'file') {
        renderFileContent(viewer, tab.data.path);
        // 如果有跳转节点ID，高亮图谱中该节点及其出边目标
        if (tab.data.highlightNodeId && typeof highlightNodeAndOutgoing2D === 'function') {
            highlightNodeAndOutgoing2D(tab.data.highlightNodeId);
        }
    }
}

function renderTabs() {
    const tabsEl = $('tabs');
    if (M.tabs.length === 0) {
        tabsEl.innerHTML = '';
        return;
    }
    tabsEl.innerHTML = M.tabs.map(t => `
        <div class="tab ${t.id === M.activeTabId ? 'active' : ''}" data-tab-id="${esc(t.id)}">
            <span>${esc(t.title)}</span>
            <span class="close-btn" data-close-id="${esc(t.id)}">×</span>
        </div>
    `).join('');

    tabsEl.querySelectorAll('.tab').forEach(el => {
        el.addEventListener('click', e => {
            if (e.target.classList.contains('close-btn')) {
                closeTab(e.target.dataset.closeId);
            } else {
                activateTab(el.dataset.tabId);
            }
        });
    });
}

// ---- 文件列表 ----

function renderFileList(container) {
    if (!M.index || !M.index.files) {
        container.innerHTML = '<p class="empty">暂无数据，请先构建索引</p>';
        return;
    }
    let html = '<div class="file-grid">';
    M.index.files.forEach(f => {
        const conceptCount = f.concepts.filter(c => c.id && !c.candidate).length;
        const candidateCount = f.concepts.filter(c => c.candidate).length;
        const edgeCount = f.edges.length;
        html += `
        <div class="file-card" data-file="${esc(f.file)}">
            <div class="file-card-name">${esc(f.file)}</div>
            <div class="file-card-desc">${esc(f.description || '')}</div>
            <div class="file-card-stats">
                <span>${conceptCount} 知识点</span>
                ${candidateCount ? `<span>${candidateCount} 候选</span>` : ''}
                <span>${edgeCount} 边</span>
            </div>
        </div>`;
    });
    html += '</div>';
    container.innerHTML = html;

    container.querySelectorAll('.file-card').forEach(card => {
        card.addEventListener('click', () => {
            openTab('file:' + card.dataset.file, card.dataset.file, 'file', { path: card.dataset.file });
        });
    });
}

// ---- 文件内容 ----

async function renderFileContent(container, relPath) {
    const tab = M.tabs.find(t => t.id === M.activeTabId);
    container.innerHTML = '<p class="empty">加载中...</p>';
    let content = await M.api.get_file(relPath);
    if (typeof content !== 'string') content = '';
    const body = stripFrontmatter(content);
    if (window.marked) {
        container.innerHTML = `<div id="file-header">
            <span id="file-title">${esc(relPath)}</span>
        </div>
        <div class="markdown-body">${marked.parse(body)}</div>`;
        processMemoriaLinks(container);

        // 跳转高亮定位
        const hlName = tab?.data?.highlightName;
        if (hlName) {
            setTimeout(() => highlightAndScrollTo(container, hlName), 100);
            delete tab.data.highlightName; // 消费后清除
        }
    } else {
        container.textContent = content;
    }
}

function highlightAndScrollTo(container, targetName) {
    if (!targetName) return;
    const headings = container.querySelectorAll('h1, h2, h3, h4, h5, h6');
    for (const h of headings) {
        if (h.textContent.trim() === targetName) {
            h.scrollIntoView({ behavior: 'smooth', block: 'start' });
            const flash = document.createElement('div');
            flash.className = 'kp-highlight-flash';
            h.parentNode.insertBefore(flash, h);
            flash.appendChild(h);
            let next = flash.nextElementSibling;
            while (next && !['H1','H2','H3','H4','H5','H6'].includes(next.tagName)) {
                const toMove = next;
                next = next.nextElementSibling;
                flash.appendChild(toMove);
            }
            // 3秒后开始淡出，淡出动画1.5秒
            setTimeout(() => flash.classList.add('fade-out'), 1500);
            setTimeout(() => {
                const parent = flash.parentNode;
                while (flash.firstChild) parent.insertBefore(flash.firstChild, flash);
                parent.removeChild(flash);
            }, 3000);
            // 销毁跳转标记，防止再次激活标签时重复跳转
            const tab = M.tabs.find(t => t.id === M.activeTabId);
            if (tab) delete tab.data.highlightName;
            return;
        }
    }
}

function processMemoriaLinks(container) {
    // 将 [[id]] 文本转换为可点击的链接
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);

    const definedIds = new Set((M.index?.concepts || []).filter(c => c.id && !c.candidate).map(c => c.id));

    nodes.forEach(node => {
        const text = node.textContent;
        if (!text.includes('[[')) return;
        const parts = text.split(/(\[\[[^\]]+\]\])/g);
        if (parts.length <= 1) return;

        const frag = document.createDocumentFragment();
        parts.forEach(part => {
            const m = part.match(/^\[\[([^\]]+)\]\]$/);
            if (m) {
                const linkText = m[1].split('|')[0].split('#')[0];
                const span = document.createElement('span');
                const isBroken = !definedIds.has(linkText);
                span.className = isBroken ? 'memoria-broken-link' : 'memoria-link';
                span.textContent = linkText;
                span.dataset.target = linkText;
                span.addEventListener('click', () => navigateToConcept(linkText));
                // 悬停时高亮图谱中对应节点
                span.addEventListener('mouseenter', () => {
                    if (typeof hoverHighlightNode2D === 'function') hoverHighlightNode2D(linkText);
                });
                span.addEventListener('mouseleave', () => {
                    if (typeof _resetGraphStyle === 'function') _resetGraphStyle();
                });
                frag.appendChild(span);
            } else {
                frag.appendChild(document.createTextNode(part));
            }
        });
        node.parentNode.replaceChild(frag, node);
    });
}

function navigateToConcept(id) {
    const kp = M.index?.concepts?.find(c => c.id === id);
    if (kp && kp.file) {
        pushNav('link');
        openTab('file:' + kp.file, kp.file, 'file', { path: kp.file, highlightName: kp.name, highlightNodeId: id });
    }
}

// ---- 导航栈 ----
function pushNav(source) {
    const tab = M.tabs.find(t => t.id === M.activeTabId);
    if (!tab || tab.type !== 'file') return;
    const entry = { file: tab.data.path, name: tab.data.highlightName || '' };
    M.navStack.push(entry);
    M.navForward = [];
    updateNavButtons();
}

function navBack() {
    if (M.navStack.length === 0) return;
    const tab = M.tabs.find(t => t.id === M.activeTabId);
    if (tab && tab.type === 'file') {
        M.navForward.push({ file: tab.data.path, name: tab.data.highlightName || '' });
    }
    const prev = M.navStack.pop();
    openTab('file:' + prev.file, prev.file, 'file', { path: prev.file, highlightName: prev.name, _nav: true });
    updateNavButtons();
}

function navForward() {
    if (M.navForward.length === 0) return;
    const tab = M.tabs.find(t => t.id === M.activeTabId);
    if (tab && tab.type === 'file') {
        M.navStack.push({ file: tab.data.path, name: tab.data.highlightName || '' });
    }
    const next = M.navForward.pop();
    openTab('file:' + next.file, next.file, 'file', { path: next.file, highlightName: next.name, _nav: true });
    updateNavButtons();
}

function updateNavButtons() {
    const btnBack = $('btn-nav-back');
    const btnForward = $('btn-nav-forward');
    if (btnBack) btnBack.disabled = M.navStack.length === 0;
    if (btnForward) btnForward.disabled = M.navForward.length === 0;
}

function showWelcome() {
    $('viewer').innerHTML = `
        <div id="welcome">
            <h1>Memoria</h1>
            <p>以知识点为最小单元的知识管理系统</p>
            <button id="btn-welcome-open-inner">打开知识库</button>
        </div>`;
    $('btn-welcome-open-inner').addEventListener('click', openDirectory);
}

// ---- 图谱 ----

// 计算连通分量（Union-Find）
function computeGroups() {
    if (!M.graph || !M.graph.nodes || M.graph.nodes.length === 0) {
        M.groups = [];
        M.filteredGraph = M.graph;
        return;
    }
    const nodes = M.graph.nodes;
    const links = M.graph.links || [];

    // Union-Find
    const parent = {};
    nodes.forEach(n => parent[n.id] = n.id);
    function find(x) { return parent[x] === x ? x : (parent[x] = find(parent[x])); }
    function union(a, b) { parent[find(a)] = find(b); }

    links.forEach(l => {
        const s = typeof l.source === 'object' ? l.source.id : l.source;
        const t = typeof l.target === 'object' ? l.target.id : l.target;
        if (parent[s] !== undefined && parent[t] !== undefined) union(s, t);
    });

    // 按根分组
    const groupMap = {};
    nodes.forEach(n => {
        const root = find(n.id);
        if (!groupMap[root]) groupMap[root] = [];
        groupMap[root].push(n.id);
    });

    // 排序：大的群在前
    const groups = Object.entries(groupMap)
        .map(([root, ids]) => ({ id: root, nodeIds: ids }))
        .sort((a, b) => b.nodeIds.length - a.nodeIds.length);

    // 为每个群生成标签：取群中第一个节点的名称
    const nodeMap = {};
    nodes.forEach(n => nodeMap[n.id] = n);
    groups.forEach(g => {
        const first = nodeMap[g.nodeIds[0]];
        g.label = first ? (first.title.length > 10 ? first.title.substring(0, 10) + '…' : first.title) : '群';
    });

    M.groups = groups;

    // 默认选中"全部"
    if (!M.activeGroupId || !groups.find(g => g.id === M.activeGroupId)) {
        M.activeGroupId = '__all__';
    }
    applyGroupFilter();
    renderGroupTabs();
}

function applyGroupFilter() {
    if (!M.graph) { M.filteredGraph = null; return; }
    if (M.activeGroupId === '__all__') {
        M.filteredGraph = M.graph;
        return;
    }
    const group = M.groups.find(g => g.id === M.activeGroupId);
    if (!group) { M.filteredGraph = M.graph; return; }
    const idSet = new Set(group.nodeIds);
    const nodes = M.graph.nodes.filter(n => idSet.has(n.id));
    const links = (M.graph.links || []).filter(l => {
        const s = typeof l.source === 'object' ? l.source.id : l.source;
        const t = typeof l.target === 'object' ? l.target.id : l.target;
        return idSet.has(s) && idSet.has(t);
    });
    M.filteredGraph = { nodes, links };
}

function renderGroupTabs() {
    const el = $('group-tabs');
    if (!el) return;
    if (M.groups.length <= 1) { el.innerHTML = ''; el.classList.add('hidden'); return; }
    el.classList.remove('hidden');
    let html = `<button class="group-tab ${M.activeGroupId === '__all__' ? 'active' : ''}" data-group="__all__">全部</button>`;
    M.groups.forEach((g, i) => {
        html += `<button class="group-tab ${M.activeGroupId === g.id ? 'active' : ''}" data-group="${esc(g.id)}" title="${g.nodeIds.length} 个节点">${esc(g.label)} (${g.nodeIds.length})</button>`;
    });
    el.innerHTML = html;
    el.querySelectorAll('.group-tab').forEach(btn => {
        btn.addEventListener('click', () => {
            M.activeGroupId = btn.dataset.group;
            applyGroupFilter();
            renderGroupTabs();
            renderGraph();
        });
    });
    // 滚轮横向滚动
    el.addEventListener('wheel', (e) => {
        e.preventDefault();
        el.scrollLeft += e.deltaY;
    }, { passive: false });
}

function renderGraph() {
    if (!M.filteredGraph && !M.graph) return;
    const data = M.filteredGraph || M.graph;
    if (M.graphMode === '2d') {
        if (typeof initGraph2D === 'function') initGraph2D(data);
    } else {
        if (typeof initGraph3D === 'function') initGraph3D(data);
    }
}

function toggleGraphMode() {
    const c2d = $('graph-2d');
    const c3d = $('graph-3d');
    const data = M.filteredGraph || M.graph;
    if (M.graphMode === '3d') {
        c2d.classList.add('hidden');
        c3d.classList.remove('hidden');
        if (typeof initGraph3D === 'function') initGraph3D(data);
    } else {
        c3d.classList.add('hidden');
        c2d.classList.remove('hidden');
        if (typeof initGraph2D === 'function') initGraph2D(data);
    }
}

// 图谱节点点击 → 打开对应文件并定位
function openGraphNode(nodeId) {
    if (!M.index) return;
    const kp = M.index.concepts.find(c => c.id === nodeId);
    if (kp && kp.file) {
        pushNav('link');
        openTab('file:' + kp.file, kp.file, 'file', { path: kp.file, highlightName: kp.name, highlightNodeId: nodeId });
    }
}

// 缩放控制
function graphZoom(factor) {
    if (M.graphMode === '2d' && typeof graph2DZoom === 'function') graph2DZoom(factor);
}
function graphZoomReset() {
    if (M.graphMode === '2d' && typeof graph2DZoomReset === 'function') graph2DZoomReset();
}

// ---- 搜索 ----

async function doSearch() {
    const q = $('search-box').value.trim();
    if (!q || !M.index) return;
    const results = M.index.concepts.filter(c =>
        c.name.toLowerCase().includes(q.toLowerCase()) ||
        (c.tags || []).some(t => t.toLowerCase().includes(q.toLowerCase()))
    );
    if (typeof highlightNodes2D === 'function') highlightNodes2D(results.map(c => c.id));
    setStatus(`找到 ${results.length} 个知识点`);
}

// ---- 工具函数 ----

function $(id) { return document.getElementById(id); }
function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function setStatus(msg) { $('status-info').textContent = msg; }

function stripFrontmatter(raw) {
    const lines = raw.split('\n');
    if (!lines.length || lines[0].trim() !== '---') return raw;
    for (let i = 1; i < lines.length; i++) {
        if (lines[i].trim() === '---') return lines.slice(i + 1).join('\n');
    }
    return raw;
}

// 全局数据引用
let fullGraphData = null;

// ---- Mock API ----
function createMockApi() {
    return {
        select_directory: async () => '',
        set_kb_path: async (p) => ({ status: 'ok', path: p }),
        build_index: async () => ({ status: 'ok', stats: { files: 0, concepts: 0, candidates: 0, edges: 0 } }),
        get_index: async () => ({}),
        get_graph: async () => ({ nodes: [], links: [] }),
        get_file: async () => '',
        save_file: async () => ({ status: 'ok' }),
    };
}
