# Phase 3 异议 —— C agent 检索语义（agent-arch）

> **协议**：PROTOCOL.md（FROZEN），M1/M2/M3/E1。**日期**：2026-10-25。
> **Phase 1 独立性已解除**：本文件写作前已读 `PROPOSAL-arch-contract.md`、`PROPOSAL-todo-owner.md`、`PROPOSAL-metrics-baseline.md`、`PHASE2-UNION.md`。
> **纪律**：未改 `src/**`、未 commit；只新增本文件与 §1 的冻结测量证据（`evidence/kg_corpus_freeze.py` + `.json`）。
> **证据记号**：`ev:file:<path>#L<n>` / `ev:measure:<id>`（= §1 脚本输出）/ `ev:session:<...>`。
> **格式**：每条异议 = 【异议】≤120 字 + 【ev】+【撤回条件】。**打的是别人的主张**。

---

## 1. 【Lead ① / C4】语料冻结方案 —— 四个数字其实不是同一个量

### 1.1 先说结论（一句话）

> **479 是 links、454 才是 edges；408 是 2026-10-23 的旧 build cache；429/404 是 2026-10-25 live worktree；HEAD 冻结后是 160 links / 154 edges。**
> 四家都没有"算错"，但**A 和 D 把 links 数当成了 edge 数**、**B 把旧 cache 当成了语料事实**，而**我的 404 也没声明快照** —— 四份数字在 E1 下同等无效，除非冻结。

### 1.2 冻结协议（两条 sha + 一个测量源）

| 项 | 定义 |
|---|---|
| **语料（规范）** | `git archive HEAD docs/example` 的 tar 字节 sha256 = **`051deb7895c861857111947272016f0c4871ae0a1af906592e9eb30765795deb`** |
| **文件清单 sha（HEAD）** | 对纳入文件按 `(relpath, sha256)` 排序再哈希 = **`e12edfad133fe52dfceb2520f0110d363589c260de0f032bcc2e44b417d7849c`**（182 个文件：`*.md` + `.memoria/sidecars/**`） |
| **排除项** | `.memoria/agent/**`（会话/备份/运行时）、`.memoria/build/**`（旧生成物）、`.memoria/cache/**`（可再生）、`__pycache__/**` |
| **测量源（规范）** | **现场调用 `memoria.graph.collector.collect_graph_data()`**；**不得**用 `.memoria/build/graph.json`（那是 2026-10-23T09:43 的旧 cache） |
| **live 快照声明** | 若必须引用用户 live 库，必须同时给 worktree manifest sha + 测量时间。本次 live：**`52cc2ca05c4690bbcd3364c91bd44687c9b76edd5af21ff3ae969f3fb4c09d91`**（923 文件，2026-10-25 ≈20:20 CST） |

**可复跑命令**
```bash
python artifacts/agent/verify/debate/kg/evidence/kg_corpus_freeze.py \
  --json artifacts/agent/verify/debate/kg/evidence/kg_corpus_freeze.json
```
（脚本：`ev:file:artifacts/agent/verify/debate/kg/evidence/kg_corpus_freeze.py`；输出：`ev:measure:kg-c-corpus-freeze` = `…/evidence/kg_corpus_freeze.json`）

### 1.3 冻结后的数字（`ev:measure:kg-c-corpus-freeze`）

| 量 | 值 | 来源 | 量纲 |
|---|---|---|---|
| **HEAD 规范语料** | AAA_Vocab **61 nodes / 154 edges**（link 152 + sidecar_edge 2；**reference 154/154**）；links **160**；showcase 73 边（extend 11）；rename-test 7 | `git archive HEAD` + live collector | edges |
| **live worktree** | AAA_Vocab **133 / 404**（reference 404/404；origin link 402 + sidecar_edge 2）；links **429**；平均入度 3.038、最大入度 18 | 同上，live manifest `52cc2ca0…` | edges |
| **旧 build cache** | AAA_Vocab **121 / 408**（reference 408/408；origin link 406 + sidecar_edge 2），mtime **2026-10-23T09:43:34** | `docs/example/AAA_Vocab/.memoria/build/graph.json` | edges（**旧快照**） |
| **task-86 快照** | **links 479（reference 479/479）**；**edges 454（reference 454/454）** | `ev:file:artifacts/agent/verify/kg-research-phase1.md#L94-L96` | **links=479 / edges=454** |
| **A 引用** | "479 条数据 100% reference" | `ev:file:artifacts/agent/verify/debate/kg/PROPOSAL-arch-contract.md#L20` | **把 links 写成"数据/边"** |
| **D 引用** | "479/479 reference（AAA_Vocab 454/454）" | `ev:file:artifacts/agent/verify/debate/kg/PROPOSAL-metrics-baseline.md#L164` | 同一混用（括号里才是 edges） |
| **B 引用** | "121 节点 / 408 边" | `ev:file:artifacts/agent/verify/debate/kg/PROPOSAL-todo-owner.md#L5`、`#L86` | 旧 build cache |

### 1.4 争论点因此消解（谁"错"在哪）

1. **"479 vs 404"不是同一量的冲突**：479 是 **links**（task-86 phase1 §2 表头就写 `links[] 总数 479`），404 是 **edges**（live）。A 与 D 的"479/479 reference"是把 links 当 edges 用 —— **结论（100% reference）不受影响，但数字引用失效**。
2. **"408 vs 404"是同一量不同快照**：408 = 2026-10-23 的 `.memoria/build/graph.json`（B 明确引用了该文件，`#L86`）；404 = 2026-10-25 live。**旧 cache 不得作为语料事实。**
3. **"100% reference"在四个快照上全部成立**（479 links/454 edges、408、429/404、160/154）⇒ **裁决不应依赖绝对数字**，只依赖比例/结构结论。
4. **HEAD 只能复核 3 个库**（AAA_Vocab / rename-test / showcase）；行政法、examples 等 9 个库是 **live-only（未提交）** ⇒ 任何引用它们的数字必须带 live manifest sha，否则第三方不可复核。

### 1.5 我自己的漏洞（Lead ① 点出的）— 自我裁定

我 Phase 1 写"现测 links 429 / 图边 404 / 纯边 2"**没有给语料 sha、也没有给测量源**，按 E1 与 A 的 479 **同等无效**。本节即修正：
- live 快照 = manifest `52cc2ca0…`（923 文件），测量时间 ≈2026-10-25 20:08–20:18 CST；**我 Phase-1 首部写的"20:20–20:45"是笔误（自曝）**。
- **规范语料应为 HEAD**（第三方可用 `git archive` 复核）：HEAD 数字为 **61/154/160**，**"100% reference"依然成立**。
- **新规则（我主张写入裁决）**：任何边量化必须写成 `(语料 sha, 测量源, 时间)` 三元组；缺一即 E1 无效，不得进入裁决。

---

## 2. 对 A（arch-contract）的异议

### A1（量纲混用，动摇 A 的核心论据）
【异议】A 写"479 条数据 100% reference"并与 454 边混用；task-86 原文 479 是 links、454 才是 edges。A"数据为 0 所以拆字段无收益"的论据因此建在错数上。
【ev】`ev:file:artifacts/agent/verify/debate/kg/PROPOSAL-arch-contract.md#L20`；`ev:file:artifacts/agent/verify/kg-research-phase1.md#L94-L96`；`ev:measure:kg-c-corpus-freeze`
【撤回条件】A 承认 479=links、454=edges，并用 §1 冻结三元组重述数据为 0 的论据。

### A2（"429/429 全产边"是错的）
【异议】A 称"429/429 link 全产边"不成立：HEAD 160 links 仅产 152 条 link 边，live 429→402。"有 instances"≠"产边"，还需 target 可解析+行在 KP range 内。
【ev】`ev:file:artifacts/agent/verify/debate/kg/PROPOSAL-arch-contract.md#L20`；`ev:measure:kg-c-corpus-freeze`（edges_per_link 0.963/0.942）；`ev:file:src/memoria/graph/edge_derivation.py#L548-L560`
【撤回条件】A 改述为"全部 link 有 instances、进入推导流程"，并给出转化率数字。

### A3（"只文档化"不能修静默改写，且违反已裁 D3(c)）
【异议】A 主张 0.5 只文档化+断言；但 link 上 contain→reference 是运行期改写（迁移同款），断言只锁现状。D3(c) 已裁"回落但留痕 warn"，link 侧无 warn 即违反已裁规则。
【ev】`ev:file:src/memoria/graph/edge_types.py#L61-L66`；`ev:file:src/memoria/graph/kb_build.py#L72-L87`；`ev:file:artifacts/agent/verify/kg-research-phase1.md#L231`（D3=(c)）
【撤回条件】A 方案包含"link 归一化对 contain 出 warn 或报错"+覆盖该路径的断言（约 3 行级改动），或 Lead 重裁"contain-on-link 不属 D3(c)"。

### A4（"只文档化"还漏了 agent 死参数）
【异议】A 同意"判据不能挂 agent"，却据此不改 agent 面：`upsert_edge.edge_type` 无读取者、35 会话 0 使用、无消费者，是死参数。0.5 删参数是零行为损失的契约清理，成本低于 A 的 warn 改动。
【ev】`ev:file:src/memoria/services/agent/plan.py#L187`；`ev:session:docs/example/*/.memoria/agent/sessions/*.jsonl`（`"edge_type"` 0 命中）；`ev:file:artifacts/agent/verify/debate/kg/PROPOSAL-agent-arch.md#L154-L158`
【撤回条件】A 给出该参数的真实 agent 使用或消费者证据。

### A5（A 的"get_graph_data 零调用者"不成立）
【异议】A 称`get_graph_data()`Python 侧零调用者，据此证 agent 不读图；实测 `ui.py#L372-L374` 就是调用者（→app.js RPC）。结论仍成立，但该证据表述错误。
【ev】`ev:file:artifacts/agent/verify/debate/kg/PROPOSAL-arch-contract.md#L23`、`#L249`；`ev:file:src/memoria/services/ui.py#L372-L374`；`ev:file:src/memoria/services/document.py#L2124`
【撤回条件】A 把表述改为"除 UI RPC 外无业务消费者"，或指出 `ui.py` 不在其"Python 侧"定义内并说明定义。

---

## 3. 对 B（todo-owner）的异议

### B1（"真实库 121/408"来自旧 build cache）
【异议】B 的"真实库 121/408"出自旧 `.memoria/build/graph.json`（mtime 2026-10-23T09:43）；冻结 HEAD 实测 61/154、live 133/404。旧 cache≠语料事实。
【ev】`ev:file:artifacts/agent/verify/debate/kg/PROPOSAL-todo-owner.md#L5`、`#L86`；`ev:measure:kg-c-corpus-freeze`（stale_build_snapshot.mtime=2026-10-23T09:43:34）
【撤回条件】B 改用现场 `collect_graph_data()` 并给冻结三元组；或明确标注"408 为 2026-10-23 build 快照"。

### B2（"reference 全降级为 link"有无锚点反例）
【异议】B"reference 不是边、应降级为 link"存在反例类：无正文锚点的纯 reference 边（HEAD 2 条、live 3 条，`edges[]` 直声明）无法降级为 link，只能删除或另立类型；B 未给处置规则。
【ev】`ev:measure:kg-c-corpus-freeze`（HEAD AAA_Vocab sidecar_edge=2；live sidecar_edge=2+1）；`ev:file:src/memoria/graph/edge_derivation.py#L643-L676`
【撤回条件】B 证明这些纯边可全部迁移到正文锚点（或给"保留为 human-only / 删除"的规则）。

### B3（5 类的"消费者"是设计视图，不是已发生使用）
【异议】B 的 sequence/contrast/exemplify 只有设计中的视图当消费者，按 M1 不算证据；D 的 M-06 已证现有类型 100% 默认 ⇒ 无填写机制时新类型同样 0 填。
【ev】`ev:file:artifacts/agent/verify/debate/kg/PROPOSAL-todo-owner.md#L28-L38`；`ev:file:artifacts/agent/verify/debate/kg/PROPOSAL-metrics-baseline.md#L36`；`ev:session:35 会话 edge_type 0 命中`
【撤回条件】B 给出冻结语料中人工填写的该类型实例（≥10 条），或"强制填写 UI + 完成率测量"方案。

### B4（3D 方向性"加辅助即可"低估成本）
【异议】B 称 3D 有向边"必须箭头+着色+legend"；实测无把 `EDGE_COLORS` 渲染成图例的代码，类型只进颜色。加 legend/箭头是新可发现层，成本被低估，无 M-11 埋点也验不了可读。
【ev】`ev:file:src/memoria/ui/static/app/js/graph-view-3d.js#L499`；`ev:file:src/memoria/ui/static/app/js/graph-engine.js#L7-L10`（无 EDGE_COLORS→legend 消费者）
【撤回条件】B 给出方向箭头/边颜色 legend 的现有实现证据，或把该条降级为 v1 待埋点。

---

## 4. 对 D（metrics-baseline）的异议

### D1（"无埋点前不可测"范围过宽）
【异议】D"无埋点前不可测"只适用于"人导航命中率"；agent 侧 token 成本与需求频次可从会话日志离线算（工具结果长度/参数已有），不需要新埋点。D 把两个域一起判死。
【ev】`ev:file:artifacts/agent/verify/debate/kg/PROPOSAL-metrics-baseline.md#L34-L35`；`ev:file:src/memoria/services/agent/trace_index.py#L1-L60`（trace/call 记 `result_chars/est_tokens`）；`ev:measure:kg-c-20261025T2035`（Phase-1 §8：sidecar 全扫 43,880 tok）
【撤回条件】D 证明 agent 侧现有会话日志无法算成本（如无字符数/无工具结果留存）。

### D2（token 代理：效率轴 ≠ 有效性轴）
【异议】token 代价不能当"边有用"的代理，只是成本侧上限：省 token 但答案不变=只省钱，答案变差=负价值。M-05 的 15% 应撤回（D 已自认），但不能用 token 替代"有效性"。
【ev】`ev:file:artifacts/agent/verify/debate/kg/PROPOSAL-metrics-baseline.md#L35`、`#L471`；`ev:file:artifacts/agent/verify/debate/kg/PROPOSAL-agent-arch.md#L17`、`#L118`
【撤回条件】D 证明存在"cost↓ ⇒ value↑"的单调映射（需报"需求恒定"这个不成立的前提）。

### D3（M-01 不能裁决"reference 是边还是 link"）
【异议】M-01/M-02 测导航可达性；link 也是跳转，二者在可达性上等价 ⇒ M-01 对 B 的语义主张不可证伪。判"语义断言 vs 跳转"需 M-08/M-09，但现数据仅 43 条 link 带 target_edges，样本不足。
【ev】`ev:file:artifacts/agent/verify/debate/kg/PROPOSAL-metrics-baseline.md#L31-L32`、`#L38-L39`；`ev:measure:kg-c-corpus-freeze`（live AAA_Vocab target_edges=43，links=429）
【撤回条件】D 给出可区分"语义断言/跳转"的可测判据且样本量 ≥30。

---

## 5. Lead 点名问题的直答

### ② B 的"reference 降级"——我**支持语义降级**，但不支持无条件删字段

- **agent 面：零损失**。我的 19 条读取点 + 零读取点表（`ev:file:.../PROPOSAL-agent-arch.md#L27-L67`）证明 agent 无任何边读取路径；35 会话 `edge_type` 0 命中、create_edge 仅 2 次默认值 ⇒ 降级 reference 不会让 agent 丢任何能力。
- **人类面：link 能承担导航**（B 说的"点一下跳过去"；D 的"多点 2 跳"也是 link 路径长度）⇒ 导航不依赖 edge.reference。
- **但**：HEAD/live 各有 **2/3 条无锚点的纯 reference 边**（B2），且 `M-08/M-09` 映射保真度需要边侧类型才能算 ⇒ 我支持 (i) 语义上 reference 不再算"关系断言"（B 的主张成立）；(ii) **保留 `reference` 作为内部投影值**（"无断言跳转"），不删除枚举值；(iii) 纯边必须给处置规则（迁移/删除/human-only）。
- **裁决建议**：B 的"reference 不是边"作为**语义定义**接受；作为**字段删除**需先解 B2。

### ③ A 的"只文档化+断言"——**不够**，必须要 3 行级的 warn

- 静默改写是运行期行为（`edge_types.py#L61-L66`），文档不改变行为（A3）。
- D3(c) 是**已裁规则**（"未知值回落但留痕 warn"），link 上 contain 落 default 且无 warn = 违反已裁，不是"设计选择"。
- 最小合规改动：`normalize_link_edge_type` 对 `contain` 输出一次 warn（或由调用方 warn）+ 断言测试锁住；这比 A 的"修不对称"目标更小、且让失败可见（项目 L6 教训）。
- **若 Lead 裁定 0.5 完全不改代码**：那 A 的主张应降级为"记录已知违例"，不能宣称"修枚举不对称"。

### ④ B 的 5 类：用我的消费者判据逐类判

我的判据分两级（Phase 1 §硬门槛）：**(a) 有 agent 决策消费者**；**(b) 有已发生的人看视图使用证据**（设计图纸不算）。

| B 的类型 | 我的判定 | 依据 |
|---|---|---|
| `contains` | 现状已是派生事实（`origin=range`），**无需新增**；agent 用不上（outline 更强） | R3/R18；`ev:measure` contain 只在 range origin |
| `prerequisite` | **0.5 不加**：唯一消费者（复习排序）未实现；且枚举无此类型、遗留 `#prerequisite` 被别名成 reference | `edge_types.py#L18`；D 的 M-15 标"不可测" |
| `sequence` / `contrast` / `exemplify` | **0.5 不加、v1 可议**：B 的证据是正文模板/槽位表（设计意图），无填写机制；D 的 M-06 说现有类型 100% 默认 ⇒ 新类型同样 0 填。v1 前置条件：强制填写 UI + M-06/M-08 闸 + 至少 10 条人工实例 | B3 证据 |
| B 的"reference=link" | **接受语义降级**（见 ②） | 我的零读取点表 |

**若 Lead 把"设计中的视图"也算消费者**：我放宽为"可加，但必须 (i) 标 human-only、不进 agent API；(ii) 每类配 D 的三闸（区分度/relevance 异质/决策绑定）；(iii) 没有使用指标前不得进验收"。这不是"过严"，是给 B 一条可执行准入路径 —— **消费者 = 能指到具体动作 + 有证据，而不是"某视图可能会用"**。

### ⑤ token 代价能不能当"边有用"的代理？—— 能当"效率轴"，不能当"有效性轴"

- **能当代理的部分**：若 agent 确实会问"谁引用了我"，反向邻接接口把 43,880 tok → ~60 tok 是**成本侧**硬收益（`ev:measure:kg-c-20261025T2035`，Phase-1 §8）。这足以**支持建接口的成本论证**，也足以**证明 D 的 M-04/05 不是唯一路径**。
- **不能当代理的部分**：省 token ≠ 有用。三种结果要分开：
  - 省 token 且**答案更好** ⇒ 有用（强）；
  - 省 token 且**答案不变** ⇒ 只省钱（弱有用，可接受但不构成"边有价值"）；
  - 省 token 且**答案变差** ⇒ 负价值（比不建更糟）。
- **结论**：M-05 的"≥15%"应撤（D 已自认拍的），但**不能降级为"只看 token"**。替代 = **双轴**：效率轴（token，现在可离线算/已有 trace 字段）+ 有效性轴（A/B 或埋点）。这正是我 Phase 1 的 U1：**先 A/B，再决定建不建**。
- **对 C10 的裁决**：不是"埋点 vs 代理"二选一，而是**两个轴的职责不同**；D 的"必须埋点"只在人导航域成立。

### F8「图 provenance 要不要给人看」—— 我**自我推翻强版本**，弱版本保留

- **错在哪**：我 Phase 1 说"UI 不展示 derived"⇒ 暗示用户分不清边来源。实测 **KP 边面板展示了 `origin`**（link/range/manual 三标签，`app.js#L4430-L4436`、`#L4456`、`#L4491`），且**删除按钮只对 `sidecar_edge` 出现**（`#L4465`），link-origin 给的是"配置链接"按钮 ⇒ **动作已按 provenance 分流**。我的 F8 强版本撤回。
- **保留什么**：**图画布**（2D/3D）仍只有颜色、无 legend/origin 区分（`graph-engine.js#L7-L10` 无 legend 消费者）。但 0.5 **不需要**给画布加 provenance（成本>收益）。
- **要不要给人看**：**要，且已经在边面板给了；画布不加**。**但**：若 B 的 5 类/视图着色进 v1，**必须先给 legend**，否则颜色不可解释（见 F2）。

### F2「类型只影响颜色」算不算"类型有用"？—— 条件算，现状不算

- 颜色是 pre-attentive cue，**可以**服务"识别类别"这个决策；但需要三个条件：(i) **legend/可发现**（现状 0：`grep legend` 在图 JS 无命中）；(ii) 类别语义被教会（文档/图例）；(iii) 用户据此有动作（D 的 M-13/M-16 类使用指标）。
- **现状 3 色无 legend ⇒ 颜色不构成"服务决策"**，只是视觉标签；B 的 5 色在无 legend 下更不可解释（5 种颜色无说明 = 噪声）。
- **与 B 的核心分歧**：不是"颜色有没有用"，而是**"用前必须有 legend + 可发现性 + 使用证据"**。若 B 先给 legend + 图例交互，颜色可以算**弱服务**（识别），但仍不构成"边类型存在"的充分理由（类型门槛仍是 D 的三闸/我的消费者判据）。

---

## 6. C1–C10 我的裁决表（按并集 §9）

| 编号 | 冲突 | 我的立场 | 依据 | 撤回条件 |
|---|---|---|---|---|
| C1 exemplify | A 不加 / B 加 / C 有消费者前不加 | **0.5 不加**；v1 前置=填写机制+M-06/M-08+≥10 实例 | B3；D#L36 | B 给冻结语料实例或强制填写方案 |
| C2 类型由谁给 | C 系统推断 agent 只覆盖 | 维持：**agent 面去掉类型参数**，系统默认 reference | 35 会话 0 使用；A4 | 出现 agent 类型有效使用证据 |
| C3 sequence/contrast | B 必须进 | **0.5 不进**；v1 可议（同 C1 前置） | B3 | 同上 |
| C4 数字口径 | 479/429/404 | **已解**：479=links、454=edges、408=旧 cache、404/429=live、154/160=HEAD；**冻结三元组** | §1；ev:measure | 若有人给出 479 为 edges 的冻结证据则重开 |
| C5 反向邻接 | 先 A/B 还是先接口 | **先 A/B（U1）再建**；token 省 488× 只证明成本侧 | 我 §3 表；D2 | A/B 显示无质量收益 ⇒ 不建 |
| C6 3D 方向链接 | B 加辅助才展示 / C 类型只颜色 | 支持 B 的"无 legend 不展示有向边"；但是 v1，不是 0.5 | B4 | B 给现有箭头/legend 实现 |
| C7 0.5 改动范围 | A 只文档化 / C 去参数+统一归一化 / B 要 5 类 | **最小集 = ①去 agent 类型参数 ②link 归一化 warn ③统一归一化器注释**；B 的 5 类不进 0.5 | A3/A4；B3 | A 证明零代码即可消除静默改写 |
| C8 D4 prereq 链 | B 要 / D 不可测 | **0.5 不做**：无消费者（复习未实现）且不可测 | ④；D#L45 | 复习域给出消费者接口 |
| C9 外部研究 | B 要 / A/C 部分保留 | **本阶段不做**；外部研究回答不了"agent 价值" | D6 精神；我的 §5⑤ | 出现"外部框架能给出可测判据"的证据 |
| C10 边的价值可测吗 | D 不可测 / C 给了 token | **分域**：人导航需埋点；agent 成本可离线算；有效性需 A/B。**M-05 阈值撤** | D1/D2；⑤ | D2/D1 撤回条件 |

---

## 7. 自我更正（Phase 3 允许且鼓励）

1. **C4 自我裁**：我 Phase-1 的 429/404 **无语料 sha / 无测量源**，按 E1 与 A 的 479 同等无效；且我写的"20:20–20:45"是**笔误**（实际 ≈20:08–20:18）。§1 已补规范冻结。
2. **F8 强版本撤回**：我 Phase-1 说"provenance 不给人看"过头 —— KP 边面板展示了 origin 且动作按 origin 分流（`app.js#L4430-L4465`）。只有图画布没展示。
3. **我的 "479/429/404" 表述**：应写"links 429 / edges 404（live）"而非"图边 429"；§1 已更正为规范三元组。

---

## 8. 新增可证伪断言（本轮）

| # | 断言 | falsifier |
|---|---|---|
| G1 | "100% reference"在四个冻结快照上都成立 | 任一冻结快照出现非 reference 边占比 >1% ⇒ 本条不成立（现 HEAD 154/154、live 404/404、旧 cache 408/408、task-86 454/454 均 100%） |
| G2 | HEAD 语料 AAA_Vocab link→edge 转化率 <100% | 重跑发现 160 links 全部各产 ≥1 条唯一边（152→160）⇒ 本条不成立 |
| G3 | KP 边面板已展示 provenance 且动作按 origin 分流 | 找到 origin=link 的边也出现删除按钮 ⇒ 本条不成立 |
| G4 | 图画布无 legend/origin 展示 | 在图 JS 找到 legend 渲染/类型说明消费者 ⇒ 本条不成立 |
| G5 | agent 侧成本可从现有会话日志算 | 日志无工具结果长度/参数 ⇒ 本条不成立（现 trace/call 有 `result_chars/est_tokens`） |

---

## 9. unknowns / not_doing

**unknowns**
- **U-C7-1**：去掉 agent 类型参数是否破坏任何现存集成（MCP 客户端/测试）？*if_true（破坏）* ⇒ 改为保留参数但标 deprecated + 0.5 只加 warn。
- **U-C4-1**：HEAD 只含 3 个库，行政法/examples 的 contain 结论无法用 HEAD 复核；*if_需要* ⇒ 需用户授权把 live 库快照入库后再冻结（不可行则永久标注 live-only）。
- **U-F2-1**：颜色在无 legend 下是否真的产生"可读性"？*if_true（有）* ⇒ 我的 F2 弱化；*if_false* ⇒ 5 类着色无意义。

**not_doing**
- 不新增 `src/**` 改动（Phase 3 纯异议）。
- 不实现反向邻接接口（需 U1 A/B 后）。
- 不裁决 B 的学习场景/视图设计（非我域）。
- 不重跑 479 那个 task-86 快照（语料已不可得；只登记为历史快照）。

---

## 10. 证据清单（本轮新增）

| 文件 | 用途 |
|---|---|
| `artifacts/agent/verify/debate/kg/PHASE3-OBJECTION-agent-arch.md` | 本文件 |
| `artifacts/agent/verify/debate/kg/evidence/kg_corpus_freeze.py` | C4 冻结测量脚本（可复跑） |
| `artifacts/agent/verify/debate/kg/evidence/kg_corpus_freeze.json` | `ev:measure:kg-c-corpus-freeze` 输出（含 HEAD/live/旧cache 三组数字 + 两条 sha） |

**未改动**：`src/**`、`docs/**`、其他三方提案文件。**未 commit**。
