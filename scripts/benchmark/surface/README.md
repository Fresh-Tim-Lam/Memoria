# 显示子系统探针报告（surface probe）

> 位置：`scripts/benchmark/surface/`。与 `scripts/benchmark/graph/`（图谱引擎性能）、
> `maintenance/`（维护作业）、`usage/`（模型用量）**并列**的基准子域：
> 本目录量的是**显示子系统（视图引擎）** —— **契约一致性 + 性能预算**。
> 契约与测试清单的权威说明：[docs/design/view-surface-contract.md](../../../docs/design/view-surface-contract.md)（§5 的 C1–C12、§3.3 的 flush 清单与预算）。
> 语料与操作脚本：`tests/probe-kb/`（构造覆盖 ×7 + 三档规模 + `cases/cases.json`）。

## 为什么报告落这里（而不是 `artifacts/`）

`AGENTS.md §1` 把 `artifacts/**` 定为**可再生缓存**，且 `.gitignore` 忽略它 ⇒ 放那儿的报告**溯不到**。
人 2026-09-28 定：「**入库，相关的测试报告便于溯源**」⇒ 报告走**可提交**路径，即本目录（与 `graph` / `maintenance` / `usage` 同构）。

## 怎么跑（**尚未实现**，如实）

> ⚠️ **运行器还没写。** 目前只有**数据契约**（`tests/probe-kb/cases/cases.json`：14 条操作序列 + 断言）。
> 待实现：一个浏览器驱动（参照 `AGENTS.md` 的 **L4 交互验证**与 `docs/example/rich-content-test/_harness.py`），
> 读 `cases.json` → 对**指定插头**执行操作序列 → 产出报告。

```powershell
# 目标形态（占位；脚本落地后替换为真实用法）
python scripts\benchmark\surface\run_probe.py --kb tests\probe-kb --surface legacy --label legacy-baseline
```

## 产物

- `results/probe-<surface>-<label>_<sha>.json`：结构化 —— 每条 C 的**绿/红**、读数、断言明细；
- `results/probe-<surface>-<label>_<sha>.md`：人读报告 —— C1–C12 逐条结论 + 读数 + **口径与限制**。

## 口径边界（引用数字时必须一起给出）

1. **绿/红按契约判**，**不按"跟 legacy 一致"判** —— 期望值来自**真源文本 + 行为契约**（`view-surface-contract.md` §5）。
2. **性能读数必须绑定文档规模与机器**：不写清档位（1k / 5k / 10k）与运行环境，数字无意义。
3. **C11「插头等价」在不一致时由人裁**：报告**只呈现差异**，不自动判定谁对。
4. **覆盖率以 `cases.json` 的 `covers` 字段为准**；**未被覆盖的 C 必须标「未测」**，不得默认为绿。

## 权限（**尚欠人在 `AGENTS.md §4` 补一行**）

`AGENTS.md §4` 目前只把 `scripts/benchmark/maintenance/results/**` 列为 verifier 可写区。
本目录的 `results/**` **同类**（探针报告 = 取证产物），需人在 `AGENTS.md §4` 补一行
`scripts/benchmark/surface/results/**` —— 该文件为**人维护、Agent 只读**，故 Agent 不自改。
