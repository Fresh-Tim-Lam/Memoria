# PROTOCOL v1.1 schema 补丁提案（steward）

> **依据**：Lead `77742852`（F-1..F-5/F-7 已修）+ task-116。
> **范围**：本文件**只出提案**，不改 `PROTOCOL.md` / `freeze-v2.json`（冻结产物归 Lead）。
> **格式**：每项 = 现状 → 建议（可直接抄进 v1.1 的条款文本）→ 为什么现在必须补。
> **提交时间**：2026-10-25T01:0x+08:00

---

## 1. F-2：`unique_evidence_handled` 的正式 schema

**现状**：Lead 已给 26 条裁决全部补键（无 rejected 时 `[]`）；但存在**两种并存形态**：
- R-C7：顶层 `unique_evidence_handled: []` + `rejected[]` 每项带布尔 `unique_evidence_handled: true`；
- 其余 25 条：顶层 `unique_evidence_handled: []`，无 rejected。
`deliberation_quality::dq2` 现在两种都接受（顶层长度匹配 **或** per-item 非空），**这不是漏洞，是 schema 未定**。

**建议（v1.1 条款）**：
```jsonc
// 裁决对象（ruling）固定字段
"unique_evidence_handled": [
  {
    "rejection_index": 0,                  // 对应 rejected[] 下标（必填，唯一）
    "disposition": "accepted|rejected|deferred",
    "reason": "为什么这样处置（deferred 时必须写：核验结论 + 检验者）",
    "deadline": "2026-11-01T00:00:00+08:00" // 仅 deferred 必填
  }
]
```
- **无 rejected 时必须是 `[]`，不得缺键**（缺键 = 无法区分"无需处理"与"漏写"）；
- `rejected[]` 内的 per-item 布尔字段**废弃**（历史记录保留，v1.1 起新裁决不再写）；
- `unique_evidence_handled.length == rejected.length`（id 按下标对齐）。

**为什么现在必须补**：架构辩论会产生大量 `deferred`（J2' 的核心就是"可暂时挂起"）。若 schema 不唯一：
① dq2 无法判断"漏写"；② 无法机检 dq10（超期）；③ 不同人写不同形态，冻结后无法统一重放。

---

## 2. F-3：`objection_ids` 的生成规则

**现状**：26 条 rulings 已带 `objection_ids[]`，但**异议文件本身没有 `object_id`**，映射由 Lead 按 R-C 编号 1:1 推得（例如 R-C1 → `OBJ-obj1`）。
后果：`dq7` 只能检查"ruling 有没有 objection_ids"，**无法检查"每条异议是否都有裁决"**（覆盖方向相反）。

**建议（v1.1 条款）**：
1. Phase 3 冻结时给每条 objection 分配 `OBJ-<member>-<n>`（n 从 1 连续，member ∈ {agent-arch, arch-contract, metrics-baseline, steward}），写进异议文件对应条目（markdown 里用 `object_id: OBJ-...` 行）；
2. Phase 4 每条 ruling 必须列 `objection_ids[]`（可一对多：一个裁决可合并多条异议，但**不得漏**）；
3. Phase 5 生成 `ruling-index.json`：`{object_id → ruling_id}` + `unruled_objects[]`（必须为空）；
4. `dq7`（WARN→FAIL）升级为双向覆盖：`未裁决 object 数 == 0` **且** `rulings 中引用的 object_id 都存在`。

**为什么现在必须补**：本轮 19 条异议的映射是人工一一对应的；架构辩论异议量会更大，**"每条 object 都有裁决"是 task-113 的关闭条件之一**，目前无机器证据。

---

## 3. F-4：`rules-index.json` 的维护规则

**现状**：`rules-index.json` 已产出（36 条），但存在三个可复算的不一致：
1. **rule_id 不唯一**：B4 出现 6 次（B4.a–f 全记成 `B4`）；
2. **计数口径不明**：PROTOCOL §9 写"45 条全部可追溯"，而索引只列 36 条（差在子规则：B4.a–f 6 条 + P2 (a)-(e) 5 条等）；顶层 `- **X**` 规则实际约 30 条；
3. **同步规则缺失**：索引里已有 `protocol_sha256_lf`，但没有"PROTOCOL 变了必须重生成索引"的规则。

**建议（v1.1 条款）**：
```jsonc
// rules-index.json v2
{
  "protocol_sha256_lf": "...",
  "generated_at": "...",
  "rules": [
    {"rule_id": "B4.a", "parent": "B4", "level": 2, "title": "...", "line": 106, "text_sha": "..."}
  ]
}
```
- `rule_id` **全局唯一**（子规则用 `B4.a` 形式；父规则保留 `B4` 一级条目）；
- PROTOCOL 任何修改 ⇒ **必须重新生成** `rules-index.json` 并更新 `protocol_sha256_lf`；不一致时 `deliberation_quality` 下一版新增 dq11 WARN（PROTOCOL 变了索引没变）；
- 数值口径写死：**顶层规则数 = 一级条目数；"45 条"= 一级 + 子规则**，两者都报。

**为什么现在必须补**：`deliberation_quality` 未来要核对"每条 PROTOCOL 规则都能指到来源"（Lead 自创=0 的机检化）。
`rule_id` 不唯一 ⇒ 无法建立稳定映射；没有同步规则 ⇒ 索引会与 PROTOCOL 漂移（与 F-1 同类问题：收据过期）。

---

## 4. F-6：`evidence_ledger` 的适用范围（我的判断与理由）

**现状**：J6' 提到 `evidence_ledger`，但本轮未产出；`deliberation_quality::dq8` 因缺台账只报 WARN。

**我的判断：`evidence_ledger` 从「架构辩论」起强制，本协议辩论不追溯。** 理由（不是"看情况"）：
1. **成本/收益**：本轮辩论的"证据"是 4 份提案 + 4 份异议 + 19 条 ruling，全部已 pinned（sha 可复算）、全部进 git；
   台账能新增的信息≈重复；而架构辩论会出现 `ev:bench:*`（token/性能）与外部资料，**同源去重（E2）与独立来源计数（M2）才真正有消费者**。
2. **追溯代价**：现在补台账等于**重写冻结产物**（与 append-only/J6' 冲突），且需要为 26 条裁决逐条反推 33 条证据的 `independent_group`——这是"为了审计而审计"。
3. **可操作性**：架构辩论开始时冻结物会扩展（新 `freeze` 含问题/判据/类别），同时声明 `evidence_ledger_required_from: "architecture-debate"`；
   dq8 的判据据此二值化：**marker 未声明 ⇒ WARN「无台账（本阶段不适用）」；marker 声明后台账缺失 ⇒ FAIL**。
4. **不可回避的前提**：若架构辩论仍不产出台账，则 M2（"多方一致必须 `independent_roots > 1`"）与 E2（同源去重）**无法执行**——
   所以"架构辩论起强制"不是宽松，而是把义务放到它唯一有意义的地方。

**建议（v1.1 条款）**：
```
J6'.a evidence_ledger 自「架构辩论 Phase 0」起强制；本协议辩论（2026-10-25 冻结）不追溯。
J6'.b freeze 必须声明 evidence_ledger_required_from（phase 名）；未声明视为"当前阶段不要求"。
J6'.c 声明后缺失/坏行 ⇒ deliberation_quality dq8 为 FAIL（不再是 WARN）。
```

---

## 5. F-1 教训写进协议：冻结物自身的完整性必须被检查

**现状**：Phase 0 的 `PHASE1-BASELINE.json` 缺 `question/acceptance_criteria/standards`，直到 Phase 5 我的审计才发现（F-1）。
根因：**规则写了"冻结必须包含 X"，但没有"冻结物必须通过 schema 检查"这一步**——规则只约束人，没约束产物。

**建议（v1.1 条款，加入 Phase 0 门禁）**：
```
Phase 0 出口条件（新增）：
  freeze.json 必须通过 `deliberation_quality` 的冻结检查（dq5）：
  ① question 非空 ② acceptance_criteria 非空且每项有 observable ③ standards 非空且 sha 与磁盘 LF 归一化一致
  ④ expected_categories 非空 ⑤ PINNED-PROPOSALS 的 sha 与磁盘一致
  任一条不满足 ⇒ 不得开启 Phase 1（不是"事后补"，是"不许开局"）。
```
**为什么现在必须补**：F-1 这次是"事后发现+事后补"，若架构辩论继续沿用同样流程，会再犯一次；
把冻结物完整性变成**开局门禁**，成本一次性（几秒机检），收益是整轮裁决的"按哪版标准判"可追溯。

---

## 6. 附：本次顺带发现（提交 Lead 裁决，不擅自改）

1. `rules-index.json` 的 B4 rule_id 重复（见 §3.1）——建议随 v1.1 一起重生成；
2. `PINNED-PROPOSALS.json` 未包含 `freeze-v2.json` 与 `rules-index.json` 自身的 sha（它们也是冻结物）；
   建议 v1.1 把"冻结物集合"定义清楚（PROTOCOL/`freeze`/`PINNED`/`rules-index`/`rulings` 五件套互相引用时避免循环：可用 git blob sha 而非文件自哈希）。
3. `PROTOCOL.md` §9 的"45 条"与 rules-index 36 条的口径需在 v1.1 统一（见 §3.2）。
