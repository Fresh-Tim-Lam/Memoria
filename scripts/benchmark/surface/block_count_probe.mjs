/**
 * block_count_probe.mjs —— 验证「`-src-block` 数量 == AST 块数」（0.4.7 任务 4 修补验证）
 *
 * 背景：`render-core.js` 的 `_newBlockEl()` 恒加 `-src-block` + `data--block-index`。
 * 我在 N3（`2eef3e34`）给嵌套 `<ul>` 也调了它 ⇒ 内层子列表被当成独立块：
 *   · `querySelectorAll('#preview .-src-block').length` 虚高
 *   · `querySelector('.-src-block[data--block-index=N]')` 命中内层 ul 而非块根
 *     ⇒ `mapper.astToDom()` 光标恢复落错层级
 *
 * 断言：
 *   B1 `#preview .-src-block` 数量 == `state.doc.blocks.length`
 *   B2 每个 `data--block-index` 在预览区**唯一**（不重复）
 *   B3 `data--block-index` 集合 == `[0, blocks.length)`（无缺号）
 *   B4 嵌套 `<ul>` 存在且**不带** `-src-block`
 */

const BLOCK_JS = `(() => {
  const els = Array.prototype.slice.call(document.querySelectorAll("#preview .-src-block"));
  const idx = els.map((e) => {
    const v = e.getAttribute("data--block-index");
    return v === null ? null : parseInt(v, 10);
  });
  // 块数组可能在多个位置：state.doc.blocks / MemoriaMapper.getDoc().blocks / state.ast.blocks
  let blocks = [];
  let src = "none";
  try {
    if (window.state && state.doc && Array.isArray(state.doc.blocks)) { blocks = state.doc.blocks; src = "state.doc.blocks"; }
    else if (window.MemoriaMapper && typeof window.MemoriaMapper.getDoc === "function") {
      const d = window.MemoriaMapper.getDoc();
      if (d && Array.isArray(d.blocks)) { blocks = d.blocks; src = "Mapper.getDoc().blocks"; }
    }
    if (!blocks.length && window.MemoriaAST && typeof window.MemoriaParser === "function" && window.state && state.doc && typeof state.doc.body === "string") {
      const d2 = window.MemoriaParser.parse(state.doc.body);
      if (d2 && Array.isArray(d2.blocks)) { blocks = d2.blocks; src = "parse(state.doc.body)"; }
    }
  } catch (e) { src = "err:" + e.message; }
  const ents = blocks.map((b, i) => ({ i: i, t: b ? b.type : null }));
  // 嵌套列表（depth>0）
  const nested = Array.prototype.slice.call(document.querySelectorAll("#preview .-list--nested"));
  const nestedWithSrc = nested.filter((e) => e.classList.contains("-src-block")).length;
  return {
    domCount: els.length,
    astCount: blocks.length,
    idx: idx,
    dupIdx: idx.filter((v, i) => v !== null && idx.indexOf(v) !== i),
    missing: (() => {
      const out = [];
      for (let i = 0; i < blocks.length; i++) if (idx.indexOf(i) < 0) out.push(i);
      return out;
    })(),
    outOfRange: idx.filter((v) => v !== null && (v < 0 || v >= blocks.length)),
    nullIdx: idx.filter((v) => v === null).length,
    nestedCount: nested.length,
    nestedWithSrcBlockClass: nestedWithSrc,
    types: ents.slice(0, 12),
    blocksSource: src,
  };
})()`;

export async function probeBlockCount(cdp, fixturePath) {
  const out = { checks: [], ok: true };
  const rec = (id, pass, detail) => {
    out.checks.push({ id, pass, detail });
    if (!pass) out.ok = false;
  };

  // 打开夹具（真实入口）
  const setup = await cdp.evalJS(`(async () => {
    if (!window.MemoriaApp || typeof window.MemoriaApp.openFile !== "function") return "no-openFile";
    try { await window.MemoriaApp.openFile(${JSON.stringify(fixturePath)}, {}); return "opened"; }
    catch (e) { return "err:" + e.message; }
  })()`);
  // 确保预览视图（openFile 可能被"按文件视图偏好"复位成 source）
  await cdp.evalJS(`(() => {
    if (window.state && state.viewMode !== "preview") {
      const b = document.querySelector('#btn-view-preview, [data-view="preview"]');
      if (b) b.click();
    }
    return true;
  })()`);

  let ready = false;
  for (let i = 0; i < 40; i++) {
    const n = await cdp.evalJS(`(document.querySelectorAll("#preview .-src-block")||[]).length`);
    if (n > 0) { ready = true; break; }
    await new Promise((r) => setTimeout(r, 300));
  }
  if (!ready) {
    rec("B0-ready", false, { setup });
    out.ok = false;
    return out;
  }
  rec("B0-ready", true, { setup });

  const d = await cdp.evalJS(BLOCK_JS);

  rec("B1-dom-count-eq-ast-count", d.domCount === d.astCount, {
    domCount: d.domCount, astCount: d.astCount, diff: d.domCount - d.astCount,
  });
  rec("B2-block-index-unique", d.dupIdx.length === 0, { dupIdx: d.dupIdx });
  rec("B3-block-index-complete", d.missing.length === 0 && d.outOfRange.length === 0 && d.nullIdx === 0, {
    missing: d.missing, outOfRange: d.outOfRange, nullIdx: d.nullIdx,
  });
  rec("B4-nested-not-self-block", d.nestedCount > 0 && d.nestedWithSrcBlockClass === 0, {
    nestedCount: d.nestedCount, nestedWithSrcBlockClass: d.nestedWithSrcBlockClass,
  });

  out.raw = d;
  return out;
}

export function formatReport(out) {
  const lines = ["=== -src-block 计数探针 ==="];
  for (const c of out.checks) {
    lines.push("  " + (c.pass ? "PASS" : "FAIL") + "  " + c.id + "  " + JSON.stringify(c.detail));
  }
  const fail = out.checks.filter((c) => !c.pass).length;
  lines.push("");
  lines.push(fail ? "FAIL " + fail + "/" + out.checks.length : "PASS " + out.checks.length + "/" + out.checks.length);
  return lines.join("\n");
}
