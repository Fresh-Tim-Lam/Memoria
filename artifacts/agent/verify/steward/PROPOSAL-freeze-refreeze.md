# 提案：freeze 机制补 `--refreeze`（可审计的冻结标准更新）

> **提案人**：steward；**时间**：2026-10-26T09:2x+08:00；**状态**：**提案（未实现，不改 `team_audit.py`）**
> **来源**：Lead 在 task-110 收口时记录的 design gap：
> 「freeze 机制没有 `--refreeze` 命令，只能人工更新 ⇒ 建议后续补」。
> 按 **L10**：现行条款未规定 refreeze 流程 ⇒ 先出方案，批准后再落条款/实现。

## 1. 现状与真实风险（不是"为了优雅"）

当前 `artifacts/agent/verify/debate/freeze-v2.json` 是**人工维护**的冻结物：
- 标准变更时 Lead 手工改 `standards[].sha256_lf`，并**追加** `standards_updated[]` 记录（本次 `ce9add0d` 做得对：
  含 `at/by/reason/commit/changed from→to/rule_ref/note`）；
- 风险面：
  1. **漏更新** ⇒ dq5 红（可见，可接受）；但**漏记 `changed`/`reason`** 时 dq5 只能看到"sha 不匹配"，
     审计链断在"为什么变"（本次人工记录质量靠人）；
  2. **手改错**：改错一个字符的 sha、或改错 `standards_frozen_at`、或删掉历史条目——没有机制阻止；
  3. **无 dry-run/一致性检查**：不知道"哪些标准会变"，只能跑 dq5 事后发现；
  4. **与 steward 重签（B3）没有联动**：refreeze 后 `STEWARD_STANDARDS` 若含该标准，收据立即过期，
     需要人工记得跑 rN；机制上无提示；
  5. **baseline_mutation 语义只写在 F1 文字里**：refreeze 是否算"重开受影响 Phase"没有机器记录。

## 2. 提案设计（独立脚本，不塞进 `team_audit.py`）

**落点**：`scripts/agent/freeze_refreeze.py`（独立脚本；**不**做 `team_audit.py` 子命令，
避免"改 refreeze 实现 ⇒ team_audit.py sha 变 ⇒ steward 收据过期 ⇒ 再重签"的自指循环）。

### 2.1 命令面
```text
freeze_refreeze.py --check [--freeze PATH]
    # 只读：按 content_sha256（LF 归一化，与 dq5 同口径）比较 standards 与磁盘
    # 输出 MATCH/MISMATCH + changed[]；exit 0=全匹配，1=有漂移，2=用法错误

freeze_refreeze.py --apply --reason "..." --rule-ref "..." \
    [--commit <sha>] [--by <member>] [--declare-no-reopen | --reopen <phase,...>] \
    [--allow-no-change] [--freeze PATH]
    # 只在 --check 有漂移时写；append-only 追加 standards_updated[]
    # 写入前：校验 reason 非空（≥10 字）、rule-ref 可解析、commit 存在（若给）
    # 决策标准变更时：必须显式 --declare-no-reopen 或 --reopen（记录 F1 baseline_mutation）
    # 原子写：临时文件 + os.replace；同时把旧 freeze 复制到
    #   artifacts/agent/verify/debate/freeze-history/freeze-v2.<UTC时间戳>.json
    # 输出下一步提示：需要 steward 重签（若 STEWARD_STANDARDS 含变更项）
```

### 2.2 记录格式（append-only）
```jsonc
"standards_updated": [{
  "at": "...", "by": "lead",
  "reason": "task-110 收据 sha 改 LF 归一化 + SF-031 扩 5 项（≥10 字）",
  "rule_ref": "docs/guides/agent-team-org.md §2.6 B3",
  "commit": "ce9add0d",
  "changed": [{"path": "...", "from": "<old lf sha>", "to": "<new lf sha>"}],
  "baseline_mutation": {"reopen": [], "declared_by": "lead", "why_not_reopen": "..."},
  "tool": "freeze_refreeze.py@<version>"
}]
```
- **不删除/不改写历史条目**；`standards_frozen_at` 更新为本次 `at`；
- `--check` 与 dq5 **必须共用同一实现**（`content_sha256`），否则会出现"refreeze 说匹配、dq5 说漂移"的新假象。

### 2.3 拒绝条件（fail-closed）
1. `reason` 为空或 <10 字（同 `--resign` 的 note 口径）；
2. `rule_ref` 不可解析（复用 `team_audit._validate_rule_ref` 或同规则）；
3. `--commit` 给了但 `git cat-file -e <sha>^{commit}` 失败；
4. freeze schema 不认识 / standards 项缺 `path|sha256_lf`；
5. 无漂移且未给 `--allow-no-change`（防"无变更也刷记录"）；
6. 决策标准变更但既无 `--declare-no-reopen` 也无 `--reopen`（F1 的 baseline_mutation 必须有明确结论）。

## 3. 验收（实现时）
- **负例（每条必红）**：sha 漂移未声明→拒绝；reason 空→拒绝；rule_ref 坏→拒绝；无漂移重复 apply→拒绝；决策标准变更未声明 reopen→拒绝；
- **正例**：漂移时 apply 成功、`changed` 精确 from→to、历史保留、原子写（中途 kill 不产生半文件）、`--check` 幂等；
- **一致性**：`--check` 的 MATCH/MISMATCH 结果与 `team_audit.py --json` 的 dq5 判定**逐项一致**（同一 content_sha256）；
- **联动**：refreeze 后打印"steward 需重签 rN"提示；不自动改任何收据（B3 要求真重读）。

## 4. 建议的条款（先批条款再实现）
```
L12（冻结物更新）：
冻结标准变更必须走 refreeze（append-only 记录 reason/rule_ref/commit/changed + baseline_mutation 结论）；
禁止直接手改 freeze 的 sha 字段（手改即为 A3 违规）；refreeze 后受影响审计收据必须重读重签（B3）。
```
（落点：`docs/guides/agent-team-org.md §2.6` 或 `lead-dispatch-rules §6`，由 Lead 定。）

## 5. 优先级与范围
- **P2**：当前人工流程"能工作但依赖人"；风险是审计链质量而非立即错误；
- **最小可用版**：先只做 `--check`（只读、零风险、立刻能发现"哪些标准会漂移"）；`--apply` 待条款批准后做；
- **写域**：`scripts/agent/**`（团队工具域，非 steward）；实现者需 Lead 指派并遵守 L1 建任务。

## 6. 不做什么
- 不做"自动 refreeze = 改 sha 让 dq5 绿"（那等于自动改收据，违反 B3/A3）；
- 不把 refreeze 做成 `team_audit.py` 子命令（自指循环：改实现→收据过期→重签，见 §2 落点）；
- 不自动重开 Phase（reopen 必须由人显式声明并记录理由）。
