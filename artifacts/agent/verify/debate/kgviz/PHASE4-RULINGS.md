# KG 可视化 Phase 4 裁决（Lead）

> **裁决者**：Lead
> **输入**：Phase 1 四方提案（4 份）＋ Phase 2 并集（V1–V8）＋ Phase 3 四方异议（4 份）＋ 人裁决（`USER-RULING-node-size-range.md`）＋ 语料重冻（`corpus-refreeze.json`）
> **协议**：`artifacts/agent/verify/debate/PROTOCOL.md`（FROZEN）M1 证据优先 / M2 独立根 / M3 登记未知 / E1 证据身份
> **产出**：本文件 → 冻结为 `docs/design/kg-visualization-v0.md`
> **日期**：2026-10-26

## 0. 裁决原则（先声明，避免"按声音大裁"）

```
P1 人裁决优先于一切辩论结论（本次唯一用例：节点大小范围 75%~165%）
P2 有实测证据的主张 > 经验值主张；经验值必须【标注为经验值】，不得冒充实测
P3 无法判定时，裁"不可判定 + 保守取值 + 降级条件"，而不是选一个看起来合理的数字
P4 冻结文档里不得留"永不触发的门禁"（残差 B）与"不可复现的证据"（残差 C）
P5 每条裁决必须能指回某份 Phase 3 异议的 ev: 身份
```

## 1. 证据身份总表（本文件引用的全部证据）

| 代号 | 来源 | 性质 |
|---|---|---|
| `ev:P1-*` | Phase 1 四方提案 | 主张 + 各自 bench |
| `ev:bench:kgviz-v2-discriminability` | `phase3-v2-discriminability.json` | 渲染像素测量（**像素差 ≠ 人类可辨**） |
| `ev:obj:A` / `ev:obj:B` / `ev:obj:C` / `ev:obj:D` | 四份 `PHASE3-OBJECTION-*.md` | 交叉异议 |
| `ev:user:size-range` | `USER-RULING-node-size-range.md` | **人裁决，最高效力** |
| `ev:corpus:refreeze` | `corpus-refreeze.json`（manifest_sha256 `a6866c46…`） | 语料身份 |

## 2. V1–V8 逐条裁决

### D-KGV-01 · V2 节点大小档数 —— **3 档（人裁决范围 × 2px 判据）**

```
裁决：节点视觉尺寸 ∈ 基准的 75%~165%（人裁决，线性尺寸）
      基准 = 现状 nodeRadius 常量 6.0px ⇒ 半径 4.50 ~ 9.90px（跨度 5.40px）
      档数 = 3 档，相邻半径差 2.70px
判据归属（防二次误读）：采用 【A 的 ≥2px 绝对判据】，非 C 的 ≥3px
      （同一范围下 C 的 3px 判据只给 2 档）
依据：ev:user:size-range（人裁决）＋ ev:obj:A（2px 判据）＋ ev:obj:C（反锯齿 +1.0px 常量偏移）
保守性：2px 是【工程先验，非人类实测】。若将来 DS-1 判读实验证明真实阈值 ≥3px ⇒ 降为 2 档
反锯齿：+1.0px 为常量偏移，差分时抵消，不改变档数；但验收脚本必须记录该偏移
不承诺：4 / 5 / 12–13 档 —— 三个提案的范围都比人给定更宽（A 1.5× / B 2.4× / C 1.7×），
        在这些范围内相邻差分别为 1.80 / 1.35 / 0.4px，均低于 2px 判据 ⇒ 物理上不成立
```

### D-KGV-02 · V2 并列（tie）策略 —— **必须显式定义，否则分位档人口失衡**

```
问题（ev:obj:D 新发现）：degree 大量并列 ⇒ 按分位切 3 档时人口 = 59 / 35 / 40，
      其中 44% 挤在最小档 ⇒ "分位 = 人口均衡"不成立
裁决：v0 必须冻结 tiePolicy（v0 取值：tie 归入较低档；阈值取 ≥ 分位点向上取整）
      并在验收里报告实际三档人口，不得只报"3 档"
理由：不定义 tie 策略 = 同一个"分位映射"能产生完全不同的视觉效果
```

### D-KGV-03 · V3 映射契约 —— **分位驱动，不用 sizeScale**

```
裁决：冻结 kind:"quantile" + thresholds + tiePolicy + relative:true
      【不冻结】sizeScale 枚举术语
依据：ev:obj:D 实测分位 ≠ sizeScale（同一 degree=5 在 live 语料→r8、在均匀语料→r4；
      5 档人口 quantile [41,17,25,24,26] vs linear [41,66,20,4,2] / sqrt / log 均不可互换）
      ev:obj:A 已撤回「sizeScale 必须」（分位结构性消除长尾、自带上下界、不受 max 异常值影响）
附加约束（ev:obj:A 弱主张，采纳）：相对量（分位）驱动的编码【必须在 UI 显示绝对原值】
      原因：kg-ontology-v0.md 已定 reference 是"无断言跳转" ⇒ 图谱没有重要性语义；
            分位大小会凭空创造"重要性"含义 ⇒ 必须用 tooltip 显示 degree 原值抵消
```

### D-KGV-04 · V4 3D 大小 —— **v0 不做 3D 大小编码**

```
裁决：3D 视图节点等大；重要性/度数用【颜色】编码，不用大小
依据：ev:obj:D 实测透视造成屏幕尺寸比 1.78×（相机距离 1374.88–2447.01，fov 50）
      叠加人给定范围 2.2× ⇒ 最坏表观比 3.92×
      ev:obj:A 信噪比 = (1.25-1.0)/(1.78-1.0) ≈ 0.32 ⇒ 信号 < 噪声 ⇒ 不可解释
      ev:obj:B 已撤回自己的 1.0–1.25 区间
成本澄清（ev:obj:D）：3D 成本不是障碍（galaxy 共享 SphereGeometry + mesh.scale，0 额外 draw calls）
      ⇒ 拒绝 3D 大小的理由是【语义不可解释】，不是性能
falsifier：若 3D 深度判读任务正确率 ≥80% 且归一组显著优于等大组 ⇒ 可撤回本条
```

### D-KGV-05 · V1 内容体量编码 —— **v0 不做备选 size 模式，信息进 tooltip**

```
裁决：v0 只做 degree 驱动的 3 档大小；内容体量（chars/行跨度）只进 tooltip，不做视觉通道
依据：ev:obj:A 实测 collect_graph_data 的 node 字段无 chars
      （['description','end_line','file','id','kp_id','label','name','range_ok','start_line']）
      ev:obj:B 已撤回 v0 要求
      口径澄清（ev:obj:B）：A 的 3.1× 是【end_line−start_line 行跨度】，
                           chars 口径实测 46×（707–32,847）⇒ 两者不是同一个量
      D-KG-07 禁的是【验收判据】（长度/行数/块数），不是数据字段/视觉信号
v1 候选：若将来要加 size 模式，必须先做 T2 A/B 验证「用户真的需要按体量排序」
```

### D-KGV-06 · V5 标签 —— **可读性前置成立；性能前置被撤回**

```
裁决：v0 必须先做标签 LOD/避让，再做 3 档大小
      【撤回】"标签是 size 的性能前置"这一说法
依据：ev:obj:D 自我修正：真实 134 节点下标签开销仅 0.4→0.5–0.6ms（20–33%），
      占 60fps 预算 3–4%；"75%" 只在合成 N=3000 成立
      保留的可读性论据：134 个标签无条件全画、无避让 ⇒ 标签淹没大小差
验收：T-label（见 §4）
```

### D-KGV-07 · V6 布局稳定性 —— **v0 只承诺"会话内稳定"，跨会话持久化为 v1**

```
裁决：v0 = 确定性种子（同一语料每次打开布局一致）+ 会话内保位（hover/zoom/select 不触发全局 reheat）
      v1 = 跨会话位置持久化（需先做实验）
依据：ev:obj:D 真机 5 次实测：reset 平均位移 mean 185.6–219.2px（中位 199.4），p90≈398px，
      92.5–97.8% 节点移动 ⇒ 布局确实每次都大变
      ev:obj:B 已拆两级：承认"跨会话持久化"三条收益均为推理、无实测
判据（若 v1 要做）：重开定位指标 ≤1.5× 首次（C 的 V-07）
```

### D-KGV-08 · V7 埋点 —— **2 字段 + 会话末聚合**

```
裁决：采 nodeRadius 变化 + graphStyle 切换（+ style/zoom 上下文）
      【不采】node_radius_px（映射产出，改映射后历史值不可比）
      【不采】labelHover 逐事件（per-frame 写入是性能反模式）；若做必须会话末聚合
依据：ev:obj:C 把 V7 收缩为 E1/E2 且各自指向一个"现在就有用"的决策：
      · E1 nodeRadius：用户可调 4–12（graph-settings.js#L561），但当前无人知道用户是否调过
      · E2 graphStyle：D5 已冻结"曝光→点击<10% ⇒ 提示无效"，数据源不存在使该裁决无法执行
      ev:obj:A 论证：埋点只记拓扑/事件事实，不记映射产出
```

### D-KGV-09 · V8 毛球态判定 —— **零新增字段成立，但阈值组合必须重定**

```
裁决：毛球态判定用前端 Union-Find（零新增字段）；但 v0 阈值组合【当前自相矛盾，必须改】
依据：ev:obj:D 零新增字段成立（groups 已在 graph-groups.js#L83-L121，O(N+E)）
      但 ev:obj:B 的阈值组合在当前语料自相矛盾：
        labels=134>60 ✅ 命中、edges/nodes=3.02<4 ❌ 不命中、avgdeg=6.03<8 ❌ 不命中
        ⇒ 结果：开局永远判为"毛球态"
裁决：v0 改为【单条件 + 实测校准】：以 avggroupsize 或最大分组占比为主判据，按 §3 残差 B 的实测值校准
```

## 3. 对已冻结本体文档的残差裁决（ev:obj:D §8）

> 依据 P4：冻结文档里不得留"永不触发的门禁"与"不可复现的证据"。

### D-KGV-10 · 残差 A —— `kb_build` 是破坏性迁移，测量必须记 build 状态（**必须改**）

```
事实：kb_build.py#L293-298 strip hints 后 open(full,"w") 真的写回源 md；#L312 写回 sidecar
      同一临时副本：build 前 collector 404 边 → build 后 collector 454 边
⇒ 原 §5.2 写成"两条只读路径"低估了它
裁决：§5.1/§5.2 增加一句：「任何边/degree 测量必须记录 build 状态（pre/post + build sha）」
```

### D-KGV-11 · 残差 B —— 99.2% 门禁永不触发（**必须改**）

```
事实：§5.3 的"最大分组占比 99.2%"是过期数字；当前可复现语料实测 HEAD 81.97% / live 89.55%
⇒ 99.2% 阈值永远不会触发 ⇒ 等于 gate 不存在
裁决：改为「实测 >80% 触发」，并标注 99.2% 为过期数字（来源：更早语料）
```

### D-KGV-12 · 残差 C —— 语料身份改为三元组，禁止单一"语料 sha"（**必须改**）

```
事实（ev:corpus:refreeze 实测）：
  git archive HEAD docs/example  ⇒ 61 节点 / 154 边
  当前工作区 AAA_Vocab           ⇒ 134 节点 / 404 边
  方案 1（构造可复现语料）实测【不可行】：需重建 73 sidecar + 24 md ⇒ 那是"重新造数据"不是"复现"
裁决：
  ① 语料身份 = (HEAD sha, manifest_sha256, 测量时间) 三元组
  ② 禁止再用单一"语料 sha"（旧值 051deb78 无法对应任何可复现状态）
  ③ 设计文档必须写明：该语料不可从 git 复现，manifest_sha256 是唯一身份，且一旦工作区改变即永久失效
  ④ 判定"语料是否一致"看 manifest_sha256，不看 artifact_sha256（后者含时间戳）
新增事实（ev:corpus:refreeze）：158 个语料 md 中只有 134 个产生 KP，24 个不产生
  ⇒ 「1 文件 1 KP」表述修正为「134 个 KP 文件各占一个 md，另有 24 个无 KP 的库内 md」
```

## 4. v0 验收（可测）

```
T-size   3 个不同 quintile 节点，用户挑"最大" ⇒ ≥90% 正确；<80% ⇒ 降为 2 档
T-label  标签避让后，随机 20 个节点中用户能读出 ≥16 个标签（80%）
T-depth  3D：给两个深度不同但同 degree 的节点，用户判断"哪个更重要" ⇒ 若 ≥80% 判对，
         说明用户在把深度误读为重要性 ⇒ 强化"3D 不用大小"的裁决
T-double 同一节点同时用颜色+大小编码 degree ⇒ 检查是否产生"双重编码冲突"报告
T-stable 同一语料打开两次，确定性种子下节点坐标完全一致（字节级）
T-census 语料节点/边数 = 134/404（按 manifest_sha256 校验），偏差 ⇒ 验收失败并报 U-C2
```

## 5. 登记未知（不掩盖）

```
U-KGV-1  2px 判据是人类真实可辨阈值吗？ → 需要 DS-1 判读实验（做 >3 档时必要前提）
U-KGV-2  人给定 75%~165% 的基准是否会随用户 nodeRadius 设置一起缩放？
         （若用户把 nodeRadius 调到 12，范围是 9–19.8px 还是仍以 6 为基准？）
U-KGV-3  tiePolicy 取"归较低档"是否会造成"大量节点看起来一样小"的负面观感
U-KGV-4  graphStyle 埋点落地前，D5 的"点击<10% ⇒ 提示无效"仍无法执行
U-KGV-5  T-size/T-label/T-depth 需要真人参与 ⇒ v0 发布前是否必须完成，待 Lead 与人确认
```

## 6. 本裁决中属于"经验值/先验"而非实测的清单（诚实披露）

```
· 2px 可辨判据（A 的工程先验）
· 3 档这个结论（= 人范围 × 2px 判据 的算术结果，不是判读实验）
· T-size 的 90% / 80% 阈值
· T-label 的 80% 阈值
· tiePolicy「归较低档」的选择
⇒ 这些在设计文档里必须标注为【先验/待校准】，不得写成实测
```

## 7. 状态

```
本文件 = Phase 4 裁决。Phase 5 = 据此冻结 docs/design/kg-visualization-v0.md。
同一提交内同时应用 D-KGV-10/11/12 对 kg-ontology-v0.md 的修订（残差 A/B/C）。
```
