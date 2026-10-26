# Lead 派发规范（Dispatch Rules）

> **读者**：Lead（主控）。
> **用法**：**不要求通读**。按「触发时刻」读对应一节即可（见下方索引）。
> **为什么这么设计**：2026-10-24 复盘发现，**写在文档里靠"记住"的规范，遵守率就是随机数**；
> 只有"让违规在物理上做不到"的规则才稳定生效。因此本文件 95% 的条目都对应一个
> **机检（`team_audit.py`）或工具级拒绝**；纯靠自觉的只剩 3 条，见 §5。
>
> **不变量摘要（每次对话由 AGENTS.md 自动注入，≤15 行）** → 见 [AGENTS.md §0.5](../../AGENTS.md)。
> **配套**：`docs/guides/agent-team-lessons.md`（27 条教训判据，派发前必读三条）。
> **机检**：`scripts/agent/team_audit.py`（11 类）。

---

## 0. 对话被压缩后（**强制重读本节**）

> ⚠️ **危险动作强制边界见 §B-danger-1**（紧接 §1 之后）：共享工作区禁止 checkout/reset/restore 等破坏性回滚。
上下文压缩会**确定性地丢掉**：完整规范、任务板细节、未完成事项的因果。
压缩摘要能保留事实，但**不保留约束**。所以压缩后立刻做这 4 件：

```
1. 读 AGENTS.md §0.5 六条不变量（会被宿主自动注入，确认它还在）
2. 跑 team_audit.py —— 拿到当前 FAIL/WARN（这是唯一可信的现状）
3. team_task_list 未完成任务（确认 owner 与写域，别凭摘要干）
4. 确认是否有 in-flight 的后台任务（job_list）—— 摘要有可能会漏
```

**判据**：压缩后**不凭记忆回答"还剩什么要做"**，一律重新查任务板 + 机检。

---

## 1. 要 `spawn_teammate` 时

### 触发
即将创建任何 teammate（无论 fresh 还是 fork）。

### 检查清单（顺序执行，不可跳）

| # | 检查 | 机检 | 违规后果 |
|---|---|---|---|
| 1.1 | **先建任务，再 spawn**（任务存在且 `owner` 已留给该成员） | `dispatch_release::H1` | WARN「派发了但任务板无 owner」 |
| 1.2 | 该任务的 `writeScopes` **必须显式声明**，且与所有存活成员**无交集** | `write_scope`（advisory→spawn 前置） | 重叠 ⇒ **排队，不许并行** |
| **1.2b** | **写域必须写到产物级**：具体文件或**任务专属子目录**。<br>**共享产出根**（`artifacts/agent/verify`、`docs/design`、`team/`、`scripts/benchmark/`）**不得单独作为 writeScope**，<br>除非任务确实要改该根下任意文件（此时写明理由）。<br>**理由**（治理 skill 的「写域到产物级」）：共享根 vs 其子路径会产生**假重叠**；<br>实测 11 条 write_scope WARN 里 **9 条是假重叠**，会训练大家忽略 WARN（lessons L1.2 假红成本）。 | `write_scope`（分级后） | 假重叠 ⇒ INFO；同文件/同子目录 ⇒ WARN |
| 1.3 | 选模型：**默认 `deepseek-flash`**；只有需要长链推理/契约裁决才用 `v4-pro`，且必须在回报里说明理由 | 人工 | — |
| **1.3b** | **选 `mode`（四档，见下）—— 不许不选**。不传 `mode` 会被静默默认为 `standard`，等于"没做决策" | `mode_policy`（待实现） | WARN「未做模式决策」 |
| 1.4 | `context`：**默认 `fresh`**。只有"接续我自己未完成的上下文"才用 `fork` | — | — |
| 1.5 | prompt 必含 5 项：① 任务 id ② 写域 ③ 验收标准 ④ 必读文档（含 lessons 三条）⑤ **卡壳 >N 分钟先回报** | 人工 | — |
| 1.6 | 若为一次性只读调研（不写代码、不需要审计）⇒ **优先用 subagent，不占名册** | — | — |

### 1.3b 模式路由表（DSH 四档，源码 `tool-agent-team/src/index.ts`）

```ts
L43: reasoningEffort = mode === 'mechanical' ? 'off' : mode === 'deep' ? 'high' : undefined
L44: modeModel       = mode === 'deep' ? config.deepModel
                     : mode === 'mechanical' ? config.mechanicalModel : undefined
L448: const mode = args.mode ?? 'standard'      // ← 不传 = 静默默认
```

| mode | 推理链 | 模型 | 该给谁 |
|---|---|---|---|
| **`mechanical`** | **off** | 可配 `mechanicalModel` | **纯执行不可判断的活**：只读扫描 / 统计 / 格式检查 / 生成报告 / 一行修复 / 跑命令取数 |
| `standard` | 默认 | 默认 | 常规实现：多文件、需判断、要自验 |
| `deep` | **high** | `deepModel`（本部署实测 = v4-pro） | 契约裁决 / 架构设计 / 等价性判断 / 高风险评审 |
| `creator` | 默认 | 默认 + creator preset | **改 DSH 插件 / bundle / preset**（唯一能做的模式） |

**强制规则**：`mode` 必须**显式传**。确实无法判断时用 `--mode-explicit false` 显式留下「未决定」痕迹
（该状态**合法**，机检应单列 `WARN「显式未决定」`，**不得**与「历史记录缺失」混为一谈）。理由 —— 不传就是 `standard`（源码 `args.mode ?? 'standard'`），
日志上「忘了想」与「决定用 standard」完全无法区分。

**两条铁律**：
1. **能用一个命令或一次扫描得出结果的任务，不许用 `standard`/`deep`** —— 那是纯浪费推理链
2. **`deep` 会把模型换成 `deepModel`（v4-pro）** ⇒ 与人「团队统一 flash」冲突 ⇒ 用 `deep` 必须在回报里写明理由，
   否则退化为 `standard` + 显式 `model: deepseek-flash`

### 本轮实证（为什么要 1.3b）
```
2026-10-24 spawn 记录：
  steward  → mode: deep     ← 错：任务是"设计文档"，standard 够；且模型被换成 v4-pro，违反"统一 flash"
  steward2 → mode: standard
  todo-owner / team-plugin-creator → 未传 mode ⇒ 静默默认 standard
⇒ 一次都没用过 mechanical，尽管当天有大量"扫一遍仓库/生成报告/跑命令取数"的活
```


### 本轮实证（为什么要 1.1/1.2）
```
p0-selection / boot-probe 都是【先 spawn 后补任务】⇒ 违反 1.1
⇒ 后来退役时它们名下的 5 条任务变成「幽灵 owner」，机检报 2 条 FAIL
```

### 反面案例（为什么要 1.3 默认 flash）
`team-plugin-creator` 用 **flash** 交付了 R1–R8（127 tests + tsc 0），质量不打折。
`v4-pro` 本轮 3 个成员最终全部退役（成本高、收益未证明更高）。

---


## B-danger-1 禁止对共享工作区做破坏性回滚（2026-10-26；v2 细化 2026-10-26）

> 依据：`steward` SF-20261026-054 审计 v1 指出 5 个问题（命令清单不全 / 无强制力 / 共享未定义 /
> 留证格式未定义 / 位置可发现性差）。v2 逐条补齐。**强制力诚实标注见本节末**。

### 1. 共享 vs 独占（默认为共享）
```
【默认】工作区是共享的 —— 任何成员都可能正在编辑任何文件。

【独占】唯一可机检的条件：文件位于【独立 worktree】内。
  · worktree 内默认为独占，前提是【路径唯一】（按「成员+任务」命名，如 %TEMP%/wt-<member>-<task>）
  · 若同一 worktree 被多人共用 ⇒ 仍按共享处理，并显式声明使用期
  · 判定只看「是否独立 worktree 路径（+唯一性）」⇒ 拦截器也只认这一条

【为什么删掉了 v2 原稿的「git status 干净 + Lead 授予 exclusive_paths」这条】
  · `git status` 【看不到编辑器未保存 buffer】⇒ "干净"不等于"没人在改"
  · `exclusive_paths` 在 dispatch-log 里【没有这个字段/校验】⇒ 写了也没有机检
  ⇒ 留着它就是「看起来有闸」的假保护（正是 PD-1 的形态）

【共享区要独占怎么办】⇒ 降级为【派发纪律】，不是机检条件：
  Lead 在派发时明确声明该文件归谁、其他成员不得碰（可在 dispatch-log 记 declared_owner 备查），
  但【不作为 guard 判定依据】—— guard 对共享区一律 deny。
```
### 2. 禁止命令清单（对共享工作区）
```
git checkout -- <path>          git checkout .           git checkout <ref> -- <path>
git restore（含 --source / --staged / --worktree）
git reset --hard | --merge
git clean -f*（-f / -fd / -fx …）
git stash drop | clear
git apply -R
git update-index --assume-unchanged | --skip-worktree   ← 隐藏改动，比删更隐蔽
git worktree remove --force                              ← 会丢 worktree 内未提交改动
```
⇒ 这些都会丢弃未提交改动，且未提交改动**不进 git** ⇒ 丢了就是**永久丢，无历史可回滚**。

### 3. 对照实验（pre/post、A/B 基线对比）的一律做法
```
· `git worktree add <path> <ref>` 起独立工作树，或
· 复制到 %TEMP% 的独立副本里做（不得用于提交）
```

### 4. 留证格式（"留证据"必须可复核，不能只说"备份了"）
```
· worktree 方案：记录 `git worktree list --porcelain` 输出
· 副本方案：文件列表 + 每个文件的 sha256 + 复制时间
· 落点：`artifacts/agent/verify/**`，或 dispatch-log `phase=experiment`
· 副本目录不得用于提交
```

### 5. R1 例外流程（确实需要临时回滚验证时）
```
【谁可执行】仅 **Lead** 可发起 R1 例外；成员需要 Lead 授权后才可执行，
            且必须在 dispatch-log 留痕（未留痕即视为违规）。
【记录内容】dispatch-log `phase=risk` + 完整命令 + 理由 + 执行前 sha256 快照
【事后】做差集核对，并把核对结论【写回同一条 dispatch-log 记录】；
        若丢了他人改动 ⇒ 按 R1 事故上报（不得静默重写）
```
### 6. 实例
```
2026-10-26 render-perf 为做 pre/post 对照，在共享工作区 `git checkout -- app.js` 约 90 秒，
当时 sync-mapper 正在同一文件做 task-168 ⇒ 差点丢掉未提交改动（核对后未丢，属运气非方法）。
```

### 7. 同族约束
```
本条与 L2（R1 操作 Lead 亲跑）、L5（不可逆操作先给回滚方案）同源 ——
共享工作区的未提交改动同样是【不可逆资产】。
```

### ⚠️ 强制力诚实标注（重要，不得省略）
```
`git checkout -- <file>` 【不写 reflog】⇒ 事后不可取证，git 历史抓不到。
⇒ 在工具层拦截落地前，本条【不得宣称已有机检保护】，它目前只防"无意"。
⇒ 工具层方案见 `artifacts/agent/verify/steward/PROPOSAL-workspace-destructive-guard.md`
   （v1 shell 层 deny + 审计；v2 工作区完整性哨兵，覆盖 python 子进程 / alias 等绕过）
⇒ 落地后本节应更新为"已机检保护"并注明拦截器版本。
```


## 2. 要 `team_task_create` 时

| # | 检查 | 机检 |
|---|---|---|
| 2.1 | `owner` 或 `unassigned_reason` **二选一必填**（工具已强制拒绝裸无主任务） | R3（工具级） |
| 2.2 | description 必须含「**关闭条件**」（可验证的判据，不是"做完了"） | 人工 |
| 2.3 | description 必须含「**写域**」 | `write_scope` |
| 2.4 | 若依赖其它任务 ⇒ `blocked_by` 显式声明（别靠口头顺序） | 人工 |
| 2.5 | **先证红原则**：修复类任务的关闭条件必须包含"修复前该用例失败"的证据 | 人工 |

---

## 3. 要 `complete` 收口时

| # | 检查 | 机检 |
|---|---|---|
| 3.1 | 必须有 `evidence`（workspace-relative 路径），工具强制 | R4（工具级） |
| 3.2 | **执行者自报 PASS 不算验收**：Lead 必须亲跑关键门禁，或另派未参与实现的 verifier | 人工（R1 级强制） |
| 3.3 | 判"过期/已完成"**必须同时查** ① 任务书spec'd路径 ② 仓库内**功能等价物**（防假阴性） | 人工 |
| 3.4 | 退役成员名下的任务**必须同轮收口**，否则立刻变幽灵 owner | `stall`（机检 FAIL） |
| 3.5 | 收口后重导快照（`team_snapshot`）并跑 `team_audit` | 人工 |

### 本轮实证
```
3.2: 多个 agent 报「全 PASS」⇒ Lead 复跑后才发现
     · 32 条「红」其实是探针口径错误（showFlashInfo 不经门面）
     · 基线 math/mermaid 的「复制 0/4」部分是探针缺陷
3.4: 退役 p0-selection 后 task-79/75 立刻变幽灵 owner ⇒ 机检 FAIL 2 条
```

---

## 4. 要打包 / 发版 / 改 tag / 强推时（**R1 单向门**）

### 前置（缺一不可）
```
4.1 应用必须完全退出（Memoria.exe 进程数 = 0）—— 否则 EBUSY 残壳
4.2 整目录备份当前 Package（保留回滚点），并打印可直接复制的回滚命令
4.3 预演 ≥3 种失败模式（预 mortem），每种给应对
4.4 核对远端状态：该 tag 是否已存在？若存在且指向不同 commit ⇒ 先决定（删/换号），不要盲推
4.5 版本一致性三查：__version__.py == docs/conventions/version.md §1 == Package/VERSION
```

### 执行
```
4.6 顺序严格：改版本 → 构建 → 验证(Package/VERSION + 实测启动) → commit → tag → push → Release
4.7 「实测启动」= 进程存活 + 窗口出现 + **窗口标题显示正确版本** + 无 crash.log
    （只看 exit code / success:true 不算）
4.8 Release 标题**只写** `Memoria vX.Y.Z`；正文双语（中 → --- → 英），**两段都要造价章节**
```

### 事后
```
4.9  校验双资产 state=uploaded + 大小合理（对照上一版）
4.10 校验 tag 指向发布 commit
4.11 记录到 team/dispatch-log
```

### 本轮实证（为什么 4.4 必须写进规范）
```
我原本准备「删除旧 v0.4.6 tag 并重建」，
查 GitHub API 才发现 【远端根本没有 v0.4.6】—— 本地 tag 从未推送。
⇒ 若按原计划操作，会做出一个多余且不可逆的 tag 删除。
```

---

## 5. 只能靠自觉的 3 条（其余都已下沉）

```
S1. 派发的 prompt 里，必读文档要**点名到节**（别只给路径）
S2. 回报里必须区分「实测」与「推断」，且**明确写未测项**
S3. 任何"看起来成功其实没做"的路径，修法是**让失败可见**，不是"改对就完"
```

**为什么只有这 3 条**：其余 20+ 条都已变成机检或工具拒绝 ——
**规范的价值不在于"我会读它"，而在于"我读不读都得照做"。**

---

| 5.4 | **机检工具本身必须确定性**：同输入连跑两次，除 `generatedAt` 类时间戳外**逐字节一致**。<br>非确定性的门禁 ⇒ 所有「全绿」结论不可复现 ⇒ 等于没有门禁。<br>实现：`team_audit.py --determinism`（子进程连跑两次、置空时间戳、比对字节）。 | `--determinism`（待实现，SF-014） |

## 6. 要做一个"决策"时（记录义务）

### 触发（T1–T3，任一命中即须记录）
| # | 触发 | 例子 |
|---|---|---|
| **T1 可回退但影响后续走向** | 改代码/改组织资产/改团队规范 | 「P0-b 降为 P1」「退役 3 个 v4-pro」 |
| **T2 判断类（有备选被否）** | 选方案 A 不选 B | 「拒绝复制会话改用记忆卡」「steward 不合并」 |
| **T3 不可回退（R0/R1）** | 发版/迁移数据/强推/删 tag | 「v0.4.6 发布」「删旧 tag」 |

### 检查清单

| # | 动作 | 机检 |
|---|---|---|
| 6.1 | **判定是否触发**（T1/T2/T3；都不命中 ⇒ 不记录，别给所有提交加 trailer） | `decision_trail`（task-102/103 实现） |
| 6.2 | **有提交** ⇒ 在提交信息末尾写 trailer（键名固定，改名会破坏机检）：<br>`Decision:` ≤200 字、非空<br>`Why:` ≤200 字、非空<br>`Alternatives:` ≥1 项且每项含 `rejected:`（发版/回退必填）<br>`Rule-Ref:` 可选，`path#section` 必须能解析<br>`Reversibility:` 可选，∈ {R0,R1,R2}<br>`Human-Directive:` 实现人指令时必填，须为**原文摘录** ≤120 字<br>`Decision-Id:` 可选，形状 `dec-\d{8}-[0-9a-f]{8}` | 同上 |
| 6.3 | **无提交**（纯对话决策）⇒ `python scripts/agent/decide.py append --question ... --choice ... --alternative ... --why ...` | `team/decisions.jsonl` |
| 6.4 | **R0/R1** ⇒ 7 天内找**非决策者**做一次对抗复核（`review.verdict`）；决策者自己复核无效 | 人工 + `decision_trail` |
| 6.5 | **违反的后果**：首两周 **WARN**（不阻断），之后 `team_audit::decision_trail` **FAIL**（收口必须处置） | 分阶段 |

| 6.6 | **谁写**：**决策者本人**。执行者实现 Lead 的决策 ⇒ 写**自己的** `Decision:`/`Why:`（实现层取舍），<br>并用 `Human-Directive:` 引用 Lead 指令原文；**不得替 Lead 补写 Lead 的决策**（A6）。<br>Lead 的决策若只存在于会话 ⇒ 由 Lead 本人补 D2 并标 `reconstructed:true`。<br>teammate 的提交若改变范围/取舍（T1–T3）⇒ 同样要写 trailer；**纯执行（照单实现、无取舍）可不写**。 | `decision_trail` |
| 6.7 | **时效窗口**：`append` 时距决策发生 **>600s** ⇒ 强制标 `reconstructed:true`（常量 `RECONSTRUCTED_THRESHOLD_SECONDS=600`）。<br>窗口值本身是**实现常量**不是条款 ⇒ 调整需同步改 `decide.py` 与本节说明 | `decide.py`（已实现） |

### 防"事后编理由"（6 条机器判据，来自设计稿）
```
A1 时效窗口：决策记录时间必须早于或接近决策生效时间（超窗 ⇒ 标 reconstructed）
A2 reconstructed 标记：事后补写的必须显式标，不得伪装成当时写的
A3 append-only：decisions.jsonl 只追加，永不改写（改 = 伪造）
A4 同提交绑定：trailer 必须在【决策所在那个提交】里，不能事后单独补一个提交
A5 R0/R1 对抗复核：非决策者 7 天内复核
A6 机器不创作 why：decide.py 只落盘人/Lead 写的内容，永不自作理由
```

### 本轮实证（为什么要 6.2）
```
Lead 自省曾说「P0-b 降 P1 的 43ms 理由在 commit 26fa9bc6 里」
steward 抽查该 commit 完整 message：既无 43ms 也无 P0-b
⇒ 理由连 commit 都没进，只存在于已压缩的会话
另：0.4.7 的实施提交 a68ab655(10-23 13:19) 早于台账计划(10-23 22:52)
⇒ 现在跑决策/计划类机检能自动发现，不靠人抓
```

---

## 7. 机检对应表（`team_audit.py` 15 类）

| 类 | 覆盖本文件的 |
|---|---|
| `snapshot_health` | 快照新鲜度/结构 |
| `roster` | §1.1 名册一致性、§3.4 幽灵成员 |
| `stall` | §3.4 幽灵 owner、无人认领 |
| `write_scope` | §1.2 写域重叠、§2.3 写域缺失 |
| `artifact_refs` | §3.1 证据路径存在性 |
| `role_evidence` | 角色是否真在运转（14 天三源证据） |
| `silent_failure` | L2 静默失败（S1–S6） |
| `contract_drift` | 契约声明↔现实（D1–D6） |
| `commit_hygiene` | 提交卫生（H1–H3） |
| `lessons_stale` | 教训库是否在更新 |
| **`dispatch_release`** | **§1.1 spawn↔任务、§4.5 版本三查、§4.10 tag↔commit** |
| `mode_policy` / `plan_consulted` / `role_registration` / `dead_path_edit` | §1.3b 模式路由、L8 计划先行、§2 注册同步、§3 死文件 |
| `decision_trail`（待实现） | **§6 决策记录义务（T1–T3 + 6 条防伪造判据）** |

---

## 变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-24 | 首版。来自 0.4.6 一天的实施复盘：靠记忆的规则全漏（writeScope / 远端 tag / 版本权限），靠工具强制的零漏 |

### B-danger-1 v2.1（2026-10-26，据 steward SF-056 审计 4 点）

| 项 | 修正 |
|---|---|
| ① worktree「天然独占」过强 | 改为「默认独占 + 路径唯一（成员+任务）；共用则按共享处理并显式声明」 |
| ② 删除独占条件 (a) | `git status` 看不到未保存 buffer；`exclusive_paths` 无字段/校验 ⇒ 留着是「看起来有闸」的假保护。共享区独占降级为**派发纪律**，guard 只认独立 worktree |
| ③ R1 例外未写「谁可执行」 | 写明：仅 Lead 可发起；成员需 Lead 授权 + dispatch-log 留痕；差集结论写回同一记录 |
| ④ 位置可发现性差 | 已从文件末尾移到 **§1 之后**，并在 §0 加醒目指针 |
