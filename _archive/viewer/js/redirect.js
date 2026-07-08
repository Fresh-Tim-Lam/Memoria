// ========== 虚链重定向推荐 + 冗余文件选择对话框 ==========

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('btn-redirect-close')?.addEventListener('click', closeRedirectDialog);
    document.getElementById('redirect-overlay')?.addEventListener('click', closeRedirectDialog);
    document.getElementById('btn-duplicate-close')?.addEventListener('click', closeDuplicatePicker);
    document.getElementById('duplicate-overlay')?.addEventListener('click', closeDuplicatePicker);
});

/**
 * 虚链重定向推荐对话框
 * 当用户点击红色虚链 [[unknown-id]] 时弹出
 * 显示相似度匹配的已有节点，用户可选择：
 *   1. 重定向：把 [[unknown]] 替换为 [[已有id]]（修改源文件）
 *   2. 创建新文件：弹出新建节点对话框
 *   3. 取消：保持虚链
 */
async function openRedirectDialog(danglingId) {
    const panel = document.getElementById('redirect-panel');
    const overlay = document.getElementById('redirect-overlay');
    const content = document.getElementById('redirect-content');

    overlay.classList.remove('hidden');
    panel.classList.remove('hidden');
    content.innerHTML = '<div class="review-detail-empty">查询中...</div>';

    try {
        const result = await window.memoria.api.suggest_redirect(danglingId);
        if (result.status !== 'ok') {
            content.innerHTML = `<div class="review-detail-empty">${result.message || '查询失败'}</div>`;
            return;
        }

        const candidates = result.candidates || [];
        let html = `
            <div style="margin-bottom: 12px; padding: 8px; background: var(--bg-tertiary); border-radius: 3px;">
                <div style="font-size: 12px; color: var(--text-secondary);">虚链 id:</div>
                <div style="font-family: var(--font-mono); color: var(--error); font-size: 14px;">[[${escapeHtml(danglingId)}]]</div>
                <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">
                    找到 ${candidates.length} 个可能的已有节点匹配
                </div>
            </div>
        `;

        if (candidates.length === 0) {
            html += `<div class="review-detail-empty">没有相似节点，建议创建新文件</div>`;
        } else {
            html += `<div class="redirect-candidates">`;
            candidates.forEach((c, idx) => {
                const simPct = Math.round(c.similarity * 100);
                const simColor = simPct >= 80 ? 'var(--success)' : simPct >= 60 ? 'var(--warning)' : 'var(--text-secondary)';
                html += `
                    <div class="redirect-candidate" data-redirect-id="${escapeHtml(c.id)}" data-dangling-id="${escapeHtml(danglingId)}">
                        <div class="redirect-candidate-main">
                            <span class="redirect-id">${escapeHtml(c.id)}</span>
                            <span class="redirect-title">${escapeHtml(c.title)}</span>
                            <span class="redirect-sim" style="color: ${simColor}">${simPct}%</span>
                        </div>
                        <div class="redirect-candidate-reason">${escapeHtml(c.reason)}</div>
                        <button class="redirect-btn" data-action="redirect" data-redirect-id="${escapeHtml(c.id)}" data-dangling-id="${escapeHtml(danglingId)}">
                            重定向到此
                        </button>
                    </div>
                `;
            });
            html += `</div>`;
        }

        html += `
            <div class="redirect-footer">
                <button class="danger-btn" id="btn-redirect-delete">删除虚链</button>
                <button class="primary-btn" id="btn-redirect-create">创建新文件</button>
                <button class="secondary-btn" id="btn-redirect-cancel">取消</button>
            </div>
        `;

        content.innerHTML = html;

        // 绑定重定向按钮
        content.querySelectorAll('[data-action="redirect"]').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const redirectId = btn.getAttribute('data-redirect-id');
                const danglId = btn.getAttribute('data-dangling-id');
                await performRedirect(danglId, redirectId);
            });
        });

        // 创建新文件按钮
        document.getElementById('btn-redirect-create')?.addEventListener('click', () => {
            closeRedirectDialog();
            if (typeof openCreateNodeDialog === 'function') {
                openCreateNodeDialog(danglingId);
            }
        });

        // 取消按钮
        document.getElementById('btn-redirect-cancel')?.addEventListener('click', closeRedirectDialog);

        // 删除虚链按钮：把所有 [[danglingId]] 从源文件中移除（保留外围文字）
        document.getElementById('btn-redirect-delete')?.addEventListener('click', async () => {
            const ok = await showConfirm(`确认删除所有 [[${danglingId}]] 虚链？\n这会修改所有引用此虚链的源文件，移除 [[ ]] 包裹但保留内部 id 文本。`, '确认删除');
            if (!ok) {
                return;
            }
            try {
                const result = await window.memoria.api.delete_dangling(danglingId);
                if (result.status === 'ok') {
                    closeRedirectDialog();
                    if (typeof buildIndex === 'function') {
                        await buildIndex();
                    }
                    // 重新加载当前激活节点
                    const activeTab = window.memoria.state.tabs.find(t => t.id === window.memoria.state.activeTab);
                    if (activeTab && typeof loadNodeContent === 'function') {
                        await loadNodeContent(activeTab.nodeId);
                    }
                } else {
                    await showAlert('删除失败: ' + (result.message || ''), '删除失败');
                }
            } catch (e) {
                await showAlert('删除异常: ' + (e.message || ''), '异常');
            }
        });

    } catch (e) {
        content.innerHTML = `<div class="review-detail-empty">异常: ${escapeHtml(e.message || '')}</div>`;
    }
}

function closeRedirectDialog() {
    document.getElementById('redirect-overlay')?.classList.add('hidden');
    document.getElementById('redirect-panel')?.classList.add('hidden');
}

/**
 * 执行重定向：把当前节点正文中的 [[danglingId]] 替换为 [[redirectId]]
 * 这里通过修改源文件实现（用户主动选择，非自动）
 */
async function performRedirect(danglingId, redirectId) {
    const ok = await showConfirm(`确认把所有 [[${danglingId}]] 重定向为 [[${redirectId}]]？\n这会修改所有引用此虚链的源文件。`, '确认重定向');
    if (!ok) {
        return;
    }

    try {
        // 调用后端批量替换
        const result = await window.memoria.api.redirect_dangling(danglingId, redirectId);
        if (result.status === 'ok') {
            closeRedirectDialog();
            // 重建索引
            if (typeof buildIndex === 'function') {
                await buildIndex();
            }
            // 跳转到目标
            if (typeof openNode === 'function') {
                openNode(redirectId);
            }
        } else {
            await showAlert('重定向失败: ' + (result.message || ''), '重定向失败');
        }
    } catch (e) {
        await showAlert('重定向异常: ' + (e.message || ''), '异常');
    }
}

/**
 * 冗余文件选择弹窗
 * 当 [[id]] 匹配多个文件时弹出
 * 用户勾选：第一个=主跳转（高亮色），其余加入文件列表
 */
function openDuplicatePicker(targetId, matches) {
    const panel = document.getElementById('duplicate-panel');
    const overlay = document.getElementById('duplicate-overlay');
    const content = document.getElementById('duplicate-content');

    overlay.classList.remove('hidden');
    panel.classList.remove('hidden');

    // 去重：按 file 分组
    const fileMap = new Map();
    matches.forEach(m => {
        if (!fileMap.has(m.file)) {
            fileMap.set(m.file, m);
        }
    });
    const files = Array.from(fileMap.values());

    // 用 LinkTargetQueue 管理多目标
    activeLinkQueue.clear();
    files.forEach(f => {
        activeLinkQueue.enqueue({ nodeId: f.id, file: f.file, title: f.title });
    });

    renderDuplicateQueue(targetId);
}

function renderDuplicateQueue(targetId) {
    const content = document.getElementById('duplicate-content');
    const items = activeLinkQueue.all();

    let html = `
        <div style="margin-bottom: 12px; padding: 8px; background: var(--bg-tertiary); border-radius: 3px;">
            <div style="font-size: 12px; color: var(--text-secondary);">id 被多个文件声明:</div>
            <div style="font-family: var(--font-mono); color: var(--warning); font-size: 14px;">${escapeHtml(targetId)}</div>
            <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">
                第一个=主跳转（绿色），其余加入文件列表。可用按钮调整顺序或剔除。
            </div>
        </div>
        <div class="duplicate-list">
    `;

    items.forEach((it, idx) => {
        const isPrimary = idx === 0;
        html += `
            <div class="duplicate-item ${isPrimary ? 'primary' : ''}" data-idx="${idx}">
                <div class="dup-idx-badge">${isPrimary ? '主' : (idx + 1)}</div>
                <div class="duplicate-item-main">
                    <span class="duplicate-title">${escapeHtml(it.title)}</span>
                    <span class="duplicate-file">${escapeHtml(it.file.split(/[\\/]/).pop())}</span>
                </div>
                <div class="dup-actions">
                    ${idx > 0 ? '<button class="dup-btn dup-up" title="设为主跳转">↑</button>' : ''}
                    <button class="dup-btn dup-remove" title="剔除">✕</button>
                </div>
            </div>
        `;
    });

    html += `
        </div>
        <div class="redirect-footer">
            <button class="primary-btn" id="btn-duplicate-open">跳转并打开其余</button>
            <button class="secondary-btn" id="btn-duplicate-cancel">取消</button>
        </div>
    `;

    content.innerHTML = html;

    // 绑定按钮
    content.querySelectorAll('.dup-up').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const idx = parseInt(e.target.closest('.duplicate-item').getAttribute('data-idx'));
            activeLinkQueue.moveToFront(idx);
            renderDuplicateQueue(targetId);
        });
    });
    content.querySelectorAll('.dup-remove').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const idx = parseInt(e.target.closest('.duplicate-item').getAttribute('data-idx'));
            activeLinkQueue.removeAt(idx);
            if (activeLinkQueue.isEmpty()) {
                closeDuplicatePicker();
            } else {
                renderDuplicateQueue(targetId);
            }
        });
    });
    document.getElementById('btn-duplicate-open')?.addEventListener('click', async () => {
        const first = activeLinkQueue.first();
        const rest = activeLinkQueue.rest();
        if (!first) {
            await showAlert('队列为空', '提示');
            return;
        }
        closeDuplicatePicker();
        if (typeof openNode === 'function') {
            openNode(first.nodeId);
            // 其余依次打开为新标签
            rest.forEach(it => openNode(it.nodeId));
        }
    });
    document.getElementById('btn-duplicate-cancel')?.addEventListener('click', closeDuplicatePicker);
}

function closeDuplicatePicker() {
    document.getElementById('duplicate-overlay')?.classList.add('hidden');
    document.getElementById('duplicate-panel')?.classList.add('hidden');
}
