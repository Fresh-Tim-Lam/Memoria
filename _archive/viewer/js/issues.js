// ========== 问题文件检测与修复 ==========

// 问题类型中文映射
const ISSUE_TYPE_LABELS = {
    no_frontmatter: '无 Frontmatter',
    unclosed_frontmatter: 'Frontmatter 未闭合',
    missing_id: '缺少 id',
    missing_title: '缺少 title',
    duplicate_id: 'id 重复',
    invalid_id: 'id 格式错误',
};

// 当前缓存的 issues 列表
let currentIssues = [];
// 当前缓存的 warnings 列表
let currentWarnings = [];

// ========== 状态栏提示 ==========

function updateIssuesIndicator(issues) {
    currentIssues = issues || [];
    const link = document.getElementById('issues-link');
    const count = document.getElementById('issues-count');

    if (!link || !count) return;

    if (currentIssues.length > 0) {
        count.textContent = currentIssues.length;
        link.classList.remove('hidden');
    } else {
        link.classList.add('hidden');
    }
}

function updateWarningsIndicator(warnings) {
    currentWarnings = warnings || [];
    const link = document.getElementById('warnings-link');
    const count = document.getElementById('warnings-count');

    if (!link || !count) return;

    if (currentWarnings.length > 0) {
        count.textContent = currentWarnings.length;
        link.classList.remove('hidden');
    } else {
        link.classList.add('hidden');
    }
}

// ========== 问题面板 ==========

function openIssuesPanel() {
    if (currentIssues.length === 0) return;

    document.getElementById('issues-overlay').classList.remove('hidden');
    document.getElementById('issues-panel').classList.remove('hidden');
    document.getElementById('issues-panel-count').textContent = currentIssues.length;

    renderIssuesList();
}

function closeIssuesPanel() {
    document.getElementById('issues-overlay').classList.add('hidden');
    document.getElementById('issues-panel').classList.add('hidden');
}

function renderIssuesList() {
    const list = document.getElementById('issues-list');
    if (!list) return;

    list.innerHTML = '';

    currentIssues.forEach((issue, idx) => {
        const item = document.createElement('div');
        item.className = 'issue-item';

        const label = ISSUE_TYPE_LABELS[issue.type] || issue.type;
        const fixable = issue.fixable;

        // 可修复的问题显示可编辑的 id/title 输入框
        let editorHtml = '';
        if (fixable) {
            editorHtml = `
                <div class="issue-editor">
                    <label class="issue-field">
                        <span>id:</span>
                        <input type="text" class="issue-input" data-field="id"
                               value="${escapeHtml(issue.suggestion_id || '')}"
                               placeholder="不含空格和[]{}, 如 my-node">
                    </label>
                    <label class="issue-field">
                        <span>title:</span>
                        <input type="text" class="issue-input" data-field="title"
                               value="${escapeHtml(issue.suggestion_title || '')}"
                               placeholder="显示标题">
                    </label>
                </div>
            `;
        }

        item.innerHTML = `
            <div class="issue-item-header">
                <span class="issue-type-tag ${issue.type}">${label}</span>
                <span class="issue-file">${escapeHtml(issue.relpath || issue.file)}</span>
            </div>
            <div class="issue-message">${escapeHtml(issue.message)}</div>
            ${editorHtml}
            <div class="issue-actions">
                ${fixable
                    ? `<button class="issue-fix-btn" data-idx="${idx}">应用修复</button>`
                    : '<span style="color: var(--text-secondary); font-size: 11px;">需手动修改</span>'}
            </div>
        `;

        list.appendChild(item);
    });

    // 绑定"应用修复"按钮
    list.querySelectorAll('.issue-fix-btn').forEach(btn => {
        btn.addEventListener('click', () => applyFix(parseInt(btn.dataset.idx, 10), btn));
    });
}

async function applyFix(idx, btn) {
    const issue = currentIssues[idx];
    if (!issue || !issue.fixable) return;

    // 从输入框读取用户编辑后的 id/title
    const item = btn.closest('.issue-item');
    const idInput = item.querySelector('[data-field="id"]');
    const titleInput = item.querySelector('[data-field="title"]');
    const customId = idInput ? idInput.value.trim() : '';
    const customTitle = titleInput ? titleInput.value.trim() : '';

    // 校验 id 格式：不允许空格和 []{} （会破坏 [[id]] 解析），其余字符均可
    if (customId && /[\s\[\]{}]/.test(customId)) {
        btn.textContent = 'id 不能含空格或[]{}';
        btn.disabled = false;
        setTimeout(() => { btn.textContent = '应用修复'; }, 1500);
        return;
    }

    btn.disabled = true;
    btn.textContent = '修复中...';

    try {
        // 传自定义 id/title（如果为空，后端会用推断值）
        const result = await window.memoria.api.auto_fix_file(
            issue.file,
            customId || null,
            customTitle || null
        );
        if (result.status === 'ok') {
            btn.textContent = '✓ 已修复';
            btn.classList.add('success');
            // 从列表移除已修复的问题
            currentIssues.splice(idx, 1);
            // 更新计数
            document.getElementById('issues-panel-count').textContent = currentIssues.length;
            document.getElementById('issues-count').textContent = currentIssues.length;
            if (currentIssues.length === 0) {
                document.getElementById('issues-link').classList.add('hidden');
            }
            // 延迟后重新渲染列表
            setTimeout(() => renderIssuesList(), 500);
        } else {
            btn.textContent = '修复失败';
            btn.disabled = false;
            console.error('修复失败:', result.message);
        }
    } catch (e) {
        btn.textContent = '修复失败';
        btn.disabled = false;
        console.error('修复异常:', e);
    }
}

// ========== 初始化 ==========

document.addEventListener('DOMContentLoaded', () => {
    // 状态栏问题提示点击
    document.getElementById('issues-link')?.addEventListener('click', openIssuesPanel);
    // 问题面板关闭
    document.getElementById('btn-issues-close')?.addEventListener('click', closeIssuesPanel);
    document.getElementById('issues-overlay')?.addEventListener('click', closeIssuesPanel);
    // 修复后重新构建
    document.getElementById('btn-issues-rebuild')?.addEventListener('click', async () => {
        closeIssuesPanel();
        if (typeof buildIndex === 'function') {
            await buildIndex();
        }
    });

    // 编译器警告面板
    document.getElementById('warnings-link')?.addEventListener('click', openWarningsPanel);
    document.getElementById('btn-warnings-close')?.addEventListener('click', closeWarningsPanel);
    document.getElementById('btn-warnings-ok')?.addEventListener('click', closeWarningsPanel);
    document.getElementById('warnings-overlay')?.addEventListener('click', closeWarningsPanel);
});

// ========== 编译器警告面板 ==========

function openWarningsPanel() {
    if (currentWarnings.length === 0) return;

    document.getElementById('warnings-overlay').classList.remove('hidden');
    document.getElementById('warnings-panel').classList.remove('hidden');
    document.getElementById('warnings-panel-count').textContent = currentWarnings.length;

    const list = document.getElementById('warnings-list');
    list.innerHTML = '';

    // 兼容多种格式：
    // 1. 新 builder: "Broken citation: [[text]] in file.md" / "Duplicate id: xxx in N files"
    // 2. 旧 build: "Broken citation: ddpg -> [[policy-gradient]] (line 16)"
    // 3. 旧 check: "[ERROR] ..." / "[WARN] ..."
    const brokenCitations = currentWarnings.filter(w =>
        w.includes('[ERROR]') || w.toLowerCase().includes('broken citation'));
    const orphanNodes = currentWarnings.filter(w =>
        w.includes('[WARN]') || w.toLowerCase().includes('orphan'));
    const duplicates = currentWarnings.filter(w =>
        w.toLowerCase().includes('duplicate id'));

    if (brokenCitations.length > 0) {
        const header = document.createElement('div');
        header.className = 'warning-group-header';
        header.textContent = `断链/虚链引用 (${brokenCitations.length}) — 正文中 [[文本]] 无对应知识点`;
        list.appendChild(header);
        brokenCitations.forEach(w => {
            const item = document.createElement('div');
            item.className = 'warning-item error';
            // 解析出虚链文本，提供"创建知识点"或"重定向"操作
            const m = w.match(/\[\[([^\]]+)\]\]/);
            if (m) {
                const linkText = m[1].split('|')[0].split('#')[0];
                item.innerHTML = `
                    <span class="warning-text">${escapeHtml(w)}</span>
                    <div class="warning-actions">
                        <button class="warning-action-btn" data-action="redirect" data-text="${escapeHtml(linkText)}">重定向</button>
                    </div>
                `;
            } else {
                item.textContent = w;
            }
            list.appendChild(item);
        });
    }

    if (duplicates.length > 0) {
        const header = document.createElement('div');
        header.className = 'warning-group-header';
        header.textContent = `知识点 id 冲突 (${duplicates.length}) — 同一 id 被多个文件声明`;
        list.appendChild(header);
        duplicates.forEach(w => {
            const item = document.createElement('div');
            item.className = 'warning-item error';
            item.textContent = w;
            list.appendChild(item);
        });
    }

    if (orphanNodes.length > 0) {
        const header = document.createElement('div');
        header.className = 'warning-group-header';
        header.textContent = `孤立节点 (${orphanNodes.length}) — 没有 prerequisite/extend 关系的节点`;
        list.appendChild(header);
        orphanNodes.forEach(w => {
            const item = document.createElement('div');
            item.className = 'warning-item warn';
            item.textContent = w;
            list.appendChild(item);
        });
    }

    // 兜底：未分类的警告直接显示
    const classified = brokenCitations.length + orphanNodes.length + duplicates.length;
    if (classified < currentWarnings.length) {
        const others = currentWarnings.filter(w =>
            !brokenCitations.includes(w) && !orphanNodes.includes(w) && !duplicates.includes(w));
        if (others.length > 0) {
            const header = document.createElement('div');
            header.className = 'warning-group-header';
            header.textContent = `其他 (${others.length})`;
            list.appendChild(header);
            others.forEach(w => {
                const item = document.createElement('div');
                item.className = 'warning-item';
                item.textContent = w;
                list.appendChild(item);
            });
        }
    }

    // 绑定重定向按钮
    list.querySelectorAll('.warning-action-btn[data-action="redirect"]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const text = e.target.dataset.text;
            closeWarningsPanel();
            if (typeof openRedirectDialog === 'function') {
                openRedirectDialog(text);
            }
        });
    });
}

function closeWarningsPanel() {
    document.getElementById('warnings-overlay').classList.add('hidden');
    document.getElementById('warnings-panel').classList.add('hidden');
}

// 简单的 HTML 转义（复用 app.js 的 escapeHtml）
