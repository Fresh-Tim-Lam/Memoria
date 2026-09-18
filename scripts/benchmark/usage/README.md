# Agent 用量报告（usage report）

> 位置：`scripts/benchmark/usage/`。与 `scripts/benchmark/graph/` 是**并列**的基准子目录：
> graph 量的是**图谱引擎性能**（渲染/布局耗时），本目录量的是**模型 token 用量**
> （会话 `loop/end.usage` 的聚合），为后续 token benchmark / A-B 对照打前置。
> 口径与已知限制的权威说明在 `docs/reference/agent-guide/10-data-layout-and-host-embedding.md` §2.17。

## 快捷运行

```powershell
# 真实样本（`docs/example/AAA_Vocab` 有 1 个真实会话，但没有 cache 字段 ⇒ 命中率显示「未知」）
python scripts\benchmark\usage\report_usage.py --kb docs\example\AAA_Vocab --label real-sample

# 只统计某个会话
python scripts\benchmark\usage\report_usage.py --kb <知识库> --session <会话 id> --label one-session

# 自定义输出目录（默认 scripts\benchmark\usage\results\）
python scripts\benchmark\usage\report_usage.py --kb <知识库> --out artifacts\_usage
```

## 产物

- `results/usage-<label>_<sha>.json`：结构化数据（`meta` / `sessions` / `turns` / `summary`），供后续 A/B；
- `results/usage-<label>_<sha>.md`：人读报告 —— 总览 / 按会话 / 按轮次（默认最多 200 行，
  `--max-turns` 可调）/ **口径与限制**。

## 数据来源

`<kb>/.memoria/agent/sessions/*.jsonl` 里每条 `loop/end` 事件的 `usage` 载荷
（`services/agent/loop.py::_usage_payload()` 写、`services/agent/usage_report.py` 读）。
**只读**：本脚本除 `--out` 目录外不写任何位置；`--out` 落在知识库内会被直接拒绝。

## 口径边界（引用数字时必须一起给出）

1. **一轮 = 一条 `loop/end`**（一次提问里全部模型步数之和），不是"一次模型请求"。
2. **命中率未知 ≠ 0**：改动前落盘的**老会话**没有 cache 字段 ⇒ 其轮次计入
   `cache_unknown_turns` 且**不参与**命中率分母，命中率显示「未知」。
3. **`estimated`**：只有端点**完全没给** usage 才置真（启发式估算）；给了 usage 但缺 cache 字段不算估算。
4. 会话文件**未记录模型名**，逐轮行不含 `model`。
5. 单份会话最多扫描 2 MiB（`SCAN_MAX_BYTES`）；超限会话标 `capped:true`，只统计上限内的轮次。
6. **不设价格表**：报告只给"命中 / 未命中 / 输入 / 输出"这类**事实 token 数**，
   成本换算由使用方按当时的公开价自行乘。

## 与 RPC 的关系

同一套聚合也经 RPC `agent_usage_stats(kb_path, session_id=None)` 暴露（**只读**），
面板/前端可直接复用；实现是同一个 `services/agent/usage_report.py`。
