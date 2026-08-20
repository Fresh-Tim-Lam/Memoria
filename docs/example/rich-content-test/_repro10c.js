// 笔刷覆盖复现 v10c — 同步探测（无 return 关键字，browser_evaluate 兼容）
// 每个场景用独立源行，避免场景间级联污染；每场景独立 try/catch 防止一处失败影响全部
window.__r2 = (function () {
  var out = { log: [] };
  var preview = document.getElementById("preview");
  out.previewConnected = !!(preview && preview.isConnected);
  var sel = window.getSelection();
  var tx = null, curRange = null, applyRes = null, srcLines = "";

  var find = function (content) {
    var w = document.createTreeWalker(preview, NodeFilter.SHOW_TEXT);
    var n, hit = null;
    while ((n = w.nextNode())) {
      if (n.data === content) { hit = n; break; }
    }
    tx = hit;
  };
  var findContain = function (content) {
    var w = document.createTreeWalker(preview, NodeFilter.SHOW_TEXT);
    var n, hit = null;
    while ((n = w.nextNode())) {
      if (n.data.indexOf(content) >= 0) { hit = n; break; }
    }
    tx = hit;
  };
  var grabLine = function (kw) {
    srcLines = Array.from(document.querySelectorAll("#editor .m0-line-content"))
      .map(el => el.textContent)
      .filter(l => l.indexOf(kw) >= 0)
      .join("\n");
  };
  var setSel = function (sNode, sIdx, eNode, eIdx) {
    var r = document.createRange();
    r.setStart(sNode, sIdx);
    r.setEnd(eNode, eIdx);
    sel.removeAllRanges();
    sel.addRange(r);
    curRange = r;
  };
  var apply = function (fmt, color, r) {
    var ES = window.MemoriaEditSync;
    try {
      var res = ES.applyStyle(fmt, color, r, true);
      applyRes = (res && typeof res === "object") ? JSON.stringify(res) : String(res);
    } catch (e) { applyRes = "THREW:" + (e && e.message); }
  };
  var run = function (name, fn) {
    try { fn(); } catch (e) { out[name] = { err: String((e && e.message) || e) }; }
  };

  // A: L59 全段 highlight 换色（绿底灰字 → 刷 #d2986f）
  run("A", function () {
    find("撒旦a的撒");
    if (tx) {
      grabLine("撒旦a的撒"); var b = srcLines;
      setSel(tx, 0, tx, tx.data.length);
      apply("highlight", "#d2986f", curRange);
      grabLine("撒旦a的撒");
      out.A = { res: applyRes, before: b, after: srcLines };
    } else out.A = { error: "text not found" };
  });

  // B: L58 全段 fontcolor 换色（绿底紫字 → 刷 #9a6ed0）
  run("B", function () {
    find("|sss");
    if (tx) {
      grabLine("sss"); var b = srcLines;
      setSel(tx, 0, tx, tx.data.length);
      apply("fontcolor", "#9a6ed0", curRange);
      grabLine("sss");
      out.B = { res: applyRes, before: b, after: srcLines };
    } else out.B = { error: "text not found" };
  });

  // C: L64 全段 bold（已是粗斜体 → 覆盖应用）
  run("C", function () {
    find("撒旦飒飒的撒打算撒的撒大是");
    if (tx) {
      grabLine("撒旦飒飒"); var b = srcLines;
      setSel(tx, 0, tx, tx.data.length);
      apply("bold", null, curRange);
      grabLine("撒旦飒飒");
      out.C = { res: applyRes, before: b, after: srcLines };
    } else out.C = { error: "text not found" };
  });

  // E: L65 局部 fontcolor（"撒打" 前2字 → 刷 #ff0000）
  run("E", function () {
    find("撒打算");
    if (tx) {
      grabLine("撒打算"); var b = srcLines;
      setSel(tx, 0, tx, 2);
      apply("fontcolor", "#ff0000", curRange);
      grabLine("撒打算");
      out.E = { res: applyRes, before: b, after: srcLines };
    } else out.E = { error: "text not found" };
  });

  // D: L56 混合 fg（"大" fg=#9a6ed0 + "苏打" fg=gray）→ highlight #00ff00
  run("D", function () {
    find("大");
    var tBig = tx;
    find("苏打啊啊是大da是adsad dadasd");
    var tSu = tx;
    if (tBig && tSu) {
      grabLine("sad[["); var b = srcLines;
      setSel(tBig, 0, tSu, 2);
      apply("highlight", "#00ff00", curRange);
      grabLine("sad[[");
      out.D = { res: applyRes, before: b, after: srcLines };
    } else out.D = { error: "big=" + !!tBig + " su=" + !!tSu };
  });

  // F1: 跨块 — start=绿高亮文本末尾(0字符) → end=下一段第3字符（对照 log 10:22:40.879 touched=1）
  run("F1", function () {
    find("苏打啊啊是大da是adsad dadasd");
    var t9 = tx;
    find("啊实打实a|");
    var t10 = tx;
    if (t9 && t10) {
      grabLine("sad[["); var b = srcLines;
      setSel(t9, t9.data.length, t10, 3);
      apply("highlight", "#0066ff", curRange);
      grabLine("sad[[");
      var l2 = Array.from(document.querySelectorAll("#editor .m0-line-content"))
        .map(el => el.textContent).filter(l => l.indexOf("啊实打实a") >= 0).join("\n");
      out.F1 = { res: applyRes, before: b, after: srcLines + "\n>>>" + l2 };
    } else out.F1 = { error: "t9=" + !!t9 + " t10=" + !!t10 };
  });

  // F2: 跨块 — start=绿高亮文本倒数第2字 → end=下一段第3字符（应覆盖 block9 尾部）
  run("F2", function () {
    findContain("啊实打");
    var t10b = tx;
    findContain("苏打啊啊是大da是adsad");
    var t9b = tx;
    if (t9b && t10b) {
      grabLine("sad[["); var b = srcLines;
      setSel(t9b, t9b.data.length - 2, t10b, t10b.data.length);
      apply("highlight", "#0066ff", curRange);
      grabLine("sad[[");
      var l2 = Array.from(document.querySelectorAll("#editor .m0-line-content"))
        .map(el => el.textContent).filter(l => l.indexOf("啊实打实a") >= 0).join("\n");
      out.F2 = { res: applyRes, before: b, after: srcLines + "\n>>>" + l2 };
    } else out.F2 = { error: "t9b=" + !!t9b + " t10b=" + !!t10b };
  });

  out.log.push("done");
  out;
})();
