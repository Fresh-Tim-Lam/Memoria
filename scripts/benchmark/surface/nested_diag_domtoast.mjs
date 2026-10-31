/**
 * nested_diag_domtoast.mjs —— **只读诊断**：mapper.domToAst 对每个 <li> 的返回值（task-80）
 *
 * ⚠️ 本构建的 DOM 真实结构（已实测，见 nested_diag_domshape.mjs）：
 *    <UL class="-src-block" data--block-index=6>
 *      <LI>"第一项"
 *        <UL class="-src-block -list--nested">      ← 内层也带 -src-block
 *          <LI>"子项 A"
 *          <LI>"子项 B"
 *      <LI>"第二项"
 *
 *   ⇒ `document.querySelectorAll('#preview .-src-block')` **会**同时命中内外两层。
 *   ⇒ `blockEl.querySelectorAll('li')` 在父层算出的扁平索引**包含子项**，
 *      而 `block.items` 只有顶层项 ⇒ `itemIndex >= block.items.length` ⇒ 直接 bail。
 *
 * 本诊断对**每个** -src-block 元素（含内层）生成一行表：
 *   外层块索引 / 扁平 li 索引（元素自身 querySelectorAll 序）/ 直属文本 / 真实树路径 / domToAst 返回
 */
function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

const ROW_JS = (blockIdx, flatIdx) => `(() => {
  const all = Array.from(document.querySelectorAll('#preview .-src-block'));
  const b = all[${blockIdx}];
  if (!b) return { err: 'no-block' };
  const lis = Array.from(b.querySelectorAll('li'));
  const li = lis[${flatIdx}];
  if (!li) return { err: 'no-li', count: lis.length };

  // 该 li 自己的直属文本（排除子列表）
  let own = '';
  for (const cn of li.childNodes) if (cn.nodeType === 3) own += cn.nodeValue;
  if (!own.trim()) {
    // 常见情况：文本在 <strong>/<em>/<span> 等行内元素里
    for (const cn of li.childNodes) {
      if (cn.nodeType === 1 && cn.tagName !== 'UL' && cn.tagName !== 'OL') own += cn.textContent;
    }
  }
  own = own.trim();

  // 真实树路径：从本 li 起向上走「列表→父LI」链，逐级 unshift 各自在同级中的下标
  const path = [];
  let cur = li;
  while (cur && cur.tagName === 'LI') {
    const parentList = cur.parentElement;
    if (!parentList) break;
    const sibs = Array.from(parentList.children).filter((x) => x.tagName === 'LI');
    path.unshift(sibs.indexOf(cur));
    // 跳过列表本身，看它的父节点是不是 <li>
    cur = parentList.parentElement;
  }

  // 取该 li 的首个非空直属文本节点（不在嵌套 UL/OL 内）
  let tn = null;
  const walker = document.createTreeWalker(li, NodeFilter.SHOW_TEXT, {
    acceptNode(n) {
      let p = n.parentElement;
      while (p && p !== li) {
        if (p.tagName === 'UL' || p.tagName === 'OL') return NodeFilter.FILTER_REJECT;
        p = p.parentElement;
      }
      return (n.nodeValue && n.nodeValue.trim()) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
    }
  });
  while (walker.nextNode()) { tn = walker.currentNode; break; }

  const M = window.MemoriaMapper;
  let ret = null, err = null;
  if (!tn) { err = 'no-direct-text'; }
  else if (!M || typeof M.domToAst !== 'function') { err = 'no-mapper'; }
  else { try { ret = M.domToAst(tn, 0); } catch (ex) { err = String((ex && ex.message) || ex); } }

  const bi = parseInt(b.getAttribute('data--block-index'), 10);
  const doc = M && M._currentDoc;
  const blk = doc && doc.blocks && doc.blocks[bi];
  return {
    text: own.slice(0, 10),
    path,
    ret, err,
    isNested: (b.className || '').indexOf('-list--nested') >= 0,
    topItemsLen: (blk && blk.items) ? blk.items.length : null,
    lisInThisEl: lis.length,
  };
})()`;

export async function diagDomToAst(cdp) {
  const out = { blocks: [], ok: true, err: null };

  await cdp.evalJS(`(async () => {
    try { await window.MemoriaApp.openFile("nested-list-fixture.md", {}); return "opened"; }
    catch (e) { return "err:" + e.message; }
  })()`);
  await cdp.evalJS(`(() => {
    const btn = document.querySelector('#btn-view-preview, [data-view="preview"]');
    if (btn) { btn.click(); return "clicked"; }
    if (window.MemoriaApp && window.MemoriaApp.setViewMode) { window.MemoriaApp.setViewMode("preview"); return "svm"; }
    return "noop";
  })()`);
  await sleep(500);
  for (let i = 0; i < 40; i++) {
    const n = await cdp.evalJS(`(document.querySelectorAll("#preview .-src-block")||[]).length`);
    if (n > 0) break;
    await sleep(300);
  }
  await sleep(400);

  // 枚举所有含 li 的 -src-block 元素（包括内层嵌套的）
  const els = await cdp.evalJS(`(() => {
    const all = Array.from(document.querySelectorAll('#preview .-src-block'));
    const r = [];
    all.forEach((b, i) => {
      const n = b.querySelectorAll('li').length;
      if (!n) return;
      let ownTop = '';
      for (const cn of b.childNodes) if (cn.nodeType === 3) ownTop += cn.nodeValue;
      r.push({
        idx: i, tag: b.tagName, liCount: n,
        cls: b.className,
        bi: b.getAttribute('data--block-index'),
        depth: b.getAttribute('data--list-depth'),
        nestedDepth: (b.className || '').indexOf('-list--nested') >= 0 ? 'nested' : 'top',
      });
    });
    return r;
  })()`);

  for (const el of els) {
    const rows = [];
    for (let fi = 0; fi < el.liCount; fi++) {
      const row = await cdp.evalJS(ROW_JS(el.idx, fi));
      rows.push(Object.assign({ flatIdx: fi }, row));
    }
    out.blocks.push(Object.assign({}, el, { rows }));
  }
  return out;
}

export function formatDiag(out) {
  const lines = [];
  for (const b of out.blocks) {
    lines.push(`\n### .-src-block[#${b.idx}] <${b.tag}> bi=${b.bi} depth=${b.depth} ${b.nestedDepth} (${b.liCount} li)`);
    lines.push("| flat | 文本 | 树路径 | domToAst.blockIndex | listItemIndex | nodePath | topItemsLen |");
    lines.push("|---|---|---|---|---|---|---|");
    for (const r of b.rows) {
      const ret = r.ret || {};
      lines.push(
        `| ${r.flatIdx} | ${r.text || "?"} | [${(r.path || []).join(",")}] | ` +
        `${ret.blockIndex === undefined ? "—" : ret.blockIndex} | ` +
        `${ret.listItemIndex === undefined ? "(none)" : ret.listItemIndex} | ` +
        `[${(ret.nodePath || []).join(",")}] | ${r.topItemsLen} |`
      );
    }
  }
  return lines.join("\n");
}
