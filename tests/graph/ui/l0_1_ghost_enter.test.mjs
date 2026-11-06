/**
 * L0_1 折叠容器 → 进入子图 → backgroundGhost 回归（task-391 rev12）。
 *
 * 真实应用页面 + 真实 Edge，CDP `Input` 域受信任拖拽：
 *   1) 父视图把 container 组折叠成簇节点（`group:demo:L0_1`），成员 node-001 隐藏；
 *   2) 真实点击簇节点进入子图；
 *   3) 断言 child view `getPositions()` 同时有 node-001 与 ghost:A（修复前 ghost=null）；
 *   4) 拖 KP → ghost 位移>0；拖 ghost → KP 位移>0；全程单画布。
 *
 * 由 `tests/graph/ui/test_l0_1_ghost_enter.py` 起 harness 后调用：
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

/** 在两个圆可能重叠时，取离另一节点更远的圆周点，保证 pointerdown 命中目标节点。 */
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
    // 切换到 2D 图谱并加载数据（等价用户打开图谱）
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

    // 父视图：container 组应已折叠成簇节点，成员不在 scene（可以点簇进入子图）
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
    if (!parent.positions[GROUP_NODE]) throw new Error("父视图缺折叠簇节点 " + GROUP_NODE);

    // 真实点击簇 → app 内 groupClick → enterMultilevelGroup（160ms 后切子图）
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
    if (!childHasKp || !childHasGhost) throw new Error("进入子图后未同时存在 node-001 与 ghost:A");

    // ① 拖 KP → ghost 位移 > 0
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

    // ② 拖 ghost → KP 位移 > 0
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
