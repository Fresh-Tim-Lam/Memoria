// 笔刷覆盖复现测试 v2 — 浏览器 evaluate 脚本
// 分两段执行：
//   PART1: 初始化桥 + 等待文件树 + 打开 brush-test.md + 切预览视图 + 等渲染
//   PART2: 各场景构造选区 + applyStyle(highlight, yellow, range, force=true) + 读取源码结果
// 关键用例：
//   S1   纯高亮换色（text 节点内选区）
//   S2   双色荧光笔换色（text 节点内选区）
//   S4a  跨样式边界（start=普通文本 text，end=高亮 text 尾部）→ 期望成功
//   S4b  跨样式边界（end=高亮 span 元素边界 offset=0）→ 验证 domToAst 元素节点缺陷
//   S4c  跨样式边界（start=高亮 span 元素边界 offset=0）→ 验证 domToAst 元素节点缺陷
//   S8   混合嵌套（高亮内粗体+字体色）整段换色
//   S9   真实点击链路（选中文本 → mousedown+click 黄色色块 → applyFormat 路径）

// ===PART1===
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
  for (let i = 0; i < 20; i++) {
    await sleep(500);
    if (document.querySelectorAll("#file-tree .m0-tree-item").length) break;
  }
  const items = document.querySelectorAll("#file-tree .m0-tree-item");
  out.log.push("tree items=" + items.length);
  let opened = false;
  items.forEach((el) => {
    if (el.dataset.path === "brush-test.md") { el.click(); opened = true; }
  });
  out.log.push("open brush-test.md=" + opened);
  await sleep(1200);
  const vb = document.querySelector('.m0-view-btn[data-view="preview"]');
  if (vb) { vb.click(); out.log.push("view=preview"); }
  await sleep(1500);
  const preview = document.getElementById("preview");
  out.log.push("preview head=" + (preview ? JSON.stringify(preview.textContent.slice(0, 60)) : "NO-PREVIEW"));
  return out;
})()
// ===PART1END===

// ===PART2===
(async function () {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const out = {};
  const ES = window.MemoriaEditSync;
  const preview = document.getElementById("preview");
  const sel = window.getSelection();
  if (!ES || typeof ES.applyStyle !== "function") return { fatal: "MemoriaEditSync.applyStyle missing" };

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
    // 找 needle 所在 text 节点的最近 .m0-hl span 祖先
    const t = findText(needle);
    if (!t) return null;
    let el = t.node.parentElement;
    while (el && el !== preview) {
      if (el.classList && el.classList.contains("m0-hl")) return el;
      el = el.parentElement;
    }
    return null;
  }
  function selRange(s, e) {
    const r = document.createRange();
    r.setStart(s.node, s.idx);
    r.setEnd(e.node, e.idx);
    sel.removeAllRanges();
    sel.addRange(r);
    return sel.getRangeAt(0);
  }
  function selRangeNode(sNode, sIdx, eNode, eIdx) {
    const r = document.createRange();
    r.setStart(sNode, sIdx);
    r.setEnd(eNode, eIdx);
    sel.removeAllRanges();
    sel.addRange(r);
    return sel.getRangeAt(0);
  }
  function srcLines() {
    return Array.from(document.querySelectorAll("#editor .m0-line-content")).map((el) => el.textContent);
  }
  async function run(name, range) {
    let res;
    try {
      res = ES.applyStyle("highlight", "yellow", range, true);
    } catch (e) {
      res = { ok: false, error: String((e && e.stack) || e) };
    }
    await sleep(250);
    out[name] = { res, lines: srcLines() };
  }
  function miss(name, info) { out[name] = { error: "not found: " + info }; }

  // S1
  const s1 = findText("绿高亮");
  if (s1) await run("S1", selRange({ node: s1.node, idx: s1.idx }, { node: s1.node, idx: s1.idx + 3 })); else miss("S1", "绿高亮");

  // S2
  const s2 = findText("绿底灰字");
  if (s2) await run("S2", selRange({ node: s2.node, idx: s2.idx }, { node: s2.node, idx: s2.idx + 4 })); else miss("S2", "绿底灰字");

  // S4a 跨样式边界（end 为高亮 text 尾部）：start=普通text 的"普通" → end="高亮"text 尾部
  const t4a = findText("普通");
  const t4b = findText("高亮");
  if (t4a && t4b) await run("S4a", selRangeNode(t4a.node, t4a.idx, t4b.node, t4b.idx + 2)); else miss("S4a", "普通/高亮 text");

  // S4b end 为高亮 span 元素边界（offset=0）
  const s4bSpan = findHlSpan("高亮");
  if (t4a && s4bSpan) await run("S4b", selRangeNode(t4a.node, t4a.idx, s4bSpan, 0)); else miss("S4b", "span");

  // S4c start 为高亮 span 元素边界（offset=0），end=高亮 text 尾部
  const s4cSpan = findHlSpan("高亮");
  const t4c = findText("高亮");
  if (s4cSpan && t4c) await run("S4c", selRangeNode(s4cSpan, 0, t4c.node, t4c.idx + 2)); else miss("S4c", "span");

  // S8 混合嵌套整段换色：start=加粗text → end=S8B 前
  const s8a = findText("加粗");
  const s8b = findText("S8B");
  if (s8a && s8b) await run("S8", selRangeNode(s8a.node, s8a.idx, s8b.node, 0)); else miss("S8", "加粗/S8B");

  // S9 真实点击链路：选中"绿高亮九" → mousedown+click 黄色色块
  const s9t = findText("绿高亮九");
  if (s9t) {
    const r = document.createRange();
    r.setStart(s9t.node, s9t.idx);
    r.setEnd(s9t.node, s9t.idx + 4);
    sel.removeAllRanges();
    sel.addRange(r);
    // 展开 H 下拉
    const hlBtn = document.querySelector('.m0-fmt-btn[data-fmt="highlight"]');
    if (hlBtn) hlBtn.click();
    await sleep(150);
    const yellow = document.querySelector('.m0-hl-swatch[data-hl-color="yellow"]');
    if (yellow) {
      yellow.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, button: 0 }));
      await sleep(60);
      yellow.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }));
      await sleep(300);
      out.S9 = { lines: srcLines() };
    } else {
      out.S9 = { error: "yellow swatch missing" };
    }
  } else {
    out.S9 = { error: "绿高亮九 not found" };
  }

  return out;
})()
// ===PART2END===
