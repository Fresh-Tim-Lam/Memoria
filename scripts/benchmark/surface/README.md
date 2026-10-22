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

## 惰性路径交互门禁（W4.1，2026-10-23 新增）

**为什么另起一套**：上面 12 个交互剧本的语料都是 <200 块的小文档 ⇒ `_lazyMaterializeEnabled` 走**全量渲染**，
惰性物化 / 工作集淘汰 / 公式 pending 三个已合入的重量级特性**没有任何固定回归**。本门禁专门跑
≥1000 块的大文档，把「打开/拖到 30·50·70·90%/回顶/长滚/编辑保护」变成一条命令可复跑的 PASS/FAIL。

| 文件 | 作用 |
|---|---|
| `run_lazy_gate.py` | **一条命令入口**：复用 `run_probe.load_harness()` 起服务（与 12 剧本同一套 harness），跑 `lazy_gate.mjs`，落 JSON + MD |
| `lazy_gate.mjs` | CDP 执行器：复用 `interaction.mjs` 的 `withBrowser` / `CDP` / `Interactions`，按 L0–L5 量断言 |
| `scenarios/lazy-gate.json` | 检查清单与阈值（fractions / 漂移行数 / DOM 屏数 / 堆预算） |
| `make_lazy_gate_fixture.py` | 确定性生成 fixture（160 节 ≈ 3662 块，含公式/表格/mermaid/代码/列表/引用） |
| `fixtures/lazy-gate-kb/` | **入库的固定 fixture**（不依赖 `artifacts/**`，可提交、可 diff） |

```powershell
# 门禁本体（默认 6 项检查，~26s）
python scripts/benchmark/surface/run_lazy_gate.py

# 顺带证明既有 12 剧本仍 12/12（同一次运行，证据写进同一份 JSON）
python scripts/benchmark/surface/run_lazy_gate.py --with-existing-12

# 负向验证：门禁必须 FAIL（证明守卫不是摆设）
python scripts/benchmark/surface/run_lazy_gate.py --sabotage viewport-placeholder --label neg-placeholder
python scripts/benchmark/surface/run_lazy_gate.py --sabotage noevict              --label neg-noevict
```

产物：`results/lazy-gate-<label>_<sha>.{json,md}`（JSON 每步含 `assertions[{name,ok,expected,actual,note}]`
与 `readings`，FAIL 时直接定位到 `L2-positions / position-30pct / settled-viewport-placeholders-0`）。

### 检查与阈值

| id | 量什么 | 阈值/口径 |
|---|---|---|
| L0 `idle-raf` | **测量可信门**：空转 90 帧 rAF 间隔 p50 | ≤20ms；不过则 `measurement.trusted=false`，整体 FAIL（最小化窗口会节流 rAF，读数不可信） |
| L1 `open-first-screen` | `openFile()` → 首个已物化块进入视口 | ≤500ms；且 `totalBlocks≥1000`、`placeholders>0`、`materialized<total`、`metricsSrc∈{probe,computed}`（确实走惰性，且占位高度是实测而非 detached 24px bug） |
| L2 `positions` | 30/50/70/90%（按**源行数**定位；先 settle 再对齐一次） | 停稳后视口 `.-pv-placeholder`=0；文本与**该位置覆盖的源行区间**重合 ≥8 个 token/2-gram；远离视口 >250 行的 MARK/TOKEN = 串位；相对漂移 = 同一锚点块屏幕位移÷实测行高 ≤5 行 |
| L3 `back-to-top` | 回 `scrollTop=0` | 首块相对视口顶偏移 Δ≤5 行、绝对源行 Δ≤5、视口占位=0、有文本/媒体（无白屏） |
| L4 `long-scroll` | 32 步滚完整篇 | 同时物化块 ≤ `8 × ceil(paneH/行高)`；`evictTotal` 在长滚期间必须增长；`suspended=false`；堆峰值/驻留增量有上限，且轨迹不能严格单调递增 |
| L5 `edit-protect` | 编辑已物化块 → 滚到 95% 触发远处淘汰 → 滚回 | 远处 `evictTotal` 必须增长（证明淘汰真的发生）；被编辑块仍是真块；编辑文本仍在；光标块+字符偏移不变 |

### 负向验证（每个守卫都必须能报错）

- `--sabotage viewport-placeholder`：把 30% 位置视口内一个已物化块换回占位，并把块下标改成**非数字**
  （产品任何补物化路径都会跳过它 ⇒ 缺陷是持续的，不会 1.5s 后自愈）。期望输出：`L2-positions FAIL`，
  唯一失败断言 `settled-viewport-placeholders-0：期望 0，实际 1`。
- `--sabotage noevict`：调用产品自带 `window.__MEMORIA_MATERIALIZE_ALL()`（它会把全文物化并全程
  `_lazyEvictSuspended=true`，等价于把 `LAZY_EVICT_KEEP_SCREENS` 调到极大）。期望输出：
  `L4-long-scroll FAIL`（`eviction-ran-during-long-scroll` / `eviction-not-suspended` / `dom-within-8-screens`），
  并连带 `L5-edit-protect FAIL`（远处不再淘汰）。两次实测均 FAIL，恢复后重跑 PASS。

### JSON 结构（`schema=memoria-lazy-gate/v1`）

```jsonc
{
  "schema": "memoria-lazy-gate/v1",
  "sabotage": null,                     // 负向验证注入；正常为 null
  "fixture": { "path": "...", "totalLines": 5784, "markers": 160 },
  "measurement": { "raf": { "p50Ms": 16.6, "p95Ms": 17.7 }, "trusted": true },
  "open": { "firstVisibleMs": 118, "stats": { "totalBlocks": 3662, "placeholders": 3629, "lhPx": 22.4 } },
  "positions": [ { "frac": 0.3, "driftLines": 0, "vpPlaceholders": 0, "topLine": 1735, "ratio": 0.3 } ],
  "longScroll": { "evictTotal": 3250, "maxMaterialized": 107, "domLimit": 248, "peakDeltaMb": 17.4 },
  "edit": { "blockIndex": 1834, "editSurvives": true, "caretPreserved": true },
  "checks": [ { "id": "L2-positions", "status": "PASS", "steps": [ { "step": "...", "assertions": [ ... ], "readings": { ... } } ] } ],
  "summary": { "pass": true, "failedIds": [] },
  "existing12": { "ok": true, "returncode": 0 }   // 仅 --with-existing-12
}
```

### 口径与限制（引用数字时必须一起给）

1. 跑在**无头 Edge harness**（与 12 剧本同一条 CDP 路径），不是真机 pywebview；首开 118ms 是 harness 读数，
   真机（WebView2 + 真实窗口）需按 `docs/design/benchmark-measurement-protocol.md` 另测。
2. 「堆」是 `performance.memory.usedJSHeapSize`（不是进程 RSS）；采样前后尽量 `gc()`（启动加了
   `--js-flags=--expose-gc --enable-precise-memory-info`），仍受引擎 GC 时机影响 ⇒ 结论看「峰值/驻留增量 +
   是否严格单调」的组合，不看单个采样点。
3. 「DOM ≤ 视口×8」按**同时存在的块数**（含占位）计；`#preview` 节点数只作报告读数列出。
4. fixture 全部合成，无用户数据；`LAZYGATE-MARK-<NNNN>` 每节一行，是「文本↔源行号」的对齐锚点。
   改 fixture 后必须重跑 `make_lazy_gate_fixture.py` 并更新本页读数。
5. 已知未验证：L4 堆断言在长时间/并发跑机器上是否稳定；fixture 的真实感（合成文档，非教材原文）；
   真机 GPU/字体/缩放组合下的漂移；公式 pending 的独立断言（当前由「视口文本/媒体存在 + 公式块可物化」间接覆盖）。

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
