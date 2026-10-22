#!/usr/bin/env node
/**
 * lazy_gate.mjs —— W4.1「惰性路径交互门禁」执行器（零新依赖）
 *
 * 为什么要有它：`interaction.mjs` 的 12 个剧本都跑 <200 块小文档 ⇒ 永远全量渲染，
 *   惰性物化 / 工作集淘汰 / 公式 pending 三个特性没有固定回归。本文件复用同一套
 *   CDP 基础设施（`interaction.mjs` 的 withBrowser / Interactions），专门量**大文档**：
 *
 *   L0 测量可信门：空转 rAF p50 ≤ 20ms（最小化窗口会节流 rAF ⇒ 假读数，必须拒跑）
 *   L1 打开：≥1000 块 → 首块可见 ≤500ms，且确实走惰性路径（占位 > 0、未全量物化）
 *   L2 位置：30/50/70/90% 每个位置 ⇒ 视口占位=0、关键文本命中、相对漂移 ≤5 行
 *   L3 回顶：绝对位置 Δ≤5 行、视口占位=0、无白屏
 *   L4 长滚动：物化块 ≤ 8 屏、evictTotal>0、堆不单调增长
 *   L5 编辑保护：编辑已物化块 → 远处淘汰 → 内容与光标位置不受影响
 *
 * 用法（一般由 run_lazy_gate.py 调起，它负责起 harness/密封配置/落报告）：
 *   node scripts/benchmark/surface/lazy_gate.mjs --scenarios <json> --out <json> --url <url>
 *
 * 负向验证（证明门禁抓得住真实缺陷；结果必须 FAIL）：
 *   --sabotage noevict             调用产品自带 `__MEMORIA_MATERIALIZE_ALL()`（全程停淘汰）
 *   --sabotage viewport-placeholder 把视口内某已物化块换回占位（模拟“视口占位残留”）
 */

import fs from 'node:fs';
import path from 'node:path';
import { withBrowser, Interactions, sleep } from './interaction.mjs';

// ─────────────────────────────────────────────────────────────────────────────
// 0. 小工具
// ─────────────────────────────────────────────────────────────────────────────
const js = (v) => JSON.stringify(v);

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) continue;
    const k = a.slice(2);
    const v = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true;
    out[k] = v;
  }
  return out;
}

function pct(part, total) {
  return total > 0 ? Math.round((part / total) * 1000) / 10 : null;
}

function loadFixture(p) {
  const text = fs.readFileSync(p, 'utf8');
  const lines = text.split(/\r?\n/);
  const markers = [];
  for (let i = 0; i < lines.length; i++) {
    const m = /(LAZYGATE-MARK-\d+)/.exec(lines[i]);
    if (m) markers.push({ id: m[1], line: i + 1 });
  }
  return { path: p, totalLines: lines.length, lines, markers };
}

/** 断言累计器：同一个 check 的 steps 里逐条记录 expected/actual，FAIL 时能定位到具体步骤。 */
function makeCheck(id, desc) {
  const rec = { id, desc, status: 'PASS', steps: [], error: null };
  return {
    rec,
    step(name) {
      const st = { step: name, ok: true, assertions: [], readings: {} };
      rec.steps.push(st);
      return {
        read(k, v) { st.readings[k] = v; },
        assert(name2, ok, expected, actual, note) {
          st.assertions.push({ name: name2, ok: !!ok, expected, actual: actual === undefined ? null : actual, note: note || null });
          if (!ok) { st.ok = false; rec.status = 'FAIL'; }
          return !!ok;
        },
        get ok() { return st.ok; },
      };
    },
    fail(err) {
      rec.status = 'FAIL';
      rec.error = String((err && err.message) || err);
      rec.steps.push({ step: 'error', ok: false, assertions: [{ name: 'no-exception', ok: false, expected: 'no exception', actual: rec.error }], readings: {} });
    },
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. 页面内测量原语
// ─────────────────────────────────────────────────────────────────────────────
/**
 * 一次测量返回「视口内」的真实状态。用二分定位视口块区间（`.-preview-content` 子元素
 * 按文档序排列、位置单调）⇒ 不随文档规模线性变慢，也不因数千次 rect 读而制造长帧。
 */
const MEASURE_JS = `(function(){
  var pane=document.getElementById('preview-pane');
  var pv=document.getElementById('preview');
  var cc=pv?pv.querySelector('.-preview-content'):null;
  var out={ok:false,reason:null};
  if(!pane||!pv||!cc){out.reason='no-pane-or-preview-content';return out;}
  var pr=pane.getBoundingClientRect();
  var kids=cc.children,n=kids.length,rect=function(e){return e.getBoundingClientRect();};
  if(!n){out.reason='no-blocks';return out;}
  // first：bottom > 视口顶
  var lo=0,hi=n-1,first=n;
  while(lo<=hi){var m=(lo+hi)>>1;if(rect(kids[m]).bottom>pr.top){first=m;hi=m-1;}else{lo=m+1;}}
  // last：top < 视口底
  var last=-1;lo=first;hi=n-1;
  while(lo<=hi){var m2=(lo+hi)>>1;if(rect(kids[m2]).top<pr.bottom){last=m2;lo=m2+1;}else{hi=m2-1;}}
  var vpPh=0,vpReal=0,vpTextLen=0,vpText='',topLine=null,bottomLine=null,vpMedia=0;
  var topBlockIndex=null,topBlockTop=null;
  var vpBlocks=[];
  // mermaid 的 style 元素会被 textContent 吞进来（实测单个块 5014 字符 CSS）⇒ 跳过 STYLE/SCRIPT。
  function textOf(el){
    var out='';
    for(var ci=0;ci<el.childNodes.length;ci++){
      var c=el.childNodes[ci];
      if(c.nodeType===3)out+=c.nodeValue;
      else if(c.nodeType===1){
        var tn=String(c.tagName||'').toUpperCase();
        if(tn!=='STYLE'&&tn!=='SCRIPT')out+=' '+textOf(c);
      }
    }
    return out;
  }
  if(first<n&&!isNaN(first)){
    for(var i=first;i<=last;i++){
      var el=kids[i];
      var sl=parseInt(el.getAttribute('data--src-line'),10);
      var se=parseInt(el.getAttribute('data--src-line-end'),10);
      if(topLine===null&&!isNaN(sl)&&sl>0)topLine=sl;
      if(!isNaN(se)&&se>0&&(bottomLine===null||se>bottomLine))bottomLine=se;
      if(i===first){
        topBlockIndex=parseInt(el.getAttribute('data--block-index'),10);
        topBlockTop=Math.round(rect(el).top*10)/10;
      }
      if(el.classList.contains('-pv-placeholder')){vpPh++;if(vpBlocks.length<24)vpBlocks.push({idx:parseInt(el.getAttribute('data--block-index'),10),line:isNaN(sl)?null:sl,ph:true});continue;}
      vpReal++;
      var t=textOf(el).replace(/\\s+/g,' ').trim();
      if(el.querySelector('svg,table,img,mjx-container'))vpMedia++;
      vpTextLen+=t.length;
      if(t)vpText+=' '+t;
      if(vpBlocks.length<24)vpBlocks.push({idx:parseInt(el.getAttribute('data--block-index'),10),line:isNaN(sl)?null:sl,end:isNaN(se)?null:se,ph:false,len:t.length,kind:(el.querySelector('svg')||el.querySelector('.-mermaid-pan')?'diagram':(el.querySelector('table')?'table':(el.querySelector('pre')?'code':(el.querySelector('mjx-container')?'math':'text')))),text:t.slice(0,400)});
    }
  }
  var ws=(typeof window.__MEMORIA_WORKSET_STATS==='function')?window.__MEMORIA_WORKSET_STATS():null;
  var mem=window.performance&&performance.memory?performance.memory:null;
  var firstEl=kids[0],lastEl=kids[n-1];
  out={
    ok:true,reason:null,
    paneTop:Math.round(pr.top*10)/10,paneBottom:Math.round(pr.bottom*10)/10,
    paneHeight:Math.round(pr.height*10)/10,
    scrollTop:Math.round(pane.scrollTop*10)/10,
    scrollHeight:Math.round(pane.scrollHeight*10)/10,
    clientHeight:Math.round(pane.clientHeight*10)/10,
    ratio:pane.scrollHeight>pane.clientHeight?Math.round((pane.scrollTop/(pane.scrollHeight-pane.clientHeight))*1000)/1000:0,
    firstBlockIndex:firstEl?parseInt(firstEl.getAttribute('data--block-index'),10):null,
    firstBlockTop:firstEl?Math.round(rect(firstEl).top*10)/10:null,
    lastBlockIndex:lastEl?parseInt(lastEl.getAttribute('data--block-index'),10):null,
    lastBlockLine:lastEl?parseInt(lastEl.getAttribute('data--src-line-end'),10):null,
    blocksInDom:n,
    vpPlaceholders:vpPh,vpRealBlocks:vpReal,vpTextLen:vpTextLen,vpMedia:vpMedia,
    vpMarkers:(vpText.match(/LAZYGATE-MARK-\\d+/g)||[]),
    vpTextSample:vpText.slice(0,220),
    vpBlocks:vpBlocks,
    topLine:topLine,bottomLine:bottomLine,topBlockIndex:topBlockIndex,topBlockTop:topBlockTop,
    workset:ws,
    heapMB:mem?Math.round(mem.usedJSHeapSize/1048576*100)/100:null,
    domPreview:pv.getElementsByTagName('*').length,
    domBody:document.body.getElementsByTagName('*').length,
    lazyHook:(typeof window.__MEMORIA_LAZY==='boolean')?window.__MEMORIA_LAZY:null,
    editMode:window.MemoriaEditHandler?!!window.MemoriaEditHandler.editMode:null
  };
  return out;
})()`;

async function measure(cdp) {
  return await cdp.evalJS(MEASURE_JS);
}

/** 「无白屏」判据：视口里至少 3 个真块，且有可读文本或媒体（图/表/公式）。
 *  mermaid 屏可能只有少量文字（SVG 标签），不能按纯文本长度判空白。 */
function hasVisibleContent(m) {
  return !!m && m.vpRealBlocks >= 3 && (m.vpTextLen >= 40 || m.vpMedia > 0);
}

/** 等「视口内占位 = 0」连续 3 次（60ms 采样）——这是“用户停下后不再看到空洞”的判据。 */
async function waitViewportSettled(cdp, { timeoutMs = 9000, requireText = 1 } = {}) {
  const t0 = Date.now();
  let stable = 0, last = null, samples = 0;
  while (Date.now() - t0 < timeoutMs) {
    const m = await measure(cdp);
    samples++;
    last = m;
    const okNow = m && m.ok && m.vpPlaceholders === 0 && m.vpRealBlocks >= requireText;
    if (okNow) stable++; else stable = 0;
    if (stable >= 3) return { settled: true, ms: Date.now() - t0, samples, last };
    await sleep(60);
  }
  return { settled: false, ms: Date.now() - t0, samples, last };
}

/** 把「源文件行号」对应的块滚到视口顶部（块可能是占位，也可能已物化）。
 *
 *  为什么不用 `window.state.doc.blocks`：`state.doc` 是**已载入文档**（body/lines/version），
 *  不是 AST；AST 是 app.js 闭包里的 `_doc`，页面外拿不到。占位与真块都带
 *  `data--src-line` / `data--src-line-end`（来自 AST），且按文档序单调 ⇒ 在 DOM 上二分即可。
 */
const SCROLL_TO_LINE_JS = `(function(targetLine){
  var pane=document.getElementById('preview-pane');
  var pv=document.getElementById('preview');
  var cc=pv?pv.querySelector('.-preview-content'):null;
  if(!pane||!cc)return null;
  var kids=cc.children,n=kids.length;
  if(!n)return null;
  function lineOf(el,which){
    var v=parseInt(el.getAttribute(which),10);
    return isNaN(v)?null:v;
  }
  // 第一个「src-line-end >= targetLine」的块（块按行号单调递增）
  var lo=0,hi=n-1,found=n;
  while(lo<=hi){
    var mid=(lo+hi)>>1;
    var se=lineOf(kids[mid],'data--src-line-end');
    if(se===null)se=lineOf(kids[mid],'data--src-line');
    if(se!==null&&se>=targetLine){found=mid;hi=mid-1;}else{lo=mid+1;}
  }
  if(found>=n)found=n-1;
  var el=kids[found];
  if(!el)return null;
  // 直接设 scrollTop（不用 scrollIntoView）：后者可能触发平滑滚动/滚动锚定，
  // 在测量窗口里会把位置“动画”回去，制造假漂移（实测 30% 位置被拉回 0）。
  try{pane.style.scrollBehavior='auto';}catch(e){}
  var paneTop=pane.getBoundingClientRect().top;
  var elTop=el.getBoundingClientRect().top;
  var want=pane.scrollTop+(elTop-paneTop);
  pane.scrollTop=want;
  if(Math.abs(pane.scrollTop-want)>1){pane.scrollTop=want;}   // 极少数情况下首帧被 clamp，再设一次
  return {targetBlock:parseInt(el.getAttribute('data--block-index'),10),
    blockSrcLine:lineOf(el,'data--src-line'),blockSrcLineEnd:lineOf(el,'data--src-line-end'),
    scrollTop:Math.round(pane.scrollTop*10)/10,targetLine:targetLine};
})`;

async function scrollToLine(cdp, targetLine) {
  return await cdp.evalJS(SCROLL_TO_LINE_JS + '(' + targetLine + ')');
}

async function scrollToBlockIndex(cdp, idx, blockPos = 'center') {
  return await cdp.evalJS(`(function(i,pos){
    var pane=document.getElementById('preview-pane');
    var cc=document.getElementById('preview').querySelector('.-preview-content');
    var el=cc?cc.querySelector('[data--block-index="'+i+'"]'):null;
    if(!pane||!el)return null;
    el.scrollIntoView({block:pos});
    return {blockIndex:i,top:Math.round(el.getBoundingClientRect().top*10)/10,scrollTop:Math.round(pane.scrollTop*10)/10};
  })(${idx},${js(blockPos)})`);
}

async function scrollToScrollTop(cdp, top) {
  return await cdp.evalJS(`(function(t){var p=document.getElementById('preview-pane');if(!p)return null;p.scrollTop=t;return {scrollTop:p.scrollTop,scrollHeight:p.scrollHeight};})(${Number(top) || 0})`);
}

/** 空转 rAF 间隔（毫秒数组）。测量可信门：p50 ≤ 20ms 才允许采信后续性能读数。 */
async function rafIntervals(cdp, frames = 90) {
  return await cdp.evalJS(`new Promise(function(res){
    var ts=[],last=performance.now(),n=0;
    function tick(){var now=performance.now();ts.push(Math.round((now-last)*100)/100);last=now;n++;
      if(n>=${frames})res(ts);else requestAnimationFrame(tick);}
    requestAnimationFrame(tick);
  })`);
}

function median(arr) {
  if (!arr.length) return null;
  const s = arr.slice().sort((a, b) => a - b);
  const mid = s.length >> 1;
  return s.length % 2 ? s[mid] : Math.round((s[mid - 1] + s[mid]) / 2 * 100) / 100;
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. 单项检查
// ─────────────────────────────────────────────────────────────────────────────
function newRunCtx(spec, fixture, sabotage) {
  return {
    spec, fixture, sabotage,
    open: null,           // L1 结果（供 L3 比较“绝对位置”）
    positions: [],        // L2 结果（供报告）
    longScroll: null,
    firstScreen: null,
  };
}

async function checkIdleRaf(cdp, ctx, th) {
  const c = makeCheck('L0-idle-raf', '测量可信门：空转 rAF p50 ≤ 阈值（窗口被节流则拒跑）');
  const st = c.step('measure-idle-raf');
  const samples = await rafIntervals(cdp, th.frames || 90);
  const p50 = median(samples);
  const p95 = samples.slice().sort((a, b) => a - b)[Math.min(samples.length - 1, Math.floor(0.95 * samples.length))] || null;
  st.read('frames', samples.length);
  st.read('p50Ms', p50);
  st.read('p95Ms', p95);
  st.read('maxMs', samples.length ? Math.max(...samples) : null);
  st.assert('idle-raf-p50', p50 != null && p50 <= th.p50MaxMs, `≤ ${th.p50MaxMs} ms`, p50, 'p50 > 阈值通常意味着窗口被最小化/后台节流，性能读数不可信');
  ctx.rAF = { p50Ms: p50, p95Ms: p95, frames: samples.length };
  return c.rec;
}

async function checkOpen(cdp, ctx, th) {
  const c = makeCheck('L1-open-first-screen', '打开 ≥1000 块文档：首块可见 ≤预算，且确实走惰性路径');
  const st = c.step('open-timed');
  // 确保当前视图是预览（否则打开后 #preview 为空，测到的是源码视图）
  await cdp.evalJS(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]');if(!b)return false;if((window.state||{}).viewMode!=='preview')b.click();return true;})()`);
  await cdp.waitFor('(window.state||{}).viewMode === "preview"', { timeout: 15000, label: 'viewMode-preview' });
  // 惰性钩子必须在 open 之前设置（它是阈值覆盖，见 app.js `_lazyMaterializeEnabled`）
  await cdp.evalJS(`(function(){window.__MEMORIA_LAZY=true;try{localStorage.setItem('memoria.perf.lazy','1')}catch(e){}return window.__MEMORIA_LAZY;})()`);
  // W3.3：批尾布局模式必须在**首次物化/淘汰之前**选定（否则 open 阶段的淘汰会用默认模式）。
  // 这里只调用产品自己的运行时开关（`__MEMORIA_TAIL_LAYOUT.setMode`），不写死任何实现细节。
  if (ctx.tailMode) {
    const applied = await cdp.evalJS(`(function(m){
      try { return window.__MEMORIA_TAIL_LAYOUT ? window.__MEMORIA_TAIL_LAYOUT.setMode(m) : null; }
      catch(e){ return 'ERR:'+e.message; }
    })(${js(ctx.tailMode)})`);
    st.read('tailMode', applied);
    st.assert('tail-mode-applied', applied === ctx.tailMode, ctx.tailMode, applied, 'AB 实验要求逐轮显式指定批尾模式');
  }
  ctx.tailModeSeen = await cdp.evalJS(`(window.__MEMORIA_TAIL_LAYOUT?window.__MEMORIA_TAIL_LAYOUT.getMode():null)`, false);
  const file = ctx.spec.fixture.file;
  const r = await cdp.evalJS(`(async function(file){
    var t0=performance.now();
    await window.MemoriaApp.openFile(file,{});
    var tFirst=null,tScreen=null,start=performance.now();
    await new Promise(function(res){
      function tick(){
        var p=document.getElementById('preview-pane');
        var pr=p?p.getBoundingClientRect():{top:0,bottom:window.innerHeight};
        var els=document.querySelectorAll('#preview .-src-block:not(.-pv-placeholder)');
        var vis=0,len=0;
        for(var i=0;i<els.length;i++){var b=els[i].getBoundingClientRect();if(b.height>0&&b.bottom>pr.top&&b.top<pr.bottom){vis++;len+=(els[i].textContent||'').replace(/\\s+/g,' ').trim().length;}}
        if(vis>0&&tFirst===null)tFirst=performance.now()-t0;
        if(vis>=3&&len>=60&&tScreen===null){tScreen=performance.now()-t0;return res();}
        if(performance.now()-start>15000)return res();
        requestAnimationFrame(tick);
      }
      tick();
    });
    var ws=window.__MEMORIA_WORKSET_STATS?window.__MEMORIA_WORKSET_STATS():null;
    return {firstVisibleMs:tFirst,screenReadyMs:tScreen,wallMs:performance.now()-t0,stats:ws,
      renderedBlocks:document.querySelectorAll('#preview .-src-block').length,
      currentPath:(window.state||{}).currentPath||null,
      hook:(typeof window.__MEMORIA_LAZY==='boolean')?window.__MEMORIA_LAZY:null};
  })(${js(file)})`);
  st.read('open', r);
  const first = r && r.firstVisibleMs;
  st.assert('first-block-visible', first != null && first <= th.firstVisibleMaxMs, `≤ ${th.firstVisibleMaxMs} ms`, first, '首个已物化块进入视口的时间');
  st.assert('opened-file', r && r.currentPath === file, file, r ? r.currentPath : null);
  st.assert('lazy-hook-on', r && r.hook === true, true, r ? r.hook : null);
  const ws = (r && r.stats) || {};
  st.read('workset', ws);
  st.assert('blocks>=1000', (ws.totalBlocks || 0) >= 1000, '≥1000', ws.totalBlocks || 0, 'fixture 规模必须足以触发惰性路径');
  st.assert('lazy-path-placeholders', (ws.placeholders || 0) > 0, '>0', ws.placeholders || 0, '占位>0 = 没有一次性全量物化');
  st.assert('not-full-render', (ws.materialized || 0) < (ws.totalBlocks || 0), '< totalBlocks', `${ws.materialized || 0}/${ws.totalBlocks || 0}`);
  st.assert('metrics-measured', ws.metricsSrc === 'probe' || ws.metricsSrc === 'computed', 'probe|computed', ws.metricsSrc, '占位度量必须来自实测（detached 度量 bug 会给出 24px）');
  const lh = ws.lhPx;
  st.assert('line-height-sane', lh > 15 && lh < 40, '15..40 px', lh);
  ctx.open = {
    firstVisibleMs: first, screenReadyMs: r && r.screenReadyMs, wallMs: r && r.wallMs,
    stats: ws, file, blocksPerScreen: null,
  };
  // 首屏快照（L4 DOM 参考 + 报告）
  const m = await measure(cdp);
  ctx.firstScreen = m;
  ctx.open.blocksPerScreen = lh ? Math.ceil((m.clientHeight || 720) / lh) : null;
  st.read('blocksPerScreen', ctx.open.blocksPerScreen);
  // 打开后的收尾动作（默认文档恢复/预览池预渲染/首次排版）可能异步改滚动位置。
  // L2 的第一个位置若撞上它，会被“拉回顶部”误判成漂移 ⇒ 这里等它落定，并重取基准。
  await sleep(th.postOpenSettleMs || 1500);
  ctx.firstScreen = await measure(cdp);
  st.read('postOpenSettle', { scrollTop: ctx.firstScreen.scrollTop, topLine: ctx.firstScreen.topLine, vpPlaceholders: ctx.firstScreen.vpPlaceholders });
  return c.rec;
}

/** 负向验证注入：把视口内某已物化块换回占位（模拟“该位置占位残留”）。 */
async function sabotageViewportPlaceholder(cdp) {
  return await cdp.evalJS(`(function(){
    var pane=document.getElementById('preview-pane');
    var cc=document.getElementById('preview').querySelector('.-preview-content');
    if(!pane||!cc)return {ok:false,reason:'no-pane'};
    var pr=pane.getBoundingClientRect();
    var kids=cc.children;
    var vis=[];
    for(var i=0;i<kids.length;i++){
      var el=kids[i],r=el.getBoundingClientRect();
      if(r.bottom<=pr.top||r.top>=pr.bottom)continue;
      if(el.classList.contains('-pv-placeholder'))continue;
      if(r.height<10)continue;
      vis.push(el);
    }
    if(!vis.length)return {ok:false,reason:'no-visible-materialized'};
    // 不拿第一个可见块：它是漂移锚点，换掉会污染其它断言。取第二个（没有就取第一个）。
    var victim=vis.length>1?vis[1]:vis[0];
    var donor=null;
    for(var j=0;j<kids.length;j++){
      var e2=kids[j];
      if(!e2.classList.contains('-pv-placeholder'))continue;
      var r2=e2.getBoundingClientRect();
      if(r2.bottom<=pr.top||r2.top>=pr.bottom){donor=e2;break;}
    }
    if(!donor)return {ok:false,reason:'no-offscreen-placeholder'};
    var ph=donor.cloneNode(true);
    // 关键：块下标设成**非数字** ⇒ 产品的补物化路径（IO / scroll-stop sync / 调度器）都会
    // parseInt 失败并跳过它 ⇒ 占位残留是**持续缺陷**，不会被 1.5s 后的同步物化自愈。
    // （不能设 -1 或超大数：sync materialize 会把它们并进区间，触发大范围物化。）
    ph.setAttribute('data--block-index','sabotage');
    if(victim.getAttribute('data--src-line'))ph.setAttribute('data--src-line',victim.getAttribute('data--src-line'));
    if(victim.getAttribute('data--src-line-end'))ph.setAttribute('data--src-line-end',victim.getAttribute('data--src-line-end'));
    ph.setAttribute('data--pv-sabotage','1');
    ph.style.height=Math.max(24,Math.round(victim.getBoundingClientRect().height))+'px';
    var victimIdx=victim.getAttribute('data--block-index');
    victim.replaceWith(ph);
    return {ok:true,replacedBlockIndex:parseInt(victimIdx,10),sabotageIndex:'sabotage',kind:'viewport-placeholder'};
  })()`);
}

/**
 * 「文本正确」的判据：**逐块比对源文件**。
 * 每个视口块的 `data--src-line..src-line-end` 给出它来自 fixture 的哪几行；
 * 该块渲染出的文本里，至少要有 N 个 token 能在对应的源行里找到 ⇒ 证明“这个位置显示的是这块内容”，
 * 而不是残留/串位的幽灵块。比“视口里必须有 MARK”更稳：大表格/大代码块可以占满一屏，
 * 两个 marker 之间本来就可能没有任何 marker。
 *
 * 同时做**串位检测**：可见的 `LAZYGATE-MARK-xxxx` / `TOKEN-xxxx-A` 所属章节行若离视口 > 250 行，
 * 视为串位/残留（90% 位置的旧读数正是这样暴露的）。
 */
function featuresOf(s) {
  // 表格/代码块的 textContent 会把相邻单元格拼成 "81keepScreens4" ⇒ 先按 camelCase / 字母数字边界拆开。
  const norm = String(s || '')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/([A-Za-z])(\d)/g, '$1 $2')
    .replace(/(\d)([A-Za-z])/g, '$1 $2')
    .toLowerCase();
  const out = new Set();
  for (const t of (norm.match(/[a-z0-9_][a-z0-9_-]{2,}/g) || [])) out.add('t:' + t);
  // 中文没有空格 ⇒ 用 2-gram；mermaid 标签/正文/列表都能对上，且能发现“错误信息文本”。
  for (const run of norm.replace(/[^\u4e00-\u9fff]+/g, ' ').split(/\s+/)) {
    for (let i = 0; i + 2 <= run.length; i++) out.add('c:' + run.slice(i, i + 2));
  }
  return out;
}

function sourceTextCheck(ctx, m) {
  const blocks = (m.vpBlocks || []).filter((b) => !b.ph && b.line != null && b.line > 0 && (b.len || 0) > 0).slice(0, 16);
  const details = [];
  for (const b of blocks) {
    const line = b.line;
    let end = b.end != null && b.end >= line ? b.end : line;
    if (end - line > 200) end = line;
    const srcFeat = featuresOf((ctx.fixture.lines || []).slice(line - 1, end).join('\n'));
    const renFeat = featuresOf(b.text || '');
    let matched = 0;
    const hits = [];
    for (const t of renFeat) { if (srcFeat.has(t)) { matched++; if (hits.length < 6) hits.push(t); } }
    details.push({ idx: b.idx, line, end, len: b.len, kind: b.kind || null, matched, hits, head: (b.text || '').slice(0, 40) });
  }
  // 聚合口径：视口内**全部可见文本** vs 视口覆盖的**源行区间**。
  const lo = m.topLine != null ? m.topLine : 1;
  const hi = m.bottomLine != null && m.bottomLine >= lo ? m.bottomLine : lo;
  const srcFeat = featuresOf((ctx.fixture.lines || []).slice(lo - 1, hi).join('\n'));
  const renText = (m.vpBlocks || []).map((b) => b.text || '').join(' ');
  const renFeat = featuresOf(renText);
  let matchedAgg = 0;
  const aggHits = [];
  for (const t of renFeat) { if (srcFeat.has(t)) { matchedAgg++; if (aggHits.length < 12) aggHits.push(t); } }
  const ratio = renFeat.size ? Math.round((matchedAgg / renFeat.size) * 1000) / 1000 : 0;
  // 串位检测
  const midLine = m.topLine != null && m.bottomLine != null ? (m.topLine + m.bottomLine) / 2 : (m.topLine || 0);
  const stale = [];
  for (const mm of renText.matchAll(/(LAZYGATE-MARK-(\d{4})|TOKEN-(\d{4})-A)/g)) {
    const sec = mm[2] || mm[3];
    const mk = ctx.fixture.markers.find((x) => x.id === 'LAZYGATE-MARK-' + sec);
    if (!mk) { stale.push({ token: mm[1], reason: 'no-source-line' }); continue; }
    if (Math.abs(mk.line - midLine) > 250) stale.push({ token: mm[1], sourceLine: mk.line, viewportMidLine: Math.round(midLine) });
  }
  return {
    blocksChecked: blocks.length,
    sourceSpan: { from: lo, to: hi },
    renderedFeatures: renFeat.size, matchedFeatures: matchedAgg, ratio, hits: aggHits,
    ok: matchedAgg >= 8,
    stale, details,
  };
}

async function checkPositions(cdp, ctx, th) {
  const c = makeCheck('L2-positions', '拖到 30/50/70/90%：视口占位=0、文本命中、相对位置漂移 ≤ 阈值');
  const totalLines = ctx.fixture.totalLines;
  const markerLines = new Map(ctx.fixture.markers.map((m) => [m.id, m.line]));
  for (const frac of th.fractions) {
    const targetLine = Math.max(1, Math.round(totalLines * frac));
    const st = c.step(`position-${Math.round(frac * 100)}pct`);
    const target = await scrollToLine(cdp, targetLine);
    if (!target) { st.assert('scroll-target-found', false, 'block for line ' + targetLine, null); continue; }
    // 第一次跳转可能改变高度（占位→物化/远处淘汰）⇒ 布局落定后再对齐一次，
    // 否则量到的是“跳转误差”，不是“停稳后的漂移”。
    await waitViewportSettled(cdp);
    const target2 = await scrollToLine(cdp, targetLine);
    const settled = await waitViewportSettled(cdp);
    const a = settled.last;
    // 负向验证：在**第一个位置**注入“视口占位残留”，看门禁是否报错（只注入一次，保证 FAIL 可定位）
    let sabotage = null;
    if (ctx.sabotage === 'viewport-placeholder' && !ctx.sabotageDone) {
      sabotage = await sabotageViewportPlaceholder(cdp);
      ctx.sabotageDone = true;
    }
    await sleep(th.driftSettleMs);          // 让淘汰/异步排版跑完（漂移正是在这里暴露）
    const b = await measure(cdp);
    const lh = (b.workset && b.workset.lhPx) || 22.4;
    let driftLines = null, driftPx = null;
    if (a && b && a.topBlockIndex != null) {
      const anchorTopNow = await cdp.evalJS(`(function(i){var el=document.querySelector('#preview .-preview-content [data--block-index="'+i+'"]');if(!el)return null;return Math.round(el.getBoundingClientRect().top*10)/10;})(${a.topBlockIndex})`);
      if (anchorTopNow != null) { driftPx = Math.abs(anchorTopNow - a.topBlockTop); driftLines = Math.round((driftPx / lh) * 10) / 10; }
    }
    const markerChecks = (b.vpMarkers || []).map((id) => ({ id, line: markerLines.get(id) || null }));
    const near = markerChecks.filter((x) => x.line != null && b.topLine != null && b.bottomLine != null && x.line >= b.topLine - 60 && x.line <= b.bottomLine + 60);
    const srcCheck = sourceTextCheck(ctx, b);
    st.read('fraction', frac);
    st.read('target', target);
    st.read('settledMs', settled.ms);
    st.read('before', a && { vpPlaceholders: a.vpPlaceholders, vpRealBlocks: a.vpRealBlocks, topLine: a.topLine, topBlockIndex: a.topBlockIndex, topBlockTop: a.topBlockTop, ratio: a.ratio });
    st.read('after', b && { vpPlaceholders: b.vpPlaceholders, vpRealBlocks: b.vpRealBlocks, topLine: b.topLine, bottomLine: b.bottomLine, topBlockIndex: b.topBlockIndex, topBlockTop: b.topBlockTop, ratio: b.ratio, vpTextLen: b.vpTextLen });
    st.read('drift', { driftPx, driftLines, lineDelta: a && b ? Math.abs((b.topLine || 0) - (a.topLine || 0)) : null });
    st.read('markersVisible', markerChecks);
    st.read('markerNear', near);
    st.read('sourceTextCheck', srcCheck);
    st.read('vpBlocks', (b.vpBlocks || []).map((x) => ({ idx: x.idx, line: x.line, end: x.end, len: x.len, kind: x.kind, head: (x.text || '').slice(0, 100) })));
    st.read('sourceExcerpt', (ctx.fixture.lines || []).slice(Math.max(0, (b.topLine || 1) - 2), (b.bottomLine || b.topLine || 1)).join('\n').slice(0, 1200));
    st.read('sabotage', sabotage);
    st.assert('settled-viewport-placeholders-0', settled.settled && b.vpPlaceholders === 0, 0, b ? b.vpPlaceholders : null, '滚动停稳后视口里不得有未物化的空白占位');
    st.assert('viewport-has-text', hasVisibleContent(b), 'real>=3 && (text>=40 || media>0)', b ? `${b.vpRealBlocks}/${b.vpTextLen}/media=${b.vpMedia}` : null);
    st.assert('scroll-ratio-near-target', b.ratio != null && Math.abs(b.ratio - frac) <= th.ratioTolerance, `${frac}±${th.ratioTolerance}`, b.ratio, '按源行数定位后的实际滚动比例');
    st.assert('align-target-line', b.topLine != null && target.blockSrcLine != null && Math.abs(b.topLine - target.blockSrcLine) <= th.alignToleranceLines, `≤${th.alignToleranceLines} lines (target block srcLine ${target.blockSrcLine})`, b.topLine != null && target.blockSrcLine != null ? Math.abs(b.topLine - target.blockSrcLine) : null);
    st.assert('text-matches-source', srcCheck.ok, 'viewport text shares ≥8 features with its own source lines', `${srcCheck.matchedFeatures}/${srcCheck.renderedFeatures} ratio=${srcCheck.ratio} (${srcCheck.sourceSpan.from}..${srcCheck.sourceSpan.to})`, '聚合比对：视口文本必须来自该位置覆盖的源行区间（防幽灵/串位）');
    st.assert('no-stale-content', srcCheck.stale.length === 0, 0, srcCheck.stale.length, '远离视口的 MARK/TOKEN 说明串位或残留: ' + srcCheck.stale.map((x) => x.token + '@' + x.sourceLine).join(','));
    st.assert('relative-drift-lines', driftLines != null && driftLines <= th.driftLinesMax, `≤${th.driftLinesMax} lines`, driftLines, '同一锚点块在 settle 前后的屏幕位置差');
    st.assert('top-line-delta', a && b ? Math.abs((b.topLine || 0) - (a.topLine || 0)) <= th.driftLinesMax : false, `≤${th.driftLinesMax} lines`, a && b ? Math.abs((b.topLine || 0) - (a.topLine || 0)) : null);
    ctx.positions.push({ frac, targetLine, driftLines, vpPlaceholders: b && b.vpPlaceholders, topLine: b && b.topLine, ratio: b && b.ratio });
    // 注：负向注入后不等待重建（真实缺陷就是“停稳后仍有占位”，门禁必须当场抓到）
  }
  return c.rec;
}

async function checkBackToTop(cdp, ctx, th) {
  const c = makeCheck('L3-back-to-top', '滚回顶部：绝对位置 Δ≤阈值、视口占位=0、无白屏');
  const st = c.step('scroll-to-top');
  const before = ctx.open && ctx.open.stats ? ctx.open : null;
  const initial = ctx.firstScreen;
  await scrollToScrollTop(cdp, 0);
  const settled = await waitViewportSettled(cdp);
  const m = settled.last;
  const lh = (m && m.workset && m.workset.lhPx) || 22.4;
  let absDeltaLines = null;
  if (initial && m && initial.firstBlockTop != null && m.firstBlockTop != null) {
    absDeltaLines = Math.round((Math.abs(m.firstBlockTop - initial.firstBlockTop) / lh) * 10) / 10;
  }
  const lineDelta = initial && m && initial.topLine != null && m.topLine != null ? Math.abs(m.topLine - initial.topLine) : null;
  st.read('before', initial && { topLine: initial.topLine, firstBlockTop: initial.firstBlockTop, firstBlockIndex: initial.firstBlockIndex });
  st.read('after', m && { topLine: m.topLine, firstBlockTop: m.firstBlockTop, firstBlockIndex: m.firstBlockIndex, vpPlaceholders: m.vpPlaceholders, vpRealBlocks: m.vpRealBlocks, vpTextLen: m.vpTextLen, scrollTop: m.scrollTop, ratio: m.ratio });
  st.read('delta', { absDeltaLines, lineDelta });
  st.assert('scrolltop-zero', m.scrollTop === 0, 0, m ? m.scrollTop : null);
  st.assert('viewport-placeholders-0', m.vpPlaceholders === 0, 0, m ? m.vpPlaceholders : null);
  st.assert('absolute-position-delta', absDeltaLines != null && absDeltaLines <= th.driftLinesMax, `≤${th.driftLinesMax} lines`, absDeltaLines, '首块相对视口顶的偏移回到打开时位置');
  st.assert('absolute-line-delta', lineDelta != null && lineDelta <= th.driftLinesMax, `≤${th.driftLinesMax} lines`, lineDelta);
  st.assert('no-blank-screen', hasVisibleContent(m), 'real>=3 && (text>=40 || media>0)', m ? `${m.vpRealBlocks}/${m.vpTextLen}/media=${m.vpMedia}` : null);
  return c.rec;
}

async function checkLongScroll(cdp, ctx, th) {
  const c = makeCheck('L4-long-scroll', '长滚动一遍：物化块 ≤ 视口×8、evictTotal>0、堆不单调增长');
  const st = c.step('scroll-entire-document');
  // 负向验证：产品自带“门禁强制全量物化”接口会停掉淘汰（等价于把 KEEP_SCREENS 调到极大）
  let sabotage = null;
  if (ctx.sabotage === 'noevict') {
    sabotage = await cdp.evalJS(`(async function(){
      if(typeof window.__MEMORIA_MATERIALIZE_ALL!=='function')return {ok:false,reason:'no-api'};
      var made=await window.__MEMORIA_MATERIALIZE_ALL();
      var ws=window.__MEMORIA_WORKSET_STATS?window.__MEMORIA_WORKSET_STATS():null;
      return {ok:true,kind:'noevict',made:made,stats:ws};
    })()`);
  }
  // 从顶部开始，gc 一次拿基线
  await scrollToScrollTop(cdp, 0);
  await waitViewportSettled(cdp);
  const gc = async () => { try { return await cdp.evalJS('(function(){if(typeof window.gc==="function"){window.gc();return true;}return false;})()'); } catch { return false; } };
  await gc();
  await sleep(300);
  const base = await measure(cdp);
  const baseHeap = base.heapMB;
  const baseEvict = base.workset ? base.workset.evictTotal : 0;
  const maxScroll = base.scrollHeight - base.clientHeight;
  const steps = th.longScrollSteps || 32;
  const samples = [];
  let maxMaterialized = 0, maxDomPreview = 0, maxVpPh = 0;
  for (let i = 0; i <= steps; i++) {
    const top = Math.round((maxScroll * i) / steps);
    await scrollToScrollTop(cdp, top);
    await sleep(th.longScrollStepMs || 130);
    const m = await measure(cdp);
    samples.push({ i, scrollTop: m.scrollTop, materialized: m.workset ? m.workset.materialized : null, placeholders: m.workset ? m.workset.placeholders : null, evictTotal: m.workset ? m.workset.evictTotal : null, heapMB: m.heapMB, domPreview: m.domPreview, vpPlaceholders: m.vpPlaceholders });
    maxMaterialized = Math.max(maxMaterialized, (m.workset && m.workset.materialized) || 0);
    maxDomPreview = Math.max(maxDomPreview, m.domPreview || 0);
    maxVpPh = Math.max(maxVpPh, m.vpPlaceholders || 0);
  }
  await sleep(1200);
  await gc();
  await sleep(300);
  const fin = await measure(cdp);
  const ws = fin.workset || {};
  const blocksPerScreen = ctx.open.blocksPerScreen || Math.ceil((fin.clientHeight || 720) / ((ws.lhPx || 22.4)));
  const domLimit = th.domScreensMax * blocksPerScreen;
  const heapVals = samples.map((s) => s.heapMB).filter((v) => v != null);
  const peakHeap = heapVals.length ? Math.max(...heapVals) : null;
  const peakDelta = peakHeap != null && baseHeap != null ? Math.round((peakHeap - baseHeap) * 100) / 100 : null;
  const retainedDelta = fin.heapMB != null && baseHeap != null ? Math.round((fin.heapMB - baseHeap) * 100) / 100 : null;
  const deltas = heapVals.slice(1).map((v, i) => Math.round((v - heapVals[i]) * 100) / 100);
  const strictlyIncreasing = deltas.length > 3 && deltas.every((d) => d > -0.01);
  const evictTotal = ws.evictTotal || 0;
  const evictDelta = evictTotal - baseEvict;
  st.read('blocksPerScreen', blocksPerScreen);
  st.read('domLimit', domLimit);
  st.read('baseHeapMB', baseHeap);
  st.read('finalHeapMB', fin.heapMB);
  st.read('peakHeapMB', peakHeap);
  st.read('peakDeltaMB', peakDelta);
  st.read('retainedDeltaMB', retainedDelta);
  st.read('strictlyIncreasing', strictlyIncreasing);
  st.read('evictTotal', evictTotal);
  st.read('evictDeltaDuringLongScroll', evictDelta);
  st.read('baseEvictTotal', baseEvict);
  st.read('maxMaterialized', maxMaterialized);
  st.read('maxDomPreview', maxDomPreview);
  st.read('maxViewportPlaceholdersDuringScroll', maxVpPh);
  st.read('sabotage', sabotage);
  st.read('samples', samples);
  st.assert('eviction-ran', evictTotal > 0, '>0', evictTotal, '__MEMORIA_WORKSET_STATS().evictTotal 必须增长，否则工作集淘汰没生效');
  st.assert('eviction-ran-during-long-scroll', evictDelta > 0, `>${baseEvict}`, evictTotal, '长滚动期间必须新增淘汰（不能只靠此前的淘汰计数）');
  st.assert('eviction-not-suspended', ws.suspended !== true, false, ws.suspended === true);
  st.assert('dom-within-8-screens', maxMaterialized <= domLimit, `≤${domLimit} blocks (8 × ${blocksPerScreen}/screen)`, maxMaterialized, '#preview 内同时存在的块数（含占位）不得超过视口×8');
  st.assert('viewport-settles-at-bottom', fin.vpPlaceholders === 0 && hasVisibleContent(fin), '0 placeholders && real>=3 && (text>=40 || media>0)', fin ? `${fin.vpPlaceholders}/${fin.vpRealBlocks}/${fin.vpTextLen}/${fin.vpMedia}` : null);
  st.assert('heap-not-strictly-monotonic', !strictlyIncreasing || (peakDelta != null && peakDelta <= th.heapPeakDeltaMbWhenMonotonic), `not strictly increasing (or peakΔ≤${th.heapPeakDeltaMbWhenMonotonic}MB)`, strictlyIncreasing, '要求采样轨迹出现回落（GC），或涨幅足够小');
  st.assert('heap-peak-delta', peakDelta == null || peakDelta <= th.heapPeakDeltaMb, `≤${th.heapPeakDeltaMb} MB`, peakDelta);
  st.assert('heap-retained-delta', retainedDelta == null || retainedDelta <= th.heapRetainedDeltaMb, `≤${th.heapRetainedDeltaMb} MB`, retainedDelta, 'GC 后的驻留增量（真正的泄漏会远超）');
  ctx.longScroll = { evictTotal, evictDelta, maxMaterialized, domLimit, peakDelta, retainedDelta, blocksPerScreen, final: fin };
  return c.rec;
}

/** 当前光标/选区（块身份用 `data--block-index`；注意 `interaction.mjs` 的 selection() 读的是
 *  `dataset.blockIndex`，而应用实际写的是 `data--block-index`（双横线）⇒ 那里恒为 null，本门禁另读。 */
const CARET_JS = `(function(){
  var s=window.getSelection();
  if(!s||!s.rangeCount)return null;
  var r=s.getRangeAt(0);
  function info(node,off){
    var el=node?(node.nodeType===1?node:node.parentElement):null;
    var blk=el&&el.closest?el.closest('[data--block-index]'):null;
    return {offset:off,blockIndex:blk?parseInt(blk.getAttribute('data--block-index'),10):null,
      textLen:(node&&node.nodeType===3)?node.nodeValue.length:null,
      sample:(node&&node.nodeType===3)?node.nodeValue.slice(0,48):''};
  }
  return {collapsed:s.isCollapsed,text:s.toString(),anchor:info(r.startContainer,r.startOffset),focus:info(r.endContainer,r.endOffset)};
})()`;

async function caretInfo(cdp) {
  return await cdp.evalJS(CARET_JS);
}

async function checkEditProtect(cdp, ctx, th) {
  const c = makeCheck('L5-edit-protect', '在已物化块上编辑 → 远处淘汰 → 编辑内容与光标位置不受影响');
  const st = c.step('edit-then-evict-elsewhere');
  // 50% 位置，进入编辑态
  const totalLines = ctx.fixture.totalLines;
  await scrollToLine(cdp, Math.round(totalLines * 0.5));
  await waitViewportSettled(cdp);
  await cdp.evalJS(`(function(){var E=window.MemoriaEditHandler;if(E&&!E.editMode&&E.toggleEditMode)E.toggleEditMode();return !!(E&&E.editMode);})()`);
  await sleep(400);
  // 找一个视口内、有足够文本、无公式的块，并取一个可点字符位置
  const pick = await cdp.evalJS(`(function(){
    var pane=document.getElementById('preview-pane');
    var cc=document.getElementById('preview').querySelector('.-preview-content');
    if(!pane||!cc)return null;
    var pr=pane.getBoundingClientRect(),kids=cc.children;
    for(var i=0;i<kids.length;i++){
      var el=kids[i];if(el.classList.contains('-pv-placeholder'))continue;
      var r=el.getBoundingClientRect();if(r.bottom<=pr.top+4||r.top>=pr.bottom-4)continue;
      var t=(el.textContent||'').replace(/\\s+/g,' ').trim();
      if(t.length<60)continue;
      // 只挑正文块（p/li/h/blockquote）：代码块点进去会进块编辑器、表格/图/公式不可直接落光标。
      if(el.querySelector('pre,table,svg,mjx-container'))continue;
      if(el.closest('pre,table'))continue;
      var walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT,null),node=null,x;
      while((x=walker.nextNode())){if((x.nodeValue||'').trim().length>20){node=x;break;}}
      if(!node)continue;
      var rng=document.createRange();
      var off=Math.min(4,node.nodeValue.length-2);
      rng.setStart(node,off);rng.setEnd(node,Math.min(node.nodeValue.length,off+1));
      var rects=rng.getClientRects(),rr=rects.length?rects[0]:rng.getBoundingClientRect();
      if(!rr||(!rr.width&&!rr.height))continue;
      var hit=document.elementFromPoint(Math.round(rr.left+Math.max(1,rr.width/2)),Math.round(rr.top+rr.height/2));
      var hitBlk=hit&&hit.closest?hit.closest('[data--block-index]'):null;
      return {blockIndex:+el.getAttribute('data--block-index'),x:Math.round(rr.left+Math.max(1,rr.width/2)),y:Math.round(rr.top+rr.height/2),text:t.slice(0,80),
        paneTop:+pr.top.toFixed(1),blockTop:+r.top.toFixed(1),blockBottom:+r.bottom.toFixed(1),scrollTop:+pane.scrollTop.toFixed(1),
        hitTag:hit?hit.tagName:null,hitBlock:hitBlk?parseInt(hitBlk.getAttribute('data--block-index'),10):null,
        hitPh:!!(hitBlk&&hitBlk.classList.contains('-pv-placeholder'))};
    }
    return null;
  })()`);
  if (!pick) { st.assert('editable-block-found', false, 'a visible text block', null); return c.rec; }
  // 用受信任点击落光标 + 受信任键盘输入唯一标记
  const ix = ctx.ix;
  // 点击前后的落点诊断：pred 若在 pick 与 click 之间发生布局漂移，这里能直接看到命中块/占位。
  const clickProbe = (p) => cdp.evalJS(`(function(p){
    var pane=document.getElementById('preview-pane');
    var pv=document.getElementById('preview');
    var e=document.elementFromPoint(p.x,p.y);
    var el=e&&e.closest?e.closest('[data--block-index]'):null;
    var s=window.getSelection(),r=s&&s.rangeCount?s.getRangeAt(0):null;
    function bi(node){var n=node?(node.nodeType===1?node:node.parentElement):null;var b=n&&n.closest?n.closest('[data--block-index]'):null;return b?parseInt(b.getAttribute('data--block-index'),10):null;}
    var picked=document.querySelector('#preview .-preview-content [data--block-index="'+p.i+'"]');
    var a=document.activeElement;
    return {scrollTop:+pane.scrollTop.toFixed(1),hitTag:e?e.tagName:null,hitBlock:el?parseInt(el.getAttribute('data--block-index'),10):null,
      hitPh:!!(el&&el.classList.contains('-pv-placeholder')),
      activeTag:a?a.tagName:null,activeId:a?a.id||null:null,focusInPreview:!!(a&&pv&&pv.contains(a)),
      rangeCount:s?s.rangeCount:null,caretBlock:r?bi(r.startContainer):null,caretOffset:r?r.startOffset:null,
      pickedExists:!!picked,pickedPh:!!(picked&&picked.classList.contains('-pv-placeholder')),
      tail:(window.__MEMORIA_TAIL_LAYOUT?window.__MEMORIA_TAIL_LAYOUT.stats():null)};
  })(${JSON.stringify({ x: p.x, y: p.y, i: p.i })})`);
  st.read('pick', pick);
  st.read('clickBefore', await clickProbe({ x: pick.x, y: pick.y, i: pick.blockIndex }));
  await ix.click(pick.x, pick.y);
  st.read('clickAfter', await clickProbe({ x: pick.x, y: pick.y, i: pick.blockIndex }));
  await sleep(250);
  st.read('clickAfter250', await clickProbe({ x: pick.x, y: pick.y, i: pick.blockIndex }));
  await ix.typeText('ZGATE');
  await sleep(800);
  st.read('clickAfterType', await clickProbe({ x: pick.x, y: pick.y, i: pick.blockIndex }));
  const afterType = await cdp.evalJS(`(function(i){
    var el=document.querySelector('#preview .-preview-content [data--block-index="'+i+'"]');
    return {text:(el?el.textContent:'').replace(/\\s+/g,' ').trim(), has:(el?el.textContent:'').indexOf('ZGATE')>=0};
  })(${pick.blockIndex})`);
  const selBefore = await caretInfo(cdp);
  const beforeStats = await measure(cdp);
  const evictBefore = beforeStats.workset ? beforeStats.workset.evictTotal : 0;
  st.read('editedBlock', pick.blockIndex);
  st.read('afterType', afterType);
  st.read('selectionBefore', selBefore);
  st.read('evictTotalBefore', evictBefore);
  st.assert('edit-landed', afterType.has, true, afterType.has, '受信任键盘输入必须落到已物化块里');
  const anchorBlock = selBefore && selBefore.anchor ? selBefore.anchor.blockIndex : null;
  const anchorOffset = selBefore && selBefore.anchor ? selBefore.anchor.offset : null;
  st.assert('caret-in-edited-block', anchorBlock === pick.blockIndex, pick.blockIndex, anchorBlock);
  // 滚到 95% 触发远处淘汰；被编辑块必须被保护区保住
  await scrollToLine(cdp, Math.round(totalLines * 0.95));
  await sleep(2200);
  const during = await cdp.evalJS(`(function(i){
    var el=document.querySelector('#preview .-preview-content [data--block-index="'+i+'"]');
    var ws=window.__MEMORIA_WORKSET_STATS?window.__MEMORIA_WORKSET_STATS():null;
    return {exists:!!el,isPlaceholder:!!(el&&el.classList.contains('-pv-placeholder')),stats:ws,
      text:el?(el.textContent||'').replace(/\\s+/g,' ').trim().slice(0,200):null};
  })(${pick.blockIndex})`);
  st.read('whileFarAway', during);
  st.read('selectionFarAway', await caretInfo(cdp));
  st.assert('eviction-ran-elsewhere', during.stats && during.stats.evictTotal > evictBefore, `>${evictBefore}`, during.stats ? during.stats.evictTotal : null, '必须先证明远处真的发生了淘汰，否则“保护”无从谈起');
  st.assert('edited-block-not-evicted', during.exists && !during.isPlaceholder, 'materialized', during.exists ? (during.isPlaceholder ? 'placeholder' : 'materialized') : 'missing');
  // 滚回编辑块，校验内容与光标
  await scrollToBlockIndex(cdp, pick.blockIndex, 'center');
  await waitViewportSettled(cdp, { timeoutMs: 6000 });
  await sleep(400);
  const back = await cdp.evalJS(`(function(i){
    var el=document.querySelector('#preview .-preview-content [data--block-index="'+i+'"]');
    return {text:el?(el.textContent||'').replace(/\\s+/g,' ').trim():'',has:el?(el.textContent||'').indexOf('ZGATE')>=0:false,
      isPlaceholder:!!(el&&el.classList.contains('-pv-placeholder'))};
  })(${pick.blockIndex})`);
  const selAfter = await caretInfo(cdp);
  const anchorAfter = selAfter && selAfter.anchor ? selAfter.anchor : null;
  st.read('back', back);
  st.read('selectionAfter', selAfter);
  st.assert('edit-content-survives', back.has, true, back.has);
  st.assert('block-still-materialized', !back.isPlaceholder, false, back.isPlaceholder);
  st.assert('caret-block-preserved', anchorAfter && anchorAfter.blockIndex === anchorBlock, anchorBlock, anchorAfter ? anchorAfter.blockIndex : null);
  st.assert('caret-offset-preserved', anchorAfter && anchorAfter.offset === anchorOffset, anchorOffset, anchorAfter ? anchorAfter.offset : null);
  ctx.edit = { blockIndex: pick.blockIndex, anchorOffset, evictBefore, evictAfter: during.stats && during.stats.evictTotal, editSurvives: back.has, caretPreserved: !!(anchorAfter && anchorAfter.blockIndex === anchorBlock && anchorAfter.offset === anchorOffset) };
  return c.rec;
}

// ─────────────────────────────────────────────────────────────────────────────
// 3. main
// ─────────────────────────────────────────────────────────────────────────────
async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.scenarios || !args.out) throw new Error('用法：--scenarios <json> --out <json> --url <url> [--sabotage ...]');
  const spec = JSON.parse(fs.readFileSync(args.scenarios, 'utf8'));
  const fixturePath = path.resolve(spec.fixture.path);
  const fixture = loadFixture(fixturePath);
  const th = spec.thresholds || {};
  const sabotage = args.sabotage || null;
  if (sabotage && !['noevict', 'viewport-placeholder'].includes(sabotage)) {
    throw new Error('未知 --sabotage: ' + sabotage + '（支持 noevict | viewport-placeholder）');
  }
  const run = async (cdp, ix, edge) => {
    const ctx = newRunCtx(spec, fixture, sabotage);
    ctx.ix = ix;
    // W3.3：`--tail-mode legacy|pred|noSh` 让你在同一 fixture 上逐轮切换批尾模式（默认不干预）。
    ctx.tailMode = args['tail-mode'] || null;
    if (ctx.tailMode && !['legacy', 'pred', 'noSh'].includes(ctx.tailMode)) {
      throw new Error('未知 --tail-mode: ' + ctx.tailMode + '（支持 legacy | pred | noSh）');
    }
    const checks = [];
    const only = spec.checks || ['idleRaf', 'open', 'positions', 'backToTop', 'longScroll', 'editProtect'];
    const started = Date.now();
    const runOne = async (key, fn) => {
      if (!only.includes(key)) return;
      try { checks.push(await fn()); } catch (e) {
        const c = makeCheck(key, 'crashed');
        c.fail(e);
        checks.push(c.rec);
      }
    };
    await runOne('idleRaf', () => checkIdleRaf(cdp, ctx, th));
    // 测量可信门未过 ⇒ 后续性能读数不可采信；仍跑完（报告如实标红），但整体必 FAIL
    await runOne('open', () => checkOpen(cdp, ctx, th));
    await runOne('positions', () => checkPositions(cdp, ctx, th));
    await runOne('backToTop', () => checkBackToTop(cdp, ctx, th));
    await runOne('longScroll', () => checkLongScroll(cdp, ctx, th));
    await runOne('editProtect', () => checkEditProtect(cdp, ctx, th));
    const failed = checks.filter((c) => c.status !== 'PASS');
    return {
      schema: 'memoria-lazy-gate/v1',
      startedAt: new Date(started).toISOString(),
      finishedAt: new Date().toISOString(),
      durationMs: Date.now() - started,
      url: args.url || null,
      label: args.label || null,
      sabotage,
      tailMode: ctx.tailMode,
      tailModeSeen: ctx.tailModeSeen || null,
      browser: edge ? edge.browser : null,
      fixture: { path: path.relative(process.cwd(), fixturePath).replace(/\\/g, '/'), totalLines: fixture.totalLines, markers: fixture.markers.length, segments: spec.fixture.segments || null },
      thresholds: th,
      measurement: { raf: ctx.rAF || null, trusted: !!(ctx.rAF && ctx.rAF.p50Ms != null && ctx.rAF.p50Ms <= th.p50MaxMs) },
      open: ctx.open ? { firstVisibleMs: ctx.open.firstVisibleMs, screenReadyMs: ctx.open.screenReadyMs, wallMs: ctx.open.wallMs, stats: ctx.open.stats, blocksPerScreen: ctx.open.blocksPerScreen } : null,
      positions: ctx.positions,
      longScroll: ctx.longScroll ? { evictTotal: ctx.longScroll.evictTotal, evictDeltaDuringLongScroll: ctx.longScroll.evictDelta, maxMaterialized: ctx.longScroll.maxMaterialized, domLimit: ctx.longScroll.domLimit, peakDeltaMb: ctx.longScroll.peakDelta, retainedDeltaMb: ctx.longScroll.retainedDelta, blocksPerScreen: ctx.longScroll.blocksPerScreen } : null,
      edit: ctx.edit || null,
      checks,
      summary: { pass: failed.length === 0, checks: checks.length, failed: failed.length, failedIds: failed.map((c) => c.id) },
    };
  };
  const extraArgs = ['--js-flags=--expose-gc', '--enable-precise-memory-info'];
  const out = args['cdp-port']
    ? await (async () => { const { withLiveApp } = await import('./interaction.mjs'); return withLiveApp(parseInt(args['cdp-port'], 10), run); })()
    : await withBrowser(args.url, run, { extraArgs });
  fs.mkdirSync(path.dirname(path.resolve(args.out)), { recursive: true });
  fs.writeFileSync(path.resolve(args.out), JSON.stringify(out, null, 2), 'utf8');
  const line = `__LAZY_GATE_JSON__${JSON.stringify({ ok: out.summary.pass, out: path.resolve(args.out), checks: out.summary.checks, failed: out.summary.failed, failedIds: out.summary.failedIds })}`;
  process.stdout.write(line + '\n');
  process.exit(out.summary.pass ? 0 : 1);
}

main().catch((e) => { process.stderr.write(String((e && e.stack) || e) + '\n'); process.exit(1); });
