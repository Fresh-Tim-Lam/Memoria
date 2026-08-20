// 笔刷覆盖复现 v10 — 修复后回归：混合嵌套整段 + 跨样式边界

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

// ===PART2: S4 跨样式边界 + S8 混合嵌套整段（元素边界选区）→ 点击黄色色块===
(async function () {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const out = {};
  const sel = window.getSelection();
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
      if (n.data.indexOf("高亮") >= 0 || n.data.indexOf("加粗") >= 0 || n.data.indexOf("红字") >= 0) {
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

  // A: S4 跨样式边界 — start=text"普通"中段 → end=span 元素末尾（元素边界）
  {
    const ta = paraText("S4A");
    const ps = paraSpan("S4A");
    if (ta && ps) {
      const before = grab("S4A");
      setSel(ta, ta.data.indexOf("普通") + 1, ps.span, ps.span.childNodes.length);
      const clickRet = await clickYellow();
      out.S4_cross = { clickRet, before: before, after: grab("S4A") };
    } else {
      out.S4_cross = { error: "not found ta=" + !!ta + " span=" + !!ps };
    }
  }

  // B: S8 混合嵌套整段 — start=highlight 内 text"加粗" → end=span 元素末尾（元素边界）
  {
    const t8 = paraText("加粗");
    const ps = paraSpan("S8A");
    if (t8 && ps) {
      const before = grab("S8A");
      setSel(t8, t8.idx !== undefined ? t8.idx : 0, ps.span, ps.span.childNodes.length);
      const clickRet = await clickYellow();
      out.S8_mixed = { clickRet, before: before, after: grab("S8A") };
    } else {
      out.S8_mixed = { error: "not found t8=" + !!t8 + " span=" + !!ps };
    }
  }

  // C: S9 基线（文本节点内）→ 画笔涂抹
  {
    const t9 = paraText("S9A");
    const ps = paraSpan("S9A");
    if (t9 && ps) {
      const before = grab("S9A");
      // 画笔：先武装（无选区点黄色）
      sel.removeAllRanges();
      await sleep(80);
      const hlBtn = document.querySelector('.m0-fmt-btn[data-fmt="highlight"]');
      if (hlBtn) hlBtn.click();
      await sleep(100);
      const yellow = document.querySelector('.m0-hl-swatch[data-hl-color="yellow"]');
      if (yellow) yellow.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }));
      await sleep(120);
      const armed = document.body.classList.contains("m0-brush-active");
      // 选区：绿高亮九 文本内部（画笔真实拖动形态：start=text 中 → end=text 尾）
      const t9h = paraText("绿高亮九");
      if (armed && t9h) {
        setSel(t9h, 0, t9h, t9h.data.length);
        document.getElementById("preview").dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true, button: 0 }));
        await sleep(300);
        out.S9_brush = { armed: armed, before: before, after: grab("S9A") };
      } else {
        out.S9_brush = { error: "armed=" + armed + " t9h=" + !!t9h };
      }
    } else {
      out.S9_brush = { error: "not found t9/span" };
    }
  }

  return out;
})()
// ===PART2END===
