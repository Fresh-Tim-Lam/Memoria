// Dev-only click annotation board for Memoria.
// Injected through WebView2 CDP; not part of the product build.
// Multi-annotation: every saved annotation gets a numbered marker and an editable row.
(() => {
  if (window.__MEMORIA_ANNOTATOR__) {
    window.__MEMORIA_ANNOTATOR__.ensureMounted?.();
    return;
  }
  const KEY = 'memoria.dev.annotations.v1';
  const state = {
    active: false,
    pending: null,
    editingId: null,
    items: (() => { try { return JSON.parse(localStorage.getItem(KEY) || '[]'); } catch { return []; } })(),
  };
  const host = document.createElement('div');
  host.id = '__memoria_annotator_host__';
  host.style.all = 'initial';
  // 不能留在普通文档流里：否则 html 末尾会多一个行盒，点选面板一开整个应用会下移。
  host.style.position = 'fixed';
  host.style.top = '0';
  host.style.left = '0';
  host.style.width = '0';
  host.style.height = '0';
  host.style.zIndex = '2147483000';
  host.style.pointerEvents = 'none';
  const root = host.attachShadow({ mode: 'open' });
  root.innerHTML = `
    <style>
      :host, * { box-sizing: border-box; }
      .wrap { position: fixed; right: 18px; bottom: 18px; z-index: 2147483000; pointer-events: auto; font: 13px/1.45 system-ui, -apple-system, Segoe UI, sans-serif; color: #e6edf3; }
      .bar { display: flex; gap: 8px; align-items: center; background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 8px 10px; box-shadow: 0 8px 28px rgba(0,0,0,.45); cursor: grab; touch-action: none; user-select: none; }
      .wrap.is-dragging .bar { cursor: grabbing; }
      .wrap.is-dragging { user-select: none; }
      .bar b { font-weight: 650; font-size: 12px; color: #adbac7; }
      .bar #count { color: #58a6ff; }
      button { all: unset; cursor: pointer; padding: 5px 9px; border-radius: 7px; background: #21262d; border: 1px solid #30363d; color: #e6edf3; font: inherit; }
      button:hover { background: #30363d; }
      button.primary { background: #1f6feb; border-color: #1f6feb; color: #fff; }
      button.danger { color: #ff7b72; }
      button.tiny { padding: 2px 6px; font-size: 11px; }
      .panel { margin-top: 8px; width: 380px; max-width: calc(100vw - 36px); background: #0d1117; border: 1px solid #30363d; border-radius: 10px; padding: 12px; box-shadow: 0 8px 28px rgba(0,0,0,.45); display: none; }
      .exportbox { margin-top: 8px; width: 420px; max-width: calc(100vw - 36px); background: #0d1117; border: 1px solid #30363d; border-radius: 10px; padding: 12px; box-shadow: 0 8px 28px rgba(0,0,0,.45); display: none; }
      .exportbox.open { display: block; }
      .exportbox textarea { min-height: 140px; font-family: ui-monospace, Consolas, monospace; font-size: 11px; }
      .panel.open { display: block; }
      .meta { font-size: 11px; color: #8b949e; word-break: break-all; margin-bottom: 8px; }
      label { display: block; font-size: 12px; color: #adbac7; margin: 8px 0 4px; }
      textarea, input { width: 100%; background: #161b22; border: 1px solid #30363d; border-radius: 6px; color: #e6edf3; padding: 7px; font: inherit; resize: vertical; }
      textarea { min-height: 64px; }
      .row { display: flex; gap: 8px; justify-content: flex-end; margin-top: 10px; }
      .hint { font-size: 11px; color: #8b949e; margin-top: 8px; }
      .list { max-height: 220px; overflow: auto; margin-top: 8px; border-top: 1px solid #21262d; }
      .item { padding: 6px 0; border-bottom: 1px solid #21262d; font-size: 12px; }
      .item .k { color: #d2a8ff; word-break: break-all; }
      .item .n { color: #adbac7; margin-top: 2px; }
      .item .ops { display: flex; gap: 6px; margin-top: 4px; }
      .item .ops button { padding: 1px 6px; font-size: 11px; }
      .outline { position: fixed; pointer-events: none; z-index: 2147482999; border: 2px solid #58a6ff; background: rgba(88,166,255,.12); border-radius: 3px; }
      .markers { position: fixed; inset: 0; pointer-events: none; z-index: 2147482998; }
      .marker { position: fixed; pointer-events: auto; min-width: 18px; height: 18px; padding: 0 4px; border-radius: 9px; background: #1f6feb; color: #fff; border: 1px solid #fff; font: 11px/16px system-ui, sans-serif; text-align: center; cursor: pointer; box-shadow: 0 1px 4px rgba(0,0,0,.5); }
      .marker:hover { background: #388bfd; }
    </style>
    <div class="wrap">
      <div class="bar">
        <b>批注板 <span id="count">0</span></b>
        <button id="toggle" class="primary">开始点选</button>
        <button id="export">导出 JSONL</button>
        <button id="close" title="关闭">×</button>
      </div>
      <div class="exportbox" id="exportbox">
        <div class="meta">导出内容（可全选复制；若下载无反应就用复制）</div>
        <textarea id="exporttext" readonly></textarea>
        <div class="row">
          <button id="copyexport" class="primary">复制到剪贴板</button>
          <button id="downloadexport">下载</button>
          <button id="closeexport">关闭</button>
        </div>
      </div>
      <div class="panel" id="panel">
        <div class="meta" id="meta"></div>
        <label>定位（自动生成，可改）</label>
        <input id="selector" />
        <label>原文（可改）</label>
        <textarea id="text"></textarea>
        <label>批注 / 问题 / 期望</label>
        <textarea id="note" placeholder="例如：这里应该拆成两个知识点；引用错了；文字应为…"></textarea>
        <div class="row">
          <button id="cancel">取消</button>
          <button id="delete" class="danger">删除</button>
          <button id="save" class="primary">保存</button>
        </div>
        <div class="hint">点选时按住 Alt 可复制元素选择器；Esc 取消当前点选。每个批注会生成一个编号标记。</div>
        <div class="list" id="list"></div>
      </div>
    </div>
    <div class="markers" id="markers"></div>
  `;
  (document.body || document.documentElement).appendChild(host);
  const $ = (s) => root.querySelector(s);
  const panel = $('#panel');
  const wrapEl = $('.wrap');
  const barEl = $('.bar');

  // 2026-11-10：批注板可拖动，便于查看/操作被它遮住的 UI。位置存 localStorage；
  // 双击标题栏复位到右下角。只从标题栏起拖，按钮点击不触发。
  const POS_KEY = 'memoria.dev.annotator.pos.v1';
  function clampPos(left, top) {
    const w = wrapEl.offsetWidth || 380;
    const h = wrapEl.offsetHeight || 48;
    return {
      left: Math.max(4, Math.min(Math.max(4, window.innerWidth - w - 4), left)),
      top: Math.max(4, Math.min(Math.max(4, window.innerHeight - h - 4), top)),
    };
  }
  function applyPos(pos) {
    if (!pos) {
      wrapEl.style.left = '';
      wrapEl.style.top = '';
      wrapEl.style.right = '18px';
      wrapEl.style.bottom = '18px';
      return;
    }
    const p = clampPos(Number(pos.left) || 0, Number(pos.top) || 0);
    wrapEl.style.right = 'auto';
    wrapEl.style.bottom = 'auto';
    wrapEl.style.left = p.left + 'px';
    wrapEl.style.top = p.top + 'px';
  }
  try { applyPos(JSON.parse(localStorage.getItem(POS_KEY) || 'null')); } catch (_) { /* ignore */ }
  let boardDrag = null;
  barEl.addEventListener('pointerdown', (e) => {
    if (e.button !== undefined && e.button !== 0) return;
    if (e.target.closest('button')) return;
    const r = wrapEl.getBoundingClientRect();
    boardDrag = { dx: e.clientX - r.left, dy: e.clientY - r.top };
    wrapEl.classList.add('is-dragging');
    try { barEl.setPointerCapture(e.pointerId); } catch (_) { /* noop */ }
    e.preventDefault();
  });
  barEl.addEventListener('pointermove', (e) => {
    if (!boardDrag) return;
    const p = clampPos(e.clientX - boardDrag.dx, e.clientY - boardDrag.dy);
    wrapEl.style.right = 'auto';
    wrapEl.style.bottom = 'auto';
    wrapEl.style.left = p.left + 'px';
    wrapEl.style.top = p.top + 'px';
  });
  function endBoardDrag(e) {
    if (!boardDrag) return;
    boardDrag = null;
    wrapEl.classList.remove('is-dragging');
    try { barEl.releasePointerCapture(e.pointerId); } catch (_) { /* noop */ }
    try {
      localStorage.setItem(POS_KEY, JSON.stringify({
        left: parseInt(wrapEl.style.left, 10) || 0,
        top: parseInt(wrapEl.style.top, 10) || 0,
      }));
    } catch (_) { /* ignore */ }
  }
  barEl.addEventListener('pointerup', endBoardDrag);
  barEl.addEventListener('pointercancel', endBoardDrag);
  barEl.addEventListener('dblclick', (e) => {
    if (e.target.closest('button')) return;
    try { localStorage.removeItem(POS_KEY); } catch (_) { /* ignore */ }
    applyPos(null);
  });
  window.addEventListener('resize', () => {
    if (wrapEl.style.left || wrapEl.style.top) {
      applyPos({ left: parseInt(wrapEl.style.left, 10), top: parseInt(wrapEl.style.top, 10) });
    }
  });
  barEl.title = '拖动标题栏移动批注板；双击复位到右下角';

  const outline = document.createElement('div');
  outline.className = 'outline';
  outline.style.display = 'none';
  // 必须放在 shadow root 内：`.outline` 的 CSS 只定义在 shadow 的 <style> 里。
  // 之前 append 到 document.body ⇒ 样式不生效，outline 变成普通块级元素，
  // 每次 hover 都把页面撑高/下移，严重时整窗黑屏。
  root.appendChild(outline);

  // 自愈：若页面框架重写 body/documentElement 把宿主摘掉，自动挂回。
  function ensureMounted() {
    if (!host.isConnected) (document.body || document.documentElement).appendChild(host);
    if (!outline.isConnected) root.appendChild(outline);
  }
  try {
    new MutationObserver(ensureMounted).observe(document.documentElement, { childList: true, subtree: true });
  } catch (_) { /* noop */ }
  setInterval(ensureMounted, 1500);

  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  function selectorOf(el) {
    if (!(el instanceof Element)) return '';
    if (el.id) return '#' + CSS.escape(el.id);
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && parts.length < 6) {
      let part = cur.tagName.toLowerCase();
      if (cur.classList.length) part += '.' + [...cur.classList].slice(0, 3).map((c) => CSS.escape(c)).join('.');
      const parent = cur.parentElement;
      if (parent) {
        const same = [...parent.children].filter((x) => x.tagName === cur.tagName);
        if (same.length > 1) part += ':nth-of-type(' + (same.indexOf(cur) + 1) + ')';
      }
      parts.unshift(part);
      cur = parent;
    }
    return parts.join(' > ');
  }
  function showOutline(el) {
    if (!el || !(el instanceof Element)) { outline.style.display = 'none'; return; }
    const r = el.getBoundingClientRect();
    Object.assign(outline.style, { display: 'block', left: r.left + 'px', top: r.top + 'px', width: r.width + 'px', height: r.height + 'px' });
  }
  function persist() { localStorage.setItem(KEY, JSON.stringify(state.items)); }
  function renderCount() { $('#count').textContent = String(state.items.length); }
  function renderList() {
    $('#list').innerHTML = state.items.map((a, i) => `
      <div class="item" data-id="${esc(a.id)}">
        <div class="k">#${i + 1} ${esc(a.selector).slice(0, 90)}</div>
        <div class="n">${esc(a.note || a.text || '').slice(0, 160)}</div>
        <div class="ops"><button data-act="edit" data-id="${esc(a.id)}">编辑</button><button data-act="del" data-id="${esc(a.id)}" class="danger">删除</button></div>
      </div>
    `).join('') || '<div class="hint">还没有批注。</div>';
    renderCount();
    renderMarkers();
  }
  function targetOf(item) {
    try { return item.selector ? document.querySelector(item.selector) : null; } catch (_) { return null; }
  }
  let markerRaf = 0;
  function renderMarkers() {
    markerRaf = 0;
    const layer = $('#markers');
    layer.innerHTML = '';
    state.items.forEach((item, i) => {
      const el = targetOf(item);
      if (!el) return;
      const r = el.getBoundingClientRect();
      if (!r.width && !r.height) return;
      const m = document.createElement('button');
      m.className = 'marker';
      m.textContent = String(i + 1);
      m.title = item.note || item.text || item.selector || '';
      m.style.left = Math.max(0, Math.min(window.innerWidth - 20, r.right - 9)) + 'px';
      m.style.top = Math.max(0, Math.min(window.innerHeight - 20, r.top - 9)) + 'px';
      m.addEventListener('click', (e) => { e.preventDefault(); e.stopPropagation(); editItem(item.id); });
      layer.appendChild(m);
    });
  }
  function scheduleMarkers() {
    if (markerRaf) return;
    markerRaf = requestAnimationFrame(renderMarkers);
  }
  function openEditor(pending) {
    $('#meta').textContent = `${pending.selector}\n${pending.url || ''}`;
    $('#selector').value = pending.selector || '';
    $('#text').value = pending.text || '';
    $('#note').value = pending.note || '';
    panel.classList.add('open');
    showOutline(pending.el || targetOf(pending));
  }
  function editItem(id) {
    const item = state.items.find((x) => String(x.id) === String(id));
    if (!item) return;
    state.editingId = item.id;
    state.pending = {
      el: targetOf(item), selector: item.selector, text: item.text, note: item.note,
      rect: item.rect, url: item.url,
    };
    openEditor(state.pending);
    setActive(false);
  }
  function closeEditor() {
    state.pending = null;
    state.editingId = null;
    panel.classList.remove('open');
    showOutline(null);
  }
  function setActive(on) {
    state.active = on;
    $('#toggle').textContent = on ? '点选中…（Esc 退出）' : '开始点选';
    $('#toggle').classList.toggle('primary', !on);
    if (!on) showOutline(null);
  }
  function beginCapture(e) {
    if (!state.active) return;
    const el = e.target;
    if (!el || e.composedPath().includes(host)) return;
    e.preventDefault();
    e.stopPropagation();
    state.editingId = null;
    state.pending = { el, selector: selectorOf(el), text: (el.innerText || el.textContent || '').trim().slice(0, 500), rect: el.getBoundingClientRect().toJSON(), url: location.href };
    openEditor(state.pending);
    setActive(false);
  }
  function save() {
    if (!state.pending) return;
    const rec = {
      id: state.editingId || ('ann-' + Date.now().toString(36)),
      ts: new Date().toISOString(),
      url: state.pending.url || location.href,
      selector: ($('#selector').value || state.pending.selector).trim(),
      tag: (state.pending.el || targetOf(state.pending))?.tagName?.toLowerCase() || '',
      text: ($('#text').value || '').trim(),
      note: ($('#note').value || '').trim(),
      rect: state.pending.rect || null,
    };
    const idx = state.items.findIndex((x) => String(x.id) === String(rec.id));
    if (idx >= 0) state.items[idx] = rec; else state.items.push(rec);
    persist();
    closeEditor();
    renderList();
  }
  function removeItem(id) {
    const idx = state.items.findIndex((x) => String(x.id) === String(id));
    if (idx < 0) return;
    state.items.splice(idx, 1);
    persist();
    if (state.editingId === id) closeEditor();
    renderList();
  }
  function exportBody() {
    return state.items.map((x) => JSON.stringify(x)).join('\n') + (state.items.length ? '\n' : '');
  }
  function showExport() {
    $('#exporttext').value = exportBody() || '# no annotations yet\n';
    $('#exportbox').classList.add('open');
    $('#exporttext').focus();
    $('#exporttext').select();
  }
  function downloadExport() {
    const body = exportBody();
    const blob = new Blob([body], { type: 'application/x-ndjson' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'memoria-annotations.jsonl';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }
  async function copyExport() {
    const text = $('#exporttext').value;
    try {
      await navigator.clipboard.writeText(text);
      $('#copyexport').textContent = '已复制 ✓';
      setTimeout(() => { $('#copyexport').textContent = '复制到剪贴板'; }, 1500);
    } catch (e) {
      $('#exporttext').focus();
      $('#exporttext').select();
      document.execCommand('copy');
      $('#copyexport').textContent = '已复制 ✓';
      setTimeout(() => { $('#copyexport').textContent = '复制到剪贴板'; }, 1500);
    }
  }
  document.addEventListener('click', beginCapture, true);
  document.addEventListener('mousemove', (e) => { if (state.active) showOutline(e.target); }, true);
  document.addEventListener('keydown', (e) => {
    if (e.altKey && e.shiftKey && e.code === 'KeyA') { e.preventDefault(); setActive(!state.active); }
    if (e.key === 'Escape') { setActive(false); closeEditor(); }
  }, true);
  document.addEventListener('scroll', scheduleMarkers, true);
  window.addEventListener('resize', scheduleMarkers);
  $('#toggle').addEventListener('click', () => setActive(!state.active));
  $('#export').addEventListener('click', showExport);
  $('#copyexport').addEventListener('click', copyExport);
  $('#downloadexport').addEventListener('click', downloadExport);
  $('#closeexport').addEventListener('click', () => $('#exportbox').classList.remove('open'));
  $('#close').addEventListener('click', () => host.remove());
  $('#cancel').addEventListener('click', closeEditor);
  $('#delete').addEventListener('click', () => { if (state.editingId) removeItem(state.editingId); });
  $('#save').addEventListener('click', save);
  $('#list').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-act]');
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    if (btn.dataset.act === 'edit') editItem(btn.dataset.id);
    else if (btn.dataset.act === 'del') removeItem(btn.dataset.id);
  });
  renderList();
  setActive(false);
  window.__MEMORIA_ANNOTATOR__ = {
    toggle: () => setActive(!state.active),
    items: () => state.items.slice(),
    ensureMounted,
  };
})();
