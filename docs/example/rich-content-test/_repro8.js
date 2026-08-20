// 笔刷覆盖复现 v9 — 修正 span 定位（按段落前缀判断）

// ===PART1: 初始化 + 打开 + 切预览===
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
  out.log.push("preview=" + (preview && preview.isConnected ? "ok" : "NO"));
  return out;
})()
// ===PART1END===

// ===PART2: T3 行 domToAst 元素边界诊断（只读）===
(async function () {
  const out = {};
  const M = window.MemoriaMapper;
  const preview = document.getElementById("preview");
  if (!preview) return { fatal: "no preview" };

  function hlSpanOf(textNode) {
    let el = textNode.parentElement;
    while (el && el !== preview) {
      if (el.classList && el.classList.contains("m0-hl")) return el;
      el = el.parentElement;
    }
    return null;
  }
  function paraSpan(prefix) {
    const w = document.createTreeWalker(preview, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = w.nextNode())) {
      if (n.data.indexOf("高亮") >= 0) {
        const sp = hlSpanOf(n);
        if (!sp) continue;
        let b = sp.parentElement;
        while (b && b !== preview && !(b.classList && b.classList.contains("m0-src-block"))) b = b.parentElement;
        if (b && b.textContent.startsWith(prefix)) return { span: sp, blockEl: b };
      }
    }
    return null;
  }
  function paraText(prefix) {
    const w = document.createTreeWalker(preview, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = w.nextNode())) {
      if (n.data.startsWith(prefix)) return n;
    }
    return null;
  }

  const t3a = paraText("T3A");
  const ps = paraSpan("T3A");
  if (!t3a) return { fatal: "T3A text not found" };
  if (!ps) return { fatal: "T3 span not found" };
  const { span, blockEl } = ps;
  out.t3 = {
    t3aData: t3a.data,
    spanChildCount: span.childNodes.length,
    spanText: span.textContent,
    blockText: blockEl.textContent,
    blockTotalLen: blockEl.textContent.length,
  };
  out.domToAst = {
    text_normal: M.domToAst(t3a, t3a.data.indexOf("普通") + 1),
    span_offset0: M.domToAst(span, 0),
    span_offsetEnd: M.domToAst(span, span.childNodes.length),
  };
  return out;
})()
// ===PART2END===

// ===PART3: 元素边界选区 → 应用黄色高亮===
(async function () {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const out = {};
  const sel = window.getSelection();
  const ES = window.MemoriaEditSync;
  const preview = document.getElementById("preview");

  function hlSpanOf(textNode) {
    const p = document.getElementById("preview");
    let el = textNode.parentElement;
    while (el && el !== p) {
      if (el.classList && el.classList.contains("m0-hl")) return el;
      el = el.parentElement;
    }
    return null;
  }
  function paraText(prefix) {
    const p = document.getElementById("preview");
    const w = document.createTreeWalker(p, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = w.nextNode())) {
      if (n.data.startsWith(prefix)) return n;
    }
    return null;
  }
  function paraSpan(prefix) {
    const p = document.getElementById("preview");
    const w = document.createTreeWalker(p, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = w.nextNode())) {
      if (n.data.indexOf("高亮") >= 0) {
        const sp = hlSpanOf(n);
        if (!sp) continue;
        let b = sp.parentElement;
        while (b && b !== p && !(b.classList && b.classList.contains("m0-src-block"))) b = b.parentElement;
        if (b && b.textContent.startsWith(prefix)) return { span: sp };
      }
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
  async function clickYellow() {
    const hlBtn = document.querySelector('.m0-fmt-btn[data-fmt="highlight"]');
    if (!hlBtn) return "no-hl-btn";
    hlBtn.click();
    await sleep(120);
    const yellow = document.querySelector('.m0-hl-swatch[data-hl-color="yellow"]');
    if (!yellow) return "no-yellow";
    yellow.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, button: 0 }));
    await sleep(50);
    yellow.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }));
    await sleep(300);
    return "clicked";
  }
  function grab(prefix) {
    return srcLines().filter((l) => l.startsWith(prefix)).join("\n");
  }

  // A: T2 行 end=span 元素边界 → 点击色块
  {
    const ta = paraText("T2A");
    const ps = paraSpan("T2A");
    if (ta && ps) {
      const before = grab("T2A");
      setSel(ta, ta.data.indexOf("普通") + 2, ps.span, ps.span.childNodes.length);
      const clickRet = await clickYellow();
      out.T2_click = { clickRet, before: before, after: grab("T2A") };
    } else {
      out.T2_click = { error: "not found ta=" + !!ta + " span=" + !!ps };
    }
  }

  // B: T3 行 start=span 元素边界 offset=0 → 点击色块（核心：颜色完全没变？）
  {
    const t3b = paraText("T3B");
    const ps = paraSpan("T3A");
    if (t3b && ps) {
      const before = grab("T3A");
      setSel(ps.span, 0, t3b, t3b.data.length);
      const clickRet = await clickYellow();
      out.T3_click = { clickRet, before: before, after: grab("T3A") };
    } else {
      out.T3_click = { error: "not found t3b=" + !!t3b + " span=" + !!ps };
    }
  }

  // C: T4 行 直接 applyStyle（画笔内部同逻辑），start=text 中段 → end=span 元素边界
  {
    const t4a = paraText("T4A");
    const ps = paraSpan("T4A");
    if (t4a && ps) {
      const before = grab("T4A");
      const r = setSel(t4a, t4a.data.indexOf("普通") + 2, ps.span, ps.span.childNodes.length);
      const ret = ES.applyStyle("highlight", "yellow", r, true);
      await sleep(250);
      out.T4_applyStyle = { ret: ret, before: before, after: grab("T4A") };
    } else {
      out.T4_applyStyle = { error: "not found t4a=" + !!t4a + " span=" + !!ps };
    }
  }

  // D: T5 行 画笔涂抹：armBrush → 构造元素边界选区 → dispatch mouseup
  {
    sel.removeAllRanges();
    await sleep(100);
    const hlBtn = document.querySelector('.m0-fmt-btn[data-fmt="highlight"]');
    if (hlBtn) hlBtn.click();
    await sleep(120);
    const yellow = document.querySelector('.m0-hl-swatch[data-hl-color="yellow"]');
    if (yellow) yellow.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }));
    await sleep(150);
    const armed = document.body.classList.contains("m0-brush-active");
    const t5a = paraText("T5A");
    const ps = paraSpan("T5A");
    if (armed && t5a && ps) {
      const before = grab("T5A");
      setSel(t5a, t5a.data.indexOf("普通") + 2, ps.span, ps.span.childNodes.length);
      document.getElementById("preview").dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true, button: 0 }));
      await sleep(300);
      out.T5_brush = { armed: armed, before: before, after: grab("T5A") };
    } else {
      out.T5_brush = { error: "armed=" + armed + " t5a=" + !!t5a + " span=" + !!ps };
    }
  }

  return out;
})()
// ===PART3END===
