# GitHub 宣传体系重写报告（task-182）

> **执行者**：prompt-owner（delegated）｜**时间**：2026-10-26｜**状态**：完成（未 commit）
> **任务**：README 双语重写 + 仓库描述/topics + tag/Release 规范 + **断言—证据表**
> **写域**：`README.md` / `README.cn.md` / `docs/marketing/**` / `artifacts/agent/verify/marketing/**`（未改代码、未改 `Package/**`、未动 `__version__.py` 与 `version.md`）

---

## 0. 交付物

| # | 交付物 | 路径 | 规模 |
|---|---|---|---|
| 1 | 英文 README（重写） | `README.md` | 286 行 / 15.4 KB |
| 2 | 中文 README（重写，与英文镜像） | `README.cn.md` | 255 行 / 8.5 KB |
| 3 | **断言—证据表（最重要）** | `docs/marketing/claims.md` | 139 行 / 35 条断言 |
| 4 | 仓库描述 / topics / 社交预览 / 截图脚本 | `docs/marketing/repo-metadata.md` | 143 行 |
| 5 | tag 与 Release 机制清单 | `docs/marketing/tag-release-spec.md` | 159 行 |
| 6 | 机检脚本（可复跑） | `artifacts/agent/verify/marketing/check_claims.py` | 60 项检查 |
| 7 | 证据产物 | `artifacts/agent/verify/marketing/evidence/*.txt` | 8 个文件 |

---

## 1. 关键事实处理：「图谱赋能 agent」按 design-intent 写（Lead 已裁定）

**写法（已落地，英文/中文）**：
- `README.md` 章节 *"The graph is an index, not decoration"*；
- `README.cn.md` 章节 *"图谱是索引，不是装饰"*。

**证据链（claims.md CLM-10 / CLM-16）**：
- `docs/design/kg-ontology-v0.md:13`「agent 侧从不读边」、`:20`「检索/选节/读取/写作/复习路径完全不读边」、
  `:27-28`「边服务的是人看的图 + 写质量诊断，不是 agent 推理；任何为 agent 加边能力的设计，必须先证明它能改变一个 agent 决策」；
- `docs/design/kg-visualization-v0.md`：FROZEN + 两轮人裁决（节点大小 75%–165%；连续、不设档位）+ 3D 不用大小编码；
- 这两份文档本身证明"这是有意为之的设计，不是事后编的故事"。

**实际写法**：README 明确写 **design intent**，并紧跟一句「图谱目前**尚不**参与 agent 检索」；
Roadmap 章节写「让图谱拓扑参与 agent 检索 —— 但必须先在 A/B 证明它能改变 agent 决策」。
**没有**出现「图谱赋能 agent 检索」「提高 agent 交互效率」等已实现式表述（机检 FORBIDDEN 列表覆盖）。

---

## 2. README 文件命名：保留 `README.cn.md`（未创建 `README.zh-CN.md`）

任务书写的是 `README.zh-CN.md`，但仓库的**生效规范**是 `README.md`（英文）+ `README.cn.md`（中文）：
- `docs/conventions/readme-i18n.md:13`：「仓库根只维护 `README.md`（英文）与 `README.cn.md`（中文），**不维护第三份**（如 `README.en.md`）」；
- 现有引用点（改名会产生坏链）：`README.md:7,13`、`benchmarks/README.md:1`、`config/README.md:1`、`docs/README.md:1`、`docs/conventions/README.md:25`。

⇒ 按本任务"重写双语 README"的**意图**执行（`README.md` 英文在前、`README.cn.md` 中文镜像），
**不新增第三份**，避免与 readme-i18n 规范冲突。若 Lead 决定统一改名，需要同批改 6 处引用 + readme-i18n 规范，不在本任务写域。

---

## 3. claims.md：35 条断言 × 四档状态

**状态词表**：`implemented` / `bounded`（已交付但有条件，必须写条件）/ `design-intent`（只进设计理念语境）/ `roadmap`（只进 Roadmap）。
另设 **§9 禁止词条**（出现即返工）：图谱赋能 agent 检索、掌握程度评分、防篡改/安全/已签名、最快、零网络/完全离线、
"AI 无痕自动改"、移动端/跨平台已支持等。

**README 能力性断言 → claims 覆盖映射**（抽查）：

| README 位置 | 断言 | CLM |
|---|---|---|
| 顶部一句话 | 知识点级链接 / 精确片段范围 | CLM-02 |
| Why 表 | 纯文件 + sidecar、普通文件夹 | CLM-01 |
| Why 表 / Design philosophy | 图谱按索引设计（design intent） | CLM-10 / CLM-11 / CLM-12 |
| Why 表 | 内置 FSRS 复习（due/grade/状态） | CLM-20 / CLM-21 / CLM-23 |
| Features › AI | 读工具面（read_document/kb_overview/三级粒度…） | CLM-30 |
| Features › AI | 单一写路径 + 备份 + 撤销 + 三档审批 | CLM-14 / CLM-31 / CLM-31b / CLM-32 |
| Features › AI | MCP 4 工具（544 tok） | CLM-33 |
| Features › 渲染 | LaTeX / Mermaid / 荧光笔 / 图片 | CLM-40 |
| Measured performance | 5000 节点 9108→41.5ms；冷启动 15.4→2.4s | CLM-41 / CLM-42（带版本与口径） |
| Data & privacy | 无账号/云同步/上传遥测；出网开关；更新检查；非数字签名 | CLM-50 / CLM-51 / CLM-52 / CLM-53 |
| Tech stack | 1,600+ tests | CLM-60（**不写精确数**，见 §7.4） |
| 对比表 / 不适合谁 | 与 Obsidian 的取舍（不贬低） | CLM-70（editorial） |

「掌握程度评分 / mastery」**未实现**（`git grep "掌握\|mastery" src` = 0 命中）⇒ claims 标 **roadmap**（CLM-22），
README 只写「每卡保留调度状态 stability/difficulty/due」，没有写"掌握程度可视化"。

---

## 4. 「先证红」：抽 3 条断言实际验证（不止跑脚本，逐条给命令与输出）

### 4.1 CLM-14/31「默认审批档 = auto-approval，删除类才问」——**实测**
```powershell
python -c "from memoria.services.agent import permission_presets as pp; print(pp.DEFAULT_PRESET); [print(n, s.approval) for n,s in pp.PRESETS.items()]"
```
输出（`evidence/claim_approval_default.txt`）：
```
DEFAULT_PRESET = auto-approval
manual-approval: approval='ask'       desc=每次写入都等你确认后才落盘。
auto-approval:  approval='auto'       desc=常规写入自动放行；含删除类改动时仍会问你一次。
all-access:     approval='allow-all'  desc=任何工具调用都不再询问（仍写前备份、可整批撤销）。
RISKY_OPS: delete_file / rename_file / move_file / delete_kp / rename_kp
```
⇒ **发现并修正了一个真实脱节**：初稿 README 写「you approve each item / 逐条确认」，
但默认档是**自动审批**（2026-09-21 人拍板"全线放开写机制"，安全兜底是写前备份 + 可撤销）。
已改 README/claims/repo-metadata 为「分档 + 备份 + 撤销 + 审计」，并写清"要逐条确认请切 manual-approval"。
**这正是本任务要防的"宣称≠事实"**。

### 4.2 CLM-20「内置 FSRS 调度（due/init/grade）」——**实测**
```powershell
python resources/agent-prompts/fsrs.py --help
```
输出（`evidence/claim_fsrs.txt`）：`subcommands=['due','init','grade']`、`compute_next_state=True`、
`usage: fsrs.py ... {due,init,grade}`、`Memoria FSRS-5 确定性间隔重复调度（标准库实现，无第三方依赖、不联网）`。

### 4.3 CLM-41/42「5000 节点 9108→41.5ms；冷启动 15.4→2.4s」——**实测有据**
`docs/design/graph-benchmark.md` 含基线 `9108.5 ms` 与结果 `41.5 ms`；
原始产物 `scripts/benchmark/graph/results/render-*.md` 存在（3 个不同阶段）；
`docs/conventions/version.md` 0.4.6 行含 `15.4s → 2.4s（−84%）`。
输出（`evidence/claim_benchmark.txt`）。README 已标注「**measured at v0.3.4 / v0.4.6；本轮未复跑；复现见 docs/...**」，
不写成"当前版本更快"。

### 4.4 附加抽查（诚实边界）——CLM-51/52 隐私与联网
`evidence/claim_privacy.txt`：`is_enabled() 缺省 = True`（出网开关默认开）、`update.py` 含"零请求"与"数字签名"（明确不做）、
`graph_telemetry.py` 声明"不上传"、`src/**` 无 `login/sign in/account` 命中。
⇒ README 写的是「无账号/无云同步/无上传遥测；**只有你启用/配置的功能才联网**；出网关闭 ⇒ 零请求；可关自动检查」，
**没有**写"零网络/完全离线"。发布包只写「结构与完整性校验，**不是数字签名**」，未出现"防篡改/安全/已签名"。

### 4.5 素材与版本（防"第一条就点坏"）
`evidence/screenshots.txt`：`resources/screenshots` 8 张 `demo-*.png` 全部存在，两份 README 各引用 8 张且集合相等；
`evidence/version.txt`：`__version__.py = 0.4.9`，两份 README badge 一致。

---

## 5. 双语与 readme-i18n 自查

- 两份 README 节结构镜像：Why / Design philosophy / Features / Quick start / Trade-offs / Who it's **not** for /
  Screenshots / Measured performance / Data & privacy / Docs / Tech stack / Roadmap / License；
- 语言切换 badge 互指（英文→`README.cn.md`，中文→`README.md`）；
- 截图路径前缀统一 `resources/screenshots/`（8 张，两版一致，无坏链）；
- 版本 badge/「当前版本」两版一致（0.4.9）；
- 「不适合谁」两版都写（敢写"不适合"是本任务明确要求）。

---

## 6. tag / Release 清单（`docs/marketing/tag-release-spec.md`）

与 `docs/conventions/version.md §6` + `release-copy.md` 对齐，**不新增规则**：
- **0a/0b/0c 三步机检**（`release_preflight.py --phase pre/post/--verify-published`，exit 1 不得继续；SKIP 不算通过）；
- **标题严格等于** `Memoria vX.Y.Z`（`TITLE-EXACT`；副标题只进 body）；
- **正文双语，English 在前、中文在后，两段均 >200 字符**（stub 判不合格）；代码/文件名/file:line 不翻译；
- **造价段**：英文 `## Cost (Agent compute)`、中文 `## 造价（Agent 算力）`（全角括号），含量级 + 统计口径 + 成本结构；
- **资产 canonical**：`Memoria-vX.Y.Z-win64.zip` + `Memoria-vX.Y.Z-win64-lite.zip`（历史教训：v0.4.7/v0.4.8 缺 `win64-` 段；已发布不改名）；
- **完整性边界**：只做 manifest 结构与完整性校验，**不做数字签名**；
- 发布后核对清单（8 条）+ 与 claims 的一致性要求（Release 里的能力断言同样受 claims 约束）。

---

## 7. 仓库元数据（`docs/marketing/repo-metadata.md`）

| 项 | 交付 |
|---|---|
| 英文 description | 336 字符（≤350；机检 `check_claims.py` 实测） |
| 中文 description | 137 字符（≤350） |
| topics | 15 个（10–20 区间）：local-first / markdown / knowledge-base / knowledge-graph / note-taking / spaced-repetition / fsrs / ai-agent / llm / mcp / python / desktop-app / windows / pkm / second-brain |
| 社交预览 | 1280×640 方案：真实工作区截图 + `The graph is an index, not decoration.` + 四个 implemented 能力点；禁止在预览图放性能数字 |
| 截图/GIF | 8 张现有截图登记 + 5 条 GIF 脚本（snippet-range 跳转 / 2D-3D / 复习 / 出网开关 / 审批写+撤销），全部用仓库示例库（`docs/example/showcase`、`AAA_Vocab`），不造假数据 |

---

## 8. 机检结果

```
python artifacts/agent/verify/marketing/check_claims.py --full
  exit=0
  汇总：PASS=60 FAIL=0 合计 60 项
  结论：可机检断言全部有证据；禁止词条未出现
```
覆盖：版本一致性 / description 长度与 topics / 截图存在与引用 / claims 覆盖与禁止词条 / 图谱 design-intent 与
禁止式表述 / benchmark 数字与原始产物 / agent 工具面 / 默认审批档 / FSRS / 隐私与出网 / 相对链接无坏链 / 双语互链 / pytest。

`pytest -q tests`（point-in-time，2026-10-26）= **1624 passed**（`evidence/pytest.txt`）。
README 写 **1,600+** 而不是精确数：精确数每次提交都会漂，固定数字会变成新的"宣称≠事实"。
**本轮未改代码**（`git status` 只有 `README.md` / `README.cn.md` / 新增 `docs/marketing/`）。

---

## 9. 残余与建议（如实）

1. **索引登记**：`docs/marketing/**` 是新增目录，按 `docs/conventions/docs-management.md` 应登记进 `docs/README.md`
   与对应目录 README —— 不在本任务写域（登记属 registrar/todo-owner），**建议 Lead 派登记**。
2. **截图登记**：本轮**未新增/替换截图**，故 `resources/README.md` 与 `docs-management.md` 的截图登记无需改；
   若后续按 repo-metadata §4.3 拍 GIF，需按 readme-i18n §3 登记。
3. **社交预览图未生成**：只有尺寸/构图/文案方案（需设计产出图），未造假图。
4. **manual 项**：claims 里"对比是否克制""设计理念表述是否准确"等属人工判断，机检只能防禁止词条；
   建议下次改 README 时由非作者复核一次（对照 claims §8）。
5. **Obsidian 许可行已从 README 对比表删除**：竞品许可/定价会变，公开文案只写自身 MIT（claims CLM-71 已改）。
6. **测试精确数**：若 Lead 坚持要精确数字 badge，需要每次发版同步 README，否则会漂；当前选择"1,600+"。
7. **未 commit**：等 Lead 审核后统一提交。
