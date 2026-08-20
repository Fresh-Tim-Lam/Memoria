// 笔刷覆盖复现 v7 — domToAst 元素边界诊断（只读）
// 验证假设：选区 start/end 落在 <span class=m0-hl> 元素节点时，domToAst 映射错乱

// ===PART1: 初始化 + 打开 + 切预览（实时获取引用，避免分离 DOM 问题）===
(async function () {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const out = { log: [] };
  if (window.MemoriaBridge && window.pywebview && window.pywebview.api) {
    window.MemoriaBridge.installApi(window.pywebview.api);
    out.log.push("api installed");
  } else {
    return { log: ["bridge missing"] };
  }
  for (let i = 0; i < 30; i++) {
    await sleep(400);
    if (document.querySelectorAll("#file-tree .m0-tree-item").length) break;
  }
  let opened = false;
  document.querySelectorAll("#file-tree .m0-tree-item").forEach((el) => {
    if (el.dataset.path === "brush-test.md") { el.click(); opened = true; }
  });
  out.log.push("open=" + opened);
  await sleep(1500);
  const vb = document.querySelector('.m0-view-btn[data-view="preview"]');
  if (vb) { vb.click(); out.log.push("view=preview"); }
  await sleep(1500);
  const preview = document.getElementById("preview");
  out.log.push("preview connected=" + (preview ? preview.isConnected : false) + " head=" + (preview ? JSON.stringify(preview.textContent.slice(0, 50)) : "NO"));
  return out;
})()
// ===PART1END===

// ===PART2: 文本节点清单 + domToAst 元素边界诊断===
(async function () {
  const out = {};
  const preview = document.getElementById("preview");
  if (!preview || !preview.isConnected) return { fatal: "preview not connected" };
  const M = window.MemoriaMapper;

  function findText(needle) {
    const p = document.getElementById("preview");
    const w = document.createTreeWalker(p, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = w.nextNode())) {
      const i = n.data.indexOf(needle);
      if (i >= 0) return { node: n, idx: i };
    }
    return null;
  }
  function findHlSpan(needle) {
    const t = findText(needle);
    if (!t) return null;
    let el = t.node.parentElement;
    while (el && el !== document.getElementById("preview")) {
      if (el.classList && el.classList.contains("m0-hl")) return el;
      el = el.parentElement;
    }
    return null;
  }

  // 1) 所有文本节点
  out.textNodes = [];
  const w = document.createTreeWalker(preview, NodeFilter.SHOW_TEXT);
  let n; let i = 0;
  while ((n = w.nextNode())) {
    out.textNodes.push({
      i: i,
      data: n.data,
      parentTag: n.parentElement ? n.parentElement.tagName : "",
      parentClass: n.parentElement ? n.parentElement.className : "",
    });
    i++;
  }

  // 2) 所有 .m0-hl span
  out.hlSpans = [];
  preview.querySelectorAll(".m0-hl").forEach((el, k) => {
    out.hlSpans.push({ k: k, cls: el.className, childCount: el.childNodes.length, text: el.textContent });
  });

  // 3) S4 行各形态 domToAst
  const tNorm = findText("普通");
  const tHl = findText("高亮");
  const tS4b = findText("S4B");
  const span4 = findHlSpan("高亮");
  out.s4 = {
    tNorm: tNorm ? { data: tNorm.node.data, idx: tNorm.idx } : null,
    tHl: tHl ? { data: tHl.node.data, idx: tHl.idx } : null,
    tS4b: tS4b ? { data: tS4b.node.data, idx: tS4b.idx } : null,
    span4: span4 ? { childCount: span4.childNodes.length, text: span4.textContent } : null,
  };
  out.domToAst = {};
  if (tNorm) out.domToAst.text_normal = M.domToAst(tNorm.node, tNorm.idx);
  if (span4) {
    out.domToAst.span_offset0 = M.domToAst(span4, 0);
    out.domToAst.span_offsetEnd = M.domToAst(span4, span4.childNodes.length);
  }
  if (tHl) out.domToAst.text_highlight = M.domToAst(tHl.node, tHl.idx);
  if (tS4b) out.domToAst.text_s4b = M.domToAst(tS4b.node, tS4b.idx);

  // 4) 整块参考：S4 所在 block 的文本总长（对比 span_offsetEnd 是否被错映射到整块末尾）
  const s4line = document.querySelector("#editor .m0-line-content");
  out.sourceS4Line = s4line ? s4line.textContent : null;

  return out;
})()
// ===PART2END===
