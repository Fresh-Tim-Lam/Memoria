// Dev-only click annotation board for Memoria.
// Injected through WebView2 CDP; not part of the product build.
(() => {
  if (window.__MEMORIA_ANNOTATOR__) return;
  const KEY = 'memoria.dev.annotations.v1';
  const state = {
    active: false,
    pending: null,
    items: (() => { try { return JSON.parse(localStorage.getItem(KEY) || '[]'); } catch { return []; } })(),
  };
  const host = document.createElement('div');
  host.id = '__memoria_annotator_host__';
  host.style.all = 'initial';
  const root = host.attachShadow({ mode: 'open' });
  root.innerHTML = `
    <style>
      :host, * { box-sizing: border-box; }
      .wrap { position: fixed; right: 18px; bottom: 18px; z-index: 2147483000; font: 13px/1.45 system-ui, -apple-system, Segoe UI, sans-serif; color: #e6edf3; }
      .bar { display: flex; gap: 8px; align-items: center; background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 8px 10px; box-shadow: 0 8px 28px rgba(0,0,0,.45); }
      .bar b { font-weight: 650; font-size: 12px; color: #adbac7; }
      button { all: unset; cursor: pointer; padding: 5px 9px; border-radius: 7px; background: #21262d; border: 1px solid #30363d; color: #e6edf3; font: inherit; }
      button:hover { background: #30363d; }
      button.primary { background: #1f6feb; border-color: #1f6feb; color: #fff; }
      button.danger { color: #ff7b72; }
      .panel { margin-top: 8px; width: 360px; max-width: calc(100vw - 36px); background: #0d1117; border: 1px solid #30363d; border-radius: 10px; padding: 12px; box-shadow: 0 8px 28px rgba(0,0,0,.45); display: none; }
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
      .list { max-height: 180px; overflow: auto; margin-top: 8px; border-top: 1px solid #21262d; }
      .item { padding: 6px 0; border-bottom: 1px solid #21262d; font-size: 12px; }
      .item .k { color: #d2a8ff; }
      .item .n { color: #adbac7; }
      .outline { position: fixed; pointer-events: none; z-index: 2147482999; border: 2px solid #58a6ff; background: rgba(88,166,255,.12); border-radius: 3px; }
    </style>
    <div class="wrap">
      <div class="bar">
        <b>批注板</b>
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
          <button id="save" class="primary">保存</button>
        </div>
        <div class="hint">点选时按住 Alt 可复制元素选择器；Esc 取消当前点选。</div>
        <div class="list" id="list"></div>
      </div>
    </div>
  `;
  document.documentElement.appendChild(host);
  const $ = (s) => root.querySelector(s);
  const panel = $('#panel');
  const outline = document.createElement('div');
  outline.className = 'outline';
  outline.style.display = 'none';
  document.documentElement.appendChild(outline);

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
  function renderList() {
    $('#list').innerHTML = state.items.slice(-8).reverse().map((a, i) => `
      <div class="item"><span class="k">${esc(a.selector).slice(0, 70)}</span><br><span class="n">${esc(a.note || a.text || '').slice(0, 130)}</span></div>
    `).join('') || '<div class="hint">还没有批注。</div>';
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
    state.pending = { el, selector: selectorOf(el), text: (el.innerText || el.textContent || '').trim().slice(0, 500), rect: el.getBoundingClientRect().toJSON(), url: location.href };
    $('#meta').textContent = `${state.pending.selector}\n${state.pending.url}`;
    $('#selector').value = state.pending.selector;
    $('#text').value = state.pending.text;
    $('#note').value = '';
    panel.classList.add('open');
    showOutline(el);
    setActive(false);
  }
  function save() {
    if (!state.pending) return;
    const rec = {
      id: 'ann-' + Date.now().toString(36),
      ts: new Date().toISOString(),
      url: state.pending.url,
      selector: ($('#selector').value || state.pending.selector).trim(),
      tag: state.pending.el.tagName.toLowerCase(),
      text: ($('#text').value || '').trim(),
      note: ($('#note').value || '').trim(),
      rect: state.pending.rect,
    };
    state.items.push(rec);
    localStorage.setItem(KEY, JSON.stringify(state.items));
    state.pending = null;
    panel.classList.remove('open');
    showOutline(null);
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
    if (e.key === 'Escape') { setActive(false); panel.classList.remove('open'); showOutline(null); }
  }, true);
  $('#toggle').addEventListener('click', () => setActive(!state.active));
  $('#export').addEventListener('click', showExport);
  $('#copyexport').addEventListener('click', copyExport);
  $('#downloadexport').addEventListener('click', downloadExport);
  $('#closeexport').addEventListener('click', () => $('#exportbox').classList.remove('open'));
  $('#close').addEventListener('click', () => host.remove());
  $('#cancel').addEventListener('click', () => { state.pending = null; panel.classList.remove('open'); showOutline(null); });
  $('#save').addEventListener('click', save);
  renderList();
  setActive(false);
  window.__MEMORIA_ANNOTATOR__ = { toggle: () => setActive(!state.active), items: () => state.items.slice() };
})();
