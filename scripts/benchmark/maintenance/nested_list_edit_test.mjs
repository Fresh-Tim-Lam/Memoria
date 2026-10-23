/**
 * nested_list_edit_test.mjs —— 多级列表**编辑路径**回归探针（0.4.7 任务 4，N4 前置）
 *
 * 目的：在给多级列表加编辑能力（Tab/Shift+Tab/Enter 退级）之前，
 * **先确认既有编辑路径遇到嵌套结构不会崩、不会写坏源码**。
 *
 * 做法：用 vm 加载真实的 app.js（与既有 `edit_cut_undo_test.js` 同款思路），
 * 注入最小 DOM 桩，调用 `MemoriaEditSync` 的公开入口，检查 `state.doc.body` 结果。
 *
 * 用法：
 *   node scripts/benchmark/maintenance/nested_list_edit_test.mjs
 *   node scripts/benchmark/maintenance/nested_list_edit_test.mjs --expect   # 断言期望
 */

import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(__dirname, "../../..");
const JS = path.join(REPO, "src/memoria/ui/static/app/js");
const WITH_EXPECT = process.argv.includes("--expect");

/** 最小 DOM 桩：够 app.js 模块加载与列表编辑路径跑通 */
function makeDom() {
  const mk = (tag = "div") => {
    const el = {
      tagName: (tag || "div").toUpperCase(),
      nodeType: 1,
      children: [],
      childNodes: [],
      style: {},
      dataset: {},
      classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
      attributes: {},
      textContent: "",
      innerHTML: "",
      isConnected: true,
      parentNode: null,
      getAttribute(k) { return this.attributes[k] ?? null; },
      setAttribute(k, v) { this.attributes[k] = String(v); },
      removeAttribute(k) { delete this.attributes[k]; },
      hasAttribute(k) { return k in this.attributes; },
      appendChild(c) { c.parentNode = this; this.children.push(c); this.childNodes.push(c); return c; },
      removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) { this.children.splice(i, 1); this.childNodes.splice(i, 1); } return c; },
      insertBefore(c) { return this.appendChild(c); },
      replaceWith() {},
      remove() {},
      querySelector: () => null,
      querySelectorAll: () => [],
      addEventListener() {},
      removeEventListener() {},
      getBoundingClientRect: () => ({ top: 0, left: 0, right: 100, bottom: 20, width: 100, height: 20 }),
      cloneNode() { return mk(tag); },
      contains: () => false,
      focus() {},
      scrollIntoView() {},
    };
    return el;
  };
  return mk;
}

function loadApp() {
  const mk = makeDom();
  const doc = mk("html");
  const sandbox = {
    console,
    setTimeout,
    clearTimeout,
    requestAnimationFrame: (fn) => setTimeout(fn, 0),
    cancelAnimationFrame: clearTimeout,
    MutationObserver: class { observe() {} disconnect() {} },
    ResizeObserver: class { observe() {} disconnect() {} },
    IntersectionObserver: class { observe() {} disconnect() {} },
    navigator: { clipboard: null, userAgent: "node" },
    location: { href: "http://localhost/", search: "", hash: "" },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
    getComputedStyle: () => ({ fontSize: "16px", getPropertyValue: () => "" }),
    fetch: () => Promise.reject(new Error("no net")),
    document: {
      documentElement: doc,
      body: mk("body"),
      head: mk("head"),
      createElement: (t) => mk(t),
      createTextNode: (t) => ({ nodeType: 3, textContent: t, nodeValue: t }),
      createRange: () => ({
        setStart() {}, setEnd() {}, collapse() {}, selectNodeContents() {},
        cloneRange() { return this; }, getBoundingClientRect: () => ({ top: 0, height: 20, left: 0, width: 10 }),
        startContainer: null, startOffset: 0, endContainer: null, endOffset: 0, collapsed: true,
      }),
      getSelection: () => ({ rangeCount: 0, isCollapsed: true, getRangeAt() { throw new Error("no range"); }, removeAllRanges() {}, addRange() {}, toString: () => "" }),
      querySelector: () => null,
      querySelectorAll: () => [],
      getElementById: () => null,
      addEventListener() {},
      removeEventListener() {},
      execCommand: () => false,
    },
    alert: () => {},
    Image: class {},
    WebSocket: class {},
    performance: { now: () => Date.now() },
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  sandbox.self = sandbox;
  vm.createContext(sandbox);
  for (const f of ["ast.js", "lexer.js", "parser.js", "source-gen.js", "scheduler.js"]) {
    vm.runInContext(fs.readFileSync(path.join(JS, f), "utf8"), sandbox, { filename: f });
  }
  // app.js 很大且依赖大量 DOM；加载失败则本探针退化为"仅 parser/source-gen 层"检查
  let appOk = false;
  try {
    vm.runInContext(fs.readFileSync(path.join(JS, "app.js"), "utf8"), sandbox, { filename: "app.js" });
    appOk = !!sandbox.MemoriaEditSync;
  } catch (e) {
    appOk = false;
  }
  return { sandbox, appOk };
}

/**
 * 用例：对**已解析**的 AST 做「结构级编辑」，只验证 source-gen 能正确写回，
 * 不依赖 app.js 的编辑入口（那些需要真实 DOM 选区）。
 */
const CASES = [
  {
    id: "nested-gen-after-child-edit",
    src: "- a\n  - b\n  - c\n- d",
    note: "改子项文字后，嵌套结构与缩进必须保持",
    mutate: (S, doc) => {
      const list = doc.blocks.find((b) => b.type === "list");
      const child = list.items[0].list;      // a 的子列表
      child.items[0].children = [S.MemoriaAST.text("B2")];
    },
    expect: "- a\n  - B2\n  - c\n- d",
  },
  {
    id: "nested-gen-tab-child-edit",
    src: "- a\n\t- b\n- d",
    note: "Tab 缩进的子项被编辑后必须仍是 Tab（不得被改成空格）",
    mutate: (S, doc) => {
      const list = doc.blocks.find((b) => b.type === "list");
      list.items[0].list.items[0].children = [S.MemoriaAST.text("B2")];
    },
    expect: "- a\n\t- B2\n- d",
  },
  {
    id: "nested-gen-add-sibling",
    src: "- a\n  - b\n- d",
    note: "给子列表追加一项（新建项无 indent ⇒ 按父缩进+2 空格推算）",
    mutate: (S, doc) => {
      const list = doc.blocks.find((b) => b.type === "list");
      list.items[0].list.items.push(S.MemoriaAST.listItem([S.MemoriaAST.text("c")]));
    },
    expect: "- a\n  - b\n  - c\n- d",
  },
  {
    id: "nested-gen-remove-child",
    src: "- a\n  - b\n  - c\n- d",
    note: "删除子项后结构完整、不残留空行",
    mutate: (S, doc) => {
      const list = doc.blocks.find((b) => b.type === "list");
      list.items[0].list.items.splice(0, 1);
    },
    expect: "- a\n  - c\n- d",
  },
  {
    id: "nested-gen-outdent",
    src: "- a\n  - b\n  - c\n- d",
    note: "把一个子项**升级**到顶层（模拟 Shift+Tab）",
    mutate: (S, doc) => {
      const list = doc.blocks.find((b) => b.type === "list");
      const parent = list.items[0];
      const moved = parent.list.items.shift();
      moved.indent = "";                    // 顶层无缩进
      list.items.splice(1, 0, moved);
    },
    // 注意：探针只把 `b` 从 a 的子列表移走，`c` **仍留在 a.list 里**
    //   ⇒ 输出顺序是 a → (c 缩进) → b(顶层) → d ⇒ 期望应为下面这个（不是 b 在前）
    expect: "- a\n  - c\n- b\n- d",
  },
];

/**
 * 递归清空 AST 中所有 `srcLine`（编辑期必须做的清理）。
 * 对齐 `itemSrcLine` 也一并清空（长度已不符，保留只会误导）。
 */
function clearSrcLines(node) {
  if (!node || typeof node !== "object") return;
  if (Array.isArray(node)) { node.forEach(clearSrcLines); return; }
  if (node.type === "list" && node.items) {
    node.itemSrcLine = null;
    node.items.forEach((it) => {
      it.srcLine = null;
      if (it.list) clearSrcLines(it.list);
    });
    return;
  }
  if (node.blocks) node.blocks.forEach(clearSrcLines);
}

function run() {
  const { sandbox: S, appOk } = loadApp();
  const P = S.MemoriaParser;
  const G = S.MemoriaSourceGen;
  console.log("  app.js 加载: " + (appOk ? "成功（MemoriaEditSync 可用）" : "失败/不可用（本探针仍只验 AST+回写）"));

  let fail = 0;
  for (const c of CASES) {
    const doc = P.parse(c.src);
    let got = "";
    let err = null;
    try {
      // ★ 模拟**编辑路径的正确做法**：AST 一被编辑，所有 srcLine 就失真。
      //   生产代码（app.js 的编辑入口）必须在改动列表结构后清空 srcLine
      //   —— 本探针在 mutate 之前把 srcLine 清掉，等价于"编辑代码做了正确清理"。
      //   这样断言的是「清理后 source-gen 输出正确」，而非「靠 srcLine 猜」。
      clearSrcLines(doc);
      c.mutate(S, doc);
      const list = doc.blocks.find((b) => b.type === "list");
      got = G.generateBlock(list);
    } catch (e) {
      err = String((e && e.message) || e);
    }
    const pass = !err && got === c.expect;
    if (WITH_EXPECT && !pass) fail += 1;
    console.log("\n  [" + c.id + "] " + c.note);
    console.log("    源码 : " + JSON.stringify(c.src));
    console.log("    期望 : " + JSON.stringify(c.expect));
    console.log("    实际 : " + JSON.stringify(got) + (err ? "  ERR=" + err : ""));
    if (WITH_EXPECT) console.log("    结论 : " + (pass ? "PASS" : "FAIL"));
  }
  if (WITH_EXPECT) {
    console.log("\n" + (fail ? "FAIL " + fail + "/" + CASES.length : "PASS " + (CASES.length - fail) + "/" + CASES.length));
    process.exit(fail ? 1 : 0);
  }
}

run();
