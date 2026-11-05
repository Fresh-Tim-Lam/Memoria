# JUDGE-PACK（草稿）— 状态与使用

> **状态**：`draft_pre_amendment`；**不是 C0 gate 证据**，不用于 0.5 解禁。
> **生成**：`scripts/corpus/build_judge_pack.py`；产物 `artifacts/corpus/pilot/JUDGE-PACK.zip`（zip 不含答案 key）。
> **用途**：先校准人类 judge 流程（20 题 + 3 个 A/B 呈现题），约 2–3 小时。

## 包含

| 文件 | 说明 |
|---|---|
| `JUDGE-GUIDE.md` | 操作说明、评分列定义、2–3h 流程 |
| `judge-pack.json` | 20 题盲判包：问题 + 候选答案 + 3–5 个候选片段（不含 expected id） |
| `judge-sheet.csv` / `.jsonl` | 空白评分表（20 行） |
| `A-B-TASKS.md` | 3 个静态呈现偏好题 + 两张图 |
| `images/` | 旧 KGviz 2D / 新多层次 2D 截图 |
| `TIME-LOG.csv` | 计时模板 |
| `NOTICE.md` | 源许可/归属 |

答案 key 单独在 `artifacts/corpus/pilot/judge-answer-key.json`，**不放进 zip**；judge 不应查看。

## 限制

- 20 题来自 pilot 既有 draft queries；答案候选由机器 KP 描述生成，**不是** C0 的 MHA-20；
- 静态 A/B 不能测拖拽/悬停/找答案时间；
- 结果只用于校准 judge 流程和发现题目/片段问题；正式 pilot 需 C0a-2 工具 + MHA-20 + 预注册。

## 校验

- 20 题 / 80 片段 / 上下文 13,769 字符（不是 126k 全文）；
- 盲判包无 `expected_kp_ids`；zip 无 `answer-key`；
- 2× 重建 `judge-pack.json` sha 相同：`c4346b2b…`。
