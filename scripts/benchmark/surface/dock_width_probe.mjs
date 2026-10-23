/**
 * dock_width_probe.mjs —— agent 会话栏宽度上限探针（0.4.7 任务 3）
 *
 * **模块形态**：导出 `probeDockWidth(cdp)`，由调用方（`withBrowser`）传入**已连接**的 cdp。
 * 不自己建连接 —— 否则与 withBrowser 抢同一浏览器的 CDP 连接会 fetch failed。
 *
 * 验证目标（改前 `max-width:34rem` + `DOCK_MAX_REM=34` ⇒ 可拖宽被钉死 ≈544px）：
 *   A1 宽屏 1920：请求 50rem ⇒ dock 实际宽 > 34rem（证明静态上限已解除）
 *   A2 同时「文档区 #content ≥ 360px」（没破文档区保护）
 *   A3 窄屏 1280 + 请求 60rem ⇒ 被 available 钳住，content 仍 ≥ 360
 *   A4 极窄 900 ⇒ 自动隐藏或缩到最小，不溢出
 *   A5 回宽屏 ⇒ 期望宽恢复（不被窄屏污染）
 *
 * CLI（兼容旧用法，手工排查）：
 *   node dock_width_probe.mjs <url> [--json]
 */

const GEOM_JS = `(() => {
  const d = document.querySelector('#-agent-dock');
  const sb = document.querySelector('#-sidebar');
  const c = document.querySelector('#content');
  const m = document.querySelector('#main');
  const px = (el) => el ? Math.round(el.getBoundingClientRect().width) : null;
  const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
  return {
    rem,
    dock: px(d), dockInline: d ? d.style.width || "" : "",
    dockCollapsed: !!(d && d.classList.contains('-agent-dock--collapsed')),
    dockAutoHidden: !!(d && d.classList.contains('-agent-dock--auto-hidden')),
    dockMaxWidth: d ? getComputedStyle(d).maxWidth : "",
    dockMinWidth: d ? getComputedStyle(d).minWidth : "",
    sidebar: px(sb), content: px(c), main: m ? m.clientWidth : null,
    win: { w: window.innerWidth, h: window.innerHeight },
  };
})()`;

const SET_WIDTH_JS = (wantRem) => `(() => {
  const AP = window.MemoriaAgentPanel || null;
  if (AP && typeof AP.setDockWidthForTest === 'function') { AP.setDockWidthForTest(${wantRem}); return 'testHook'; }
  return 'no-hook';
})()`;

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function setViewport(cdp, width, height) {
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await sleep(450);
}

/**
 * 跑全部断言。
 * @param {object} cdp 已连接的 CDP 客户端（需 send / evalJS）
 * @returns {Promise<{ok:boolean, checks:Array}>}
 */
export async function probeDockWidth(cdp) {
  const out = { checks: [], ok: true };
  const rec = (id, pass, detail) => {
    out.checks.push({ id, pass, detail });
    if (!pass) out.ok = false;
  };

  // 确保会话栏展开
  await cdp.evalJS(`(() => {
    const d = document.querySelector('#-agent-dock');
    if (d && d.classList.contains('-agent-dock--collapsed')) {
      const b = document.querySelector('#btn-agent');
      if (b) b.click();
    }
    return true;
  })()`);
  await sleep(600);

  const g0 = await cdp.evalJS(GEOM_JS);
  rec("G0-dock-present", !!g0.dock, g0);

  // ── A1/A2：宽屏 1920，请求 50rem（> 旧上限 34rem）──
  await setViewport(cdp, 1920, 1080);
  const mode = await cdp.evalJS(SET_WIDTH_JS(50));
  await sleep(600);
  const g1 = await cdp.evalJS(GEOM_JS);
  rec("A1-wide-exceeds-34rem", g1.dock > 34 * g1.rem, {
    gotPx: g1.dock, gotRem: +(g1.dock / g1.rem).toFixed(2),
    oldCapPx: Math.round(34 * g1.rem), mode,
    maxWidth: g1.dockMaxWidth, win: g1.win,
  });
  rec("A2-content-kept-360", g1.content != null && g1.content >= 360, {
    content: g1.content, main: g1.main, sidebar: g1.sidebar,
  });

  // ── A3：1280 窄屏 + 请求 60rem（远超可用）⇒ 被 available 钳住 ──
  await cdp.evalJS(SET_WIDTH_JS(60));
  await sleep(200);
  await setViewport(cdp, 1280, 800);
  const g3 = await cdp.evalJS(GEOM_JS);
  rec("A3-narrow-capped-by-available", g3.content != null && g3.content >= 360 && g3.dock <= g3.main, {
    dock: g3.dock, content: g3.content, main: g3.main, win: g3.win,
  });

  // ── A4：极窄 900 ⇒ 自动隐藏或缩到最小，不溢出 ──
  await setViewport(cdp, 900, 700);
  const g4 = await cdp.evalJS(GEOM_JS);
  const okA4 =
    g4.dockAutoHidden || g4.dockCollapsed || g4.dock <= 0 ||
    (g4.content != null && g4.content >= 360);
  rec("A4-very-narrow-safe", okA4, {
    dock: g4.dock, collapsed: g4.dockCollapsed, autoHidden: g4.dockAutoHidden,
    content: g4.content, main: g4.main, win: g4.win,
  });

  // ── A5：回宽屏 ⇒ 期望宽恢复 ──
  await setViewport(cdp, 1920, 1080);
  await sleep(600);
  const g5 = await cdp.evalJS(GEOM_JS);
  rec("A5-restored-after-resize", g5.dock > 34 * g5.rem, {
    dock: g5.dock, gotRem: +(g5.dock / g5.rem).toFixed(2),
    content: g5.content, autoHidden: g5.dockAutoHidden,
  });

  return out;
}

/** 打印成可读报告 */
export function formatReport(out) {
  const lines = ["=== agent 会话栏宽度探针 ==="];
  for (const c of out.checks) {
    lines.push("  " + (c.pass ? "PASS" : "FAIL") + "  " + c.id);
    lines.push("        " + JSON.stringify(c.detail));
  }
  const fail = out.checks.filter((c) => !c.pass).length;
  lines.push("");
  lines.push(fail ? "FAIL " + fail + "/" + out.checks.length : "PASS " + out.checks.length + "/" + out.checks.length);
  return lines.join("\n");
}

// ── CLI 兼容入口（手工排查用；正常路径走 runner）──
const run = async () => {
  const url = process.argv[2] && process.argv[2].startsWith("http") ? process.argv[2] : "http://127.0.0.1:50486/";
  const { withBrowser } = await import("./interaction.mjs");
  let result = null;
  await withBrowser(url, async (cdp) => {
    result = await probeDockWidth(cdp);
  });
  if (!result) {
    console.error("探针未产出结果");
    process.exit(2);
  }
  if (process.argv.includes("--json")) console.log(JSON.stringify(result, null, 2));
  else console.log(formatReport(result));
  process.exit(result.ok ? 0 : 1);
};

import("node:url").then(({ pathToFileURL }) => {
  try {
    if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) run();
  } catch {
    /* 被 import 时不执行 */
  }
});
