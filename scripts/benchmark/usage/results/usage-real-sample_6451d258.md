# Agent 用量报告 — real-sample

> 生成时间（UTC）：`2026-09-18T06:56:53.801637+00:00` ；来源 commit：`6451d258`（dirty（含未提交改动））
> 知识库：`D:\AAA_Jupyter\Memoria\docs\example\AAA_Vocab` ；脚本：`python scripts/benchmark/usage/report_usage.py --kb … --label real-sample`

## 1. 总览

| 指标 | 值 |
|---|---|
| 会话数 | 1 |
| 轮次 | 3 |
| 输入 tokens | 128,907 |
| 输出 tokens | 4,504 |
| 合计 tokens | 133,411 |
| 命中 tokens | 未知 |
| 未命中 tokens | 未知 |
| 命中率 | 未知 |
| 估算轮次 | 0 |
| cache 未知轮次 | 3 |

## 2. 按会话

| 会话 | 轮次 | 输入 | 输出 | 合计 | 命中 | 未命中 | 命中率 | 估算轮次 | cache 未知 | 备注 |
|---|---|---|---|---|---|---|---|---|---|---|
| `session-20260918T025752Z-7e93534e` | 3 | 128,907 | 4,504 | 133,411 | 未知 | 未知 | 未知 | 0 | 3 |  |

## 3. 按轮次

| 会话 | seq | 输入 | 输出 | 合计 | 命中 | 未命中 | 命中率 | 估算 |
|---|---|---|---|---|---|---|---|---|
| `session-20260918T025752Z-7e93534e` | 3 | 8,713 | 233 | 8,946 | 未知 | 未知 | 未知 | 否 |
| `session-20260918T025752Z-7e93534e` | 23 | 43,178 | 2,008 | 45,186 | 未知 | 未知 | 未知 | 否 |
| `session-20260918T025752Z-7e93534e` | 45 | 77,016 | 2,263 | 79,279 | 未知 | 未知 | 未知 | 否 |

## 4. 口径与限制

- **一轮** = 会话文件里的一条 `loop/end` 事件（一次提问里全部模型步数之和）；字段即 `loop/end.usage`。
- **命中 / 未命中** = 端点上报的 `cache_read_tokens` / `cache_miss_tokens`（DeepSeek 顶层 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`；OpenAI 形态的 `prompt_tokens_details.cached_tokens` 只给命中量，未命中量按 `prompt - 命中` 补出）。
- **命中率未知 ≠ 0**：本次改动之前落盘的**老会话**没有 cache 字段，其轮次计入 `cache 未知轮次`（`cache_unknown_turns`），且**不参与**命中率分母 ⇒ 命中率显示「未知」而不是 0%。
- **估算**（`estimated`）：端点**完全没给** usage、由启发式估算得出；只有「没给 usage」才置真，端点给了 usage 但缺 cache 字段不算估算。
- 会话文件**未记录模型名**，故逐轮行不含 `model`。
- 单份会话最多扫描 2 MiB（`SCAN_MAX_BYTES`）；超限的会话在「备注」标注「扫描超上限、仅统计前半段」（`capped:true`）。
- **本脚本只读知识库**：只读 `<kb>/.memoria/agent/sessions/*.jsonl`，除 `--out` 目录外不写任何位置。
- 来源：commit `6451d258`、生成于 `2026-09-18T06:56:53.801637+00:00`、命令 `python scripts/benchmark/usage/report_usage.py --kb D:\AAA_Jupyter\Memoria\docs\example\AAA_Vocab --label real-sample`。
