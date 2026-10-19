# 渲染底层重构 · 系统作战图

> ⚠️ **先读 [display-refactor-charter.md](display-refactor-charter.md)**——那份是**人话版重构宪章**
> （痛点 / 牵涉功能 / 牵涉交互 / 鸠占鹊巢含义 / 验收标准）。**本文是内部实施细节附录**：
> 阶段编号、契约测试编号（C1–C12）、内部代号（A0/A1/A3/K5a/K5b/K5c）都在这里，
> 供施工与度量使用，**不作为向人汇报的主文档**。

> **性质**：这是「系统分析阶段」的交付物，综合了 5 份 agent 报告（render-perf / sync-mapper /
> render-impl / arch-agent / detail-agent）与 12 份探针 baseline 的证据，形成统一的施工蓝图。
> **不是施工记录**：本图只负责「现状真相 + 待裁决 + 分阶段顺序」，逐阶段施工另派 agent。
> 细节证据见 `artifacts/agent/verify/*-report.md`，本图不重复。

## 0. 一句话现状（已从源码取证，非文档声明）

**接口层已经做了一半，但无人经过它；真正的核心（NewSurface/RenderCore/稳定块id/高度账本）几乎空转。**

- `surface/registry.js` + `surface/legacy-surface.js` 已存在并注册 legacy（双插头协议 §4 完整）；
- 但 `app.js:14386-14408` 明写「不迁移任何既有调用路径」⇒ 插口空转、无消费者；
- `NewSurface`（技术选型未定）/ `RenderCore` / `block-metrics.js`（高度账本）**全部 0 命中不存在**；
- 11 次 CDP 探针 baseline 在 `scripts/benchmark/surface/results/`，最后一次 2026-10-06，之后只修 bug 没按红项推进。

## 1. 两个架构级裁决（人已拍板，2026-10-19）

### 裁决 A：「预览区可编辑双向同步」—— ✅ 保留，dicussion 那条是错的

- 人拍板：**预览区当然可编辑 + 双向同步**，这是产品能力，不是历史包袱。
- `docs/design/dicussion.md:730-733` 那句「阅读器不做编辑、保存、同步」**作废**（历史遗留，与现状矛盾）。
- 影响：施工图按「保留可编辑」推进 ⇒ K5a（输入所有权反转）+ flush F1-F8 是绕不过的硬骨头，**不走“砍预览编辑”降维路线**。

### 裁决 B：真源 = AST（内存运行时唯一坐标系）+ .md（磁盘唯一事实源）

- 旧 S 文档「AST 是唯一真理」**半对**：对的是「运行时锚定 AST」，错的是「让 AST 取代 .md 上磁盘」。
- 契约 §0「真源是正文文本」**半对**：对的是「磁盘 .md 是持久真相、git/外部编辑友好」，错的是「因此运行时也要用 text 坐标系」。
- **人拍板的正确解是「分层锚定」**：
  ```
  .md（磁盘，持久真相，git/外部编辑友好，永不放弃）
      │ 加载 parse（单向，快，可 mtime+增量）
      ▼
  AST（内存，运行时唯一坐标系：行号/列号/块id/高度都锚它）
      │ 保存 serialize 回写
      ▼
  .md（写回磁盘）
  ```
- **代价**：用户在 Trae/VSCode 等外部编辑器改 .md 后，AST 需重新 parse 合并（用 mtime 检测 + 增量 parse 压到很低）。
- **收益**：双向同步从「两套解析器各自算偏移再对齐」变成「单边 AST 推导 + 单边回写」，根治 sync-mapper 报告的 R1/R3/R5 等 P0。
- **结论**：锚定 AST（内存）+ .md 磁盘持久，是对的，是「双向同步 + 准确性」的根治方向。施工图按「AST 运行时唯一坐标系」走。

## 2. 已被证据确证的关键事实（施工时不可违背）

1. **主预览走 AST 管线**（`P.parse → R.render`，app.js:1959/1963），`marked` 只服务助手气泡（agent-panel.js:5325）和复习卡面。**别在主预览里优化 marked。**
2. **度量目前不可信**：8 次 run 同一 commit `f4ea83d8`，C9 中位数 14.0→26.2ms 摆动（1.87×），噪声大于代码差异 ⇒ 现有「单次 median≤16ms」判据失效。**任何重构前必须先修度量（A0）。**
3. **7 笔热路径成本 7/7 全在**：`spliceBlockSource` 整篇 split/join、`logCursorContext` 无开关全篇选择器扫描、`beforeinput` 仍 `preventDefault`、块内整块重建、整篇 mermaid 逐块 await、整篇 MathJax 不 await。
4. **窗口化回退是干净的**（无 MemoriaPreviewWindow / 无 content-visibility / 无 pv-spacer）—— K5c 视口化可从零重新评估，不受旧回退污染。
5. **两个已修 bug 是真的修好了**：`astToDom` 用错长度函数、`liCol=2` 硬编码（即我们 79865b1d 修的 R3 + 更早的）。
6. **三个「被实测推翻」的方向别再重试**（render-perf 报告）：content-visibility（paint 只 1833→1788）、缓存存序列化 HTML、窗口化 K4a。
7. **D9 是共同前提**：稳定块 id 不存在（只有位置下标 `data--block-index`），而它是 A2/K5b/C1/I3 的前提 ⇒ **重构第一颗钉子不是性能，是块身份**（arch-agent 结论）。
8. **公式渲染后端必须可插拔（人裁决，2026-10-19）**：CHTML→SVG（`4a3e5a7d`）是「同一 MathJax 引擎换输出组件」，SVG **不是「公式变图片」**（是矢量文本，可缩放/可选/可复制 LaTeX）。CHTML 不是该遗弃的旧线——**真正的彻底重构是把公式输出组件做成可配置**，当前 `index.html` 写死 `tex-svg.js` 是临时态。这条与导出 HTML（R12）强耦合：导出时把已排版 SVG 内联，实现「离线 + 绕开渲染开销」。

## 3. 分阶段施工顺序（两 agent 独立得出，高度一致）

| 阶段 | 事项 | 交叉面 | 目标 |
|---|---|---|---|
| **阶段0** | 修文档状态 + **A0 分段读数复活** + `logCursorContext` 加默认关开关 + 修 C6 判据 | 零 | 让度量可判绿 |
| **阶段1** | 稳定块 id + `block-metrics.js`（高度账本）+ 落点接线 | 低 | C1/C6/C7 转绿，撤 AG104 二次校准 |
| **阶段2** | 冻结规则通电（`isBlockFrozen` 现在有定义无执行） | 低 | C5 转绿 |
| **阶段3** | A1 输入所有权反转（必须与 flush F1-F8 一起） | 中 | C9 转绿 |
| **阶段4** | 接口接线（applyEdit/onTextChange 真正跑起来） | 中 | 摆脱 legacy 空转 |
| **阶段5** | RenderCore + NewSurface | 高（需先定选型） | C10/C11/C12 |
| **阶段6** | K5c 视口化（门槛：K5a+K5b 落地取证） | 高 | 大库滚动 |

**最小可行（如果只做一段）**：阶段0 + 阶段1 —— 零/低交叉面，能把 3 条红/未测变绿，证明「接口化+探针门禁」有效。

**明确别做**（两 agent 都警告）：
- 立刻改 A2 inline 复用（判据 U4 无法定 + 冻结未通电）；
- 立刻写 NewSurface（选型未定，会变成第二个 legacy）；
- 把复习卡的 R3a/R4 待定项混进 K5 排期。

## 4. 两个独立小 bug（可先单独修，成本极低，不依赖蓝图）

1. **D1 只修了一半**：`refreshFiles()` 仍被无条件调用（agent-panel.js:4527）→ `_previewCacheClear()` 仍让 agent 每回话一次清空整库预览缓存。
2. **增量重渲后块节点瞬时不带 `data--src-line`**：`renderRange` 换节点 + `keepLineMap` 跳过 stamp ⇒ 按该属性定位的入口在瞬间失明。

## 4.5 外部参考：xerj 的可借鉴设计（2026-10-19 取证自 xerj-1.0.0-rc.96 README）

xerj（开源、Rust、ES 兼容检索引擎，本机 `C:\xerj\...\xerj.exe`）有两个设计与我们的痛点**直接同构**：

### 4.5.1 增量重建由「内容哈希」判定，不由「脏标记」判定

> xerj 原文：「a file whose content is **byte-identical** to the last indexed generation **skips the parse
> entirely** and carries its committed result forward… The **full content hash still runs** to detect changes,
> so total re-index time is **floored by hashing, not parsing**.」

**对应我们的病灶**：`render-perf` 实测预览缓存命中率 **0%**，根因是 `app.js:13133-13134` 的早退条件
（`_dirty`、缺 `preview_body`）——**用「脏标记」判定缓存有效性，而非用「内容身份」**。
编辑中的大文件因此永远进不了预览池：整篇解析 ~1s，代价付了、收益没有。

**可借鉴的修法**：缓存有效性改为「**当前正文指纹 == 缓存代指纹**」——
指纹相同 ⇒ 直接复用已解析 AST / 已渲染 DOM，不重进 parse/render；
指纹不同 ⇒ 才走解析。哈希成本远低于解析，这正是 xerj 说的「riced by hashing」。
（与 `render-perf` 自提的「按 `fp` 指纹判失效」一致 —— 两条独立路径同一结论。）

### 4.5.2 检索给「符号 + 行号」，不给「整文件」

> xerj 原文：「**Grep does not solve this either, because a grep hit is a line, and judging that line means
> opening the whole file.**」/「AST-aware indexing, so an agent **finds a function instead of a line**.」

**对应我们的病灶**：本轮会话 10.6M token 的结构性原因就是「grep 命中 → 读大段文件 → 才敢下结论」。
这正是 xerj 要消灭的模式。

**可借鉴的修法（已接入，见 §4.5.3）**：agent 查代码优先走 xerj 索引（`xerj_search` 定义优先、
`xerj_map` 先看字段），**只在需要精确上下文时才读文件片段**。

### 4.5.3 实测与接入结论（2026-10-19）

**先说事实：xerj 早就索引了 Memoria**——`C:\xerj\data` 下已有 `.xerj-memory-{memoria,src,scripts}-edges`，
ES 里 `ax-docs` 有 30,512 条、内容包含本仓 `app.js` / `agent-panel.js` 的真实代码段。
所以「接入 xerj」不是新建索引，而是**改变 agent 的行为：查代码先走 xerj，而不是 grep 一遍再读全文**。

**实测数据（本机单节点）**：
| 操作 | 结果 |
|---|---|
| `xerj_search`（MCP）查 `增量渲染 缓存命中` | 成功，返回 `app.js` 真实代码段（缓存命中分段计时那段），**26,034 ms** |
| 直连 `POST /ax-docs/_search` 查 `_previewCacheStash` | 成功，23 命中，**9,854 ms** |
| MCP 工具短超时查询 | **失败**（服务端 10–26s 才能返回，超出工具超时） |

**结论（不吹不黑）**：
- xerj **擅长「跨文件定位概念」**（一问问出「缓存命中计时在哪、怎么写的」，不用读整个 app.js）——这正是消灭「grep→读全文」的关键；
- 但**单次 10–26s 太慢**，不适合当高频单点查询的 grep 替代；
- ⇒ **分级用法**：**概念性/跨文件问题走 xerj**（一次问答换掉几万 token 的文件阅读）；**已知符号名的单点查找仍用 grep**（毫秒级）。

**运维注意（本次踩坑）**：
- xerj 服务端由 `C:\xerj\start_server.cmd` 启动（`--insecure --data-dir C:\xerj\data`），**它是 ES 节点本身**，
  杀掉它会让 `ax-*` 全部不可用（我误杀一次，已用同一脚本恢复，数据完好）；
- `xerj autoindex` 会把**整个仓**扫进去；本仓有 68,207 个文件（`benchmarks` 42,840 + `dsh-src` 11,239），
  **必须加 `--stub` 排除**，否则重演 AOCI 那次 57MB 膨胀（本次已踩到并中止）。
- 已有的 `ax-*` 索引足够用；**增量刷新按需再跑，不必每次全量**。

## 5. 下一动作

裁决 A/B **已拍板**（见 §1，2026-10-19）。下一步是**按阶段 0 开派第一个施工 agent**：修文档状态 + A0 分段读数复活 + `logCursorContext` 加默认关开关 + 修 C6 判据。施工前需先确保度量协议（`benchmark-measurement-protocol.md`）已落地，因为阶段 0 的第一目标就是「让度量可判绿」。
