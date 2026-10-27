# KG 驱动的 agent 检索：v0 设计（0.5.x）

> **状态**：草案（技术部分已定；R7 五项待用户确认）
> **来源**：六方研讨会 Phase 1–4 全部产物（`artifacts/agent/verify/debate/kg-retrieval/`）
> **裁决依据**：`PHASE4-RULINGS.md`（R1–R7）
> **日期**：2026-10-27

---

## 0. 一句话

**索引的价值不是给 agent 一张目录，而是让它少走几个来回。**

这句不是口号，是实测结论：section 标题骨架（373 条 / 2,227 tok）hit@1 55% / hit@3 70%，
而无索引直接 grep 是 55% / 70% —— **骨架索引在冷启动不比 grep 更好**。
所以本案设计的一切都围绕「减少往返（iterations）+ 消除错切片」，而不是「提供索引」。

---

## 1. 问题定义（用实测数字，不用形容词）

### 1.1 现状
```
真库 数字通信原理（26 md / 11 sidecar / 358 KP，14:09:46 快照）
  21 轮 / 116 iterations / 135 tool calls
  prompt 合计 5,724,271；均值 272,584/轮；峰值 845,926 = 1M 的 84.6%
  缓存命中率 94.17%（不是"低"）
  compaction 8 次；每次压缩后命中率掉到 61–84%
  费用 2.4453 元 = 输出 66.4% + 未命中 24.7% + 命中 8.9%
  工具结果单次最大：grep 34,249 字符 > read_document 8,857 字符
```

### 1.2 索引现状（"尚未建立"的精确含义）
```
覆盖：14 章中仅 4 章有 KP；61.8% 教材 token 无 KP
粒度：93.3% KP 起点就是 markdown 标题行 ⇒ 标题切分，不是学习单元
      教材 KP 中 69.0% >1200 字（全部 KP 为 24.6%）
质量：同文件重名 28.6%（102 条）；非知识点 5.0%（18 条）；OCR 脏名 11.2%
      description 落盘：大库 0/357（机制在 AAA_Vocab 可用：25/134）
锚点：snippet 不唯一 37.0%；前插 50 行后 18.8% 静默钉错且 ok=True
      已坏 8 条（含 1 条 range 反转 span=0）；fresh 98.9%
```

### 1.3 一个代码级缺陷（本次研讨会最重发现）
```
read_kp 连 range_ok 都不检查：kb.py#L344-L351 用 `start_line or 1`
⇒ range 解析失败时【静默返回第 1 行内容】，不报错
⇒ 现状不是"锚点漂了还能勉强用"，是"坏了返回错内容且无感知"
```

---

## 2. 设计原则

```
P1 单一身份：kp_id 是唯一语义身份，不新建第二套 id
P2 视图分离：切片是 kp_id 的视图（kp_ids[]），slice_id 只做视图键
P3 锚点自证：只有 anchor_verified 的切片才允许进入 agent 上下文
P4 结构不做相关度：结构负责"范围/顺序/邻接"，相关度交给 lexical/semantic
P5 预算硬约束：任何注入上下文的东西都有 token 上限，模型不负责自救
P6 失效可降级：不确定时退回"读原文 + 标 unverified"，绝不静默使用
P7 价值可证伪：每项收益必须有 A/B（尤其"少往返"）
```

---

## 3. 数据模型

### 3.1 三层定义（Phase 3 语料方修订后写死）
```
identity  = sha256(file + normalize(text))      ← 只做 stale / dedup / cache 键
location  = (file, char_start, char_end)        ← 每次 build 重算，【不是身份】
anchor    = (section_number, ordinal_in_section, identity)
                                                 ← 跨 build 重定位，唯一可信锚
说明：单 hash 必然不唯一 —— 实测 14,395 块中 unique 13,260 ⇒ 重复 7.9%
      （`$$` / `<details>` / `## 目录`），所以 anchor 必须 composite。
      插入 40 行后 893/938 块 identity 保留（95.2%）⇒ "平移"只发生在 location。
```

### 3.2 索引条目（视图层）
```yaml
slice:
  slice_id: string        # 视图键，仅缓存/定位用，禁止承载语义
  file: string
  section_number: string  # 从标题编号解析（373 标题中 300 可解析）
  char_range: [int, int]  # location，每次 build 重算
  identity: sha256        # 块内容身份
  kp_ids: [string]        # 必须非空（映射孤儿率门禁 <20%）
  description: string     # 【必填】问句型 ≤80 字，含"何时不该读"
  note: string            # 【可选】人读笔记，可空，不参与机器判据
  anchor_verified: bool   # 只有 true 才允许进 agent 上下文
  source_hash: sha256     # 源文件 hash，用于 stale 检测
```

### 3.3 身份关系
```
kp_id（语义锚，不变）
  ├─ FSRS 卡（105/114 张以 kp_id 为锚）
  ├─ 图谱节点 id
  ├─ 引用锚
  └─ slice_ids[]（视图，可重建，不承载语义）
```

---

## 4. 锚点 gate（R1，P0）

### 4.1 三个判据（缺一不可）
```
① range_ok == False                 → ANCHOR_UNRESOLVED（拒绝返回内容，不得返回第 1 行）
② snippet 全文出现 >1 且无法消歧     → AMBIGUOUS_ANCHOR
③ end 非唯一 / 超预算 / 解析失败      → 夹到下一同级标题（不得留 span=0 或反转）
```

### 4.2 消歧手段（按优先级）
```
A 用 heading 结构消歧（同一 section 内的同名 snippet）
B 用出现序号 + 前文 hash 消歧（记录 context_hash）
C 仍无法消歧 ⇒ 标 AMBIGUOUS_ANCHOR，不进 agent 上下文
```

### 4.3 写入路径（必须）
```
正文写入 ⇒ 同一事务内重算受影响的 range ⇒ 重算后立即自检（range_ok / 反转 / span=0）
禁止：事后补一条、下一次 build 再修
（现场事故已证明"维护成功可以继续坏着"：start 修 fresh 了，end="$$" 仍坏）
```

---

## 5. 检索路径（R3 + R6）

### 5.1 分层（预算硬约束）
```
L0  库概览        ≤300 tok（现状 kb_overview 267）—— 只给文件清单 + KP 数
L1  单文件索引    ≤800 tok（复用 OUTLINE_MAX_TOKENS）+ cursor 分页
L2  候选切片      ≤4,000 tok（snippet 600 / section 4000 / read_document 2000 行）
禁止：全库 358 KP 摘要整包（≈21.4k tok）
```

### 5.2 结构的作用位置（不走 RRF）
```
检索前：确定性过滤（章节范围 / section_number 序）
检索后：有界跳数扩展（hops ≤2，超界标 not_shown）
排序：  确定性结构序（章序 / section_number），不是相关度
融合：  若必须与 lexical/semantic 合并 → 分数加权线性 + 单列 A/B，不叫 RRF 臂
```
依据：外部四类真实实现（HippoRAG=PPR / GraphRAG=社区摘要 / LightRAG=按 id 轮转+配额 /
XERJ=跳数遍历独立 API）**没有一个是 RRF**；RRF 只有 rank，表达不了邻接与顺序。

### 5.3 工具结果预算（R4 降为 P1，但仍需做）
```
单次工具结果有 token 上限；超限给 locator-only + 记账
优先收紧 grep（单次最大 34,249 字符，GREP_MAX_MATCHES=250 无 token 预算）
错误信息永不截断（截断错误会让人误判失败原因）
```

---

## 6. 建索引方法（R6 + 语料 R9/R10/R13）

### 6.1 冷启动 C0–C4（替代"按书序建深"）
```
C0 导入时只建 section 骨架（373 条 ≈ 2,227 tok，0.4% 全书）
C1 首问先用 grep / read 定位（骨架 ≈ grep，所以不期待骨架救命）
C2 命中 → lazy 深化该章（建切片 + 写 description）
C3 失败（实测 30–50%）→ 读 top-3 候选章 / 让用户点章 / 用 @file 指路
C4 禁止冷启动按书序建深（真实 4 库实测：书序覆盖 9.7% / 15.2% / 100% / 89.8%，
   前沿优先 2 胜 2 平 0 负）
```

### 6.2 深化顺序（有信号时）
```
score = 3×复习卡 + 2×会话读 + 1×批注 → argmax
证据：复习卡 cards.json 的 file 字段与实际使用 top 章 2/2 完全一致
mtime 有噪声（ch8 rank2 因编辑非学习）；sidecar mtime 不可用（反映建索引非使用）
全 0 → 回退书序（仅作兜底）
```

### 6.3 切分规则
```
① section_number 给语义边界（标题比块稳定：编辑后 section 数不变）
② 块 identity 给精确边界与缓存键（改一行只改 1 块，但 7.9% 块 hash 重复 → composite）
③ 单元 >3,000 tok 先按下级编号拆、再按块边界拆（保留 1 块重叠）
④ 不切公式块 / 表格块（3,557 纯公式块 / 984 图片块只作附件）
⑤ 无编号文件退化为 page 模式
```

### 6.4 不该建索引的语料
```
OCR/PPT 提取的 img/*：过"可描述"闸门仅 22.5%，42.1% 硬性不可描述，32 组同名全在这里
⇒ 不按知识点建；或只建 page 级 + source_kind=slide + 禁入"先读索引"路径
目录 / 答案页：标 nav，不写知识描述
```

---

## 7. description 规范（R5）

```
必填 `description`（机器读）：
  · 问句型，≤80 汉字
  · 必须含：回答什么问题 / 判别关键词 / 【何时不该读】
  · 必须写成【可比较】的（"与 X 的区别是…"），不是流水摘要
  · 禁止：截正文前 N 字（实测 hit@3 53.8% → 38.5%）
实测：改写成问句型后 hit@3 76.9%（合格线 ≥70%）

可选 `note`（人读）：
  · 可空、不阻塞落盘、不参与任何机器判据
  · 落盘率与 description 【分开计】
  · 用途：词源 / 易错 / 记忆法（Vocab 25 条真实用例即此类）
```

`description` 落盘率门禁：**≥70%**（当前大库 0/357、Vocab 25/134；机制可用但大库未落）。

---

## 8. 验收（R4）

### 8.1 门禁（确定性、全量、可复跑）
```
M4 锚点健康      fresh ≥99%；inverted = 0；anchor_verified 覆盖率（基线：98.9%/8 坏）
M5 陈旧         增量 = 0；静默坏 = 0
M2 有害误路由    = 0（同名碰撞必须消歧；风险基线 77.6% / 32 组 102 条）
M12（新增）      索引上线后 Δhit ≥ −5pp（不得破坏前缀缓存）
```

### 8.2 观测（不作通过门槛）
```
P0 观测  峰值 prompt（基线 845,926 = 1M 的 84.6%）
P1 观测  iters/answer（基线 116/21 = 5.524）、tool calls（135）、
         compaction 次数（8）、单次工具结果 max（grep 34,249 字符）
```

### 8.3 已废弃的门禁（不得复活）
```
M1 hit@3 ≥70%     n=13 时 Wilson95=[49.7,91.8] ⇒ 不可证（需 n≥158）→ 降 smoke
M3 可判性 ≥85%    n=20 时 C=0 上界 16.1% ⇒ 不可证（需 n≥230）→ 降 smoke
iterations 作主 KPI  证据为算术外推，非测量 → 候选，需三臂实验
```

### 8.4 判决性 A/B（必须有 Arm-1 对照）
```
Arm-0 现状（grep + read_document）
Arm-1 【只注入索引 token 但不改行为】← 分离"索引 token 成本"与"索引行为收益"
Arm-2 索引驱动（L0→L2 + anchor gate + description）
指标：iters/answer、错切片率、答对率（盲评 rubric）、峰值 prompt、成本
判据：Arm-2 vs Arm-0 —— iters 降 且 答对率不降；Arm-1 用于归因
```

---

## 9. 不做（明确边界）

```
· GraphRAG 全局检索（机制不匹配：97.5% 读同一章；610K 数字来自 Legal 跨文档多跳）
· RAPTOR 递归摘要树（建树成本无公开数据）
· Self-RAG / Adaptive-RAG（需训练管线）
· 语义切分（问题在"边界不可靠"，不在"切分算法")
· 新建第二套语义 id
· 以"提高缓存命中率"为目标（已 94.17%；改 Δhit ≥ −5pp 否决条件）
· 搬 AOCI 完整重写回环（可搬：证据身份 / 哈希基线 / 软失效）
· 把 M1/M3 小样本阈值当门禁
```

---

## 10. 待用户确认（R7）

| # | 事项 | 影响 |
|---|---|---|
| 7.1 | KP 边界会被重算（教材 69% KP >1200 字需切开） | 用户可见的知识点边界变化（id 不变） |
| 7.2 | sidecar 增加 `description` / `note` 字段 | 用户数据文件结构变化 |
| 7.3 | 0.5.x 价值主张改为「省往返」而非「给目录」 | 版本目标与验收口径 |
| 7.4 | 索引构建时机（C0–C4：骨架 + lazy 深化） | 首次使用体验与 token 花费 |
| 7.5 | 新增 `step/usage` 埋点 | 把 iteration 成本从算术变实测 |

---

## 11. 未决 unknowns（实现前必须回答）

```
U1 anchor_verified 覆盖率（加 gate 后多少可用？若 <50% 需先建重建管线）
U2 KP→切片 映射孤儿率（阈值 20%）
U3 Arm-2 vs Arm-0 的 iters A/B（R6/R7 的判决实验）
U4 description 落盘率能否 ≥70%
U5 同名碰撞消歧方案（77.6% 风险）
U6 note 填写率与作者负担
U7 Δhit 实测（索引更新对前缀缓存影响；外部无公开研究）
U8 冷启动 C0–C4 的首次提问质量
```

---

## 12. 证伪条件（设计失败长什么样）

```
F1 Arm-2 的 iters 不比 Arm-0 低 ⇒ "省往返"主张失败 ⇒ 放弃索引路线，
   退回"工具结果预算 + 检索栈能力暴露"这一层
F2 答对率下降 ⇒ 立即回滚（任何 token 节省都不值得）
F3 anchor_verified 覆盖率 <50% ⇒ 锚点重建成为独立大工程，索引延后
F4 description 落盘率长期 <70% ⇒ 索引退化为纯结构骨架（价值大幅缩水）
F5 Δhit 跌破 −5pp ⇒ 索引不得进前缀，只能经工具结果（设计需改）
```
