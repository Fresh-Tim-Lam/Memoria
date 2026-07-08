// ========== 链接右键菜单 + 多目标队列管理 ==========

/**
 * 可剔除中间节点的队列数据结构
 * 用于管理多目标链接跳转：第一个=主跳转，其余=文件列表
 * 支持从中间剔除、移动到队首、查看队列状态
 */
class LinkTargetQueue {
    constructor() {
        this.items = [];  // [{nodeId, file, title}, ...]
    }

    /** 入队 */
    enqueue(item) {
        this.items.push(item);
    }

    /** 取队首（主跳转目标） */
    first() {
        return this.items.length > 0 ? this.items[0] : null;
    }

    /** 除队首外的所有项（加入文件列表） */
    rest() {
        return this.items.slice(1);
    }

    /** 按索引移除（可剔除中间节点） */
    removeAt(index) {
        if (index < 0 || index >= this.items.length) return null;
        return this.items.splice(index, 1)[0];
    }

    /** 按 nodeId 移除 */
    removeByNodeId(nodeId) {
        const idx = this.items.findIndex(i => i.nodeId === nodeId);
        if (idx === -1) return false;
        this.items.splice(idx, 1);
        return true;
    }

    /** 把某项移到队首（提升为主跳转） */
    moveToFront(index) {
        if (index < 0 || index >= this.items.length) return;
        const [item] = this.items.splice(index, 1);
        this.items.unshift(item);
    }

    /** 队列长度 */
    size() {
        return this.items.length;
    }

    /** 是否为空 */
    isEmpty() {
        return this.items.length === 0;
    }

    /** 清空 */
    clear() {
        this.items = [];
    }

    /** 获取所有项 */
    all() {
        return [...this.items];
    }
}

// 当前待处理的链接队列（多目标时使用）
let activeLinkQueue = new LinkTargetQueue();

/**
 * 显示链接右键菜单
 * @param {MouseEvent} e contextmenu 事件
 * @param {HTMLElement} linkEl 触发的 <a> 元素（可为实链/虚链/autolink）
 * @param {string} sourceNodeId 当前节点 id（用于后端操作）
 */
function showLinkContextMenu(e, linkEl, sourceNodeId) {
    e.preventDefault();
    e.stopPropagation();

    const targetId = linkEl.getAttribute('data-node-id') || '';
    const isBroken = linkEl.classList.contains('memoria-broken-link');
    const isAutoLink = linkEl.classList.contains('memoria-autolink');
    const linkText = linkEl.textContent || '';

    // 移除已有菜单
    hideLinkContextMenu();

    const menu = document.createElement('div');
    menu.id = 'link-context-menu';
    menu.className = 'link-context-menu';

    const items = [];

    // 编辑链接 id（联动所有文件）
    items.push({ label: '✎ 修改此知识点 id（全局联动）', action: async () => {
        const newId = await showPrompt('输入新的知识点 id（将联动修改所有文件中的引用）：', targetId, '修改知识点 id');
        if (newId && newId !== targetId) {
            changeLinkIdGlobal(targetId, newId);
        }
    }});

    // 在配置窗口中编辑此链接所在文件
    items.push({ label: '⚙ 在配置窗口中编辑此文件', action: async () => {
        if (typeof openConfigWindow === 'function') {
            await openConfigWindow();
            // 如果能找到链接所在文件，自动加载
            if (sourceNodeId) {
                const node = findNode(sourceNodeId);
                if (node && node.file && typeof loadFileConfig === 'function') {
                    setTimeout(() => loadFileConfig(node.file), 300);
                }
            }
        }
    }});

    // 添加新链接（对选中文本）
    if (window.getSelection().toString().trim()) {
        const selText = window.getSelection().toString().trim();
        items.push({ label: '🔗 把选中文本加为链接', action: async () => {
            const newId = await showPrompt(`把 "${selText}" 链接到 id：`, '', '添加链接');
            if (newId && sourceNodeId) {
                wrapKeywordWithLinkApi(sourceNodeId, newId, selText);
            }
        }});
    }

    items.push({ divider: true });

    // 删除链接
    if (isAutoLink) {
        // autolink 是隐式渲染的，删除=加入黑名单（不修改文件）
        items.push({ label: '🚫 移除此自动链接（本地）', action: async () => {
            const ok = await showConfirm(`移除此自动链接？\n关键词: ${linkText}\nid: ${targetId}\n（仅本地隐藏，不修改文件）`, '确认');
            if (ok) {
                addToAutolinkBlacklist(sourceNodeId, targetId, linkText);
                linkEl.outerHTML = linkText;  // 恢复纯文本
            }
        }});
    } else {
        // [[]] 语法链接，删除=移除包裹（修改文件）
        items.push({ label: '🗑 删除链接（移除 [[]] 包裹）', action: async () => {
            const ok = await showConfirm(`删除文件中的此链接？\n关键词: ${linkText}\nid: ${targetId}`, '确认删除');
            if (ok && sourceNodeId) {
                removeLinkFromFile(sourceNodeId, targetId, linkText);
            }
        }});
    }

    // 构建菜单 DOM
    items.forEach(it => {
        if (it.divider) {
            const div = document.createElement('div');
            div.className = 'ctx-menu-divider';
            menu.appendChild(div);
        } else {
            const div = document.createElement('div');
            div.className = 'ctx-menu-item';
            div.textContent = it.label;
            div.addEventListener('click', () => {
                hideLinkContextMenu();
                it.action();
            });
            menu.appendChild(div);
        }
    });

    document.body.appendChild(menu);

    // 定位菜单（避免超出视口）
    const rect = menu.getBoundingClientRect();
    let x = e.clientX;
    let y = e.clientY;
    if (x + rect.width > window.innerWidth) x = window.innerWidth - rect.width - 4;
    if (y + rect.height > window.innerHeight) y = window.innerHeight - rect.height - 4;
    menu.style.left = x + 'px';
    menu.style.top = y + 'px';
}

function hideLinkContextMenu() {
    document.getElementById('link-context-menu')?.remove();
}

document.addEventListener('click', hideLinkContextMenu);
document.addEventListener('scroll', hideLinkContextMenu, true);

// ========== 选中文本右键菜单（创建链接） ==========

/**
 * 阅读区选中文本后右键，弹出"创建链接"菜单
 * @param {Event} e contextmenu 事件
 * @param {string} text 选中的文本
 * @param {string} sourceNodeId 当前文件节点 id
 */
function showSelectionContextMenu(e, text, sourceNodeId) {
    // 移除已有菜单
    document.getElementById('link-context-menu')?.remove();

    const menu = document.createElement('div');
    menu.id = 'link-context-menu';
    menu.className = 'custom-context-menu';
    menu.style.left = e.clientX + 'px';
    menu.style.top = e.clientY + 'px';

    // 查询该文本是否已有对应知识点
    const index = window.memoria.state.index;
    const concepts = (index && index.concepts) || [];
    const matches = concepts.filter(c => c.name === text || c.id === text);

    const items = [];

    if (matches.length === 1) {
        // 唯一匹配：直接创建链接到该知识点
        items.push({
            label: `🔗 创建链接 → ${matches[0].name} (#${matches[0].id})`,
            action: () => createLinkFromSelection(text, matches[0].id, sourceNodeId),
        });
    } else if (matches.length > 1) {
        // 多匹配：让用户选择
        matches.forEach(m => {
            items.push({
                label: `🔗 链接到 ${m.name} (#${m.id})`,
                action: () => createLinkFromSelection(text, m.id, sourceNodeId),
            });
        });
    } else {
        // 无匹配：创建新知识点并链接
        items.push({
            label: `✨ 创建新知识点 "${text}" 并链接`,
            action: () => createLinkFromSelection(text, '', sourceNodeId, true),
        });
        // 或作为虚链
        items.push({
            label: `❓ 作为虚链 [[${text}]]`,
            action: () => createLinkFromSelection(text, '', sourceNodeId, false),
        });
    }

    items.forEach(item => {
        const mi = document.createElement('div');
        mi.className = 'context-menu-item';
        mi.textContent = item.label;
        mi.addEventListener('click', () => {
            hideLinkContextMenu();
            item.action();
        });
        menu.appendChild(mi);
    });

    document.body.appendChild(menu);
}

/**
 * 在正文里把选中文本替换为 [[id|text]] 或 [[text]]
 * @param {string} text 选中文本（作为显示文本）
 * @param {string} targetId 目标知识点 id（空则虚链）
 * @param {string} sourceNodeId 当前文件节点 id
 * @param {boolean} createConcept 是否同时创建新知识点（id 为空时才有效）
 */
async function createLinkFromSelection(text, targetId, sourceNodeId, createConcept = false) {
    try {
        // 读取当前文件内容
        const result = await window.memoria.api.get_node_raw(sourceNodeId);
        if (result.status !== 'ok') {
            showAlert('读取文件失败: ' + (result.message || ''), '错误');
            return;
        }
        let content = result.content;

        // 创建新知识点（如果需要）
        if (createConcept && !targetId && sourceNodeId) {
            // 生成新 id（用文本作为 id，去除空格）
            const newId = text.replace(/\s+/g, '_').slice(0, 30);
            // 在当前文件的 frontmatter 添加 concept
            const node = findNode(sourceNodeId);
            if (node) {
                // 调用保存配置 API 增加 concept
                const cfg = await window.memoria.api.get_file_config(node.file);
                if (cfg.status === 'ok') {
                    cfg.concepts.push({
                        id: newId, name: text, weight: 0.5, tags: [],
                    });
                    await window.memoria.api.save_file_config(
                        node.file, cfg.description, cfg.concepts, cfg.edges
                    );
                    targetId = newId;
                }
            }
        }

        // 替换正文中第一个出现的 text 为 [[targetId|text]] 或 [[text]]
        // 避开 frontmatter 和已有的 [[...]] 内部
        const fmMatch = content.match(/^---\n[\s\S]*?\n---\n/);
        let body = fmMatch ? content.slice(fmMatch[0].length) : content;
        const fmPart = fmMatch ? fmMatch[0] : '';

        // 只替换非 [[ 内的文本
        // 简化策略：先 escape regex 特殊字符
        const escaped = text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        // 排除已在 [[xxx|text]] 或 [[text]] 内部的匹配
        const linkRe = new RegExp(`(?<!\\[\\[[^\\]|]*\\|?)(${escaped})(?!\\]\\])`, '');
        if (linkRe.test(body)) {
            const replacement = targetId ? `[[${targetId}|${text}]]` : `[[${text}]]`;
            body = body.replace(linkRe, replacement);
            const newContent = fmPart + body;
            const saveRes = await window.memoria.api.save_node_raw(sourceNodeId, newContent);
            if (saveRes.status === 'ok') {
                showAlert('链接已创建', '成功');
                if (typeof buildIndex === 'function') await buildIndex();
                if (typeof loadNodeContent === 'function') await loadNodeContent(sourceNodeId);
            } else {
                showAlert('保存失败: ' + (saveRes.message || ''), '错误');
            }
        } else {
            showAlert('未在正文中找到选中文本（可能已在链接内）', '提示');
        }
    } catch (e) {
        showAlert('异常: ' + (e.message || e), '错误');
    }
}

// ========== 后端操作辅助 ==========

/**
 * 在 markdown 内容中替换链接 id，保留原渲染文本不变
 *
 * 设计哲学：id 是隐式的，渲染文本与关键字绑定。
 * 修改 id 前后用户看到的链接文字必须完全一致。
 *
 * 替换规则：
 *   [[oldId]]             → [[newId|oldId]]           （原渲染=oldId，补 |oldId 保留）
 *   [[oldId#anchor]]      → [[newId#anchor|oldId]]
 *   [[oldId|text]]        → [[newId|text]]            （原渲染=text，不变）
 *   [[oldId#anchor|text]] → [[newId#anchor|text]]
 *
 * 封装此方法是为了避免其他地方做"修改 id"时遗漏保留文本，导致渲染不一致。
 *
 * @param {string} content 原始 markdown 内容
 * @param {string} oldId 旧链接 id
 * @param {string} newId 新链接 id
 * @returns {string} 替换后的内容
 */
function replaceLinkIdPreservingText(content, oldId, newId) {
    const re = new RegExp(`\\[\\[${escapeRegExp(oldId)}(#[^\\]|]*)?(\\|([^\\]]*))?\\]\\]`, 'g');
    return content.replace(re, (m, anchor, pipe, text) => {
        // 保留原渲染文本：有 |text 用 text；否则 [[oldId]] 默认渲染 oldId，补 |oldId
        const preservedText = (text !== undefined && text !== '') ? text : oldId;
        return `[[${newId}${anchor || ''}|${preservedText}]]`;
    });
}

/**
 * 修改文件中的链接 id，保留渲染文本不变
 * 详见 replaceLinkIdPreservingText 的替换规则。
 */
async function changeLinkId(sourceNodeId, oldId, newId) {
    try {
        const result = await window.memoria.api.get_node_raw(sourceNodeId);
        if (result.status !== 'ok') {
            showAlert('读取文件失败: ' + (result.message || ''), '错误');
            return;
        }
        const newContent = replaceLinkIdPreservingText(result.content, oldId, newId);
        const saveRes = await window.memoria.api.save_node_raw(sourceNodeId, newContent);
        if (saveRes.status === 'ok') {
            if (typeof buildIndex === 'function') await buildIndex();
            if (typeof loadNodeContent === 'function') await loadNodeContent(sourceNodeId);
        } else {
            showAlert('保存失败: ' + (saveRes.message || ''), '错误');
        }
    } catch (e) {
        showAlert('异常: ' + (e.message || ''), '错误');
    }
}

/**
 * 全局修改知识点 id（联动所有文件的 concepts/edges/正文引用）
 * 使用后端 replace_link_id API，保留渲染文本不变。
 */
async function changeLinkIdGlobal(oldId, newId) {
    try {
        const result = await window.memoria.api.replace_link_id(oldId, newId);
        if (result.status === 'ok') {
            const count = (result.modified_files || []).length;
            showAlert(`已修改 ${count} 个文件，正在重建索引...`, '成功');
            if (typeof buildIndex === 'function') await buildIndex();
            // 重新加载当前 tab 内容
            if (window.memoria.state.activeTab) {
                const tab = window.memoria.state.tabs.find(t => t.id === window.memoria.state.activeTab);
                if (tab && typeof loadNodeContent === 'function') {
                    await loadNodeContent(tab.nodeId);
                }
            }
        } else {
            showAlert('修改失败: ' + (result.message || ''), '错误');
        }
    } catch (e) {
        showAlert('异常: ' + (e.message || ''), '错误');
    }
}

/**
 * 调用后端 wrap_link 把关键词包装为 [[id|keyword]]
 */
async function wrapKeywordWithLinkApi(sourceNodeId, targetId, keyword) {
    try {
        const result = await window.memoria.api.apply_auto_links([{
            type: 'wrap_link',
            node_id: sourceNodeId,
            target_id: targetId,
            keyword: keyword,
        }]);
        if (result.status === 'ok' && result.applied > 0) {
            if (typeof buildIndex === 'function') await buildIndex();
            if (typeof loadNodeContent === 'function') await loadNodeContent(sourceNodeId);
        } else {
            showAlert(`未在正文中找到关键词 "${keyword}"`, '提示');
        }
    } catch (e) {
        showAlert('异常: ' + (e.message || ''), '错误');
    }
}

/**
 * 从文件中删除链接（移除 [[]] 包裹，保留文本）
 */
async function removeLinkFromFile(sourceNodeId, targetId, linkText) {
    try {
        const result = await window.memoria.api.get_node_raw(sourceNodeId);
        if (result.status !== 'ok') {
            showAlert('读取文件失败: ' + (result.message || ''), '错误');
            return;
        }
        let content = result.content;
        const re = new RegExp(`\\[\\[${escapeRegExp(targetId)}(#[^\\]|]*)?(\\|([^\\]]*))?\\]\\]`, 'g');
        content = content.replace(re, (m, anchor, pipe, text) => {
            return text || linkText || targetId;
        });
        const saveRes = await window.memoria.api.save_node_raw(sourceNodeId, content);
        if (saveRes.status === 'ok') {
            if (typeof buildIndex === 'function') await buildIndex();
            if (typeof loadNodeContent === 'function') await loadNodeContent(sourceNodeId);
        } else {
            showAlert('保存失败: ' + (saveRes.message || ''), '错误');
        }
    } catch (e) {
        showAlert('异常: ' + (e.message || ''), '错误');
    }
}

/**
 * 加入 autolink 黑名单（仅本地，不修改文件）
 * 下次渲染时不再自动包装此关键词
 */
function addToAutolinkBlacklist(sourceNodeId, targetId, keyword) {
    if (!window.memoria.autolinkBlacklist) {
        window.memoria.autolinkBlacklist = {};
    }
    const key = `${sourceNodeId}::${keyword.toLowerCase()}::${targetId}`;
    window.memoria.autolinkBlacklist[key] = true;
}

function escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
