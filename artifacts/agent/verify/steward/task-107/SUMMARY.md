# task-107 交付报告：`dispatch_log.py` 记录 spawn 的 mode / modeExplicit

> **执行者**：steward2（flash）；**日期**：2026-10-24；**任务**：task-107（rev 2）
> **依据**：`AGENTS.md §0.5 L9`、`docs/guides/lead-dispatch-rules.md §1.3b`、task-100 遗留（mode_policy 无法判定）
> **写域**：`scripts/agent/dispatch_log.py`、`artifacts/agent/verify/**`（Lead 已授权扩展）；**未改** `team_audit.py`（消费端只读联调）

---

## 0. 结论

派发日志现在**记录并可校验 spawn 的模式决策**；`phase=spawn` **fail-closed**：

| 场景 | CLI | 结果 |
|---|---|---|
| spawn 不带 mode | `append --phase spawn` | **exit 2，拒绝写入**（不落盘）|
| spawn 带显式模式 | `--mode mechanical` | exit 0，行含 `mode:"mechanical"` + `modeExplicit:true` |
| 显式「未决定」留痕 | `--mode-explicit false` | exit 0，行含 `modeExplicit:false`（**不伪造 mode**）|
| 自相矛盾 | `--mode standard --mode-explicit false` | exit 2，拒绝 |
| 历史 spawn 行（append-only） | 无 | `check` 只报 **WARN**（不阻断），并给 `mode_coverage{spawn,judgeable,unknown}` |

`dispatch_log.py --selftest` PASS（红 9 类，其中新增 2 类：spawn 无 mode 被拒、mode 自相矛盾被拒；绿含带 mode 落盘/显式未决定）。

---

## 1. 实现要点

1. **`append` 参数**：`--mode {mechanical,standard,deep,creator}`、`--mode-explicit {true,false}`（默认不写）。
2. **`build_entry`**：`--mode` 存在 ⇒ 写 `mode`，且 spawn 时默认 `modeExplicit:true`；`--mode-explicit` 显式写布尔。
3. **`validate_entry`（写前 fail-closed）**：
   - spawn 且 (`mode` 缺失 且 `modeExplicit` 不是 `false`) ⇒ 拒绝，提示 L9「不传 mode 会被静默默认为 standard = 没做决策」，并给出 `--mode-explicit false` 留痕路径；
   - `mode` 与 `modeExplicit:false` 同用 ⇒ 拒绝（自相矛盾）；
   - `mode` 不在四档 ⇒ 拒绝；
   - 非 spawn 的 phase：mode 可选（不强制）。
4. **`check`（读侧）**：新增 `warnings`（不参与 `ok`，历史行不回改）：
   - spawn 缺 mode（`modeExplicit` 不是 false）⇒ `mode_missing` WARN；
   - 非法 mode ⇒ `mode_invalid` WARN；有 mode 但 `modeExplicit` 非 true ⇒ `mode_not_explicit` WARN；
   - `mode_coverage`：`{spawn, judgeable, unknown}`，其中「显式未决定」(`modeExplicit:false`) 也算**可判定状态**。
5. **用法 docstring** 链接 `lead-dispatch-rules §1.3b`（不重复规则文本）。

---

## 2. 联调证据（`demo-mode-policy.txt`，脚本 `demo_mode_policy.py`）

用**临时日志**（不写真实 `team/dispatch-log.jsonl`，不伪造历史）构造「2 条历史缺 mode + 2 条新记录显式 mode」，调真实检查函数：

```
[WARN] 2/4 条 spawn 记录缺 mode 字段（legacy-1, legacy-2）⇒ 无法判定（checked_count=4）
[INFO] mode_policy 统计：checked_count=4，with_mode=2，缺显式标记=0
dispatch_log.py check mode_coverage = {"spawn": 4, "judgeable": 2, "unknown": 2}
warnings = 2（只命中两条历史行）
```

⇒ **新写入的 spawn 行现在可判定**（不再"全部缺 mode"）；历史 14 条按 append-only 保留为「无法判定」WARN。
真实日志只读核验（`real-log-check.json`）：`ok=True, count=37, mode_coverage={"spawn":14,"judgeable":0,"unknown":14}, warnings=14, problems=0`。

---

## 3. 关闭条件逐条对照

| # | 条件 | 结果 |
|---|---|---|
| 1 | `dispatch_log.py --selftest` PASS；「spawn 无 mode 被拒」是必红用例 | ✅（`selftest.txt`） |
| 2 | 实测不带 mode ⇒ 非 0 且不落盘；带 `--mode mechanical` ⇒ 成功且行含 mode/modeExplicit | ✅（selftest 断言 + 输出） |
| 3 | `team_audit.py --json` 的 `mode_policy` 对新 spawn 行给出可判定结论 | ✅（`demo-mode-policy.txt`：新行不产生 WARN；`with_mode` 计数可见） |
| 4 | 历史 12（实为 14）条旧记录不手工篡改 | ✅（真日志 count/problems 不变；`check` 只 WARN） |
| 5 | `git diff --numstat` 删除 < 插入；报告落 artifacts | ✅（`111 4`；本目录） |

> 说明：真实 `team/dispatch-log.jsonl` 本轮**未追加任何行**（没有真实 spawn 发生，不能为了"演示"伪造派发记录）。

---

## 4. 遗留（需 Lead 裁决，已作为 proposal 记入 `team/steward/findings.jsonl`）

1. **SF-20261024-014**：`audit_determinism` 机检（连跑两次、排除 generatedAt 比对字节）—— 你已实测通过；
   现有规范无「机检必须确定性」条款 ⇒ 等你批准条款后再实现。
2. **SF-20261024-015**：写域粒度（`artifacts/agent/verify` 根 vs 子目录造成 9/11 假重叠 WARN）——
   推荐 (a)+(b) 组合，详见上报消息。
3. **SF-20261024-016**：`mode_policy` 目前把「显式未决定」也计入「缺 mode」；建议把它单列为
   `WARN「显式未决定」`（属既有检查判据细化，需 Lead 批条款后我改 `team_audit.py`；本轮未越界改）。

## 5. 复跑

```powershell
python scripts/agent/dispatch_log.py --selftest
python scripts/agent/dispatch_log.py check
python artifacts/agent/verify/steward/task-107/demo_mode_policy.py
```
