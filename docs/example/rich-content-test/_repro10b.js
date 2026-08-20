// 笔刷覆盖复现 v10 — PART2: 样式内笔刷覆盖场景（在 PART1 已打开的 test-content.md 预览上执行）
(async function () {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const out = { log: [] };
  try {
    const preview = document.getElementById("preview");
    if (!preview || !preview.isConnected) { out.log.push("preview not connected"); return out; }
    const sel = window.getSelection();
    function findTextExact(content) {
      const w = document.createTreeWalker(preview, NodeFilter.SHOW_TEXT);
      let n;
      while ((n = w.nextNode())) {
        if (n.data === content) return n;
      }
      return null;
    }
    function setSel(sNode, sIdx, eNode, eIdx) {
      const r = document.createRange();
      r.setStart(sNode, sIdx);
      r.setEnd(eNode, eIdx);
      sel.removeAllRanges();
      sel.addRange(r);
      return r;
    }
    function srcLine() {
      return Array.from(document.querySelectorAll("#editor .m0-line-content"))
        .map((el) => el.textContent).filter((l) => l.indexOf("sad[[") >= 0).join("\n");
    }
    function apply(fmt, color, range) {
      const ES = window.MemoriaEditSync;
      if (!ES || typeof ES.applyStyle !== "function") return "no-ES";
      const res = ES.applyStyle(fmt, color, range, true);
      return JSON.stringify(res);
    }
    function curSel() {
      try {
        if (!sel.rangeCount) return "none";
        const r = sel.getRangeAt(0);
        const sc = r.startContainer.nodeType === 3 ? "#t:" + r.startOffset : "E:" + r.startOffset;
        const ec = r.endContainer.nodeType === 3 ? "#t:" + r.endOffset : "E:" + r.endOffset;
        return sc + " -> " + ec;
      } catch (e) { return "err:" + e.message; }
    }

    // A: 样式内 全段 highlight 换色（绿底灰字 → 刷底色 #d2986f）
    {
      const t = findTextExact("苏打啊啊是大da是adsad dadasd");
      if (t) {
        const before = srcLine();
        const r = setSel(t, 0, t, t.data.length);
        await sleep(80);
        const res = apply("highlight", "#d2986f", r);
        await sleep(350);
        out.A = { res, before, after: srcLine(), selAfter: curSel() };
      } else out.A = { error: "text not found" };
    }

    // B: 样式内 全段 fontcolor 换色（绿底灰字 → 刷前景色 #9a6ed0）
    {
      const t = findTextExact("苏打啊啊是大da是adsad dadasd");
      if (t) {
        const before = srcLine();
        const r = setSel(t, 0, t, t.data.length);
        await sleep(80);
        const res = apply("fontcolor", "#9a6ed0", r);
        await sleep(350);
        out.B = { res, before, after: srcLine(), selAfter: curSel() };
      } else out.B = { error: "text not found" };
    }

    // C: 样式内 bold（已是粗斜体 → 覆盖应用应无可见变化）
    {
      const t = findTextExact("苏打啊啊是大da是adsad dadasd");
      if (t) {
        const before = srcLine();
        const r = setSel(t, 0, t, t.data.length);
        await sleep(80);
        const res = apply("bold", null, r);
        await sleep(350);
        out.C = { res, before, after: srcLine(), selAfter: curSel() };
      } else out.C = { error: "text not found" };
    }

    // D: 混合 fg 不一致（"大" fg=#9a6ed0 + "苏打" fg=gray）→ highlight 换色
    {
      const tBig = findTextExact("大");
      const tSu = findTextExact("苏打啊啊是大da是adsad dadasd");
      if (tBig && tSu) {
        const before = srcLine();
        const r = setSel(tBig, 0, tSu, 2);
        await sleep(80);
        const res = apply("highlight", "#d2986f", r);
        await sleep(350);
        out.D = { res, before, after: srcLine(), selAfter: curSel() };
      } else out.D = { error: "big=" + !!tBig + " su=" + !!tSu };
    }

    // E: 样式内局部（"打啊啊是大d" 绿底灰字内）→ fontcolor 换色
    {
      const t = findTextExact("苏打啊啊是大da是adsad dadasd");
      if (t) {
        const before = srcLine();
        const r = setSel(t, 2, t, 8);
        await sleep(80);
        const res = apply("fontcolor", "#9a6ed0", r);
        await sleep(350);
        out.E = { res, before, after: srcLine(), selAfter: curSel() };
      } else out.E = { error: "text not found" };
    }

    out.log.push("done");
  } catch (e) {
    out.error = e && e.stack ? e.stack : String(e);
  }
  return out;
})()
