// ========== Memoria 前端主逻辑 ==========

// pywebview API 就绪后会调用此函数
window.addEventListener('pywebviewready', () => {
    console.log('pywebview API ready');
    window.memoria = {
        api: window.pywebview.api,
        state: {
            kbPath: null,
            index: null,
            graph: null,
            tabs: [],
            activeTab: null,
        }
    };
    initApp();
});

// 开发态调试（无 pywebview 时用 mock）
// 用 setTimeout 延迟检测，避免 pywebview 注入前误触发
setTimeout(() => {
    if (!window.pywebview && !window.memoria) {
        console.warn('pywebview not detected, running in mock mode');
        window.memoria = {
            api: createMockApi(),
            state: {
                kbPath: null,
                index: null,
                graph: null,
                tabs: [],
                activeTab: null,
            }
        };
        initApp();
    }
}, 3000);

function initApp() {
    // 配置 marked
    if (window.marked) {
        marked.setOptions({
            breaks: true,
            gfm: true,
        });
    }

    bindEvents();
    showWelcome();
}

function bindEvents() {
    document.getElementById('btn-open').addEventListener('click', openDirectory);
    document.getElementById('btn-build').addEventListener('click', buildIndex);
    document.getElementById('btn-check').addEventListener('click', checkIndex);
    document.getElementById('search-box').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') doAiSearch(e.target.value);
    });
    document.getElementById('btn-ai-search').addEventListener('click', () => {
        const q = document.getElementById('search-box').value;
        if (q) doAiSearch(q);
    });
    document.getElementById('btn-search-close').addEventListener('click', () => {
        document.getElementById('search-panel').classList.add('hidden');
    });
    document.getElementById('btn-ai-close').addEventListener('click', () => {
        document.getElementById('ai-panel').classList.add('hidden');
    });
}

// ========== 知识库管理 ==========

async function openDirectory() {
    const path = await window.memoria.api.select_directory();
    if (!path) return;
    window.memoria.state.kbPath = path;
    document.getElementById('kb-status').textContent = `已加载: ${path}`;
    document.getElementById('search-box').disabled = false;
    document.getElementById('btn-search-menu').disabled = false;
    document.getElementById('btn-ai-search').disabled = false;

    // 优先复用 .build/ 缓存，命中则秒开；未命中 fallback 到完整构建
    setStatus('正在加载...');
    try {
        const cached = await window.memoria.api.load_index();
        if (cached.status === 'ok') {
            await _applyIndexResult(cached, true);
            // 缓存命中时，extracted 已在 .build/ 中，预加载关键词仍需走一遍
            setStatus(`已从缓存加载: ${path}（点击"构建索引"可强制重建）`);
            return;
        }
        if (cached.status === 'stale') {
            console.log('缓存无效或不存在，开始完整构建:', cached.message || '');
        }
    } catch (e) {
        console.log('load_index 异常，fallback 到 build_index:', e);
    }
    await buildIndex();
}

/**
 * 把后端返回的索引结果应用到 UI（渲染图谱、打开首个节点、启用按钮等）
 * 抽取此函数供 load_index（缓存命中）和 build_index（重建）共用，避免逻辑漂移
 *
 * @param {object} result 后端返回的索引结果
 * @param {boolean} fromCache 是否来自缓存（仅影响提示文案）
 */
async function _applyIndexResult(result, fromCache = false) {
    window.memoria.state.index = result.index;
    window.memoria.state.graph = result.graph;

    const stats = result.stats || { nodes: 0, relations: 0, citations: 0 };
    const prefix = fromCache ? '已加载' : '构建完成';
    let msg = `${prefix}: ${stats.nodes} 节点, ${stats.relations} 关系, ${stats.citations} 引用`;

    // 更新编译器警告提示（可点击）
    if (typeof updateWarningsIndicator === 'function') {
        updateWarningsIndicator(result.warnings || []);
    }

    // 更新问题文件提示（可点击）
    if (typeof updateIssuesIndicator === 'function') {
        updateIssuesIndicator(result.issues || []);
    }
    setStatus(msg);

    // 渲染图谱（失败不阻塞后续流程）
    if (window.memoria.state.graph) {
        try {
            renderGraph(window.memoria.state.graph);
        } catch (e) {
            console.error('图谱渲染失败:', e);
            setStatus(msg + ' | 图谱渲染失败: ' + e.message);
        }
    }

    // 如果有节点，打开第一个
    if (result.index && result.index.nodes && result.index.nodes.length > 0) {
        openNode(result.index.nodes[0].id);
    }

    // 启用配置按钮
    if (typeof enableConfigButton === 'function') {
        enableConfigButton();
    }

    // 预加载知识点关键词（供搜索时模糊匹配）
    // 缓存命中时 extracted 也存在 .build/embeddings_extracted.json，同样走此路径
    try {
        const ext = await window.memoria.api.get_extracted_keywords();
        if (ext.status === 'ok') {
            window.memoria.state.keywords = {};
            for (const [nid, data] of Object.entries(ext.extracted || {})) {
                window.memoria.state.keywords[nid] = data.all_keywords || [];
            }
        }
    } catch (e) {
        console.log('加载关键词失败:', e);
    }

    // 加载并应用保存的设置（主题色等）
    if (typeof loadSearchConfig === 'function') {
        loadSearchConfig();
    }
}

async function buildIndex() {
    if (!window.memoria.state.kbPath) {
        showAlert('请先选择知识库目录', '提示');
        return;
    }
    setStatus('正在构建索引（强制重建）...');
    const result = await window.memoria.api.build_index();

    if (result.status === 'ok') {
        await _applyIndexResult(result, false);
    } else {
        setStatus('构建失败: ' + (result.message || ''));
        showAlert('构建失败: ' + (result.message || ''), '错误');
    }
}

async function checkIndex() {
    if (!window.memoria.state.kbPath) {
        showAlert('请先选择知识库目录', '提示');
        return;
    }
    setStatus('正在检查...');
    const result = await window.memoria.api.check_index();

    // 无论成功失败都更新状态栏（C++ check 在有断链时返回 error）
    // 注意：状态栏文字本身不可点击，可点击的是右下角的 #issues-link / #warnings-link
    let msg = '检查完成';
    if (result.errors) {
        // 解析 C++ check 输出中的断链数
        const brokenCount = (result.errors.match(/\[\[([^\]]+)\]\]/g) || []).length;
        if (brokenCount > 0) {
            msg += ` | ${brokenCount} 个断链`;
        }
    }
    setStatus(msg);

    // 更新问题文件提示（右下角可点击）
    if (typeof updateIssuesIndicator === 'function') {
        updateIssuesIndicator(result.issues || []);
    }

    // 更新编译器警告提示（右下角可点击）
    if (typeof updateWarningsIndicator === 'function') {
        // 新 builder 的 check_index 返回 output 字段，每行一条警告
        // 格式: "Broken citation: [[text]] in file.md" / "Duplicate id: xxx in N files"
        const rawOutput = result.output || result.errors || '';
        const warningLines = rawOutput
            .split('\n')
            .map(s => s.trim())
            .filter(s => s.length > 0);
        updateWarningsIndicator(warningLines);
    }

    if (result.output) {
        console.log('Check output:', result.output);
    }
    if (result.errors) {
        console.log('Check errors:', result.errors);
    }
}

// ========== 标签页管理 ==========

function openNode(nodeId) {
    // 检查是否已打开
    const existing = window.memoria.state.tabs.find(t => t.nodeId === nodeId);
    if (existing) {
        switchTab(existing.id);
        return;
    }

    // 创建标签
    const tabId = 'tab-' + Date.now();
    const node = findNode(nodeId);

    window.memoria.state.tabs.push({
        id: tabId,
        nodeId: nodeId,
        title: node ? node.title : nodeId,
    });

    renderTabs();
    switchTab(tabId);
}

/**
 * 处理链接点击：支持多匹配弹窗（LinkTargetQueue 语义）
 * 新数据模型：[[文本]] 的文本可能是 id 或 name
 * - 1 个匹配：直接跳转
 * - N 个匹配（不同文件）：弹窗让用户多选，第一个=主跳转
 * - 0 个匹配：作为虚链处理（弹重定向对话框）
 */
function handleLinkClick(targetText) {
    const index = window.memoria.state.index;
    if (!index) {
        openNode(targetText);
        return;
    }

    // 新数据模型：先按 id 查，再按 name 查
    const concepts = findConceptsByText(targetText);
    const matches = concepts.length > 0 ? concepts : [];

    if (matches.length === 0) {
        // 无匹配，虚链处理
        if (typeof openRedirectDialog === 'function') {
            openRedirectDialog(targetText);
        } else {
            openNode(targetText);
        }
        return;
    }

    if (matches.length === 1) {
        openConcept(matches[0]);
        return;
    }

    // 多匹配：检查是否真的指向不同文件
    const uniqueFiles = new Set(matches.map(m => m.file));
    if (uniqueFiles.size <= 1) {
        openConcept(matches[0]);
        return;
    }

    // 真正的多文件冗余：弹窗让用户选择
    if (typeof openDuplicatePicker === 'function') {
        // 适配旧 API：把 concept 转成 node 格式
        const nodeLike = matches.map(m => ({ id: m.id, title: m.name, file: m.file }));
        openDuplicatePicker(targetText, nodeLike);
    } else {
        openConcept(matches[0]);
    }
}

/**
 * 打开知识点（跳转到所在文件并定位标题）
 * 新数据模型：concept_locations 提供 id → {file, heading_line, heading_text}
 */
function openConcept(concept) {
    const index = window.memoria.state.index;
    const locations = index?.concept_locations || {};
    const loc = locations[concept.id];

    if (!loc) {
        // 无定位信息，回退到 openNode（用 concept id）
        openNode(concept.id);
        return;
    }

    // 用文件路径作为 tab 标识（一个文件一个 tab）
    // 但旧 openNode 用 nodeId，需要适配：找该文件的主 concept id
    const fileConcepts = (index.concepts || []).filter(c => c.file === loc.file);
    const primaryId = concept.id || (fileConcepts[0] && fileConcepts[0].id) || loc.file;

    // 检查是否已打开该文件
    const existing = window.memoria.state.tabs.find(t => t.nodeId === primaryId);
    if (existing) {
        switchTab(existing.id);
        // 切换后滚动到目标标题
        setTimeout(() => scrollToHeading(loc), 100);
        return;
    }

    // 创建新 tab
    const tabId = 'tab-' + Date.now();
    window.memoria.state.tabs.push({
        id: tabId,
        nodeId: primaryId,
        title: concept.name || concept.id,
        anchor: loc.heading_text,  // 用标题文本作为锚点
        targetConceptId: concept.id,
    });
    renderTabs();
    switchTab(tabId);
}

function closeTab(tabId) {
    const idx = window.memoria.state.tabs.findIndex(t => t.id === tabId);
    if (idx === -1) return;

    window.memoria.state.tabs.splice(idx, 1);

    if (window.memoria.state.activeTab === tabId) {
        if (window.memoria.state.tabs.length > 0) {
            switchTab(window.memoria.state.tabs[Math.max(0, idx - 1)].id);
        } else {
            window.memoria.state.activeTab = null;
            showWelcome();
        }
    }
    renderTabs();
}

function switchTab(tabId) {
    window.memoria.state.activeTab = tabId;
    renderTabs();

    const tab = window.memoria.state.tabs.find(t => t.id === tabId);
    if (!tab) return;

    loadNodeContent(tab.nodeId);
}

async function loadNodeContent(nodeId) {
    const content = await window.memoria.api.get_node_content(nodeId);
    const node = findNode(nodeId);

    const viewer = document.getElementById('viewer');
    viewer.innerHTML = '';

    // 节点操作工具条：仅显示节点 id（解析功能已移至顶栏"知识点解析"下拉菜单）
    const actionBar = document.createElement('div');
    actionBar.className = 'node-action-bar';
    actionBar.innerHTML = `
        <span class="node-id-label">${escapeHtml(nodeId)}</span>
    `;
    viewer.appendChild(actionBar);

    const wrapper = document.createElement('div');
    wrapper.className = 'markdown-body';

    // 渲染 Markdown
    let html = '';
    if (window.marked) {
        html = marked.parse(content);
    } else {
        html = `<pre>${escapeHtml(content)}</pre>`;
    }

    // 将 [[id]] 或 [[id|text]] 替换为可点击链接
    html = html.replace(/\[\[([^\]]+)\]\]/g, (match, inner) => {
        // 支持 [[id]]、[[id#anchor]]、[[id|text]]、[[id#anchor|text]]
        let anchor = '';
        let displayText = '';
        let cleanId = inner;

        // 先分离 |text（显示文本）
        if (inner.includes('|')) {
            const parts = inner.split('|');
            cleanId = parts[0];
            displayText = parts.slice(1).join('|');
        }
        // 再分离 #anchor
        if (cleanId.includes('#')) {
            const parts = cleanId.split('#');
            anchor = parts[1] || '';
            cleanId = parts[0];
        }

        // 新数据模型：cleanId 可能是知识点 id 或 name
        // 优先按 id 查找 concept，再按 name 查找
        const concepts = findConceptsByText(cleanId);
        const isRealLink = concepts.length > 0;
        const concept = concepts[0];

        // 显示文本优先级：用户指定的 |text > 实链的 concept.name > 原文本
        const text = displayText || (concept ? concept.name : cleanId);
        if (isRealLink) {
            return `<a class="memoria-link" data-node-id="${cleanId}" data-anchor="${anchor}" title="${cleanId}">${escapeHtml(text)}</a>`;
        } else {
            return `<a class="memoria-broken-link" data-node-id="${cleanId}" title="点击创建或重定向 '${cleanId}'">${escapeHtml(text)}</a>`;
        }
    });

    // 将 [:anchor:xxx] 替换为锚点标记
    html = html.replace(/\[:anchor:([^\]]+)\]/g, (match, anchor) => {
        return `<span class="anchor-marker" data-anchor="${anchor}">⚓${anchor}</span>`;
    });

    // 自动渲染：正文中出现的已有节点 id/title（未用 [[]] 包裹）也渲染为可点击链接
    // 仅在文本节点中替换，避开 HTML 标签和已有的链接
    html = autoLinkExistingKeywords(html, nodeId);

    wrapper.innerHTML = html;
    viewer.appendChild(wrapper);

    // 渲染 KaTeX
    if (window.katex) {
        renderMath(wrapper);
    }

    // 绑定链接点击 + 右键菜单
    const currentSourceNodeId = nodeId;  // 当前节点 id（用于右键菜单操作）
    wrapper.querySelectorAll('.memoria-link, .memoria-broken-link, .memoria-autolink').forEach(link => {
        // 左键：跳转或重定向
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const targetId = link.getAttribute('data-node-id');
            if (link.classList.contains('memoria-broken-link')) {
                // 虚链不跳转，弹重定向
                if (typeof openRedirectDialog === 'function') {
                    openRedirectDialog(targetId);
                }
            } else {
                handleLinkClick(targetId);
            }
        });
        // 右键：菜单（删除/添加/编辑链接）
        link.addEventListener('contextmenu', (e) => {
            if (typeof showLinkContextMenu === 'function') {
                showLinkContextMenu(e, link, currentSourceNodeId);
            }
        });
    });

    // 选中文本右键：创建链接
    wrapper.addEventListener('contextmenu', (e) => {
        // 如果点击的是链接元素，让链接的 contextmenu 处理
        if (e.target.closest('.memoria-link, .memoria-broken-link, .memoria-autolink')) {
            return;
        }
        const sel = window.getSelection();
        const text = sel.toString().trim();
        if (!text || text.length < 1) return;
        // 仅当选区在 wrapper 内才弹出
        if (!sel.containsNode || !sel.anchorNode) return;
        const range = sel.getRangeAt(0);
        if (!wrapper.contains(range.commonAncestorContainer)) return;

        e.preventDefault();
        if (typeof showSelectionContextMenu === 'function') {
            showSelectionContextMenu(e, text, currentSourceNodeId);
        }
    });

    // 滚动到锚点（支持旧 anchor 标记和新标题定位）
    const tab = window.memoria.state.tabs.find(t => t.id === window.memoria.state.activeTab);
    if (tab && tab.targetConceptId) {
        // 新模型：根据 concept_locations 定位标题
        const loc = (window.memoria.state.index?.concept_locations || {})[tab.targetConceptId];
        if (loc) {
            scrollToHeading(loc);
        }
    } else if (tab && tab.anchor) {
        // 旧模型：根据 anchor 标记定位
        const anchorEl = wrapper.querySelector(`[data-anchor="${tab.anchor}"]`);
        if (anchorEl) {
            anchorEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }
}

/**
 * 滚动到指定标题位置（新数据模型定位机制）
 * @param loc {heading_line, heading_text} 来自 concept_locations
 */
function scrollToHeading(loc) {
    if (!loc || !loc.heading_text) return;
    const viewer = document.getElementById('viewer');
    // 在渲染区查找匹配标题文本的元素
    const headings = viewer.querySelectorAll('h1, h2, h3, h4, h5, h6');
    for (const h of headings) {
        const hText = h.textContent.trim().toLowerCase();
        if (hText === loc.heading_text.trim().toLowerCase()) {
            h.scrollIntoView({ behavior: 'smooth', block: 'start' });
            // 高亮闪烁
            h.classList.add('heading-highlight');
            setTimeout(() => h.classList.remove('heading-highlight'), 2000);
            return;
        }
    }
    // 标题文本未匹配，回退到文件开头
    viewer.scrollTop = 0;
}

function renderTabs() {
    const container = document.getElementById('tabs');
    container.innerHTML = '';

    window.memoria.state.tabs.forEach(tab => {
        const el = document.createElement('div');
        el.className = 'tab' + (tab.id === window.memoria.state.activeTab ? ' active' : '');
        el.innerHTML = `
            <span>${escapeHtml(tab.title)}</span>
            <span class="close-btn" data-tab-id="${tab.id}">✕</span>
        `;
        el.addEventListener('click', (e) => {
            if (e.target.classList.contains('close-btn')) {
                closeTab(tab.id);
            } else {
                switchTab(tab.id);
            }
        });
        container.appendChild(el);
    });
}

// ========== 辅助函数 ==========

function findNode(nodeId) {
    if (!window.memoria.state.index) return null;
    // 优先在 nodes（兼容层）中查找
    let node = window.memoria.state.index.nodes.find(n => n.id === nodeId);
    if (node) return node;
    // 回退到 concepts
    const concept = (window.memoria.state.index.concepts || []).find(c => c.id === nodeId);
    if (concept) {
        return { id: concept.id, title: concept.name, file: concept.file };
    }
    return null;
}

/**
 * 根据文本查找知识点（id 或 name 匹配）
 * 新数据模型：[[文本]] 中的文本可能是 id 也可能是 name
 *
 * @param text 链接文本
 * @returns 匹配的 concept 数组（可能 0/1/N 个）
 */
function findConceptsByText(text) {
    if (!window.memoria.state.index) return [];
    const concepts = window.memoria.state.index.concepts || [];
    return concepts.filter(c => c.id === text || c.name === text);
}

/**
 * 自动把正文中出现的已有节点 id/title 渲染为可点击链接
 * 仅修改文本节点内容，跳过 <a> <code> <pre> 等标签内部
 *
 * @param html 原始 HTML
 * @param currentNodeId 当前节点 id（避免把自己渲染成链接）
 * @returns 处理后的 HTML
 */
function autoLinkExistingKeywords(html, currentNodeId) {
    const currentAutoLinkSourceId = currentNodeId;
    if (!window.memoria.state.index) return html;

    const nodes = window.memoria.state.index.nodes;
    // 构造匹配列表：(keyword, target_node)，按长度降序避免短词先匹配
    const matches = [];
    nodes.forEach(n => {
        if (n.id && n.id !== currentNodeId && n.id.length >= 3) {
            matches.push({ keyword: n.id, node: n, isTitle: false });
        }
        if (n.title && n.title !== currentNodeId && n.title.length >= 3) {
            matches.push({ keyword: n.title, node: n, isTitle: true });
        }
    });
    // 去重（同 keyword 优先用 id 匹配）
    const seen = new Set();
    const uniqueMatches = [];
    matches.sort((a, b) => b.keyword.length - a.keyword.length);
    matches.forEach(m => {
        const key = m.keyword.toLowerCase();
        if (seen.has(key)) return;
        seen.add(key);
        uniqueMatches.push(m);
    });

    if (uniqueMatches.length === 0) return html;

    // 用 DOM Parser 安全处理：只在文本节点中替换
    const tmp = document.createElement('div');
    tmp.innerHTML = html;

    const SKIP_TAGS = new Set(['A', 'CODE', 'PRE', 'SCRIPT', 'STYLE', 'TEXTAREA', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6']);

    function processTextNodes(node) {
        if (node.nodeType === Node.TEXT_NODE) {
            const text = node.nodeValue;
            if (!text || text.trim() === '') return;
            // 逐个关键词匹配（首次出现）
            let replaced = text;
            uniqueMatches.forEach(m => {
                const kw = m.keyword;
                // 转义正则特殊字符
                const pattern = new RegExp('(?<![a-zA-Z0-9_])' + kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?![a-zA-Z0-9_])', 'i');
                if (pattern.test(replaced)) {
                    // 检查黑名单（用户右键删除过的自动链接）
                    const blKey = `${currentAutoLinkSourceId}::${kw.toLowerCase()}::${m.node.id}`;
                    if (window.memoria.autolinkBlacklist && window.memoria.autolinkBlacklist[blKey]) {
                        return;  // 跳过此关键词
                    }
                    const linkHtml = `<a class="memoria-link memoria-autolink" data-node-id="${m.node.id}">${kw}</a>`;
                    replaced = replaced.replace(pattern, linkHtml);
                }
            });
            if (replaced !== text) {
                const span = document.createElement('span');
                span.innerHTML = replaced;
                node.parentNode.replaceChild(span, node);
            }
        } else if (node.nodeType === Node.ELEMENT_NODE) {
            if (SKIP_TAGS.has(node.tagName)) return;
            // 复制子节点列表以避免迭代时被修改
            const children = Array.from(node.childNodes);
            children.forEach(processTextNodes);
        }
    }

    Array.from(tmp.childNodes).forEach(processTextNodes);
    return tmp.innerHTML;
}

function setStatus(msg) {
    document.getElementById('status-info').textContent = msg;
}

function showWelcome() {
    const viewer = document.getElementById('viewer');
    viewer.innerHTML = `
        <div class="welcome">
            <h1>Memoria</h1>
            <p>AI 知识库浏览器</p>
            <p style="margin-top: 24px">点击「打开」选择你的知识库目录</p>
            <p>目录中应包含 nodes/ 子目录，存放 .md 知识文件</p>
        </div>
    `;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 渲染 LaTeX 数学公式
function renderMath(container) {
    // 行内公式 $...$
    container.querySelectorAll('code').forEach(code => {
        const text = code.textContent;
        if (text.startsWith('$') && text.endsWith('$')) {
            const formula = text.slice(1, -1);
            try {
                const span = document.createElement('span');
                katex.render(formula, span, { throwOnError: false });
                code.replaceWith(span);
            } catch (e) {}
        }
    });
}

// ========== Mock API（开发调试用） ==========
function createMockApi() {
    return {
        select_directory: async () => '',
        set_kb_path: async (p) => ({ status: 'ok' }),
        get_kb_path: async () => '',
        build_index: async () => ({ status: 'error', message: 'mock mode' }),
        check_index: async () => ({ status: 'ok' }),
        get_node_content: async () => '',
        get_index: async () => ({}),
        get_graph: async () => ({}),
        ai_search: async () => ({ status: 'error', message: 'mock' }),
        content_search: async () => ({ status: 'ok', results: [] }),
        ai_suggest_links: async () => ({ status: 'error', message: 'mock' }),
        suggest_auto_links: async () => ({ status: 'ok', suggestions: [] }),
        apply_auto_links: async () => ({ status: 'ok', applied: 0, errors: [] }),
        create_node: async () => ({ status: 'error', message: 'mock' }),
        suggest_redirect: async () => ({ status: 'ok', candidates: [] }),
        redirect_dangling: async () => ({ status: 'error', message: 'mock' }),
        delete_dangling: async () => ({ status: 'error', message: 'mock' }),
        reparse_keywords: async () => ({ status: 'ok', extracted: {}, user_config: {} }),
        get_node_raw: async () => ({ status: 'ok', content: '' }),
        save_node_raw: async () => ({ status: 'ok' }),
        ai_graph_analysis: async () => ({ status: 'error', message: 'mock' }),
    };
}
