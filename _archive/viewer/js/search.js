// ========== 搜索功能 ==========

// 搜索模式状态（默认开启知识点搜索，关闭内容搜索）
let searchMode = {
    keyword: true,   // 知识点搜索（语义 + 模糊匹配关键词）
    content: false,  // 内容搜索（正文里搜字符串）
};

// ========== 模糊匹配工具 ==========

/**
 * Levenshtein 距离
 */
function levenshtein(a, b) {
    const m = a.length, n = b.length;
    if (m === 0) return n;
    if (n === 0) return m;
    const dp = new Array(n + 1);
    for (let j = 0; j <= n; j++) dp[j] = j;
    for (let i = 1; i <= m; i++) {
        let prev = dp[0];
        dp[0] = i;
        for (let j = 1; j <= n; j++) {
            const tmp = dp[j];
            dp[j] = Math.min(
                dp[j] + 1,        // 删除
                dp[j - 1] + 1,    // 插入
                prev + (a[i - 1] === b[j - 1] ? 0 : 1)  // 替换
            );
            prev = tmp;
        }
    }
    return dp[n];
}

/**
 * 模糊相似度 [0, 1]
 * - 完全相同 → 1.0
 * - 子串包含 → 0.95
 * - 否则用 1 - 距离/最大长度
 */
function fuzzyScore(query, text) {
    if (!query || !text) return 0;
    query = query.toLowerCase();
    text = text.toLowerCase();
    if (text === query) return 1.0;
    if (text.includes(query) || query.includes(text)) return 0.95;
    const dist = levenshtein(query, text);
    return 1 - dist / Math.max(query.length, text.length);
}

/**
 * 在节点的关键词集合中找最佳模糊匹配分数
 */
function bestKeywordMatch(query, keywords) {
    if (!keywords || keywords.length === 0) return 0;
    let best = 0;
    for (const kw of keywords) {
        const s = fuzzyScore(query, kw);
        if (s > best) best = s;
    }
    return best;
}

// ========== 搜索菜单 ==========

document.addEventListener('DOMContentLoaded', () => {
    const menuBtn = document.getElementById('btn-search-menu');
    const menu = document.getElementById('search-menu');

    // 点击按钮切换菜单
    menuBtn?.addEventListener('click', (e) => {
        e.stopPropagation();
        menu.classList.toggle('hidden');
    });

    // 点击菜单外部关闭
    document.addEventListener('click', (e) => {
        if (!menu?.contains(e.target) && e.target !== menuBtn) {
            menu?.classList.add('hidden');
        }
    });

    // 复选框切换
    document.getElementById('chk-keyword-search')?.addEventListener('change', (e) => {
        searchMode.keyword = e.target.checked;
    });
    document.getElementById('chk-content-search')?.addEventListener('change', (e) => {
        searchMode.content = e.target.checked;
    });
});

// ========== 主搜索入口（Enter 触发） ==========

async function doSearch(query) {
    if (!query.trim()) return;

    const panel = document.getElementById('search-panel');
    const resultsDiv = document.getElementById('search-results');
    panel.classList.remove('hidden');
    resultsDiv.innerHTML = '<p>正在搜索...</p>';

    const tasks = [];

    // 知识点搜索：语义 + 模糊匹配
    if (searchMode.keyword) {
        tasks.push(doKeywordSearch(query));
    }

    // 内容搜索
    if (searchMode.content) {
        tasks.push(doContentSearch(query));
    }

    // 至少勾选一个
    if (tasks.length === 0) {
        resultsDiv.innerHTML = '<p>请在搜索菜单中至少勾选一种搜索方式</p>';
        return;
    }

    const allResults = await Promise.all(tasks);

    // 合并结果
    const merged = mergeResults(allResults);

    showSearchResults(merged, query);
}

/**
 * 知识点搜索：语义搜索 + 模糊匹配关键词
 */
async function doKeywordSearch(query) {
    const results = [];

    // 1. AI 语义搜索
    try {
        const aiResult = await window.memoria.api.ai_search(query);
        if (aiResult.status === 'ok' && aiResult.results) {
            for (const r of aiResult.results) {
                if (r.error) continue;
                results.push({
                    id: r.id,
                    title: r.title || r.id,
                    score: r.score,        // 语义相似度 [0,1]
                    source: 'semantic',
                    snippet: '',
                });
            }
        }
    } catch (e) {
        console.log('语义搜索失败:', e);
    }

    // 2. 模糊匹配关键词（容错拼写错误）
    const keywordsMap = window.memoria.state.keywords || {};
    const index = window.memoria.state.index;
    if (index && index.nodes) {
        const FUZZY_THRESHOLD = 0.6;  // 模糊匹配阈值
        for (const node of index.nodes) {
            const nid = node.id;
            // 收集该节点所有可匹配文本
            const kws = [
                ...(node.title ? [node.title] : []),
                ...(node.id ? [node.id] : []),
                ...(node.tags || []),
                ...(keywordsMap[nid] || []),
            ];

            const bestScore = bestKeywordMatch(query, kws);
            if (bestScore >= FUZZY_THRESHOLD) {
                // 检查是否已存在（语义搜索可能已返回）
                const existing = results.find(r => r.id === nid);
                if (existing) {
                    // 取较高分
                    if (bestScore > existing.score) {
                        existing.score = bestScore;
                        existing.source = 'fuzzy';
                    }
                } else {
                    results.push({
                        id: nid,
                        title: node.title || nid,
                        score: bestScore,
                        source: 'fuzzy',
                        snippet: '',
                    });
                }
            }
        }
    }

    return { type: 'keyword', results };
}

/**
 * 内容搜索
 */
async function doContentSearch(query) {
    const results = [];
    try {
        const r = await window.memoria.api.content_search(query);
        if (r.status === 'ok' && r.results) {
            for (const item of r.results) {
                // 把命中次数归一化到 [0,1]，用 log 缩放避免次数过多导致分数爆炸
                const normalized = Math.min(1.0, 0.3 + Math.log10(item.score + 1) * 0.2);
                results.push({
                    id: item.id,
                    title: item.title || item.id,
                    score: normalized,
                    source: 'content',
                    snippet: item.snippet || '',
                });
            }
        }
    } catch (e) {
        console.log('内容搜索失败:', e);
    }
    return { type: 'content', results };
}

/**
 * 合并多种搜索方式的结果
 */
function mergeResults(groups) {
    const map = new Map();
    for (const group of groups) {
        if (!group || !group.results) continue;
        for (const r of group.results) {
            const existing = map.get(r.id);
            if (existing) {
                // 取较高分
                if (r.score > existing.score) {
                    existing.score = r.score;
                    existing.source = r.source;
                }
                // 合并 snippet
                if (r.snippet && !existing.snippet) {
                    existing.snippet = r.snippet;
                }
                existing.sources = Array.from(new Set([...(existing.sources || [existing.source]), r.source]));
            } else {
                map.set(r.id, { ...r, sources: [r.source] });
            }
        }
    }
    const merged = Array.from(map.values());
    merged.sort((a, b) => b.score - a.score);
    return merged;
}

function showSearchResults(results, query) {
    const resultsDiv = document.getElementById('search-results');

    let header = `搜索: "${escapeHtml(query)}"`;
    if (results.length === 0) {
        resultsDiv.innerHTML = `<p style="margin-bottom: 8px">${escapeHtml(header)}</p><p>未找到相关知识点</p>`;
        return;
    }

    const sourceLabels = {
        semantic: '语义',
        fuzzy: '模糊',
        content: '正文',
    };

    resultsDiv.innerHTML = `<p style="margin-bottom: 8px; color: var(--text-secondary); font-size: 11px">${escapeHtml(header)} · ${results.length} 个结果</p>` +
        results.map(r => {
            const sources = (r.sources || [r.source]).map(s => sourceLabels[s] || s).join('+');
            return `
                <div class="search-item" data-node-id="${escapeHtml(r.id)}">
                    <div>
                        <span class="title">${escapeHtml(r.title)}</span>
                        <span class="score">${(r.score * 100).toFixed(0)}%</span>
                        <span class="search-source">${sources}</span>
                    </div>
                    ${r.snippet ? `<div class="snippet">${escapeHtml(r.snippet)}</div>` : `<div class="snippet">${escapeHtml(r.id)}</div>`}
                </div>
            `;
        }).join('');

    resultsDiv.querySelectorAll('.search-item').forEach(item => {
        item.addEventListener('click', () => {
            openNode(item.getAttribute('data-node-id'));
            document.getElementById('search-panel').classList.add('hidden');
        });
    });
}

// 兼容旧调用（如 AI 按钮）
async function doAiSearch(query) {
    // 如果用户没勾选任何模式，默认用知识点搜索
    if (!searchMode.keyword && !searchMode.content) {
        searchMode.keyword = true;
        document.getElementById('chk-keyword-search').checked = true;
    }
    return doSearch(query);
}
