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

## 交互契约测试（interaction，2026-10-20 新增）

**为什么另起一套**：`cdp.mjs` 量的是**性能与渲染契约**（C1–C12），它的输入只有「打字」；
而重构要保住的是**鼠标/键盘/IME 的交互手感**（选区三态、双击选词、拖拽跨块、Ctrl/Shift 组合扩选、样式画笔）。
这些必须用**受信任的 Input 事件**去驱动，用 `el.value=` / `dispatchEvent` 伪造是测不出来的。

| 文件 | 作用 |
|---|---|
| `interaction.mjs` | CDP 客户端 + 交互原语（`Input.dispatchMouseEvent` 拖拽/双击、带 `modifiers` 的键盘、`imeSetComposition`）+ 剧本执行器 + 选区断言与快照 |
| `run_interaction.py` | 复用 `run_probe.py` 的 `load_harness()` 起服务与桥，跑剧本并落报告 |
| `scenarios/interactions.json` | 11 个交互契约剧本（拖选同块/跨块、双击选词、Shift+方向、Ctrl+Shift 按词、Shift+Home/End、Ctrl+A、Shift+点击、IME、画笔） |

用法：

```bash
# 在「旧实现」上跑一遍，产出金标准（新实现落地后用同一份剧本再跑，逐剧本 diff 快照）
python scripts/benchmark/surface/run_interaction.py \
    --kb "artifacts/baseline-kb/数字通信原理" \
    --label legacy-golden
```

产物：`results/interaction-<label>_<sha>.md`（人读）+ `raw-interaction-<label>_<sha>.json`（快照明细）。

**口径**：
- 每个剧本抓「选区 anchor/focus（节点偏移 + 所属块）+ 块可见文本」⇒ 新老实现**同一剧本结果必须一致**；
- 剧本内**不要**依赖绝对像素/绝对行号，用「块内第 N 个字符」定位，抗布局漂移；
- 三条实测坑（写进代码注释，别再踩）：① `mouseMoved` 必须带 `button:'left'` 才会扩选（只给 `buttons:1` 不扩）；
  ② 跨块拖拽两点必须**同时在视口内**（视口外的事件会被浏览器丢弃）；③ 应用启动会**异步自动打开默认文件**，
  抢在它前面 `open` 会被覆盖 ⇒ 必须先等 `currentPath` 稳定。
