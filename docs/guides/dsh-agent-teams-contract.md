# DSH Agent Teams 实操契约（增量补充）

> **定位**：这‌份文档补充 [`AGENTS.md`](../../AGENTS.md) 与 [`docs/guides/collaboration.md`](collaboration.md)，
> 专门记录在 **DSH 执行环境**下用 `spawn_teammate` / `send_message` / 共享任务板跑多 agent 协作时，
> 那一套「SOLO 主控 + 磁盘事件流」范式之外新增/不同的事实。
> **不改写** AGENTS.md 已有的角色与事件契约；冲突时以 AGENTS.md 为准，这里只补「DSH 怎么落地」。

## 0. 两条范式的边界（先说清，避免误用）

| | AGENTS.md 范式 | DSH Agent Teams 范式 |
|---|---|---|
| 角色 | SOLO 主控(Trae) + 静态三角色 builder/verifier/registrar | Lead + 动态 spawn 的 teammate |
| 交接 | 磁盘产物 + `events.jsonl` 事件流 | 共享任务板 + `send_message` + 磁盘报告 |
| 上下文 | 子 agent 独立隔离，不回灌历史 | `context: fresh`（默认）/ `fork`（继承已完成轮） |
| 触发 | 主控按事件派发 | Lead 直接 `spawn_teammate` |

**结论**：两套是「协作思想一致、执行载体不同」。AGENTS.md 的「三角色职责 + 不经对话记忆交接 + 单一事实源」
这三条铁律**在 DSH 下依然成立**，只是载体从「事件流」换成「任务板 + 磁盘报告」。

## 0.5 派发前必读「对象认知」——这是 token 效率的第一道闸（2026-10-19 新增，最高优先级）

**反面教训（删文件夹，耗 ~15M token）**：Lead 自己 grep 了 file-tree.js / document.py / sidecar.py，
又把同样几份文件塞进 subagent 的 prompt 让它**再读一遍** ⇒ 同一份知识被读两次、传两次。
而这些知识**早就在** `docs/reference/agent-guide/02-file-tree-and-nav.md` 里写到了「可据以定位实现」的粒度
（右键菜单结构、`deleteTreeFile`、确认弹窗、sidecar 镜像布局、路径安全范式），Lead 却没先读它。

**铁律（派发任何 agent 前，Lead 必须先做）**：
1. 按任务归属定位对应的对象认知：`docs/reference/agent-guide/0X-*.md`
   （01-shell / **02-file-tree-and-nav** / 03-editor / 04-preview / 05-kp / 06-links-graph /
   07-search-images / 08-import-export / 09-settings-i18n / 10-data-layout），
   以及 `docs/design/preview-render-refactor.md` 等设计稿。
2. **Lead 先读这份认知**，把它里的「现状 + 行号 + 历史决策」直接写进派发 prompt，**agent 只读增量、不重 grep 全貌**。
3. 做完改动后，**同步更新对应这份对象认知**（功能变了，认知必须跟着变）——否则认知再次漂移，下一次又得重 grep。

**这一条是 §2「索引分层」的补全**：对象认知（agent-guide）是「人可读的项目内投影」，
AOCI 是「机器索引」，两者都服务于「各看自己那份、不读全量」。派发不读对象认知 = token 浪费的直接来源。

## 1. 硬分工：Lead 负责「需扩权的原子操作」，teammate 负责「逻辑 + 复核」

**本轮实测结论（2026-10-19，最重要的一条）**：

- teammate（子进程）的 shell 写入**被 DSH 沙箱整体拦截**：`Copy-Item`、`cmd copy`、`.NET WriteAllText`、
  `python shutil`、`Start-Job`、`symlink` 全部 `Access denied`，且**与目标路径无关**（全树都拒写）。
- 只有 **Lead** 用 `pwsh` 工具 + `sandbox_permissions: "danger-full-access"` 能写受保护路径
  （`.git/`、`.aoci/`、`vendor/`、`artifacts/` 等）。

**因此分派时必须先划清**：
- 需要写 `.git/`、`.aoci/`、`vendor/`、删除残留文件的**原子操作** → 交给 Lead（一次扩权单条 `pwsh`）。
- **逻辑推理、代码复核、报告撰写**（= 读多、写少、且写到常规 `src/**` 或报告目录）→ 交给 teammate。
- 凡是要「复制二进制/大文件、删文件、git add/commit」这些**越权写**，必须由 Lead 做，不能指望 teammate。

## 2. 索引分层：agent 各看自己那份，绝不读全量

**本轮最痛的教训**：AOCI `drafts/` 膨胀到 **57MB**（30 个候选，其中 4 个各 14.5MB，内含 **43,330 个**
`benchmarks/ai_zh/kb_gold/.memoria/cache/search_aux/kp/m5_*.json` 缓存对象），导致
`cognition_check` 单次 **318 秒**、`aoci_overview` 直接超时。

根因：某次认知维护把「测试基准库的可再生缓存」当作要索引的 code 对象，全量塞进候选草稿。

**纪律**：
- 正式认知（`baseline.json` + `aoci.code.txt`）必须保持小而纯（清后 `whole_index_tokens=13,947`, `healthy`）。
- 任何 agent **只消费自己那份投影**（`aoci_search`/`aoci_get_entries` 按 scope 取），**绝不读整个 drafts 或全量索引**。
- 可再生产物（`.memoria/cache/**`、`drafts/**`、`benchmarks/**`）**永不进认知候选**；配置层已有
  `exclude-benchmarks` 规则（`.aoci/config.json`），若再次复现 43K 缓存对象，先查这条规则是否生效，而非清数据。

## 3. 一次只做一件事，disjoint 写范围

**补充（2026-10-19，2026-10-23 更新）：`spawn_teammate`（进团队）vs `subagent`（一次性）的选择边界** —— 团队名额上限 **16**（Lead 之外最多 16 个 teammate；2026-10-20 由 8 提升，见 `agent-team-profile/cordis.patch.yml`），必须按「是否需要跨轮协作」分流：

| 用 `spawn_teammate`（持久、可寻址） | 用 `subagent`（一次性、用完即弃） |
|---|---|
| 需要 send_message 多轮往返、认领共享任务、跨多个工作单元协作 | 一次性只读盘点 / 单次独立实现 / 跑完即弃 |
| 工程的「分析→施工→验证」长链，需要 Lead 中途 steer | 分片并发、disjoint 只读、产出单一报告 |
| 名额充足（< 8） | 名额满，或本就是一次性 |

**反面教训**：删文件夹那种「已摸清现状的小功能」不该派 subagent（应 Lead 直接做或 teammate）；
而「4 分片文档体检」这种一次性只读盘点是 subagent 的正确用例。**判据 = 需要不需要跨轮协作、需不需要中途 steer。**

本轮三个 agent 的成功范式：每个 agent 有**明确的 write_scopes（互不重叠）+ 单一交付物**，跑完即停。

- `render-perf` → 只写 `artifacts/agent/verify/render-perf-report.md`，只读业务代码；
- `sync-mapper` → 只写 `artifacts/agent/verify/sync-mapper-report.md`，只读业务代码；
- `render-impl` → 只写 `tex-svg.js`(新) + `index.html`，grep 复核但**不改** mapper/app/edit-handler。

**反模式**（要避免）：一个 agent 同时改多个不相关的文件、或边读边改边汇报 → 范围失控、难验收。
**一次只派一件事，做完验证、再派下一件。**

## 4. 先测量、后改动、诚实标注证据等级

两份报告高质量的原因，是它们**各自先读透源码、给出「文件:行号」级的证据**，并**把【实测】和【推断】分开标注**：

- 【实测】：引自 `docs/design/preview-render-pipeline.md` 已记录的真机读数；
- 【推断】：由复杂度外推，明确说「未做真机计时」。

**纪律**：报告里所有性能数字必须标注来源；未实测的不能冒充实测。宁可说「缺口：x 需真机补测」，
也不写一个凭空捏造的 ms 数。这正是「避免错事反复」的基础——错误认知比缺失更有害（AGENTS.md §18 同源）。

## 5. teammate 结束 ≠ 全部完成

- teammate `inactive` 只表示「这一轮 turn 结束了」，**不代表任务成功或交付物正确**。
- Lead 必须：① 读 teammate 的**磁盘交付物**（报告/patch），② 核实它声称的写范围是否真的只写了自己那份，
③ 处理 teammate 因沙箱扩权而**做不了、留给 Lead** 的收尾项（本轮的「复制 tex-svg.js」「删探针残留」就是）。

## 6. token 纪律（2026-10-19 新增，简单对话保持低消耗）

**实测大头不是"对话本身"，而是这几个隐性开销**：

1. **AGENTS.md 每编辑一次就触发一次全文重注入**（25 KB／次）。本轮曾连改 4 次 ⇒ 约 100 KB ≈ 30 K tokens 纯浪费。
   **纪律：批量攒够再一次改完，禁止边想边改同一文件的多轮 edit。**
2. **team 名额上限 16，且有 `retire_teammate`（2026-10-20 起）**：单点任务完成后当轮退役、释放名额；
   `retire_teammate` 会移除 roster 条目并释放会话，journal 历史保留。仍建议：**一次性分析任务用 `subagent`（不占名额）**；
   只有需要多轮 steer 的长任务才 `spawn_teammate`。**不再有「无 kill 工具、占位不还」的问题。**
3. **工具输出必须截断**：`pytest`/`grep`/`git diff` 一律 `| Select-Object -Last N` 或 `-First N`，禁止整段回灌。
4. **不为简单问题查全仓/跑全量测试**：能凭已有认知答的直接答；要取证再定位读。

---

**维护**：本文档只记录「被实践验证过的契约」。新增一条 = 先在一个真实任务里跑通并得到结论，再补记，
**不提前写臆想的规则**（呼应「先搜索学习、不凭空想象」）。

---

## 模型选择偏好（2026-10-22 用户指令）

**尽量不要使用 deepseek-pro 模型**，默认使用 flash（deployment default）。
- 新建 teammate / subagent 时省略 model 参数（走 mode 默认 = flash）
- 需要更强推理时优先用 mode: "deep" 而非换 pro 模型
- 既有 deepseek-v4-pro 的 teammate（如度量域）保持 idle，不主动 resume；
  新的测量任务改用新起的 flash subagent 承担

---

## 7. 派发日志（P3，2026-10-23 落地）

**每次 `spawn_teammate` / `send_message` / 收口后，Lead 必须追加一条 append-only 记录**：

```
team/dispatch-log.jsonl
```

用仓库脚本追加（自动时间戳、字段校验）：

```powershell
$env:PYTHONIOENCODING="utf-8"
# 派发
python scripts/agent/dispatch_log.py append --actor lead --target executor-x --phase spawn `
  --task task-80 --desc "mapper 嵌套支持"
# 完成/收口
python scripts/agent/dispatch_log.py append --actor executor-x --target lead --phase done `
  --task task-80 --outcome pass --report artifacts/agent/verify/xx.md
# 收口前自检（退出码 0 才可收口）
python scripts/agent/dispatch_log.py check
```

字段：`ts / actor / phase` 必需；`phase ∈ spawn|message|done|retire|backfill`；
可选 `target / task / desc / outcome / report / evidence / source`。
**禁止改写历史行**；Curator 用它判 `active`（V2/V3 证据）。

## 8. Creator 模式与 Curator（P4，2026-10-23 落地）

DSH 宿主已支持 **Creator 模式的 teammate**：

```
spawn_teammate({ name:"curator", mode:"creator", prompt:"..." })
```

- `mode:"creator"` 让子 agent 运行部署的 Creator preset（默认 `cordis`），获得
  `plugin_manager` / `tool-cordis` / 创造模式技能，可维护 DSH 插件、bundle、preset。
- Creator teammate 仍是 Team 成员：保留 `send_message` / `list_agents` / 任务板工具。
- **权限继承 Lead**：`plugin_manager` 修改 profile 需要 danger-full-access 或单次审批，
  权限不足时会失败关闭（不会静默跳过）。
- Curator 的团队资产写域见 [curator-agent-prompt.md](curator-agent-prompt.md) 与
  `agents.json` 的 `curator.write_scope`；**DSH 无路径级硬隔离**，写域是提示词 + 工具过滤 + 审计约束。

## 9. 任务板历史（Curator 判据必需）

`team_task_list` 返回**全部未删除任务**（pending / in_progress / completed），含 `status / ownerName / revision`；
`team_task_get` 可取单条最新 revision。**任务板历史 + dispatch-log + 磁盘报告** 三者合起来构成
「谁认领、谁真的干、产出在哪」的证据链；不要只看 pending。

## 10. 权限与写域边界（2026-10-23 实测）

- DSH 文件策略只有 `read-only / workspace-write / danger-full-access`，**没有子路径白名单**；
  因此「Curator 只准写团队资产」无法由沙箱强制，只能靠 preset 工具集 + 提示词 + Lead/人类复核。
- 旧版「teammate shell 写入被整体拦截」是当时沙箱环境所致；当前会话为 `danger-full-access` 时写入不受限。
  **派发前仍建议按最小权限原则给任务**（能读就别给写）。
- 删除类操作（P5 清理）**必须人类确认清单**，Agent 不得自行删除不可逆资产。

---

## 11. 派发日志的两个 fail-closed 守卫（2026-10-23 第三轮新增）

第三轮复盘发现：**「日志写了」不等于「日志有用」**。实测三类失真（都可复跑）：

| 失真 | 证据 | 后果 |
|---|---|---|
| `done` 不绑产物 | 13 条记录中，早期 `done` 只写 `desc` 不写 `report` | 「做完了」不可验证 |
| `report` 路径已失效 | 第 7/10/12 行的 `report` 仍指 `artifacts/agent/curator/...`，但资产已迁到 `team/curator/...` ⇒ 3/5 条 done 的产物指不到 | 完成声明变成死链 |
| `done.ts` 是补记值 | 第 11/12 行 spawn→done 相差 **1 秒**，而产物实际落盘晚 13 分钟 | 「是否按时完成」全部失真 |

**守卫 1：append 前 fail-closed（`dispatch_log.py`）**

```powershell
# 没有产物就必须显式说明，禁止静默留空
python scripts/agent/dispatch_log.py append --actor lead --target x --phase done --report <路径>
python scripts/agent/dispatch_log.py append --actor lead --target x --phase done `
  --no-report-reason "纯会话操作，无磁盘产物"
```
`phase=done` 缺 `--report` 且缺 `--no-report-reason` ⇒ 退出码 2，**不写入**。

**守卫 2：更正协议（append-only 下唯一合法的修法）**

历史行永不改写；路径失效/字段写错靠追加 `backfill` + `corrects`：

```powershell
python scripts/agent/dispatch_log.py append --actor lead --target lead --phase backfill `
  --corrects-line 7 --corrects-field report `
  --corrects-old artifacts/agent/curator/audit-2026-10-23/cleanup-deleted.json `
  --corrects-new team/curator/audit-2026-10-23/cleanup-deleted.json `
  --desc "team_assets 迁移后路径失效"
```
`team_audit.py::silent_failure` 会验证 `corrects.new` **真实存在**；
若更正本身也指不到东西 ⇒ 仍然 FAIL（「更正不可验证」= 二次静默失败）。

**机检投影**（收口必跑）：`python scripts/agent/team_audit.py` 的 `silent_failure`（S1–S6）。

## 12. 三方对账缺口：DSH roster 实况不可机检（2026-10-23 第三轮发现）

合同要求的对账本是**三方**：`org.md §2`（文档）↔ `team-board-snapshot.json`（快照）↔ **DSH `list_agents`（实况）**。
`team_audit.py` 的 `roster` 检查只做了前两方；**第三方没有机检入口**，因此必然漂移：

- 实测：快照 `members` 11 名、`org.md` 称 11 名，但同一时刻 `list_agents` 返回 **13 名**
  （本轮 `curator-r3` 与常驻 `team-curator` 并存），无人发现——直到人工调用 `list_agents` 比对。
- 结论：**「人工确认项」= 一定漂移的项**。凡写进 `org.md §10.2` 的人工检查，要么给出机检入口，要么降级为 WARN。

**可执行缓解（当前唯一可行）**：
1. Lead 每次收口前调一次 `list_agents`，把结果写进快照 `members`（快照即实况的存档）；
2. 快照 `exportedAt` 必须晚于最后一次 roster 变更（`snapshot_health` 已有过期 WARN）；
3. 名字分叉必须登记 `agents.json` 的 `roster_alias`（`contract_drift` D4 强制）。
**真正的修法在宿主侧**：见 [team-plugin-improvement-spec.md](team-plugin-improvement-spec.md) 需求 R1
（把 roster 导出成机器可读文件 / 或给 Curator 一个 `list_agents` 落盘工具）。

---

## 13. 打包 DSH 桌面应用 = **单向门**（2026-10-23 事故后立，血泪）

> 本节的「单向门」判定与 Pre-mortem/回滚要求，来自团队风险协议
> （`risk-management.md` §2/§4/§5/§6）。**打包产物属于典型单向门**：
> 「改打包产物 / 版本号 ⇒ 发布语义变化，产物已流出就无法收回」。

### 13.1 为什么它是单向门（不是例行命令）
`electron-builder` 的 `appOutDir` **就是用户日常启动的那棵树**：
它**先清空 `win-unpacked`，再复制**。
只要有一个文件被占用，它就**删到一半中断**，留下一具缺 `icudtl.dat` / `locales/` 的残壳
——**表现是「双击毫无反应、无任何报错」**，比崩溃更难查。

**已实际发生（2026-10-23）**：
```
⨯ EBUSY: resource busy or locked, unlink '...esourcespp.asar'
```
原因：DSH 桌面应用正在运行（我们的会话就跑在它上面），Windows 锁住了 `app.asar`。

### 13.2 三条硬教训（用户提供 + 实测确认）
| # | 教训 | 判据 / 应对 |
|---|---|---|
| L1 | **打包前必须彻底退出 app** | 任务管理器里 0 个 `DeepSeek Harness` 进程；打包后校验 `icudtl.dat` / `locales/` / `resources/app.asar` 齐全 |
| L2 | **本机打包需避开沙箱** | `prepare:dsh` 的冒烟测试要建 junction，沙箱内报 `EPERM` ⇒ 用普通终端或无沙箱执行 |
| L3 | **改完一定实测启动，不要只看 `success: true`** | 退出码 0 证明不了应用能启动。必须真的启动一次、看到窗口 |

### 13.3 唯一可复用的执行入口
`D:\deepseek-harness\finish-rebuild.ps1`（253 行，**纯 ASCII**）已实现完整协议：

```
Preflight 1  应用进程数为 0（否则拒跑并解释残壳风险）
Preflight 2  无 electron / electron-builder 残留进程
Preflight 3  把当前 win-unpacked 整目录备份为 win-unpacked.bak-<ts>
             → 打印可直接复制的回滚命令
Step 3/3     pnpm run package:desktop:win:x64:unsigned
Postflight  ① asar 时间戳必须更新
             ② 与 Electron 发行包逐文件对比（不硬编码清单 ——
                Electron 44 已不再发行 libEGL.dll/libGLESv2.dll，
                硬编码会误报"缺失"）
             ③ locales/ 的 .pak 数量 ≥10
             ④ 扫 asar 内特征串（如 creatorPreset）确认新代码真的进包
失败时       打印回滚命令，明确提示"壳可能已半删"
```

**为什么要"与 Electron 发行包对比"而不是硬编码清单**：
我第一次检查时按硬编码清单，误报 4 项缺失（`app.asar`、`elevate.exe`、`libEGL.dll`、`libGLESv2.dll`），
实际全部正常 —— 前两个本就不该在那些位置，后两个 Electron 44 源里就没有。
**正确校验方式 = 与源发行包做集合差**。

### 13.4 残留缺口
- 备份是**整目录复制**（~1.4GB），磁盘占用大；尚未做「保留最近 N 份 + 自动清理」。
- 尚未自动化**真正启动应用并检测窗口出现**（L3 仍需人工确认）。
- 未覆盖 macOS / Linux 打包路径。
