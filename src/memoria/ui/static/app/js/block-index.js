/**
 * MemoriaBlockIndex — 预览块身份 + 块↔源码行区间 索引（阶段 1 地基）
 *
 * 契约 / 裁决依据：docs/design/block-identity-design.md §2–§3 + §7（六条裁决已生效）
 *   R1 内容摘要 id（djb2）
 *   R2 独立模块（NewSurface 可直接 import，不拖 app.js）
 *   R4 startsValid 懒失效（行数不变不得重建）
 *   R5 账本侧表 _metrics（estHeight/realHeight 按 id 关联，不进 BlockHandle）
 *   R6 isFrozen(id) 方法（冻结是时变状态，不进 handle）
 *
 * ── UMD 双出口 ──────────────────────────────────────────────────────────
 *   浏览器：window.MemoriaBlockIndex
 *   Node  ：module.exports = { BlockIndex, hashBlockId }
 *   **不依赖任何 DOM**（纯数据；domEl 只是可选引用，本模块不读写 DOM 属性）
 *
 * ── 关键语义（R1 + task-22，必须写死）──────────────────────────────────────
 *   id = djb2(kind + "\0" + blockSrcText) ⊕ 出现序（纯函数：同文本同序 ⇒ 同 id）。
 *
 *   ★ id 何时变（两条路径，最终口径）：
 *     · **局部路径**（单块重渲 / 编辑点）：调用方**显式传 id**（app.js 用 _keepId）
 *       ⇒ **同一 id 就地更新** ⇒ **被编辑块的 id 不变**；
 *     · **整篇重 parse**（换文件 / 整篇重渲 / 缓存搬回）：纯内容哈希生效，文本变 ⇒ 该块 id 变。
 *   两种路径下契约 C1（"改一处 ⇒ **其余块** id 不变"）都成立。
 *
 *   ★★ **id 标识身份，不保证内容不变。消费者不得用「id 未变」推断「内容未变」。**
 *      内容变化信号只来自三处：`onPatched({changedIds})` / `BlockHandle.domVersion` / 行区间变化。
 *      （task-22 前本文写的是「被编辑的块 id 会变」，已被 Lead 裁决修正 —— 见设计 §7.4。）
 *
 * ── 为什么不叫 hash8 ──────────────────────────────────────────────────────
 *   设计 §2.2 写「hash8」，但仓内既有指纹先例是 djb2（app.js _bodyFingerprint，32 位）。
 *   为保持一致 + 避免与"8 位截断"的二义，本实现用 djb2 32 位取 base36 低 8 位字符，
 *   消歧后缀用十进制出现序 —— 纯函数、确定性，可 node 直测。
 */
(function (root, factory) {
  "use strict";
  var api = factory();
  if (typeof module === "object" && module !== null && typeof module.exports === "object") {
    module.exports = api;                       // Node / NewSurface import
  } else {
    root.MemoriaBlockIndex = api;               // 浏览器全局
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // ── djb2 32 位哈希（与 app.js _bodyFingerprint 同源，但独立实现，不依赖闭包）──
  function djb2(s) {
    var h = 5381;
    for (var i = 0; i < s.length; i++) {
      h = ((h << 5) + h + s.charCodeAt(i)) | 0;   // *33 + c，保持 32 位有符号
    }
    return h;
  }

  /**
   * id = base36(hash) ⊕ "-" ⊕ 出现序 n（n 从 0 起，同 hash 首现 0、次现 1…）
   * 纯函数：同 (kind, blockSrcText) ⇒ 同 id（首现）；同文档重复块靠出现序消歧。
   * 注意：**调用方必须自己保证"同文档同 hash 的出现序"一致** —— 由 BlockIndex.upsert
   * 在整轮 beginStamp 内用 _seq 计数，不依赖调用顺序以外的任何外部状态。
   */
  function hashBlockId(kind, blockSrcText, occurrenceIndex) {
    var key = String(kind) + "\u0000" + String(blockSrcText == null ? "" : blockSrcText);
    var h = djb2(key);
    return (h >>> 0).toString(36).slice(-8) + "-" + (occurrenceIndex >>> 0);
  }

  /**
   * 创建一个空的 BlockIndex。
   * @param {object} [opts]
   *   opts.syncDom   —— 可选同步回写钩子（P2 薄壳注入：把 data--src-line / data-block-id 同步到 domEl）。
   *                    签名 (domEl, handle) => void。P1 **不注入**，故本模块默认不碰 DOM。
   * @returns {object} BlockIndex 实例
   */
  function createBlockIndex(opts) {
    opts = opts || {};

    var byId = new Map();       // id -> BlockHandle（O(1)）
    var byOrder = [];           // 文档序（按 srcLineStart 升序）的 BlockHandle 引用
    var starts = [];            // 前缀数组：starts[i] = byOrder[i].srcLineStart；仅 startsValid 时可用
    var startsValid = false;    // R4：行数变化 ⇒ 置 false，下次查询重建（懒失效）

    var _metrics = new Map();   // R5：账本侧表 id -> { estHeight?, realHeight? }，不进 handle
    var _seq = new Map();       // beginStamp 一轮内的 hash-key -> 出现序计数器（供 id 消歧）
    var _stamping = false;      // beginStamp..commit 之间为 true
    var _pendingRemove = [];    // 本轮删除的 id（commit 时回吐 removedIds）
    // ★ 2026-10-20 语义修正（Lead 裁决 task-22）：本轮**真正被 upsert 过**的 id（commit 时回吐 changedIds）。
    //   旧实现是「整轮=全量」的 P1 简化 ⇒ 下游无法用 changedIds 做精准缓存失效（会把没变的块也判失效）。
    //   现在只有 upsert() 写入的 id 才进这里；删除的走 removedIds。
    var _pendingChanged = new Set();
    var _listeners = [];        // onPatched 订阅者
    var _lineDelta = 0;         // 本轮行数净变化（commit 时回吐 lineDelta）
    var _touched = false;       // 本轮是否触碰了 byOrder 的区间/结构（决定 commit 后 startsValid）
    var _frozen = new Set();    // R6：冻结 id 集合（时变状态，不落 handle）

    var _syncDom = (typeof opts.syncDom === "function") ? opts.syncDom : null;

    // ── 内部：重建 starts 前缀（懒失效点）───────────────────────────────
    function _rebuildStarts() {
      starts = new Array(byOrder.length);
      for (var i = 0; i < byOrder.length; i++) {
        starts[i] = byOrder[i].srcLineStart;
      }
      startsValid = true;
    }
    function _ensureStarts() {
      if (!startsValid) _rebuildStarts();
    }

    // ── 内部：二分定位「srcLineStart <= line 的最大下标」，返回插入上界 ──
    function _upperBound(line) {
      _ensureStarts();
      var lo = 0, hi = starts.length;
      while (lo < hi) {
        var mid = (lo + hi) >>> 1;
        if (starts[mid] <= line) lo = mid + 1; else hi = mid;
      }
      return lo;
    }

    // ── 外部 API ──────────────────────────────────────────────────────────
    var api = {};

    /** @returns {BlockHandle[]} 按文档序（srcLineStart 升序）的快照 */
    api.blocks = function () { return byOrder.slice(); };

    /** @returns {BlockHandle|null} 按 id 精确查找（O(1)） */
    api.get = function (id) { return byId.get(id) || null; };

    /**
     * 一行可能被多个块覆盖（嵌套/松散列表）。按 srcLineStart<=line<=srcLineEnd 匹配全部。
     * @param {number} line 1-based 源码行
     * @param {object} [opts] opts.outermost=true ⇒ 只回 srcLineStart 最小的那个（等价旧 closest() 语义）
     * @returns {BlockHandle[]}
     */
    api.atSrcLine = function (line, opts) {
      opts = opts || {};
      _ensureStarts();
      var out = [];
      for (var i = 0; i < byOrder.length; i++) {
        var b = byOrder[i];
        if (b.srcLineStart <= line && line <= b.srcLineEnd) out.push(b);
      }
      if (!out.length) return out;
      if (opts.outermost) {
        // 最外层 = srcLineStart 最小（区间覆盖最广）；并列取文档序靠前者
        var min = out[0];
        for (var j = 1; j < out.length; j++) {
          if (out[j].srcLineStart < min.srcLineStart) min = out[j];
          else if (out[j].srcLineStart === min.srcLineStart && out[j].srcLineEnd > min.srcLineEnd) min = out[j];
        }
        return [min];
      }
      return out;
    };

    /** @returns {{startLine:number, endLine:number}|null} 等价旧 dataset.SrcLine/SrcLineEnd */
    api.rangeOf = function (id) {
      var b = byId.get(id);
      return b ? { startLine: b.srcLineStart, endLine: b.srcLineEnd } : null;
    };

    /**
     * 区间谓词：b.srcLineStart <= end && b.srcLineEnd >= start（与 previewElOverlapsRange 同义）。
     * O(log n + k)：二分起点 + 右扫，不做 O(n) 全扫。
     * @returns {BlockHandle[]} 交集块，文档序
     */
    api.blocksInRange = function (start, end) {
      _ensureStarts();
      var out = [];
      // 二分找到「srcLineStart <= end 的上界」为实际起点的邻近区，但仍须回溯：
      // 一个块的 srcLineEnd 可能 >= start 而其 srcLineStart < start（块跨过 start）。
      // 安全做法：从 0 起右扫到 srcLineStart > end 即停 —— 功能等价、无遗漏；
      // 二分仅是起点优化，不改变谓词正确性（A4 朴素 filter 等价金标准会兜底）。
      for (var i = 0; i < byOrder.length; i++) {
        var b = byOrder[i];
        if (b.srcLineStart > end) break;         // 越过右端，升序 ⇒ 余下不可能命中
        if (b.srcLineEnd >= start) out.push(b);  // 区间交集谓词（b.start<=end 已由 break 保证，b.end>=start 在此判）
      }
      return out;
    };

    /**
     * 订阅变更通知（I10 重放）。返回取消函数。
     * @param {function} h h({changedIds, removedIds, lineDelta})
     */
    api.onPatched = function (h) {
      if (typeof h !== "function") return function () {};
      _listeners.push(h);
      return function () {
        var i = _listeners.indexOf(h);
        if (i >= 0) _listeners.splice(i, 1);
      };
    };

    // ── 渲染期（内核专用）────────────────────────────────────────────────
    /**
     * 进入一整轮更新；期间查询走当前快照。清空本轮 counters。
     *
     * G1 分路径裁决（Lead 2026-10-20）：
     *  - **局部路径**（单块重渲 / 结构编辑 / commitRange）：`beginStamp()` 默认**不清空**，
     *    调用方显式传 id ⇒ 同 id 就地更新，不产生"新 id + 旧 id 残留"。
     *  - **整篇路径**（整篇 reparse / 换文件 / 缓存搬回）：`beginStamp({reset:true})` ——
     *    先清空 byId/byOrder（旧 id 全记入 removedIds 供 I10 重放）再全量 upsert。
     *    此时 O(n) 本来就是固有成本，不会让打字路径背上它。
     * @param {object} [opts] opts.reset=true ⇒ 整篇重建：清空现有索引
     */
    api.beginStamp = function (opts) {
      _stamping = true;
      _seq = new Map();
      _pendingRemove = [];
      _pendingChanged = new Set();
      _lineDelta = 0;
      _touched = false;
      if (opts && opts.reset) {
        // 整篇路径：清空旧索引；旧 id 全部进 removedIds（订阅者据此重放/清理 band/hover）
        byId.forEach(function (_, id) { _pendingRemove.push(id); });
        byId.clear();
        byOrder.length = 0;
        starts.length = 0;
        startsValid = false;
        _metrics.clear();
        _frozen.clear();
        _touched = true;          // 整篇重建 ⇒ commit 后前缀须重算
      }
    };

    /**
     * 单块回填（O(1) 维护 byId/byOrder）。行数如果变了，置 startsValid=false（R4 懒失效）。
     * @param {object} h { id?, srcLineStart, srcLineEnd, kind, domEl?, domVersion?, blockSrcText? }
     *   —— 若未给 id，则据 kind + (blockSrcText || 拼接 srcLineStart..srcLineEnd 的占位) 自动生成。
     * @returns {object} 落到 byId 的 handle
     */
    api.upsert = function upsert(h) {
      h = h || {};
      var id = h.id;
      if (id == null) {
        // 调用方未给 id：按 kind + 出现序派发（整轮内 _seq 保证同 hash 递增）
        var key = String(h.kind) + "\u0000" + String(h.blockSrcText == null ? "" : h.blockSrcText);
        var n = _seq.get(key) || 0;
        id = hashBlockId(h.kind, h.blockSrcText, n);
        _seq.set(key, n + 1);
      }

      var prev = byId.get(id);
      var start = h.srcLineStart >>> 0;
      var end = h.srcLineEnd >>> 0;
      var handle = {
        id: id,
        srcLineStart: start,
        srcLineEnd: end == null ? start : end,
        kind: h.kind,
        domEl: h.domEl || (prev ? prev.domEl : null),
        domVersion: (prev ? prev.domVersion : 0) + 1,
      };

      // 行数变化检测：prev 存在且区间长度变 ⇒ 触碰结构（行数不变的同 id 打字不放 touched）
      var prevRange = prev ? (prev.srcLineEnd - prev.srcLineStart + 1) : -1;
      var newRange = handle.srcLineEnd - handle.srcLineStart + 1;
      if (prevRange !== newRange) {
        _lineDelta += (newRange - (prevRange === -1 ? 0 : prevRange));
        _touched = true;          // 首次插入或区间长度变 ⇒ 本轮结构变了 ⇒ commit 后 startsValid=false
      }

      byId.set(id, handle);
      _pendingChanged.add(id);   // ★ 语义修正：只有真正被 upsert 的 id 才进 changedIds（供下游精准失效）
      // 维持 byOrder 按 srcLineStart 升序
      var replaced = false;
      for (var i = 0; i < byOrder.length; i++) {
        if (byOrder[i].id === id) { byOrder[i] = handle; replaced = true; break; }
      }
      if (!replaced) {
        var j = _upperBoundInsertPosition(start);
        byOrder.splice(j, 0, handle);
        if (prevRange === -1) _touched = true;   // 纯新增也触碰
      }

      // 默认 DOM 回写 + 可选覆盖钩子（写入点**必须**在 upsert() 内，见 R3 门禁 check_line_attr_gate.js）
      if (_syncDom) {
        try { _syncDom(handle.domEl, handle); } catch (e) { /* 覆盖钩子异常不影响索引 */ }
      } else if (handle.domEl && typeof handle.domEl.setAttribute === "function") {
        try {
          var _el = handle.domEl;
          var _start = String(handle.srcLineStart);
          var _end = String(handle.srcLineEnd);
          if (_el.getAttribute("data-block-id") !== handle.id) _el.setAttribute("data-block-id", handle.id);
          if (_el.getAttribute("data--src-line") !== _start) _el.setAttribute("data--src-line", _start);
          if (_el.getAttribute("data--src-line-end") !== _end) _el.setAttribute("data--src-line-end", _end);
        } catch (e) { /* 回写失败不得影响索引 */ }
      }

      return handle;
    };

    // 内部：插入位置（srcLineStart 升序稳定插入）。读 byOrder，不依赖/不重建 starts。
    function _upperBoundInsertPosition(start) {
      var lo = 0, hi = byOrder.length;
      while (lo < hi) {
        var mid = (lo + hi) >>> 1;
        if (byOrder[mid].srcLineStart <= start) lo = mid + 1; else hi = mid;
      }
      return lo;
    }

    /**
     * 结束一轮：回吐**本轮真正变更的** id、removedIds、lineDelta，触发 onPatched。**不强制重建前缀**——
     * R4 懒失效：starts 的重建留给下一次查询（_ensureStarts 被 blocksInRange/atSrcLine 等触发）。
     *
     * ⚠️ 语义（Lead 裁决 task-22）：
     *   · `changedIds` = **本轮被 upsert() 写过的 id**（不是全量！），下游据此做精准失效；
     *   · **同一 id 被再次 upsert ⇒ 该 id 会出现在 changedIds 里、且 handle.domVersion 会 +1** ——
     *     这是"内容变了"的信号来源（**不要靠 id 是否变化推断内容**：局部路径同 id 就地更新，
     *     被编辑块的 id 可能不变，见 block-identity-design.md §7.3）。
     * @returns {{changedIds:string[], removedIds:string[], lineDelta:number}}
     */
    api.commit = function () {
      var changedIds = [];
      _pendingChanged.forEach(function (id) { if (byId.has(id)) changedIds.push(id); });   // 已删的不算"变更"
      var removedIds = _pendingRemove.slice();
      var ret = { changedIds: changedIds, removedIds: removedIds, lineDelta: _lineDelta };
      // R4：本轮触碰了结构（增/删/改区间）⇒ 前缀失效，留给下次查询懒重建；
      //      纯行数不变的同 id 打字（_touched=false）⇒ 前缀仍有效。
      startsValid = !_touched;
      _stamping = false;
      _listeners.forEach(function (fn) {
        try { fn(ret); } catch (e) { /* 订阅者异常不影响索引 */ }
      });
      return ret;
    };

    /** 删除一个块（进 removedIds，commit 时回吐）。 */
    api.remove = function (id) {
      var b = byId.get(id);
      if (!b) return false;
      byId.delete(id);
      for (var i = 0; i < byOrder.length; i++) {
        if (byOrder[i].id === id) { byOrder.splice(i, 1); break; }
      }
      _metrics.delete(id);
      _frozen.delete(id);
      _pendingRemove.push(id);
      startsValid = false;
      return true;
    };

    // ── R5：账本侧表（不进 handle）───────────────────────────────────────
    /** 写估算/实测高度到侧表（按 id 关联）。 */
    api.setMetrics = function (id, m) {
      m = m || {};
      var cur = _metrics.get(id) || {};
      if ("estHeight" in m) cur.estHeight = m.estHeight;
      if ("realHeight" in m) cur.realHeight = m.realHeight;
      _metrics.set(id, cur);
      return cur;
    };
    /** 读账本侧表。 */
    api.getMetrics = function (id) { return _metrics.get(id) || null; };

    // ── R6：冻结（方法形态，时变状态）────────────────────────────────────
    /** 查询某块是否冻结。 */
    api.isFrozen = function (id) { return _frozen.has(id); };
    /** 设置/清除冻结（内核专用）。 */
    api.setFrozen = function (id, frozen) {
      if (frozen) _frozen.add(id); else _frozen.delete(id);
      return api;
    };

    // ── 诊断（只读，仅供单测断言 A7/R4；生产代码不得依赖）──────────────────
    /** @returns {{startsValid:boolean, size:number, stamping:boolean}} */
    api._diagnose = function () {
      return { startsValid: startsValid, size: byOrder.length, stamping: _stamping };
    };

    return api;
  }

  return {
    BlockIndex: createBlockIndex,
    createBlockIndex: createBlockIndex,
    hashBlockId: hashBlockId,
    djb2: djb2,
  };
});
