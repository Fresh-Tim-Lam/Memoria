// ========== 创建新节点对话框 ==========

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('btn-createnode-close')?.addEventListener('click', closeCreateNodeDialog);
    document.getElementById('createnode-overlay')?.addEventListener('click', closeCreateNodeDialog);
    document.getElementById('btn-createnode-submit')?.addEventListener('click', submitCreateNode);
});

/**
 * 打开创建节点对话框
 * @param prefillId 预填的 id（来自虚链点击）
 */
function openCreateNodeDialog(prefillId) {
    const panel = document.getElementById('createnode-panel');
    const overlay = document.getElementById('createnode-overlay');

    overlay.classList.remove('hidden');
    panel.classList.remove('hidden');

    const idInput = document.getElementById('createnode-id');
    const titleInput = document.getElementById('createnode-title');
    const tagsInput = document.getElementById('createnode-tags');
    const bodyInput = document.getElementById('createnode-body');

    idInput.value = prefillId || '';
    titleInput.value = '';
    tagsInput.value = '';
    bodyInput.value = '';

    // 自动根据 id 推断 title
    if (prefillId) {
        titleInput.value = prefillId.replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    }

    setTimeout(() => idInput.focus(), 50);
}

function closeCreateNodeDialog() {
    document.getElementById('createnode-overlay').classList.add('hidden');
    document.getElementById('createnode-panel').classList.add('hidden');
}

async function submitCreateNode() {
    const id = document.getElementById('createnode-id').value.trim();
    const title = document.getElementById('createnode-title').value.trim();
    const tags = document.getElementById('createnode-tags').value.trim();
    const body = document.getElementById('createnode-body').value;

    if (!id) {
        showAlert('请输入节点 id', '提示');
        return;
    }
    if (/[\s\[\]{}]/.test(id)) {
        showAlert('id 不能含空格或 []{}', '提示');
        return;
    }

    const btn = document.getElementById('btn-createnode-submit');
    btn.disabled = true;
    btn.textContent = '创建中...';

    try {
        const result = await window.memoria.api.create_node(id, title, body, tags);
        if (result.status === 'ok') {
            btn.textContent = '✓ 已创建';
            setTimeout(async () => {
                closeCreateNodeDialog();
                btn.disabled = false;
                btn.textContent = '创建并打开';
                // 重建索引并打开新节点
                if (typeof buildIndex === 'function') {
                    await buildIndex();
                }
                if (typeof openNode === 'function') {
                    openNode(id);
                }
            }, 600);
        } else {
            showAlert('创建失败: ' + (result.message || '未知错误'), '错误');
            btn.disabled = false;
            btn.textContent = '创建并打开';
        }
    } catch (e) {
        showAlert('创建异常: ' + (e.message || ''), '错误');
        btn.disabled = false;
        btn.textContent = '创建并打开';
    }
}
