# 必红证明报告：真实历史违规 → 检查器必须 exit 1

> **目的**：证明发版门禁不是「我推论它会红」，而是**实际喂真实数据后真的红**。
> **作者**：release-manager（2026-10-25）。**未 commit**。
> **runner**：`artifacts/agent/verify/todo/release-standard-fixtures/run_must_red.py`
> **日志**：`artifacts/agent/verify/todo/release-standard-fixtures/must-red.log`
> **结果**：**32/32 PASS**（`MUST-RED PROOF PASS`）。

---

## 1. 为什么用真实历史违规，而不是编造 fixture

本项目已实证：规范**写在文档里靠记住 = 随机数**。v0.4.7 / v0.4.8 / v0.5.0 连续三版标题带副标题，
而规则早已写在 `docs/conventions/version.md`。所以必红 fixture 直接使用：

1. **Lead 记录的三个真实旧标题**（修复前原样）；
2. **真实已发布 body**（GitHub API 抓取的 v0.4.7/0.4.8/0.5.0 当前合规 body），按历史违规形态精确改坏。

这证明检查器能拦住**我们实际犯过的错**，而不是拦住编造的错。

---

## 2. 方法（每个 fixture 都走完整三步）

```
取真实 Release JSON（name/body/assets）
  → 改坏（只改临时副本）
  → 跑 CLI（--verify-published --offline --release-json 副本 --json）
  → 断言 exit == 1 且 failed 列表精确包含预期检查 ID
  → 还原（原始 JSON 再跑）⇒ 必须 exit == 0
  → 仓库文件哈希 + git diff 前后比对（证明 runner 不写工作区）
```

- 真实历史标题：
  - v0.4.7：`Memoria v0.4.7 —— 收摊`
  - v0.4.8：`Memoria v0.4.8 —— 修 P1 + 知识图谱调研`
  - v0.5.0：`Memoria v0.5.0 —— agent 能力架构（S1–S5…）`
- 「改坏」全部可逆、只作用于临时 JSON，不 PATCH GitHub、不写仓库。

---

## 3. 结果：32/32 PASS

每个版本 10 项（3 版 × 10 = 30）+ 2 项全局 = **32**：

| # | fixture（每版各一次） | 改坏方式 | 预期 | 实测 |
|---|---|---|---|---|
| 1 | 已修复真实 body 基线 | 不改 | exit 0 | ✅ exit 0 |
| 2 | **真实历史副标题** | 标题换回 Lead 记录的原标题 | `TITLE-EXACT` FAIL / exit 1 | ✅ |
| 3 | 标题后缀 | `+ " (hotfix)"` | `TITLE-EXACT` FAIL | ✅ |
| 4 | 中文在前 | 交换 EN / ZH 两个语言块 | `BODY-BILINGUAL` FAIL | ✅ |
| 5 | 英文 stub | 英文段主内容替换为 `Short stub.` | `BODY-BILINGUAL` FAIL | ✅ |
| 6 | 缺中文造价段 | `## 造价（Agent 算力）` → `## 造价说明` | `COST-SECTION` FAIL | ✅ |
| 7 | 造价无量级 | 删除 元人民币/元/人民币/CNY/USD/RMB/花费 | `COST-SECTION` FAIL | ✅ |
| 8 | 造价无统计口径 | `统计口径`→`统计说明`、`合并统计`→`合并记账` | `COST-SECTION` FAIL | ✅ |
| 9 | 资产只剩 1 个 | `assets[:1]` | `ASSETS-COUNT` FAIL | ✅ |
| 10 | 还原后必绿 | 原始 body 再跑 | exit 0 | ✅ |
| 31 | 仓库文件哈希前后一致 | `__version__.py` / `version.md` / `Package/VERSION` | 相等 | ✅ |
| 32 | `git diff -- src/` 前后一致 | runner 不写 src | 相等 | ✅（仓库已有其他 agent 未提交改动，故断言「前后一致」而非「为空」） |

日志摘录：

```
MUST-RED PROOF PASS
  [PASS] v0.4.7 已修复真实 body 基线: exit=0 failed=[]
  [PASS] v0.4.7 真实历史副标题必红: exit=1 failed=['TITLE-EXACT']
  [PASS] v0.4.7 中文在前必红: exit=1 failed=['BODY-BILINGUAL']
  [PASS] v0.4.7 造价无量级必红: exit=1 failed=['COST-SECTION']
  ...
  [PASS] v0.5.0 资产数量=1 必红: exit=1 failed=['ASSETS-COUNT']
  [PASS] v0.5.0 还原后必绿: exit=0 failed=[]
  [PASS] 仓库文件哈希前后一致（fixture 未写工作区）
  [PASS] git diff -- src/ 前后一致（本 runner 不写 src）
合计 32 项：32 PASS / 0 FAIL
```

---

## 4. 与 `--selftest` 的分工

| 证明 | 内容 | 是否依赖网络/真实数据 |
|---|---|---|
| `--selftest`（36 项） | 合成最小仓库 fixture：覆盖每条检查的红/绿、CLI 退出码、SKIP 语义、tag 本地 bare remote、资产 JSON 回放 | 完全离线、完全自包含 |
| `run_must_red.py`（32 项） | **真实已发布 body + 真实旧标题**；证明检查拦住实际犯过的错 | 离线（读已抓取 JSON） |

两者互补：selftest 保证逻辑分支全覆盖；must-red 保证「不是只对合成样例有效」。

---

## 5. 复跑方式

```powershell
python scripts/agent/release_preflight.py --selftest
python artifacts/agent/verify/todo/release-standard-fixtures/run_must_red.py
```

退出码 0 = 全部符合预期；1 = 检查器漏检或误报（此时**不得发版**，先修检查器/夹具）。
