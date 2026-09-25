/**
 * 预览池的**智能替换策略**（纯函数，无 DOM 依赖；2026-09-24 追加）。
 *
 * **谁在用**：`app.js` 末尾「预览池智能替换」块。它把池里每个条目摊成
 * `{ path, bytes, hits, lastOpenAt, loadMs, agingStamp }` 交给这里打分 ⇒ 淘汰**分最低**的那个；
 * 后台预渲染的新条目还要先过一道**入场闸**（`admits`）。
 *
 * **模型来处**（都是既有研究，不是本仓发明的）：
 *   · **GDSF**（GreedyDual-Size-Frequency，Cao & Irani）：`H = L + cost/size + freq`，其中 `L`
 *     是**老化/膨胀**值 —— 每淘汰一次就上浮 ⇒ "很久没被用"的条目相对地越来越不值钱。
 *     本文件把它落成**离散事件版**：`A(r)` = 距它最后一次被使用，池里一共发生过多少次淘汰。
 *   · **TinyLFU / W-TinyLFU**（Einziger / Friedman / Manes）：只做淘汰不够，还得有**入场闸** ——
 *     新来者先与"当前最该被淘汰的那个"比分，赢了才换入。这正是防 scan attack（扫一遍目录把热页签
 *     全冲掉）的那一道。
 *   · **Hyperbolic caching**：变长对象必须按**占用**折算 ⇒ 有 `− w_s·Ŝ(bytes)` 这一项。
 *
 * **排名分（越大越该留）**：
 *
 *     S(r) = w_t·T̂(loadMs) + w_f·lg(1+hits) + w_r·2^(−idle/τ) − w_s·Ŝ(bytes) − w_a·A(r)
 *
 *     T̂ = ln(1 + loadMs/8000) / ln2        ∈ [0,1]（8000 ms ⇒ 1.0；取 AG51 实测冷切 5–10 s 为满量程）
 *     Ŝ = min(1, bytes / 4 MiB)
 *     idle = (now − lastOpenAt) / 3600000（小时）；τ = perfHalfLifeH（半衰期，小时）
 *     A(r) = min(淘汰总数 − agingStamp(r), 20)（夹上限：早该淘汰的条目不必无限下探）
 *
 * **淘汰**：取 S 最小者。**新入池**：`hits=0 / idle=0 / A=0 / loadMs=本次实测` ⇒ 分数**重新初始化**。
 * **入场闸**：池未满 ⇒ 一律放行；满 ⇒ 只有 `S(候选) > S(当前最小者)` 才换入（后台预渲染专用；
 * 人**当前看着**的那个页签永远直接入池 —— 那是"正在付代价"的条目，不该被投机项挤掉）。
 *
 * **与"乘性"写法的关系**：`T̂ × (1−w·累计未打开) × f(hits)` 在 idle 大时会**过零变负**（老条目一起
 * 压到 0 之后退化成 FIFO），且三因子量纲不可比 ⇒ 改成**对数域相加**（数学上等价于一条乘性式，但处处
 * 为正、每个系数都能单独调）。`2^(−idle/τ)` 就是那条线性衰减的指数版。因子与口径的对照见 `docs/reference/agent-guide/09-settings-i18n-and-shortcuts.md §2.24`。
 */
(function (global) {
  "use strict";

  /** 归一化参考：`T̂` 的满量程（毫秒）。AG51 实测「切一个文件」冷路径 5–10 s ⇒ 取 8000 ms。 */
  const LOAD_REF_MS = 8000;
  /** 占用参考：`Ŝ` 到 1.0 的字节数（自估口径见 `app.js::_estimatePreviewBytes`）。 */
  const BYTES_REF = 4 * 1024 * 1024;
  /** `A(r)` 的上限：早该被淘汰的条目不需要无限下探（也让"分"保持可比较）。 */
  const AGING_CAP = 20;
  /** 没有冷加载样本时的 `T̂`（后台预渲染的条目、或刚入池就参与评分）。中性值 ⇒ 不奖不罚。 */
  const NEUTRAL_T = 0.5;

  /** 默认策略。**与 `display-settings.js` 的 `DEFAULTS` 必须逐字相等**（有一条跨文件钉子测试核对两边）。
   *
   * 2026-09-24 追加后三个键：它们是**原来硬编码在 `app.js` 里的门槛**，因真机反馈（教材第 8 章 3983 行
   * 永远进不了预渲染射程）搬到这里可配 —— 默认值同时放宽（1200→4000 / 4000→8000 / 4→8）。
   * 权衡：预渲染大文档是**长任务**（输入可能卡一下），所以默认只覆盖到 4000 行，再大请自己调。 */
  const DEFAULTS = Object.freeze({
    previewCacheMax: 8,
    previewCacheMaxLines: 8000,
    preloadMaxLines: 4000,
    preloadMaxTabs: 8,
    perfTimeWeight: 1.0,
    perfFreqWeight: 0.5,
    perfRecencyWeight: 0.6,
    perfSizeWeight: 0.4,
    perfAgingWeight: 0.05,
    perfHalfLifeH: 12,
    perfAdmission: true,
  });

  /** 每个键的合法区间（设置页传进来的坏值不该让算法崩，也不该静默变成怪值）。 */
  const RANGES = {
    previewCacheMax: [1, 32],
    previewCacheMaxLines: [200, 200000],
    preloadMaxLines: [200, 200000],
    preloadMaxTabs: [1, 64],
    perfTimeWeight: [0, 5],
    perfFreqWeight: [0, 5],
    perfRecencyWeight: [0, 5],
    perfSizeWeight: [0, 5],
    perfAgingWeight: [0, 5],
    perfHalfLifeH: [0.5, 168],
  };

  function clamp(value, lo, hi) {
    return value < lo ? lo : value > hi ? hi : value;
  }

  function num(value, fallback) {
    const n = typeof value === "number" ? value : parseFloat(String(value == null ? "" : value));
    return Number.isFinite(n) ? n : fallback;
  }

  /** 外部传入的策略 → 与默认值合并 + 逐键夹到合法区间 + 类型归一（**唯一**的入口）。 */
  function sanitize(raw) {
    const p = Object.assign({}, DEFAULTS);
    if (raw && typeof raw === "object") {
      for (const key of Object.keys(DEFAULTS)) {
        if (!(key in raw)) continue;
        if (key === "perfAdmission") p[key] = !!raw[key];
        else p[key] = num(raw[key], DEFAULTS[key]);
      }
    }
    for (const key of Object.keys(RANGES)) p[key] = clamp(p[key], RANGES[key][0], RANGES[key][1]);
    p.previewCacheMax = Math.round(p.previewCacheMax);
    p.previewCacheMaxLines = Math.round(p.previewCacheMaxLines);
    p.preloadMaxLines = Math.round(p.preloadMaxLines);
    p.preloadMaxTabs = Math.round(p.preloadMaxTabs);
    return p;
  }

  /** 加载耗时项：对数压到 [0,1]（`loadMs` 未知 ⇒ 中性值）。 */
  function costTerm(loadMs, policy) {
    const ms = num(loadMs, 0);
    if (!(ms > 0)) return NEUTRAL_T;
    const value = Math.log(1 + ms / LOAD_REF_MS) / Math.LN2;
    return clamp(value, 0, 1);
  }

  /** 占用项：`bytes / 4 MiB` 夹到 [0,1]。 */
  function sizeTerm(bytes) {
    return clamp(num(bytes, 0) / BYTES_REF, 0, 1);
  }

  /** 新鲜度项：`2^(−idle/τ)`（半衰期 = `perfHalfLifeH` 小时；`lastOpenAt` 未知 ⇒ 当"刚用过"）。 */
  function recencyTerm(idleHours, policy) {
    const tau = num(policy && policy.perfHalfLifeH, DEFAULTS.perfHalfLifeH);
    const idle = num(idleHours, 0);
    if (!(tau > 0) || !(idle > 0)) return 1;
    return Math.pow(2, -idle / tau);
  }

  /** 打开次数项：`lg(1+hits)`（对数阻尼 ⇒ 历史热点不会永生）。 */
  function freqTerm(hits) {
    return Math.log(1 + Math.max(0, num(hits, 0))) / Math.LN2;
  }

  /** 老化项：距最后一次被使用，池里发生过多少次淘汰（夹 `AGING_CAP`）。 */
  function agingTerm(entry, evicts) {
    const stamp = num(entry && entry.agingStamp, 0);
    return clamp(num(evicts, 0) - stamp, 0, AGING_CAP);
  }

  /**
   * 给一个池条目打分（越大越该留）。`entry` 缺字段一律按"刚入池、无样本"处理 ⇒ 绝不抛。
   * `evicts` = 池的累计淘汰次数（老化时钟）；`now` = 毫秒时间戳。
   */
  function score(entry, policy, now, evicts) {
    const p = policy && policy.perfTimeWeight !== undefined ? policy : DEFAULTS;
    const item = entry || {};
    const last = num(item.lastOpenAt, 0);
    const idleHours = last > 0 && now > 0 ? Math.max(0, now - last) / 3600000 : 0;
    return (
      num(p.perfTimeWeight, DEFAULTS.perfTimeWeight) * costTerm(item.loadMs, p) +
      num(p.perfFreqWeight, DEFAULTS.perfFreqWeight) * freqTerm(item.hits) +
      num(p.perfRecencyWeight, DEFAULTS.perfRecencyWeight) * recencyTerm(idleHours, p) -
      num(p.perfSizeWeight, DEFAULTS.perfSizeWeight) * sizeTerm(item.bytes) -
      num(p.perfAgingWeight, DEFAULTS.perfAgingWeight) * agingTerm(item, evicts)
    );
  }

  /** 淘汰候选：分最低者（并列取**先入池**的 ⇒ 确定性）。空池 ⇒ `null`。 */
  function pickVictim(entries, policy, now, evicts) {
    let best = null;
    for (const entry of entries || []) {
      if (!entry || !entry.path) continue;
      const s = score(entry, policy, now, evicts);
      if (best === null || s < best.score) best = { path: entry.path, score: s };
    }
    return best;
  }

  /**
   * 入场闸：后台预渲染的**投机**条目要不要进池。
   * 池未满 ⇒ 放行；满 ⇒ 只有比当前最低分者更值得（严格大于）才换入。
   */
  function admits(candidate, entries, policy, now, evicts, limit) {
    const list = entries || [];
    const cap = Math.max(1, Math.round(num(limit, DEFAULTS.previewCacheMax)));
    if (list.length < cap) return true;
    const victim = pickVictim(list, policy, now, evicts);
    if (!victim) return true;
    return score(candidate, policy, now, evicts) > victim.score;
  }

  /** 活 DOM 与序列化 HTML 的**每节点**经验字节区间。
   *
   * 来源见 `docs/design/preview-render-pipeline.md` §2（带出处）：活 DOM 每节点约 **100–200 B**
   * （Blink 的 Element/Text 对象 + 属性表，DevTools 官方口径），序列化 HTML 平均每节点 **20–40 B**
   * ⇒ 约 3–6 倍。文本自身（2 B/字符）两档都一样，属共同底噪。
   * **用途**：配合池的**实测节点数**回答"改存序列化 HTML 能省多少"（设计 §3.3 的第一组数）——
   * 不必等完整实测就能给量级；但**要定默认值仍须量恢复耗时与功能完整性**（`innerHTML` 要重解析、
   * 监听要重绑、MathJax/Mermaid 产物能否活过序列化未知）。 */
  const NODE_BYTES = Object.freeze({ live: [100, 200], html: [20, 40] });

  /** 由实测 `nodes` / `chars` 给出两档区间（纯函数 ⇒ 可 `node` 单独跑）。 */
  function estimateBand(nodes, chars) {
    const n = Math.max(0, Math.round(Number(nodes) || 0));
    const text = Math.max(0, Math.round(Number(chars) || 0)) * 2;
    return {
      nodes: n,
      text: text,
      live: [n * NODE_BYTES.live[0] + text, n * NODE_BYTES.live[1] + text],
      html: [n * NODE_BYTES.html[0] + text, n * NODE_BYTES.html[1] + text],
    };
  }

  global.MemoriaPreviewPolicy = {
    AGING_CAP: AGING_CAP,
    BYTES_REF: BYTES_REF,
    DEFAULTS: DEFAULTS,
    LOAD_REF_MS: LOAD_REF_MS,
    NEUTRAL_T: NEUTRAL_T,
    NODE_BYTES: NODE_BYTES,
    RANGES: RANGES,
    admits: admits,
    agingTerm: agingTerm,
    costTerm: costTerm,
    estimateBand: estimateBand,
    freqTerm: freqTerm,
    pickVictim: pickVictim,
    recencyTerm: recencyTerm,
    sanitize: sanitize,
    score: score,
    sizeTerm: sizeTerm,
  };
})(window);
