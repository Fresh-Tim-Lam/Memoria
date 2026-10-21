# 显示子系统探针报告（surface probe）

> 位置：`scripts/benchmark/surface/`。与 `scripts/benchmark/graph/`（图谱引擎性能）、
> `maintenance/`（维护作业）、`usage/`（模型用量）**并列**的基准子域：
> 本目录量的是**显示子系统（视图引擎）** —— **契约一致性 + 性能预算**。
> 契约与测试清单的权威说明：[docs/design/view-surface-contract.md](../../../docs/design/view-surface-contract.md)（§5 的 C1–C12、§3.3 的 flush 清单与预算）。
> 语料与操作脚本：`tests/probe-kb/`（构造覆盖 ×7 + 三档规模 + `cases/cases.json`）。

## 🚨 硬规则（task-55，先读这段再跑任何测量）

> **冻结语料只读；测试写入一律在副本上；每次真机测试前后校验 sha。**

| 规则 | 说明 |
|---|---|
| **冻结语料只读** | `artifacts/_p5_matrix_kb`、`artifacts/baseline/**`、`artifacts/baseline-kb/**` 一律**只读**。 |
| **写类测试用副本** | `save` / `paste` / 编辑 / 结构编辑 / 撤销重做 等**会写 KB** 的操作，必须用 `make_work_copy()` 建副本，`MEMORIA_KB` 指向副本，报告里写明**副本路径**。 |
| **前后校验 sha** | 每次真机测试开始前 + 结束后各算一次全 13 文档 sha，不一致 ⇒ **判红并点名文件**。 |

**为什么（真实缺陷，进行中）**：2026-10-21 22:57:54，`artifacts/_p5_matrix_kb/corpus/03-block-boundaries.md`
被测试的自动保存写入了 `ZZZ`（778B→814B，同时 LF→CRLF）。而 P6a 在 20:49 的 diag 里该文档**不含** `ZZZ`
⇒ **污染发生在测试运行期间**，不是早年遗留。后果：`p5_perf_frozen` 的 `blocks=32` / `upsert=48`
是污染态下的值，**基线失效并已重建**（task-55）。

**怎么用**：

```powershell
# ① 测试前：冻结 KB 校验 + 落 manifest
python scripts/benchmark/surface/_kb_guard.py --kb artifacts/_p5_matrix_kb `
    --manifest artifacts/baseline/p5_perf_frozen/kb-manifest.json

# ② 跑测量 …

# ③ 测试后：对比前快照（不一致 ⇒ exit 1 并点名）
python scripts/benchmark/surface/_kb_guard.py --kb artifacts/_p5_matrix_kb `
    --verify artifacts/agent/verify/frozen-kb-guard-before.json
```

```python
# 需要写 KB 的测试：一律用副本
sys.path.insert(0, "scripts/benchmark/surface")
from _kb_guard import KbGuard, make_work_copy

guard = KbGuard("artifacts/_p5_matrix_kb"); guard.snapshot_before()
work  = make_work_copy("artifacts/_p5_matrix_kb", label="save-test")   # 副本
os.environ["MEMORIA_KB"] = str(work)                                   # 指向副本
...                                                                     # 跑测量
guard.assert_clean("后")                                                # 不干净即抛异常判红
```

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

## 大库基线读数（baseline，2026-10-20 新增）

`run_probe.py` 的用例绑死 `tests/probe-kb` 构造语料；**大库**（真实知识库，如 `数字通信原理`）需要另一套读数：

```bash
python scripts/benchmark/surface/run_baseline.py \
    --kb "artifacts/baseline-kb/数字通信原理" \
    --file "教材/02_第2章_信号分析基础.md" \
    --file-b "教材/04_第4章_信息论基础.md" \
    --label legacy-bigdoc
```

量四件事：**首开就绪 / 切页签回原文件 / 逐键打字时延 / JS 堆与 DOM 节点规模**。

**已知读数限制（必须随报告一起读）**：
- 「就绪」判据 = 块数连续稳定 + 无 loading 占位；在**无头 harness** 里公式排版（MathJax）可能不完成
  （实测某 158KB 文档预 览 `svg` 仅 3 个）⇒ 该读数应理解为**布局就绪**，不含完整公式排版；
- 含公式的**完整**首开耗时需要在**真实应用**上补测（人执行，按 §交互契约测试 口径记录）。
- 台账里的历史基线（`results/`）与本次读数必须同语料同机器才可比。
