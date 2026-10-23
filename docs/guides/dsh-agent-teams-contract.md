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
artifacts/agent/dispatch-log.jsonl
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
