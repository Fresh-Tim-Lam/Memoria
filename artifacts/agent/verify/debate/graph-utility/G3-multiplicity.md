# G3 · 多重出现：placement（嵌入） vs inbound（被引用）

> **议题**：G3（人 2026-10-27 追加口径）——「"一段文字出现在多处"还指被多个地方引用或者链接（不管什么类型的链接）」。
> **本文件范围**：只做 G3（placement / inbound / 派生相似度），不碰 L3/G4，不 commit，不改产品代码，不写 `docs/design`。
> **基线快照**：`kg-retrieval/round2/frozen/数字通信原理`（26 md / 11 sidecar；MANIFEST `a4beaedc…`；taken_at 14:09:46）。
> **产物**：本文件 + `G3-inbound-baseline.json` + `scripts/G3-multiplicity.py`（只读 frozen；产品 `collect_graph_data` 真值 + sidecar 原文）。
> **证据分级**：A 论文/标准｜B 本仓代码/运行数据｜C 优秀开源/产品文档｜D 语料（**D 不作设计依据**）。

---

## 0. 摘要（先给人看）

1. **人追加的这条要求把"多重出现"拆成两个不同机制，必须分开建模与计数**：
   ```
   A placement（出现/嵌入）  同一内容被物理放进多个视图/层级
                            —— 例：同一段定义同时属于「第一章总述」和「期末复习清单」
   B inbound（被引用）        多个地方用【任意类型】的链接指向它
                            —— contain / extend / reference / contrast / 甚至无断言的 see-also
   A 是【同一内容的多重归属】；B 是【多个来源对它的断言/指向】。二者语义完全不同。
   另有第三类：派生相似度（co-citation / bibliographic coupling）——【不是边】，禁止物化。
   ```
2. **四条规则已写死**（§2）：① 一个 identity 可有多个 placement + 多个 inbound（各自带类型/来源/版本）；
   ② inbound **按类型分组呈现**，不能拉平成邻居列表；③ 禁止把"共同引用同一目标"变成边；
   ④ 派生相似度**按需计算、永不物化**（否则 O(N²) 伪边）。
3. **本仓现状（§4，62 边）**：被多个地方指向的节点 **4 / 357 = 1.12%**（在"被边覆盖的 56 节点"里占 **7.1%**）；
   且这 4 个多重入边节点是**混合来源**的结果（例：`ideal-sampling` = extend + reference；`ch2-10-cosine-…` = 1 contain + 3 reference）；
   **extend 自身永远不造成入度 ≥2**（21 条 extend 的 target 全不同，各 1 入）。
   links[]（正文锚点）**3 条 / 3 个 target / 5 个 instances，0 个 target 被 ≥2 条链接指**；另有 **1 个孤儿 target**（`通带抽样定理`，指向不存在的 identity）。
   **placement 多重归属机制在本仓不存在**（一个 KP 只属于 1 个文件/区间；multi-file identity = 0）⇒ A 类现状 = 0。
4. **派生相似度若物化的爆炸证据（§4.4）**：62 条边立即产生 **57 对 co-citation 伪边**（57/62 ≈ 92% 于现有边数）
   与 9 对 bibliographic coupling；清洗退化边后仍是 55 对。⇒ 规则④不是洁癖，是防图爆炸。
5. **与 GUE-IDEA-004/005 的关系（§5）**：
   - **004 退化边（8 条）**：会给"被引用计数"注入 8 条伪入边（同名/OCR 目标），并在按 target 统计时制造同名歧义；但**不改变 ≥2 入度的节点数**（4 个不变）；co-citation 从 57→55。
   - **005 extend 混合**：21 条 extend 的入度全为 1 ⇒ 对"多重入边"数字无影响；但**若按原枚举分组**，"extend"这一组会把顺序/前置/实例混在一起 ⇒ 人要求的"按类型分组"必须按 **G2 的谓词（P1–P5/D）** 分组，不能按 `contain/extend/reference` 枚举。
6. **同名碰撞 ≠ 多重出现**：36 组 / 114 个 KP（31.9%）同名，但那是**身份歧义**（不同 identity 名字相同），既不是 placement 也不是 inbound；不能拿来当"多处出现"的证据。

---

## 1. 概念拆分（A / B / 派生）

### 1.1 三个概念

| 概念 | 定义 | 断言？ | 方向 | 典型载体 | 本仓现状 |
|---|---|---|---|---|---|
| **identity** | 稳定身份（`kp_id`）；内容可变、身份不变 | — | — | sidecar `knowledge_points[].id` | 357 个 |
| **A placement** | identity 的内容被**物理放进**某个视图/层级（同一内容 ∈ 多个容器） | 无断言，只有归属 | 容器 → 内容 | transclusion / FRBR 的多重体现 / 复习清单 | **0**（无机制） |
| **B inbound** | 某个来源**指向** identity（任意链接类型） | 可能带断言（语义边）或无断言（see-also） | 来源 → identity | links[]（anchor/instances）、edges[]（type） | 62 edges + 3 links |
| **D 派生相似度** | 由"共同指向/共同被指"**算出来**的相似关系 | 无（不是断言） | 对称 | co-citation / bibliographic coupling | 可算，未物化 |

### 1.2 为什么必须拆（三个反例）

```
反例 1：把"同名"当"多处出现"
  36 组同名 / 114 个 KP（如「线性相位理想低通滤波器」5 个不同 id）——
  这是【身份歧义】，不是同一内容的多重归属，也不是被多处引用。
  若按名字统计"出现次数"，会把 114 个不同 identity 误算成"同一条内容出现 114 次"。

反例 2：把"contain 的父子"当"被引用"
  contain 是结构派生边（子节点被父节点"包含"）。每个子节点天然有 1 条入边，
  但这不代表它"被多处引用"；它是【层级归属】。若把它算入 inbound 断言计数，
  "被引用"就退化成"有父节点"（本库 33 条 contain 会让 33 个节点凭空有入边）。

反例 3：把 co-citation 变成边
  两个节点被同一来源引用 ⇒ 算"相似"，但**不构成它们之间的断言**。
  若物化：一个来源引 k 个目标就产生 C(k,2) 条伪边；本库 62 边立即多出 57 对（§4.4）。
```

### 1.3 计数口径（先写死，防混用）

| 计数 | 定义 | 本库示例 |
|---|---|---|
`placement_count(identity)` | placement 记录条数（同一内容被放进几个容器） | 现状恒 1；无多重 |
`inbound_occurrence(identity)` | 指向它的**链接实例**数（同一 link 的多处 anchor 各算一次） | 本库 links instances=5（3 条 link） |
`inbound_assertion(identity)` | 指向它的**语义边**数（按身份去重；不含 contain 结构边、不含 reference 无断言） | 29 条作者边分布在 24 个 target |
`inbound_structural(identity)` | contain 结构入边数（归属，不参与"被引用"语义计数） | 33 |
`inbound_distinct_source(identity)` | 不同来源 identity 的个数（去重同源多类型） | 4 个节点 ≥2 |
`derived_similarity` | 查询时算，不入图 | co-citation 57 对 |

---

## 2. 四条硬规则的落地（数据模型 / 呈现 / 禁止物化）

### 2.1 规则①：一个 identity 可以有多个 placement + 多个 inbound

**数据结构（建议，G5 再定稿；这里只给 G3 的约束）**

```
Identity {
  identity_id: string            # = kp_id；稳定，不随内容变
  content_hash: sha256?          # 只做 stale/去重，不做身份（E1-1）
}

Placement {                      # A 类：同一内容被放进多个视图/层级
  placement_id: string
  identity_id: string
  container: { kind: collection|view|outline|checklist, ref: string }
  char_range: { start:int, end:int }   # 在该容器中的物理位置
  source_version: string               # 该容器的版本（manifest sha / 文档版本）
  valid_from: datetime?; valid_to: datetime?
  note?: string
}

Inbound {                        # B 类：多个来源指向它
  inbound_id: string
  identity_id: string            # 被指向者
  edge_type: enum(P1..P5/D)      # 语义谓词（G2 定义），不是 contain/extend/reference 原枚举
  or no_assert: bool             # reference/see-also
  source_identity: string        # 断言/指向的来源（另一 identity）
  source_version: string
  assertion_source: {file:string, char_range:{start,end}}   # 断言在原文哪一段（provenance）
  valid_from: datetime?; valid_to: datetime?; superseded_by: string?
  instances: [{file, line}]      # link 锚点实例（可多处）
}
```

**约束**
- 同一个 `(identity_id, edge_type, source_identity, source_version)` 只算一条 inbound（去重）；
- `inbound` 与 `placement` **分开存储**（不同表/不同字段），不允许用一个扁平 `neighbors[]`；
- 每条 inbound 必须能回原文（`assertion_source`）；无 provenance 的 inbound 只能是"链接实例"（低可信）。

### 2.2 规则②：呈现必须按类型分组

```
人看的目标不同：
  「我属于哪」    → placement 分组（按容器类型：章节/复习清单/视图），带容器名与范围
  「谁引用了我」  → inbound 分组（按语义谓词：组成/前置/例证/对比/无断言；结构包含单列）
禁止：把 placement 与 inbound 混成一个"邻居"列表；禁止把 contain 结构入边混进"被引用"。
分组内排序：source 版本/时间 → source 名称；跨组不排序。
计数展示：每组给 count + distinct_source 数；无断言的 see-also 单列并标"非断言"。
```

**示例（本库真实数据）**
```
identity: ideal-sampling（低通信号理想抽样）
  placement:  [1] 教材/03 · KP 区间 L26-L53（现状：唯一）
  inbound（语义）: 前置 ← sampling-theorem?（待 G2 判）；对比 ← natural-sampling（reference）
  inbound（结构）: contain ← 低通和带通信号抽样定理（父节）
  （注意：不要把 contain 混进"谁引用了我"）
```

### 2.3 规则③：禁止把"共同引用同一目标"变成边

- **co-citation**（两篇文献被同一文献引用）与 **bibliographic coupling**（两篇文献引用同一文献）都是**派生相似度**，不是断言。
- 若把"A 与 B 都引用 C"写成边 A—B，则：
  1. 语义错误（A/B 之间没有断言）；
  2. 图爆炸（一个 C 被 k 个来源引用 → C(k,2) 条伪边）；
  3. 与 G2 的"该边该不该存在"判据冲突（这种边无法给断言/消融，只能给相似度）。
- 规则：**永不物化**；只在查询时计算并标注"派生相似度（非断言）"。

### 2.4 规则④：派生相似度按需计算、永不物化

```
查询时 API（示意）：
  related_by_co_citation(identity_id)      -> [{peer, shared_sources[], count}]
  related_by_bibliographic_coupling(identity_id) -> [{peer, shared_targets[], count}]
缓存键：(corpus_identity, graph_version, algorithm, params)；图变即失效。
复杂度：Σ_v C(k_v,2)（k_v = 指向 v 的来源数）；**永不写入 edges[]**。
```

**本库物化爆炸证据**：62 条边 → co-citation 57 对（见 §4.4）；若未来图扩到 1 万边、平均入度 3，物化伪边量级 ≈ Σ C(k,2) ≈ 边数 × 平均入度/2 级别，**不是线性增长**。

---

## 3. 学科定名与文献（用于检索；不是本仓结论）

| 概念 | 经典来源 | 与本议题关系 | 证据状态 |
|---|---|---|---|
| **Co-citation** | Small, H. (1973). *Co-citation in the scientific literature: A new measure of the relationship between two documents*. JASIS 24(4):265–269 | 定义"两文献被同一文献引用"= 派生相似 | A（经典；DOI `10.1002/asi.4630240406`，本轮未联网核一手页） |
| **Bibliographic coupling** | Kessler, M. M. (1963). *Bibliographic coupling between scientific papers*. American Documentation 14(1):10–25 | 定义"两文献引用同一文献"= 派生相似 | A（经典；本轮未联网核一手页） |
| **Transclusion / 超文本** | Nelson, T. H. (1965) *Complex information processing…*（ACM）；"transclusion"见 Nelson, *Literary Machines* (1981) | A 类（嵌入/多重归属）的原始概念 | A（经典；本轮未联网核一手页） |
| **FRBR** | IFLA (1998). *Functional Requirements for Bibliographic Records*；[LoC FRBR 页面](https://loc.gov/aba/pcc/conser/summit/FRBR-summit.html) | 同一作品可有多个"体现/载体"（多重归属的 bibliographic 模型） | A（LoC 页面已核；IFLA 原文未逐页读） |
| **Backlink model** | Obsidian / Roam / Logseq 的 backlinks 面板（产品文档/源码） | 人看"谁引用了我"的 UI 先例；需看它们**是否把共引变边** | C（产品文档；本轮未读源码，标"待核"） |
| **Provenance/assertion** | W3C PROV-O (2013) https://www.w3.org/TR/prov-o/ | 每条 inbound 带 assertion 来源（G1/G2 已提） | A（W3C 标准） |
| **Meta-path** | Sun et al. 2011 PathSim（G1 已引） | **不用于 co-citation**；meta-path 是类型化路径相似度，不是引用相似 | A（G1 已列） |

> **诚实**：Small 1973 / Kessler 1963 / Nelson 1965 是领域公认经典，但本轮只凭知识引述（未逐一联网核 DOI/页码）；
> 若要进决策包，需按 G1 的 A 源纪律补一次 arXiv/DOI 核验。FRBR/PROV-O 的 URL 已核。

---

## 4. §X 引用多重性（inbound multiplicity）——本仓现状对照

> 数字来自 `G3-inbound-baseline.json`（产品 `collect_graph_data` 62 边 + sidecar 原文 links/edges；frozen 副本；pre_build）。

### 4.1 62 条边的入边分布（回答"被多个地方指向的节点有几成"）

| 口径 | 被边覆盖节点 | 入度 ≥2 节点 | 占全部 357 节点 | 占被覆盖节点 |
|---|---|---|---|---|
| **全部 62 边** | 56 | **4** | **1.12%** | 7.1% |
| 去 8 条退化 contain（54 边） | 48 | 4 | 1.12% | 8.3% |
| 只作者边（26 sidecar + 3 link = 29） | 24 | 4 | 1.12% | 16.7% |
| 只 extend（21） | 21 | **0** | 0% | 0% |
| 只 contain（33） | 33 | **0** | 0% | 0% |

**入度分布（62 边）**：入度 1：52 个；入度 2：3 个（`ideal-sampling`、`scalar-quantization`、`dm-pcm-error-comparison`）；
入度 4：1 个（`ch2-10-cosine-plus-narrowband-gaussian`）。
⇒ **"被多个地方指向"的节点 = 4 个（1.12%）**；其中 0 条多重入边来自 extend（extend 是链，每个 target 入度 1）。

### 4.2 links[]（正文锚点；人说的"不管什么类型的链接"）

| 指标 | 值 |
|---|---|
| link 条目 | 3 |
| link 实例（instances，即"出现位置"） | **5** |
| 被 link 指向的 target | 3 |
| 被 ≥2 条 link 指向的 target | **0** |
| 孤儿 target（指向不存在的 identity） | **1**（`通带抽样定理`） |

⇒ **"被多处链接"在本库也几乎没有**：3 条 link 分布在 3 个 target 上，0 个多重；且有 1 个孤儿 target（inbound 目标不存在 ⇒ 必须能显示"悬空引用"，不能静默丢）。

### 4.3 identity 多重 placement 现状

```
multi-file identities = 0   （357 个 KP 各只属于 1 个文件/区间）
⇒ A 类（同一内容多重归属）在当前模型【不存在机制】。
注意：
  · slices（G1 的视图层）是"派生视图"，不是 placement（它从同一 range 派生，不产生多重内容）；
  · 同名 36 组/114 KP 是身份歧义（见 §1.2 反例 1），不是 placement。
```

### 4.4 若物化派生相似度（证明必须按需算）

| 口径 | co-citation 对（targets sharing a source） | bibliographic coupling 对（sources sharing a target） |
|---|---|---|
| 全部 62 边 | **57** | 9 |
| 去 8 退化 contain（54 边） | 55 | 9 |
| 只作者边（29） | 9 | 6 |

⇒ 62 条边一旦物化 co-citation，会多出 **57 条伪边**（≈ 现有边数的 92%）；来源集中在 contain 的 fanout（一个父节点多个子节点）。
这直接证明规则③④：**派生相似度不能进 edges[]**。

---

## 5. 与 GUE-IDEA-004 / 005 的关系（会不会影响"被引用"计数）

| 现象 | 对 inbound 计数的影响 | 处置 |
|---|---|---|
| **004 退化 contain（8 条：7 同名 + 1 OCR 错名）** | ① 给 8 个（同名/OCR）target 各注入 1 条**伪入边**；② 若按名字统计，会与同名 identity 混淆；③ 不改变"入度 ≥2 节点数 = 4"；④ co-citation 57→55（2 对消失） | inbound 记录必须带 `valid`/`degenerate` 标记；统计"被引用"时排除退化边；退化边只作 known-bad 夹具（G2 已用） |
| **005 extend 语义混合（顺序/前置/实例）** | 21 条 extend 的入度全为 1 ⇒ 对"多重入边数"**无影响**；但**按枚举分组会错**：把顺序当断言、把前置/实例混成一组 | 分组必须用 **G2 谓词（P1–P5/D）**；D（仅顺序）组单列且不计入断言；G2 人判结果决定每条 extend 归哪组 |
| **contain 结构入边（33）** | 若混入"被引用"会虚增 33 个入边（每个子节点 1 条） | 单列 `inbound_structural`；"谁引用了我"只显示断言组；结构组单独显示"所属" |
| **同名 36 组 / 114 KP** | 若按名字 join 会把不同 identity 合并 | inbound 一律按 **identity_id**，不按名字 |

---

## 6. 规则落地验收（G3 → G5 的实现前检查清单）

```
C1 数据模型：placement[] 与 inbound[] 分开；inbound 每条带 {type(谓词), source, source_version, assertion_source, valid_from/to}
C2 呈现：inbound 按谓词分组；contain 结构入边单列；无断言 see-also 单列并标"非断言"；不给扁平邻居列表
C3 禁止物化：图数据（edges/nodes）中不得出现 co-citation / bibliographic coupling 派生的边；
           相关查询必须是 API 现算，响应标 "derived-similarity, not assertion"
C4 去重：同一 (identity, type, source, source_version) 只算 1 条 inbound；link 多实例只增 occurrence，不重复算 assertion
C5 悬空：inbound 目标不存在 ⇒ 显示"悬空引用"（本库 1 例：通带抽样定理），不得静默丢
C6 退化：degenerate inbound 标记并可排除（GUE-IDEA-004）
C7 计数口径三类分开：placement_count / inbound_occurrence / inbound_assertion（§1.3）
```

---

## 7. 开放问题（给 Lead/人裁）

| # | 问题 | 说明 |
|---|---|---|
| U1 | **A 类（placement/transclusion）产品上要不要？** | 本仓当前无机制；若"同一段定义同时属于第一章总述与期末复习清单"是真实需求，需 G5 数据模型支持（多容器归属）；否则 A 类可只做概念记录 |
| U2 | "同一内容"如何判定？ | 内容哈希（E1-1）只做 stale，不做身份；A 类的 identity 复用还是新建 placement？需裁 |
| U3 | inbound 是否把 `reference`（无断言）计入"被引用"？ | 建议：**可显示、不计入断言计数**；否则 see-also 会污染"被引用次数" |
| U4 | 悬空 inbound（孤儿 target）怎么处理？ | 建议显示"悬空引用 + 来源区间"，不自动建 identity（防凭空造点） |
| U5 | co-citation/bibliographic coupling 是否需要给用户看？ | 建议先做 API + 调试面板，不进主图（避免"派生相似度被误当关系"） |
| U6 | 跨库 inbound（A 库引用 B 库）？ | 本库无跨库边；若未来支持，需 source 带 kb 身份 |

---

## 8. 证据身份与复跑

```text
基线快照   round2/frozen/数字通信原理（MANIFEST a4beaedc…；taken_at 14:09:46；26 md/11 sidecar）
产物       G3-inbound-baseline.json   sha256 EEF5459147CA6F9CFFDCAEDFE567297BC8DC6353DDB4BE7A7BA0B12B8E6D4CD6
脚本       scripts/G3-multiplicity.py sha256 E892BD44551897790AD713D5BE604C243DED62E92308779C7F2F1761A1AE1EA9
台账       ideas-ledger.md（GUE-IDEA-008/009 新增） sha256 9FFA2B6B99134A61CF09DA9FBE12AFFAAF52569A3BCFD38B73FE18FD5C4B1BF7
复跑       python scripts/G3-multiplicity.py
确定性     同命令连跑 2 次，JSON 无 timestamp 字段 ⇒ 逐字节一致（已验 deterministic=True）
本文件     未 commit；未改产品代码；未写 docs/design
```
