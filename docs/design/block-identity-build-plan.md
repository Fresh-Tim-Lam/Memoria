# 块身份 · 施工拆分计划（可并行扇出）

> **状态**：待施工（2026-10-20）。**上位**：[block-identity-design.md](block-identity-design.md) §7 六条裁决**已生效**，本计划只拆片，不改裁决。
> **行号纪律**（设计 §7.2）：所有 `文件:行号` 只作起点，施工**必须按符号名重新 grep**。

## 0. 依赖图与并行度
```
P1 block-index.js（新模块+单测）  ← 先行，无依赖；P4 门禁可并行（只写 scripts/）
   ├──► P2 stampBlockLines 薄壳化 + 5 调用点   （写 app.js）
   └──► P3 消费者迁移 M6/M7/M8                 （写 app.js + edit-handler.js）
            └ P2 与 P3 都写 app.js ⇒ 必须串行（P2 先）
```
| 片 | 写域 | 依赖 | 可并行 |
|---|---|---|---|
| **P1** 新模块 + 单测 | `js/block-index.js`（新）、`scripts/benchmark/maintenance/block_index_test.js`（新）、`index.html`（+1 行） | 无 | ✅ 立即 |
| **P2** 薄壳化 + 5 调用点 | `js/app.js` | **P1** | ❌ 与 P3 串行 |
| **P3** 消费者迁移 M6/M7/M8 | `js/app.js`、`js/edit-handler.js` | **P1+P2** | ❌ 与 P2 串行 |
| **P4** 写入门禁 + deprecated | `scripts/benchmark/surface/check_line_attr_gate.js`（新）、`surface/README.md` | 无 | ✅ 立即 |

> **只有 P1 与 P4 能真并行**；P2→P3 是一条串行链（同改 `app.js`）。**禁止两个 agent 同时写 `app.js`。**

## P1 · `block-index.js` + 单测（**必须最先**）
**写域**：`src/memoria/ui/static/app/js/block-index.js`（新）、`scripts/benchmark/maintenance/block_index_test.js`（新）、`index.html`（在 `<script src="/app/js/ast.js">` 之后插一行）。

**必做约束（R1/R2/R4/R5/R6）**
1. **UMD 双出口（硬性）**：现有模块全是 `window.X = (function(){…})()`，实测 `node -e "require('…/source-gen.js')"` 报 **`window is not defined`** ⇒ 照抄该范式会让"能被 NewSurface import + 能 node 单测"两条同时落空。写成 `if (typeof module!=="undefined") module.exports=…; else window.MemoriaBlockIndex=…`。
2. **R1** `id = hash8(kind+"\0"+blockSrcText) ⊕ 出现序 n`，纯函数；文件头注释**写死**「被编辑的块 id 会变；消费者禁止跨该块自身被编辑持 id」。
3. **R2** 本文件是**唯一索引实现**，`stampBlockLines` 将来只做投射。
4. **R4** `startsValid` 显式标志 + 懒重建；`commit()` 检测行数变即置 invalid。
5. **R5** 账本 `estHeight/realHeight` 放**侧表** `_metrics: Map<id,…>`，**不进 `BlockHandle`**。
6. **R6** `isFrozen(id)` 方法，不放进 handle。

**验收**
```bash
node scripts/benchmark/maintenance/block_index_test.js   # 全 PASS、exit 0
node --check src/memoria/ui/static/app/js/block-index.js
```
**断言（≥12 条）**：A1 同文本同 id（I3）｜A2 改一块 ⇒ **其余块 id 全不变**（C1）｜A3 同文档两相同块 ⇒ id 不同｜A4 `blocksInRange` 与朴素 `filter(b.start<=end&&b.end>=start)` 在 200 组随机上**逐条一致**｜A5 一行多块 ⇒ 回多个、`{outermost}` 只回最外层｜A6 `upsert` 后 `get` 立即可见｜A7 行数不变 ⇒ `startsValid` 保持 true（**打字不重建**）｜A8 行数变 ⇒ 失效+重建正确｜A9 `commit().removedIds` 正确｜A10 `isFrozen` 是方法、非字段｜A11 `_metrics` 不泄漏进 handle｜A12 纯函数性（两次调用同 id）。

**回滚**：`git checkout -- index.html && rm block-index.js block_index_test.js`；无人引用，零运行时影响。

## P2 · `stampBlockLines` 薄壳化 + 5 调用点（**依赖 P1**）
**写域**：仅 `js/app.js`。

**必做**
1. 按符号 `function stampBlockLines` 定位；**删掉 8 类正则启发式**，改 4 步：`beginStamp()` → 逐块 `upsert({id, srcLineStart:b.srcLine, srcLineEnd:b.srcLineEnd,…})` → `commit()` → 保留 `window.__blockLineMap` 作为**兼容投影**。
2. **R3 硬约束**：`data--src-line`/`-end` **只允许在 `upsert()` 内写**；薄壳**不得**自己 `setAttribute` 这两个属性。
3. 5 个调用点**零改**（符号 `stampBlockLines(`）；若签名须变，加可选参数、不改形参顺序。
4. `keepLineMap` **保留形参**（免改调用点），内部改由 `upsert` 的 O(1) 承担。

**验收**
```bash
node --check src/memoria/ui/static/app/js/app.js
node scripts/benchmark/maintenance/block_index_test.js
python scripts/benchmark/surface/run_probe.py --kb tests/probe-kb --label p2-stamp
```
**断言**：B1 探针 **C2/C3/C4 保持绿**｜B2 `window.__blockLineMap` 与 `--label before-p2` 基线**逐项相等**｜B3 `grep -c 'setAttribute("data--src-line' app.js` **不新增**｜B4 启发式已删（grep 该正则 = 0）。

**回滚**：`git checkout -- app.js`（P1 模块留用无害）。

## P3 · 消费者迁移 M6/M7/M8（**依赖 P1+P2，与 P2 串行**）
**写域**：`js/app.js`（M6/M7）、`js/edit-handler.js`（M8）。

**必做（按符号定位）**
- **M6** `function previewElOverlapsRange` → 体内改 `BlockIndex.blocksInRange(startLine,endLine)`；**保留函数名与签名**。
- **M7** `layoutPreviewRangeBand` 里的 `preview.querySelectorAll("[data--src-line]")` → `blocksInRange` + 直接 `handle.domEl`。
- **M8** `edit-handler.js` 两处 `querySelector('.-src-block[data--src-line="'+srcLine+'"]')`（用 `srcLine` 符号定位）→ `BlockIndex.atSrcLine(srcLine,{outermost:true})`，**顺手修掉"假定行号唯一"隐患**。

**验收**
```bash
node --check src/memoria/ui/static/app/js/app.js && node --check src/memoria/ui/static/app/js/edit-handler.js
python scripts/benchmark/surface/run_probe.py --kb tests/probe-kb --label p3-consumers
python scripts/benchmark/surface/run_interaction.py --label p3-consumers
```
**断言**：C1 **C6/C7 不新增红**、C8 转绿或保持｜C2 **交互金标准 11/11 与 legacy-baseline 一致**｜C3 KP 四链路可跑（hover/跳转/静默标记/错误高亮）｜C4 `grep -c querySelectorAll.*data--src-line app.js` 与 `grep -c 'data--src-line="' edit-handler.js` **均为 0**（证明真迁移）。

**回滚**：`git checkout -- app.js edit-handler.js`。

## P4 · `data--src-line` 写入门禁 + deprecated（**可立即并行**）
**写域**：`scripts/benchmark/surface/check_line_attr_gate.js`（新）、`scripts/benchmark/surface/README.md`。**不写 `src/**`**（避免与 P2/P3 抢 app.js）。

**必做**
1. 门禁扫 `js/**/*.js`：对 `data--src-line`/`-end` 的**任何 `setAttribute`** 必须落在 `block-index.js` 的 `upsert` 函数体内（**文件白名单 + 函数体归属**双判定），否则非零退出并打印违规 `文件:行号`。
2. 允许清单初始仅 `block-index.js`。**P2 若在 app.js 保留写入 ⇒ 必须显式登记豁免并写理由**（宁可红，不可静默绿）。
3. `README.md` 记：属性 = **派生投影（deprecated）**、唯一真源 = BlockIndex，并列出待迁移的 12 个消费者（设计 §1.4）。

**验收**
```bash
node scripts/benchmark/surface/check_line_attr_gate.js              # 期望 exit 0
node scripts/benchmark/surface/check_line_attr_gate.js --self-test  # 反向验证：注入违规必须 FAIL
```
**断言**：D1 干净仓 exit 0；**反向验证**——临时给 `app.js` 加裸 `setAttribute("data--src-line",…)` ⇒ 必须**非零退出**（不做反向验证的门禁不算门禁）｜D2 跑完 `git status` 无新增改动（只读）。

**回滚**：纯新增，`rm check_line_attr_gate.js` 即回滚。

## 交付总验收（4 片合并后 Lead 把关）
```bash
node --check src/memoria/ui/static/app/js/{block-index,app,edit-handler}.js
node scripts/benchmark/maintenance/block_index_test.js
node scripts/benchmark/surface/check_line_attr_gate.js
python scripts/benchmark/surface/run_probe.py --kb tests/probe-kb --label phase1-final
python scripts/benchmark/surface/run_interaction.py --label phase1-final
```
**阶段 1 通过条件（全绿，任一红即止步不进阶段 2）**
1. `block_index_test.js` 全 PASS（≥12 条）；
2. 门禁 exit 0 且反向验证有效；
3. **C1 由"未测"转绿**；C2/C3/C4 不回退；C6/C7 不新增红；C8 转绿或保持；
4. 交互金标准 11/11 与 `legacy-baseline` 一致；
5. **P1 性能闸（设计 §7.1）**：交付「每键 DOM 写入次数」读数；打字时延**不倒退**（现 26.5ms / 预算 16ms）。**变慢 ⇒ 阶段 1 判失败。**

## 已知风险
| # | 风险 | 片 | 处置 |
|---|---|---|---|
| 1 | 写成 `window.X=` ⇒ 单测跑不了、"可 import"落空 | P1 | 硬性 UMD 双出口 |
| 2 | P2/P3 同改 `app.js` | — | **串行**（P2 先），禁并发 |
| 3 | `upsert` 每键多 2 次 `setAttribute` 拖慢打字 | P2 | 值真变才写 + 交付时延读数，触发性能闸 |
| 4 | 行号并行漂移 | 全部 | 一律按符号 grep |
| 5 | `_previewBlockSig`（约 14049）与 `id` 语义重叠被误当 id | P2 | id 用 `hash8`，签名保持原样，**不合并** |
