# S10 agent 设计知识点与语义边提案 B（独立复核方）

> **依据**：`multilevel-graph-vision.md` U-1..U-35（重点 U-12/13/14/19/21/22/25/27/32）；上游冻结 S0（`241b1e1e…`）、S1（`6676c71d…`）、S2（`92bb0041…`）、S3（`0ca4ea0e…`+ADDENDUM-1）、S4（`2576f6c8…`）、S5（`7f4c4515…`）、S6（`40f12e5f…`+ADDENDUM-1）、S7（`70dd8748…`）、S8（`c6a135ff…`）、S9（`…`），不得违反；本场 `S10-charter.md`。
> **性质**：独立复核方提案；写作时**未读** `S10-kp-proposal-A.md`（尚未落盘）；写完再对照，差异见 `S10-objections.md`。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S0–S9 冻结。
> **日期**：2026-11-04（Asia/Shanghai）。

---

## 0. 总原则

1. **agent 只写 KP/语义边，不写事实正文**；事实 `.md`/sidecar/manifest 只读；写只通过 `propose_write`（plan）→人工确认→apply；**0.5 不做**。
2. **不得编造**：每个 KP/边必须有可机检 source anchor（file/line/anchor）与证据；无源/歧义/低置信 ⇒ 不 apply（proposed/unknown）。
3. **语义边只用 S0 `E_relation` 允许类型**；结构/引用边不得被标成 semantic/语义分数；S10 不新增边类型；S1 registry 只增不删。
4. **双引用/curation**：source/target 引用 + assertion source；`curated_by/curated_at`；人工确认；undo。
5. **写路径 atomic/backup/undo/audit/零写入失败**；批处理可回滚；不得绕过 propose_write。
6. **冲突/去重/合并**显式；冲突保留 vs 合并人工裁决；历史 append-only。
7. edition 变化 ⇒ S9 索引失效/重建；S6 cache；旧 KP/边保留可回滚。
8. 质量 golden/抽检/置信阈值；S8 消费，S10 不自动 apply；隐私不写正文/PII。
9. S1 只增不删；S2 clustering 由 run 重建，不写簇；0.5 边界明确。

### 0.1 覆盖矩阵（U + S0–S9）

| U# | 落点 | U# | 落点 |
|---|---|---|---|
| U-12/U-13 | 语义/非严格连通=S10-2/S10-4 | U-14 | 语义小群=S10-4 |
| U-19 | KP/簇=S10-2/S10-10 | U-21 | 多归属=S10-10 |
| U-22 | 更深/扩展=S10-8 | U-25 | 注释/curation=S10-5 |
| U-27 | 边存无/类型=S10-4 | U-32 | 规模/质量=S10-9 |
| S1 registry | 只增不删=S10-10 | S2 clustering | 不写簇=S10-10 |
| S6 | 单一真源/写=S10-1/S10-6 | S9 | 失效/重建=S10-8 |

---

## S10-1 定位与边界

**规则**：S10 规范 **agent 如何提出/写入 KP 与语义边**；agent 不写事实正文、不修改产品 sidecar 直写；写路径 = `propose_write` plan（含证据/目标）→人工确认→apply；v1/0.5 **不做自动 apply**。
**形式化/机检**：
```
S10 可写：KP（curated overlay）+ 语义边（curated overlay）
不可写：.md 正文、manifest、sidecar 原始事实、S2 cluster/run、registry（除 S1 允许的追加）、VM/frame
写入口唯一：propose_write → plan → human_confirm → apply/undo
0.5：S10 不实现/不自动/semantic 生成；人工确认后才可 apply（未来版本）
```
**反例**：agent 直接改 md/写 sidecar；绕过 plan 写 curated；0.5 自动 semantic；写 cluster。
**边界**：无源；低置信；冲突；权限不足；S10 未启用。
**U 映射**：U-12、U-25、U-29、U-34。
**建议裁决**：冻结只写 KP/语义边/不写事实/唯一 propose_write/0.5 不做。
**证据等级**：A（S6-1/S6-10；S0 D-3；S7-1）+ R。

---

## S10-2 KP 定义/粒度/字段

**规则**：KP = **可标注的语义单元**（一个可独立引用/断言的命题或概念），附 source range；粒度：
```
最小：一个可断言子句/概念（>=1 句/1 公式）；
最大：一个 section 内连续文本（不跨 section，除非显式跨节引用）；
默认：一句/一个定义/一个命题；不得整篇/整节当一个 KP（除显式章节 KP）
```
**字段**：
```
KP{
  kp_id: canonical (source_anchor + normalized_label hash),
  title, aliases[], summary?, source_refs[{file,line_start,line_end,anchor}],
  range{start,end}, status∈{proposed,accepted,rejected,merged},
  confidence:0..1, curated_by?, curated_at?, curated_version?,
  evidence_refs[], parent_section?, tags?[]
}
```
- kp_id 由 anchor+label 确定性派生；同 anchor/label 不重复；title/alias 可多语言；summary 必须来自源或显式生成（生成需标 `summary_generated=true`）。
**机检**：字段/类型；kp_id 可复算；range 在文件内；anchor 存在；粒度边界；不整节；summary 来源标记。
**反例**：一个 KP 覆盖整篇；无 anchor；title 编造；kp_id 随机；summary 当事实。
**边界**：section 超长；跨节引用；公式/图；多语言。
**U 映射**：U-12、U-13、U-19、U-25。
**建议裁决**：冻结 KP 定义/粒度/字段/id/来源标记。
**证据等级**：A（S0 KP/ref；S6 DataSource anchor）+ PI（粒度阈值）。

---

## S10-3 KP 抽取/生成

**规则**：
```
输入：md/sidecar（只读）+ 可读结构；输出 KP 候选，每个带 source anchor/range。
不得无源生成；每个 KP 至少一个 source_ref；summary 生成须标 generated。
去重：canonical(anchor+normalized_title/alias) 相同 ⇒ 合并候选（不重复 KP）。
低置信：confidence<阈值（S10 配置）⇒ status=proposed/不自动 apply；人工复核。
幂等：同输入同 candidates/kp_id；重跑不重复写。
```
**机检**：anchor 存在/行号范围；无源=FAIL；去重键；低置信不 apply；2x 幂等；candidate 不写事实。
**反例**：编造段落；无 anchor；低置信自动写；重复 KP；同输入不同结果。
**边界**：短 section；表格/代码；多语言；sidecar 缺失。
**U 映射**：U-12、U-13、U-14、U-32。
**建议裁决**：冻结抽取输入/锚/无源禁止/去重/低置信/幂等。
**证据等级**：A（S6 DataSource；现有 plan/apply 只读）+ R。

---

## S10-4 语义边设计

**规则**：
```
允许类型 = S0 E_relation 已允许（contain(structural/semantic), reference, extend）；不新增类型
语义边：label=semantic 或 contain(semantic) 仅当有 source assertion + 两端 KP；
方向：source→target（含方向字段；无向边用 direction=both）；
证据：evidence_refs（两端 source_refs + assertion/file/line/anchor）；confidence。
结构/引用边不得标 semantic/不得进入语义分/簇（S2 semantic-only）。
边可解释：edge_reason/assertion。
```
**机检**：类型枚举 S0；semantic 边必须有 evidence + 两端 KP；结构/ref 不被当 sem；方向合法；confidence；S2 输入只 semantic。
**反例**：新增未冻结类型；contain(structural) 标 semantic；无证据边；方向缺失；用 reference 当语义。
**边界**：跨节/跨文档；有向/无向；多证据；冲突边。
**U 映射**：U-14、U-15、U-27。
**建议裁决**：冻结允许类型/语义条件/方向/证据/禁止结构伪装。
**证据等级**：A（S0 E_relation；S1；S2 semantic-only）+ R。

---

## S10-5 双引用/curation

**规则**：
```
KP/边必须双引用：
  source_refs（source 端 anchor）
  target_refs（target 端 anchor，边）
  assertion_source（原文断言 file/line/anchor）
curated_by / curated_at / curated_version / decision_id
人工确认：apply 前 human_confirm（S10 设计；0.5 UI 未来）
undo：每次 apply 产生 undo record（before/after），可回滚；审计。
```
**机检**：双引用非空；assertion source 可解析；curated_by/at；human_confirm 记录；undo 可逆；审计。
**反例**：无 target 引用；无 assertion；无 curated_by；undo 不可回滚；人工确认缺失。
**边界**：多源；跨文档；人工拒绝；批量 undo。
**U 映射**：U-25、U-27、U-32。
**建议裁决**：冻结双引用/curated_by/at/人工确认/undo/审计。
**证据等级**：A（S6 anchor；S7 refs）+ R。

---

## S10-6 写路径

**规则**：
```
唯一入口：propose_write(plan{ops[],evidence[],actor,edition}) 
→ validate（schema/anchor/权限/冲突/预算）
→ human_confirm（S10 未来；0.5 不实现）
→ apply（atomic：全成功或零写入）
→ backup（before snapshot）+ audit + undo record
```
- 禁止直接写 md/sidecar/registry；写 curated overlay/产品 curation 允许路径；失败零写入（atomic）；批处理可回滚；同 plan 幂等；不自动 apply。
**机检**：唯一入口；plan schema；atomic 失败零写入；backup/undo/audit；human_confirm；批量回滚；不绕过。
**反例**：直接写 sidecar；部分成功；无 backup；无 audit；跳过 propose_write；自动 apply。
**边界**：冲突/权限/budget/中断/重复 plan。
**U 映射**：U-25、U-29、U-32。
**建议裁决**：冻结 propose_write/atomic/backup/undo/audit/零写入/human_confirm。
**证据等级**：A（S6-1/S6-8；现有 plan/apply）+ R。

---

## S10-7 冲突/去重/合并

**规则**：
```
重复 KP：同 anchor+normalized label/alias ⇒ 合并候选；不同来源同义 ⇒ alias/merge proposal，人工裁决
冲突断言：保留双方 + 来源与置信；不静默覆盖；人工裁决
同义边/重复边：canonical(source,target,type,label) 去重；冲突方向/类型 ⇒ 保留 + 标记
合并：append history（before/after/decision_id）；可 undo；不丢来源
```
**机检**：去重键；冲突保留/人工决策；history/undo；无静默覆盖；同义边去重。
**反例**：静默覆盖旧 KP；重复边；合并丢来源；无历史。
**边界**：多语言别名；跨文档同义；矛盾来源；批量合并。
**U 映射**：U-12、U-14、U-21、U-25。
**建议裁决**：冻结去重/冲突保留/合并/历史/undo。
**证据等级**：A（S6/S2 id；现有 curation）+ R。

---

## S10-8 版本/失效/回滚

**规则**：
```
S10 写入 ⇒ edition/curated_version 变化 ⇒ S9 索引失效/重建；S6 cache 失效；
旧 KP/边保留（history）；可回滚到 before（undo/edition restore）；
S1 registry 只增不删（若涉及维度）；S2 run 重新生成，不写旧 run；
S10 不直接改 S9 索引；由失效事件触发。
```
**机检**：edition 变化；S9 失效/重建；旧数据保留；undo/rollback；S1 只增；不写 S2 run；审计。
**反例**：写后不失效 S9；覆盖旧数据；回滚丢历史；S10 改 S1 删除；写 S2 run。
**边界**：批量/部分失败/回滚/旧 edition；多 KB。
**U 映射**：U-21、U-22、U-32。
**建议裁决**：冻结 edition/失效/重建/保留/回滚/S1/S2 边界。
**证据等级**：A（S6/S9/S1/S2）+ R。

---

## S10-9 质量/评估

**规则**：
```
指标：KP precision/recall（golden）、边 precision/recall、引用完整率、
      人工抽检通过率、低置信比例、冲突率、重复率、错误类型分布。
golden：edition-pinned，标注 KP/边/证据；测试集不参与调参。
置信阈值：低于阈值不 apply；抽检 N/批；S8 消费；S10 定义阈值。
```
**机检**：指标公式；golden/sha；抽检记录；阈值；错误类型；S8 消费；不自动 apply。
**反例**：无 golden；人工抽检缺失；低置信自动写；S10 用 S8 阈值改算法。
**边界**：无 golden；小样本；多 KB；多语言。
**U 映射**：U-12、U-14、U-32。
**建议裁决**：冻结质量指标/golden/抽检/阈值/S8 消费。
**证据等级**：A（S8-12）+ PI（阈值）。

---

## S10-10 与 S1/S2 交互

**规则**：
```
S1 registry：S10 不改维度注册表删除/改名；只增不删；KP 不直接写 registry（registry 管维度）；
S2 clustering：KP/语义边写入后，S2 run 按新 edition 重建；S10 不写 cluster/membership；
  多归属由 S2 membership；cluster 稳定性归 S2；
S10 不做 cluster 合并/拆分。
```
**机检**：S10 无 registry 删/改；无 cluster/membership 写；S2 重建由 run；S1 只增。
**反例**：S10 改 registry 删维度；写 cluster；合并簇；把 KP 当簇。
**边界**：多归属；无簇；S2 未运行；旧 edition。
**U 映射**：U-10、U-11、U-21、U-31。
**建议裁决**：冻结 S10/S1 只增/S2 只重建不写簇/多归属。
**证据等级**：A（S1/S2 冻结）+ R。

---

## S10-11 失败/降级/隐私

**规则**：
```
无源/歧义/低置信/冲突/超预算/权限：
  fail-closed / propose_only；不自动 apply；可见错误/原因；不编造
隐私：不写正文/PII 到 KP summary；summary 受源限制；审计只存 id/anchor/counts
失败零写入；重试有限；人工确认才 apply。
```
**机检**：失败码/可见；不 apply；无正文/PII；audit；零写入。
**反例**：无源编造；低置信自动；隐私正文入 KP；失败半写。
**边界**：无源/歧义/冲突/预算/权限。
**U 映射**：U-13、U-14、U-27、U-32。
**建议裁决**：冻结失败/降级/隐私/不自动/零写入。
**证据等级**：A（S6/S7 失败；S8-6 隐私）+ R。

---

## S10-12 与 0.5 边界

**规则**：S10 设计**不在 0.5**；0.5 不做 agent 自动 semantic/写图；未来版本实施；人工确认 UI 才可 apply；不影响 0.5 DoD；S10 设计不夹带 S7/S9 改动。
**机检**：0.5 DoD 无 S10 写；feature flag；人工确认；S10 不影响 S8；不夹带。
**反例**：0.5 顺手自动 semantic；S10 改 0.5 DoD；无人工确认。
**边界**：0.5 只读；S10 未来；旧 KB。
**U 映射**：U-29、U-32、U-34。
**建议裁决**：冻结 S10 不在 0.5/人工确认/不夹带。
**证据等级**：A（S6-12 0.5 边界）+ R。

---

## 附：S10 章程预注册判据自检

| 判据 | 本提案 |
|---|---|
| 只写 KP/语义边/不写事实/0.5 | S10-1/S10-12 |
| KP 定义/粒度/字段/锚 | S10-2/S10-3 |
| 语义边类型/方向/证据/置信 | S10-4 |
| 双引用/curated/人工确认/undo | S10-5 |
| 写路径 atomic/零写入/审计 | S10-6 |
| 冲突/去重/合并/历史 | S10-7 |
| edition/S9/回滚 | S10-8 |
| 质量/golden/抽检 | S10-9 |
| S1/S2 交互 | S10-10 |
| 失败/隐私 | S10-11 |
| 0.5 边界 | S10-12 |
| A/B 差异逐条 | 见 `S10-objections.md` |
| 不写产品代码/契约/commit | 本文件只写设计 |

> 独立声明：本文件写作时未读 `S10-kp-proposal-A.md`（尚未落盘）；差异与判断见 `S10-objections.md`，逐项列不合并。
