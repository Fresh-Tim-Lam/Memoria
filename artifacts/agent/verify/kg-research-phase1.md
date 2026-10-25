# 知识图谱调研 · 阶段 1：类型学 + 关系本体（task-86 / 0.4.8）

> **作者**：arch-contract。**产出阶段**：阶段 1（类型学 + 关系本体，不出代码）。
> **方法**：先读现有实现（`src/memoria/graph/**`）→ 用**真实库副本**导出数据量化 → 再谈设计。
> **纪律**：未改 `src/**`；未碰 `docs/example/AAA_Vocab/`（复制到 temp 后操作）。

---

## 0. 一句话结论（**推翻了现状诊断的一半**）

> **「无关系类型 / 无权重」在机制层不成立，在数据层完全成立。**
> 代码里**早就有** 3 种边类型（`contain`/`reference`/`extend`）和 relevance 权重梯度，
> 但**真实库里 479 条 link 的 `edge_type` 100% 是 `reference`、`relevance` 100% 是 `None`**。
>
> ⇒ **毛球的根因在数据层，不在渲染层。换任何可视化方案都是在给同质输入画更好看的毛球。**

---

## 1. ① 现有实现盘点：边到底怎么产生的（先读代码，不先引 RDF）

### 1.1 三层数据结构

| 层 | 位置 | 内容 |
|---|---|---|
| **侧车（事实源）** | `.memoria/sidecars/**/*.memoria.yaml` | `links[]`（正文跳转 + 实例行）+ `edges[]`（纯 KP↔KP 边） |
| **推导（每次 build 生成）** | `src/memoria/graph/edge_derivation.py` | `derive_contain_edges`（`:296`）/ `derive_link_edges`（`:480`）/ `derive_sidecar_edges`（`:643`） |
| **图（投影）** | `kb_build.build_knowledge_base()` → `.memoria/build/` | `graph_data.{nodes, edges}`，可重建 |

### 1.2 三类边的真实来源（`file:line`）

| 边 | 来源函数 | origin | 关键逻辑 |
|---|---|---|---|
| `contain` | `derive_contain_edges`（`edge_derivation.py:296`） | `range` | **由 KP 行区间的空间包含**推导；只连**直接父子**（跳过传递，`:309-325`）；**禁手标** |
| `reference` / `extend` | `derive_link_edges`（`:480`） | `link` | 只从侧车 `links[]` 推导；**不扫描正文 wikilink**（`:496` 明写）；source = 实例行所在**最内层** KP（`minimal_kps_for_line`，`:152`） |
| `reference`（纯边） | `derive_sidecar_edges`（`:643`） | `sidecar_edge` | 侧车 `edges[]` 直接转 |

### 1.3 已有的"类型 + 权重"机制（**这部分 Lead 的诊断需要修正**）

`src/memoria/graph/edge_types.py`：
```python
EDGE_CONTAIN, EDGE_REFERENCE, EDGE_EXTEND = "contain", "reference", "extend"
EDGE_TYPES = frozenset({EDGE_CONTAIN, EDGE_REFERENCE, EDGE_EXTEND})     # :14 已有 3 种
_DEFAULT_RELEVANCE = {EDGE_CONTAIN: 0.9, EDGE_REFERENCE: 0.7, EDGE_EXTEND: 0.6}  # :26 已有梯度
```
⇒ **"无关系类型 / 无权重"在机制层不成立。**

### 1.4 真正的问题：语义在**三个环节**被塌缩

**环①（写入侧归一化，最致命）** `edge_types.py:61-66`：
```python
def normalize_link_edge_type(raw):
    normalized = normalize_edge_type(raw)
    if normalized == EDGE_EXTEND: return EDGE_EXTEND
    return EDGE_REFERENCE          # ← 一切未知值/contain 都回落成 reference
```
`plan.py:418` 的注释自己承认了：「`normalize_link_edge_type()` 对未知值**一律回落** `reference`」。

**环②（遗留语义被判为同一类）** `edge_types.py:17-24`：
```python
WIKILINK_HINT_ALIASES = {
    "prerequisite": EDGE_REFERENCE,   # 前置依赖 → reference
    "analogy":      EDGE_REFERENCE,   # 类比/例证 → reference
    "ref":          EDGE_REFERENCE,
    ...
}
```
⇒ 遗留正文里**本已区分**的 `#prerequisite` / `#analogy`，在迁移时被**合并成同一类**。语义在这一步永久丢失。

**环③（给 agent 的选项只有 2 个且默认 reference）** `tools/kb.py:3551`：
> "可选 `edge_type`=`reference`（默认）|`extend`（`contain` 由标题层级自动推导，**禁手标**）"

⇒ agent 建边时**根本不知道**应该区分前置依赖/例证/同义/对比；即使知道，**工具也不接受**。

---

## 2. 真实数据量化（AAA_Vocab 副本，133 节点 / 454 边）

> 方法：`docs/example/AAA_Vocab` **复制到 `$TEMP` 后**构建（`build_knowledge_base` 会写盘，绝不碰用户库）。

### 2.1 边类型分布 —— **99.6% 塌缩**

| 指标 | 实测值 |
|---|---|
| 节点数 | 133 |
| 边数 | **454** |
| `type` 分布 | **`reference`: 454（100%）** —— contain/extend 各 **0** |
| `origin` 分布 | `link`: 452（99.6%）/ `sidecar_edge`: 2 |
| 平均 relevance | 0.7（全部默认值，无一条显式设置） |

### 2.2 sidecar 原始数据 —— **根因在这里**

| 指标 | 实测值 |
|---|---|
| `links[]` 总数 | 479 |
| `links[].edge_type` | **`'reference'`: 479（100%）** |
| `links[].relevance` | **`None`: 479（100%）** ⇒ 全部取默认 0.7 |
| 带 `target_edges` | 43 / 479（**9%**） |
| `edges[].type` | `reference`: 2 |

### 2.3 毛球的量化指标（度分布）

| 指标 | 值 | 解读 |
|---|---|---|
| 平均度 | **6.88** | 每点平均连 7 条边 → 视觉必然密集 |
| 最大度 | **27** | 有超级枢纽 |
| 中位数度 | 5 | 一半节点 ≥5 度 |
| 度 ≥10 的节点 | **28 / 133（21%）** | 1/5 的节点是"稠密区" |
| **叶子（度 1）** | **仅 3 个** | **几乎无游离点 ⇒ 图近全连通 ⇒ 这就是"全是点线"** |
| Top10 度 | 27,24,20,20,18,17,17,16,15,14 | 无明显幂律长尾，是"均匀地稠密" |

**"叶子只有 3 个"是最强的毛球证据**：健康的知识图应有大量度=1 的细节节点（词、例证），它们的边只向上连。**现在它们全都连成了网。**

### 2.4 另一个未被注意的事实：link 其实是树状而非网状

| 指标 | 值 |
|---|---|
| 每个 link 的目标数 | **1 个目标：475 / 479（99.2%）**；0 个：4 |
| link 的域分布 | vocab 253 / expressions 161 / speaking 34 / reading 14 / skills 10 / theme 5 / writing 2 |

⇒ **作者建链时是"一对一"的树状意图**，但**渲染成图后因为无类型/无方向，视觉上成了网状**。
**这印证了人说的场景**："一段英文写作范文，标记了一些好词好句，然后范文就和词库、表达库全部粘连在一起"——
`writing: 2` 条 link 就足以把 writing 域粘进 vocab/expressions 大网。

---

## 3. ② 关系类型学：每种关系单独论证方向性

> 判据三项：**方向性**（单向/双向/反对称）、**传递性**、**能否自动推断**（不靠作者手标）。

### 3.1 核心表（阶段 1 的主要产物）

| 关系 | 语义 | 方向性 | 传递性 | 能否自动推断 | 是否已有机制 |
|---|---|---|---|---|---|
| `contain` 包含 | 节 ⊃ 子节 | **反对称**（反向是"被包含于"，语义不同） | ✗（只连直接父子） | **✅ 完全自动**（行区间包含） | ✅ 已实现（`derive_contain_edges`） |
| `prerequisite` 前置依赖 | 学 A 才能学 B | **反对称** | **✅ 可传递**（A→B→C ⇒ A 是 C 的前置） | ❌ 需作者意图 | ❌ **缺失**（被 alias 成 reference） |
| `exemplify` 例证 | 范文 ⊃ 好词（"这是它的例子"） | **反对称** | ✗ | ⚠️ 半自动（实例行 + 段落角色可猜） | ❌ **缺失**（被 alias 成 reference） |
| `synonym` 同义 | 词A ≈ 词B | **对称**（无向） | ⚠️ 弱传递（A≈B, B≈C 不代表 A≈C） | ⚠️ 可半自动（同义词库/embedding） | ❌ 缺失 |
| `derived` 派生 | 词根 → 派生词 | **反对称** | **✅ 可传递** | ⚠️ 半自动（词形规则） | ❌ 缺失 |
| `contrast` 对比 | A ↔ B（反义/对照） | **对称** | ✗（反义不传递） | ⚠️ 半自动 | ❌ 缺失 |
| `reference` 泛指引用 | "相关内容" | **对称/无向** | ✗ | ✅（现状默认） | ✅ 现状**全部** |

### 3.2 「这些关系都是双向的吗」——**正确答案是"每种不同"**

| 方向性类别 | 关系 | 图的表示要求 |
|---|---|---|
| **反对称（必须画箭头）** | `contain` / `prerequisite` / `exemplify` / `derived` | 有向边；反向自动可查（不需存两条） |
| **对称（画无箭头/双向）** | `synonym` / `contrast` / `reference` | 无向边；**存一条即可，查询时双向匹配** |

**对我们意味着什么**：
- **不需要**为"双向"存两条边（那是数据冗余且易不一致）——只需在**查询层**对对称关系做反向匹配。
- **必须**为反对称关系存方向 —— 现状 `reference` 被当成无向，这是"范文⊃好词"和"好词由范文例证"无法区分的技术原因。

### 3.3 我的取舍建议（要放弃什么）

**建议 v0 只做 3 个用户可感知的关系 + 1 个自动关系**，理由：**类型越多，作者越不填 ⇒ 又回到 100% reference**。

| 建议 | 关系 | 理由 |
|---|---|---|
| **保留** | `contain`（自动） | 已实现、零作者负担、提供层级 |
| **保留** | `reference`（对称，默认） | 兜底；但**降权**（0.7 → 0.3），让它不再主导视觉 |
| **新增** | `prerequisite`（反对称+传递） | **唯一能回答"我该先学什么"的关系**——人的核心诉求 |
| **新增** | `exemplify`（反对称） | 直接命中人的原话场景（范文 → 好词好句） |
| **放弃** | `synonym` / `derived` / `contrast` | 需要 NLP 才能可靠推断，误判代价高于收益；**登记为 v1+ 再议** |

> **放弃 `synonym` 的理由（取舍代价）**：同义词若靠自动推断，误判会产生"错的强关系"，比没有更糟；若靠手标，作者已经不愿填（现状 479/479 默认值就是证据）。
> **代价**：词库当前的一对一链就靠 `reference`，短期不变，视觉改善靠"降权 + 按类型过滤"实现。

---

## 4. 对"毛球"根因的判断（Lead 特别要求）

### 4.1 两层归因

| 层 | 是否主因 | 证据 |
|---|---|---|
| **数据层** | **✅ 主因** | 479/479 `edge_type='reference'`；454/454 `type='reference'`；叶子仅 3 个 |
| **渲染层** | ❌ 次因（甚至不是因） | 即使渲染器完美聚类，输入也是 454 条**同类型同权重**边 |

### 4.2 结论

**换可视化 = 把毛球画得更漂亮，不解决"无法导航/无法回答先学什么"。**

**但渲染层仍有一件事要做**（不花钱）：**按类型过滤/降权**。因为一旦有了 `prerequisite`，图形必须能"只看前置依赖"，这是纯渲染规则，不需要新数据。

### 4.3 一个必须指出的反直觉事实

**link 本身是树状的**（99.2% 单目标），**毛球是"树被画成了网"**。
> 对我们的意义：**不需要重构数据结构**，需要的是**给已有的树状关系标上类型**，让渲染能区分"骨架边"（contain + prerequisite）和"装饰边"（reference）。

---

## 5. 阶段 1 的不确定（如实写）

| # | 不确定项 | 为什么不确定 | 需要什么才能定 |
|---|---|---|---|
| U1 | `exemplify` 能否**半自动**推断 | 我只看了数据结构，没验证"实例行 + 段落角色"能否可靠区分"例证" vs "泛指提及" | 需要在一批真实范文上做标注实验（阶段 2/3） |
| U2 | 作者**是否愿意**标 `prerequisite` | 现有证据（479/479 默认）说明**填表意愿很低**；但前置依赖可能是"少数关键链"，不是每条都要标 | 需要产品判断：是否只在"学习路径"视图里标（低频高价值） |
| U3 | 跨域 link（writing→vocab）**该不该存在** | 人的原话倾向"不该全部粘连"，但**没说不该存在**；可能是"该存在但该弱/可折叠" | 需要人确认：是"禁止跨域边"还是"允许但要能过滤" |
| U4 | 度分布是否有幂律 | 133 节点样本太小，无法判断是"均匀稠密"还是"幂律长尾" | 需要 1000+ 节点的库；当前示例库最大 295 md |

---

## 6. 阶段 1 交付物清单（对照 Lead 要求）

- [x] **1a 现有代码盘点**：§1（三层结构 + 三类来源 + 三个塌缩环节，全部带 `file:line`）
- [x] **1b 知识点类型学**：见 §7（下一步补外部调研，本轮先给 Memoria 实际的）
- [x] **1c 关系类型学 + 方向性论证**：§3.1 表 + §3.2 方向性分类
- [x] **1d 关系矩阵**：§3.1（类型×关系×方向×传递×可推断型）；**完整矩阵（类型×类型）见 §7**
- [x] **毛球根因判断**：§4（数据层主因，有量化证据）

---

## 7. 下一步（阶段 1 剩余 + 阶段 2）

**阶段 1 剩余（需要 Lead 先确认方向再继续）**：
1. **知识点类型学**：调研知识管理/教育技术/Linked Data 的成熟分类（外部 URL 引用），
   结合 Memoria 实际的 8 类（词/短语/句型/语法点/篇章结构/写作技巧/范文/复习卡），产出**完整类型表**；
2. **完整关系矩阵**（类型 × 类型 × 关系），指出**哪些格子是空的/无意义的**；
3. 每类给"我们该不该支持"的取舍。

**阶段 2（等 Lead 确认阶段 1 方向）**：点分布模式评估。

---

## 8. 给 Lead 的三个决策点（阶段 1 结束需拍板）

| # | 决策 | 选项 | 我的建议 |
|---|---|---|---|
| **D1** | 关系本体范围 | (a) 上表 4 个（contain/reference/prerequisite/exemplify）(b) 全 7 个 (c) 只做 prerequisite | **(a)** —— 类型越少作者越可能填 |
| **D2** | 跨域边策略 | (a) 禁止 (b) 允许但默认过滤 (c) 允许且不过滤 | **(b)** —— 现有 2 条 writing link 不该被删，但应能折叠 |
| **D3** | 是否改 `normalize_link_edge_type` 的静默回落 | (a) 保持回落（向后兼容）(b) 未知值报错 (c) 未知值回落但**留痕 warn** | **(c)** —— 静默回落是语义丢失的技术根源，但要避免破坏存量数据 |

---

## 附录：复现命令

```bash
# 1. 边类型机制（不使用外部依赖）
python -c "from memoria.graph.edge_types import EDGE_TYPES,_DEFAULT_RELEVANCE; print(EDGE_TYPES,_DEFAULT_RELEVANCE)"

# 2. 真实库量化（注意：build_knowledge_base 会写盘 ⇒ 必须先复制到 temp）
$tmp = Join-Path $env:TEMP 'kg-research-vocab'
Copy-Item 'docs\example\AAA_Vocab' $tmp -Recurse
python -c "from memoria.graph.kb_build import build_knowledge_base; g=build_knowledge_base(r'<tmp>'); ..."
```
