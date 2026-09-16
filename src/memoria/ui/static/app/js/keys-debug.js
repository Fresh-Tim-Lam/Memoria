/**
 * keys-debug.js — 键盘选区/删除 诊断埋点（临时文件，定位完即删）
 *
 * 用途：不打点修改任何业务逻辑，只从外部监听键盘、选区、删除入口，
 *      把 16 项（Shift / Ctrl+Shift × 上/下/左/右 × 预览区/源码区）的
 *      前后状态打到控制台，标签统一为 [KDBG]，便于整段复制。
 *
 * 用法：python app.py → DevTools 控制台 → 按顺序操作 → 复制所有 [KDBG] 行
 * 卸载：删除 index.html 里的 <script src="/app/js/keys-debug.js"></script>
 */
(function () {
  "use strict";

  // ── 0) 控制台降噪：默认只保留 [KDBG] 行，屏蔽应用噪声 ──
  //     （[SYNC] [MAP] [CTX] [STYLE] [EH] [UNDO] [job] [img-*] ... 全部丢弃）
  //     需要恢复全量日志：控制台执行  window.__KDBG_FILTER = false
  (function () {
    var origLog = console.log;
    window.__KDBG_FILTER = true;
    console.log = function () {
      try {
        if (window.__KDBG_FILTER) {
          var s = "";
          for (var i = 0; i < arguments.length; i++) {
            var x = arguments[i];
            if (typeof x === "string") { s += x; }
            else { try { s += JSON.stringify(x); } catch (_e) { s += String(x); } }
            s += " ";
          }
          // 白名单：埋点 + 删除/写回相关的关键链路（其余噪声丢弃）
          var KEEP = ["[KDBG]", "[STYLE]", "deleteMulti", "deleteSelection",
                      "[UNDO]", "srcEdit", "collectEditorBody", "syncToDisk",
                      "[CTX]", "[EH] ", "[MAP] domToAst"];
          var keep = false;
          for (var k = 0; k < KEEP.length; k++) {
            if (s.indexOf(KEEP[k]) >= 0) { keep = true; break; }
          }
          if (!keep) return;  // 应用噪声 → 不输出
        }
      } catch (_e) { /* 过滤自身出错则照常输出，避免丢日志 */ }
      return origLog.apply(console, arguments);
    };
  })();

  var N = 0;
  function ts() {
    N += 1;
    var d = new Date();
    return "#" + String(N).padStart(3, "0") + " +" + d.toISOString().slice(11, 23);
  }

  function log(section, msg) {
    console.log("[KDBG][" + section + "] " + ts() + " " + msg);
  }

  /** 块信息：块索引 + 文本长度 + 前 18 字 */
  function blkInfo(node) {
    var el = node && (node.nodeType === 3 ? node.parentElement : node);
    var b = el && el.closest ? el.closest(".-src-block") : null;
    if (!b) return "-";
    return (
      "bi=" + b.getAttribute("data--block-index") +
      " len=" + String(b.textContent || "").length +
      " txt=" + JSON.stringify(String(b.textContent || "").slice(0, 18))
    );
  }

  /** 选区快照 */
  function selSnap() {
    var s = window.getSelection();
    if (!s || !s.rangeCount) return "sel=none";
    var r = s.getRangeAt(0);
    return (
      "sel len=" + (s.toString() || "").length +
      " collapsed=" + s.isCollapsed +
      " A[" + blkInfo(s.anchorNode) + " off=" + s.anchorOffset + "]" +
      " F[" + blkInfo(s.focusNode) + " off=" + s.focusOffset + "]" +
      " txt=" + JSON.stringify((s.toString() || "").slice(0, 24))
    );
  }

  // ── 正文行级前后监控 ──────────────────────────────────────────
  function bodyLines() {
    var app = window.MemoriaApp;
    var b = app && app.state && app.state.doc && app.state.doc.body;
    return typeof b === "string" ? b.split("\n") : null;
  }

  /** 逐行 diff：公共前缀/后缀之外即为本次变化的行 */
  function dumpDiff(tag, before, after) {
    if (!before || !after) { log("DIFF", tag + " 正文不可用"); return; }
    var p = 0;
    while (p < before.length && p < after.length && before[p] === after[p]) p++;
    var s = 0;
    while (s < before.length - p && s < after.length - p &&
           before[before.length - 1 - s] === after[after.length - 1 - s]) s++;
    var removed = before.slice(p, before.length - s);
    var added = after.slice(p, after.length - s);
    log("DIFF", tag + " | 行数 " + before.length + " → " + after.length +
      " | 自第 " + (p + 1) + " 行起 | 删除 " + removed.length + " 行 / 新增 " + added.length + " 行");
    for (var i = 0; i < removed.length; i++) {
      console.log("[KDBG][DIFF-] 第" + (p + 1 + i) + "行 " + JSON.stringify(removed[i]));
    }
    for (var j = 0; j < added.length; j++) {
      console.log("[KDBG][DIFF+] 第" + (p + 1 + j) + "行 " + JSON.stringify(added[j]));
    }
    if (!removed.length && !added.length) log("DIFF", "（正文无变化）");
  }

  var _bodyBefore = null;

  /** 环境快照 */
  function envSnap() {
    var EH = window.MemoriaEditHandler || {};
    var cur = EH.cursorAST || EH.currentCursor || null;
    var ae = document.activeElement;
    return (
      "editMode=" + String(!!EH.editMode) +
      " view=" + String((window.MemoriaApp && window.MemoriaApp.state && window.MemoriaApp.state.viewMode) || "?") +
      " active=" + (ae ? ae.id || ae.className || ae.tagName : "-") +
      " cursorAST=" + JSON.stringify(cur)
    );
  }

  function region(target) {
    var pv = document.getElementById("preview");
    var src = document.getElementById("source") || document.querySelector(".-source-pane") || document.getElementById("editor");
    if (pv && target && pv.contains(target)) return "PV";
    if (src && target && src.contains(target)) return "SRC";
    if (pv && document.activeElement && pv.contains(document.activeElement)) return "PV*";
    if (src && document.activeElement && src.contains(document.activeElement)) return "SRC*";
    return "?";
  }

  function keyDesc(e) {
    var mods = (e.shiftKey ? "Shift+" : "") + ((e.ctrlKey || e.metaKey) ? "Ctrl+" : "") + (e.altKey ? "Alt+" : "");
    return mods + e.key;
  }

  // ── 1) keydown：按键前状态 ─────────────────────────────────────
  document.addEventListener(
    "keydown",
    function (e) {
      if (!/^Arrow(Up|Down|Left|Right)$/.test(e.key)) return;
      _bodyBefore = bodyLines();
      log("KEYDOWN", "region=" + region(e.target) + " key=" + keyDesc(e) +
        " | BEFORE " + selSnap() + " | " + envSnap());
    },
    true
  );

  // ── 2) beforeinput：删除/键入的入口状态 ────────────────────────
  document.addEventListener(
    "beforeinput",
    function (e) {
      _bodyBefore = bodyLines();
      log("BEFOREINPUT", "region=" + region(e.target) + " inputType=" + e.inputType +
        " cancelable=" + e.cancelable + " data=" + JSON.stringify(e.data) +
        " | " + selSnap());
      // 交给业务处理后再看结果（微任务后 + 一帧后各看一次）
      Promise.resolve().then(function () {
        log("BI/after-microtask", "defaultPrevented=" + e.defaultPrevented + " | " + selSnap());
      });
      requestAnimationFrame(function () {
        log("BI/after-rAF", "prevented=" + e.defaultPrevented + " | " + selSnap());
      });
      // ★ 正文逐行前后对照（等写回完成后再取）
      var tag = String(e.inputType || "input");
      setTimeout(function () { dumpDiff(tag + " @300ms", _bodyBefore, bodyLines()); }, 300);
      setTimeout(function () { dumpDiff(tag + " @1000ms", _bodyBefore, bodyLines()); }, 1000);
    },
    true
  );

  // ── 3) selectionchange：选区变化轨迹（rAF 合并）───────────────
  var pending = false;
  document.addEventListener("selectionchange", function () {
    if (pending) return;
    pending = true;
    requestAnimationFrame(function () {
      pending = false;
      log("SELECTION", "changed | " + selSnap());
    });
  });

  // ── 4) 删除入口：入参 + 返回值 ────────────────────────────────
  function wrapDelete() {
    var ES = window.MemoriaEditSync;
    if (!ES || typeof ES.deleteSelection !== "function" || ES.__kdbgWrapped) return false;
    var orig = ES.deleteSelection;
    ES.deleteSelection = function (range) {
      log("DEL/enter", "argRange=" + (range ? "[" + blkInfo(range.startContainer) + " → " + blkInfo(range.endContainer) + "]" : String(range)) +
        " | " + selSnap());
      var out;
      try {
        out = orig.apply(this, arguments);
      } catch (err) {
        log("DEL/throw", String(err && err.stack ? err.stack.split("\n")[0] : err));
        throw err;
      }
      log("DEL/return", "ret=" + String(out) + " | " + selSnap());
      return out;
    };
    ES.__kdbgWrapped = true;
    return true;
  }
  if (!wrapDelete()) {
    var tries = 0;
    var t = setInterval(function () {
      tries += 1;
      if (wrapDelete() || tries > 40) {
        clearInterval(t);
        log("INIT", "deleteSelection wrapped=" + String(!!(window.MemoriaEditSync && window.MemoriaEditSync.__kdbgWrapped)));
      }
    }, 250);
  }

  // ── 5) 手动快照 ───────────────────────────────────────────────
  window.__kdbg = {
    dump: function (tag) {
      log("DUMP", (tag || "") + " | " + selSnap() + " | " + envSnap());
      var body = window.MemoriaApp && window.MemoriaApp.state && window.MemoriaApp.state.doc && window.MemoriaApp.state.doc.body;
      if (typeof body === "string") {
        console.log("[KDBG][BODY] " + JSON.stringify(body.split(String.fromCharCode(10))));
      }
      return "ok";
    },
  };

  log("INIT", "keys-debug loaded | " + envSnap());
})();
