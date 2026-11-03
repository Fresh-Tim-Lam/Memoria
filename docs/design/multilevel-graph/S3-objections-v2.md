# S3 异议与 A/B 差异 v2（复核方修订版对照）

> **依据（唯一裁决依据）**：`docs/design/multilevel-graph/S3-RULINGS.md`（sha `1d62fb48…`，R-S3-1..R-S3-8）。
> **对象**：`S3-visual-proposal-A-v2.md`（主办研究，sha **`b8311e10664a15c9e7325cd13b2cf44c9075e744443dd3ffe019afdbc775d2aa`**，31,849 B）与 `S3-visual-proposal-B-v2.md`（本复核方，sha **`b3a6fdd84b2155c8c4e9ea9474418171710822c238dc1aa864087f5b6768f754`**，21,595 B）。
> **性质**：B-v2 以 S3-RULINGS 为依据独立修订，完成后对照 A-v2；逐项列差异、不合并。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S3-RULINGS/S0/S1/S2。

---

## 0. R-S3 关闭矩阵

| 裁决 | A-v2 落位 | B-v2 落位 | 判定 |
|---|---|---|---|
| R-S3-1 label 确定性 | S3-2：min canonical member label + 「等 N 个」；root_exempt「全库」；禁 local_seq；fallback cluster_key 前缀；跨 run 机检 | S3-2：同规则；root_exempt「全库」；禁 local_seq；跨 run 稳定机检；fallback 稳定短串 | **关闭**（fallback 细节见 §2-2） |
| R-S3-2 预算归属 | S3-11：S4 裁剪；Renderer 只校验/渲染；超硬上限 `RENDER_BUDGET_EXCEEDED`；数值 S8 | S3-11：同 | **关闭** |
| R-S3-3 bridge 视觉 | S3-1/S3-5：无 node role=bridge；桥只 edge state + 统计；role∈{member,focus} | 同 | **关闭** |
| R-S3-4 接口命名 | S3-6：render/update/dispose/on/getCapabilities；无 mount/setSelection | 同 | **关闭** |
| R-S3-5 无簇 UX | S3-8：layout_group semantic=false、非 cluster；banner/affordance 用户动作 | 同 | **关闭** |
| R-S3-6 level_label | S3-4：VM level_label；渲染器非交互层标；面包屑/历史归 S5 | 同 | **关闭** |
| R-S3-7 KP 固定大小 | S3-3：KP 固定 8px；cluster 公式；2D/3D 同 token | 同（固定 8px + A 公式） | **关闭** |
| R-S3-8 并集 | 吸收 B 的 label/VM 白名单/bridge；A 的 token 表/a11y/无簇/预算；metrics 不进 VM；layout_group semantic=false | 吸收 A 的 token 表/公式/无簇 UX/a11y/预算；保持独立 VM 白名单/metrics 不进 VM | **关闭**（VM 字段差异见 §2-1） |

**结论**：R-S3-1..8 两版均关闭，**无 P0/P1**；剩 P2 收口（VM schema 字段、fallback 字符串、3D token 语义），可由 SE/Lead 在冻结稿统一。

---

## 1. A-v2 / B-v2 逐项差异（S3-1..S3-12）

| 议项 | A-v2 | B-v2 | 差异与判断 |
|---|---|---|---|
| S3-1 节点类型 | kind 两类；role∈{member,focus}；无 bridge；token 表带 a11y 列 | 同；无 bridge；role∈{member,focus}；token 表 2D/3D | 一致；A 的 a11y 列更显式，B 的 S3-10 覆盖。 |
| S3-2 簇视觉 | A 公式 + 确定性 label（min member+等 N）+ root「全库」+ fallback `cluster_key[:8]`；token 表 | 同公式/规则；fallback 稳定短串；token 表吸收 A | 核心一致；**fallback 字符串不同（P2-2）**；A 的 `label_key?`/localize 细节更细。 |
| S3-3 KP 视觉 | 固定 8px；range_ok；点击提示；不按 degree | 固定 8px；label/range/click；不按 degree | 一致。 |
| S3-4 层次感知 | level_label + 非交互层标；面包屑/历史归 Presentation/S5 | 同 | 一致。 |
| S3-5 边视觉 | 完整 type token 表（颜色/线宽/虚线） + bridge 仅 state + data_edge_ids 不进 renderer | 同 token 表（吸收 A）+ bridge 仅 edge state + 不画幽灵边 | 一致；A 的 `aggregate_count`/`data_edge_ids` 字段更细。 |
| S3-6 接口 | canonical 五方法；getCapabilities 含 maxNodes/maxEdges；无 mount/setSelection；R1–R6 | 同五方法；getCapabilities 含 renderer/supports*（**未列 maxNodes/maxEdges**，预算在 S3-11） | 基本一致；**B 需在 capabilities 补 maxNodes/maxEdges 或明确引用 S3-11 字段（P2-3）**。 |
| S3-7 事件 | 最小集 + 可选 hover/focus；2D/3D 同 payload；无导航 | 同 | 一致。 |
| S3-8 无簇 UX | KP+layout_group semantic=false+banner+用户动作 affordance | 同；无自动 agent；不伪造 semantic | 一致；A 文案/按钮更细。 |
| S3-9 默认/全展开 | 同源同 VM/Renderer；全展开徽标；不第二数据源 | 同 | 一致。 |
| S3-10 a11y | 对比度/键盘/aria overlay/reduced motion；无 setSelection | 同核心；断言更简 | 一致；A 更细（aria-expanded/aria-live/焦点环）。 |
| S3-11 预算 | S4 裁剪；Renderer 只校验；硬上限 fail-visible；maxNodes/maxEdges；target_fps/动画/布局稳定 | 同归属/失败语义；预算字段存在；数值 S8 | 一致；A 的 capabilities max 字段更明确。 |
| S3-12 VM 一致性 | 白名单允许 `data_edge_ids?`（审计、Renderer 剔除）、`label_key?`、`underlying_hop_count`、`aggregate_count`；metrics 不进 | 白名单允许 level_label/layout_group；**未列 data_edge_ids 进 VM**；metrics 不进；renderer 不读审计字段 | 核心一致；**VM schema 字段集不同（P2-1）**；A 审计字段在 VM、B 更严；需 S6a 统一。 |

**总判断**：两版在 R-S3 上已收敛；A-v2 的 token 表/a11y/无簇文案/接口细节更完整，B-v2 的 VM 白名单更严；无实质 P0/P1。建议冻结稿以 A 的 token/UX 为主干、取 B 的严格 VM 白名单，并统一下列 P2。

---

## 2. 仍未解决的 P2（建议 SE/Lead 在冻结稿统一）

### 2-1 `data_edge_ids`/审计字段是否进 VM：A 允许、B 排除

- **现状**：A-v2 S3-12 VM 白名单包含 `data_edge_ids?（仅审计，不进 Renderer）`、`label_key?`、`underlying_hop_count`、`aggregate_count`；B-v2 S3-12 白名单只含 `level_label/layout_group/nodes/edges`，明确 Renderer 不读 `data_edge_ids`，但未把 `data_edge_ids` 列为 VM 字段。
- **风险**：S6a 若按 A 允许 `data_edge_ids` 进 VM，可能被渲染器/第三方读取；若按 B 排除，审计方需从 VM 外取（S2 run/DataSource）。两种都合法但必须唯一 schema；冻结门禁 Lead 机检会比对 VM 白名单。
- **建议**：冻结 **`data_edge_ids` 不进 VM**（B 更安全；审计从 run/DataSource 取）；若保留审计字段，必须定义 `audit_only=true` 且 Renderer 投影剔除 + schema 拒绝渲染器读取。`label_key`/`underlying_hop_count` 同理决定进/出；`aggregate_count` 可由取景层计算，不进 VM 或仅作为显示字段且不暴露内部 id。
- **证据**：A-v2 S3-12；B-v2 S3-12；S0 R-3/S2 R-S2-9。

### 2-2 label fallback 字符串与本地化后缀未唯一

- **现状**：A-v2 fallback = `"簇 " + cluster_key[:8]`；B-v2 fallback = 稳定短串（canonical id/label 派生）；两者都确定性，但字符串不同；「等 N 个」的本地化/i18n key 未冻结。
- **风险**：同成员集在两版实现下显示名不同；i18n 文案（标点/顺序/语言）未定导致 2D/3D/审计不一致；S3 预注册要求视觉可机检，label 是视觉编码。
- **建议**：冻结 fallback 格式（推荐 `cluster_key` 前 8 hex + 可选 "簇" 前缀）与 i18n key/参数（`cluster.more_members`、`cluster.root_label`）；机检 `label == deterministic_label(members, locale)`，跨 run 稳定；本地化只影响后缀，不影响 min member base。
- **证据**：R-S3-1；A-v2 S3-2；B-v2 S3-2。

### 2-3 3D KP 固定大小的 screen-space vs world-space 未裁

- **现状**：R-S3-7 要求 KP 固定大小、2D/3D 同 token；A-v2 S3-3 固定 8px，S3-15.5 自列"3D 投影下固定 screen-space 还是 world-space 需 S3/SE 定"；B-v2 S3-3 固定 8px、2D/3D 同 token，但同样未定义 3D 投影语义。
- **风险**：若 3D 用 world-space，缩放/远近会改变视觉大小，等同"大小随距离变"，可能被误读为重要性/成员数；2D/3D 同 token 无法机检；若 screen-space 固定则需每帧投影计算。
- **建议**：S3 冻结"3D KP 固定 **screen-space** 尺寸（等价 2D 8px token；距离只影响遮挡/深度，不影响屏幕直径）"；cluster 半径公式按 member_count 映射到 screen-space；3D 投影只影响深度/遮挡；机检同 VM 下 2D/3D 的节点屏幕直径 token 一致（允许 DPI 缩放）。
- **证据**：R-S3-7；A-v2 S3-3/§15.5；B-v2 S3-3。

> 另：B-v2 的 `getCapabilities` 未列 `maxNodes/maxEdges`（A 有）；建议 B 吸收（P2-4，不阻塞）。A 的 `label_key` 进 VM 与 B 白名单需统一（归 2-1）。A 的 `aggregate_count` 显示来源需明确"取景层给、不遍历 data_edge_ids"（P2-5）。

---

## 3. 点名审查结论（v2）

1. 节点类型第三类/单点簇：**PASS**（两版 kind 两类、role∈{member,focus}、无 bridge 节点、singleton→kp；A/B S3-1 断言）。
2. 簇大小/计数可机检/伪造：**PASS**（A 公式、badge=member_count、确定性 label；B 同；fallback 细节 P2-2）。
3. 边视觉/presence：**PASS**（只画 shown；suppressed/unknown 不画幽灵边；type token 表；bridge 仅 edge state）。
4. 渲染接口纯度/2D/3D：**PASS**（canonical 五方法、VM 白名单、无 mount/setSelection；B capabilities max 字段 P2-4）。
5. 事件最小/导航不进：**PASS**（两版一致）。
6. 无簇 UX：**PASS**（KP+layout_group semantic=false+非 cluster+banner+用户动作；不伪造语义）。
7. 默认/全展开第二数据源：**PASS**（同源同 VM/Renderer；全展开徽标；无第二数据源）。
8. a11y/性能预算可机检：**PASS**（对比度/键盘/aria/reduced motion；S4 裁剪/Renderer 校验/硬上限；数值 S8）。
9. VM 纯度/簇状态不进 VM：**PASS**（两版无 run/dendrogram/mode/nav；metrics 不进；data_edge_ids 审计字段差异 P2-1）。

---

## 4. 结论

- **S3 两版均关闭 R-S3-1..8，无 P0/P1**；A-v2 的 token 表/a11y/无簇 UX/接口细节更完整，B-v2 的 VM 白名单更严格；可进入 SE 工程校核与 Lead 机检。
- **P2 收口**：① `data_edge_ids`/审计字段是否进 VM（推荐不进）；② label fallback/i18n 字符串唯一；③ 3D KP screen/world 固定；④ B capabilities 补 maxNodes/maxEdges；⑤ aggregate_count 不遍历内部 id。
- 未写产品代码/契约，未 commit；差异逐项列出未静默合并。

> 参考锚：R-S3 `S3-RULINGS.md:17-49`；A-v2 S3-1..S3-12/§15；B-v2 S3-1..S3-12；S0-9/D-4 `S0-terms-v1.md:75-79`；S1 D-4 `S1-dimensions-v1.md:99-107`；S2 R-S2-6/12 `S2-clustering-v1.md:17,69-76`。
