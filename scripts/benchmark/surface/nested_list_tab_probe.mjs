/**
 * nested_list_tab_probe.mjs —— Tab / Shift+Tab 真机行为探针（0.4.7 任务 4，N4 验证）
 *
 * 为什么单独写：本机 CDP `Input.dispatchKeyEvent` 对部分组合会卡死目标
 * （已确认 Ctrl+X 会让 target 永久无响应）。Tab 会触发焦点移动，需**先小步试探**，
 * 一旦某次 send 超时立刻标记 INFRA_BLOCKED 并**换新浏览器**继续，绝不静默挂死。
 *
 * 断言：
 *   T1 列表项内 Tab     ⇒ 该项降级（源码出现上一行有缩进、该项更深）
 *   T2 列表项内 Shift+Tab ⇒ 该项升级
 *   T3 普通段落内 Tab   ⇒ 插入 2 个空格（不移动焦点）
 *   T4 列表首项 Tab     ⇒ 无处降级 ⇒ 插空格（不崩）
 *
 * 用法（模块形态，由 run_nested_tab.py 用 withBrowser 调用）：
 *   import { probeNestedTab } from "./nested_list_tab_probe.mjs";
 *   const out = await probeNestedTab(cdp);
 */

const KEY_TIMEOUT_MS = 6000;

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/** 读当前文档源码（真实 state.doc.body） */
const BODY_JS = `(() => {
  try {
    const b = (window.state && state.doc && state.doc.body);
    return typeof b === "string" ? b : ("<NON-STRING:" + (b === null ? "null" : typeof b) + ">");
  } catch (e) { return "<ERR:" + e.message + ">"; }
})()`;

/** 读光标 AST 位置 */
const CURSOR_JS = `(() => {
  const EH = window.MemoriaEditHandler;
  const c = EH && EH.cursorAST;
  return c ? { blockIndex: c.blockIndex, nodePath: c.nodePath || [], offset: c.offset } : null;
})()`;

/**
 * 把光标放到「第 blockIndex 块内第 flatIdx 个 <li>」的首个文本位置。
 *
 * ★ 关键：**必须用真实鼠标点击**，不能只 setStart/addRange。
 *   原因：`EH.cursorAST` 只由产品自己的 click / arrow / beforeinput 处理器
 *   （内部私有 `syncFromSelection()`）填充；纯 Selection API 改选区**不会**触发它们 ⇒
 *   `getEditContext()` 返回 null ⇒ `indentListLevel` 一律返回 false（实测 cursorAST:null）。
 *   ⇒ 本函数返回该文本节点首字符的**屏幕坐标**，调用方用 `Input.dispatchMouseEvent` 点一下。
 */
function cursorPointJs(blockIndex, flatIdx) {
  return `(() => {
    const blocks = document.querySelectorAll('#preview .-src-block');
    const b = blocks[${blockIndex}];
    if (!b) return { err: 'no-block' };
    const lis = b.querySelectorAll('li');
    if (${flatIdx} >= lis.length) return { err: 'no-li', count: lis.length };
    const li = lis[${flatIdx}];
    // 用该 li 内**第一个文本节点**的起点矩形（比 getBoundingClientRect 整体更准，
    //   否则 ul 的 padding 会让点击落到父级 <li> 上）
    const w = document.createTreeWalker(li, NodeFilter.SHOW_TEXT, null);
    let n = null;
    while (w.nextNode()) { if (w.currentNode.nodeValue && w.currentNode.nodeValue.trim()) { n = w.currentNode; break; } }
    if (!n) return { err: 'no-text' };
    // ⚠️ 必须用**非折叠** Range：折叠（空）Range 的 getBoundingClientRect 在 Chromium 里
    //   可能返回全零矩形（实测 err:'zero-rect'）。取第 1 个字符的范围。
    const len = (n.nodeValue || '').length;
    const r = document.createRange();
    r.setStart(n, 0);
    r.setEnd(n, Math.max(1, Math.min(1, len)));
    let rect = r.getBoundingClientRect();
    if (!rect || !rect.width || !rect.height) rect = li.getBoundingClientRect();
    if (!rect || !rect.width || !rect.height) return { err: 'zero-rect', len: len };
    return {
      x: Math.round(rect.left + 1),
      y: Math.round(rect.top + rect.height / 2),
      wantText: (n.nodeValue || '').trim().slice(0, 8),
    };
  })()`;
}

/** 真实鼠标单击（左键按下+抬起）—— 让产品的 click 处理器同步 cursorAST */
async function clickAt(cdp, x, y) {
  await cdp.send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
  await cdp.send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
  await sleep(350);
}

async function sendKey(cdp, keyDef) {
  // 带超时：若 CDP 不回，判 INFRA_BLOCKED（不静默挂死）
  const to = (p) => Promise.race([p, sleep(KEY_TIMEOUT_MS).then(() => Promise.reject(new Error("CDP key timeout")))]);
  await to(cdp.send("Input.dispatchKeyEvent", { type: "rawKeyDown", ...keyDef }));
  await to(cdp.send("Input.dispatchKeyEvent", { type: "keyUp", ...keyDef }));
}

const TAB = { key: "Tab", code: "Tab", windowsVirtualKeyCode: 9, nativeVirtualKeyCode: 9 };
const SHIFT_TAB = { key: "Tab", code: "Tab", windowsVirtualKeyCode: 9, nativeVirtualKeyCode: 9, modifiers: 8 };

export async function probeNestedTab(cdp) {
  const out = { checks: [], ok: true, infraBlocked: false };
  const rec = (id, pass, detail) => {
    out.checks.push({ id, pass, detail });
    if (!pass) out.ok = false;
  };

  // ── 准备：用**真实入口** MemoriaApp.openFile 打开含多级列表的 fixture ──
  //   ⚠️ 不能直接改 state.doc：那样 _blockLineMap / _doc 等编辑管线未初始化，
  //      indentListLevel 会失败（实测 setupMode:"direct" 时 T1/T2 全不生效）。
  //   ⚠️ 也不要在页面里 await 轮询（evalJS 的 awaitPromise 会超时）——在 node 侧轮询。
  const setup = await cdp.evalJS(`(async () => {
    const path = "nested-list-fixture.md";
    if (!window.MemoriaApp || typeof window.MemoriaApp.openFile !== "function") return "no-openFile";
    try { await window.MemoriaApp.openFile(path, {}); return "opened"; }
    catch (e) { return "openFile-err:" + e.message; }
  })()`);
  // ★ 打开后视图可能被「按文件的视图偏好」复位成 source 模式
  //   ⇒ 必须确保在预览视图，否则 `#preview .-src-block` 永远为 0（实测踩过）。
  await cdp.evalJS(`(() => {
    const st = window.state;
    if (st && st.viewMode !== "preview") {
      const btn = document.querySelector('#btn-view-preview, [data-view="preview"]');
      if (btn) { btn.click(); return "clicked"; }
      if (window.MemoriaApp && typeof window.MemoriaApp.setViewMode === "function") {
        window.MemoriaApp.setViewMode("preview"); return "setViewMode";
      }
    }
    return "already";
  })()`);
  await sleep(500);

  // node 侧轮询就绪（最多 12s）
  let ready = false;
  for (let i = 0; i < 40; i++) {
    const n = await cdp.evalJS(`(document.querySelectorAll("#preview .-src-block")||[]).length`);
    const hasDoc = await cdp.evalJS(`!!(window.state && state.doc && state.doc.body)`);
    if (n > 0 && hasDoc) { ready = true; break; }
    await sleep(300);
  }
  if (!ready) {
    out.infraBlocked = true;
    out.reason = "文档未就绪（setup=" + setup + "）";
    rec("T0-setup", false, { setup });
    return out;
  }
  await sleep(600);

  const body0 = await cdp.evalJS(BODY_JS);
  rec("T0-setup", typeof body0 === "string" && body0.indexOf("第一项") >= 0, {
    setup: setup,
    body: typeof body0 === "string" ? body0.slice(0, 120) : String(body0),
  });
  if (typeof body0 !== "string" || body0.indexOf("第一项") < 0) {
    out.infraBlocked = true;
    out.reason = "文档内容不符合预期（setup=" + setup + "）";
    return out;
  }

  // ── T1：在「基本两级」列表的第 2 项（"子项 B"）上按 Tab ⇒ 应降级 ──
  //   注意：fixture 有多个块，先定位到那个 list 块
  const listBlockIdx = await cdp.evalJS(`(() => {
    const bs = document.querySelectorAll("#preview .-src-block");
    for (let i = 0; i < bs.length; i++) {
      if (bs[i].tagName === "UL" && (bs[i].textContent || "").indexOf("第一项") >= 0 &&
          bs[i].querySelectorAll("li li").length >= 2) return i;
    }
    return -1;
  })()`);
  rec("T0b-list-block-found", listBlockIdx >= 0, { listBlockIdx });
  if (listBlockIdx < 0) { out.infraBlocked = true; out.reason = "找不到目标列表块"; return out; }
  // 光标放在该列表里第 2 个**子项**（"子项 B"，扁平 li 顺序 = 第一项, 子项A, 子项B, 第二项）
  const pt1 = await cdp.evalJS(cursorPointJs(listBlockIdx, 2));
  if (pt1 && pt1.x != null) await clickAt(cdp, pt1.x, pt1.y);
  else { out.infraBlocked = true; out.reason = "光标定位失败: " + JSON.stringify(pt1); return out; }
  // 诊断：点击坐标附近到底是什么元素（决定 listItemIndex 的真相）
  const hitDiag = await cdp.evalJS(`(() => {
    const el = document.elementFromPoint(${pt1 && pt1.x != null ? pt1.x : 0}, ${pt1 && pt1.y != null ? pt1.y : 0});
    const li = el ? el.closest('li') : null;
    const allLis = Array.from(document.querySelectorAll('#preview .-src-block')[${listBlockIdx}].querySelectorAll('li'));
    return {
      tag: el ? el.tagName : null,
      liText: li ? (li.textContent || '').trim().slice(0, 10) : null,
      liIdxInAll: li ? allLis.indexOf(li) : -1,
      allLiTexts: allLis.map((x) => (x.textContent || '').trim().slice(0, 6)),
    };
  })()`);
  out.checks.push({ id: "DIAG-hit", pass: true, detail: hitDiag });

  // 点击后核对产品的 listItemIndex 是否就是我们点的那个 li
  const idxAfter1 = await cdp.evalJS(`window.MemoriaEditHandler ? window.MemoriaEditHandler.listItemIndex : null`);
  rec("T0c-click-lands-on-target", idxAfter1 === 2, { listItemIndex: idxAfter1, want: 2, point: pt1 });
  try {
    await sendKey(cdp, TAB);
  } catch (e) {
    out.infraBlocked = true;
    out.reason = "Tab 键导致 CDP 超时：" + String((e && e.message) || e);
    rec("T1-list-tab-indent", false, { infra: "CDP blocked" });
    return out;
  }
  await sleep(900);
  const body1 = await cdp.evalJS(BODY_JS);
  // 诊断：直接调 indentListLevel 看返回值与上下文
  const diag = await cdp.evalJS(`(() => {
    const EH = window.MemoriaEditHandler;
    const ES = window.MemoriaEditSync;
    const cur = EH && EH.cursorAST;
    let ret = "n/a", err = null;
    try { ret = ES && typeof ES.indentListLevel === "function" ? ES.indentListLevel(+1) : "no-fn"; }
    catch (e) { err = String(e && e.message || e); }
    return {
      hasEH: !!EH, hasES: !!ES,
      cursorAST: cur ? { bi: cur.blockIndex, np: cur.nodePath, off: cur.offset } : null,
      editMode: EH ? EH.editMode : null,
      listItemIndex: EH ? EH.listItemIndex : "no-EH",
      ret: ret, err: err,
      fns: { flatLi: typeof ES.flatLiToTreePath },
    };
  })()`);
  out.checks.push({ id: "DIAG-t1", pass: true, detail: diag });
  // 降级后：c 行应出现缩进（前面有空格/Tab）
  rec("T1-list-tab-indent", (typeof body1 === "string") && /\n {4}-\s*子项 B/.test(body1), { body: (typeof body1 === "string" ? body1.slice(0, 400) : String(body1)) });

  // ── T2：同一项 Shift+Tab ⇒ 升级回来 ──
  const pt2 = await cdp.evalJS(cursorPointJs(listBlockIdx, 2));
  if (pt2 && pt2.x != null) await clickAt(cdp, pt2.x, pt2.y);
  try {
    await sendKey(cdp, SHIFT_TAB);
  } catch (e) {
    out.infraBlocked = true;
    out.reason = "Shift+Tab 导致 CDP 超时：" + String((e && e.message) || e);
    rec("T2-list-shifttab-outdent", false, { infra: "CDP blocked" });
    return out;
  }
  await sleep(900);
  const body2 = await cdp.evalJS(BODY_JS);
  // T2 强断言：T1 必须已把「子项 B」变成子子项（4 空格），Shift+Tab 后应回到 2 空格
  const t1Changed = /\n {4}-\s*子项 B/.test(body1);
  rec("T2-list-shifttab-outdent", t1Changed && /\n {2}-\s*子项 B/.test(body2) && !/\n {4}-\s*子项 B/.test(body2), {
    t1Changed: t1Changed, body: (typeof body2 === "string" ? body2.slice(0, 400) : String(body2)),
  });

  // ── T3：普通段落内 Tab ⇒ 插入 2 空格 ──
  const paraRes = await cdp.evalJS(`(() => {
    const blocks = document.querySelectorAll('#preview .-src-block');
    for (let i = 0; i < blocks.length; i++) {
      const t = (blocks[i].textContent || '').trim();
      if (t.indexOf('plain para') === 0) {
        const w = document.createTreeWalker(blocks[i], NodeFilter.SHOW_TEXT, null);
        let n = null;
        while (w.nextNode()) { if (w.currentNode.nodeValue.trim()) { n = w.currentNode; break; } }
        if (!n) return 'no-text';
        const r = document.createRange();
        r.setStart(n, 0); r.setEnd(n, 0);
        const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
        return 'ok';
      }
    }
    return 'no-para';
  })()`);
  await sleep(200);
  let t3 = { pass: false, detail: { place: paraRes } };
  if (paraRes === "ok") {
    try {
      await sendKey(cdp, TAB);
      await sleep(700);
      const body3 = await cdp.evalJS(BODY_JS);
      // 段落行首应出现 2 个空格
      t3 = { pass: /plain para/.test(body3) && /\n {4}plain para/.test(body3), detail: { body: (typeof body3 === "string" ? body3.slice(-120) : String(body3)) } };
    } catch (e) {
      out.infraBlocked = true;
      out.reason = "段落 Tab 导致 CDP 超时：" + String((e && e.message) || e);
    }
  }
  rec("T3-paragraph-tab-spaces", t3.pass, t3.detail);

  return out;
}

export function formatReport(out) {
  const lines = ["=== Tab / Shift+Tab 真机探针（N4）==="];
  if (out.infraBlocked) lines.push("  ⚠️ INFRA_BLOCKED: " + (out.reason || ""));
  for (const c of out.checks) {
    lines.push("  " + (c.pass ? "PASS" : "FAIL") + "  " + c.id);
    lines.push("        " + JSON.stringify(c.detail));
  }
  const fail = out.checks.filter((c) => !c.pass).length;
  lines.push("");
  lines.push(fail ? "FAIL " + fail + "/" + out.checks.length : "PASS " + out.checks.length + "/" + out.checks.length);
  return lines.join("\n");
}
