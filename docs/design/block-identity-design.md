# 稳定块身份 + 块↔源行区间 · 接口设计草案

> **状态**：**草案 / 待裁决**（2026-10-20，arch-agent）。**只出设计，未改代码、未 commit。**
> **上位依据**（冲突时优先级从高到低）：① 宪章 §5.2 必保接口 I1–I12（人已认可）；② battlemap §1 **裁决 B：运行时唯一坐标系 = AST**（人已拍板 2026-10-19）；③ 契约 §2 RenderCore（**其 §0「真源=文本」已被裁决 B 部分作废**，见 K1）。
> **消费者**：KP hover / 跳转落点 / 静默标记 / 错误高亮 / band / 源码行寻址。

---

## 1. 现状盘点（行号为本稿实测）

### 1.1 块身份 = 位置下标，**不是身份**
渲染器只写 `data--block-index`（`renderer.js` **12 处**：`77,84,93,102,115,122,168,174,193,213,243,250,260`）；全仓**无** `data-block-id`/`blockId`（grep 零命中）。
- 结构编辑后**整篇重编下标**：`app.js:14168`（`setAttribute("data--block-index", String(j))`）。
⇒ 第 3 块前插入一段，原第 3 块变第 4 块 ⇒ 冻结/缓存/锚点/hover 全部指错。

### 1.2 `stampBlockLines` 是「顺序 zip」，且**有两套边界判定**
`app.js:1831-1916`：`while(srcIdx<srcLines && blockIdx<blocks)` 顺序推进；`1844-1902` 用 8 类正则启发式算 `lineCount`（空行/fence/`$$`/表格/列表/引用）；`1904` 再用 parser 值覆盖；`1905` 写 `_blockLineMap`；`1908-1909` 写 `data--src-line`(1-based 起)/`-end`。
- **权威源**：`parser.js:344-348 emit()` 落的 `blk.srcLine/srcLineEnd`，注释自称"**单一事实源**…不得再各自复写一套块边界判定（历史上重复实现导致 223/274 份文档行号漂移）"（`parser.js:334-338`）。**兜底源** = 上述启发式 ⇒ **同一件事两套实现**，正是那句警告的复发。

### 1.3 重渲后不可靠：三个独立断链
| # | 断链 | 证据 | 后果 |
|---|---|---|---|
| **A** | `renderRange` **remove+重建**，旧元素身份作废 | `renderer.js:471-474` → `477-491` | 持 `domEl` 者拿到游离节点 |
| **B** | `keepLineMap=true` **跳过 stamp** ⇒ 新块**瞬时不带** `data--src-line` | `app.js:7759-7760`；调用 `8194` | **X2 瞬时失明** |
| **C** | `_blockLineMap` **整体重新赋值**，外部持旧数组 | `1833`；`14170` 注释自述 | 外部缓存（`9655`、`14226/14246`）读陈旧 |

### 1.4 I9 消费者（谁在读这些属性）
| 消费者 | 位置 | 读什么 |
|---|---|---|
| KP hover band | `11253-11258` `previewElOverlapsRange` → `11445-11486` `layoutPreviewRangeBand` | `[data--src-line]`+`SrcLine/SrcLineEnd` |
| 滚动落点 | `1737-1741`、`1762-1766` | 同上（逐块 getBoundingClientRect） |
| wikilink 行号 | `6119-6120`、`6357-6358`、`6673-6684`、`6769-6799` | `closest("[data--src-line]")` |
| 编辑模块（行→块） | `edit-handler.js:154-158,167,269-274,757,1344-1345,1941-1943,1958-1960` | 同上 |
| 助手字符区间 | `agent-panel.js:3208-3231,4063-4089` | `[data--src-line][-end]` |
| 图片工具 / band 自身 | `image-tools.js:104,609` / `11485` `band.dataset.srcRange` | 同上 / 供"预览带跟随布局"（`13072-13073`） |

> **既存隐患**：`edit-handler.js:1941,1958` 用 `data--src-line` **反查元素且假定行号唯一** ⇒ 一行被多块覆盖（嵌套/松散列表）时取错。

---

## 2. 设计

### 2.1 `BlockHandle`（只读视图，持有者不得原地改）
```js
{ id: "b7f3a2c1",       // ★ 稳定标识，§2.2
  srcLineStart: 42,     // 1-based 含端点（与 I8/#line-N/既有属性同口径）
  srcLineEnd:   47,
  kind: "list",         // AST block 类型
  domEl: HTMLElement,   // 当前节点；可能为 null
  domVersion: 3,        // 该 id 下 domEl 重建次数 ⇒ 引用失效判定
  frozen: false }       // 冻结快照（是否保留见 R6）
```

| 字段 | 服务 | 理由 |
|---|---|---|
| `id` | **I9**、I10、契约 C1 | 唯一能跨"整篇重编下标"存活的锚 |
| `srcLineStart/End` | I3、I4/I5/I6/I7、I9、I12 | 既有高亮语义全是 1-based 闭区间，**口径一字不改** |
| `kind` | I9、C8 | 空行块不该被 hover 成一条空带 |
| `domEl`+`domVersion` | I10、X2 | 消灭 `querySelector('[data--src-line=…]')` 反查 |
| `frozen` | C5 | 让"能不能动这块"可查询（则 R6 存疑） |

### 2.2 `id` 生成（★ 最易被推翻，见 R1）
```
id = hash8(kind + "\0" + blockSrcText)  ⊕  同文档内该 hash 的出现序 n
```
- `blockSrcText` 由 **AST 的 `srcLine*` 直接切片**（不跑启发式）；**纯函数**：同文本 ⇒ 同 id（满足契约 **I3**）；与裁决 B 一致：id 从 AST 单向派生，不引入第二套边界判定。
- **不用计数器/下标**：整篇 reparse 会重置；下标会被 `14166-14168` 重编。**代价（如实）**：块被编辑 ⇒ 文本变 ⇒ id 变 ⇒ `id` 只保证"**未编辑的块**身份稳定"——**恰与契约 C1 断言吻合**（C1 只要求"改一处 → **其余块** id 不变"）。若要"编辑中的块也保 id"，唯一可行解是显式 id 表 + 编辑点合并（ProseMirror `identity` 量级）⇒ **列为 R1**。

### 2.3 接口签名（不实现）
```js
// 查询（同步只读）
BlockIndex.blocks()                  -> BlockHandle[]
BlockIndex.get(id)                   -> BlockHandle | null        // O(1)
BlockIndex.atSrcLine(line, opts?)    -> BlockHandle[]             // ★ 一行可被多块覆盖
                                                                  //   opts.outermost ⇒ 只回最外层（等价旧 closest()）
BlockIndex.rangeOf(id)               -> {startLine, endLine}      // 等价旧 SrcLine/SrcLineEnd
BlockIndex.blocksInRange(start, end) -> BlockHandle[]             // ★ 谓词: b.start<=end && b.end>=start
                                                                  //   等价 previewElOverlapsRange 的 filter
// 变更通知（I10 重放）
BlockIndex.onPatched(h) -> off       // h({changedIds, removedIds, lineDelta})
                                    // removedIds ⇒ 持 band/hover 者必须重算
// 渲染期（内核专用）
BlockIndex.beginStamp()              // 一轮开始，期间查询走稳定快照
BlockIndex.upsert(handle)            // ★ 单块回填；同步写 data--src-line（消灭 X2）
BlockIndex.commit()                  // 一轮结束：重算前缀 / 触发 onPatched
```
**关键**：`upsert` 必须**同步**回写 DOM 属性，不允许"先换节点、稍后补属性"——这正是 X2 的成因。

**消费者侧只需换取数方式，其余逻辑不动**：
```js
// 旧: el.closest("[data--src-line]") → dataset.SrcLine/SrcLineEnd
// 新: BlockIndex.get(el.dataset.blockId) → srcLineStart/srcLineEnd
```

### 2.4 与 parser 的关系：**删掉第二套判定**
`stampBlockLines` 的 8 类启发式（`1844-1902`）**整体废弃**；行区间只来自 `parser.js:344-348`；`stampBlockLines` 退化为"**把 AST 区间投射到 DOM 属性**"的纯投射器，不再计算区间。`_blockLineMap` 迁入 `BlockIndex`，**不再整体重新赋值**（消灭断链 C）。附带收益：`keepLineMap` 补丁可删——`upsert` 是 O(1) 单块写，无需"跳过整篇扫描"省时间。

---

## 3. 对 I9 的支撑：增量重渲后旧块区间仍可查
### 3.1 数据结构
```
BlockIndex = { byId: Map<id, BlockHandle>      // O(1)
               byOrder: BlockHandle[]          // 按 srcLineStart 升序
               starts: Int32Array              // 二分用前缀
               lineToIds?: Map<line, id[]> }   // 仅"多头映射"证伪热路径时才建
```
`blocksInRange(s,e)` = **二分定位 + 右扫** ⇒ `O(log n + k)`，**不是 O(n)**。这正是替代"每次重渲都 `querySelectorAll('[data--src-line]')` 全篇扫"（`11446`）的关键：band/hover 从 O(n) DOM 扫降为 O(log n+k) 内存查。

### 3.2 谁能改它（写权限唯一 = 渲染内核）
| 时机 | 动作 | 复杂度 |
|---|---|---|
| 整篇渲染/reparse | `beginStamp → 全量 upsert → commit` | O(n)（本就如此） |
| 单块重渲 `reRenderBlock` | `upsert(id)`，同步写属性 | **O(1)** |
| 结构编辑（行数变） | 变更点之后平移 + 重建 `starts` | O(n−k)，优化见 R4 |
| 换文件/缓存搬回 | 整篇 beginStamp；**缓存必须连 BlockIndex 一起存** | O(n) |

**消费者一律只读**（KP 面板、编辑模块、助手面板）。

### 3.3 避免 O(n) 全扫的三条规则
1. **消费者禁止 DOM 扫描**：`querySelectorAll("[data--src-line]")`（`11446`）→ `blocksInRange()`；
2. **单块更新 O(1)**：`upsert` 只碰 `byId` + 就地改属性；`starts` 仅在行数变时失效；
3. **行数不变走免重算快路径**（打字/行内格式化）⇒ `starts` 保持有效。

### 3.4 失效与更新（对齐 I10）
- `renderRange` 换节点后**立刻** `upsert`（同步，不延后）⇒ X2 消灭；
- 删除的块进 `commit().removedIds` ⇒ 派 `onPatched` ⇒ **持 band 者必须重放 I4/I7**（契约 I10 原文）；
- `band.dataset.srcRange`（`11485`）改记 **id + 行区间双份**：id 用于重渲后重定位，行号用于跨 reparse 兜底。
---

## 4. 与老接口的映射表（宪章 §5.2 硬要求，**不允许绕开**）

| # | 老接口 | 老位置 | 新等价物 | 成本 |
|---|---|---|---|---|
| M1 | `[data--src-line]`/`[-end]` | `1908-1909` 写；§1.4 全部读者 | **保留属性**（值不变）+ 新增 `[data-block-id]` | **零**（见 R3） |
| M1·门禁 | ↑ 的**写入门禁**（R3② 的落地） | `scripts/benchmark/maintenance/check_line_attr_gate.js`（正反例自测 `…_test.js`） | 只允许 `block-index.js` 的 `upsert()` 内写；其余命中即 exit 1 | **P2/P3 交付前必跑、须归零** |
| M2 | `data--block-index` | `renderer.js` 12 处 | `data--block-id`（**并存**，index 降为调试） | 低 |
| M3 | `.-src-block` | `renderer.js` / 各处 | **不变** | 零 |
| M4 | `#line-N`/`.-line`/`.-line-content`（**I8，源码面板侧**） | `1642-1645` 产；`11297,11333,11347,11383` 用 | **不变**（I8 不在本设计范围，另文） | 零 |
| M5 | `#-preview-range-band`+`.error`/`fade-out` | `11366,11428,11475-11489` | **元素 id/类名不变**，style 改由 BlockIndex 算 | 低 |
| M6 | `previewElOverlapsRange` | `11253-11258` | `blocksInRange` | 低（O(n)→O(log n+k)） |
| M7 | `layoutPreviewRangeBand` 的全篇扫 | `11446` | `blocksInRange`+直接 `domEl` | 低（顺手修反查失败） |
| M8 | `querySelector('[data--src-line="N"]')`（假定唯一） | `edit-handler.js:1941,1958` | `atSrcLine(n,{outermost:true})` | 低（顺手修多头隐患） |
| M9 | `window.__blockLineMap` | `1975` 导出；`9655,14226,14246` 读 | `rangeOf`/`blocksInRange` | 中（门面 `getBlockSourceRange` 同步改写） |
| M10 | `_blockLineMap[idx]` | `1825`；`14039,14133,14148-14170` | BlockIndex 内部，**不再整体重赋值** | 中（消灭断链 C） |
| M11 | `_domBlockSig` | `1973,7760` | `domVersion`+`upsert` 记录 | 中（整篇签名 → 按 id 版本号） |
| M12 | `stampBlockLines()` | `1831-1916`；调用 `1973,7759,13491,14133,14169` | 拆 `beginStamp/upsert/commit` | **中高**（唯一需改写的核心函数，见 R2） |

---

## 5. 风险与需裁决的分歧

### 5.1 与 `sync-mapper`（映射域）｜5.2 与 `render-perf`（性能域）
| # | 冲突 | 风险 / 缓解 |
|---|---|---|
| S1 | 坐标口径**三套并存**（块内 `nodePath+offset` / 源码行 / `data--src-line`；宪章 P4 已记） | 若把 `srcLine*` 误当"块内坐标"⇒ **第四次分裂**。须写死：**BlockHandle 只有行级粒度，块内坐标仍属 mapper** |
| S2 | `mapper.js:359-365` 已在读 `b.srcLine/srcLineEnd`（自称单一事实源） | ✅ 与新设计**同源**，无冲突 |
| S3 | `mapper.js:642,857` 用 `data--block-index` 反查 | 需同步迁到 `data-block-id` |
| S4 | `domToAst` 依赖 DOM 结构，换节点后旧 Range 失效 | `domVersion` 可**主动检测**"Range 指向已废弃节点"→ 提前降级而非静默错位 |
| P1 | `upsert` 同步写属性 = 每键多 2 次 `setAttribute` | 打字热路径（现 **26.5ms**，预算 **16ms**）**加成本**。缓解：只在值真变时写；仍**需实测** |
| P2 | `starts` 结构编辑后 O(n−k) 重算 | 与 A3"消灭 O(文档)"方向相反。缓解：行数不变不重建（§3.3-3） |
| P3 | `id` 需每块切片+哈希 | 整篇 O(n) 哈希，占用首开 1434ms 预算的一部分。缓解：`beginStamp` 整轮只算一次 |
| P4 | **高度账本（K5b）也按块为键** | 两个索引会重复。**建议合并进同一 BlockIndex 承载 `estHeight/realHeight`**（battlemap 阶段 1 本就要求"块身份+账本一起做"） |

### 5.3 需 Lead 裁决（**6 条**）
| # | 分歧 | 选项 | 倾向 |
|---|---|---|---|
| **R1** | `id` 生成 | (a) 内容摘要（纯函数，满足 I3）(b) 显式 id 表 + 编辑点合并（被编辑块也保 id） | **(a)**——C1 只要求"其余块"稳定 |
| **R2** | `stampBlockLines` 改造范围 | (a) **就地改造**，保留函数名/5 个调用点 (b) 新建 `block-index.js`，旧函数变薄壳 | **(a)** 先做，(b) 留 NewSurface |
| **R3** | **是否保留 `data--src-line`** | (a) **保留**（12+ 消费者零改动）(b) 逐步下线，全改走 BlockIndex | **(a)**——宪章"接口可换、行为不可变"，属性是最低保真成本；下线留待 NewSurface |
| **R4** | `starts` 维护 | (a) 懒失效，首次查询重建 (b) 编辑时同步重建 | **(a)**——打字路径不碰 `starts` |
| **R5** | 是否与高度账本合并 | (a) 合并（一键两用）(b) 分开 | **(a)**——键集完全相同，分开必然同步失调 |
| **R6** | `frozen` 是否进 handle | (a) 进（快照字段）(b) 只留 `isFrozen(id)` 方法 | **(b)**——冻结是时变状态，放进 handle 会造成"读到陈旧冻结"；契约 §3.4 本就是方法形态 |

---

## 6. 关键取舍与待裁决汇总
**为什么不是"块 id 替代所有行号"**：源码面板侧（**I8** `#line-N`）、KP 侧（`range_resolved.start_line/end_line` 来自后端）、检查面板错误（行号）**都是行坐标**。若 `BlockHandle` 不提供行区间，KP 面板必须自己从 id 反查行 ⇒ **把 O(1) 变 O(n)**，正是宪章 §5.2 验收 #1 明令禁止的"绕开"。
⇒ **块 id 管身份，行区间管位置，同一 handle 同时给出**——这是本设计能与 I9 对齐的根本原因。

---

## 7. Lead 裁决（2026-10-20，**已生效，施工按此**）

| # | 裁决 | 理由与附带约束 |
|---|---|---|
| **R1** | **采纳 (a) 内容摘要 id** | C1 只要求"改一处 → **其余块** 稳定"；(b) 是 ProseMirror 级复杂度，当前不划算。**附带约束**：文档与代码注释必须写死「**被编辑的块 id 会变**」，消费者**禁止**跨"该块自身被编辑"持有 id 做身份假设；`domVersion` 已足够表达重建。 |
| **R2** | **混合方案（不是 a 也不是 b）**：行为就地改造（保留 `stampBlockLines` 函数名与 5 个调用点）**但索引实现放独立模块 `block-index.js`** | 就地改造保证 5 个调用点零改、可增量验证；把 `BlockIndex` 独立成文件，是为了 NewSurface 能**直接 import**、不必把 `app.js` 拖进新实现。`stampBlockLines` 退化为薄壳（只做"AST 区间 → upsert"投射）。 |
| **R3** | **采纳 (a) 保留 `data--src-line`，但定性为「派生投影」不是「第二套坐标」** | 硬约束：①**唯一真源 = BlockIndex**；②`data--src-line` 只允许经 `upsert()` 写，**禁止任何其它 `setAttribute`**（加门禁：grep 校验）；③属性旁标 deprecated 注释 + 排一个后续迁移任务（迁移 12 个消费者到 `blocksInRange`）。这样"两套坐标"的说法不成立——是**一份数据、两处渲染**。 |
| **R4** | **采纳 (a) 懒失效** | 附带约束：必须有显式 `startsValid` 标志；`commit()` 检测到行数变化即置无效；**打字路径不得触发重建**（P1 的缓解前提）。 |
| **R5** | **采纳 (a) 与高度账本合并进同一 BlockIndex** | 键集完全相同，分开必然同步失调；battlemap 阶段 1 原本就要求"块身份 + 账本一起做"。**附带约束**：账本字段（`estHeight/realHeight`）**不放进 `BlockHandle`**（handle 是只读身份视图），放 `BlockIndex` 侧表，用 id 关联。 |
| **R6** | **采纳 (b) 方法形态 `isFrozen(id)`** | 冻结是时变状态，放进 handle 会造成"读到陈旧冻结"；契约 §3.4 本就是方法形态。 |

### 7.1 施工前必须补的两条硬约束（来自 §5 风险）

1. **S1 口径锁**：`BlockHandle` **只有行级粒度**，块内坐标（`nodePath+offset`）**仍属 mapper 域**。任何人把 `srcLine*` 当块内坐标用 ⇒ 直接打回（这是宪章 P4 记的"第四套坐标"风险）。
2. **P1 性能闸**：`upsert` 同步写属性会让打字热路径（现 **26.5ms**，预算 **16ms**）多加成本。阶段 1 **必须**同时交付：
   - 「每键 DOM 写入次数」读数（`metrics-baseline` 域负责加）；
   - 打字时延回归（**不得倒退**，目标下降）；
   - 缓解落地：值未变不写（比字段比较）、`starts` 懒失效。
   **若阶段 1 后打字变慢 ⇒ 视为阶段 1 失败**，不进入阶段 2。

### 7.2 行号漂移的施工纪律（本设计自身也被影响）

`arch-contract` 施工期间 `app.js` 被 `kp-owner` 改动 9 行，文档引用行号已漂 1–3 行。⇒ **硬纪律**：
- 本文档中所有 `文件:行号` **只作起点**；
- 施工时**必须以符号名重新 grep 定位**（函数名/变量名/DOM attr 名），不得直接按行号改；
- 提交前用 `git diff` 复核"改的确实是那个符号"。

> 这条不是形式主义：`kp-owner` 与 `arch-contract` 同时改 `app.js` 已实际发生过行号漂移——这正是 D10 的实时复现。

### 7.3 G1 裁决：R1「被编辑块 id 会变」的**取代语义**——分路径，不二选一

> **来源**：P1 报告 §5 缺口 G1（task-14）。**Lead 裁决 2026-10-20**，已写入 task-18 实现要求。
> **问题**：R1 规定"块被编辑 ⇒ `blockSrcText` 变 ⇒ 自动生成的 id 变"。但 `upsert` 无法知道"新 id 取代了哪个旧 id"，旧块会残留在 `byId/byOrder` ⇒ `blocksInRange` 同时命中新旧两块 = **重复命中**。

**裁决：按路径分治，因为两条路径的代价结构不同。**

| 路径 | 触发场景 | 做法 | 代价 |
|---|---|---|---|
| **局部路径** | 单块重渲 / 结构编辑 / `commitRange` | **调用方显式传 `id`** ⇒ 同 id 就地更新，不产生"新 id + 旧 id 残留" | **O(1)** |
| **整篇路径** | 整篇 reparse / 换文件 / 缓存搬回 | `beginStamp({reset:true})` —— 先清空 `byId/byOrder`（旧 id 全记入 `removedIds` 供 I10 重放）再全量 upsert | **O(n)**（本就如此） |

**为什么不是一刀切**：重复命中只在"新旧同时存在"时发生。若让局部路径也走"清空重来"，**打字路径就会背上 O(n)**——与 §7.1 性能闸直接冲突。反之若让整篇路径也依赖显式 id，整篇 reparse 时调用方并无 identity 可传（文本全变了），只能靠清空。

**代码落点（P1 已实现，P2 接线）**
- `block-index.js` 的 `beginStamp(opts)`：`opts.reset=true` 时清空 `byId/byOrder/starts/_metrics/_frozen`，并把旧 id 全推进 `_pendingRemove`；默认 `beginStamp()` **不清空**（局部路径）。
- 断言：`block_index_test.js` **A13-1**（局部路径：编辑后受影响行只 1 个 handle、索引总数不增长）、**A13-2**（整篇路径：reset 把旧 id 记入 removedIds、重建后受影响行只 1 个 handle、索引总数不翻倍）。

**P2 必须遵守**：局部路径的每个 `upsert` 调用点都要拿到并传 `id`（编辑点天然知道 identity）；整篇路径（`renderPreview` 全量重渲等）才用 `beginStamp({reset:true})`。**用错路径 = A13 红 = 重复命中回归。**

---

**裁决状态：R1–R6 已全部拍板并生效（见 §7），本设计转入施工拆分** —— 见 [block-identity-build-plan.md](block-identity-build-plan.md)。
