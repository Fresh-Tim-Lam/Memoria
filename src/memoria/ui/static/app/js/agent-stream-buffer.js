/**
 * 流式中间缓冲（AG11）：把模型增量切成「可渲染前缀 + 未完成尾部」的**纯函数**分割器。
 *
 * 用途：对话面板每 250ms 轮询拿到一片增量，若每片都整段重排 Markdown，早期会渲染出
 * 半截表格/半截代码块；若只在结束时渲染，又完全没有"逐行出现"的观感。本模块回答
 * 一个问题：**当前累计文本里，最长能从哪切一刀，使左半段"作为完整 Markdown 渲染"是安全的**。
 *
 * 契约：`window.MemoriaStreamBuffer.split(text) -> { safe, pending, openBlock }`
 *   - `safe`      = 可安全渲染的最长前缀，**恒以换行边界收尾（或为空串）**；
 *   - `pending`   = 尚未成型、不能渲染的尾部；**恒有 `safe + pending === text`**；
 *   - `openBlock` = 扣住尾部的那类构造：`"" | "fence" | "math" | "frontmatter" | "line"`。
 *
 * 规则（按优先级）：
 *   ① **文首 frontmatter**：首行 trim 为 `---` 时视为 frontmatter 候选，找不到下一个
 *      `---` / `...` 行就整段扣住（`frontmatter`）；
 *   ② **围栏代码块**：```` ``` ```` / `~~~`（≥3 个、可带 info string）开启，只有**同类同量**
 *      且**整行只有围栏字符**的行才关闭 —— 未闭合时从该开启行起整段扣住（`fence`）；
 *      这样期间可以给"转圈进度条"，避免把半个代码块当正文渲染；
 *   ③ **`$$` 公式块**：整行以 `$$` 开头且该行内不再出现第二个 `$$` 时开启，后续任意行出现
 *      `$$` 即关闭；未闭合时从该行起整段扣住（`math`）；
 *   ④ 其余情况**只扣最后一行未完成的行**（末尾尚无 `\n`）—— 这正是"表格给完一行就渲染
 *      一行"的来源：完整行落进 `safe` 立刻渲染，正在到达的半行留在 `pending`（`line`）。
 *
 * 纯函数：不碰 DOM、不引 `marked`、无副作用；因此可在 Node 的 VM 里按 `scheduler_vm_test.js`
 * 同款方式单测（`scripts/benchmark/maintenance/agent_stream_buffer_test.js`）。
 * 完整文本（无未闭合构造）时 `pending` 为空、`openBlock` 为 `""` ⇒ 对既有行为零影响。
 */
(function (g) {
  "use strict";

  /** 按行切分，保留每行的起始偏移与"是否以换行收尾"。 */
  function scanLines(src) {
    var out = [];
    var i = 0;
    while (i < src.length) {
      var nl = src.indexOf("\n", i);
      if (nl === -1) {
        out.push({ line: src.slice(i), start: i, complete: false });
        break;
      }
      out.push({ line: src.slice(i, nl), start: i, complete: true });
      i = nl + 1;
    }
    return out;
  }

  /** 整行是否由同一种围栏字符构成、且数量 ≥ 开启时的数量（CommonMark 关闭条件）。 */
  function isFenceClose(t, ch, len) {
    if (t.length < len) return false;
    for (var i = 0; i < t.length; i += 1) {
      if (t.charAt(i) !== ch) return false;
    }
    return true;
  }

  /** 该行是否开启围栏代码块；返回 `{char, len}` 或 null。info string 允许任意后缀文本。 */
  function fenceOpen(t) {
    if (t.length < 3) return null;
    var ch = t.charAt(0);
    if (ch !== "`" && ch !== "~") return null;
    var n = 0;
    while (n < t.length && t.charAt(n) === ch) n += 1;
    if (n < 3) return null;
    // 反引号围栏的 info string 不允许再含反引号（含则不是围栏行）
    if (ch === "`" && t.slice(n).indexOf("`") !== -1) return null;
    return { char: ch, len: n };
  }

  function split(text) {
    var src = text == null ? "" : String(text);
    if (!src) return { safe: "", pending: "", openBlock: "" };

    var lines = scanLines(src);
    var start = 0;

    // ① 文首 frontmatter：首行 `---`，找下一个 `---` / `...` 行闭合
    if (lines.length && lines[0].line.trim() === "---") {
      var close = -1;
      for (var k = 1; k < lines.length; k += 1) {
        var ft = lines[k].line.trim();
        if (ft === "---" || ft === "...") { close = k; break; }
      }
      if (close === -1) return { safe: "", pending: src, openBlock: "frontmatter" };
      start = close + 1;
    }

    // ② / ③ 围栏代码块与 `$$` 公式块：逐行推进状态，记下最后一次开启的偏移
    var fenceChar = "";
    var fenceLen = 0;
    var openAt = -1;
    var openBlock = "";
    var inFence = false;
    var inMath = false;
    for (var i = start; i < lines.length; i += 1) {
      var t = lines[i].line.trim();
      if (inFence) {
        if (isFenceClose(t, fenceChar, fenceLen)) inFence = false;
        continue;
      }
      if (inMath) {
        if (t.indexOf("$$") !== -1) inMath = false;
        continue;
      }
      var f = fenceOpen(t);
      if (f) {
        inFence = true;
        fenceChar = f.char;
        fenceLen = f.len;
        openAt = lines[i].start;
        openBlock = "fence";
        continue;
      }
      if (t.indexOf("$$") === 0 && t.slice(2).indexOf("$$") === -1) {
        inMath = true;
        openAt = lines[i].start;
        openBlock = "math";
      }
    }
    if (inFence) return { safe: src.slice(0, openAt), pending: src.slice(openAt), openBlock: "fence" };
    if (inMath) return { safe: src.slice(0, openAt), pending: src.slice(openAt), openBlock: "math" };

    // ④ 其余：只扣最后一行未完成的行（完整行全部进 safe ⇒ 逐行渲染）
    var last = lines[lines.length - 1];
    if (last.complete) return { safe: src, pending: "", openBlock: "" };
    return { safe: src.slice(0, last.start), pending: src.slice(last.start), openBlock: "line" };
  }

  g.MemoriaStreamBuffer = {
    split: split,
  };
})(typeof window !== "undefined" ? window : globalThis);
