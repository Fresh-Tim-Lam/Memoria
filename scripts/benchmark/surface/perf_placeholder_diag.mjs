/**
 * 占位块真实状态诊断：类名 / 数量 / computed style / 主题变量实际值
 * 关键：在"拖拽中"（有占位块时）查询，而不是物化后
 */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(u) { const r = await fetch(u); return await r.json(); }
class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) { return new Promise((res, rej) => { const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('ws timeout')), 25000); ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); }); ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('ws error')); }); }); }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(method, params = {}, timeoutMs = 120000) { return new Promise((res, rej) => { const id = ++this._id; const to = setTimeout(() => { this._p.delete(id); rej(new Error('cdp timeout ' + method)); }, timeoutMs); this._p.set(id, { resolve: (v) => { clearTimeout(to); res(v); }, reject: (e) => { clearTimeout(to); rej(e); } }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async ev(expr) { const r = await this.send('Runtime.evaluate', { expression: expr, returnByValue: true, userGesture: true }); if (r && r.exceptionDetails) throw new Error('eval: ' + String(r.exceptionDetails.text || '')); return r.result ? r.result.value : undefined; }
  async waitFor(expr, timeoutMs = 60000) { const t0 = Date.now(); while (Date.now() - t0 < timeoutMs) { try { if (await this.ev(`!!(${expr})`)) return true; } catch (e) { /* */ } await sleep(150); } return false; }
  close() { try { this.ws.close(); } catch { /* */ } }
}
const port = Number(process.argv[2]);
const DOC = process.argv[3] || '教材/08_第8章_差错控制编码.md';

let page = null;
for (let a = 0; a < 40; a++) {
  try { const l = await httpJson(`http://127.0.0.1:${port}/json/list`); page = (l || []).find(t => t.type === 'page' && /^https?:\/\//.test(t.url || '') && t.webSocketDebuggerUrl); if (page) break; } catch (e) { /* */ }
  await sleep(1000);
}
if (!page) { console.error('no page'); process.exit(2); }
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
if (!(await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', 90000))) { console.error('app not ready'); process.exit(2); }
await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);
await cdp.ev(`(function(){ try{ delete window.__MEMORIA_LAZY; }catch(e){} try{ localStorage.removeItem("memoria.perf.lazy"); }catch(e){} try{ window.__MEMORIA_DEFER=false; }catch(e){} return 1; })()`);

// ★ 关键：在"打开瞬间、首批物化前"抢查占位块状态
await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
for (let i = 0; i < 10; i++) { if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break; await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1;})()`); await sleep(200); }

// 立即高频采样（每 30ms），抓最早的占位块状态
const samples = [];
for (let k = 0; k < 40; k++) {
  const s = await cdp.ev(`(function(){
    var pv = document.getElementById('preview');
    if (!pv) return null;
    var cc = pv.querySelector('.-preview-content') || pv;
    var phClasses = ['. -pv-placeholder', '.-pv-placeholder', '[class*="placeholder"]'];
    var ph = cc.querySelectorAll('.-pv-placeholder');
    var anyPh = cc.querySelectorAll('[class*="placeholder"]');
    var first = ph[0] || anyPh[0];
    var cs = first ? getComputedStyle(first) : null;
    var root = getComputedStyle(document.documentElement);
    return {
      phCount_dash: ph.length,
      phCount_any: anyPh.length,
      ccClass: cc.className,
      totalBlocks: cc.querySelectorAll('.-src-block').length,
      firstPhClass: first ? first.className : null,
      firstBg: cs ? cs.backgroundColor : null,
      firstH: first ? Math.round(first.getBoundingClientRect().height) : null,
      varBgTertiary: root.getPropertyValue('--bg-tertiary').trim() || '(unset)',
      varTextPrimary: root.getPropertyValue('--text-primary').trim() || '(unset)',
      varPvBg: root.getPropertyValue('--pv-placeholder-bg').trim() || '(unset)',
      bodyBg: getComputedStyle(document.body).backgroundColor
    };
  })()`);
  if (s) samples.push({ t: k * 30, ...s });
  if (s && s.phCount_dash > 0 && samples.length > 3) break;
  await sleep(30);
}

console.log('=== 打开瞬间的占位块状态（前 6 个采样）===');
samples.slice(0, 6).forEach(s => {
  console.log('  t≈' + s.t + 'ms  ph(-pv-placeholder)=' + s.phCount_dash + '  ph(class*=placeholder)=' + s.phCount_any +
    '  blocks=' + s.totalBlocks);
});
console.log('');
const last = samples[samples.length - 1];
if (last) {
  console.log('=== 首个占位块详情 ===');
  console.log('  className: ' + last.firstPhClass);
  console.log('  backgroundColor: ' + last.firstBg);
  console.log('  height: ' + last.firstH + 'px');
  console.log('  cc.className: ' + last.ccClass);
  console.log('');
  console.log('=== 主题变量实际值 ===');
  console.log('  --bg-tertiary    = ' + last.varBgTertiary);
  console.log('  --text-primary   = ' + last.varTextPrimary);
  console.log('  --pv-placeholder-bg = ' + last.varPvBg);
  console.log('  body background  = ' + last.bodyBg);
  console.log('');
  // 计算 color-mix 结果
  const bg3 = last.varBgTertiary;
  console.log('=== color-mix 计算 ===');
  console.log('  color-mix(in srgb, var(--bg-tertiary, #333) 88%, var(--text-primary, #ccc) 4%)');
  console.log('  = color-mix(in srgb, ' + (bg3 === '(unset)' ? '#333(fallback)' : bg3) + ' 88%, ' + (last.varTextPrimary === '(unset)' ? '#ccc(fallback)' : last.varTextPrimary) + ' 4%)');
  console.log('  ⚠️ 百分比和 = 92% ≠ 100% ⇒ 浏览器按比例归一化 (88/92=95.65%, 4/92=4.35%)');
}
console.log('');
console.log('=== 全量采样（ph 变化过程）===');
samples.forEach(s => {
  if (s.phCount_dash > 0 || s.phCount_any > 0)
    console.log('  t≈' + s.t + 'ms  ph=' + s.phCount_dash + '  bg=' + s.firstBg);
});

// ① 样式表确认：app.css 是否加载、规则是否可查
const cssCheck = await cdp.ev(`(function(){
  var found = [];
  var out = { sheets: 0, withPlaceholderRule: 0, ruleText: null, matched: [] };
  try {
    for (var i = 0; i < document.styleSheets.length; i++) {
      var ss = document.styleSheets[i];
      out.sheets++;
      var rules = null;
      try { rules = ss.cssRules; } catch (e) { continue; }  // 跨域
      if (!rules) continue;
      for (var j = 0; j < rules.length; j++) {
        var r = rules[j];
        if (r.selectorText && r.selectorText.indexOf('pv-placeholder') >= 0) {
          out.withPlaceholderRule++;
          if (!out.ruleText) out.ruleText = r.cssText.slice(0, 250);
        }
      }
    }
  } catch (e) { out.err = String(e && e.message); }
  // 当前所有 el 里带 pv- 或 placeholder 的类名
  try {
    var els = document.querySelectorAll('[class*="pv-"], [class*="placeholder"]');
    var seen = {};
    for (var k = 0; k < els.length && out.matched.length < 8; k++) {
      var cls = els[k].className;
      if (typeof cls === 'string' && !seen[cls]) {
        seen[cls] = 1;
        var cs = getComputedStyle(els[k]);
        out.matched.push({ cls: cls, bg: cs.backgroundColor, h: els[k].style.height || '(no inline)' });
      }
    }
  } catch (e) { /* */ }
  return out;
})()`);
console.log('');
console.log('=== ① 样式表与类名确认 ===');
console.log('  styleSheets 总数: ' + cssCheck.sheets);
console.log('  含 pv-placeholder 规则的表数: ' + cssCheck.withPlaceholderRule);
if (cssCheck.ruleText) console.log('  规则文本: ' + cssCheck.ruleText);
if (cssCheck.err) console.log('  ⚠️ err: ' + cssCheck.err);
console.log('  实际出现的类名样本:');
(cssCheck.matched || []).forEach(m => console.log('    cls="' + m.cls + '"  bg=' + m.bg + '  h=' + m.h));

// ② 公式源码态持续时长（拖拽停止后）
console.log('');
console.log('=== ② 拖拽后「公式源码态」持续时长 ===');
// 先拖到 80%
for (let s = 1; s <= 10; s++) {
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*${(0.8 * s / 10).toFixed(3)}; return 1; })()`);
  await sleep(16);
}
const t20 = Date.now();
const rawSamples = [];
let untypedRunStart = null, maxUntypedRun = 0;
for (let k = 0; k < 80; k++) {
  const s = await cdp.ev(`(function(){
    var p = document.getElementById('preview-pane');
    if (!p) return null;
    var pr = p.getBoundingClientRect();
    var mjx = 0, rawDollar = 0, ph = 0;
    // 视口内 mjx-container
    p.querySelectorAll('mjx-container').forEach(function(e){ var r=e.getBoundingClientRect(); if (Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2) mjx++; });
    // 视口内占位块
    p.querySelectorAll('.-pv-placeholder').forEach(function(e){ var r=e.getBoundingClientRect(); if (Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2) ph++; });
    // 视口内"含 $ 的文本"（未排版公式的源码态）
    var walker = document.createTreeWalker(p, NodeFilter.SHOW_TEXT, null);
    var node;
    while ((node = walker.nextNode())) {
      var t = node.nodeValue || '';
      if (t.indexOf('$') < 0) continue;
      var parent = node.parentElement;
      if (!parent) continue;
      // 排除已在 mjx / code / pre 内的
      if (parent.closest('mjx-container') || parent.closest('pre') || parent.closest('code')) continue;
      var r = parent.getBoundingClientRect();
      if (Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top) > 2) rawDollar++;
    }
    return { mjx: mjx, rawDollar: rawDollar, ph: ph };
  })()`);
  if (s) {
    const t = Date.now() - t20;
    rawSamples.push({ t, ...s });
    if (s.rawDollar > 0 && s.mjx === 0) { if (untypedRunStart === null) untypedRunStart = t; }
    else { if (untypedRunStart !== null) { const d = t - untypedRunStart; if (d > maxUntypedRun) maxUntypedRun = d; untypedRunStart = null; } }
  }
  await sleep(50);
}
if (untypedRunStart !== null) { const d = (Date.now() - t20) - untypedRunStart; if (d > maxUntypedRun) maxUntypedRun = d; }

console.log('  ★ 「有 $ 源码但无 mjx」最长连续时长: ' + maxUntypedRun + 'ms');
console.log('  采样明细（前 30，只显示 rawDollar>0 或 ph>0）:');
rawSamples.slice(0, 30).forEach(s => {
  if (s.rawDollar > 0 || s.ph > 0)
    console.log('    t=' + s.t + 'ms  mjx=' + s.mjx + '  rawDollar=' + s.rawDollar + '  ph=' + s.ph);
});

// ③ 同一时刻三态对比
console.log('');
console.log('=== ③ 同一时刻三态对比（修复"phCount=0 但 cov=100%"矛盾）===');
const tri = await cdp.ev(`(function(){
  var p = document.getElementById('preview-pane');
  var pv = document.getElementById('preview');
  if (!p || !pv) return null;
  var cc = pv.querySelector('.-preview-content') || pv;
  var pr = p.getBoundingClientRect();
  var r = { paneClientH: p.clientHeight, scrollHeight: p.scrollHeight,
            phWhole: cc.querySelectorAll('.-pv-placeholder').length,
            phViewport: 0, covH: 0, mjxViewport: 0 };
  cc.querySelectorAll('.-pv-placeholder').forEach(function(e){
    var b = e.getBoundingClientRect();
    var vis = Math.min(pr.bottom, b.bottom) - Math.max(pr.top, b.top);
    if (vis > 2) { r.phViewport++; r.covH += vis; }
  });
  cc.querySelectorAll('mjx-container').forEach(function(e){ var b=e.getBoundingClientRect(); if (Math.min(pr.bottom,b.bottom)-Math.max(pr.top,b.top)>2) r.mjxViewport++; });
  r.cov = p.clientHeight > 0 ? +(r.covH / p.clientHeight).toFixed(3) : null;
  return r;
})()`);
console.log('  ' + JSON.stringify(tri));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
