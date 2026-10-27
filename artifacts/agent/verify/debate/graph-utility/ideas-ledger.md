# GUE 板块 ideas / 缺陷台账（**Agent 研究发现，不是人的需求**）

> **用途**：记录「图谱-agent记忆」板块研究中发现的**待办/缺陷/待裁问题**，防丢。
> **与 `docs/todo/ideas.md` 的区别**：那个文件只记**人提出**的需求（其维护规则禁止混入 Agent 发现），且不在本研究员写域。
> 本文件是 GUE 板块的内部台账；**Lead 可把它合并/转登到正式台账**（若需要）。
> **纪律**：不 commit；不改产品代码；每条给证据（file:line / 产物路径）；状态：`待并入` / `已由 G2 采用` / `待裁`。
> 最后更新：2026-10-27（G2 轮）

| 编号 | 类型 | 发现 | 证据（file:line / 产物） | 影响 | 状态 / 动作 |
|---|---|---|---|---|---|
| **GUE-IDEA-001** | 文档缺陷 | `collector.collect_graph_data()` 的 docstring 写「边仅由两类来源构建（**不读侧车 edges[]**、不扫描正文 wikilink）」，但实现经 `derive_file_graph_edges` → **`derive_sidecar_edges` 读取 `sidecar.edges[]`**（本库 26 条作者边即来自此） | `src/memoria/graph/collector.py:44-49`；`src/memoria/graph/edge_derivation.py:643-676`；`collector.py:79-84` | G2 基线说明若照抄 docstring 会漏 26 条边；任何"边类型/数量"描述可能错 | **已由 G2 采用**：G2 以代码为准，不改产品代码；建议 Lead 转登后由 builder 修 docstring（1 行） |
| **GUE-IDEA-002** | 测量陷阱 | 图谱有**两条后端路径**：`get_graph_data()→collect_graph_data()` 与 `build_kb()→build_knowledge_base()` 看到不同边集；且 `kb_build` 是**破坏性迁移**（回写源 md/sidecar），同一副本 build 前 404 边 → build 后 454 边 | `src/memoria/services/document.py:2124-2141`；`src/memoria/graph/kb_build.py:293-298,312`；`docs/design/kg-visualization-v0.md:273-278`；`docs/design/kg-ontology-v0.md:104-127` | 所有边/度/覆盖率数字跨路径、跨 build 不可比 | **已由 G2 采用**：G2 协议 §4 给出必填字段清单（build_state/build_sha/measurement_source 等 12 项） |
| **GUE-IDEA-003** | 语料绑定事实被误当普适 | `kg-ontology-v0.md:21` 写「全部快照 100% reference；relevance 100% 默认 0.7」——那是 **docs/example（AAA_Vocab）** 语料；**本库（数字通信原理 frozen）实测 contain 33 / extend 21 / reference 8，relevance 0.6/0.7/0.9 三种**（100% 类型默认） | `docs/design/kg-ontology-v0.md:21`；`G1-framework.md §3`；`G1-baseline.json`；`G2-edge-inventory-raw.json` | 若把"100% reference"写成 GUE 基线事实 ⇒ 错；会掩盖 extend 的存在 | **已由 G1/G2 采用**：所有结论按本库重测；建议 Lead 在汇总时注明该结论语料边界 |
| **GUE-IDEA-004** | 数据缺陷（研究输入） | 62 边中 **8 条 contain 退化边**：7 条同名自指（如「※线性相位理想低通滤波器 → 同名」）+ 1 条 OCR 错名（「连续时间LTI系统的频域分析应用 → 传连续时间LTI系统的频域分析应用」）；另 1 条疑似**并列错包含**（`(1) 两个正交的脉冲信号 → (2) 两个正交的已调信号`）与 1 条疑似**松引用**（`瑞利分布与莱斯分布的比较 → 余弦信号加窄带高斯随机信号`） | `G2-edge-inventory-raw.json`；`scripts/G2-edge-inventory.py` 退化判定；`G2-sampling.json` 的 `derived_contain_degenerate` 层 | L2 语义基线必须清洗；否则"边语义合格率"被稀释；这些同时是 M2 known-bad 夹具 | **待 G2 执行/待裁**：G2 人判时作 known-bad；是否修数据属产品侧（不在本研究员写域） |
| **GUE-IDEA-005** | 语义混合（研究问题） | `extend` 21 条至少混了 3 种用法：章节先后 / 子题展开 / 平行变体；没有谓词定义，无法区分 | `G2-edge-inventory` 全量清单；`G2-L2-protocol.md §1` | "extend 是一种语义关系"可能不成立；若人判 D 占比 >50% ⇒ 应降级为顺序/结构边或拆新类型（须走 `kg-ontology-v0.md:161-169` 三闸） | **待 G2 人判**：预注册 falsifier；结果出来再裁 |
| **GUE-IDEA-006** | 测量口径 | G1 发现「357 节点 / 62 边中仅 79 节点(22.1%)被边覆盖、278 孤立、296 连通块、最大块 25」——图极稀疏，L3 在现图不可测 | `G1-framework.md §3`；`G1-baseline.json` | "链路语义"研究必须等图扩充或独立生成候选路径；不能拿现图当"链路样本" | **已由 G1 采用**：L3 列"完全没测法"；等 G4/G5 |
| **GUE-IDEA-007** | 方法 | LLM/agent 判官不可直接当人判（Lead/G1 已定） | `G1-framework.md §5.7 M3`；本协议 §2.1-C | 若用 agent 代判，α 只作内部参考 | **已由 G2 采用**：判定者表显式标注；人判优先 |

## 备注

- 本台账**不替代** `docs/todo/ideas.md`（人需求）与 `docs/todo.md`（工作项索引）；若 Lead 认为 GUE-IDEA-001/002 应进正式台账，请由 todo-owner 转登（本研究员无该写域）。
- GUE-IDEA-001 的修复建议（供 Lead 转派 builder）：把 `collector.py:44-49` docstring 改成
  「边来自 range 几何 contain + sidecar links[] 投影 + **sidecar edges[]**（经 derive_sidecar_edges）」；不改行为，只改注释。
