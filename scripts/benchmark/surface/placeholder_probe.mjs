#!/usr/bin/env node
/**
 * placeholder_probe.mjs —— W3.4「占位高度估值准确性」对比探针（零新依赖）
 *
 * 目的：同一 fixture、同一窗口尺寸、同一缩放、同一进程里，先走**全量渲染**量真值，
 *   再走**惰性渲染**量占位估值 ⇒ 输出整篇 scrollHeight 比值 + 逐类型误差表 + 滚动期
 *   scrollHeight 变化（跳动）。
 *
 * 用法（一般由 run_placeholder_probe.py 调起，它负责 harness/密封配置/落报告）：
 *   node scripts/benchmark/surface/placeholder_probe.mjs --out <json> --url <url> \
 *        --file 教材/08_第8章_差错控制编码.md [--scroll-steps 24] [--settle-ms 2000]
 *
 * 口径：
 *   - 全量真值 = `window.__MEMORIA_LAZY=false` 下 `openFile()` 完成后稳定态的
 *     `#preview-pane.scrollHeight`；逐块真高 = `.-preview-content` 直接子元素的
 *     `getBoundingClientRect().height`（CSS 已把块 margin 归零，块高即贡献）。
 *   - 占位估值 = `window.__MEMORIA_LAZY=true` 下 `.-pv-placeholder` 的 inline
 *     `style.height`（与 `_makePlaceholder` 写入值同源）。
 *   - 逐类型统计按 `data--block-index` 与全量真值 join；类型由**全量真块**的
 *     tagName / class 判定（占位 div 自身不带类型）。
 *   - 动态过程：惰性模式下从顶到底分步滚动，每步记录 scrollHeight；跳动 = 整轮
 *     scrollHeight 的极差 / 全量真值。
 */

import fs from 'node:fs';
import path from 'node:path';
import { withBrowser, sleep } from './interaction.mjs';

const js = (v) => JSON.stringify(v);

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    if (!k.startsWith('--')) continue;
    const key = k.slice(2);
    const v = argv[i + 1];
    if (v === undefined || v.startsWith('--')) out[key] = true;
    else { out[key] = v; i++; }
  }
  return out;
}

// ── 页面内：逐块量高 + 类型分类 ───────────────────────────────────────────────
const BLOCK_MEASURE_JS = `(function(){
  var pane=document.getElementById('preview-pane');
  var pv=document.getElementById('preview');
  var cc=pv?pv.querySelector('.-preview-content'):null;
  if(!pane||!cc)return {ok:false,reason:'no-pane-or-content'};
  var kids=cc.children,n=kids.length;
  var blocks=new Array(n);
  var sum=0,topSum=0;
  var tops=new Array(n),bottoms=new Array(n),heights=new Array(n);
  for(var i=0;i<n;i++){
    var el=kids[i];
    var r=el.getBoundingClientRect();
    tops[i]=r.top;bottoms[i]=r.bottom;heights[i]=r.height;
    var h=Math.round(r.height*100)/100;
    sum+=r.height;
    var idx=parseInt(el.getAttribute('data--block-index'),10);
    var sl=parseInt(el.getAttribute('data--src-line'),10);
    var se=parseInt(el.getAttribute('data--src-line-end'),10);
    var ph=el.classList.contains('-pv-placeholder');
    var type='unknown';
    if(ph){type='__placeholder__';}
    else{
      var tn=String(el.tagName||'').toUpperCase();
      var cl=el.classList;
      if(cl.contains('-blank-block'))type='blank_line';
      else if(cl.contains('-math-block'))type='math_block';
      else if(cl.contains('-code-block'))type='code_block';
      else if(cl.contains('-mermaid'))type='mermaid';
      else if(cl.contains('-table'))type='table';
      else if(cl.contains('-image-block'))type='image';
      else if(tn==='HR')type='horizontal_rule';
      else if(tn==='H1'||tn==='H2'||tn==='H3'||tn==='H4'||tn==='H5'||tn==='H6')type='heading';
      else if(tn==='P')type='paragraph';
      else if(tn==='UL'||tn==='OL')type='list';
      else if(tn==='BLOCKQUOTE')type='blockquote';
      else if(cl.contains('-unsupported-block'))type='unsupported';
    }
    var est=null;
    if(ph){var st=parseFloat(el.style.height);est=isFinite(st)?Math.round(st*100)/100:null;}
    var img=null;
    if(!ph&&type==='image'){
      var im=el.querySelector('img');
      img=im?{complete:!!im.complete,nw:im.naturalWidth||0,nh:im.naturalHeight||0,
              src:(im.getAttribute('src')||'').slice(0,140),
              boxH:Math.round(im.getBoundingClientRect().height*100)/100}:null;
    }
    var cs=null;
    if(!ph){var _cs=getComputedStyle(el);cs={mt:parseFloat(_cs.marginTop)||0,mb:parseFloat(_cs.marginBottom)||0,
      lh:(_cs.lineHeight==='normal'?null:parseFloat(_cs.lineHeight)),fs:parseFloat(_cs.fontSize)||0};}
    blocks[i]={i:i,idx:isNaN(idx)?null:idx,type:type,ph:ph,h:h,est:est,
               sl:(!isNaN(sl))?sl:null,se:(!isNaN(se))?se:null,
               lines:(!isNaN(sl)&&!isNaN(se)&&se>=sl)?(se-sl+1):null,img:img,cs:cs,
               textLen:(!ph&&el.textContent)?String(el.textContent).length:null,
               text:(!ph&&el.textContent)?String(el.textContent).slice(0,4000):null,
               tag:String(el.tagName||'').toLowerCase(),cls:String(el.className||'').slice(0,120)};
  }
  // 真实「布局贡献」：用相邻块 top 差（包含块间外边距/MathJax 上下 margin），
  // 末块用自身高度。逐块 rect 高度之和会漏掉公式等内部外边距 ⇒ 与 scrollHeight 对不上。
  for(var q=0;q<n;q++){
    var contrib=(q<n-1)?(tops[q+1]-tops[q]):(bottoms[q]-tops[q]);
    if(!(contrib>=0))contrib=heights[q];
    blocks[q].contrib=Math.round(contrib*100)/100;
    topSum+=contrib;
  }
  var ws=(typeof window.__MEMORIA_WORKSET_STATS==='function')?window.__MEMORIA_WORKSET_STATS():null;
  var imgs=cc.querySelectorAll('img');
  var imgStat={total:imgs.length,complete:0,loaded:0,failed:0};
  for(var k=0;k<imgs.length;k++){
    var im2=imgs[k];
    if(im2.complete)imgStat.complete++;
    if(im2.naturalWidth>0)imgStat.loaded++;
    else if(im2.complete)imgStat.failed++;
  }
  var mjxCount=cc.querySelectorAll('mjx-container').length;
  var mjMathSize=null;
  try{var md=window.MathJax&&window.MathJax.startup&&window.MathJax.startup.document;
      mjMathSize=md&&md.math?md.math.size:null;}catch(e){}
  return {ok:true,n:n,scrollHeight:Math.round(pane.scrollHeight*10)/10,
          clientHeight:Math.round(pane.clientHeight*10)/10,
          scrollTop:Math.round(pane.scrollTop*10)/10,
          sumBlockH:Math.round(sum*100)/100,
          sumContrib:Math.round(topSum*100)/100,
          contentScrollHeight:(cc.scrollHeight||0),
          availWidth:cc.clientWidth||0,
          panePadTop:parseFloat(getComputedStyle(pane).paddingTop)||0,
          panePadBottom:parseFloat(getComputedStyle(pane).paddingBottom)||0,
          blocks:blocks,workset:ws,imgStat:imgStat,
          mjxCount:mjxCount,mjMathSize:mjMathSize,
          lazyHook:(typeof window.__MEMORIA_LAZY==='boolean')?window.__MEMORIA_LAZY:null,
          viewport:window.innerWidth+'x'+window.innerHeight,
          dpr:window.devicePixelRatio||1};
})()`;

const RAF_JS = `(async function(frames){
  var ts=[],last=performance.now(),n=0;
  return await new Promise(function(res){
    function tick(){var now=performance.now();if(n>0)ts.push(now-last);last=now;n++;if(n>frames)return res(ts);requestAnimationFrame(tick);}
    requestAnimationFrame(tick);
  });
})`;

function median(a) {
  if (!a || !a.length) return null;
  const s = a.slice().sort((x, y) => x - y);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

async function measureBlocks(cdp) {
  return await cdp.evalJS(BLOCK_MEASURE_JS);
}

/** 等 scrollHeight 稳定（连续 stableReads 次相同），返回最后一次测量。 */
async function waitStable(cdp, { stableReads = 4, interval = 400, timeout = 90000, minWait = 0 } = {}) {
  const t0 = Date.now();
  if (minWait) await sleep(minWait);
  let last = null, same = 0, m = null;
  for (;;) {
    m = await measureBlocks(cdp);
    if (!m || !m.ok) throw new Error('measure failed: ' + JSON.stringify(m));
    if (last != null && Math.abs(m.scrollHeight - last) < 0.6) same++;
    else same = 0;
    last = m.scrollHeight;
    if (same >= stableReads) return m;
    if (Date.now() - t0 > timeout) return m;
    await sleep(interval);
  }
}

async function openMode(cdp, file, lazy, th) {
  await cdp.evalJS(`(function(lazy){
    window.__MEMORIA_LAZY = !!lazy;
    try{localStorage.setItem('memoria.perf.lazy', lazy?'1':'0')}catch(e){}
    return window.__MEMORIA_LAZY;
  })(${lazy ? 'true' : 'false'})`);
  // 确保预览视图
  await cdp.evalJS(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]');if(b&&(window.state||{}).viewMode!=='preview')b.click();return (window.state||{}).viewMode;})()`);
  const t0 = Date.now();
  const opened = await cdp.evalJS(`(async function(file){
    try{ await window.MemoriaApp.openFile(file,{}); }
    catch(e){ return {error:String((e&&e.message)||e)}; }
    var pane=document.getElementById('preview-pane');
    var pv=document.getElementById('preview');
    return {ok:true, currentPath:(window.state||{}).currentPath||null,
            nBlocks:(pane&&pv)?pv.querySelectorAll('.-src-block').length:0};
  })(${js(file)})`);
  if (!opened || !opened.ok) throw new Error('openFile failed: ' + JSON.stringify(opened));
  const wall = Date.now() - t0;
  // 等块数与占位/物化状态到位
  await cdp.waitFor(`(function(){
    var p=document.getElementById('preview-pane');
    var cc=p?document.getElementById('preview').querySelector('.-preview-content'):null;
    if(!cc)return false;
    var kids=cc.children;
    if(kids.length<2)return false;
    var ph=cc.querySelectorAll('.-pv-placeholder').length;
    var ws=(typeof window.__MEMORIA_WORKSET_STATS==='function')?window.__MEMORIA_WORKSET_STATS():null;
    if(!ws)return false;
    if(${lazy ? 'true' : 'false'}) return ws.placeholders>0;
    return ws.placeholders===0;
  })()`, { timeout: 60000, label: lazy ? 'lazy-placeholders' : 'full-no-placeholders' });
  const m = await waitStable(cdp, { minWait: th.postOpenSettleMs || 1200, stableReads: 5, interval: 450, timeout: th.settleTimeoutMs || 90000 });
  m.openWallMs = wall;
  return m;
}

// ── 逐类型聚合 ───────────────────────────────────────────────────────────────
function aggregate(full, lazy) {
  const byIdx = new Map();
  for (const b of full.blocks) if (b.idx != null) byIdx.set(b.idx, b);
  const types = {};
  const mism = [];
  for (const b of lazy.blocks) {
    if (b.idx == null) continue;
    const fb = byIdx.get(b.idx);
    if (!fb) { mism.push(b.idx); continue; }
    if (fb.type === '__placeholder__') continue;
    const t = fb.type;
    if (!types[t]) types[t] = { count: 0, phCount: 0, matCount: 0, sumReal: 0, sumEst: 0, sumRect: 0, sumLines: 0, sumText: 0, ratios: [], reals: [], lineHist: {}, tags: {} };
    const rec = types[t];
    rec.count++;
    const ln = fb.lines || 0;
    if (!rec.lineHist[ln]) rec.lineHist[ln] = { count: 0, sumReal: 0 };
    rec.lineHist[ln].count++;
    rec.lineHist[ln].sumReal += fb.contrib;
    rec.sumReal += fb.contrib;   // 真实布局贡献（含块间/块内外边距）
    rec.sumRect += fb.h;
    rec.sumLines += fb.lines || 0;
    rec.sumText += fb.textLen || 0;
    rec.reals.push(fb.contrib);
    if (fb.tag) rec.tags[fb.tag + (fb.cls ? '.' + fb.cls.split(' ')[0] : '')] = (rec.tags[fb.tag + (fb.cls ? '.' + fb.cls.split(' ')[0] : '')] || 0) + 1;
    if (b.ph) {
      rec.phCount++;
      rec.sumEst += b.contrib;   // 占位实际布局贡献（≈ inline height）
    } else {
      rec.matCount++;
      rec.sumEst += b.contrib;   // 已物化：估值即真实
    }
    if (b.est != null && fb.contrib > 0) rec.ratios.push(b.est / fb.contrib);
  }
  const rows = [];
  for (const t of Object.keys(types)) {
    const r = types[t];
    const realMean = r.sumReal / r.count;
    const estMean = r.sumEst / r.count;
    const sorted = r.reals.slice().sort((a, b) => a - b);
    const q = (p) => sorted.length ? Math.round(sorted[Math.min(sorted.length - 1, Math.floor(p * sorted.length))] * 100) / 100 : null;
    rows.push({
      type: t, count: r.count, placeholders: r.phCount, materialized: r.matCount,
      meanRealH: Math.round(realMean * 100) / 100,
      medianRealH: q(0.5), p90RealH: q(0.9),
      meanRectH: Math.round((r.sumRect / r.count) * 100) / 100,
      meanGap: Math.round(((r.sumReal - r.sumRect) / r.count) * 100) / 100,
      meanEstH: Math.round(estMean * 100) / 100,
      ratio: realMean > 0 ? Math.round((estMean / realMean) * 10000) / 10000 : null,
      pct: realMean > 0 ? Math.round((estMean / realMean - 1) * 10000) / 100 : null,
      meanLines: Math.round((r.sumLines / r.count) * 100) / 100,
      meanTextLen: Math.round((r.sumText / r.count) * 10) / 10,
      lineHist: Object.keys(r.lineHist).sort((a, b) => a - b).reduce((o, k) => {
        o[k] = { count: r.lineHist[k].count, meanRealH: Math.round((r.lineHist[k].sumReal / r.lineHist[k].count) * 100) / 100 };
        return o;
      }, {}),
      tags: r.tags,
    });
  }
  rows.sort((a, b) => b.count - a.count);
  return { rows, mismatches: mism.length };
}

// ── 滚动期 scrollHeight 变化 ────────────────────────────────────────────────
async function scrollTrace(cdp, steps, pauseMs) {
  const series = [];
  await cdp.evalJS(`(function(){var p=document.getElementById('preview-pane');if(p)p.scrollTop=0;return p?p.scrollTop:null;})()`);
  await sleep(600);
  for (let i = 0; i <= steps; i++) {
    const r = await cdp.evalJS(`(function(f){
      var p=document.getElementById('preview-pane');
      if(!p)return null;
      var max=Math.max(0,p.scrollHeight-p.clientHeight);
      p.scrollTop=Math.round(max*f);
      return {f:f,scrollTop:Math.round(p.scrollTop*10)/10,scrollHeight:Math.round(p.scrollHeight*10)/10,
              clientHeight:Math.round(p.clientHeight*10)/10};
    })(${i / steps})`);
    series.push(r);
    await sleep(pauseMs);
  }
  // 回顶再量一次（渲染收尾可能改高度）
  await cdp.evalJS(`(function(){var p=document.getElementById('preview-pane');if(p)p.scrollTop=0;return p?p.scrollTop:null;})()`);
  await sleep(900);
  const tail = await measureBlocks(cdp);
  const hs = series.filter(Boolean).map((s) => s.scrollHeight);
  const min = Math.min(...hs), max = Math.max(...hs);
  return {
    series,
    steps: series.length,
    minScrollHeight: min,
    maxScrollHeight: max,
    spreadPx: Math.round((max - min) * 10) / 10,
    spreadPct: Math.round(((max - min) / max) * 10000) / 100,
    backToTopScrollHeight: tail.scrollHeight,
    tailWorkset: tail.workset,
  };
}

// ── 主流程 ──────────────────────────────────────────────────────────────────
async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.out || !args.url || !args.file) {
    throw new Error('用法：--out <json> --url <url> --file <kb-relative-md> [--scroll-steps N] [--settle-ms N]');
  }
  const th = {
    postOpenSettleMs: parseInt(args['settle-ms'] || '1500', 10),
    settleTimeoutMs: parseInt(args['settle-timeout-ms'] || '120000', 10),
    scrollSteps: parseInt(args['scroll-steps'] || '24', 10),
    scrollPauseMs: parseInt(args['scroll-pause-ms'] || '220', 10),
    p50MaxMs: 20,
  };
  const run = async (cdp) => {
    // L0 测量可信门
    const samples = await cdp.evalJS(`(${RAF_JS})(${90})`);
    const p50 = median(samples);
    const raf = { p50Ms: p50, frames: samples.length, trusted: p50 != null && p50 <= th.p50MaxMs };
    const info = await cdp.evalJS(`({href:location.href,innerWidth:window.innerWidth,innerHeight:window.innerHeight,dpr:window.devicePixelRatio||1})`);

    const full = await openMode(cdp, args.file, false, th);
    const lazy = await openMode(cdp, args.file, true, th);
    const agg = aggregate(full, lazy);
    // 回到惰性模式做滚动轨迹（openMode 已停在 lazy）
    const scroll = await scrollTrace(cdp, th.scrollSteps, th.scrollPauseMs);

    const fullH = full.scrollHeight;
    const lazyH = lazy.scrollHeight;
    const out = {
      schema: 'memoria-placeholder-probe/v1',
      startedAt: new Date().toISOString(),
      url: args.url,
      file: args.file,
      browser: info,
      measurement: { raf, trusted: raf.trusted },
      thresholds: th,
      full: { scrollHeight: fullH, clientHeight: full.clientHeight, availWidth: full.availWidth, sumBlockH: full.sumBlockH, sumContrib: full.sumContrib, contentScrollHeight: full.contentScrollHeight, panePadTop: full.panePadTop, panePadBottom: full.panePadBottom, workset: full.workset, imgStat: full.imgStat, openWallMs: full.openWallMs, n: full.n },
      lazy: { scrollHeight: lazyH, clientHeight: lazy.clientHeight, sumBlockH: lazy.sumBlockH, sumContrib: lazy.sumContrib, contentScrollHeight: lazy.contentScrollHeight, workset: lazy.workset, imgStat: lazy.imgStat, openWallMs: lazy.openWallMs, n: lazy.n },
      deltaPct: Math.round(((lazyH - fullH) / fullH) * 10000) / 100,
      ratio: Math.round((lazyH / fullH) * 10000) / 10000,
      perType: agg.rows,
      joinMismatches: agg.mismatches,
      diagnostics: {
        mathjax: { mjxCount: full.mjxCount, mathListSize: full.mjMathSize },
        samples: ['blank_line', 'math_block', 'paragraph', 'image', 'unknown'].reduce((o, t) => {
          o[t] = full.blocks.filter((b) => b.type === t).slice(0, 6).map((b) => ({
            idx: b.idx, h: b.h, contrib: b.contrib, lines: b.lines, cs: b.cs, cls: b.cls,
          }));
          return o;
        }, {}),
      },
      scrollTrace: scroll,
      checks: {
        within2pct: Math.abs((lazyH - fullH) / fullH) <= 0.02,
        measurementTrusted: raf.trusted,
        noPlaceholderLeft: lazy.workset ? lazy.workset.placeholders > 0 : null,
      },
    };
    fs.mkdirSync(path.dirname(path.resolve(args.out)), { recursive: true });
    if (args['dump-blocks']) {
      fs.writeFileSync(path.resolve(args.out).replace(/\.json$/, '.blocks.json'),
        JSON.stringify({ file: args.file, viewport: info, full: full.blocks, lazy: lazy.blocks }), 'utf8');
    }
    fs.writeFileSync(path.resolve(args.out), JSON.stringify(out, null, 2), 'utf8');
    fs.writeFileSync(path.resolve(args.out).replace(/\.json$/, '.txt'), renderText(out), 'utf8');
    return out;
  };
  const extraArgs = ['--js-flags=--expose-gc', '--enable-precise-memory-info'];
  const out = args['cdp-port']
    ? await (async () => { const { withLiveApp } = await import('./interaction.mjs'); return withLiveApp(parseInt(args['cdp-port'], 10), run); })()
    : await withBrowser(args.url, run, { extraArgs });
  process.stdout.write('__PLACEHOLDER_PROBE_JSON__' + JSON.stringify({
    ok: out.checks.within2pct, out: path.resolve(args.out),
    deltaPct: out.deltaPct, ratio: out.ratio, scrollSpreadPct: out.scrollTrace.spreadPct,
  }) + '\n');
  process.exit(0);
}

function renderText(out) {
  const L = [];
  L.push('# W3.4 占位高度估值对比探针');
  L.push('');
  L.push('- 时间：' + out.startedAt);
  L.push('- 文件：`' + out.file + '`');
  L.push('- 视口：' + out.browser.innerWidth + '×' + out.browser.innerHeight + '，dpr=' + out.browser.dpr);
  L.push('- 测量可信门：rAF p50=' + out.measurement.raf.p50Ms + 'ms ⇒ ' + (out.measurement.trusted ? '可信' : '不可信'));
  L.push('- 全量 scrollHeight：' + out.full.scrollHeight + ' px（' + out.full.n + ' 块，' + out.full.openWallMs + ' ms）');
  L.push('- 惰性 scrollHeight：' + out.lazy.scrollHeight + ' px（占位 ' + (out.lazy.workset || {}).placeholders + '，物化 ' + (out.lazy.workset || {}).materialized + '，' + out.lazy.openWallMs + ' ms）');
  L.push('- **偏差：' + (out.deltaPct >= 0 ? '+' : '') + out.deltaPct + '%**（目标 |Δ| ≤ 2%）');
  L.push('- 滚动过程 scrollHeight 极差：' + out.scrollTrace.spreadPx + ' px = ' + out.scrollTrace.spreadPct + '%');
  L.push('- 图片：全量 total=' + out.full.imgStat.total + ' loaded=' + out.full.imgStat.loaded + ' failed=' + out.full.imgStat.failed + ' / 惰性 total=' + out.lazy.imgStat.total);
  L.push('');
  L.push('| 类型 | 块数 | 占位 | 真实均值 px | 中位 | p90 | rect均值 | gap均值 | 估值均值 px | 偏差 | 平均源行 | 平均字数 | 标签 |');
  L.push('|---|---|---|---|---|---|---|---|---|---|---|---|---|');
  for (const r of out.perType) {
    L.push('| ' + r.type + ' | ' + r.count + ' | ' + r.placeholders + ' | ' + r.meanRealH + ' | ' + r.medianRealH + ' | ' + r.p90RealH + ' | ' + r.meanRectH + ' | ' + r.meanGap + ' | ' + r.meanEstH + ' | ' + (r.pct == null ? '—' : (r.pct >= 0 ? '+' : '') + r.pct + '%') + ' | ' + r.meanLines + ' | ' + r.meanTextLen + ' | ' + Object.keys(r.tags || {}).join(', ') + ' |');
  }
  L.push('');
  L.push('## 滚动轨迹（scrollHeight）');
  L.push('');
  L.push(out.scrollTrace.series.filter(Boolean).map((s) => Math.round(s.f * 100) + '%=' + s.scrollHeight).join('；'));
  return L.join('\n') + '\n';
}

main().catch((e) => {
  process.stderr.write(String((e && e.stack) || e) + '\n');
  process.exit(1);
});
