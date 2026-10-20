# 绩效操作覆盖矩阵 · inject（7487e5df）

> 模式：**headless**（无头 Edge；首开/公式相关需 `--cdp` 真机）
> 轮数：每操作 3 轮　｜　噪声门：IQR/med≤0.25, p95/med≤1.60, roundSpread≤0.20

> **注入**：`"busywait"` —— 期望被判超预算时须如实显红

## 操作矩阵（A 级必测 13 项 / B 级记录 1 项）

| 操作 | 级 | 度量 | p50 | **p95** | 样本 | P_old | 预算 | 判定 |
|---|---|---|---|---|---|---|---|---|
| `typing` | A | latency | 1.55 ms | **2.66 ms** | 30 | 0.55 ms | 0.63 ms | 🔴 FAIL |
| `scroll` | A | frames | 34.0 ms | **39.36 ms** | 150 | 18.56 ms | 16.0 ms | 🔴 FAIL |
| `select` | A | latency | 77.9 ms | **103.05 ms** | 15 | 34.44 ms | 39.61 ms | 🔴 FAIL |
| `paste` | A | latency | 50.8 ms | **51.53 ms** | 15 | 34.96 ms | 40.2 ms | 🔴 FAIL |
| `undo` | A | latency | 91.7 ms | **92.93 ms** | 15 | 33.15 ms | 38.12 ms | 🔴 FAIL |
| `find` | A | latency | 51.8 ms | **71.12 ms** | 15 | 34.22 ms | 39.35 ms | 🔴 FAIL |
| `save` | A | latency | 50.5 ms | **50.85 ms** | 15 | 44.32 ms | 50.97 ms | 🟢 PASS |
| `viewSwitch` | A | latency | 83.9 ms | **107.7 ms** | 27 | 34.07 ms | 39.18 ms | 🔴 FAIL |
| `structEdit` | A | latency | 68.7 ms | **104.83 ms** | 24 | 42.79 ms | 49.21 ms | 🔴 FAIL |
| `format` | A | latency | 52.0 ms | **57.09 ms** | 15 | 34.38 ms | 39.54 ms | 🔴 FAIL |
| `kpHover` | A | latency | - | **-** | 0 | - | - | - |
| `open` | A | latency | 1148.5 ms | **1250.3 ms** | 9 | 995.3 ms | 1000.0 ms | 🔴 FAIL |
| `tabSwitch` | A | latency | 172.6 ms | **181.44 ms** | 12 | 122.3 ms | 140.64 ms | 🔴 FAIL |
| `memGrowth` | B | heap | -5.42 MB | **7.51 MB** | 3 | 7.8 MB | 8.97 MB | 🟢 PASS |

## 滚动专项（Lead 重点项）

指标 = **帧间隔 p95**（不是"滚完耗时"，后者随文档长度线性增长会掩盖卡顿）+ 长任务数。

- 帧间隔：p50=34.0 ms，**p95=39.36 ms**，max=73.6 ms（150 帧）
- **卡顿比例**（帧间隔 > 25 ms 的帧占比）：中位 **1**，最大 1
- 长任务：中位数 **0** 个，最长 73 ms
- 滚动距离：2000 px

## 预算口径

**绝对预算 = min(用户可感知阈值, P_old × 1.15)**；无用户阈值的取 `P_old × 1.15`。

| 操作 | 用户可感知阈值 | 依据 |
|---|---|---|
| `typing` | 16.0 | 60fps 单帧预算（gate §0 G1' 既定目标 16ms） |
| `scroll` | 16.0 | 帧间隔 p95 落在单帧预算内，否则肉眼可见掉帧 |
| `open` | 1000.0 | 可接受首开阈值（gate 已用 1434ms 观测作参照） |
