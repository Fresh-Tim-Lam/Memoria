// ========== 自定义对话框（替代 alert/confirm/prompt） ==========

/**
 * 显示自定义 alert 对话框
 * @param {string} message
 * @param {string} [title='提示']
 * @returns {Promise<void>}
 */
function showAlert(message, title = '提示') {
    return new Promise(resolve => {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.style.zIndex = '10001';
        overlay.innerHTML = `
            <div class="dialog-panel">
                <div class="dialog-header">
                    <span>${escapeHtml(title)}</span>
                </div>
                <div class="dialog-body">${escapeHtml(message)}</div>
                <div class="dialog-footer">
                    <button class="primary-btn dialog-ok">确定</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        const close = () => { overlay.remove(); resolve(); };
        overlay.querySelector('.dialog-ok').addEventListener('click', close);
        overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
    });
}

/**
 * 显示自定义 confirm 对话框
 * @param {string} message
 * @param {string} [title='确认']
 * @returns {Promise<boolean>}
 */
function showConfirm(message, title = '确认') {
    return new Promise(resolve => {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.style.zIndex = '10001';
        overlay.innerHTML = `
            <div class="dialog-panel">
                <div class="dialog-header">
                    <span>${escapeHtml(title)}</span>
                </div>
                <div class="dialog-body">${escapeHtml(message)}</div>
                <div class="dialog-footer">
                    <button class="secondary-btn dialog-cancel">取消</button>
                    <button class="primary-btn dialog-ok">确认</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        const close = (v) => { overlay.remove(); resolve(v); };
        overlay.querySelector('.dialog-ok').addEventListener('click', () => close(true));
        overlay.querySelector('.dialog-cancel').addEventListener('click', () => close(false));
        overlay.addEventListener('click', e => { if (e.target === overlay) close(false); });
    });
}

/**
 * 显示自定义 prompt 对话框（带文本输入）
 * @param {string} message
 * @param {string} [defaultValue='']
 * @param {string} [title='输入']
 * @returns {Promise<string|null>} 输入值，取消则返回 null
 */
function showPrompt(message, defaultValue = '', title = '输入') {
    return new Promise(resolve => {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.style.zIndex = '10001';
        overlay.innerHTML = `
            <div class="dialog-panel">
                <div class="dialog-header">
                    <span>${escapeHtml(title)}</span>
                </div>
                <div class="dialog-body">
                    <div style="margin-bottom: 8px;">${escapeHtml(message)}</div>
                    <input type="text" class="dialog-input" value="${escapeHtml(defaultValue)}">
                </div>
                <div class="dialog-footer">
                    <button class="secondary-btn dialog-cancel">取消</button>
                    <button class="primary-btn dialog-ok">确定</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        const input = overlay.querySelector('.dialog-input');
        input.focus();
        input.select();
        const close = (v) => { overlay.remove(); resolve(v); };
        overlay.querySelector('.dialog-ok').addEventListener('click', () => close(input.value));
        overlay.querySelector('.dialog-cancel').addEventListener('click', () => close(null));
        input.addEventListener('keydown', e => {
            if (e.key === 'Enter') close(input.value);
            if (e.key === 'Escape') close(null);
        });
        overlay.addEventListener('click', e => { if (e.target === overlay) close(null); });
    });
}

/**
 * 显示右键菜单
 * @param {number} x 屏幕坐标 x
 * @param {number} y 屏幕坐标 y
 * @param {Array<{label:string, action:Function}>} items
 */
function showContextMenu(x, y, items) {
    // 关闭已有菜单
    const existing = document.getElementById('custom-context-menu');
    if (existing) existing.remove();

    const menu = document.createElement('div');
    menu.id = 'custom-context-menu';
    menu.className = 'custom-context-menu';
    menu.style.left = x + 'px';
    menu.style.top = y + 'px';

    items.forEach(item => {
        const mi = document.createElement('div');
        mi.className = 'context-menu-item';
        mi.textContent = item.label;
        mi.addEventListener('click', () => {
            menu.remove();
            item.action();
        });
        menu.appendChild(mi);
    });

    document.body.appendChild(menu);

    // 点击其他地方关闭
    const closeHandler = (e) => {
        if (!menu.contains(e.target)) {
            menu.remove();
            document.removeEventListener('click', closeHandler);
        }
    };
    setTimeout(() => document.addEventListener('click', closeHandler), 0);
}

/**
 * 显示表单对话框（多个字段）
 * @param {string} title
 * @param {Array<{key:string, label:string, value:string}>} fields
 * @returns {Promise<Object|null>} 字段值对象，取消则返回 null
 */
function showFormDialog(title, fields) {
    return new Promise(resolve => {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.style.zIndex = '10001';

        const formRows = fields.map(f => `
            <div class="form-row">
                <label class="form-label">${escapeHtml(f.label)}</label>
                <input type="text" class="form-input" data-key="${escapeHtml(f.key)}" value="${escapeHtml(f.value || '')}">
            </div>
        `).join('');

        overlay.innerHTML = `
            <div class="dialog-panel dialog-panel-wide">
                <div class="dialog-header">
                    <span>${escapeHtml(title)}</span>
                </div>
                <div class="dialog-body">
                    ${formRows}
                </div>
                <div class="dialog-footer">
                    <button class="secondary-btn dialog-cancel">取消</button>
                    <button class="primary-btn dialog-ok">确定</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        const firstInput = overlay.querySelector('.form-input');
        if (firstInput) { firstInput.focus(); firstInput.select(); }

        const collect = () => {
            const result = {};
            overlay.querySelectorAll('.form-input').forEach(inp => {
                result[inp.dataset.key] = inp.value;
            });
            return result;
        };
        const close = (v) => { overlay.remove(); resolve(v); };
        overlay.querySelector('.dialog-ok').addEventListener('click', () => close(collect()));
        overlay.querySelector('.dialog-cancel').addEventListener('click', () => close(null));
        overlay.querySelectorAll('.form-input').forEach(inp => {
            inp.addEventListener('keydown', e => {
                if (e.key === 'Enter') close(collect());
                if (e.key === 'Escape') close(null);
            });
        });
        overlay.addEventListener('click', e => { if (e.target === overlay) close(null); });
    });
}
