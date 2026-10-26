# 提案：共享工作区破坏性 git 命令的工具层拦截（草案）

> **提案人**：steward（设计草案）；**时间**：2026-10-26T19:1x+08:00；**状态**：**草案，供 Lead 批 → 派 team-plugin-creator 实现**
> **依据**：B-danger-1 v2 细化（`PROPOSAL-b-danger-1-refinement.md`）+ r7 审计结论：`git checkout -- <file>` **不写 reflog**，
> 事后不可取证 ⇒ 纯条款无强制力，必须在 DSH 工具层拦。
> **我只出方案，不实现**（DSH 插件属 team-plugin-creator 写域；`scripts/agent/**` 属 Lead/他人写域）。

## 1. 目标与非目标

**目标**：在 agent 执行 shell 的工具入口，**阻止**在共享主工作区执行"会丢弃/覆盖/隐藏未提交改动"的 git 命令；
拒绝时给出可执行的替代方案；被拒绝的命令**不执行**；所有拒绝可审计。

**非目标**：不是阻止一切 git 写操作（commit/checkout 分支/merge 等不在本条）；不替代 B-danger-1 的人的行为规范；
不追求"绝对无法绕过"（见 §5 残余风险），但要把"无意违规"和"随手绕过"挡住，且绕过留下证据。

## 2. 拦截点与判定

### 2.1 拦截点
DSH 的 shell 工具执行入口（本会话可用的是 `pwsh`/PowerShell；若 DSH 同时提供 bash 工具，**两者都要接**）。
在**命令真正执行前**做静态解析（不执行、不 eval），decision = `allow | deny`。

### 2.2 解析规则（防简单绕过）
1. 按命令分隔符拆段：`;`、`&&`、`||`、`|`、换行（PowerShell 还有 `&` 调用运算符）；
2. 去掉每段前置的 `&`、`command`、`env`、变量赋值（`FOO=bar git ...`）；
3. 识别 `git`/`git.exe`/`git.cmd`；支持 `git -C <dir> ...`（把 `<dir>` 作为"目标工作区"），也支持 `git --git-dir/--work-tree`；
4. 忽略 `--help`/`--version` 等只读子命令；其余按 §2.3 匹配；
5. 对 `git -c <key>=<value>` 解析（防 `-c alias.x='reset --hard'` 注入，见 §5）；
6. 任何解析异常 ⇒ 若段内出现 `git` 且出现危险子串 ⇒ **fail-closed deny**；否则 allow（不误伤普通命令）。

### 2.3 危险命令清单（与 B-danger-1 v2 对齐）
```
checkout      : 带 `-- <path>` 或路径为 `.` / 带 `<ref> -- <path>`
restore       : 任何形式（--source/--staged/--worktree）
reset         : --hard / --merge
clean         : -f / -fd / -fdx（含组合短参）
stash         : drop / clear
apply         : -R / --reverse
update-index  : --assume-unchanged / --skip-worktree
worktree      : remove --force
```
匹配细节：短参要拆组合（`-fd` 含 f）；长参允许 `=`（`--source=HEAD`）。

### 2.4 目标工作区判定（决定 allow/deny）
- 令 `cwd` = 工具调用工作目录；令 `main_root` = 主工作树根（`git worktree list --porcelain` 第一条，或 `git rev-parse --show-toplevel` 后判断是否主树）。
- **在 linked worktree/独立副本内** ⇒ allow（天然独占）；
- **目标是主工作树（含其子目录）** ⇒ deny；
- `git -C <path>` 指向主工作树 ⇒ deny（即使 cwd 在 worktree 里）；
- 主工作树存在但无法判定（git 失败/解析失败）⇒ 对危险命令 **fail-closed deny**（错误信息说明原因）。

### 2.5 拒绝语义（结构化、可行动）
返回错误而不是崩溃：
```jsonc
{
  "status": "denied",
  "code": "SHARED_WORKTREE_DESTRUCTIVE",
  "command": "<normalized>",
  "reason": "B-danger-1：共享主工作区禁止会丢弃未提交改动的 git 命令（checkout -- 不留 reflog，事后不可取证）",
  "alternatives": [
    "git worktree add %TEMP%/wt-<ts> HEAD  # 然后在 worktree 内做对照实验",
    "cd %TEMP%/wt-<ts> && <same git command>",
    "如确需在主工作区执行：让 Lead 记 dispatch-log phase=risk + 理由（B-danger-1 例外流程）"
  ],
  "audit_log": "dispatch-log phase=risk-denied（append-only）"
}
```
- 拒绝**必须**写一条 append-only 审计（`dispatch-log` 或插件自己的 audit jsonl）：`ts/actor/cwd/command/normalized/decision=denied/rule=B-danger-1`；
- **不提供"自我批准"flag**（模型不应能给自己开例外）；例外只能走 Lead 的显式工具/记录。

## 3. 分两期落地

### v1（优先，1 天内可完成）：shell 层 deny + 审计
- 解析 + 危险清单 + 主树判定 + deny（§2）；
- 拒绝日志；
- 单测/fixture（§4 的 1–6、9、10）。

### v2（v1 之后）：工作区完整性哨兵（覆盖 v1 的残余绕过）
每次 shell 调用**前后**采集低成本指纹：
- `git status --porcelain`（路径集合）；
- 本次运行中被标记为 dirty 的每个文件的 `sha256`（只对 dirty 文件，通常很少）。
规则：若"调用前 dirty 的文件在调用后消失/变回 HEAD，且该调用未包含 `git commit`/`git checkout <branch>`/`git stash` 等合法变更来源"
⇒ 记 `risk=workspace-drift` 到审计并 WARN（不是 FAIL：可能有合法来源如格式化工具重建文件，但**必须可复核**）。
这条覆盖 §5 的 python/subprocess/alias 绕过（它们绕得过命令解析，绕不过工作区指纹变化）。

## 4. 验收（实现者必跑的必红/必绿 fixture）
| # | 场景 | 期望 |
|---|---|---|
| 1 | 主工作区 `git checkout -- app.js` | **deny**，文件内容未被改变，审计有记录 |
| 2 | `git restore app.js` / `git clean -fd` / `git stash drop` / `git reset --hard` / `git apply -R p.patch` / `git update-index --assume-unchanged f` | 各自 **deny** |
| 3 | linked worktree 内同样命令 | **allow**（不误伤） |
| 4 | 只读：`git status` / `git diff` / `git log` / `git worktree list` | allow |
| 5 | cwd 在 worktree，但 `git -C <主树> checkout -- f` | **deny** |
| 6 | 命令链：`echo hi && git checkout -- f` | **deny** |
| 7 | `git -c alias.wipe='reset --hard' wipe`（alias 注入） | **deny**（v1 解析 `-c`）或 v2 哨兵 WARN |
| 8 | 主工作区上 python 脚本内部 `subprocess.run(['git','checkout','--','f'])` | v1 不拦（记录残余）；v2 哨兵 **WARN** |
| 9 | 解析器自身异常 | 危险命令 fail-closed deny；普通命令 allow |
| 10 | 拒绝时不得执行、不得吞错（返回结构化错误 + 审计） |  |
> 每条 fixture 都要有"命令未执行"的可验证证据（文件内容 sha 前后相同），不能只看返回码。

## 5. 残余风险（必须写进实现文档，不得宣称"绝对安全"）
1. **python/node 子进程绕过**：模型可用 `python -c "subprocess.run(['git',...])"` 绕过 shell 正则 ⇒ v1 拦不住；v2 哨兵只能事后 WARN；
2. **git alias 注入**：`git config alias.x 'reset --hard'` 后 `git x`；v1 解析 `-c` 只能拦单次注入，持久 alias 需哨兵；
3. **其他执行通道**：IDE/编辑器写文件、MCP 工具、远端脚本等不经过该 shell 入口 ⇒ 不在本拦截范围；
4. **不可判定时**：主树判定失败 ⇒ 对危险命令 fail-closed（可能误伤；需清晰错误信息 + 允许 Lead 例外流程）。
**结论**：v1+v2 是"防无意 + 让绕过留痕"，不是"物理不可绕过"；B-danger-1 的强制力说明要如实这么写。

## 6. 实现与排期建议（供 Lead 派活）
| 步骤 | 内容 | 归属 | 估计 | 依赖 |
|---|---|---|---|---|
| P0 | Lead 落 B-danger-1 v2 条款（`PROPOSAL-b-danger-1-refinement.md`） | Lead | 10 分钟 | — |
| P1 | 本方案评审 + 定稿（确认拦截点/清单/deny 语义） | Lead + team-plugin-creator | 0.5h | P0 |
| P2 | v1：shell 层 deny + 审计 + fixtures 1–6/9/10 | team-plugin-creator | 0.5–1 天 | P1 |
| P3 | v2：工作区完整性哨兵 + fixtures 7/8 | team-plugin-creator | 0.5 天 | P2 |
| P4 | 发布后观测：deny 次数、误伤（安全命令被拒=0）、绕过事件 | Lead | 持续 | P2/P3 |
| 并行 | **SF-052（L1 可机检化）**：`dispatch_log.py` `--task` 必填 + spawn 校验 | Lead 另派（scripts/agent/**） | 1–2h | 独立，可并行 |

**排期判断（我的建议，理由）**：
1. **先 P0/P1**（条款 + 方案定稿）——因为拦截语义（共享/独占、危险清单、例外流程）必须先有条款，否则实现会各自猜；
2. **再 P2（v1）**——这是当前最高风险面（已发生 near-miss：render-perf checkout 90s）；
3. **P3（哨兵）可紧跟**，因为 python 绕过是 v1 的已知缺口；
4. **SF-052 与 P2 并行**（独立、小、纯 scripts/agent；L1 曾有 2 次真实违规，越早机检越好）；
5. **两份新机检脚本**（ui_contract/test_guard）维持"观察期 + B3-e 修复 + 同批纳管"，不与本轮抢优先级。
