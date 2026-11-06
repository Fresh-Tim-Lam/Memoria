/**
 * 链接小窗 pin 状态回归（task-391 rev14，真实应用 + 真实 Edge + CDP 受信任输入）。
 *
 * 预置 ui-settings 的 `linkPanel.pinned=true`（模拟历史持久化），断言：
 *   1) 新面板仍为 `pinned=false`（不再从 prefs 恢复），pin 图标 aria-pressed=false；
 *   2) 未 pin 时点面板外（真实画布/空白）→ 小窗关闭；
 *   3) 点 pin 后 aria-pressed=true；
 *   4) 已 pin 时点面板外 → 小窗保留；
 *   5) 保存回读的 ui-settings.linkPanel **不含 pinned=true**（不再持久化 pinned）。
 *
 * 由 `tests/graph/ui/test_link_panel_pin.py` 起 harness 后调用。
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
const URL = arg("url", "http://127.0.0.1:9501/");
const OUT = arg("out", path.join(HERE, "link-panel-pin-realapp.json"));
const FILE = arg("file", "imp-kp-alpha.md");

const evidence = { kind: "task-391-link-panel-pin-realapp", url: URL, file: FILE, steps: [], checks: {}, verdict: null };

function rectExpr(sel) {
  return `(() => { const el = document.querySelector(${JSON.stringify(sel)}); if (!el) return null; const r = el.getBoundingClientRect(); if (r.width < 1 || r.height < 1) return null; return { x: r.left + r.width / 2, y: r.top + r.height / 2, left: r.left, top: r.top, width: r.width, height: r.height }; })()`;
}

/** 面板外、且 elementFromPoint 不在面板内的可点位置。 */
const OUTSIDE_EXPR = `(() => {
  const p = document.querySelector('#link-panel');
  const r = p ? p.getBoundingClientRect() : null;
  const cands = [[10, 10], [window.innerWidth - 24, window.innerHeight - 24], [window.innerWidth / 2, window.innerHeight - 30], [10, window.innerHeight - 30]];
  for (const [x, y] of cands) {
    if (r && x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) continue;
    const el = document.elementFromPoint(x, y);
    if (el && !el.closest('#link-panel')) return { x, y, tag: el.tagName };
  }
  return null;
})()`;

async function panelState(cdp) {
  return cdp.evalJS(`(() => {
    const A = window.MemoriaApp;
    const pop = A.state.linkPanel;
    const el = document.querySelector('#link-panel');
    const pin = document.querySelector('#link-panel [data-panel-pin]');
    return {
      hasPanel: !!el,
      statePinned: pop ? !!pop.pinned : null,
      ariaPressed: pin ? pin.getAttribute('aria-pressed') : null,
      prefsPinned: A.state.linkPanelPrefs ? A.state.linkPanelPrefs.pinned : null,
    };
  })()`);
}

async function clickOutside(cdp, ix) {
  const pt = await cdp.evalJS(OUTSIDE_EXPR);
  if (!pt) throw new Error("找不到面板外可点位置");
  await ix.click(pt.x, pt.y);
  await sleep(350);
}

async function openPanelFromWikilink(cdp, ix) {
  const chip = await cdp.evalJS(rectExpr("#preview .-wikilink"));
  if (!chip) throw new Error("预览中找不到 .-wikilink");
  await ix.click(chip.x, chip.y);
  await cdp.waitFor(`!!document.querySelector('#link-panel')`, { timeout: 30000, label: "link panel" });
  await sleep(250);
}

try {
  await withBrowser(URL, async (cdp, ix) => {
    await cdp.waitFor("!!window.MemoriaApp", { timeout: 90000, label: "MemoriaApp" });
    // 打开带 wikilink 的文档
    const opened = await cdp.evalJS(`(async () => {
      try { await window.MemoriaApp.openFile(${JSON.stringify(FILE)}); return { ok: true }; }
      catch (e) { return { ok: false, reason: String((e && e.message) || e) }; }
    })()`);
    evidence.steps.push({ step: "open-file", ...opened });
    // 切到「预览」视图（wikilink 只在预览 DOM 渲染；默认可能是源码视图）
    const viewBtn = await cdp.evalJS(`(() => {
      const pane = document.querySelector('#preview-pane');
      const visible = !!(pane && pane.offsetParent !== null);
      const b = document.querySelector('[data-view="preview"]');
      if (!b) return { ok: false, reason: "no preview view button", visible };
      const r = b.getBoundingClientRect();
      return { ok: true, visible, x: r.left + r.width / 2, y: r.top + r.height / 2 };
    })()`);
    evidence.steps.push({ step: "preview-view-button", ...viewBtn });
    if (viewBtn.ok && !viewBtn.visible) {
      await ix.click(viewBtn.x, viewBtn.y);
      await sleep(600);
    }
    await cdp.waitFor(`!!document.querySelector('#preview .-wikilink')`, { timeout: 60000, label: "wikilink in preview" });

    // 预置 prefs 应为 pinned=true（模拟历史持久化）
    const prefsLoaded = await cdp.evalJS(`(async () => {
      const res = await window.MemoriaApp.call('get_ui_settings');
      const lp = res && res.status === 'ok' && res.settings ? res.settings.linkPanel : null;
      return { ok: true, filePinned: lp ? lp.pinned === true : null, fileHasLinkPanel: !!lp };
    })()`);
    evidence.steps.push({ step: "prefs-before-open", ...prefsLoaded });

    // ① 打开小窗：即使 prefs.pinned=true，新面板也必须是 false
    await openPanelFromWikilink(cdp, ix);
    const s1 = await panelState(cdp);
    evidence.steps.push({ step: "panel-opened", ...s1 });

    // ② 未 pin：点面板外 → 关闭
    await clickOutside(cdp, ix);
    const s2 = await panelState(cdp);
    evidence.steps.push({ step: "outside-after-open", ...s2 });

    // ③ 重新打开 → 点 pin → pinned=true
    await openPanelFromWikilink(cdp, ix);
    const pinRect = await cdp.evalJS(rectExpr("#link-panel [data-panel-pin]"));
    if (!pinRect) throw new Error("找不到 pin 按钮");
    await ix.click(pinRect.x, pinRect.y);
    await sleep(250);
    const s3 = await panelState(cdp);
    evidence.steps.push({ step: "after-pin-click", ...s3 });

    // ④ 已 pin：点面板外 → 保留
    await clickOutside(cdp, ix);
    const s4 = await panelState(cdp);
    evidence.steps.push({ step: "outside-while-pinned", ...s4 });

    // ⑤ 持久化回读：不应含 pinned=true（等待 300ms 去抖 + RPC）
    await sleep(900);
    const persisted = await cdp.evalJS(`(async () => {
      const res = await window.MemoriaApp.call('get_ui_settings');
      const lp = res && res.status === 'ok' && res.settings ? res.settings.linkPanel : null;
      return { ok: true, linkPanel: lp, pinnedStored: lp ? lp.pinned === true : false };
    })()`);
    evidence.steps.push({ step: "persisted-settings", ...persisted });

    evidence.checks = {
      prefsSeededPinnedTrue: prefsLoaded.filePinned === true,
      defaultUnpinnedWithPrefsPinned: s1.hasPanel && s1.statePinned === false && s1.ariaPressed === "false",
      outsideClosesUnpinned: !s2.hasPanel && s2.statePinned === null,
      pinToggleWorks: s3.hasPanel && s3.statePinned === true && s3.ariaPressed === "true",
      pinnedSurvivesOutside: s4.hasPanel && s4.statePinned === true && s4.ariaPressed === "true",
      persistOmitsPinned: persisted.pinnedStored === false,
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
