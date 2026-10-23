# Curator 第三轮：独立复核与组织改造（2026-10-23 22:00 起）

> 输入：`docs/agent/lead-mistake-inventory-2026-10-23.md`（Lead 自陈，主观）、
> 本轮磁盘证据（git / dispatch-log / 任务板快照 / artifacts）。
> **本文只写能复跑的**；每条附命令。**不照抄 Lead 的结论**——成立/不成立/新发现分开列。
> 角色：`curator-r3`（standard 模式；creator 模式因运行中 `app.asar` 为 10-21 构建而不可用）。

---

## 1. 复跑入口（任何人可复核本文全部结论）

```powershell
cd D:\AAA_Jupyter\Memoria
$env:PYTHONIOENCODING="utf-8"

# 团队机检（本轮扩到 9 类）+ 自测
python scripts/agent/team_audit.py
python scripts/agent/team_audit.py --selftest
python scripts/agent/team_audit.py --json | python -c "import json,sys;d=json.load(sys.stdin);print(d['summary'])"

# 派发日志（本轮加 fail-closed + 更正协议）
python scripts/agent/dispatch_log.py check
python scripts/agent/dispatch_log.py --selftest

# 本文用到的原始证据
git log --since="2026-10-23 00:00" --oneline | Measure-Object -Line          # 73
git log --since="2026-10-23 00:00" --format="%an" | Sort-Object -Unique      # 仅 Lead
Get-Content team/dispatch-log.jsonl | Measure-Object -Line                   # 本轮收口时 17（之后只增）
python -c "import json;d=json.load(open('team/team-board-snapshot.json',encoding='utf-8'));print('tasks',len(d['tasks']),'with-owner',sum(1 for t in d['tasks'] if t.get('owner')))"
```

---

## 2. Lead 清单：逐条核对

| # | Lead 的说法 | 复核结论 | 证据（复跑） |
|---|---|---|---|
| A1 | `indentListLevel` 调未定义 `findItem`，异常被 `try/catch` 吞 ⇒ Shift+Tab 静默失效 | ✅ **成立**（且**已修**） | `git show 17c20c62 --stat`；`grep -n "findItem" src/memoria/ui/static/app/js/app.js` |
| A2 | N3 给嵌套 `<ul>` 也用 `_newBlockEl()` ⇒ `-src-block` 26/22 不符 | ✅ **成立**（已修 `9bdb1211`） | `git show 9bdb1211`；该提交说明自认"修复 2eef3e34 引入的 -src-block 污染" |
| A3 | `deleteSelectionMulti` 跨块返回 false 且无提示 | ⚠️ **未核实**（本轮未读该函数体，不采信） | 需 `grep -n "deleteSelectionMulti" src/**/app.js` + 真机 |
| A4 | `openFile()` 启动期静默 resolve | ✅ **成立**（第三方证据） | `git log --oneline --grep="openFile"` → `c33c9353 fix(review/render): 修 openFile 跳转静默失败 bug` |
| A5 | dispatch-log 只在收口记、spawn 不记 | ✅ **成立，且比 Lead 说的更重** | 见 §3.1（11 次 spawn 仅 1 条记录，且该条 ts 是补记值） |
| B1 | 12 剧本 10 失败是 fixture 被覆盖，不是回归 | ✅ **成立，且污染未清干净** | `Get-ChildItem artifacts -Recurse -Filter "hw-003*" \| ? Length -eq 605` → **4 份 605B 占位副本**仍在（正常 7545B） |
| B2 | 花 1h 自己调探针，本该派活 | ✅ 成立（自陈，无磁盘反证） | `team/dispatch-log.jsonl` 该时段 0 条 spawn |
| B3 | 探针连踩 5 坑 | ✅ 成立（同类坑在 `org.md §11.3/§9.1/§9.2` 有记录，说明反复复现） | `docs/guides/agent-team-org.md` §9.1/§9.2/§11.3 |
| B4 | L5 首跑 FAIL 判"环境抖动"，重跑 PASS 就过 | ✅ **成立，且是方法论缺陷**（重跑不能作为因果证明） | 无磁盘反证；但 `org.md §12.3` 已要求 null-build 自检，说明口径矛盾 |
| B5 | `interaction.mjs` 无超时 | ⚠️ **未核实** | 需 `grep -n "timeout" scripts/benchmark/surface/interaction.mjs` |
| C1 | 覆盖快照前没读字段结构（`name` vs `target`） | ✅ 成立；**同类风险仍在**（快照仍靠手写，见 §4.3） | 快照 `members[].target` 是唯一被 `team_audit` 认的字段 |
| C2/C3 | 误判 `nodePath` / `listItemIndex` 语义 | ⚠️ 未核实（属代码语义，本轮不读实现，避免误判） | — |
| C4 | 任务书方案过细反倒限制 agent | ✅ 成立（结构性判断，与 `org.md §4` 派发规则一致） | — |
| C5 | `git checkout` 回滚了 agent 正在写的实现 | ✅ **成立，且证据比自陈更强** | `8e51e2f9`：「记录我并发 git checkout 破坏 agent 工作的事故与新纪律」；另有 `d40e5fc8` 同类（陈旧缓冲区覆盖静默回退 `17ee05d9`） |
| D1 | AGENTS.md 描述 Trae 三角色，DSH 下从未运行 | ✅ 成立（43 天） | `Test-Path artifacts/agent/events.jsonl` → False；`agents.json` 中 3 条 `retired-in-dsh` |
| D2 | `events.jsonl` 契约预留从未落盘 | ✅ 成立 | 同上 |
| D3 | `org.md §9` 写"Lead 单写"与 Curator 冲突 | ✅ 成立（已改白名单） | `org.md §9` 现为「Lead 或 Curator」 |
| D4 | `team_audit` 只解析 §2 不解析 §2.2 | ✅ 成立（已修） | 现 `roster` INFO 同时列出 §2 与 §2.2 |
| D5 | 团队单一事实源零版本历史 | ✅ 成立（已修，`team/` 入库） | `git check-ignore team/agents.json` → 无输出（未忽略）；`git ls-files artifacts/ \| wc -l` → 0 |
| E | 五条根因（无静默失败门禁/Lead 唯一审计/漂移无检测/知识不沉淀/派发粒度） | ✅ **方向成立**，但 E1/E3 已被本轮落成机检（见 §5） | `team_audit.py` 检查 7/8/9 |
| F | 四个问题 | 已答，见 §5 | — |

**小结**：Lead 清单 **没有夸大**（这是少见的自陈偏保守）。本轮 **未发现"Lead 报错了"** 的条目；
真正的补充在 §3 —— **Lead 完全没提到的 6 条**，其中 3 条比他清单里任何一条都更接近"机制缺陷"。

---

## 3. Lead 清单里**没有**的错误（本轮新发现）

### 3.1 派发日志的 `done` 记录绑不到产物，且时间戳是补记值

| 事实 | 证据 |
|---|---|
| 5 条 `done` 里 **3 条**的 `report` 指向不存在的路径（资产迁 `team/` 后未同步） | 第 7/10/12 行 `report=artifacts/agent/curator/audit-2026-10-23/*`；`Test-Path` 全部 False |
| 第 11/12 行 spawn→done 相差 **1 秒**，而其产物实际落盘晚 **13 分钟** | `dispatch-log.jsonl:11` ts=21:27:35、`:12` ts=21:27:36；`team/curator/audit-2026-10-23/` mtime=21:40:43 |
| 行序与时间不同向（1 处倒序） | 第 9 行 ts=16:20:50 排在第 8 行 ts=16:22:12 之后 |

**为什么这条最重**：它让"派发日志"从证据退化为**装饰**——查得到记录，但记录既指不到产物，
时间也不可信 ⇒ 任何"是否按时完成/是否真的做完"的统计都是假的。
**本轮处置**：`dispatch_log.py` 加 fail-closed（done 无产物拒写）+ `corrects` 更正协议；
`team_audit.py::silent_failure` S1–S6 把这三类失真变成 FAIL/WARN；3 条死链按协议追加更正。

### 3.2 「无人认领的任务」让三个检查同时空转，而机检仍报全绿

| 事实 | 证据 |
|---|---|
| 快照 12 条未完成任务：`owner` 字段 **0 条**、`writeScopes` **0 条** | `python -c "...print('with owner', sum(1 for t in tasks if t.get('owner')))"` → 0 / 0 |
| `stall` 只扫 `in_progress` ⇒ 12 条 pending 无主任务全部漏检 | 旧实现 `if not in_progress: return` |
| `write_scope` 在两两比较前不验输入，直接输出「12 条，两两写域无重叠」= **假绿** | 旧输出原文：「未完成任务 12 条，两两写域无重叠」 |

**这是全轮最像"静默失败"的一条**：检查"通过"了，但**它根本没有输入**。
**本轮处置**：`stall` 增「无人认领」WARN；`write_scope` 增输入充分性判定
（全部缺失 → 「输入不足，结论无效」；部分缺失 → 「输入不全」）。

### 3.3 「契约 vs 现实」的第三方对账**没有入口**，漂移必然发生

| 事实 | 证据 |
|---|---|
| 快照 `members` 11 名、`org.md` 称 11 名，同一时刻 `list_agents` 返回 **13 名** | 本轮 `list_agents` 输出：lead + 9 owner + todo-owner + team-curator + **curator-r3** |
| 同一角色三套名字：`agents.json`=`curator`、roster=`team-curator`、本轮 spawn=`curator-r3` | 三者并存；旧 `role_evidence` 按精确 id 匹配 ⇒ **假报「curator 是幽灵角色」** |
| 快照里的 `limit.currentMembers` 键名与检查器口径曾不一致（C1 同源风险） | 快照仍由 Lead 手写，无生成器 |

**结论**：D1/D2 能活 43 天不是偶然——**凡"人工确认项"都会漂移**。`org.md §10.2` 的"五项人工确认"
里第 1 项（名册 vs `list_agents`）就没有机检入口。
**本轮处置**：`agents.json` 增 `roster_alias`（声明即契约，`contract_drift` D4 强制）；
`role_evidence` 改按 `id ∪ roster_alias` 匹配；把"第三方无法机检"写进 contract §12 + 插件规格 R1。

### 3.4 提交说明与最终代码不符（Lead 清单无此类）

```
405f2959 fix(parser): 引用块前缀字节保真（E28 第一步…）
  ↓ 次日自我更正
2f4918aa docs(plan): 更正 405f2959 提交说明（与最终代码不符）
        "405f2959 的 message 描述的是中途版本…实际代码为最终版"
```
**影响**：后人按错误提交说明改代码会改错。**本轮处置**：`commit_hygiene` H1 把
「提交说明与代码不符 / 修复前提交引入 / 回退」纳入每轮机检清单（实仓命中 4 条）。

### 3.5 「静默回退」：一次提交把别人的已验收改动覆盖掉

```
17ee05d9 fix(lazy): 淘汰饥饿 …（已验收）
  ↓ 陈旧缓冲区覆盖
d40e5fc8 事故 —— app.js 被陈旧缓冲区覆盖静默回退了 17ee05d9；已从 HEAD 恢复
```
`org.md` 早已写「numstat 删除>插入 是强异常信号」，但**没有任何脚本实现它**。
**本轮处置**：H2（同文件同日 ≥3 次）作为"未收敛"信号；**仍缺**：真正的 `删除>插入` 拦截（见 §6 未解决项）。

### 3.6 B1 的 fixture 污染从未被机检防住，4 份 605B 占位副本仍在

`hw-003-frequency-response.md` 正常 7545B，`artifacts/` 下仍有 **4 份 605B**（`_interaction_kb_legacy-golden_39620/40952` 等）。
Lead 说 B1 已修根因（恢复 fixture），但**没有任何守卫防止再次被覆盖**：
`org.md §12.5` 自己记录 `run_interaction.py` 的 Inputs guard = ❌。
**本轮处置**：写入 §6 未解决项（需 KB sha256 守卫）；不擅自改测量脚本（禁写区）。

---

## 4. 回应 Lead 追加证据（Q3 细化）

### 4.1 "同一天同文件被改 ≥2 次且后者修前者"能否机检？——**能，已实现**

不是靠"看起来像"，而是三条可判定规则（`team_audit.py::check_commit_hygiene`，默认窗口 3 天）：

| 规则 | 判据 | 实仓命中（`--git-days=3`） |
|---|---|---|
| **H1 自修链** | subject 匹配 `修复.{0,16}引入 / 我引入 / 被我(破坏\|覆盖\|回退) / 回退了 / 提交说明.*不符 / 重大更正 / 事故：` | **4 条**：`9bdb1211`(修复 2eef3e34 引入)、`45e84be2`(重大更正)、`d40e5fc8`(事故·静默回退)、`2f4918aa`(说明与代码不符) |
| **H2 未收敛热点** | 同一 (`day`,`file`) 在 `src/**` 被改 ≥3 次 | **12 组**：`app.js @10-22 ✕37`、`app.js @10-23 ✕10`、`new-surface.js @10-21 ✕7`、`render-core.js @10-22 ✕5`… |
| **H3 不变量缺位** | `feat(` 提交改了 `src/**`，但同 commit 未触碰任何 `tests/ scripts/benchmark/ probe/ selftest` | **16 条**（例：`2eef3e34` N3 嵌套渲染 = A2 的引入点） |

**为什么这三条而不是"commit message 含 X 就标记"**：单看 message 只能抓到**已自认**的
（H1 全轮只有 4 条）；H2/H3 抓的是**没自认的**——`app.js` 一天 37 次改动本身就是"没收敛"，
而 16 个 feat 里没有不变量检查的那批，正是 A1/A2 类缺陷的温床。

### 4.2 提交前那道闸现在是什么？——**是"门禁全绿"，但它不覆盖新特性的不变量**

- 现状：`F7/F9` 门禁验的是**既有行为没退化**，不验"新特性的不变量成立"。
- 新特性不变量**目前没人定义**：`-src-block` 数量 == AST 块数这条，是事后才补的。
- **同意 Lead 的提议**（新特性必须同 commit 提交不变量检查），并给可执行判据（已写入 `org.md §13.2`）：
  1. **红过的证据**：报告必须写"我把哪行改坏 → 该检查变红"；
  2. **能指名失败模式**：检查名/注释写出它防哪个已知坏法（例「嵌套 `<ul>` 不得带 `-src-block`」）；
  3. **删特性必须变红**：临时删实现，检查 FAIL（一次即可，留报告）。
  缺任一条 ⇒ 视为"无覆盖"，该改动落入 **R2 强制独立审查**。
- 机检代理：H3 只能判"有没有附检查"，判不了"检查是否真覆盖"——**第 3 条判据必须靠人/审查方执行**，
  这是本规格里唯一无法完全机器化的部分（诚实标注）。

### 4.3 "73 提交、0 次第二方审查"要不要写进 org.md？——**要，已写**

写入 `org.md §13.0`（含复跑命令），并配套 §13.1 风险分级 R0/R1/R2（触发条件全部可机检）
+ §13.3 三条落地机制。**不写"已知风险"而是写"触发条件 + 谁必须做什么"**——
只登记风险不改变行为，登记触发条件才会。

对 Lead §E 第 2 条（"我是唯一审计者"）的**反驳一半**：本轮证据显示问题不在"只有一个人"，
而在**没有第二个人被强制要求看**。今日 73 提交里有 16 个 feat 无测试、12 组同文件同日 ≥3 次改动——
这些**不需要读代码就能筛出来**，所以缺的不是审查者，是**分诊机制**。§13.1 就是那个分诊机制。

---

## 5. 四个核心问题的答案（摘要）

| 问题 | 答案 | 落地 |
|---|---|---|
| **Q1 静默失败可机检吗？** | 能。抽象成一条：**每句"完成了"都必须绑定一个"当时已存在"的产物**（S1–S6） | `check_silent_failure`（实仓 3 FAIL → 按更正协议清零，1 WARN 保留：S5 历史倒序） |
| **Q2 契约漂移能自动暴露吗？** | 能。逐条验证"契约声明的通道在磁盘上指得到"（D1–D6：事件流路径/枚举双源/证据路径/status/id 对账/待办残留） | `check_contract_drift`（实仓 1 FAIL：id 无别名 → 已修） |
| **Q3 Lead 错误能被系统性发现吗？** | 部分能：H1/H2/H3 把"自修链/热点/无不变量"变成每轮清单；其余靠 R2 风险分级强制派审查 | `check_commit_hygiene` + `org.md §13` |
| **Q4 组织形态合理吗？** | 不合理（11 名常驻仅 2 名有证据，且 id 三套名字）。改为 **Lead + 5 领域 standby + 2 非领域 + 按需 Curator + L2 一次性子代理**；退役 4 名 | `org.md §1/§2.3`；`agents.json` `dsn_roster_actions`（Lead 执行 DSH 侧 retire） |

**Q4 三个子问题**：
1. **9 个常驻领域 Owner 是资产还是负债？** 是**潜在资产 + 当前负债**。零 token 成本（inactive 不跑），
   但「名额占用」(11/16) + 「认知误导」(文档称"在运转") + 「活性判据失真」是实付利息。
   ⇒ 退役 4 名（域已死/被脚本取代），其余 5 名 + 2 非领域改 `standby` 语义（保留能力、不再假装在跑）。
2. **org.md 该改成真实形态吗？** 该。§1 已改写为「设计意图 vs 实况」并给复跑命令。
3. **Curator 常驻还是按需？** **按需 spawn**。理由：无 cron（不能定时）＋工作天然按轮（今日 3 轮）＋
   spawn 成本 ≈ 一次窄任务。但**必须登记别名**，否则活性检查会假报（本轮实测）。

---

## 6. 仍未解决（不粉饰）

| # | 问题 | 为什么没修 | 建议 |
|---|---|---|---|
| U1 | Creator 模式不可用（运行 asar 10-21，源码 10-23） | 需重打包 + 重启桌面应用，非 Curator 可做 | 插件规格 R9；重打包后本角色改走 creator 模式 |
| U2 | 第三方对账（`list_agents`）无机检入口 | DSH 不落盘 roster | 插件规格 R1；临时替代：Lead 每轮手工存档 |
| U3 | 12 条未完成任务无 owner/writeScopes | 属任务板历史，改它＝改历史；需 Lead 重新认领 | 已加 WARN 拦住"假绿"；建议 Lead 逐条认领或关闭 |
| U4 | `commit_hygiene` H3 判不了"检查是否真覆盖新特性" | 语义判断，不可机检 | org.md §13.2 三条人工判据 + R2 审查 |
| U5 | numstat「删除>插入」拦截未实现 | 需 git hook 或 pre-commit，本轮无权限建 hook（且属 Lead 流程） | 建议加 `scripts/agent/commit_guard.py`，收口前对今日提交批量检查 |
| U6 | fixture（`hw-003` 等）无 sha256 守卫，4 份 605B 污染副本仍在 | 涉及测量脚本（`scripts/benchmark/**`），本轮禁写区 | 给 `run_interaction.py` 加 Inputs guard（`org.md §12.5` 已列 ❌） |
| U7 | dispatch-log 历史 1 处行序倒序（第 8/9 行） | append-only 不可改历史 | 永久 WARN（已知历史事实），S5 会持续报 |
| U8 | 本轮 spawn 记录 ts 由 Lead 事后补写 | spawn 时 Curator 尚未启动，无法自记 | 插件规格 R2（宿主自动记）落地后消失 |
