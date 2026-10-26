# 提案：B-danger-1 条款细化（可直接替换/并入 `lead-dispatch-rules.md`）

> **提案人**：steward；**时间**：2026-10-26T19:0x+08:00；**状态**：提案（供 Lead 落盘，我不改 `docs/**`）
> **依据**：Lead 认可 r7 审计的 5 条问题（SF-20261026-048），并给出 ③④⑤ 判定输入。
> **用法**：Lead 可直接把 §2 文本替换现有 `## B-danger-1 ...` 整节，并更新 §变更记录；或按 §4 的 diff 说明人工改。

## 1. 为什么细化（一句话）
原条款只有两条命令、无"共享/独占"定义、无留证格式、无强制力声明 ⇒ 读者无法判定边界，工具无法据此拦截，
且**只能靠自觉**（`checkout -- <file>` 不写 reflog，事后不可取证）。细化后它同时是"人的行为规范"和"工具拦截的语义输入"。

## 2. 建议条款正文（替换现 B-danger-1 整节）

```markdown
## B-danger-1 禁止对共享工作区做破坏性回滚（2026-10-26，v2 细化 2026-10-26）

### 适用范围（"共享工作区"的定义）
默认状态 = **共享**：本仓主工作树的 working tree（`git worktree list --porcelain` 中首个/主工作树），
任何成员都可能正在编辑任何文件。
**独占仅两种情形**：
  (a) 目标文件当前无任何未提交改动（`git status --porcelain -- <path>` 为空）**且** Lead 在派发时显式授予
      （`dispatch-log` 记 `phase=spawn` 的 `exclusive_paths`；无记录 = 未授予）；
  (b) 在独立 `git worktree` 中（`git worktree list --porcelain` 可见、且不是主工作树）。
除上述两种，一律按共享处理；**"看起来没人改"不构成豁免**。

### 禁止命令（在主工作区）
以下命令会丢弃、覆盖或隐藏他人未提交改动，主工作区内一律禁止：
  · `git checkout -- <path>` / `git checkout <ref> -- <path>` / `git checkout .`
  · `git restore <path>` / `git restore .`（含 `--source/--staged/--worktree`）
  · `git reset --hard [<commit>]` / `git reset --merge`
  · `git clean -f` / `-fd` / `-fdx`
  · `git stash drop` / `git stash clear`
  · `git apply -R <patch>`
  · `git update-index --assume-unchanged` / `--skip-worktree`（隐藏改动，同样危险）
  · `git worktree remove --force <path>`
判据：**只要会丢弃/覆盖/隐藏未提交改动，就在禁止范围内**；上表是清单不是穷举，
实现层（工具拦截）按命令模式匹配，条款层写"等同类命令"。

### 对照实验（pre/post、A/B 基线）
一律在**独立 worktree** 或 **%TEMP% 独立副本**里做；禁止在主工作区做。
同一时间同一文件只能有一个实验执行者。

### 留证格式（可核验，不依赖 %TEMP% 存活）
· worktree 方案：记录 `git worktree list --porcelain` 输出 + worktree 路径 + 基准 ref；
· 副本方案：记录文件列表 + 每个文件的 `sha256` + 复制时间；
以上记录写入 `artifacts/agent/verify/**` 或 `dispatch-log`（`phase=experiment`，含 `worktree`/`copydir` 字段）。
副本目录不得用于提交。

### 例外与升级（R1）
确需在主工作区执行禁止命令（例如修复已被破坏的工作区）必须：
  ① Lead 在 `dispatch-log` 记 `phase=risk` + 完整命令 + 理由；
  ② 执行前对受影响文件做 sha256 快照留证；
  ③ 执行后核对 `git status` 与快照差集：丢改动立即按 R1 事故上报（L2/L5）。
无上述记录 = 违例。

### 强制力说明（诚实标注，L10）
本条**无法仅靠 git 历史取证**：`git checkout -- <file>` 不写 reflog（只有 `reset --hard` 会留记录）。
因此本条的可执行性来自：
  1. **DSH shell 工具层拦截**（见 `PROPOSAL-workspace-destructive-guard.md`）；
  2. `dispatch-log` 的实验/风险记录 + 审计；
在工具拦截落地前，本条属于【靠自觉的行为规范】，不得宣称已被机检保护。
```

## 3. 放置与变更记录
- 位置：从当前"变更记录之后"移到 **§1 派发主流程之后、§2 建任务之前**（或新增 `## 7.5 共享工作区安全` 并在 §0 清单加一行指针）；
  理由：这是派发/执行期约束，放在 changelog 后等于藏起来。
- §变更记录加一行：
  `| 2026-10-26 | B-danger-1 v2：命令清单补齐（restore/clean/stash drop/apply -R/update-index/worktree remove）+ 共享/独占定义 + 留证格式 + 强制力标注 |`

## 4. 与现行条款的关系（不重复、不冲突）
- **L2**（R1 操作 Lead 亲跑）：本条把"R1"具体化到"共享工作区的未提交改动"；
- **L5**（不可逆操作先给回滚方案）：本条对"共享工作区"更严（直接禁止，而非给方案）；
- **L6**（让失败可见）：本条的强制力说明明确"未落地机检前不得吹绿"，是对 L6 的遵守而非例外。

## 5. 验收（Lead 落盘后）
1. `docs/guides/lead-dispatch-rules.md` 的 sha 变化 ⇒ 按 B3 通知 steward 重签（r8）；
2. 若同时落"工具拦截"条款，需在同一轮把 `STEWARD_STANDARDS`/冻结收据的处理写清（B3-c/B3-e 相关）。
