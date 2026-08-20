// 笔刷覆盖复现 v6 — 元素边界选区 + 真实点击色块路径
// 目标：复现"颜色完全没变"（同类型样式覆盖失败）
// 关键：真实鼠标拖动跨出样式容器时，选区边界落在 <span class=m0-hl> 元素节点上（offset=0 或 子节点数），
//       domToAst 只匹配文本节点 → renderedOffset 错乱 → 映射到错误位置

// ===PART1: 初始化 + 打开 brush-test.md + 切预览视图===
(async function () {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const out = { log: [] };
  if (window.MemoriaBridge && window.pywebview && window.pywebview.api) {
    window.MemoriaBridge.installApi(window.pywebview.api);
    out.log.push("api installed");
  } else {
    out.log.push("bridge missing bridge=" + !!window.MemoriaBridge + " pywebview=" + !!window.pywebview);
    return out;
  }
  for (let i = 0; i < 30; i++) {
    await sleep(400);
    if (document.querySelectorAll("#file-tree .m0-tree-item").length) break;
  }
  const items = document.querySelectorAll("#file-tree .m0-tree-item");
  out.log.push("tree items=" + items.length);
  let opened = false;
  items.forEach((el) => {
    if (el.dataset.path === "brush-test.md") { el.click(); opened = true; }
  });
  out.log.push("open brush-test.md=" + opened);
  await sleep(1500);
  const vb = document.querySelector('.m0-view-btn[data-view="preview"]');
  if (vb) { vb.click(); out.log.push("view=preview"); }
  await sleep(1500);
  const preview = document.getElementById("preview");
  out.log.push("preview head=" + (preview ? JSON.stringify(preview.textContent.slice(0, 60)) : "NO-PREVIEW"));
  const es = window.MemoriaEditSync;
  out.log.push("MemoriaEditSync=" + (es ? "yes" : "NO"));
  return out;
})()
// ===PART1END===

// ===PART2: 元素边界选区 → 点击黄色色块 → 检查源码颜色===
(async function () {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const out = {};
  const sel = window.getSelection();
  const preview = document.getElementById("preview");

  function findText(needle) {
    const w = document.createTreeWalker(preview, NodeFilter.SHOW_TEXT);
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
    while (el && el !== preview) {
      if (el.classList && el.classList.contains("m0-hl")) return el;
      el = el.parentElement;
    }
    return null;
  }
  function srcLines() {
    return Array.from(document.querySelectorAll("#editor .m0-line-content")).map((el) => el.textContent);
  }
  function setSel(sNode, sIdx, eNode, eIdx) {
    const r = document.createRange();
    r.setStart(sNode, sIdx);
    r.setEnd(eNode, eIdx);
    sel.removeAllRanges();
    sel.addRange(r);
    return r;
  }
  function descNode(n) {
    if (!n) return "null";
    if (n.nodeType === 3) return "#text:" + JSON.stringify(n.data.slice(0, 20));
    return "<" + (n.nodeName || "").toLowerCase() + ">";
  }
  async function clickYellow() {
    const hlBtn = document.querySelector('.m0-fmt-btn[data-fmt="highlight"]');
    if (!hlBtn) return "no-hl-btn";
    hlBtn.click();
    await sleep(120);
    const yellow = document.querySelector('.m0-hl-swatch[data-hl-color="yellow"]');
    if (!yellow) return "no-yellow-swatch";
    yellow.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, button: 0 }));
    await sleep(50);
    yellow.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }));
    await sleep(300);
    return "clicked";
  }
  async function scenario(name, s, e, clickPath) {
    const lines0 = srcLines();
    const r = setSel(s.node, s.idx, e.node, e.idx);
    let info;
    if (clickPath) {
      info = { via: "click", ret: await clickYellow() };
    } else {
      const ES = window.MemoriaEditSync;
      info = { via: "applyStyle", ret: ES.applyStyle("highlight", "yellow", r, true) };
      await sleep(250);
    }
    const lines1 = srcLines();
    out[name] = {
      sel: descNode(s.node) + ":" + s.idx + " -> " + descNode(e.node) + ":" + e.idx,
      info: info,
      before: lines0.filter((l) => /S1A|S4A|S8A|S9A/.test(l)).join("\n"),
      after: lines1.filter((l) => /S1A|S4A|S8A|S9A/.test(l)).join("\n"),
    };
  }
  function miss(name, what) { out[name] = { error: "not found: " + what }; }

  // SC1 基线：文本节点内选中"绿高亮" → 点击色块（应成功 green→yellow）
  const t1 = findText("绿高亮");
  if (t1) await scenario("SC1_text_inner", { node: t1.node, idx: t1.idx }, { node: t1.node, idx: t1.idx + 3 }, true);
  else miss("SC1_text_inner", "绿高亮");

  // SC2 元素边界 end：start=text("普通") → end=highlight span 元素 offset=子节点数
  const ta = findText("普通");
  const span4 = findHlSpan("高亮");
  if (ta && span4) await scenario("SC2_elemEnd", { node: ta.node, idx: ta.idx }, { node: span4, idx: span4.childNodes.length }, true);
  else miss("SC2_elemEnd", "普通/span");

  // SC3 元素边界 start：start=highlight span 元素 offset=0 → end=text("S4B")末尾
  const tb = findText("S4B");
  if (span4 && tb) await scenario("SC3_elemStart", { node: span4, idx: 0 }, { node: tb.node, idx: tb.idx + 3 }, true);
  else miss("SC3_elemStart", "span/S4B");

  // SC4 普通文本中间 → span 元素末尾（跨出样式边界尾部）
  if (ta && span4) await scenario("SC4_midToSpanEnd", { node: ta.node, idx: ta.idx + 2 }, { node: span4, idx: span4.childNodes.length }, true);
  else miss("SC4_midToSpanEnd", "普通/span");

  // SC5 混合嵌套 S8：start=highlight span 内 text("加粗") → end=highlight span 元素末尾
  const s8t = findText("加粗");
  const s8span = findHlSpan("加粗");
  if (s8t && s8span) await scenario("SC5_mixed", { node: s8t.node, idx: s8t.idx }, { node: s8span, idx: s8span.childNodes.length }, true);
  else miss("SC5_mixed", "加粗/span");

  // SC6 画笔涂抹路径：先点色块武装画笔（无选区）→ 构造元素边界选区 → dispatch mouseup
  {
    // 确保无选区
    sel.removeAllRanges();
    await sleep(100);
    const hlBtn = document.querySelector('.m0-fmt-btn[data-fmt="highlight"]');
    if (hlBtn) hlBtn.click();
    await sleep(120);
    const yellow = document.querySelector('.m0-hl-swatch[data-hl-color="yellow"]');
    if (yellow) yellow.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }));
    await sleep(150);
    const brushArmed = document.body.classList.contains("m0-brush-active");
    // 构造 SC2 同形态选区
    if (brushArmed && ta && span4) {
      const lines0 = srcLines();
      setSel(ta.node, ta.idx, span4, span4.childNodes.length);
      preview.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true, button: 0 }));
      await sleep(300);
      const lines1 = srcLines();
      out.SC6_brush = {
        armed: brushArmed,
        before: lines0.filter((l) => /S4A/.test(l)).join("\n"),
        after: lines1.filter((l) => /S4A/.test(l)).join("\n"),
      };
    } else {
      out.SC6_brush = { error: "brush not armed armed=" + brushArmed };
    }
  }

  return out;
})()
// ===PART2END===
