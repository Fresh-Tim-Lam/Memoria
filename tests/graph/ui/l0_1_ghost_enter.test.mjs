/**
 * L0_1 æŠ˜å å®¹å™¨ â†’ è¿›å…¥å­å›¾ â†’ backgroundGhost å›žå½’ï¼ˆtask-391 rev12ï¼‰ã€‚
 *
 * 真实应用页面 + 真实 Edge，CDP Input 受信任拖拽：
 *   1) çˆ¶è§†å›¾æŠŠ container ç»„æŠ˜å æˆç°‡èŠ‚ç‚¹ï¼ˆ`group:demo:L0_1`ï¼‰ï¼Œæˆå‘˜ node-001 éšè—ï¼›
 *   2) 真实点击簇节点进入子图；
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
    positions[id] = { x: p.x, y: p.y, radius: node ? node.radius : null, kind: node ? node.kind : null, layer: node ? node.layer : null, label: node ? node.label : null };
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
/** 取目标节点圆周上“朝另一节点方向”的点（避开左上工具栏覆盖区，保证真实命中节点）。 */
function nodePointToward(snap, id, otherId, f = 0.55) {
  const t = snap.positions[id];
  const o = snap.positions[otherId];
  const center = toScreen(snap, t);
  if (!o) return center;
  const os = toScreen(snap, o);
  const r = (t.radius || 6) * (snap.cam.scale || 1);
  const dx = os.x - center.x, dy = os.y - center.y;
  const len = Math.hypot(dx, dy) || 1;
  return { x: center.x + (dx / len) * r * f, y: center.y + (dy / len) * r * f };
}

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
    // 侧栏若自动折叠：真实点击展开（否则图谱宿主宽 0，画布不布局）
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
      // 兜底（正常 container 组会自动折叠）：显式折叠，仍走真实 pointerdown 进入
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

    // 真实点击簇 → app 内 groupClick → enterMultilevelGroup（160ms 后切子图）
    // ② rev26 demo：4 个容器簇 + 1 个独立知识点 + presentation-only 连线（不进数据边）。
    const demo = await cdp.evalJS(`(() => {
      const r = window.MemoriaApp.state.graphMultilevel.mounted.renderer;
      const ctx = r._ctx;
      const groupIds = ['group:demo:L0_1', 'group:demo:L0_2', 'group:demo:L0_3', 'group:demo:L0_4'];
      const labels = {};
      const missing = [];
      for (const gid of groupIds) {
        const node = r.getNode(gid);
        if (!node) { missing.push(gid); continue; }
        labels[gid] = node.label;
      }
      const kp = r.getNode('node-002');
      let links = [];
      let linkStats = null;
      if (ctx) {
        const strokes = [];
        let mx = 0, my = 0, dash = [], lx = null, ly = null;
        const o = { beginPath: ctx.beginPath, moveTo: ctx.moveTo, lineTo: ctx.lineTo, setLineDash: ctx.setLineDash, stroke: ctx.stroke };
        ctx.beginPath = function () { lx = null; ly = null; return o.beginPath.call(this); };
        ctx.moveTo = function (x, y) { mx = x; my = y; return o.moveTo.call(this, x, y); };
        ctx.lineTo = function (x, y) { lx = x; ly = y; return o.lineTo.call(this, x, y); };
        ctx.setLineDash = function (a) { dash = Array.isArray(a) ? a.slice() : []; return o.setLineDash.call(this, a); };
        ctx.stroke = function () {
          strokes.push({ dash: dash.slice(), style: String(this.strokeStyle || '').replace(/\\s+/g, ''), w: this.lineWidth, from: { x: mx, y: my }, to: lx == null ? null : { x: lx, y: ly } });
          return o.stroke.call(this);
        };
        const edgesBefore = r.lastRender ? r.lastRender.edges : null;
        const edgeListBefore = r._edgeList.length;
        r._draw();
        ctx.beginPath = o.beginPath; ctx.moveTo = o.moveTo; ctx.lineTo = o.lineTo; ctx.setLineDash = o.setLineDash; ctx.stroke = o.stroke;
        links = strokes.filter((s) => s.to && s.dash.length === 2 && s.dash[0] === 4 && s.dash[1] === 4
          && s.style === 'rgba(139,148,158,0.55)' && Math.abs(s.w - 1.2) < 0.01);
        linkStats = { edgesBefore, edgesAfter: r.lastRender ? r.lastRender.edges : null, edgeListBefore, edgeListAfter: r._edgeList.length };
      }
      const g = window.MemoriaApp.state.graphMultilevel || {};
      const pres = g.presentation || {};
      const vm = g.vm || { nodes: [] };
      return {
        ok: true,
        sceneIds: [...r.getPositions().keys()].sort(),
        missing,
        labels,
        hasKp002: !!kp,
        kp002: kp ? { x: kp.x, y: kp.y } : null,
        kpLabels: ['node-003', 'node-004', 'node-005'].reduce((o, id) => { const n = r.getNode(id); if (n) o[id] = n.label; return o; }, {}),
        linkCount: links.length,
        linkEndpoints: links.map((l) => ({ from: l.from, to: l.to })),
        noEdgeStats: linkStats,
        presentationGroups: (pres.groups || []).map((x) => ({ id: x.group_id, label: x.label, members: (x.member_ids || []).length, x: x.x, y: x.y, container: x.container, empty: x.empty_container })),
        presentationLinks: pres.links || null,
        vmNodes: (vm.nodes || []).map((n) => ({ id: n.id, kind: n.kind, presence: n.presence })),
        rendererGroups: (r.getGroups() || []).map((x) => ({ id: x.group_id, members: (x.member_ids || []).length })),
        collapsedGroups: [...(r._collapsedGroups || [])],
      };
    })()`);
    evidence.steps.push({ step: "demo-l0-clusters", ...demo });
    const labelsOk = !!(demo && !demo.missing.length
      && ["L0_1", "L0_2", "L0_3", "L0_4"].every((lab) => Object.values(demo.labels).includes(lab))
      && Object.values(demo.labels).every((lab) => !/\(\d+\)/.test(String(lab || ""))));
    const linksOk = !!(demo && demo.linkCount >= 7
      && demo.noEdgeStats && demo.noEdgeStats.edgesBefore === demo.noEdgeStats.edgesAfter
      && demo.noEdgeStats.edgeListBefore === demo.noEdgeStats.edgeListAfter);
    const kp002Ok = !!(demo && demo.hasKp002);
    const l01Group = ((demo && demo.rendererGroups) || []).find((g) => g.id === "demo:L0_1");
    const parentL01Members4 = !!(l01Group && l01Group.members === 4)
      && !["node-006", "node-007", "node-008"].some((id) => (demo.sceneIds || []).includes(id));
    const hubKpsOk = !!(demo && demo.kpLabels
      && demo.kpLabels['node-003'] === '第三个知识点'
      && demo.kpLabels['node-004'] === '第四个知识点'
      && demo.kpLabels['node-005'] === '第五个知识点');
    const shotParent = arg("shot-parent", "");
    let parentScreenshot = null;
    if (shotParent) {
      try {
        await cdp.send("Page.enable", {});
        const shot = await cdp.send("Page.captureScreenshot", { format: "png" });
        fs.mkdirSync(path.dirname(shotParent), { recursive: true });
        fs.writeFileSync(shotParent, Buffer.from(shot.data, "base64"));
        parentScreenshot = shotParent;
      } catch (e) {
        parentScreenshot = "ERROR: " + String((e && e.message) || e);
      }
    }
    evidence.steps.push({ step: "demo-screenshot", parentScreenshot });

    // 真实点击 L0_1 簇 → 进入子站；布局抖动时重试一次（仍走真实 pointerdown）
    let enteredChild = false;
    for (let attempt = 0; attempt < 2 && !enteredChild; attempt++) {
      const clusterPoint = toScreen(parent, parent.positions[GROUP_NODE]);
      await ix.click(clusterPoint.x, clusterPoint.y);
      enteredChild = await cdp.waitFor(
        `(() => { const r=window.MemoriaApp.state.graphMultilevel.mounted.renderer; if(!r||!r.getPositions) return false; const p=r.getPositions(); return p.has("ghost:A") && p.has(${JSON.stringify(KP_ID)}); })()`,
        { timeout: 15000, label: "child view node-001 + ghost:A" }
      ).then(() => true).catch(() => false);
      if (!enteredChild) {
        await sleep(700);
        await stopAnim(cdp);
        parent = await cdp.evalJS(SNAP);
      }
    }
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

    // rev44：子站 hub = node-001 直连本站新增 node-006/007/008（真实数据边，不是 presentation hub）
    const childStation = await cdp.evalJS(`(() => {
      const r = window.MemoriaApp.state.graphMultilevel.mounted.renderer;
      const ids = [...r.getPositions().keys()].sort();
      const list = (r._edgeList || []).map((e) => {
        const p = String(e.id).split("|");
        return p.length >= 3 ? { type: p[0], s: p[1], t: p[2] } : null;
      }).filter(Boolean);
      const visible = list.filter((e) => ids.includes(e.s) && ids.includes(e.t));
      const degree = visible.filter((e) => e.s === "node-001" || e.t === "node-001").length;
      const stack = window.MemoriaApp.state.graphMultilevel.drill.stack || [];
      const entry = stack[stack.length - 1] || {};
      const hubEdges = ((entry.backgroundEdges) || []).filter((e) => e.hub === true).length;
      return { ids, dataEdges: visible.length, node001Degree: degree, hubEdges };
    })()`);
    const childIds = (childStation && childStation.ids) || [];
    const childStationOk = !!(childStation
      && ["node-001", "node-006", "node-007", "node-008"].every((id) => childIds.includes(id))
      && childStation.dataEdges === 3
      && childStation.node001Degree === 3
      && childStation.hubEdges === 0);
    evidence.steps.push({ step: "child-hub-station", ...(childStation || {}) });


    // ④ rev29 C：进入子站后，上一站全部 visible 节点以 dim ghost 背景层出现（不可命中/不可拖）。
    const bgView = await cdp.evalJS(`(() => {
      const r = window.MemoriaApp.state.graphMultilevel.mounted.renderer;
      const ids = [...r.getPositions().keys()].sort();
      const bg = ids.filter((id) => id.startsWith('bg:'));
      const nodes = bg.map((id) => r.getNode(id)).filter(Boolean);
      const pickIds = nodes.map((n) => { const p = r._scene.pick(n.x, n.y); return p ? String(p.id) : null; });
      const ctx = r._ctx;
      let texts = [];
      let gradients = 0;
      const fillStyles = [];
      const fills = [];
      const oFT = ctx.fillText;
      const oGrad = ctx.createRadialGradient;
      const oFill = ctx.fill;
      const oStroke = ctx.stroke;
      const strokes = [];
      ctx.fillText = function (t, x, y) { texts.push(String(t)); return oFT.call(this, t, x, y); };
      ctx.createRadialGradient = function (...a) { gradients += 1; return oGrad.apply(this, a); };
      ctx.fill = function () {
        fillStyles.push(String(this.fillStyle || ""));
        fills.push({ alpha: Number(this.globalAlpha), style: String(this.fillStyle || "") });
        return oFill.call(this);
      };
      ctx.stroke = function () {
        strokes.push({ alpha: Number(this.globalAlpha), style: String(this.strokeStyle || ""), width: Number(this.lineWidth) });
        return oStroke.call(this);
      };
      r._draw();
      ctx.fillText = oFT;
      ctx.createRadialGradient = oGrad;
      ctx.fill = oFill;
      ctx.stroke = oStroke;
      // rev35：快照项的原始半径/深度（用于校验 log 衰减）
      const stack = window.MemoriaApp.state.graphMultilevel.drill.stack || [];
      const entry = stack[stack.length - 1] || {};
      const snapshotMap = {};
      for (const item of (entry.backgroundSnapshot || [])) {
        snapshotMap[String(item.id)] = { radius: Number(item.radius), depth: Number(item.depth) };
      }
      const nodeRadii = {};
      for (const n of nodes) nodeRadii[String(n.id)] = Number(n.radius);
      const whiteAlphas = fills.filter((f) => f.style === "#f0f6fc").map((f) => f.alpha);
      return {
        ids, bg,
        labels: nodes.map((n) => n.label),
        layers: nodes.map((n) => n.layer),
        hitPolicies: nodes.map((n) => n.hitPolicy),
        pickIds,
        texts,
        gradients,
        whiteFill: fillStyles.includes("#f0f6fc"),
        dimFill: fillStyles.some((c) => String(c).includes("rgba(139") || String(c).includes("rgba(201,209,217")),
        snapshotMap,
        nodeRadii,
        whiteAlphas,
        bgEdgeCount: (r._bgSnapshotEdges || []).length,
        entryEdgeCount: ((entry.backgroundEdges) || []).length,
        bgEdgeStrokes: strokes.filter((x) => x.width < 1.2 && x.alpha < 1 && x.style === "#58a6ff").length,
      };
    })()`);
    evidence.steps.push({ step: "child-background-snapshot", ...bgView });

    const shotChild = arg("shot-child-bg", "");
    let childBgScreenshot = null;
    if (shotChild) {
      try {
        await cdp.send("Page.enable", {});
        const shot = await cdp.send("Page.captureScreenshot", { format: "png" });
        fs.mkdirSync(path.dirname(shotChild), { recursive: true });
        fs.writeFileSync(shotChild, Buffer.from(shot.data, "base64"));
        childBgScreenshot = shotChild;
      } catch (e) {
        childBgScreenshot = "ERROR: " + String((e && e.message) || e);
      }
    }
    evidence.steps.push({ step: "child-background-screenshot", childBgScreenshot });
    const bgLabels = Array.isArray(bgView && bgView.labels) ? bgView.labels : [];
    const bgOk = !!(bgView && bgView.bg.length === 7
      && bgView.layers.every((l) => l === "background")
      && bgView.hitPolicies.every((h) => h === "none")
      && bgView.pickIds.every((id) => !id || !String(id).startsWith("bg:")));
    // rev32：背景化节点=正常白色发光、不得绘制任何标签，也不得仍是 dim 灰
    const bgNoLabels = !!(bgView && Array.isArray(bgView.texts)
      && !["L0_2", "L0_3", "L0_4", "第二个知识点", "第三个知识点", "第四个知识点", "第五个知识点"]
        .some((t) => bgView.texts.includes(t)));
    const bgWhiteGlow = !!(bgView && bgView.whiteFill === true && bgView.gradients >= 4 && bgView.dimFill === false);
    // rev35：log 深度衰减——立即上一站 depth=1 ⇒ scale=0.82、alpha=0.48（±0.02），且 alpha < 1
    const bgSnapIds = Object.keys((bgView && bgView.snapshotMap) || {});
    const bgRadiiOk = bgSnapIds.length === 7 && bgSnapIds.every((id) => {
      const snap = bgView.snapshotMap[id];
      const drawn = bgView.nodeRadii[`bg:${id}`];
      if (!snap || !Number.isFinite(drawn) || !Number.isFinite(snap.radius) || snap.radius <= 0) return false;
      const ratio = drawn / snap.radius;
      return snap.depth === 1 && ratio >= 0.79 && ratio <= 0.85;
    });
    const bgAlphaOk = !!(bgView && Array.isArray(bgView.whiteAlphas)
      // depth=1 ⇒ alpha=0.48：7 个背景节点各一次白填充（前景 ghost A 的 #f0f6fc 填充 alpha=1 不计入）
      && bgView.whiteAlphas.filter((a) => Math.abs(a - 0.48) < 0.03).length >= 7
      && bgView.whiteAlphas.filter((a) => a >= 1).length <= 1);
    const bgDepthDecayOk = bgRadiiOk && bgAlphaOk;
    // rev38：上一站背景边（数据边 + presentation links）保留并绘制（alpha<1），不进数据边
    const bgEdgesOk = !!(bgView && bgView.bgEdgeCount > 0
      && bgView.bgEdgeCount === bgView.entryEdgeCount
      && bgView.bgEdgeStrokes >= bgView.bgEdgeCount);
    evidence.steps.push({
      step: "child-background-style",
      bgNoLabels, bgWhiteGlow, bgDepthDecayOk,
      snapshotMap: bgView && bgView.snapshotMap,
      nodeRadii: bgView && bgView.nodeRadii,
      whiteAlphas: bgView && bgView.whiteAlphas,
    });

    // ⑤ drillbar（rev17 人的裁决）：只保留面包屑，不得再有「← 返回」按钮；返回唯一入口 = 节点 A。
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

    // ⑤ 图谱内文字不可被拖拽选择（rev20 人的裁决）：样式 + 真机在 legend/badge 文字上拖拽无选区。
    const noSelect = await cdp.evalJS(`(() => {
      const host = document.querySelector('#graph-2d-multilevel-root');
      const canvas = host && host.querySelector('canvas');
      const badge = host && (host.querySelector('.graph-multilevel-badge') || host.querySelector('.graph-multilevel-drillbar'));
      if (!host || !canvas) return { ok: false, reason: 'no host/canvas' };
      const hs = getComputedStyle(host);
      const cs = getComputedStyle(canvas);
      const ts = badge ? getComputedStyle(badge) : null;
      const r = badge ? badge.getBoundingClientRect() : null;
      const sel = document.querySelector('#preview .-src-block') || document.querySelector('#preview');
      const ps = sel ? getComputedStyle(sel) : null;
      return {
        ok: true,
        hostUserSelect: hs.userSelect || hs.webkitUserSelect || null,
        hostWebkitUserSelect: hs.webkitUserSelect || null,
        badgeUserSelect: ts ? (ts.userSelect || ts.webkitUserSelect || null) : null,
        canvasUserSelect: cs.userSelect || cs.webkitUserSelect || null,
        canvasTouchAction: cs.touchAction || null,
        canvasUserDrag: cs.webkitUserDrag || null,
        canvasDraggableAttr: canvas.getAttribute('draggable'),
        previewUserSelect: ps ? (ps.userSelect || ps.webkitUserSelect || null) : null,
        badgePoint: r && r.width > 4 ? { x1: r.left + 2, x2: r.right - 2, y: r.top + r.height / 2 } : null,
      };
    })()`);
    let selectionAfterTextDrag = null;
    if (noSelect && noSelect.ok && noSelect.badgePoint) {
      await cdp.evalJS("(() => { window.getSelection().removeAllRanges(); return true; })()");
      const bp = noSelect.badgePoint;
      await ix.drag({ x: bp.x1, y: bp.y }, { x: bp.x2, y: bp.y }, { steps: 10, settleMs: 10 });
      await sleep(200);
      selectionAfterTextDrag = await cdp.evalJS("window.getSelection() ? window.getSelection().toString() : 'no-selection-api'");
    }
    const noSelectOk = !!(noSelect && noSelect.ok
      && noSelect.hostUserSelect === "none"
      && noSelect.badgeUserSelect === "none"
      && noSelect.canvasUserSelect === "none"
      && noSelect.canvasTouchAction === "none"
      && (noSelect.canvasUserDrag === "none" || noSelect.canvasUserDrag === null)
      && noSelect.canvasDraggableAttr === "false"
      && noSelect.previewUserSelect !== "none"
      && selectionAfterTextDrag === "");
    evidence.steps.push({ step: "text-not-selectable", ...noSelect, selectionAfterTextDrag, noSelectOk });

    // 文字拖拽发生在画布上可能平移相机：重新取快照，保证后续屏幕坐标换算使用当前 camera。
    await stopAnim(cdp);
    child = await cdp.evalJS(SNAP);


    // ③ 跨层虚线（本轮回归）：ghost → 子图入口节点，必须真实画出一条 dashed connector；
    //    且它不是数据边（edge 统计/edge 列表不变）。
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
    const bgIds = Object.keys(child.positions).filter((id) => id.startsWith("bg:"));
    const bgMovedMax = bgIds.reduce((m, id) => Math.max(m, dist(afterKp.positions[id], child.positions[id])), 0);
    const kpMoved = dist(afterKp.positions[KP_ID], child.positions[KP_ID]);
    evidence.steps.push({
      step: "drag-kp",
      kpFrom, kpTo,
      kpMovedPx: Math.round(kpMoved * 100) / 100,
      ghostMovedPx: Math.round(ghostMoved * 100) / 100,
      bgMovedMaxPx: Math.round(bgMovedMax * 100) / 100,
      ghostFrom: child.positions["ghost:A"], ghostTo: afterKp.positions["ghost:A"],
    });

    // ② 拖 ghost → KP 位移 > 0
    const gFrom = nodePointToward(afterKp, "ghost:A", KP_ID);
    const gTo = { x: gFrom.x - 72, y: gFrom.y - 30 };
    const ghostHitDiag = await cdp.evalJS(`(() => {
      const r = window.MemoriaApp.state.graphMultilevel.mounted.renderer;
      const cv = document.querySelector('#graph-2d-multilevel-root canvas');
      const rect = cv.getBoundingClientRect();
      const cam = r._camera || { x: 0, y: 0, scale: 1 };
      const sx = (${gFrom.x} - rect.left - cam.x) / (cam.scale || 1);
      const sy = (${gFrom.y} - rect.top - cam.y) / (cam.scale || 1);
      const pick = r._scene.pick(sx, sy);
      const ghost = r.getNode('ghost:A');
      const el = document.elementFromPoint(${gFrom.x}, ${gFrom.y});
      return {
        world: { x: sx, y: sy },
        elementAtPoint: el ? { tag: el.tagName, cls: String(el.className || ""), id: el.id || "" } : null,
        dragStateBefore: r._drag ? { mode: r._drag.mode, nodeId: r._drag.nodeId } : null,
        pickId: pick ? String(pick.id) : null,
        pickKind: pick ? pick.kind : null,
        ghost: ghost ? { layer: ghost.layer, hitPolicy: ghost.hitPolicy, radius: ghost.radius, x: ghost.x, y: ghost.y } : null,
        canvas: { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
      };
    })()`);
    evidence.steps.push({ step: "ghost-drag-diag", ...ghostHitDiag });
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

    // ⑥ rev29 C：返回上一站 → 背景 ghost 清除 + 上一站（L0_1..4 + KP）恢复
    const backPoint = nodePointToward(afterGhost, "ghost:A", KP_ID);
    await ix.click(backPoint.x, backPoint.y);
    await sleep(1200);
    await stopAnim(cdp);
    const restored = await cdp.evalJS(SNAP);
    const restoredIds = restored ? Object.keys(restored.positions).sort() : [];
    const bgAfterBack = restoredIds.filter((id) => id.startsWith("bg:"));
    const backOk = bgAfterBack.length === 0 && restoredIds.includes(GROUP_NODE);
    evidence.steps.push({ step: "back-to-parent", restoredIds, bgAfterBack, hasL01: restoredIds.includes(GROUP_NODE) });

    // ③ rev29 B：“全展开/Expand all” 前后，L0_1 只能有一个表达（canvas fillText 计数）。
    const countL01 = async () => cdp.evalJS(`(() => {
      const r = window.MemoriaApp.state.graphMultilevel.mounted.renderer;
      let texts = [];
      const ctx = r._ctx;
      const o = ctx.fillText;
      ctx.fillText = function (t, x, y) { texts.push(String(t)); return o.call(this, t, x, y); };
      r._draw();
      ctx.fillText = o;
      return { count: texts.filter((t) => /^L0_1(\s|$)/.test(t)).length, texts };
    })()`);
    const l01Collapsed = await countL01();
    const expandBtnRect = await cdp.evalJS(`(() => { const b=document.querySelector('.graph-multilevel-expand'); if(!b) return null; const r=b.getBoundingClientRect(); return {x:r.left+r.width/2,y:r.top+r.height/2}; })()`);
    if (expandBtnRect) { await ix.click(expandBtnRect.x, expandBtnRect.y); await sleep(1800); }
    const expandMode = await cdp.evalJS(`(() => { const nav=window.MemoriaApp.state.graphMultilevel.nav; return nav&&nav.getMode?nav.getMode():null; })()`);
    // 真实点击可能触发异步重载；无论 mode 是否切换，渲染器侧 setExpandAll 都必须保证单表达。
    const l01Expanded = await cdp.evalJS(`(() => {
      const r = window.MemoriaApp.state.graphMultilevel.mounted.renderer;
      r.setExpandAll(true);
      let texts = [];
      const ctx = r._ctx;
      const o = ctx.fillText;
      ctx.fillText = function (t, x, y) { texts.push(String(t)); return o.call(this, t, x, y); };
      r._draw();
      ctx.fillText = o;
      return {
        count: texts.filter((t) => /^L0_1(\s|$)/.test(t)).length,
        ids: [...r.getPositions().keys()].sort(),
        collapsed: [...(r._collapsedGroups || [])],
        texts,
      };
    })()`);
    await cdp.evalJS(`(() => { const r=window.MemoriaApp.state.graphMultilevel.mounted.renderer; r.setExpandAll(false); return true; })()`);
    const expandEvidence = { l01Collapsed, expandMode, l01Expanded };
    evidence.steps.push({ step: "expand-all-single-l01", ...expandEvidence });

    evidence.checks = {
      demoFourClusters: !!(demo && !demo.missing.length),
      demoClusterLabelsClean: labelsOk,
      demoKp002Visible: kp002Ok,
      demoHubKpsVisible: hubKpsOk,
      demoPresentationLinks: linksOk,
      expandAllSingleL01: !!(l01Collapsed && l01Expanded
        && l01Collapsed.count === 1 && l01Expanded.count === 1),
      childBackgroundGhosts: bgOk,
      childHubStation: childStationOk,
      parentL01Members4,
      childBackgroundNoLabels: bgNoLabels,
      childBackgroundWhiteGlow: bgWhiteGlow,
      childBackgroundDepthDecay: bgDepthDecayOk,
      childBackgroundEdges: bgEdgesOk,
      backClearsBackground: backOk,
      parentOnlyCollapsedCluster: parentHasCluster && !parentHasKp,
      childHasNode001AndGhost: childHasKp && childHasGhost,
      ghostConnectorDrawn: connectorOk,
      drillbarOnlyCrumbsNoBack: drillbarOk,
      textNotSelectable: noSelectOk,
      dragKpMovedGhost: ghostMoved > 0.01,
      bgNodesParticipateInForce: bgMovedMax > 0.05,
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
