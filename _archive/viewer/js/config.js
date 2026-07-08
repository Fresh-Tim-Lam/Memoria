// ========== 配置窗口（v3） ==========
// 左侧：文件树（文件夹可展开，选择文件不重渲染整树）
// 右侧：文件描述 → 知识点配置（多选+上下栏+区域内联链接） → 候选
// 链接 = 边：正文 [[文本]] 按"知识点区域"归属到对应知识点卡片内

let _configState = {
    files: [],
    fileTree: null,
    currentFile: null,
    currentData: null,        // {description, concepts, edges, links}
    selectedConceptIdxs: new Set(), // 多选
    lastClickedIdx: -1,       // Shift 范围选的锚点
    expandedSections: { concepts: true, edges: true },
    candidates: [],
    expandedConcepts: new Set(), // 展开的知识点卡片 idx（显示链接）
    expandedChildren: new Set(), // 展开的子节点 idx（显示子知识点）
};

/**
 * 将扁平的 concepts 数组按 heading depth 构建为树。
 * 规则：按 line 升序排列，depth 递增则入栈为子节点，depth 递减则出栈。
 * 每个 tree node: { concept, children: [], depth, expanded }
 */
function _buildConceptTree(concepts) {
    const sorted = concepts
        .map((c, idx) => ({ idx, concept: c, depth: c.depth || 0, line: c.line || 0 }))
        .filter(c => c.line > 0)  // 只有有行号（匹配到标题）才能参与树
        .sort((a, b) => a.line - b.line);

    const root = { concept: null, children: [], depth: 0, _idx: -1 };

    // 未匹配标题的 concept（line=0）单独收集
    const orphans = concepts
        .map((c, idx) => ({ idx, concept: c }))
        .filter(c => !c.concept.line);

    for (const item of sorted) {
        const node = { concept: item.concept, children: [], depth: item.depth, _idx: item.idx };
        // 从 root 往下找合适的父节点：从 root 的子节点出发，找到最后一个 depth < 当前 depth 的节点路径
        let parent = root;
        while (parent.children.length > 0) {
            const last = parent.children[parent.children.length - 1];
            if (last.depth < node.depth) {
                parent = last;
            } else {
                break;
            }
        }
        parent.children.push(node);
    }

    // orphans 作为无层级节点附加到 root 末尾
    orphans.forEach(o => {
        root.children.push({ concept: o.concept, children: [], depth: 0, _idx: o.idx });
    });

    return root;
}

// 扁平化树节点（用于保留引用到原 idx）
function _flattenTree(node) {
    const result = [];
    if (node._idx >= 0) result.push(node);
    for (const child of node.children) {
        result.push(..._flattenTree(child));
    }
    return result;
}

function initConfigButton() {
    const btn = document.getElementById('btn-config');
    if (btn) btn.addEventListener('click', openConfigWindow);
    const btnClose = document.getElementById('btn-config-close');
    if (btnClose) btnClose.addEventListener('click', closeConfigWindow);
    const btnCancel = document.getElementById('btn-config-cancel');
    if (btnCancel) btnCancel.addEventListener('click', closeConfigWindow);
    const btnSave = document.getElementById('btn-config-save');
    if (btnSave) btnSave.addEventListener('click', saveConfigAndRebuild);
}

function enableConfigButton() {
    const btn = document.getElementById('btn-config');
    if (btn) btn.disabled = false;
}

async function openConfigWindow() {
    document.getElementById('config-overlay').classList.remove('hidden');
    document.getElementById('config-panel').classList.remove('hidden');

    const editor = document.getElementById('config-editor');
    editor.innerHTML = '<p class="config-empty-hint">加载中...</p>';

    try {
        const result = await window.memoria.api.get_all_files();
        if (result.status === 'ok') {
            _configState.files = result.files || [];
            _configState.fileTree = buildFileTree(_configState.files);
            renderConfigFileTree();
            editor.innerHTML = '<p class="config-empty-hint">请从左侧选择一个文件</p>';
        } else {
            editor.innerHTML = `<p class="config-empty-hint">加载失败: ${result.message || ''}</p>`;
        }
    } catch (e) {
        editor.innerHTML = `<p class="config-empty-hint">加载异常: ${e}</p>`;
    }
}

function closeConfigWindow() {
    document.getElementById('config-overlay').classList.add('hidden');
    document.getElementById('config-panel').classList.add('hidden');
    _configState.currentFile = null;
    _configState.currentData = null;
}

// ---------- 文件树 ----------

function buildFileTree(files) {
    const root = { name: '', children: {}, files: [] };
    files.forEach(f => {
        const rel = f.relpath || f.file;
        const parts = rel.split(/[\\\/]/);
        let cur = root;
        for (let i = 0; i < parts.length - 1; i++) {
            const dir = parts[i];
            if (!cur.children[dir]) cur.children[dir] = { name: dir, children: {}, files: [] };
            cur = cur.children[dir];
        }
        cur.files.push(f);
    });
    return root;
}

// 递归渲染文件树（支持任意深度）
function renderConfigFileTree() {
    const container = document.getElementById('config-file-list');
    container.innerHTML = '';
    if (!_configState.fileTree) return;
    _renderTreeNode(_configState.fileTree, 0, container);
}

function _renderTreeNode(node, depth, parentEl) {
    // 文件夹（按字母序）
    Object.keys(node.children).sort().forEach(dn => {
        const dir = node.children[dn];
        const dirEl = document.createElement('div');
        dirEl.className = 'tree-folder';
        dirEl.style.paddingLeft = `${depth * 14 + 8}px`;
        dirEl.innerHTML = `<span class="tree-arrow">▶</span> <span class="tree-folder-name">📁 ${escapeHtml(dn)}</span>`;
        parentEl.appendChild(dirEl);

        const childContainer = document.createElement('div');
        childContainer.className = 'tree-folder-content hidden';
        parentEl.appendChild(childContainer);

        // 递归渲染子节点
        _renderTreeNode(dir, depth + 1, childContainer);

        dirEl.addEventListener('click', (e) => {
            e.stopPropagation();
            const arrow = dirEl.querySelector('.tree-arrow');
            const hidden = childContainer.classList.toggle('hidden');
            arrow.textContent = hidden ? '▶' : '▼';
        });
    });
    // 文件
    node.files.forEach(f => {
        const fileName = (f.relpath || f.file).split(/[\\\/]/).pop();
        const item = document.createElement('div');
        item.className = 'tree-file';
        item.dataset.file = f.file;
        if (f.file === _configState.currentFile) item.classList.add('active');
        item.style.paddingLeft = `${depth * 14 + 22}px`;
        item.innerHTML = `
            <span class="tree-file-name">📄 ${escapeHtml(fileName)}</span>
            <span class="tree-file-meta">${f.concept_count} 概念</span>
        `;
        item.addEventListener('click', () => loadFileConfig(f.file));
        parentEl.appendChild(item);
    });
}

// 只更新文件树的高亮，不重新渲染（保留展开状态）
function _updateTreeHighlight() {
    document.querySelectorAll('#config-file-list .tree-file').forEach(el => {
        if (el.dataset.file === _configState.currentFile) {
            el.classList.add('active');
        } else {
            el.classList.remove('active');
        }
    });
}

// ---------- 文件配置加载 ----------

async function loadFileConfig(filePath) {
    _configState.currentFile = filePath;
    _updateTreeHighlight();  // 只更新高亮，不重渲染树

    const editor = document.getElementById('config-editor');
    editor.innerHTML = '<p class="config-empty-hint">加载中...</p>';

    try {
        const result = await window.memoria.api.get_file_config(filePath);
        if (result.status !== 'ok') {
            editor.innerHTML = `<p class="config-empty-hint">加载失败: ${result.message}</p>`;
            return;
        }
        _configState.currentData = {
            description: result.description || '',
            concepts: result.concepts || [],
            edges: result.edges || [],
            links: result.links || [],
        };
        _configState.selectedConceptIdxs = new Set();
        _configState.lastClickedIdx = -1;
        _configState.candidates = [];
        _configState.expandedConcepts = new Set();
        _configState.expandedChildren = new Set();
        renderConfigEditor();
    } catch (e) {
        editor.innerHTML = `<p class="config-empty-hint">异常: ${e}</p>`;
    }
}

// ---------- 链接归属计算（按知识点区域） ----------

/**
 * 把 links 按"知识点区域"分组。
 * 规则：concepts 按 line 排序，相邻 concept line 之间的链接归前一个 concept。
 * line=0（未匹配标题）的 concept 不参与区域划分，其链接归"未分配"。
 * 链接 line < 第一个有 line 的 concept → 未分配。
 *
 * Returns: { assigned: {conceptIdx: [linkIdx...]}, unassigned: [linkIdx...] }
 */
function _groupLinksByConcept() {
    const data = _configState.currentData;
    if (!data) return { assigned: {}, unassigned: [] };

    // 有 line 的 concepts，按 line 升序，记录原 idx
    const sorted = data.concepts
        .map((c, idx) => ({ idx, line: c.line || 0 }))
        .filter(c => c.line > 0)
        .sort((a, b) => a.line - b.line);

    const assigned = {};
    sorted.forEach(c => { assigned[c.idx] = []; });
    const unassigned = [];

    data.links.forEach((link, li) => {
        const ll = link.line || 0;
        // 找到 line 最大的、且 < ll 的 concept
        let owner = -1;
        for (const c of sorted) {
            if (c.line <= ll) owner = c.idx;
            else break;
        }
        if (owner >= 0) assigned[owner].push(li);
        else unassigned.push(li);
    });
    return { assigned, unassigned };
}

// ---------- 主编辑区渲染 ----------

function renderConfigEditor() {
    const editor = document.getElementById('config-editor');
    const data = _configState.currentData;
    if (!data) return;

    editor.innerHTML = `
        <div class="cfg-section-flat">
            <div class="cfg-section-title">文件描述</div>
            <textarea id="cfg-description" class="cfg-textarea-flat" rows="2" placeholder="文件的简短描述">${escapeHtml(data.description || '')}</textarea>
        </div>

        <div class="cfg-section-flat">
            <div class="cfg-section-title" id="cfg-toggle-concepts">
                <span class="cfg-arrow">${_configState.expandedSections.concepts ? '▼' : '▶'}</span>
                知识点配置
                <span class="cfg-count">(${data.concepts.length})</span>
            </div>
            <div id="cfg-concepts-body" class="${_configState.expandedSections.concepts ? '' : 'hidden'}">
                <div class="cfg-concepts-toolbar">
                    <button class="cfg-btn-sm" id="cfg-concept-add">+ 新建</button>
                    <button class="cfg-btn-sm cfg-btn-primary" id="cfg-concept-auto">✨ 自动解析</button>
                    <button class="cfg-btn-sm cfg-btn-ai" id="cfg-concept-ai" disabled title="智能识别（即将推出）">🧠 AI 分析</button>
                    <button class="cfg-btn-sm cfg-btn-danger" id="cfg-concept-del">✕ 删除选中</button>
                    <span class="cfg-toolbar-hint" id="cfg-sel-count"></span>
                </div>
                <div class="cfg-list-title">
                    知识点树（按标题层级自动嵌套，点击卡片展开链接，Ctrl+点击多选，右键编辑）
                    <span class="cfg-hint-nesting">包含关系由层级自动推导</span>
                </div>
                <div id="cfg-concepts-tree" class="cfg-tree-flat"></div>
                <div class="cfg-list-title">候选知识点（来自自动解析，点击添加到上栏）</div>
                <div id="cfg-candidates-list" class="cfg-list-flat"></div>
            </div>
        </div>

        <div class="cfg-section-flat">
            <div class="cfg-section-title" id="cfg-toggle-edges">
                <span class="cfg-arrow">${_configState.expandedSections.edges ? '▼' : '▶'}</span>
                边配置
                <span class="cfg-count">(${data.edges.length})</span>
            </div>
            <div id="cfg-edges-body" class="${_configState.expandedSections.edges ? '' : 'hidden'}">
                <div class="cfg-edges-toolbar">
                    <span class="cfg-hint-sm">强边「—」实线吸引强 · 弱边「- -」短虚线吸引弱。包含边由树自动推导。</span>
                </div>
                <div id="cfg-edges-list" class="cfg-list-flat"></div>
            </div>
        </div>
    `;

    renderConceptsTree();
    renderCandidatesList();
    renderEdgesList();

    // 折叠切换
    document.getElementById('cfg-toggle-concepts').addEventListener('click', () => {
        _configState.expandedSections.concepts = !_configState.expandedSections.concepts;
        renderConfigEditor();
    });
    document.getElementById('cfg-toggle-edges').addEventListener('click', () => {
        _configState.expandedSections.edges = !_configState.expandedSections.edges;
        renderConfigEditor();
    });

    // 工具栏
    document.getElementById('cfg-concept-add').addEventListener('click', addConcept);
    document.getElementById('cfg-concept-del').addEventListener('click', deleteSelectedConcepts);
    document.getElementById('cfg-concept-auto').addEventListener('click', autoExtractConcepts);
}

// ---------- 知识点树渲染（取代平铺列表 + 上下移） ----------

function renderConceptsTree() {
    const container = document.getElementById('cfg-concepts-tree');
    if (!container) return;
    const data = _configState.currentData;
    const tree = _buildConceptTree(data.concepts);
    container.innerHTML = '';

    if (tree.children.length === 0) {
        container.innerHTML = '<p class="cfg-empty-sm">暂无知识点，点击"自动解析"或"+ 新建"</p>';
        _updateSelCount();
        return;
    }

    tree.children.forEach(node => _renderTreeNode(node, container, 0));
    _updateSelCount();
}

function _renderTreeNode(node, parentEl, indent) {
    const idx = node._idx;
    const c = node.concept;
    const linkGroups = _groupLinksByConcept();
    const isSelected = _configState.selectedConceptIdxs.has(idx);
    const isLinkOpen = _configState.expandedConcepts.has(idx);
    const isChildOpen = _configState.expandedChildren.has(idx);

    const card = document.createElement('div');
    card.className = 'cfg-concept-card';
    if (isSelected) card.classList.add('selected');
    if (isLinkOpen) card.classList.add('expanded');

    const hasId = !!c.id;
    const tagsStr = (c.tags || []).join(', ');
    const linkCount = (linkGroups.assigned[idx] || []).length;
    const childCount = node.children.length;

    const headerStyle = `padding-left: ${indent * 16 + 8}px`;

    card.innerHTML = `
        <div class="cfg-concept-card-header" style="${headerStyle}">
            ${childCount > 0
                ? `<span class="cfg-tree-toggle" data-toggle="children">${isChildOpen ? '▼' : '▶'}</span>`
                : '<span class="cfg-tree-toggle-placeholder"></span>'}
            <span class="cfg-concept-name">${escapeHtml(c.name || '(无名)')}</span>
            ${hasId ? `<span class="cfg-concept-id">#${escapeHtml(c.id)}</span>` : ''}
            <span class="cfg-concept-loc">H${c.depth||0}</span>
            ${c.line ? `<span class="cfg-concept-loc">行 ${c.line}</span>` : ''}
            <span class="cfg-concept-links-badge" title="该知识点区域内的链接数">🔗 ${linkCount}</span>
            ${childCount > 0 ? `<span class="cfg-child-count">⊞ ${childCount}</span>` : ''}
            ${tagsStr ? `<span class="cfg-concept-tags">${escapeHtml(tagsStr)}</span>` : ''}
            <span class="cfg-concept-expand" title="展开/收起链接">${isLinkOpen ? '▼' : '▶'}</span>
        </div>
        <div class="cfg-concept-card-body ${isLinkOpen ? '' : 'hidden'}"></div>
        <div class="cfg-children-container ${isChildOpen ? '' : 'hidden'}" style="padding-left: ${indent * 16 + 8}px"></div>
    `;

    parentEl.appendChild(card);

    // 渲染链接列表
    const body = card.querySelector('.cfg-concept-card-body');
    const linkIdxs = linkGroups.assigned[idx] || [];
    if (linkIdxs.length === 0) {
        body.innerHTML = '<p class="cfg-empty-sm">该区域无链接</p>';
    } else {
        linkIdxs.forEach(li => {
            const link = _configState.currentData.links[li];
            const row = document.createElement('div');
            row.className = 'cfg-link-item';
            row.innerHTML = `
                <span class="cfg-link-text">[[${escapeHtml(link.text)}]]</span>
                <span class="cfg-link-line">行 ${link.line}</span>
                <select class="cfg-link-select" data-link-idx="${li}">
                    ${_buildLinkTargetOptions(link.text)}
                </select>
                <button class="cfg-del-btn" data-link-idx="${li}" title="删除此链接">✕</button>
            `;
            body.appendChild(row);
        });
        body.querySelectorAll('.cfg-link-select').forEach(sel => {
            sel.addEventListener('change', (e) => {
                const li = parseInt(e.target.dataset.linkIdx);
                const val = e.target.value;
                if (val) {
                    const [kind, target] = val.split(':', 2);
                    const oldText = _configState.currentData.links[li].text;
                    _configState.currentData.links[li].text = `${target}|${oldText}`;
                }
            });
        });
        body.querySelectorAll('.cfg-del-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const li = parseInt(e.target.dataset.linkIdx);
                _configState.currentData.links[li]._deleted = true;
                renderConceptsTree();
            });
        });
    }

    // 渲染子节点
    const childrenContainer = card.querySelector('.cfg-children-container');
    node.children.forEach(child => _renderTreeNode(child, childrenContainer, indent + 1));

    // ===== 事件绑定 =====
    card.addEventListener('click', (e) => {
        // 点击 body 不触发
        if (e.target.closest('.cfg-concept-card-body')) return;
        if (e.target.closest('select') || e.target.closest('button')) return;

        // 点击子节点展开/收起按钮
        if (e.target.closest('[data-toggle="children"]')) {
            e.stopPropagation();
            if (_configState.expandedChildren.has(idx)) {
                _configState.expandedChildren.delete(idx);
            } else {
                _configState.expandedChildren.add(idx);
            }
            renderConceptsTree();
            return;
        }

        // Ctrl/Shift 多选
        if (e.ctrlKey || e.metaKey || e.shiftKey) {
            if (!e.shiftKey || _configState.lastClickedIdx < 0) {
                if (e.ctrlKey || e.metaKey) {
                    if (_configState.selectedConceptIdxs.has(idx)) {
                        _configState.selectedConceptIdxs.delete(idx);
                    } else {
                        _configState.selectedConceptIdxs.add(idx);
                    }
                    _configState.lastClickedIdx = idx;
                }
            } else {
                const sorted = _configState.currentData.concepts.map((_, i) => i);
                const start = Math.min(_configState.lastClickedIdx, idx);
                const end = Math.max(_configState.lastClickedIdx, idx);
                for (let i = start; i <= end; i++) _configState.selectedConceptIdxs.add(i);
            }
        } else {
            // 普通点击：展开/收起链接
            if (_configState.expandedConcepts.has(idx)) {
                _configState.expandedConcepts.delete(idx);
            } else {
                _configState.expandedConcepts.add(idx);
            }
        }
        renderConceptsTree();
    });

    // 右键菜单
    card.addEventListener('contextmenu', (e) => {
        if (e.target.closest('.cfg-concept-card-body')) return;
        e.preventDefault();
        if (!_configState.selectedConceptIdxs.has(idx)) {
            _configState.selectedConceptIdxs.clear();
            _configState.selectedConceptIdxs.add(idx);
            _configState.lastClickedIdx = idx;
            renderConceptsTree();
        }
        showConceptContextMenu(e.clientX, e.clientY, idx);
    });
}

function _buildLinkTargetOptions(currentText) {
    // 当前文本可能含 |：[[id|display]]
    const displayText = currentText.split('|')[0];
    const options = ['<option value="">（未分配）</option>'];
    _configState.currentData.concepts.forEach(c => {
        if (c.id) {
            const sel = (c.id === displayText) ? 'selected' : '';
            options.push(`<option value="id:${escapeHtml(c.id)}" ${sel}>知识点 #${escapeHtml(c.id)} (${escapeHtml(c.name)})</option>`);
        }
    });
    return options.join('');
}

function _updateSelCount() {
    const el = document.getElementById('cfg-sel-count');
    if (el) {
        const n = _configState.selectedConceptIdxs.size;
        el.textContent = n > 0 ? `已选 ${n} 项` : '';
    }
}

// ---------- 候选知识点（下栏，与上栏相同样式） ----------

function renderCandidatesList() {
    const container = document.getElementById('cfg-candidates-list');
    if (!container) return;
    const cands = _configState.candidates;
    container.innerHTML = '';

    if (cands.length === 0) {
        container.innerHTML = '<p class="cfg-empty-sm">点击"自动解析"识别候选知识点</p>';
        return;
    }

    cands.forEach((c, idx) => {
        const card = document.createElement('div');
        card.className = 'cfg-concept-card cfg-candidate-card';
        const srcLabel = c.source === 'heading' ? '标题' : '关键词';
        const existsLabel = c.exists
            ? '<span class="badge badge-exists">已存在</span>'
            : '<span class="badge badge-new">新建</span>';
        card.innerHTML = `
            <div class="cfg-concept-card-header">
                <span class="cfg-concept-name">${escapeHtml(c.text)}</span>
                <span class="cfg-concept-loc">[${srcLabel}]</span>
                ${existsLabel}
            </div>
        `;
        // 点击卡片即可添加（选中）
        card.addEventListener('click', (e) => {
            e.stopPropagation();
            if (!c.exists) acceptCandidate(idx);
        });
        container.appendChild(card);
    });
}

// ---------- 知识点操作（多选） ----------

function showConceptContextMenu(x, y, idx) {
    const items = [
        { label: '✎ 编辑知识点', action: () => editConcept(idx) },
        { label: '✕ 删除选中', action: () => deleteSelectedConcepts() },
    ];
    if (typeof showContextMenu === 'function') {
        showContextMenu(x, y, items);
    } else {
        editConcept(idx);
    }
}

async function editConcept(idx) {
    const c = _configState.currentData.concepts[idx];
    if (!c) return;
    if (typeof showFormDialog === 'function') {
        const result = await showFormDialog('编辑知识点', [
            { key: 'id', label: 'ID（有 id=知识点，无=标签）', value: c.id || '' },
            { key: 'name', label: '名称（与正文标题一致可自动定位区域）', value: c.name || '' },
            { key: 'tags', label: '标签（逗号分隔）', value: (c.tags || []).join(', ') },
            { key: 'weight', label: '权重', value: String(c.weight || 0.5) },
        ]);
        if (result) {
            c.id = (result.id || '').trim();
            c.name = (result.name || '').trim();
            c.tags = (result.tags || '').split(',').map(s => s.trim()).filter(s => s);
            c.weight = parseFloat(result.weight) || 0.5;
            c.line = 0;
            c.depth = 0;
            renderConceptsTree();
        }
    }
}

function addConcept() {
    _configState.currentData.concepts.push({ id: '', name: '', weight: 0.5, tags: [], line: 0, depth: 0 });
    const newIdx = _configState.currentData.concepts.length - 1;
    _configState.selectedConceptIdxs.clear();
    _configState.selectedConceptIdxs.add(newIdx);
    _configState.lastClickedIdx = newIdx;
    renderConceptsTree();
    editConcept(newIdx);
}

function deleteSelectedConcepts() {
    if (_configState.selectedConceptIdxs.size === 0) {
        showAlert('请先选中知识点', '提示');
        return;
    }
    const idxs = Array.from(_configState.selectedConceptIdxs).sort((a, b) => b - a);
    idxs.forEach(i => _configState.currentData.concepts.splice(i, 1));
    _configState.selectedConceptIdxs.clear();
    _configState.lastClickedIdx = -1;
    renderConceptsTree();
}

// moveConcepts 已废弃——树形结构中排序由 heading 层级决定

async function autoExtractConcepts() {
    if (!_configState.currentFile) return;
    setStatus('正在解析知识点候选...');
    try {
        const result = await window.memoria.api.extract_concept_suggestions(_configState.currentFile);
        if (result.status === 'ok') {
            _configState.candidates = result.candidates || [];
            renderCandidatesList();
            setStatus(`解析完成：${_configState.candidates.length} 个候选`);
        } else {
            showAlert('解析失败: ' + (result.message || ''), '错误');
        }
    } catch (e) {
        showAlert('解析异常: ' + e, '错误');
    }
}

function acceptCandidate(idx) {
    const cand = _configState.candidates[idx];
    if (!cand) return;
    _configState.currentData.concepts.push({
        id: cand.matched_id || '',
        name: cand.text,
        weight: 0.5,
        tags: [],
        line: cand.line || 0,
        depth: 0,
    });
    _configState.selectedConceptIdxs.clear();
    _configState.selectedConceptIdxs.add(_configState.currentData.concepts.length - 1);
    _configState.lastClickedIdx = _configState.currentData.concepts.length - 1;
    _configState.candidates.splice(idx, 1);
    renderConceptsTree();
    renderCandidatesList();
}

// ---------- 边配置列表 ----------

function renderEdgesList() {
    const container = document.getElementById('cfg-edges-list');
    if (!container) return;
    const edges = _configState.currentData.edges || [];
    const concepts = _configState.currentData.concepts || [];
    const nameById = {};
    concepts.forEach(c => { if (c.id) nameById[c.id] = c.name || c.id; });

    container.innerHTML = '';

    if (edges.length === 0) {
        container.innerHTML = '<p class="cfg-empty-sm">暂无边，包含关系由知识点树自动推导</p>';
        return;
    }

    edges.forEach((e, idx) => {
        const isAutoInclude = e.type === '包含';
        const targets = (e.targets || []).map(t =>
            nameById[t] ? `${nameById[t]} (#${t})` : `#${t}`
        ).join(', ') || '(无目标)';
        const strength = e.strength || 'strong';

        const card = document.createElement('div');
        card.className = 'cfg-edge-card';
        card.innerHTML = `
            <div class="cfg-edge-header">
                <span class="cfg-edge-type ${isAutoInclude ? 'include' : ''}">${escapeHtml(e.type)}</span>
                <span class="cfg-edge-targets">→ ${escapeHtml(targets)}</span>
                ${e.text ? `<span class="cfg-edge-text">[${escapeHtml(e.text)}]</span>` : ''}
                ${isAutoInclude ? '<span class="badge badge-auto">自动</span>' : `
                    <select class="cfg-strength-select" data-edge-idx="${idx}">
                        <option value="strong" ${strength === 'strong' ? 'selected' : ''}>强边 — 实线</option>
                        <option value="weak" ${strength === 'weak' ? 'selected' : ''}>弱边 - - 虚线</option>
                    </select>
                `}
            </div>
        `;
        container.appendChild(card);

        if (!isAutoInclude) {
            card.querySelector('.cfg-strength-select').addEventListener('change', (ev) => {
                e.strength = ev.target.value;
            });
        }
    });
}

// ---------- 保存 ----------

/**
 * 从概念的树形层级自动推导"包含"边。
 * parent 是其直接子级（depth 严格大 1 的第一个子级 series）的"包含"者。
 */
function _deriveIncludeEdges(concepts) {
    const tree = _buildConceptTree(concepts);
    const edges = [];

    function walk(node) {
        for (const child of node.children) {
            if (node._idx >= 0 && child._idx >= 0) {
                const parentId = node.concept.id;
                const childId = child.concept.id;
                if (parentId && childId) {
                    edges.push({ type: '包含', targets: [childId] });
                }
            }
            walk(child);
        }
    }
    walk(tree);
    return edges;
}

async function saveConfigAndRebuild() {
    if (!_configState.currentFile || !_configState.currentData) {
        showAlert('未选择文件', '提示');
        return;
    }

    const desc = document.getElementById('cfg-description').value;
    const data = _configState.currentData;

    // 清理空 concept，仅保留持久化字段
    const cleanedConcepts = data.concepts
        .filter(c => c.id || c.name)
        .map(c => {
            const cleaned = { id: c.id || '', name: c.name || '', weight: c.weight ?? 0.5 };
            if (c.tags && c.tags.length > 0) cleaned.tags = c.tags;
            return cleaned;
        });

    // 从树形层级自动推导"包含"边，保留用户定义的其他边
    const userEdges = data.edges.filter(e => e.type !== '包含');
    const includeEdges = _deriveIncludeEdges(data.concepts);
    data.edges = [...userEdges, ...includeEdges];

    // 处理标记删除的链接：需要回写正文
    // 简化：先调用 save_file_config 保存 frontmatter，链接删除需要单独 API
    // 此处仅保存 concepts/edges

    try {
        const result = await window.memoria.api.save_file_config(
            _configState.currentFile, desc, cleanedConcepts, data.edges
        );
        if (result.status === 'ok') {
            setStatus('配置已保存，正在重建索引...');
            const buildResult = await window.memoria.api.build_index();
            if (buildResult.status === 'ok') {
                await _applyIndexResult(buildResult, false);
                setStatus('配置已保存并重建完成');
                const refresh = await window.memoria.api.get_all_files();
                if (refresh.status === 'ok') {
                    _configState.files = refresh.files || [];
                    _configState.fileTree = buildFileTree(_configState.files);
                    renderConfigFileTree();
                }
                showAlert('保存并重建成功', '成功');
                // 重新加载当前文件配置（刷新 line）
                await loadFileConfig(_configState.currentFile);
            } else {
                showAlert('重建失败: ' + (buildResult.message || ''), '错误');
            }
        } else {
            showAlert('保存失败: ' + (result.message || ''), '错误');
        }
    } catch (e) {
        showAlert('异常: ' + e, '错误');
    }
}

window.addEventListener('pywebviewready', () => {
    setTimeout(initConfigButton, 100);
});
setTimeout(() => {
    if (!window.memoria) {
        setTimeout(initConfigButton, 100);
    }
}, 3500);
