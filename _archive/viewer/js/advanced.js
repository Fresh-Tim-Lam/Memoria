/**
 * 高级菜单 + 设置面板 + 主题色面板
 *
 * 顶栏「高级 ▾」按钮点击后弹出下拉菜单：
 *   - 设置：打开阈值配置面板
 *   - 主题色：打开主题色配置面板
 */

// 预设主题色
const THEME_COLORS = [
    '#007acc', '#4ec9b0', '#c586c0', '#dcdcaa',
    '#ce9178', '#f14c4c', '#6a9955',
];

let advancedState = {
    threshold: 0.2,
    themeColor: '#007acc',
};

document.addEventListener('DOMContentLoaded', () => {
    // ===== 高级下拉菜单 =====
    const advBtn = document.getElementById('btn-advanced');
    const advDropdown = document.getElementById('advanced-dropdown');

    advBtn?.addEventListener('click', (e) => {
        e.stopPropagation();
        advDropdown.classList.toggle('hidden');
    });

    // 点击菜单项
    advDropdown?.querySelectorAll('.menu-item-action').forEach(item => {
        item.addEventListener('click', () => {
            const action = item.getAttribute('data-action');
            advDropdown.classList.add('hidden');
            if (action === 'settings') {
                openAdvancedPanel();
            } else if (action === 'theme') {
                openThemePanel();
            }
        });
    });

    // 点击外部关闭下拉菜单
    document.addEventListener('click', (e) => {
        if (!advDropdown?.contains(e.target) && e.target !== advBtn) {
            advDropdown?.classList.add('hidden');
        }
    });

    // ===== 设置面板 =====
    document.getElementById('btn-advanced-close')?.addEventListener('click', closeAdvancedPanel);
    document.getElementById('btn-save-advanced')?.addEventListener('click', saveAdvanced);
    // 点击遮罩层关闭
    document.getElementById('advanced-overlay')?.addEventListener('click', closeAdvancedPanel);

    const slider = document.getElementById('threshold-slider');
    const valueLabel = document.getElementById('threshold-value');
    slider?.addEventListener('input', () => {
        const val = parseFloat(slider.value);
        valueLabel.textContent = val.toFixed(2);
        advancedState.threshold = val;
        updateActivePreset(val);
    });

    document.querySelectorAll('.preset-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const val = parseFloat(btn.dataset.value);
            slider.value = val;
            valueLabel.textContent = val.toFixed(2);
            advancedState.threshold = val;
            updateActivePreset(val);
        });
    });

    // ===== 主题色面板 =====
    document.getElementById('btn-theme-close')?.addEventListener('click', closeThemePanel);
    document.getElementById('btn-save-theme')?.addEventListener('click', saveTheme);
    // 点击遮罩层关闭
    document.getElementById('theme-overlay')?.addEventListener('click', closeThemePanel);

    document.querySelectorAll('.color-swatch').forEach(swatch => {
        swatch.addEventListener('click', () => {
            const color = swatch.dataset.color;
            advancedState.themeColor = color;
            document.querySelectorAll('.color-swatch').forEach(s => s.classList.remove('active'));
            swatch.classList.add('active');
            document.getElementById('theme-custom-input').value = color;
            applyThemeColor(color);
        });
    });

    // 自定义颜色
    const customInput = document.getElementById('theme-custom-input');
    customInput?.addEventListener('input', () => {
        const color = customInput.value;
        advancedState.themeColor = color;
        document.querySelectorAll('.color-swatch').forEach(s => s.classList.remove('active'));
        applyThemeColor(color);
    });
});

// ===== 设置面板 =====

async function openAdvancedPanel() {
    document.getElementById('advanced-overlay').classList.remove('hidden');
    document.getElementById('advanced-panel').classList.remove('hidden');
    await loadSearchConfig();
}

function closeAdvancedPanel() {
    document.getElementById('advanced-overlay').classList.add('hidden');
    document.getElementById('advanced-panel').classList.add('hidden');
}

async function loadSearchConfig() {
    try {
        const result = await window.memoria.api.get_search_config();
        if (result.status === 'ok') {
            advancedState.threshold = result.config.similarity_threshold;
            advancedState.themeColor = result.config.theme_color || '#007acc';

            const slider = document.getElementById('threshold-slider');
            const valueLabel = document.getElementById('threshold-value');
            slider.value = advancedState.threshold;
            valueLabel.textContent = advancedState.threshold.toFixed(2);
            updateActivePreset(advancedState.threshold);

            // 同步主题色选中状态
            document.querySelectorAll('.color-swatch').forEach(s => {
                s.classList.toggle('active', s.dataset.color === advancedState.themeColor);
            });
            document.getElementById('theme-custom-input').value = advancedState.themeColor;
            applyThemeColor(advancedState.themeColor);
        }
    } catch (e) {
        console.log('加载配置失败:', e);
    }
}

function updateActivePreset(val) {
    document.querySelectorAll('.preset-btn').forEach(btn => {
        const presetVal = parseFloat(btn.dataset.value);
        btn.classList.toggle('active', Math.abs(presetVal - val) < 0.001);
    });
}

async function saveAdvanced() {
    const saveBtn = document.getElementById('btn-save-advanced');
    saveBtn.textContent = '保存中...';
    saveBtn.disabled = true;

    try {
        const result = await window.memoria.api.save_search_config(
            advancedState.threshold,
            advancedState.themeColor
        );
        if (result.status === 'ok') {
            saveBtn.textContent = '保存';
            saveBtn.disabled = false;
            closeAdvancedPanel();
            setStatus(`阈值已保存（${advancedState.threshold.toFixed(2)}）`);
        } else {
            showAlert('保存失败: ' + (result.message || ''), '错误');
            saveBtn.textContent = '保存';
            saveBtn.disabled = false;
        }
    } catch (e) {
        showAlert('保存失败: ' + e.message, '错误');
        saveBtn.textContent = '保存';
        saveBtn.disabled = false;
    }
}

// ===== 主题色面板 =====

async function openThemePanel() {
    document.getElementById('theme-overlay').classList.remove('hidden');
    document.getElementById('theme-panel').classList.remove('hidden');
    await loadSearchConfig();
}

function closeThemePanel() {
    document.getElementById('theme-overlay').classList.add('hidden');
    document.getElementById('theme-panel').classList.add('hidden');
}

async function saveTheme() {
    const saveBtn = document.getElementById('btn-save-theme');
    saveBtn.textContent = '保存中...';
    saveBtn.disabled = true;

    try {
        const result = await window.memoria.api.save_search_config(
            advancedState.threshold,
            advancedState.themeColor
        );
        if (result.status === 'ok') {
            saveBtn.textContent = '保存';
            saveBtn.disabled = false;
            closeThemePanel();
            setStatus(`主题色已保存（${advancedState.themeColor}）`);
        } else {
            showAlert('保存失败: ' + (result.message || ''), '错误');
            saveBtn.textContent = '保存';
            saveBtn.disabled = false;
        }
    } catch (e) {
        showAlert('保存失败: ' + e.message, '错误');
        saveBtn.textContent = '保存';
        saveBtn.disabled = false;
    }
}

/**
 * 实时应用主题色（预览）
 */
function applyThemeColor(color) {
    document.documentElement.style.setProperty('--theme-color', color);
    document.documentElement.style.setProperty('--accent', color);
    const rgba = hexToRgba(color, 0.2);
    document.documentElement.style.setProperty('--accent-soft', rgba);
    // hover 色：稍亮（简单亮度提升）
    document.documentElement.style.setProperty('--accent-hover', lightenColor(color, 15));
}

function hexToRgba(hex, alpha) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function lightenColor(hex, percent) {
    const r = Math.min(255, parseInt(hex.slice(1, 3), 16) + Math.round(255 * percent / 100));
    const g = Math.min(255, parseInt(hex.slice(3, 5), 16) + Math.round(255 * percent / 100));
    const b = Math.min(255, parseInt(hex.slice(5, 7), 16) + Math.round(255 * percent / 100));
    return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`;
}
