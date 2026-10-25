# KG v0 落地报告（task-154）

> **作者**：arch-contract（D 架构/契约）。**依据**：`docs/design/kg-ontology-v0.md`（冻结，13 条裁决）。
> **性质**：按已冻结裁决落地，**不重开设计讨论**。
> **纪律**：不 commit；未碰 `docs/example/AAA_Vocab/**`；未改 `docs/design/kg-ontology-v0.md`。

---

## 0. 结论

**五项全部落地，门禁全绿。**

| # | 交付 | 状态 | 证据 |
|---|---|---|---|
| ① | 统一归一化器（消除枚举不对称） | ✅ | `edge_types.py` 新增 `DERIVE_ONLY_EDGE_TYPES`；`plan.py` 的 `PLAN_EDGE_TYPES` 改为派生 |
| ② | 静默改写留痕 warn | ✅ | `normalize_link_edge_type_with_warn()`，contain/遗留别名/未知值三类留痕 |
| ③ | 一致性断言测试 | ✅ | `tests/test_kg_contract_consistency.py`（10 条，**证红已验证**） |
| ④ | 边使用埋点 | ✅ | `graph-view-2d.js` 补 edge_id；`app.js` 计数 + 只读查询口；6 用例含隐私边界断言 |
| ⑤ | 语料冻结脚本入库 + 三元组规则 | ✅ | `scripts/benchmark/maintenance/kg_corpus_freeze.py` + `kg_evidence_check.py`；`version.md` §4.1 |

**门禁**：pytest **1485 passed**（基线 1475 + 新增 10）/ node --check 59 文件 0 失败 / i18n PASS /
team_audit **FAIL=0** / prompt_drift **FAIL=0**。

---

## 1. ① 统一归一化器（D-KG-04①）

### 做了什么

**问题**：`EDGE_TYPES`（3 种）与 `PLAN_EDGE_TYPES`（2 种）是**两个平级常量**，
描述同一个语义空间 ⇒ 同一枚举两端不对称。

**修法**（把关系**定义化**，不是各写一份）：

```python
# src/memoria/graph/edge_types.py
EDGE_TYPES = frozenset({EDGE_CONTAIN, EDGE_REFERENCE, EDGE_EXTEND})   # 唯一允许集合

DERIVE_ONLY_EDGE_TYPES = frozenset({EDGE_CONTAIN})                    # 只能派生、不可手写

# src/memoria/services/agent/plan.py
PLAN_EDGE_TYPES = frozenset(EDGE_TYPES - DERIVE_ONLY_EDGE_TYPES)      # 算出来的，不再手抄
```

**行为变化**：`PLAN_EDGE_TYPES` 的值**没变**（仍是 `{reference, extend}`），
但它不再是"第二份手抄清单" —— 任何一方增删类型，另一方自动跟随。

> **这符合 D-KG-04①**：裁决明确"去 agent 参数不能消除不对称，因为不对称在常量里"。
> 我 Phase 3 的 OB-06 论证了这一点，本次落地的正是那个论证。

---

## 2. ② 静默改写留痕 warn（D-KG-04② / task-86 D3(c)）

### 做了什么

新增 `normalize_link_edge_type_with_warn()`，`normalize_link_edge_type()` 委托给它。
**返回值语义完全不变**（留痕是增强可观测性，不是语义变更）。

**四类分流 + 留痕矩阵**：

| 输入 | 返回 | 留痕 | 理由 |
|---|---|---|---|
| `reference` / `extend` / 缺省 | 原值 | **无** | 合法值不产生噪音 |
| `contain`（含 `CONTain`） | `reference` | **warn** | 派生专用类型，不可手写 |
| `prerequisite` / `analogy` / `ref` | `reference` | **warn** | **遗留别名，原始语义已丢失** |
| 完全未知值（`完全未知xyz`） | `reference` | **warn** | 未知类型 |

### 关键修复：按**原始输入**判定，不按归一化结果

这是实现中发现的一个隐蔽 bug。`WIKILINK_HINT_ALIASES` 会把 `prerequisite` **先映射成** `reference`，
若按归一化结果判定，`prerequisite` 看起来"合法"⇒ **不留痕**，
但用户表达的"前置依赖"已经丢了。修正后按**原始输入**分流 ⇒ `prerequisite` 正确留痕。

### 实测（构造用例，任务关闭条件 3）

```
WARN: links[].edge_type='contain' 属于派生专用类型（不可手写）⇒ 回落为 'reference'；…
WARN: links[].edge_type='prerequisite' 是遗留别名 ⇒ 回落为 'reference'（原始语义已丢失；v0 类型空间只有 contain, extend, reference）
WARN: links[].edge_type='analogy' 是遗留别名 ⇒ 回落为 'reference'（…）
WARN: links[].edge_type='ref' 是遗留别名 ⇒ 回落为 'reference'（…）
WARN: links[].edge_type='完全未知xyz' 不是已知边类型（允许 contain, extend, reference）⇒ 回落为 'reference'
```
`reference` / `extend` / `None` / `''` ⇒ **零日志**（无噪音）。

---

## 3. ③ 一致性断言测试（D-KG-04③）—— **证红是本项最关键的发现**

### 交付

`tests/test_kg_contract_consistency.py`，10 条断言：
集合恒等关系、派生类型显式建模、可手写集合 = 全部 − 派生、留痕（contain/遗留别名/未知值/合法值零噪音）、
既有 API 行为不变、`EDGE_TYPES` 三元组不变。

### 🔴 证红过程中发现的**真问题**：第一版断言是坏尺子

**第一版**我是这样写的：
```python
def test_plan_writable_types_equal_edge_types_minus_derive_only():
    assert plan.PLAN_EDGE_TYPES == (et.EDGE_TYPES - derive_only)
```

**证红时把 `PLAN_EDGE_TYPES` 改回手抄 `frozenset({EDGE_REFERENCE, EDGE_EXTEND})`，测试仍然全绿。**

原因：当关系正确时，`{reference, extend}`（手抄）与 `EDGE_TYPES - DERIVE_ONLY`（算出）
**值完全相同** ⇒ 值断言**抓不到"有人把它改回手抄"这个形态**。

> 这正是我在 KG 辩论里批判过的模式：**看起来有守卫，其实没有**。

**修法**：新增 `test_plan_edge_types_is_derived_not_hand_copied()`，
用**源码形态判据**（`inspect.getsource` + 取赋值语句）断言
`PLAN_EDGE_TYPES` 的定义必须引用 `EDGE_TYPES` 与 `DERIVE_ONLY_EDGE_TYPES`。

**修正后的证红**：
```
派生实现 ⇒ 10 passed
改回手抄 ⇒ test_plan_edge_types_is_derived_not_hand_copied FAILED（1 failed / 9 passed）  ← 尺子有效
还原     ⇒ 10 passed
git diff 确认无残留
```

---

## 4. ④ 边使用埋点（D-KG-07）—— 长期价值最高的一项

### 裁决原文对应

> 「不是没设计指标，是指标所需数据从未采集」

过去：`nodeClick` 有事件、有消费者、有来源标记，但**标记从未被统计消费**，`edge_id` **从未被记录**。

### 三处落地

| 位置 | 改动 |
|---|---|
| `graph-view-2d.js` `_emit("nodeClick")` | 补 `edge_id`（新增 `_edgeIdForNode()`，返回 `{id, source, target, type, origin}`） |
| `app.js` `onGraphNodeClick` | 调用 `recordGraphInteraction()` —— **来源标记第一次被真正统计** |
| `app.js` 公开查询口 | `window.__memoriaGraphInteractionStats / Snapshot / Reset` |

### 隐私边界（**写进代码注释 + 本报告**，任务硬要求）

```
只记交互标识：node_id / kp_id / 边标识（id/source/target/type/origin）/ 来源 / 时间戳
绝不记：文档正文、用户输入、选区内容、任何可直接识别个人的信息
不落盘、不跨会话、不上报服务端、不建用户画像 —— 纯内存计数器，页面刷新即清零
这是「埋点」不是「遥测」：数据不出页面，只用于回答"点过没有"
```

### 验收（6 用例全过，`artifacts/agent/verify/todo/kg-v0-buried-point-test.mjs`）

```
[OK] 用例1 点击带边节点 ⇒ 节点计数 + edge_id/type/origin 全部记录
[OK] 用例2 重复点击 ⇒ count 累加（不是新条目）
[OK] 用例3 孤立节点 ⇒ 记节点、不造边（不丢事件）
[OK] 用例4 source='graph' 被真正统计（此前只标记不消费）
[OK] 用例5 快照可 dump: {"total":3,"nodeHits":2,"edgeHits":1,"edgeIds":[...],"edgeTypes":["reference"]}
[OK] 用例6【隐私边界】只含标识字段（node_id/edge_id/type/origin/count），无 content/text/input
== RESULT: PASS ==
```

用例 6 是**正向隐私断言**：它扫描统计对象的 JSON，断言不含 `content/text/body/input/selection/clipboard/prompt/answer`
任何一项。**如果将来有人往统计对象里塞文档内容，这条会红。**

---

## 5. ⑤ 语料冻结脚本入库 + 三元组规则（D-KG-01）

### 交付两个脚本

| 脚本 | 作用 |
|---|---|
| `scripts/benchmark/maintenance/kg_corpus_freeze.py` | 冻结语料 + 产出 `triplet` 三元组（schema `kg-corpus-freeze/v2`） |
| `scripts/benchmark/maintenance/kg_evidence_check.py` | **机检**：扫描文档里的量化断言是否都带三元组 |

### 三元组实测输出

```
schema: kg-corpus-freeze/v2
corpus_sha        : b63c658c0d67e5c062cfab35c7e99ed78e4c1cda4463a444dbe3fbd78a42761a
measurement_source: memoria.graph.collector.collect_graph_data() 现场调用
measured_at       : 2026-10-26T00:28:21
三元组完整: True
```

测量结果（含两条后端路径的差异，与冻结文档 §5.2 一致）：
```
head_corpus  （HEAD 已提交，3 个库）：AAA_Vocab nodes=61  edges=154
worktree_now （live，12 个库）      ：AAA_Vocab nodes=134 edges=404   ← 前端实际用的 collect_graph_data 路径
stale_build_snapshot                ：graph.json 2026-10-23 nodes=121 edges=408（旧 cache，标注为非事实源）
```

### 机检脚本自证（证红/证绿）

```
[OK] 带三元组的断言 ⇒ 通过 (failing=0)
[OK] 缺三元组的断言 ⇒ 判红 (failing=1)
== SELF-TEST: PASS ==
```

在真实文档上的判别力（`kg-ontology-v0.md`）：
```
4 条量化断言, 2 条缺三元组
  L116 缺 ['corpus_sha','measured_at']: 454 edges（kb_build 路径 / task-86 快照）
  L117 缺 ['corpus_sha','measured_at']: 408 edges（build cache 10-23）    ❌ 无效
```
> 这两行在 §5.2 口径代号表里，是**对历史坏口径的登记**（其中 408 已被标 ❌ 无效），
> 不是新增测量。**冻结文档不改**，此处如实记录为已知的机检命中。

### 规则写入规范

`docs/conventions/version.md` 新增 **§4.1「测量证据约束：三元组」**（硬规则，2026-10-26 起），
含规则表、为什么是硬规则（五个数字的历史）、机检命令。

---

## 6. 门禁结果

| 门禁 | 结果 |
|---|---|
| `pytest -q tests` | **1485 passed**（基线 1475 + 我新增 10） |
| `node --check`（59 个 app js） | 全过，失败 0 |
| `i18n_selftest.js` | PASS |
| `team_audit.py` | **FAIL=0**，exit 0 |
| `prompt_drift_check.py` | **FAIL=0**，exit 0 |

### 一个跨 agent 冲突的如实记录

`prompt_drift` 曾有 3 条 FAIL，其中：
- **`edge_types.py` 指纹变更 = 我改的**（我的写域）
- **`render-core.js` 指纹变更 = 并行的另一个 agent 改的**（task-155 引用块内块级列表，mtime 00:29:41，在我完成之后）

`kb-spec.zh-CN.md` 同时依赖这两个文件，而工具**拒绝部分签署**（要求逐条确认全部变更依赖）。
我的处理：**实际复核了 kb-spec 全文** ——
- §4 L62/L80 的边类型描述与我的 `edge_types.py` 改动一致；
- 全文**没有块渲染断言**，`render-core.js` 的 task-155 改动不影响本规范任何断言；
然后才签署，`--note` 里写清了这两点。**没有盲签。**

---

## 7. 对裁决的异议（按任务要求单独成段，未擅自改实现方向）

### 异议 1：D-KG-04③「一致性断言」的判据需要补强（我在落地时已补）

裁决只说「零成本，锁住两端集合关系，防回退」。落地时发现：
**单纯的值断言锁不住"改回手抄"这个形态**（§3 已证）。
我在落地中补了源码形态判据，**这属于实现层的必要补强，不改变裁决方向**。
**建议**：v1 若有类似「关系型常量」的断言，默认要求「用派生实现 + 形态判据」，而不是只比值。

### 异议 2：`kg_evidence_check.py` 的窗口判据是启发式

我用"前后 12 行"找三元组成分。这让 `kg-ontology-v0.md` §5.2 的两行被标红（它们在一个
记录了五个坏数字的表里，其中 408 已标 ❌ 无效）。
**我没有为了让机检全绿而放宽判据** —— 那把尺子会失效。
如实记录为已知命中，建议后续给"历史上无效值登记"一个显式豁免标记。

---

## 8. 交付物清单

| 文件 | 类型 |
|---|---|
| `src/memoria/graph/edge_types.py` | 改（① ②） |
| `src/memoria/services/agent/plan.py` | 改（①） |
| `src/memoria/ui/static/app/js/graph-view-2d.js` | 改（④ edge_id） |
| `src/memoria/ui/static/app/js/app.js` | 改（④ 计数 + 查询口） |
| `tests/test_kg_contract_consistency.py` | 新增（③） |
| `scripts/benchmark/maintenance/kg_corpus_freeze.py` | 新增（⑤，自 debate 目录迁入并升级 v2） |
| `scripts/benchmark/maintenance/kg_evidence_check.py` | 新增（⑤ 机检） |
| `docs/conventions/version.md` | 改（⑤ §4.1 规则） |
| `artifacts/agent/verify/todo/kg-v0-buried-point-test.mjs` | 新增（④ 验收） |
| `artifacts/agent/verify/todo/kg-v0-landing.md` | 本报告 |

**未动**：`docs/example/AAA_Vocab/**`、`docs/design/kg-ontology-v0.md`。
