#!/usr/bin/env node
/* E33 单测：拖拽「插入半边」insertFromDrop 必须写回源码，并与 deleteByDrag 配对为单个撤销单元。
   背景（E33，P2）：
     E30 只接管了拖拽的删除半边（deleteByDrag → EditSync.deleteSelection）；
     浏览器在落点插入时触发 insertFromDrop，旧分派表没有它 ⇒ 走原生 return
     ⇒ 插入只进 DOM 不进源码 ⇒ 下一次重渲内容消失。

   本测试为**白盒单元测试**（不依赖浏览器/jsdom）：
     从 edit-handler.js 按函数边界抽取 readDropText / beginDragMoveUndo / endDragMoveUndo /
     writeCutToClipboard / bindBeforeInput 的真实源码，在 Node `vm` 中注入最小 DOM/选区/EditSync 桩，
     然后派发合成 beforeinput 事件。
   覆盖：
     A. insertFromDrop 带 text/plain：preventDefault + 仅一次 EditSync.insertText(text)
     B. 无文本（文件/图片）：不拦、不 preventDefault、不调 EditSync
     C. 拖拽移动 deleteByDrag + insertFromDrop：beginUndoGroup → deleteSelection → insertText → endUndoGroup
        （整个移动只占一个撤销单元）；dragend 缺失/拖到应用外也能收组
     D. 回归：普通输入 / Backspace / Delete / Enter / 粘贴 / Ctrl+X / 块编辑 / IME / 只读视图

   用法：node scripts/benchmark/maintenance/edit_drag_drop_test.js
*/
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SRC_PATH = path.join(__dirname, "..", "..", "..", "src", "memoria", "ui", "static", "app", "js", "edit-handler.js");
const src = fs.readFileSync(SRC_PATH, "utf8");

let passes = 0;
let failures = 0;
const failLines = [];
function check(name, cond, extra) {
  if (cond) { passes++; console.log("PASS  " + name); }
  else {
    failures++;
    const tail = extra !== undefined ? "  " + JSON.stringify(extra) : "";
    failLines.push("FAIL  " + name + tail);
    console.log("FAIL  " + name + tail);
  }
}

/** 按缩进函数边界抽取 `function NAME(...) { ... }`（顶层函数 2 空格缩进）。 */
function extractFunction(name) {
  const head = "\n  function " + name + "(";
  const start = src.indexOf(head);
  if (start < 0) throw new Error("function not found: " + name);
  const endMark = "\n  }\n";
  const end = src.indexOf(endMark, start);
  if (end < 0) throw new Error("function end not found: " + name);
  return src.slice(start + 1, end + 4);
}

const fnCut = extractFunction("writeCutToClipboard");
const fnRead = extractFunction("readDropText");
const fnBegin = extractFunction("beginDragMoveUndo");
const fnEnd = extractFunction("endDragMoveUndo");
const fnBind = extractFunction("bindBeforeInput");

check("抽取 readDropText 源码", fnRead.indexOf("text/plain") >= 0);
check("抽取 beginDragMoveUndo/endDragMoveUndo 源码",
  fnBegin.indexOf("beginUndoGroup") >= 0 && fnEnd.indexOf("endUndoGroup") >= 0);
check("抽取 bindBeforeInput 源码（含 insertFromDrop 与 deleteByDrag）",
  fnBind.indexOf("insertFromDrop") >= 0 && fnBind.indexOf("deleteByDrag") >= 0);
check("insertFromPaste 未被接管（粘贴走另一条链路）",
  fnBind.indexOf('inputType === "insertFromPaste"') < 0);

// ── 测试沙箱 ───────────────────────────────────────────────────────────────
const sandbox = {};
sandbox.globalThis = sandbox;
sandbox.console = console;
sandbox.setTimeout = setTimeout;
sandbox.clearTimeout = clearTimeout;

let handlers = {};
let docHandlers = {};
let selection = null;
let ops = [];
let editSync = null;
let clip = null;
let execCopyResult = false;

sandbox.EH = {
  editMode: true,
  blockEditMode: null,
  _composing: false,
  _dragMoveGroup: false,
  dockAfter: null,
  cursorAST: { blockIndex: 0, nodePath: [], offset: 0 },
};
sandbox.state = { viewMode: "preview" };
sandbox.log = function () { };
sandbox.syncFromSelection = function (tag) { ops.push("sync:" + tag); };
sandbox.window = {
  getSelection: function () { return selection; },
  get MemoriaEditSync() { return editSync; },
  MemoriaApp: {
    showFlashError: function (msg) { ops.push("flash:" + msg); },
    setStatusError: function (msg) { ops.push("status:" + msg); },
  },
  alert: function (msg) { ops.push("alert:" + msg); },
};
sandbox.document = {
  getElementById: function (id) { return id === "preview" ? preview : null; },
  addEventListener: function (type, fn) { docHandlers[type] = fn; },
  execCommand: function (cmd) { ops.push("execCommand:" + cmd); return execCopyResult; },
};
sandbox.navigator = {};
const preview = {
  addEventListener: function (type, fn) { handlers[type] = fn; },
};

vm.createContext(sandbox);
vm.runInContext(
  fnCut + "\n" + fnRead + "\n" + fnBegin + "\n" + fnEnd + "\n" + fnBind +
  "\nthis.__bindBeforeInput = bindBeforeInput;",
  sandbox,
  { filename: SRC_PATH + "#E33-extracted" }
);
sandbox.__bindBeforeInput();

function setClipboard(writeText) {
  if (writeText) sandbox.navigator.clipboard = { writeText: writeText };
  else delete sandbox.navigator.clipboard;
}

function makeSelection(text, collapsed) {
  const range = { cloneRange: function () { return { __range: text }; } };
  return {
    isCollapsed: !!collapsed,
    rangeCount: collapsed ? 0 : 1,
    toString: function () { return text; },
    getRangeAt: function () { return range; },
  };
}

function makeEditSync(opts) {
  const calls = [];
  const ES = {};
  const names = ["insertText", "backspace", "deleteForward", "deleteSelection", "splitParagraph", "undo", "redo"];
  if (!(opts && opts.noGroup)) names.push("beginUndoGroup", "endUndoGroup");
  names.forEach(function (fn) {
    ES[fn] = function () {
      const args = Array.prototype.slice.call(arguments);
      calls.push({ fn: fn, args: args });
      ops.push("EditSync." + fn);
      return !(opts && opts.insertFails && fn === "insertText");
    };
  });
  ES.__calls = calls;
  return ES;
}

function resetCase(sel, opts) {
  ops = [];
  editSync = makeEditSync(opts);
  selection = sel;
  sandbox.state = { viewMode: (opts && opts.viewMode) || "preview" };
  sandbox.EH.editMode = !(opts && opts.editMode === false);
  sandbox.EH.blockEditMode = (opts && opts.blockEditMode) || null;
  sandbox.EH._composing = !!(opts && opts.composing);
  sandbox.EH._dragMoveGroup = !!(opts && opts.dragGroupOpen);
  sandbox.EH.dockAfter = null;
  setClipboard(opts && opts.clipboard);
  execCopyResult = !!(opts && opts.execCopy);
}

/** 构造 drop 事件的 dataTransfer 桩；plain 为空串表示文件/图片等无文本拖拽。 */
function makeDataTransfer(plain, opts) {
  const types = {};
  if (plain != null) types["text/plain"] = plain;
  if (opts && opts.uri) types["text/uri-list"] = opts.uri;
  return {
    getData: function (mime) {
      if (opts && opts.throwOnGet) throw new Error("denied");
      return Object.prototype.hasOwnProperty.call(types, mime) ? types[mime] : "";
    },
    types: Object.keys(types),
  };
}

function fire(inputType, data, opts) {
  const e = {
    inputType: inputType,
    data: data,
    dataTransfer: opts && Object.prototype.hasOwnProperty.call(opts, "dataTransfer")
      ? opts.dataTransfer
      : undefined,
    preventDefault: function () { ops.push("preventDefault"); },
  };
  handlers.beforeinput(e);
  return e;
}

function editCalls() { return editSync.__calls.map(function (c) { return c.fn; }); }
function insertArgs() {
  const c = editSync.__calls.filter(function (x) { return x.fn === "insertText"; })[0];
  return c ? c.args : [];
}

(async function main() {
  // ── A. insertFromDrop 带文本：接管并写回源码 ───────────────────────────
  resetCase(makeSelection("", true), {});
  fire("insertFromDrop", null, { dataTransfer: makeDataTransfer("drag me") });
  check("A1 带 text/plain ⇒ preventDefault（阻断原生只改 DOM）", ops.indexOf("preventDefault") >= 0, ops);
  check("A2 恰好调用一次 EditSync.insertText", editCalls().length === 1 && editCalls()[0] === "insertText", editCalls());
  check("A3 insertText 收到拖入文本", insertArgs()[0] === "drag me", insertArgs());
  check("A4 插入前先 sync 光标（落点）", ops.indexOf("sync:beforeinput") >= 0 &&
    ops.indexOf("sync:beforeinput") < ops.indexOf("EditSync.insertText"), ops);

  // A5：没有 dataTransfer 时退回 e.data（合成事件/部分浏览器）
  resetCase(makeSelection("", true), {});
  fire("insertFromDrop", "from data", {});
  check("A5 无 dataTransfer 时用 e.data 兜底", insertArgs()[0] === "from data" && ops.indexOf("preventDefault") >= 0,
    { args: insertArgs(), ops: ops });

  // A6：dataTransfer.getData 抛错 ⇒ 视为无文本，交还原生（不能 preventDefault 后丢字）
  resetCase(makeSelection("", true), {});
  fire("insertFromDrop", null, { dataTransfer: makeDataTransfer("x", { throwOnGet: true }) });
  check("A6 getData 抛错 ⇒ 不拦、不调 EditSync",
    ops.length === 0 && editCalls().length === 0, { ops: ops, calls: editCalls() });

  // ── B. 无文本（文件/图片拖拽）：不得拦 ─────────────────────────────────
  resetCase(makeSelection("", true), {});
  fire("insertFromDrop", null, { dataTransfer: makeDataTransfer("") });
  check("B1 text/plain 为空 ⇒ 不 preventDefault、不调 EditSync",
    ops.length === 0 && editCalls().length === 0, { ops: ops, calls: editCalls() });

  resetCase(makeSelection("", true), {});
  fire("insertFromDrop", null, { dataTransfer: makeDataTransfer(null, { uri: "file:///C:/a.png" }) });
  check("B2 只有 text/uri-list（拖文件/图片）⇒ 交还原生",
    ops.length === 0 && editCalls().length === 0, { ops: ops, calls: editCalls() });

  resetCase(makeSelection("", true), {});
  fire("insertFromDrop", null, {});
  check("B3 无 dataTransfer 且无 e.data ⇒ 交还原生", ops.length === 0 && editCalls().length === 0, ops);

  // ── C. 拖拽移动：deleteByDrag + insertFromDrop 单个撤销单元 ─────────────
  resetCase(makeSelection("moved", false), {
    clipboard: function (text) { ops.push("clipboard:" + text); return Promise.resolve(); },
  });
  fire("deleteByDrag");
  check("C1 deleteByDrag 仍走 deleteSelection",
    editCalls().filter(function (x) { return x === "deleteSelection"; }).length === 1, editCalls());
  check("C2 deleteByDrag 先开撤销分组，且早于 deleteSelection",
    ops.indexOf("EditSync.beginUndoGroup") >= 0 &&
    ops.indexOf("EditSync.beginUndoGroup") < ops.indexOf("EditSync.deleteSelection"), ops);
  check("C3 deleteByDrag 不写剪贴板", ops.filter(function (x) { return x.indexOf("clipboard:") === 0; }).length === 0, ops);
  check("C4 分组打开期间标记 _dragMoveGroup=true", sandbox.EH._dragMoveGroup === true, sandbox.EH._dragMoveGroup);

  // 紧接着落点插入：insertText 后收组，ops 顺序即一个撤销单元
  sandbox.selection = makeSelection("", true);
  selection = makeSelection("", true);
  fire("insertFromDrop", null, { dataTransfer: makeDataTransfer("moved") });
  const beginCount = ops.filter(function (x) { return x === "EditSync.beginUndoGroup"; }).length;
  const endCount = ops.filter(function (x) { return x === "EditSync.endUndoGroup"; }).length;
  check("C5 整个拖拽移动只开一次/收一次撤销分组", beginCount === 1 && endCount === 1, { beginCount: beginCount, endCount: endCount, ops: ops });
  check("C6 收组发生在 insertText 之后",
    ops.indexOf("EditSync.insertText") < ops.indexOf("EditSync.endUndoGroup"), ops);
  check("C7 收组后 _dragMoveGroup=false", sandbox.EH._dragMoveGroup === false, sandbox.EH._dragMoveGroup);

  // C8：拖到应用外/取消 —— 没有 insertFromDrop，dragend 必须收组（否则后续编辑被吞进同一撤销单元）
  resetCase(makeSelection("moved", false), {});
  fire("deleteByDrag");
  check("C8 无落点时分组保持打开", sandbox.EH._dragMoveGroup === true, sandbox.EH._dragMoveGroup);
  docHandlers.dragend({ type: "dragend" });
  check("C9 dragend 收组（删除单独成为一个撤销单元）",
    sandbox.EH._dragMoveGroup === false &&
    ops.filter(function (x) { return x === "EditSync.endUndoGroup"; }).length === 1, ops);

  // C10：dragend 缺失时，下一次非拖拽输入前兜底收组
  resetCase(makeSelection("moved", false), {});
  fire("deleteByDrag");
  fire("insertText", "x");
  check("C10 下一次普通输入前收旧组，且该输入单独走 insertText",
    ops.filter(function (x) { return x === "EditSync.endUndoGroup"; }).length === 1 &&
    ops.indexOf("EditSync.endUndoGroup") < ops.indexOf("EditSync.insertText") &&
    sandbox.EH._dragMoveGroup === false, ops);

  // C11：重复 deleteByDrag 不重复开组
  resetCase(makeSelection("moved", false), {});
  fire("deleteByDrag");
  fire("deleteByDrag");
  check("C11 重复 deleteByDrag 只开一次分组",
    ops.filter(function (x) { return x === "EditSync.beginUndoGroup"; }).length === 1, ops);

  // C12：旧版 EditSync 没有 beginUndoGroup/endUndoGroup ⇒ 不阻断编辑、也不报错
  resetCase(makeSelection("moved", false), { noGroup: true });
  let threw = null;
  try { fire("deleteByDrag"); } catch (e) { threw = e; }
  check("C12 缺少分组 API 的 EditSync 仍能删除（不抛错、不设标记）",
    !threw && editCalls().indexOf("deleteSelection") === 0 && sandbox.EH._dragMoveGroup === false,
    { threw: threw && threw.message, calls: editCalls(), flag: sandbox.EH._dragMoveGroup });

  // C13：分组 + 落点插入失败（不可编辑）也必须收组，避免永久挂起
  resetCase(makeSelection("moved", false), { insertFails: true });
  fire("deleteByDrag");
  selection = makeSelection("", true);
  fire("insertFromDrop", null, { dataTransfer: makeDataTransfer("moved") });
  check("C13 insertText 返回 false 也收组", sandbox.EH._dragMoveGroup === false &&
    ops.filter(function (x) { return x === "EditSync.endUndoGroup"; }).length === 1, ops);

  // ── D. 既有分派回归 ─────────────────────────────────────────────────────
  resetCase(makeSelection("x", true), {});
  fire("insertText", "x");
  check("D1 普通输入仍走 EditSync.insertText('x')",
    editCalls().length === 1 && insertArgs()[0] === "x", editSync.__calls);

  resetCase(makeSelection("", true), {});
  fire("deleteContentBackward");
  check("D2 折叠 Backspace 仍走 backspace", editCalls().length === 1 && editCalls()[0] === "backspace", editCalls());

  resetCase(makeSelection("", true), {});
  fire("deleteContentForward");
  check("D3 折叠 Delete 仍走 deleteForward", editCalls().length === 1 && editCalls()[0] === "deleteForward", editCalls());

  resetCase(makeSelection("sel", false), {});
  fire("deleteContentBackward");
  check("D4 非折叠 Backspace 仍走 deleteSelection", editCalls().length === 1 && editCalls()[0] === "deleteSelection", editCalls());

  resetCase(makeSelection("", true), {});
  fire("insertParagraph");
  check("D5 Enter 仍走 splitParagraph", editCalls().length === 1 && editCalls()[0] === "splitParagraph", editCalls());

  resetCase(makeSelection("", true), {});
  fire("insertFromPaste", "pasted", { dataTransfer: makeDataTransfer("pasted") });
  check("D6 粘贴仍走原生（不拦、不调 EditSync）",
    ops.length === 0 && editCalls().length === 0, { ops: ops, calls: editCalls() });

  resetCase(makeSelection("hello", false), {
    clipboard: function (text) { ops.push("clipboard:" + text); return Promise.resolve(); },
  });
  fire("deleteByCut");
  check("D7 Ctrl+X 仍写剪贴板 + deleteSelection，且不开拖拽分组",
    ops.indexOf("clipboard:hello") >= 0 && editCalls()[0] === "deleteSelection" &&
    ops.indexOf("EditSync.beginUndoGroup") < 0, ops);

  resetCase(makeSelection("sel", false), { editMode: false });
  fire("insertFromDrop", null, { dataTransfer: makeDataTransfer("x") });
  check("D8 EH.editMode=false 不拦截拖拽插入", ops.length === 0 && editCalls().length === 0, ops);

  resetCase(makeSelection("sel", false), { blockEditMode: { blockIndex: 1 } });
  fire("insertFromDrop", null, { dataTransfer: makeDataTransfer("x") });
  check("D9 块编辑模式不拦截拖拽插入", ops.length === 0 && editCalls().length === 0, ops);

  resetCase(makeSelection("sel", false), { composing: true });
  fire("insertFromDrop", null, { dataTransfer: makeDataTransfer("x") });
  check("D10 IME 组合期不拦截拖拽插入", ops.length === 0 && editCalls().length === 0, ops);

  resetCase(makeSelection("sel", false), { viewMode: "source" });
  fire("insertFromDrop", null, { dataTransfer: makeDataTransfer("x") });
  check("D11 源码视图不拦截拖拽插入", ops.length === 0 && editCalls().length === 0, ops);

  resetCase(makeSelection("sel", false), {});
  editSync = null;
  fire("insertFromDrop", null, { dataTransfer: makeDataTransfer("x") });
  check("D12 无 EditSync 时放行（不 preventDefault）", ops.length === 0, ops);

  // ── 汇总 ───────────────────────────────────────────────────────────────
  console.log("\n" + "─".repeat(46));
  console.log((failures === 0 ? "PASS " : "FAIL ") + passes + " / " + (passes + failures) +
    " （共 " + (passes + failures) + " 项）");
  if (failures) {
    failLines.forEach(function (l) { console.log(l); });
    console.log("E33 拖拽插入半边：FAIL");
    process.exit(1);
  }
  console.log("E33 insertFromDrop 写回源码 + 拖拽移动单撤销单元：全 PASS");
})().catch(function (e) {
  console.error("E33 测试异常：" + (e && e.stack || e));
  process.exit(2);
});
