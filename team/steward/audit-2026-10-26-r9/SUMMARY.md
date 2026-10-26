# steward 第九轮审计（r9）—— B-danger-1 v2.1 落盘后重签

> **触发**：Lead `ff13e47a` 落 B-danger-1 v2.1（rules sha 169c15ed→**61cb2169**）⇒ r8 收据过期（`steward_self_audit` FAIL=1，设计行为）。
> **处置**：重读 5 标准 → r9 新收据（历史 r2–r8 原样不动）；复核 v2.1 对我 SF-056 四点的修复。
> **审计者**：steward；**时间**：2026-10-26T19:2x+08:00；**git base**：`ff13e47a`

## 1. 重读标准（sha256 = LF 归一化内容 sha）

| # | 标准 | sha256 |
|---|---|---|
| 1 | AGENTS.md | `6c87fe55077c4a73…`（未变） |
| 2 | **docs/guides/lead-dispatch-rules.md** | **`61cb2169d2bd540c…`（B-danger-1 v2.1，已移到 §1 之后 L98）** |
| 3 | docs/guides/agent-team-lessons.md | `f2f86b090d6e088a…`（未变） |
| 4 | scripts/agent/team_audit.py | `4874493dfac350a8…`（SF-052 已提交 `37dffc21`，字节与 r8 绑定一致） |
| 5 | scripts/agent/prompt_drift_check.py | `75a2563c40e44728…`（未变） |

## 2. v2.1 复核（SF-20261026-058：SF-056 四点已修复）

| SF-056 项 | v2.1 状态 | 复核 |
|---|---|---|
| ① worktree「天然独占」过强 | 已改「独立 worktree 默认独占 + 路径唯一（成员+任务）；共用则按共享处理并显式声明」；并注明 guard 只认这条 | ✅ |
| ② 删除独占条件 (a) | 已删；写明理由（`git status` 看不到未保存 buffer / `exclusive_paths` 无字段校验 / 留着是「看起来有闸」的假保护）；共享区独占降级为派发纪律（`declared_owner` 仅备查、不作 guard 判定） | ✅（**完全同意**） |
| ③ R1 例外谁可执行 | 已写「仅 Lead 可发起；成员需 Lead 授权 + dispatch-log 留痕；差集结论写回同一条记录」 | ✅ |
| ④ 位置 | 已从文末移到 §1 之后（L98）+ §0 醒目指针（L17）+ 变更记录 v2.1 四点表（L329） | ✅ |

**风格评估（Lead 问）**：`【为什么删掉 v2 原稿的「git status 干净 + Lead 授予 exclusive_paths」这条】` 这段**建议保留**：
- 长度适中（4 行），与仓库既有口语体（如「别靠口头顺序」）一致；
- 它防的是**后人「好心把 (a) 加回来」**——这正是最容易被重新引入的"假保护"；
- 可选微调（非必须）：标题改「为什么不做 (a)」+ 末尾加一句「若将来 dispatch-log 支持 `exclusive_paths` 且能解决未保存 buffer 问题，可在新提案中重新评估」，避免读者误以为永久封死。

## 3. 门禁结果（r9 实跑）

- `team_audit.py --json`：**FAIL=0**（WARN=56 / INFO=29）。
- `steward_self_audit`：**INFO（5/5 匹配）**。
- `deliberation_quality dq5`：**PASS**（freeze 已重签 rules=61cb2169；仅 `team_audit.py` 的 **tooling WARN**，属 R-R6 预期）。
- `--determinism`：**PASS**（sha `7897ec60…`，compared_findings=86）。
- `prompt_drift_check.py`：exit=0 / status=ok / FAIL=0 / NOT_RUN=0 / INFO=6。
- `check_ui_contract.py`：exit=0（new_fail=0；观察期计时中，未纳入标准）。
- `test_guard_check.py`：exit=0（FAIL=0 / WARN=6）。
- `freeze_refreeze.py --check`：exit=1，DRIFT=1（`team_audit.py`，tooling；SF-052 的 4874493d 尚未进 freeze）——预期，`--apply` 仍待 L12。
- pytest：**1524 passed**（Lead 基线；本轮我后台复跑同结果）。

## 4. r8 有效性确认（Lead 问）

r8 对 `team_audit.py`（4874493d，SF-052 已提交、字节未变）、`prompt_drift`（75a2563c）、`AGENTS`、`lessons` 四项仍匹配；
但 **rules 由 169c15ed→61cb2169 ⇒ 按 B3，r8 整体失效，由 r9 取代**。
（SF-052 提交字节 = r8 绑定的工作区字节，这一条已由复跑确认。）

## 5. SF-057（强制力 marker 机检）状态

Lead 已同意随**拦截器 v1** 一起落（一次 rN，避免额外重签）；`team-plugin-creator` 已转做拦截器 v1（其自述"B 交接完毕，我转 A"）。本轮不动 `team_audit.py`。

## blind_spots

1. 未审拦截器实现细节（`exclusive_paths` 字段、worktree 归属判定、shell 解析）——属 DSH 插件侧；
2. 未审 `docs/conventions/ui-contract.md` C1–C7 判据语义；
3. v2.1 条款措辞按文本核对；guard 实现层的正则/判定需其 fixtures 验证；
4. org.md §13 台账未逐条复核；产品代码/性能不在 steward 域。

## 复跑

```powershell
python scripts/agent/team_audit.py --json
python scripts/agent/team_audit.py --determinism
python scripts/agent/prompt_drift_check.py --json
python scripts/agent/freeze_refreeze.py --check
```
