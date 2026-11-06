/**
 * L0_1 æŠ˜å å®¹å™¨ â†’ è¿›å…¥å­å›¾ â†’ backgroundGhost å›žå½’ï¼ˆtask-391 rev12ï¼‰ã€‚
 *
 * çœŸå®žåº”ç”¨é¡µé¢ + çœŸå®ž Edgeï¼ŒCDP `Input` åŸŸå—ä¿¡ä»»æ‹–æ‹½ï¼š
 *   1) çˆ¶è§†å›¾æŠŠ container ç»„æŠ˜å æˆç°‡èŠ‚ç‚¹ï¼ˆ`group:demo:L0_1`ï¼‰ï¼Œæˆå‘˜ node-001 éšè—ï¼›
 *   2) çœŸå®žç‚¹å‡»ç°‡èŠ‚ç‚¹è¿›å…¥å­å›¾ï¼›
 *   3) æ–­è¨€ child view `getPositions()` åŒæ—¶æœ‰ node-001 ä¸Ž ghost:Aï¼ˆä¿®å¤å‰ ghost=nullï¼‰ï¼›
 *   4) æ‹– KP â†’ ghost ä½ç§»>0ï¼›æ‹– ghost â†’ KP ä½ç§»>0ï¼›å…¨ç¨‹å•ç”»å¸ƒã€‚
 *
 * ç”± `tests/graph/ui/test_l0_1_ghost_enter.py` èµ· harness åŽè°ƒç”¨ï¼š
 *   node l0_1_ghost_enter.test.mjs --url http://127.0.0.1:<port>/ --out <json>
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "../../..");
const { withBrowser, sleep } = await import(
  "file://" + path.join(REPO, "scripts/benchmark/surface/interaction.mjs").replace(/\\/g, "/")
);

function arg(name, fallback) {
  const i = process.argv.indexOf("--" + name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}
const URL = arg("url", "http://127.0.0.1:9500/");
const OUT = arg("out", path.join(HERE, "l0-1-ghost-realapp.json"));
const GROUP_ID = "demo:L0_1";
const GROUP_NODE = `group:${GROUP_ID}`;
const KP_ID = "node-001";

const SNAP = `(() => {
  const A = window.MemoriaApp;
  const g = A && A.state && A.state.graphMultilevel;
  const r = g && g.mounted && g.mounted.renderer;
  if (!r || typeof r.getPositions !== "function") return null;
  const cvs = document.querySelectorAll("#graph-2d-multilevel-root canvas");
  if (!cvs.length) return null;
  const rect = cvs[0].getBoundingClientRect();
  const cam = r._camera || { x: 0, y: 0, scale: 1 };
  const positions = {};
  for (const [id, p] of r.getPositions()) {
    const node = r.getNode ? r.getNode(id) : null;
    positions[id] = { x: p.x, y: p.y, radius: node ? node.radius : null, kind: node ? node.kind : null, layer: node ? node.layer : null };
  }
  return {
    canvasCount: cvs.length,
    rect: { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
    cam, positions,
  };
})()`;

function toScreen(snap, p) {
  const s = snap.cam.scale || 1;
  return { x: snap.rect.left + p.x * s + snap.cam.x, y: snap.rect.top + p.y * s + snap.cam.y };
}
function dist(a, b) { return Math.hypot(a.x - b.x, a.y - b.y); }

/** åœ¨ä¸¤ä¸ªåœ†å¯èƒ½é‡å æ—¶ï¼Œå–ç¦»å¦ä¸€èŠ‚ç‚¹æ›´è¿œçš„åœ†å‘¨ç‚¹ï¼Œä¿è¯ pointerdown å‘½ä¸­ç›®æ ‡èŠ‚ç‚¹ã€‚ */
function pickTarget(snap, targetId, otherId) {
  const t = snap.positions[targetId];
  const o = snap.positions[otherId];
  const center = toScreen(snap, t);
  if (!o) return center;
  const r = (t.radius || 6) * (snap.cam.scale || 1);
  const os = toScreen(snap, o);
  let dx = center.x - os.x;
  let dy = center.y - os.y;
  const len = Math.hypot(dx, dy);
  if (len < 1e-6) { dx = 1; dy = 0; }
  else { dx /= len; dy /= len; }
  return { x: center.x + dx * r * 0.55, y: center.y + dy * r * 0.55 };
}

async function stopAnim(cdp) {
  await cdp.evalJS(`(() => { const r = window.MemoriaApp.state.graphMultilevel.mounted.renderer; r._stopForceAnimation && r._stopForceAnimation(); return true; })()`);
}

const evidence = { kind: "task-391-l0-1-ghost-realapp", url: URL, steps: [], checks: {}, verdict: null };
try {
  await withBrowser(URL, async (cdp, ix) => {
    await cdp.waitFor("!!window.MemoriaApp", { timeout: 90000, label: "MemoriaApp" });
    await cdp.waitFor(`(() => { const s=window.MemoriaApp.state; return !!(s && s.kbPath); })()`, { timeout: 90000, label: "kbPath" }).catch(() => null);
    // ä¾§æ è‹¥è‡ªåŠ¨æŠ˜å ï¼šçœŸå®žç‚¹å‡»å±•å¼€ï¼ˆå¦åˆ™å›¾è°±å®¿ä¸»å®½ 0ï¼Œç”»å¸ƒä¸å¸ƒå±€ï¼‰
    const side = await cdp.evalJS(`(() => { const el=document.querySelector('#-sidebar'); const r=el?el.getBoundingClientRect():null; const btn=document.querySelector('#btn-toggle-sidebar'); const br=btn?btn.getBoundingClientRect():null; return { w:r?Math.round(r.width):null, toggle: br&&br.width>1?{x:br.left+br.width/2,y:br.top+br.height/2}:null }; })()`);
    if (side.w != null && side.w < 10 && side.toggle) { await ix.click(side.toggle.x, side.toggle.y); await sleep(500); }
    // åˆ‡æ¢åˆ° 2D å›¾è°±å¹¶åŠ è½½æ•°æ®ï¼ˆç­‰ä»·ç”¨æˆ·æ‰“å¼€å›¾è°±ï¼‰
    await cdp.evalJS(`(() => { document.querySelector('[data-sidebar-tab="graph2d"]').click(); return true; })()`);
    await sleep(400);
    const load = await cdp.evalJS(`(async () => { try { await window.MemoriaApp.loadGraphData(); return { ok: true }; } catch (e) { return { ok: false, reason: String((e && e.message) || e) }; } })()`);
    evidence.steps.push({ step: "load-graph-data", ...load });
    await cdp.waitFor(
      `(() => { const A=window.MemoriaApp; const g=A&&A.state&&A.state.graphMultilevel; const r=g&&g.mounted&&g.mounted.renderer; return !!(r && typeof r.getPositions === "function" && r.getPositions().size > 0); })()`,
      { timeout: 120000, label: "renderer ready" }
    );
    await sleep(900);
    await stopAnim(cdp);

    // çˆ¶è§†å›¾ï¼šcontainer ç»„åº”å·²æŠ˜å æˆç°‡èŠ‚ç‚¹ï¼Œæˆå‘˜ä¸åœ¨ sceneï¼ˆå¯ä»¥ç‚¹ç°‡è¿›å…¥å­å›¾ï¼‰
    let parent = await cdp.evalJS(SNAP);
    const parentHasCluster = !!(parent && parent.positions[GROUP_NODE]);
    const parentHasKp = !!(parent && parent.positions[KP_ID]);
    if (!parentHasCluster) {
      // å…œåº•ï¼ˆæ­£å¸¸ container ç»„ä¼šè‡ªåŠ¨æŠ˜å ï¼‰ï¼šæ˜¾å¼æŠ˜å ï¼Œä»èµ°çœŸå®ž pointerdown è¿›å…¥
      await cdp.evalJS(`(() => { const r=window.MemoriaApp.state.graphMultilevel.mounted.renderer; if (!r.isGroupCollapsed || !r.isGroupCollapsed(${JSON.stringify(GROUP_ID)})) r.toggleGroup(${JSON.stringify(GROUP_ID)}); return true; })()`);
      await sleep(500);
      await stopAnim(cdp);
      parent = await cdp.evalJS(SNAP);
    }
    evidence.steps.push({
      step: "parent-view",
      hasGroupCluster: !!(parent && parent.positions[GROUP_NODE]),
      hasMemberKp: !!(parent && parent.positions[KP_ID]),
      sceneIds: parent ? Object.keys(parent.positions) : [],
      canvasCount: parent ? parent.canvasCount : null,
      groupNode: parent && parent.positions[GROUP_NODE] ? parent.positions[GROUP_NODE] : null,
    });
    if (!parent.positions[GROUP_NODE]) throw new Error("çˆ¶è§†å›¾ç¼ºæŠ˜å ç°‡èŠ‚ç‚¹ " + GROUP_NODE);

    // çœŸå®žç‚¹å‡»ç°‡ â†’ app å†… groupClick â†’ enterMultilevelGroupï¼ˆ160ms åŽåˆ‡å­å›¾ï¼‰
    const clusterPoint = toScreen(parent, parent.positions[GROUP_NODE]);
    await ix.click(clusterPoint.x, clusterPoint.y);
    await cdp.waitFor(
      `(() => { const r=window.MemoriaApp.state.graphMultilevel.mounted.renderer; if(!r||!r.getPositions) return false; const p=r.getPositions(); return p.has("ghost:A") && p.has(${JSON.stringify(KP_ID)}); })()`,
      { timeout: 20000, label: "child view node-001 + ghost:A" }
    ).catch(() => null);
    await sleep(900);
    await stopAnim(cdp);
    let child = await cdp.evalJS(SNAP);
    const childHasKp = !!(child && child.positions[KP_ID]);
    const childHasGhost = !!(child && child.positions["ghost:A"]);
    evidence.steps.push({
      step: "child-view-after-enter",
      childHasKp, childHasGhost,
      sceneIds: child ? Object.keys(child.positions) : [],
      ghost: child && child.positions["ghost:A"] ? child.positions["ghost:A"] : null,
      kp: child && child.positions[KP_ID] ? child.positions[KP_ID] : null,
      canvasCount: child ? child.canvasCount : null,
      parentGroupNode: parent.positions[GROUP_NODE],
    });
    if (!childHasKp || !childHasGhost) throw new Error("è¿›å…¥å­å›¾åŽæœªåŒæ—¶å­˜åœ¨ node-001 ä¸Ž ghost:A");

    // â‘¢ drillbarï¼ˆrev17 äººçš„è£å†³ï¼‰ï¼šåªä¿ç•™é¢åŒ…å±‘ï¼Œä¸å¾—å†æœ‰ã€Œâ† è¿”å›žã€æŒ‰é’®ï¼›è¿”å›žå”¯ä¸€å…¥å£ = èŠ‚ç‚¹ Aã€‚
    const drillbar = await cdp.evalJS(`(() => {
      const bar = document.querySelector('#graph-2d-multilevel-root .graph-multilevel-drillbar');
      if (!bar) return { ok: false, reason: 'no drillbar' };
      const crumbs = [...bar.querySelectorAll('.graph-multilevel-crumb')].map((b) => (b.textContent || '').trim());
      const buttons = [...bar.querySelectorAll('button')].map((b) => (b.textContent || '').trim());
      return {
        ok: true,
        hidden: !!bar.hidden,
        crumbs,
        buttons,
        hasBackClass: !!bar.querySelector('.graph-multilevel-back'),
        hasArrow: buttons.some((t) => t.includes('â†')),
        text: (bar.textContent || '').trim(),
      };
    })()`);
    const shotPath = arg("shot", "");
    let screenshot = null;
    if (shotPath) {
      try {
        await cdp.send("Page.enable", {});
        const shot = await cdp.send("Page.captureScreenshot", { format: "png" });
        fs.mkdirSync(path.dirname(shotPath), { recursive: true });
        fs.writeFileSync(shotPath, Buffer.from(shot.data, "base64"));
        screenshot = shotPath;
      } catch (e) {
        screenshot = "ERROR: " + String((e && e.message) || e);
      }
    }
    evidence.steps.push({ step: "drillbar-no-back", ...drillbar, screenshot });
    const drillbarOk = !!(drillbar && drillbar.ok && !drillbar.hidden
      && drillbar.crumbs.some((t) => String(t).startsWith("L0_1"))
      && !drillbar.hasBackClass && !drillbar.hasArrow);

    // â‘¢ è·¨å±‚è™šçº¿ï¼ˆæœ¬è½®å›žå½’ï¼‰ï¼šghost â†’ å­å›¾å…¥å£èŠ‚ç‚¹ï¼Œå¿…é¡»çœŸå®žç”»å‡ºä¸€æ¡ dashed connectorï¼›
    //    ä¸”å®ƒä¸æ˜¯æ•°æ®è¾¹ï¼ˆedge ç»Ÿè®¡/edge åˆ—è¡¨ä¸å˜ï¼‰ã€‚
    const conn = await cdp.evalJS(`(() => {
      const r = window.MemoriaApp.state.graphMultilevel.mounted.renderer;
      const ctx = r._ctx;
      if (!ctx) return { ok: false, reason: "no ctx" };
      let mx = 0, my = 0, dash = [], lx = null, ly = null;
      const strokes = [];
      const o = {
        beginPath: ctx.beginPath, moveTo: ctx.moveTo, lineTo: ctx.lineTo,
        setLineDash: ctx.setLineDash, stroke: ctx.stroke,
      };
      ctx.beginPath = function () { lx = null; ly = null; return o.beginPath.call(this); };
      ctx.moveTo = function (x, y) { mx = x; my = y; return o.moveTo.call(this, x, y); };
      ctx.lineTo = function (x, y) { lx = x; ly = y; return o.lineTo.call(this, x, y); };
      ctx.setLineDash = function (a) { dash = Array.isArray(a) ? a.slice() : []; return o.setLineDash.call(this, a); };
      ctx.stroke = function () {
        strokes.push({
          dash: dash.slice(), strokeStyle: this.strokeStyle, lineWidth: this.lineWidth,
          from: { x: mx, y: my }, to: lx == null ? null : { x: lx, y: ly },
        });
        return o.stroke.call(this);
      };
      const norm = (s) => String(s || "").replace(/\\s+/g, "");
      const edgesBefore = r.lastRender ? r.lastRender.edges : null;
      r._draw();
      const connectors = strokes.filter((s) => s.dash.length === 2 && s.dash[0] === 5 && s.dash[1] === 4
        && norm(s.strokeStyle) === "rgba(88,166,255,0.55)" && Math.abs(s.lineWidth - 1.4) < 0.01 && s.to);
      const g = r.getNode("ghost:A");
      const t = r.getNode(${JSON.stringify(KP_ID)});
      ctx.beginPath = o.beginPath; ctx.moveTo = o.moveTo; ctx.lineTo = o.lineTo;
      ctx.setLineDash = o.setLineDash; ctx.stroke = o.stroke;
      return {
        ok: true, count: connectors.length,
        connectorFrom: connectors[0] ? connectors[0].from : null,
        connectorTo: connectors[0] ? connectors[0].to : null,
        ghost: g ? { x: g.x, y: g.y } : null,
        target: t ? { x: t.x, y: t.y } : null,
        edgesBefore, edgesAfter: r.lastRender ? r.lastRender.edges : null,
      };    })()`);
    const eps = conn && conn.ghost && conn.target && conn.connectorFrom && conn.connectorTo
      ? Math.max(dist(conn.connectorFrom, conn.ghost), dist(conn.connectorTo, conn.target))
      : null;
    const connectorOk = !!(conn && conn.ok && conn.count === 1 && eps != null && eps < 0.6
      && conn.edgesBefore === conn.edgesAfter);
    evidence.steps.push({
      step: "ghost-cross-layer-connector",
      count: conn ? conn.count : null,
      endpointMaxErrPx: eps == null ? null : Math.round(eps * 100) / 100,
      ghost: conn ? conn.ghost : null,
      target: conn ? conn.target : null,
      edgesBefore: conn ? conn.edgesBefore : null,
      edgesAfter: conn ? conn.edgesAfter : null,
      connectorOk,
    });

    // â‘  æ‹– KP â†’ ghost ä½ç§» > 0
    const kpFrom = pickTarget(child, KP_ID, "ghost:A");
    const kpTo = { x: kpFrom.x + 64, y: kpFrom.y + 34 };
    await ix.drag(kpFrom, kpTo, { steps: 14, settleMs: 16 });
    await sleep(1000);
    await stopAnim(cdp);
    const afterKp = await cdp.evalJS(SNAP);
    const ghostMoved = dist(afterKp.positions["ghost:A"], child.positions["ghost:A"]);
    const kpMoved = dist(afterKp.positions[KP_ID], child.positions[KP_ID]);
    evidence.steps.push({
      step: "drag-kp",
      kpFrom, kpTo,
      kpMovedPx: Math.round(kpMoved * 100) / 100,
      ghostMovedPx: Math.round(ghostMoved * 100) / 100,
      ghostFrom: child.positions["ghost:A"], ghostTo: afterKp.positions["ghost:A"],
    });

    // â‘¡ æ‹– ghost â†’ KP ä½ç§» > 0
    const gFrom = pickTarget(afterKp, "ghost:A", KP_ID);
    const gTo = { x: gFrom.x - 72, y: gFrom.y - 30 };
    await ix.drag(gFrom, gTo, { steps: 14, settleMs: 16 });
    await sleep(1000);
    await stopAnim(cdp);
    const afterGhost = await cdp.evalJS(SNAP);
    const ghostMoved2 = dist(afterGhost.positions["ghost:A"], afterKp.positions["ghost:A"]);
    const kpMoved2 = dist(afterGhost.positions[KP_ID], afterKp.positions[KP_ID]);
    evidence.steps.push({
      step: "drag-ghost",
      ghostFrom: gFrom, ghostTo: gTo,
      ghostMovedPx: Math.round(ghostMoved2 * 100) / 100,
      kpMovedPx: Math.round(kpMoved2 * 100) / 100,
      kpFrom: afterKp.positions[KP_ID], kpTo: afterGhost.positions[KP_ID],
    });

    evidence.checks = {
      parentOnlyCollapsedCluster: parentHasCluster && !parentHasKp,
      childHasNode001AndGhost: childHasKp && childHasGhost,
      ghostConnectorDrawn: connectorOk,
      drillbarOnlyCrumbsNoBack: drillbarOk,
      dragKpMovedGhost: ghostMoved > 0.01,
      dragGhostMovedKp: kpMoved2 > 0.01,
      singleCanvas: afterGhost.canvasCount === 1 && parent.canvasCount === 1 && child.canvasCount === 1,
    };
    evidence.verdict = Object.values(evidence.checks).every(Boolean) ? "PASS" : "FAIL";
  });
} catch (err) {
  evidence.verdict = "ERROR";
  evidence.error = String((err && err.stack) || err);
}
evidence.finishedAt = new Date().toISOString();
fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, JSON.stringify(evidence, null, 2), "utf8");
console.log(JSON.stringify({ verdict: evidence.verdict, checks: evidence.checks, out: OUT }));
if (evidence.verdict !== "PASS") process.exitCode = 1;
