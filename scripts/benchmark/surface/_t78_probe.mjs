import fs from 'node:fs';
import { withBrowser, sleep } from './interaction.mjs';

const args = {};
for (let i = 2; i < process.argv.length; i += 2) args[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
if (!args.url || !args.file || !args.out) throw new Error('用法：node _t78_probe.mjs --url <url> --file <file> --mode pred|legacy --out <json>');

const mode = args.mode || 'pred';
const durationMs = Number(args.duration || 4000);
const frameStepPx = Number(args.stepPx || 900);
const jumpTo = args.jumpTo != null ? Number(args.jumpTo) : null;
const loadMs = Number(args.loadMs || 0);
const p2LoadMs = Number(args.p2LoadMs || 0);

async function run(cdp) {
  await cdp.evalJS(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]');if(b&&(window.state||{}).viewMode!=='preview')b.click();window.__MEMORIA_LAZY=true;try{localStorage.setItem('memoria.perf.lazy','1')}catch(e){}return true;})()`);
  await cdp.waitFor('(window.state||{}).viewMode === "preview"', { timeout: 15000, label: 'preview' });
  const applied = await cdp.evalJS(`(function(m){return window.__MEMORIA_TAIL_LAYOUT?window.__MEMORIA_TAIL_LAYOUT.setMode(m):null;})(${JSON.stringify(mode)})`);
  const open = await cdp.evalJS(`(async function(file){
    var t0=performance.now();
    for(var attempt=0;attempt<3;attempt++){
      await window.MemoriaApp.openFile(file,{});
      var ws=window.__MEMORIA_WORKSET_STATS?window.__MEMORIA_WORKSET_STATS():null;
      if(ws&&ws.totalBlocks>=3900)return {ok:true,attempts:attempt+1,ms:performance.now()-t0,stats:ws,path:(window.state||{}).currentPath};
      await new Promise(function(r){setTimeout(r,800);});
    }
    return {ok:false,stats:window.__MEMORIA_WORKSET_STATS?window.__MEMORIA_WORKSET_STATS():null,path:(window.state||{}).currentPath};
  })(${JSON.stringify(args.file)})`);
  await sleep(1500);
  await cdp.evalJS(`(function(){var p=document.getElementById('preview-pane');p.scrollTop=0;return true;})()`);
  await sleep(700);
  if (jumpTo != null) {
    // 瞬时大跳：制造 IO 洪峰 + pending 非空，检验淘汰作业是否会因“物化优先”而退出且不再续排。
    await cdp.evalJS(`(function(){var p=document.getElementById('preview-pane');var max=Math.max(0,p.scrollHeight-p.clientHeight);p.scrollTop=Math.min(max,${jumpTo});return {scrollTop:p.scrollTop,max:max};})()`);
    await sleep(30);
  }
  const drag = await cdp.evalJS(`new Promise(function(res){
    var pane=document.getElementById('preview-pane');
    var max=Math.max(0,pane.scrollHeight-pane.clientHeight);
    var loadTimer=null;
    if(${loadMs}>0){loadTimer=setInterval(function(){var t=performance.now();while(performance.now()-t<${loadMs}){}},16);}
    var p2Timer=null,p2N=0;
    if(${p2LoadMs}>0&&window.MemoriaScheduler){
      p2Timer=setInterval(function(){
        try{window.MemoriaScheduler.schedule({kind:'t78_p2_load',key:'t78-p2-'+p2N++,priority:2,replace:false,run:function(){var t=performance.now();while(performance.now()-t<${p2LoadMs}){}}})}catch(e){}
      },60);
    }
    var samples=[],t0=performance.now(),last=t0,lastEv=0;
    var ws0=window.__MEMORIA_WORKSET_STATS?window.__MEMORIA_WORKSET_STATS():{};
    var baseEv=ws0.evictTotal||0,maxMat=0,minEv=null,evFrames=0,frames=0;
    function tick(){
      var now=performance.now(),dt=now-last;last=now;frames++;
      pane.scrollTop=Math.min(max,pane.scrollTop+${frameStepPx});
      var ws=window.__MEMORIA_WORKSET_STATS?window.__MEMORIA_WORKSET_STATS():{};
      var ev=ws.evictTotal||0;
      if(ev>lastEv)evFrames++;
      lastEv=ev;
      maxMat=Math.max(maxMat,ws.materialized||0);
      if(frames%4===0||pane.scrollTop>=max)samples.push({t:Math.round(now-t0),st:Math.round(pane.scrollTop),mat:ws.materialized,ph:ws.placeholders,ev:ev,dt:Math.round(dt*10)/10});
      if(now-t0<${durationMs}&&pane.scrollTop<max)return requestAnimationFrame(tick);
      if(loadTimer)clearInterval(loadTimer);
      if(p2Timer)clearInterval(p2Timer);
      var total=now-t0;
      res({baseEv:baseEv,endEv:ev,evDelta:(ev-baseEv),evFrames:evFrames,frames:frames,totalMs:Math.round(total),
        fps:Math.round(frames*10000/total)/10,avgFrameMs:Math.round(total/frames*10)/10,maxMat:maxMat,
        endScrollTop:Math.round(pane.scrollTop),maxScroll:Math.round(max),samples:samples,
        mode:window.__MEMORIA_TAIL_LAYOUT?window.__MEMORIA_TAIL_LAYOUT.getMode():null});
    }
    requestAnimationFrame(tick);
  })`);
  await sleep(1500);
  const settled = await cdp.evalJS(`(function(){
    var ws=window.__MEMORIA_WORKSET_STATS?window.__MEMORIA_WORKSET_STATS():null;
    var pane=document.getElementById('preview-pane');
    var tl=window.__MEMORIA_TAIL_LAYOUT?window.__MEMORIA_TAIL_LAYOUT.stats():null;
    var sc=window.MemoriaScheduler&&window.MemoriaScheduler.counters?window.MemoriaScheduler.counters():null;
    return {stats:ws,tail:tl,sched:sc,scrollTop:Math.round(pane.scrollTop),scrollHeight:pane.scrollHeight};
  })()`);
  const dom = await cdp.evalJS(`(function(){return {previewNodes:document.getElementById('preview').querySelectorAll('*').length,blocks:document.querySelectorAll('#preview .-src-block').length};})()`);
  const heap = await cdp.evalJS(`(function(){try{if(window.gc)window.gc();}catch(e){}return performance.memory?Math.round(performance.memory.usedJSHeapSize/1048576*10)/10:null;})()`);
  return { applied, open, drag, settled, dom, heapMB: heap };
}

withBrowser(args.url, run, { extraArgs: ['--js-flags=--expose-gc', '--enable-precise-memory-info'] })
  .then((res) => {
    const out = { mode, result: res };
    fs.writeFileSync(args.out, JSON.stringify(out, null, 2));
    const d = res.drag;
    console.log(JSON.stringify({ mode, applied: res.applied, openOk: res.open.ok, blocks: res.open.stats && res.open.stats.totalBlocks,
      pressureScreens: res.open.stats && res.open.stats.pressureScreens,
      evDelta: d.evDelta, evFrames: d.evFrames, frames: d.frames, fps: d.fps, avgFrameMs: d.avgFrameMs,
      maxMat: d.maxMat, endEv: d.endEv, settledMat: res.settled.stats && res.settled.stats.materialized,
      settledEv: res.settled.stats && res.settled.stats.evictTotal, tail: res.settled.tail, heapMB: res.heapMB, dom: res.dom }, null, 2));
  })
  .catch((e) => { console.error(e && e.stack || e); process.exit(1); });
