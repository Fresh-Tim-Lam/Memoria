# G4 链路语义评价 · 独立复核清单（verifier）

> **复核对象**：`artifacts/agent/verify/debate/graph-utility/G4-link-semantics.md`（task-209，**截至本文件写入时尚未出现**）。
> **复核角色**：gm-seminar-verifier（domain=seminar / group=graph-memory-seminar），只依据磁盘产物判定，不接受口头结论。
> **本文件状态**：**复核准备版（v1）**。G4 正文出现后，按 §2 清单逐条填 PASS / FAIL / 无法核实，并追加复核结论；
> 发现的问题只写在这里并报 Lead，**不改 researcher 的文档**。
> **→ 逐条判定与结论已落在 `G4-verify-report.md`（对 G4 版本 sha256 `2211f14d…`）**。
> **独立复算产物**：
> - `G4-verify-prep.json` + `scripts-verify/G4-verify-prep.py`（用产品 `collect_graph_data()` 在独立临时副本重算 G1/G2/G3 全部关键数字；已验 deterministic：去掉 generated_at 后两次运行完全相等）
> - `G4-census-crosscheck.json` + `scripts-verify/G4-census-crosscheck.py`（对 researcher 已落盘的 `G4-path-census.json` 做独立交叉核验）
> **快照身份（已核）**：`数字通信原理` frozen · 37 文件全部 sha256 与 `MANIFEST.json` 一致 · MANIFEST 文件 sha256 = `a4beaedc5f852816…` · taken_at `2026-10-27T14:09:46+08:00`。
> **当前 git HEAD** = `589a48e769dd30459041eb7bc11cff2bc9d72604`（工作区 587 项未提交）。
> **纪律**：不改产品代码；不 commit；数字必须能复算；找不到证据写「无法核实」，不猜。

---

## 0. 复核基线（已读材料）

| 材料 | 用途 | 已读 |
|---|---|---|
| `G1-framework.md`（501 行） | 四层框架、L3 三候选必要不充分、62 边做不了代表性 L3 | ✅ |
| `G1-papers-instruments.md`（279 行） | A 源：无现成链路级仪器；κ/α 门槛（0.80 solid / 0.67 tentative）；Cranfield 小样本不能认证阈值；ablation 非 Paulheim 标准方法 | ✅ |
| `G2-L2-protocol.md`（341 行） | P1–P5 + D 谓词；24 条分层抽样；人判协议四档 α；最小任务集与功效表 | ✅ |
| `G2-judgment-sheet.md` / `JUDGE-SHEET-for-stranger.md` | 现有人判表模板（供 G4 盲判协议一致性比对） | ✅ |
| `G3-multiplicity.md`（283 行） | placement vs inbound；派生相似度永不物化；inbound 按谓词分组 | ✅ |
| `ideas-ledger.md` | GUE-IDEA-001…009（含 8 退化边、extend 语义混合） | ✅ |
| `G4-path-census.json`（researcher 已落盘，非最终 G4） | 路径普查：23 条 2-hop / 20 条 3-hop、候选样例 15 条、负例可构造性 | ✅ 已交叉核验（§3） |

---

## 1. 独立复算结果（G1/G2/G3 数字先验证，G4 才能被信任）

> 方法：不复用 researcher 的 `scripts/G*.py` 聚合代码；用产品 `collect_graph_data()` 在**独立临时副本**（`gue-verify-prep`，与 researcher 的 `gue-baseline/gue-g2/gue-g3` 不共享目录）重算。
> 判定：✅=与声称一致；⚠️=一致但口径/边界需注明；❌=不一致/不可复算。

| # | 指标 | 文档声称 | 我的独立复算 | 判定 |
|---|---|---|---|---|
| 1 | 节点 / 边 | 357 / 62 | 357 / 62 | ✅ |
| 2 | 边类型 | contain 33 / extend 21 / reference 8 | 33 / 21 / 8 | ✅ |
| 3 | 边来源 | range 33 / sidecar_edge 26 / link 3 | 33 / 26 / 3 | ✅ |
| 4 | relevance | 0.9×33 / 0.7×8 / 0.6×21（100% 类型默认） | 完全一致 | ✅ |
| 5 | derived | True 36 / False 26 | 36 / 26 | ✅ |
| 6 | 被边覆盖节点 | 79（22.1%） | 79（22.13%） | ✅ |
| 7 | 孤立节点 | 278（77.9%） | 278（77.87%） | ✅ |
| 8 | 连通块 / 最大块 | 296 / 25 | 296 / 25 | ✅ |
| 9 | 平均度 / 边节点比 | 0.347 / 0.174 | 0.3473 / 0.1737 | ✅ |
| 10 | 度分布 | 1:56, 2:13, 3:4, 4:3, 5:1, 6:1, 7:1 | 完全一致 | ✅ |
| 11 | range_ok | 352/357（98.6%） | 352 / 98.6% | ✅ |
| 12 | description 非空 | 0/357 | 0 | ✅ |
| 13 | 边字段缺失 | fact/valid_at/invalid_at/confidence/provenance/instances 各 0/62 | 全 0 | ✅ |
| 14 | 多目标边 | 0 | 0 | ✅ |
| 15 | 退化 contain | 8 条（7 同名自指 + 1 OCR 错名） | 8 条（7 same-name + 1 OCR prefix，逐条名单见 prep JSON） | ✅ |
| 16 | 入度 ≥2 节点 | 4 个（1.12% / 覆盖节点 7.1%） | 4 个：`ideal-sampling`、`scalar-quantization`、`dm-pcm-error-comparison`、`ch2-10-cosine-plus-narrowband-gaussian` | ✅ |
| 17 | 只作者边（29）入度 | 24 target、4 个 ≥2、16.7% | 24 target、4 个 ≥2（16.7%） | ✅ |
| 18 | extend 入度 | 21 条 target 全不同、各入 1 | 21 / 21，入度全 1 | ✅ |
| 19 | co-citation 若物化 | 57（全）/ 55（去退化）/ 9（只作者边） | 57 / 55 / 9 | ✅ |
| 20 | bibliographic coupling 若物化 | 9 / 9 / 6 | 9 / 9 / 6 | ✅ |
| 21 | links[] | 3 条目 / 5 instances / 3 target / 0 个 ≥2 / 1 孤儿（`通带抽样定理`） | 完全一致 | ✅ |
| 22 | 同名碰撞 | 36 组 / 114 KP（31.9%） | 36 组 / 114 / 31.93% | ✅ |
| 23 | multi-file identity | 0 | 0 | ✅ |
| 24 | frozen 快照完整性 | 37 文件 / MANIFEST `a4beaedc…` | 37/37 sha256 全对，MANIFEST 文件 sha256 全对 | ✅ |
| 25 | G1 内容哈希 | “去掉 generated_at 后 sha256 = `bfdd85ab…`” | **42 种 canonicalization 均无法复现**（含 indent/compact/sort_keys/换行/子集变体） | ❌ 不可复算 |
| 26 | G2/G3 产物哈希 | G2-sampling / edge-inventory / judgment-sheet / G3-inbound / 4 个脚本 | 全部逐字节匹配（sha256 一致） | ✅ |
| 27 | G2 §7 的 ideas-ledger 哈希 | `6E9631…` | 当前 `9FFA2B…`（G3 §8 已声明更新，非缺陷） | ⚠️ 引用须用 G3 版本 |
| 28 | G2 的 HEAD 引用 | `1b3f6787…`（dirty） | 当前 HEAD `589a48e7…`；语料身份仍由 MANIFEST 保证 | ⚠️ HEAD 已漂移，G4 不得直接抄 HEAD |

**复算结论（G1–G3 层）**：除 #25（内容哈希不可复算）与 #27/#28（引用版本漂移）外，G1/G2/G3 的**全部结构性数字可独立复现**。G4 若引用这些数字，应直接引用冻结快照三元组（MANIFEST sha256 + taken_at + 测量源 + build_state），不要引用“实时 HEAD”。

---

## 2. G4 逐条检查清单

> 判定门槛分三档：**PASS**（满足）/ **FAIL**（不满足，须改或降级）/ **无法核实**（G4 未给足够信息或当前证据不存在）。
> 每条给出「G4 必须写到什么程度」（验收口径）与「我怎么验」（可复算/可对账）。

### A. 链路定义是否可操作（能否对任意一条链路判“是/否”）

| ID | 检查项 | G4 必须写到什么程度 | 复核方式 |
|---|---|---|---|
| A1 | **图口径** | 明确：来自哪个图（`collect_graph_data()` / `build_knowledge_base()`）、pre/post_build、raw 还是 clean（去 8 退化边）、是否含 `reference`/`contain` | 对账 G2 §4 的 12 字段；核对 G4 引用的 62/54、357/65 与我复算一致 |
| A2 | **路径定义** | 明确：允许的边数/节点数上下界（k≥2？上限？）、方向是否固定、**是否允许重复节点/重复边**、是否允许混合边类型、是否要求连通 | 用 G4 的定义对 `G4-path-census.json` 的 23+20 条路径逐条重算：若定义不同（如允许 walk），路径数会变，要求 G4 给出对应数字 |
| A3 | **候选集口径** | 明确“链路候选集”的枚举规则（例如：clean 图 + 2–3 hop + 简单路径 + 至少一条作者边）；**纯 contain 子图是否单列**（结构链不是语义链） | 我复算：contain 33 条边的 source 入度全 0、target 出度全 0 ⇒ **contain 不参与任何 ≥2 边路径**；G4 若把 contain 链算进“链语义候选”须解释 |
| A4 | **来源口径（G1 U3 三选）** | 钉死：只用现有图路径 (a) / 正文独立生成 (b) / 等图扩充 (c)；若 (b)，必须与“图的语义”结论分开报告 | 检查是否混用：凡“图的链路语义率”只能来自 (a) |
| A5 | **可枚举性/样本量** | 若声称为“代表性抽样”，必须给出样本框总数。**当前事实：≥2 边简单有向路径 = 2-hop 23 条 + 3-hop 20 条 = 43 条**（全部在 25 节点最大块内，且全部同文件） | 若 G4 声称“抽样 N 条”且 N>43 或未说明样本框 ⇒ FAIL；若只做 pilot/案例研究，须显式写“不代表性” |

### B. 判据是否存在失效条件；是否把“边错”与“组合错”混为一谈

| ID | 检查项 | G4 必须写到什么程度 | 复核方式 |
|---|---|---|---|
| B1 | **“有语义”的可操作定义** | 判定单位（一条链路）、判定输出（是/否/不确定）、判定依据（原文/组合表/任务）三件齐全；定义须能对 43 条路径逐条给出“属于/不属于候选” | 抽查 3 条路径（如 `ch3-intro→quantization-overview→pcm`、`delta-modulation→dm-error-performance→dm-pcm-error-comparison`、`natural-sampling→ideal-sampling→aliasing`）看定义是否给出唯一可判结论 |
| B2 | **每条判据的失效条件（falsifier）** | 每个候选判据（NL 复述 / CQ 支撑 / 负例区分度）都写“什么结果 ⇒ 该判据无效/放弃”；不能只有合格线没有放弃条件 | 对照 G1 §5.3 的 6 项缺口逐项检查（方向与组合、溯源、非冗余、任务效用、负例规范、一致性协议） |
| B3 | **错误归因分离** | 必须能分开报告：①某跳边本身不成立（边错）；②边成立但类型组合无定义/不合法（组合错）；③命题真值不成立；④无法溯源；⑤方向错。**禁止只报一个“链路无效率”把②混进①** | 检查 G4 的判定表/错误分类；若只有“有意义/没意义”二分且不记录失败原因 ⇒ FAIL（G1 §5.3 候选①原话：“把边错与组合错混在一起”） |
| B4 | **组合语义表** | 给出边类型的组合表：哪些类型可组合、组合后是什么、是否传递、哪些组合禁止；引 A 源（OWL 2 property chains / SPARQL 1.1 property paths）为骨架 | 对账：现网 43 条路径的类型组合只有 `extend→extend` 17、`extend→reference` 3、`reference→extend` 3、`eee` 14、`eer` 3、`ree` 2、`ere` 1 ⇒ 组合表至少要覆盖这些，并说明 **含 reference（P5 无断言）的 12/43 条路径如何组合** |
| B5 | **reference / contain 的语义地位** | 与 G1/G2 一致：reference=无断言（P5）**不能**单独构成语义断言；contain=结构派生。若链路含 reference 跳，须明确该链只能算“导航/溯源链”而非“语义命题” | 用 G2 P5 定义核对；若 G4 把含 reference 的链路计入“语义成立”分子 ⇒ FAIL（与 G1 §2.3、G2 §1 P5 冲突） |
| B6 | **非冗余/信息量** | 定义“冗余链”口径（如仅沿章节顺序/祖先链）并给出统计；G1 已警示当前 extend 链可能只是章节顺序（我的复算：21/21 条 extend 的 target start_line 均在 source 之后、且同文件） | 检查是否统计“冗余链占比”；若无此项，L3×S 的合格线会被“顺序链永远真”刷高 |
| B7 | **溯源（G）** | 若判据要求“可溯源”，必须说明当前 edge **0/62 有 instances/provenance**，链路级溯源当前**不可测**（需 G5）；不能把“节点能回原文”当成“链路能回原文” | 对账 §1 #13；G4 若声称 L3×G 现在可测 ⇒ FAIL |

### C. 负例构造规范 + 难度校准（已知问题：随机负例太容易 ⇒ 区分度虚高）

| ID | 检查项 | G4 必须写到什么程度 | 复核方式 |
|---|---|---|---|
| C1 | **负例族定义** | 至少覆盖：反向、邻接替换（兄弟节点替换）、类型替换、同章/同文件近邻对、跨章对、乱序/打乱、随机对（仅作 trivial baseline 的**下界**，不得当主负例） | 检查是否有负例族清单与每族构造规则；对照 `G4-path-census.json` 的 `negative_feasibility`（N1=23、N2=10、N3=6、N5=23）是否被 G4 正确引用 |
| C2 | **难度校准方法** | 必须报告：①人类上限（human ceiling）；②**trivial-separation 检查**（连通性/同文件/同章/路径长度这些平凡规则能拿多少 BA）；③正负例按同文件/同章/同长度匹配的策略 | 我复算的可计算下界：**随机节点对同分量率 0.634%、有向可达率 0.097%**（357 节点框）；clean 覆盖 65 节点框内：同文件有序对 26.3%、相邻 1.30%、2-hop 可达 0.55%；**若用“两端同文件”这条平凡规则分类，BA 可达 0.8706** ⇒ 负例不匹配同文件就会虚高。G4 必须给出同类下界并说明如何避免 |
| C3 | **正例来源独立性** | 正例标签不能由同一张图/同一构造器产出（循环）；CQ 的 gold 链须“从原文独立标注” | 检查是否声明 gold 链来源；若 gold 链从图抽 ⇒ 与 G1 §5.3 候选②的循环风险冲突，FAIL |
| C4 | **known-bad/known-good 夹具（M2）** | 用 8 条退化边 + 人工构造正确链路做夹具；负例过易必须能被夹具检出 | 检查是否引用 G2 的 8 条退化边与 M2 设计；若 G4 的判别实验分不开夹具 ⇒ 方法无判别力（G1 R6） |

### D. 多人盲判协议：人数/样本量/α 门槛必须与 G2 一致

| ID | 检查项 | G4 必须写到什么程度 | 复核方式（G2 基线如下，逐条对账） |
|---|---|---|---|
| D1 | **判据者人数** | G2 §2.1 四档：3 真人（主证据）/ 2 真人（最低可接受）/ 1 真人+2 agent（仅参考）/ 1 人（不算证据）。G4 必须同档或更严 | 逐字对账；若 G4 写“2 人即可作产品门禁”⇒ 与 G2 “2 人=最低可接受、α 单值”一致才 PASS |
| D2 | **样本量** | 明确判定项数量与抽样规则；若抽样须给种子/分层；若 n 在 20–60，必须报 bootstrap CI（A 源：Artstein & Poesio / Krippendorff） | **当前可判定链路总数仅 43 条**（23+20）；若 G4 只抽 15 条（researcher 的 census 样例就是按排序取前 15 条，非随机），必须说明选择规则与选择偏差；我建议全量 43 或随机+种子 |
| D3 | **α/κ 门槛** | 必须沿用 G2 §2.4 的**四档**，不能拍成单阈值：α≥0.80=可作证据；0.667≤α<0.80=暂定+必须扩样；0.50≤α<0.667=marginal+扩样；α<0.50=停止重来。Q2 类 Fleiss κ 门槛 0.667 | 逐档对账。注意 Lead 摘要“≥0.80 证据 / 0.667–0.80 扩样 / <0.50 重来”省略了 0.50–0.667 档；G4 若同样省略可以，但须显式写 0.50–0.667 的处置，不得把 0.50–0.667 直接判“通过” |
| D4 | **一致性系数选择** | 序数/分类分别选 α / κ；报点估计 + bootstrap CI + 简单一致率；分歧裁决记录 | 检查是否只报一个 α 无 CI（20–43 项 CI 会很宽，A 源明确要求报 CI） |
| D5 | **盲化** | 判据者不可见：原类型/origin/derived、**分组结构提示**、他人答案、**示例答案**；条目顺序随机化 | ⚠️ 现有 `JUDGE-SHEET-for-stranger.md` 有两处泄露：①按结构分组（“两端是同一个名字”“整体→组成部分”“多个知识点都指向同一目标”）等于提示 strata/known-bad；②§三“回答格式”示例实际给出了 24 条的期望答案（锚定）。G4 若沿用该模板做路径盲判 ⇒ FAIL；须去掉分组标签与示例答案，或明确标注为非盲 pilot |
| D6 | **预注册** | 指标、合格线、扩样规则、停试规则先写死；agent 代判单独一组不混入主 α | 对照 G2 §2.4/§2.5 的 E1–E6；G4 要有自己的扩样/停止规则 |
| D7 | **条目独立性** | 路径判定项之间的独立性：同一长链滑窗会重复计权。我复算：23 条 2-hop 路径两两共享节点直方图 {0:171, 1:52, 2:30}（30 对是同一长链的滑窗） ⇒ 有效样本量 < 判定项数 | 检查 G4 是否报告重叠/有效样本量；若直接拿 43 项当独立样本算 CI ⇒ 至少标⚠️ |

### E. 是否诚实说明“当前 62 边 + 最大块 25 节点做不了代表性 L3”

| ID | 检查项 | G4 必须写到什么程度 | 复核方式 |
|---|---|---|---|
| E1 | **代表性 L3 不可做** | 必须显式写“当前图不能做代表性 L3 测量”，并给量化理由：≥2 边简单路径仅 43 条、全部在单一 25 节点连通块、全部同文件、包含 0 条 contain；只能做 pilot/案例/夹具 | 对账我的复算：len2=23、len3=20、largest=25、len2/len3 全部位于最大块、extend 21/21 同文件且 target 行号在后、最长简单路径 6 边、contain 不参与任何 ≥2 边路径 |
| E2 | **L2 前置未完成** | G2 人判矩阵（24 条边）**尚未执行**（无作答/α 结果文件）⇒ “每跳边有效”这个 L3 判据前提当前不成立；G4 必须声明依赖或改用不依赖 L2 结果的判据 | 磁盘核对：graph-utility 下无 G2 判据结果/α 文件；若 G4 默认“边已有效” ⇒ FAIL |
| E3 | **agent 侧 L3 效用不可测** | agent 路径完全不读边（B：`kg-ontology-v0.md:20`；G2 §3.1）⇒ 当前把链路接进 agent 的消融 Δ 恒等于 0，不是“效应小”而是“通路不存在”；G4 不得把它列为现在可做的 L3×U | 对账 G2 §3.1 原文；若 G4 设计当前可跑的 agent 消融 ⇒ FAIL |
| E4 | **路径来源口径** | 明确 (a)/(b)/(c) 的选择；若 (b) 独立生成路径，只作研究用、不得声称是“图的语义” | 检查结论句的主语（“图的链路” vs “生成的候选路径”） |

### F. 数字绑冻结快照；D 源不得当设计依据；≥2 源支撑

| ID | 检查项 | G4 必须写到什么程度 | 复核方式 |
|---|---|---|---|
| F1 | **快照三元组 + 测量源** | 每个数字带：语料（数字通信原理 frozen）+ MANIFEST sha256 `a4beaedc…` + taken_at `2026-10-27T14:09:46` + 测量源（`collect_graph_data()`）+ build_state（pre_build）+ raw/clean 口径 | 逐数字对账；G2 §4 的 12 字段清单可直接套 |
| F2 | **数字与复算一致** | G4 引用的 62/54、357/65/79、296/18/12、25、23/20、8、4、57/55/9、43、15 等必须与我 §1/§3 的复算一致；不一致须给口径解释 | 对账本文件 §1 + §3 |
| F3 | **不用 D 源作设计依据** | 语料观测只可作基线/测试集/最坏输入；任何“因为本库路径少/同名多，所以应设计成 X”必须另给 A/B/C 证据，否则标「本项目假设」 | 逐条检验设计主张的证据列 |
| F4 | **≥2 个 A/B/C 源支撑** | 每条设计主张标证据等级与来源；单一来源的须显式标「本项目假设」 | 抽查核心主张：链路定义（A9 OWL/SPARQL + B `edge_types.py`？）、组合表（A9 + G2 谓词？）、判据（A：CQ/Paulheim/Cranfield + ？）、负例规范（A：Paulheim/Cranfield + ？）、盲判协议（A：Krippendorff/Artstein & Poesio，是否算两源需 G4 自证） |
| F5 | **哈希可复算** | 若 G4 给产物哈希，必须给可复算 recipe（G1 的 `bfdd85ab…` 已证明无法复算；G2/G3 的文件 sha256 可逐字节核） | 复跑 G4 声称的哈希；无 recipe ⇒ ⚠️ |
| F6 | **与既有裁决一致** | 不得与 G1/G2/G3 冲突：link≠edge；reference 排除或单列；contain 结构派生；派生相似度永不物化；extend 谓词待 G2 人判；8 退化边要清洗 | 逐条对账 G1 §2.3、G2 §1、G3 §2 |
| F7 | **边界纪律** | 只做方法与协议；不改产品代码/不 commit/不写 `docs/design`；写域 `graph-utility/` | `git status` 核对 G4 期间未改 `src/**`/`docs/design`；产物路径在写域内 |

---

## 3. 对 `G4-path-census.json` 的预核（researcher 已落盘，G4 正文出现前）

> 结论：**结构性数字全部可交叉验证通过；但“候选链路样例 15/23”的选择规则未写进 JSON，且非随机，G4 必须补齐。**

| # | census 声称 | 我的独立复算 | 判定 |
|---|---|---|---|
| 1 | 62 raw / 54 clean 边；79 / 65 覆盖节点；8 退化 | 完全一致 | ✅ |
| 2 | 弱连通块 raw 18 / clean 12；clean 尺寸 top10 `[25,9,8,7,2,2,2,2,2,2]` | 完全一致 | ✅ |
| 3 | 2-hop 路径 23；类型序列 extend→extend 17 / extend→reference 3 / reference→extend 3 | 完全一致 | ✅ |
| 4 | 3-hop 路径 20；eee 14 / eer 3 / ree 2 / ere 1 | 完全一致 | ✅ |
| 5 | 2-hop/3-hop 全部同文件、无跨文件 | 一致（23/23、20/20 same-file） | ✅ |
| 6 | nodes_used_by_2hop_paths = 25 | 一致 | ✅ |
| 7 | trivial separation：65 节点 / 4160 有序对 / 相邻 54 / 同文件 1094 / 2-hop 可达 23；p=0.012981 / 0.262981 / 0.005529 | 完全一致 | ✅ |
| 8 | 负例可构造性：N1=23、N2=10、N2 outdeg≥2 节点=8、N3=6、N5=23 | 与路径/类型数据一致（N3=含 reference 或混合类型的 2-hop 路径 6 条） | ✅ |
| 9 | extend 最长链 5 边/6 节点 | 一致（我另算：最大块内**混合**图最长简单路径 6 边；extend-only 子图 5 边，口径不同不矛盾） | ✅ |
| 10 | **candidate_sample_2hop_authored = 15 条** | 实际 2-hop 路径 23 条；**少 8 条**：`quantization-overview→pcm→dpcm`、`quantization-overview→pcm→linear-pcm-error-performance`、`quantization-overview→pcm→pcm-coding-methods`、`quantization-overview→scalar-quantization→uniform-quantization`、`sampling-theorem→ideal-sampling→aliasing`、`scalar-quantization→uniform-quantization→nonuniform-quantization`、`uniform-quantization→nonuniform-quantization→logarithmic-quantization`、`vector-quantization→scalar-quantization→uniform-quantization` | ⚠️ 选择规则只在脚本 docstring（“clean 2-hop 含作者边、按 (file, 节点序列) 排序取前 15”）——**非随机**且未在 JSON/G4 中披露；若这 15 条用于人判，必须说明偏差并优先改为全量 23 条或随机+种子 |
| 11 | 我的补充下界：clean 65 节点框内“两端同文件即判正”规则的 BA 上界 | **0.8706** | 供 C2 校准：若负例不按同文件/同章匹配，平凡规则即可拿到 ~0.87 BA ⇒ 区分度虚高 |

**census 自身诚实性**：JSON `honesty` 已写“只数结构上可枚举路径、不判语义；P1–P5 尚未人判；clean/raw 口径差异”——这一点**做得好**，G4 正文应继承。

---

## 4. G4 通过 / 退回标准（复核 gate）

### 4.1 最低通过条件（缺一即不得进入 Lead 决策包）

1. §2 A1–A5 全部 PASS（链路定义可操作 + 口径钉死 + 代表性声明）。
2. §2 B1–B3 全部 PASS（可操作定义 + 每判据有失效条件 + 错误归因分离）；B4/B5/B6/B7 至少给出明确处置（做/不做 + 理由）。
3. §2 C1–C4 全部 PASS（负例族、难度校准、trivial-separation 下界、夹具判别力）。
4. §2 D1/D3/D4/D5/D6 全部 PASS（人数、α 四档、CI、盲化、预注册）；D2/D7 给出明确样本量方案与独立性说明。
5. §2 E1–E4 全部 PASS（诚实边界 + L2 前置依赖 + agent 不可测 + 路径来源口径）。
6. §2 F1–F7 全部 PASS（快照绑定、数字一致、不拿 D 当设计依据、≥2 源、哈希可复算、与既有裁决一致、边界纪律）。

### 4.2 直接退回（R 级，不需要继续审）

- 声称“从 62 边现有图抽代表性 L3 样本/发布链路语义合格率”而不承认 43 条路径、单一连通块、全同文件的限制；
- 把 `reference` 链路算作语义断言（与 G2 P5 / G1 link≠edge 冲突）；
- 用随机节点对作主负例且不报 trivial-separation 下界（已知问题复现）；
- 盲判协议沿用 `JUDGE-SHEET-for-stranger.md` 的分组标签或示例答案；
- α 门槛拍成单阈值且与 G2 四档冲突；
- 任一关键数字（62/54、23/20、43、25、8、4、57/55/9）与我复算不一致且无口径解释；
- 用 D 源（语料观测）直接当设计依据且未标「本项目假设」。

### 4.3 无法核实的项（诚实边界）

- **G4 正文尚不存在**：本文件写于 G4 落盘前，A–F 的逐条判定待正文出现后补。
- **G2 人判结果不存在**：24 条边的人判矩阵/Human α 尚未执行 ⇒ “每跳边有效”只能作为协议依赖，无法当前核实。
- **链路级溯源**：edge 0/62 有 provenance/instances ⇒ L3×G 当前只能设计、不能实测。
- **“人”未定义**：L4c 的用户研究协议不属 G4 范围，若 G4 越界声称人本效用，按无法核实处理。

---

## 5. 复跑方法与产物

```text
复跑（cwd = 仓库根）：
  python artifacts/agent/verify/debate/graph-utility/scripts-verify/G4-verify-prep.py
      → G4-verify-prep.json（独立复算 G1/G2/G3 数字 + 路径样本空间）
  python artifacts/agent/verify/debate/graph-utility/scripts-verify/G4-census-crosscheck.py
      → G4-census-crosscheck.json（对 researcher census 的独立交叉核验）

确定性：G4-verify-prep.py 两次运行除 generated_at 外逐字节一致（已验）；
        G4-census-crosscheck.py 无随机（纯读盘 + 枚举）。
输入只读：frozen 快照复制到独立临时目录（gue-verify-*），不写 frozen、不写 researcher 产物。
本文件不 commit；不改产品代码；未写 docs/design。
```

---

## 6. 最担心的三个点（先给 Lead 的摘要）

1. **负例仍是“太容易”的高风险**：我复算的平凡下界——随机节点对同分量率 0.634%、有向可达率 0.097%；clean 65 节点框内“两端同文件”规则 BA 上界 **0.8706**。若 G4 的负例不按同文件/同章/同长度匹配，且不报 trivial-separation 检查，任何“区分度 0.9+”都不可信（这正是已知问题）。
2. **当前图根本凑不出代表性 L3 样本**：≥2 边简单路径只有 **23（2-hop）+ 20（3-hop）= 43 条**，**全部在同一个 25 节点块、全部同文件**，contain 一条都不参与，含 reference（无断言）跳的占 **12/43**。G4 若不给“pilot/案例研究，不代表性”的明说，或声称能从现有图抽样到有统计意义的样本量，必须退回。
3. **协议一致性两处硬伤待 G4 避坑**：①盲判模板 `JUDGE-SHEET-for-stranger.md` 按结构分组并给出示例答案（泄露 strata/锚定），G4 若沿用则盲判不成立；②α 门槛必须沿用 G2 四档（0.50–0.667=扩样、<0.50=重来），不能拍成单阈值；且 L2 人判尚未执行，“每跳边有效”这个 L3 前提目前只是协议依赖。
