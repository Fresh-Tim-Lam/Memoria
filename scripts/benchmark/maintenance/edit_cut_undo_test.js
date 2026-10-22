#!/usr/bin/env node
/* E30 单测：Ctrl+X（deleteByCut）/ 拖拽（deleteByDrag）必须走 EditSync.deleteSelection。
   背景（E30，P0 数据正确性）：
     `beforeinput` 旧分派表只认 insertText / deleteContentBackward|Forward / insertParagraph，
     Ctrl+X 的 `deleteByCut` 落到 `else return` → 浏览器原生删掉预览 DOM 文本，但 AST/源码没变
     → 下次重渲（切文件/重排版/滚动重物化）被剪切内容"回魂"。

   本测试为**白盒单元测试**（不依赖浏览器/jsdom）：
     从 edit-handler.js 按函数边界抽取 `writeCutToClipboard` 与 `bindBeforeInput` 的真实源码，
     在 Node `vm` 中注入最小 DOM/选区/EditSync 桩，然后派发合成 beforeinput 事件。
   覆盖：
     A. deleteByCut：先 preventDefault（阻断原生 DOM 删除）→ 写剪贴板 → **只调一次**
        EditSync.deleteSelection（单个撤销单元，Ctrl+Z 只恢复一次）
     B. 剪贴板写入失败（Promise reject / API 缺失 / execCommand false）→ 必须调用
        MemoriaApp.showFlashError 明确告知，不得静默
     C. deleteByDrag：走 deleteSelection，但**不**写剪贴板（拖拽不是复制语义）
     D. 回归：insertText / Backspace / Delete / 非折叠删除 / Enter / 粘贴 / 块编辑 / IME / 只读视图
        仍按原路径分派或放行

   用法：node scripts/benchmark/maintenance/edit_cut_undo_test.js
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

/**
 * 按缩进函数边界抽取 `function NAME(...) { ... }` 源码。
 * edit-handler.js 的顶层函数以 2 空格缩进，函数结束行恰为 "\n  }"；
 * 内部嵌套函数至少 4 空格缩进，不会误匹配。
 */
function extractFunction(name) {
  const head = "\n  function " + name + "(";
  const start = src.indexOf(head);
  if (start < 0) throw new Error("function not found: " + name);
  const endMark = "\n  }\n";
  const end = src.indexOf(endMark, start);
  if (end < 0) throw new Error("function end not found: " + name);
  return src.slice(start + 1, end + 4); // 去掉前导换行，保留结尾 "  }"
}

const fnCut = extractFunction("writeCutToClipboard");
const fnBind = extractFunction("bindBeforeInput");
check("抽取 writeCutToClipboard 源码", fnCut.indexOf("navigator.clipboard.writeText") >= 0);
check("抽取 bindBeforeInput 源码", fnBind.indexOf("deleteByCut") >= 0 && fnBind.indexOf("deleteByDrag") >= 0);

// ── 测试沙箱 ───────────────────────────────────────────────────────────────
const sandbox = {};
sandbox.globalThis = sandbox;
sandbox.console = console;
sandbox.setTimeout = setTimeout;
sandbox.clearTimeout = clearTimeout;

let handlers = {};
let selection = null;
let ops = [];
let flashCalls = [];
let editSync = null;
let clip = null;
let execCopyResult = false;

sandbox.EH = {
  editMode: true,
  blockEditMode: null,
  _composing: false,
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
    showFlashError: function (msg, detail) { flashCalls.push({ kind: "flash", msg: msg, detail: detail }); },
    setStatusError: function (msg, detail) { flashCalls.push({ kind: "status", msg: msg, detail: detail }); },
  },
  alert: function (msg) { flashCalls.push({ kind: "alert", msg: msg }); },
};
sandbox.document = {
  getElementById: function (id) { return id === "preview" ? preview : null; },
  execCommand: function (cmd) { ops.push("execCommand:" + cmd); return execCopyResult; },
};
sandbox.navigator = {}; // 每个用例按需替换 clipboard
const preview = {
  addEventListener: function (type, fn) { handlers[type] = fn; },
};

vm.createContext(sandbox);
vm.runInContext(fnCut + "\n" + fnBind + "\nthis.__bindBeforeInput = bindBeforeInput;", sandbox, {
  filename: SRC_PATH + "#E30-extracted",
});
sandbox.__bindBeforeInput();

function setClipboard(writeText) {
  if (writeText) sandbox.navigator.clipboard = { writeText: writeText };
  else delete sandbox.navigator.clipboard;
}

function makeSelection(text, collapsed) {
  const range = { cloneRange: function () { return { __cutRange: text }; } };
  return {
    isCollapsed: !!collapsed,
    rangeCount: collapsed ? 0 : 1,
    toString: function () { return text; },
    getRangeAt: function () { return range; },
  };
}

function makeEditSync() {
  const calls = [];
  const ES = {};
  ["insertText", "backspace", "deleteForward", "deleteSelection", "splitParagraph", "undo", "redo"].forEach(function (fn) {
    ES[fn] = function () {
      calls.push({ fn: fn, args: Array.prototype.slice.call(arguments) });
      ops.push("EditSync." + fn);
    };
  });
  ES.__calls = calls;
  return ES;
}

function resetCase(sel, opts) {
  ops = [];
  flashCalls = [];
  editSync = makeEditSync();
  selection = sel;
  sandbox.state = { viewMode: (opts && opts.viewMode) || "preview" };
  sandbox.EH.editMode = !(opts && opts.editMode === false);
  sandbox.EH.blockEditMode = (opts && opts.blockEditMode) || null;
  sandbox.EH._composing = !!(opts && opts.composing);
  sandbox.EH.dockAfter = null;
  setClipboard(opts && opts.clipboard);
  execCopyResult = !!(opts && opts.execCopy);
}

function fire(inputType, data, opts) {
  const e = {
    inputType: inputType,
    data: data,
    preventDefault: function () { ops.push("preventDefault"); },
  };
  handlers.beforeinput(e);
  return e;
}

function editCalls() { return editSync.__calls.map(function (c) { return c.fn; }); }

(async function main() {
  // ── A. Ctrl+X 正常路径 ──────────────────────────────────────────────────
  resetCase(makeSelection("hello", false), {
    clipboard: function (text) { ops.push("clipboard:" + text); return Promise.resolve(); },
  });
  fire("deleteByCut");
  check("A1 Ctrl+X 调用 preventDefault（阻断原生 DOM 删除）", ops.indexOf("preventDefault") >= 0, ops);
  check("A2 Ctrl+X 先写剪贴板（writeText 收到选区文本）", ops.indexOf("clipboard:hello") >= 0, ops);
  check("A3 Ctrl+X 只调一次 EditSync.deleteSelection（单个撤销单元）",
    editCalls().filter(function (x) { return x === "deleteSelection"; }).length === 1 && editCalls().length === 1,
    editCalls());
  const delArg = editSync.__calls[0] && editSync.__calls[0].args[0];
  check("A4 deleteSelection 收到选区 Range 克隆", !!delArg && delArg.__cutRange === "hello", delArg);
  check("A5 顺序：preventDefault → 剪贴板 → deleteSelection",
    ops.indexOf("preventDefault") < ops.indexOf("clipboard:hello") &&
    ops.indexOf("clipboard:hello") < ops.indexOf("EditSync.deleteSelection"), ops);
  check("A6 成功路径不弹错误提示", flashCalls.length === 0, flashCalls);

  // ── B. 剪贴板失败必须提示 ────────────────────────────────────────────────
  resetCase(makeSelection("hello", false), {
    clipboard: function () { return Promise.reject(new Error("NotAllowedError")); },
  });
  fire("deleteByCut");
  await new Promise(function (r) { setTimeout(r, 0); });
  check("B1 writeText reject → showFlashError 明确告知用户",
    flashCalls.some(function (f) { return f.kind === "flash" && String(f.msg).indexOf("\u526a\u8d34\u677f") >= 0; }),
    flashCalls);
  check("B2 剪贴板失败仍完成源码删除（不半途而废）",
    editCalls().filter(function (x) { return x === "deleteSelection"; }).length === 1, editCalls());

  // B3：Clipboard API 缺失 + execCommand 成功 → 静默回退，不报错（选区仍在）
  resetCase(makeSelection("world", false), { clipboard: null, execCopy: true });
  fire("deleteByCut");
  check("B3 无 Clipboard API 时回退 execCommand('copy') 成功且不打扰用户",
    ops.indexOf("execCommand:copy") >= 0 && flashCalls.length === 0, { ops: ops, flash: flashCalls });
  check("B4 回退路径仍只删一次", editCalls().filter(function (x) { return x === "deleteSelection"; }).length === 1, editCalls());

  // B5：Clipboard API 缺失 + execCommand 失败 → 必须提示
  resetCase(makeSelection("world", false), { clipboard: null, execCopy: false });
  fire("deleteByCut");
  check("B5 execCommand 也失败 → 必须提示用户",
    flashCalls.some(function (f) { return f.kind === "flash" && String(f.msg).indexOf("\u526a\u8d34\u677f") >= 0; }),
    flashCalls);

  // ── C. 拖拽（deleteByDrag）：走源码删除，但不污染剪贴板 ──────────────────
  resetCase(makeSelection("dragme", false), {
    clipboard: function (text) { ops.push("clipboard:" + text); return Promise.resolve(); },
  });
  fire("deleteByDrag");
  check("C1 deleteByDrag 调用 preventDefault", ops.indexOf("preventDefault") >= 0, ops);
  check("C2 deleteByDrag 调 deleteSelection", editCalls().indexOf("deleteSelection") === 0, editCalls());
  check("C3 deleteByDrag 不写剪贴板", ops.filter(function (x) { return x.indexOf("clipboard:") === 0; }).length === 0, ops);

  // ── C4. 折叠选区的 Ctrl+X：浏览器本来也无事可做 → 放行 ──────────────────
  resetCase(makeSelection("", true), {
    clipboard: function (text) { ops.push("clipboard:" + text); return Promise.resolve(); },
  });
  fire("deleteByCut");
  check("C4 折叠选区 Ctrl+X 不拦截、不删除、不写剪贴板",
    ops.length === 0 && editCalls().length === 0 && flashCalls.length === 0, { ops: ops, calls: editCalls() });

  // ── D. 既有分派回归 ─────────────────────────────────────────────────────
  resetCase(makeSelection("x", true), {});
  fire("insertText", "x");
  check("D1 insertText 仍走 EditSync.insertText('x')",
    editCalls().length === 1 && editSync.__calls[0].fn === "insertText" && editSync.__calls[0].args[0] === "x",
    editSync.__calls);

  resetCase(makeSelection("", true), {});
  fire("deleteContentBackward");
  check("D2 折叠 Backspace 仍走 backspace", editCalls().length === 1 && editCalls()[0] === "backspace", editCalls());

  resetCase(makeSelection("", true), {});
  fire("deleteContentForward");
  check("D3 折叠 Delete 仍走 deleteForward", editCalls().length === 1 && editCalls()[0] === "deleteForward", editCalls());

  resetCase(makeSelection("sel", false), {});
  fire("deleteContentBackward");
  check("D4 非折叠 Backspace 仍走 deleteSelection（不写剪贴板）",
    editCalls().length === 1 && editCalls()[0] === "deleteSelection" && ops.indexOf("preventDefault") >= 0, {
      calls: editCalls(), ops: ops,
    });

  resetCase(makeSelection("", true), {});
  fire("insertParagraph");
  check("D5 Enter 仍走 splitParagraph", editCalls().length === 1 && editCalls()[0] === "splitParagraph", editCalls());

  resetCase(makeSelection("", true), {});
  fire("insertFromPaste");
  check("D6 粘贴仍走原生（不拦截、不调 EditSync）",
    ops.length === 0 && editCalls().length === 0, { ops: ops, calls: editCalls() });

  // ── E. 三条早退分支 + 只读视图 + 无 EditSync ─────────────────────────────
  resetCase(makeSelection("sel", false), { editMode: false });
  fire("deleteByCut");
  check("E1 EH.editMode=false 不拦截", ops.length === 0 && editCalls().length === 0, { ops: ops, calls: editCalls() });

  resetCase(makeSelection("sel", false), { blockEditMode: { blockIndex: 1 } });
  fire("deleteByCut");
  check("E2 块编辑模式不拦截", ops.length === 0 && editCalls().length === 0, { ops: ops, calls: editCalls() });

  resetCase(makeSelection("sel", false), { composing: true });
  fire("deleteByCut");
  check("E3 IME 组合期不拦截", ops.length === 0 && editCalls().length === 0, { ops: ops, calls: editCalls() });

  resetCase(makeSelection("sel", false), { viewMode: "source" });
  fire("deleteByCut");
  check("E4 源码视图不拦截", ops.length === 0 && editCalls().length === 0, { ops: ops, calls: editCalls() });

  resetCase(makeSelection("sel", false), {});
  editSync = null;
  fire("deleteByCut");
  check("E5 无 EditSync 时放行（不 preventDefault）", ops.length === 0, ops);

  // ── 汇总 ───────────────────────────────────────────────────────────────
  console.log("\n" + "─".repeat(46));
  console.log((failures === 0 ? "PASS " : "FAIL ") + passes + " / " + (passes + failures) +
    " （共 " + (passes + failures) + " 项）");
  if (failures) {
    failLines.forEach(function (l) { console.log(l); });
    console.log("E30 剪切/拖拽撤销单元：FAIL");
    process.exit(1);
  }
  console.log("E30 Ctrl+X 不再回魂 + 单撤销单元：全 PASS");
})().catch(function (e) {
  console.error("E30 测试异常：" + (e && e.stack || e));
  process.exit(2);
});
