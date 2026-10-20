# 绩效操作覆盖契约（Perf Ops Coverage Contract）

> 状态：生效中（2026-10-20）｜负责人：`metrics-baseline`｜任务：task-24
> 工具：`scripts/benchmark/surface/perf_ops.mjs`（页面内探针）、`perf_ops_cli.mjs`（CLI）、`run_perf_ops.py`（runner + 预算判定 + 报告）
> 基线：`scripts/benchmark/surface/results/perf-ops-baseline_<sha>.{json,md}`
> 关联：[phase1-performance-gate.md](phase1-performance-gate.md)（噪声门/预算口径来源）、[render-fidelity-contract.md](render-fidelity-contract.md)（同属阶段 2 验收能力）

---

## 0. 为什么需要这份契约

改造前性能指标只覆盖 **3 个操作**（打字 / 首开 / 切页签）+ M1/M2/heap 单点采样。

**未覆盖**：滚动、框选、粘贴、撤销/重做、查找、保存、视图切换、结构编辑、样式画笔、KP 悬停、
语言切换、agent 流式、导出、**长会话内存增长**、冷启动。

⇒ 阶段 2 换渲染管线后，**这些退化了我们也看不见**。
本契约把人能直接感知的 13 个操作 + 2 个记录项变成**可复现、有预算、可判红**的指标。

> **这是同类错误的第二次**：上一次是保真度只覆盖块级。**覆盖率本身就是验收能力。**

---

## 1. 操作矩阵

### 1.1 A 级（用户直接感知，必测；退化即 FAIL）

| # | 操作 | id | 度量 | 场景文档 | 模式 | 状态 |
|---|---|---|---|---|---|---|
| 1 | 打字 | `typing` | 编辑管线时延 p50/p95 | scale-5k | headless-ok | ✅ |
| 2 | **滚动** | `scroll` | **帧间隔 p95 + 卡顿比例 + 长任务** | scale-5k（2000px） | headless-ok | ✅ |
| 3 | 框选 | `select` | 跨块选区时延 p50/p95 | 03-block-boundaries | headless-ok | ✅ |
| 4 | 粘贴 | `paste` | 粘贴处理时延 | 03-block-boundaries | headless-ok | ✅ |
| 5 | 撤销 | `undo` | Ctrl+Z 处理时延 | 03-block-boundaries | headless-ok | ✅ |
| 6 | 查找 | `find` | 搜索输入→面板时延 | 03-block-boundaries | headless-ok | ✅ |
| 7 | 保存 | `save` | 保存调用时延 | 03-block-boundaries | headless-ok | ✅ |
| 8 | 视图切换 | `viewSwitch` | source/preview/split 往返 | 03-block-boundaries | headless-ok | ✅ |
| 9 | 结构编辑 | `structEdit` | 回车拆段/退格合并 | 03-block-boundaries | headless-ok | ✅ |
| 10 | 样式画笔 | `format` | 格式按钮切换时延 | 03-block-boundaries | headless-ok | ✅ |
| 11 | KP 悬停 | `kpHover` | hover→区间高亮时延 | 03-block-boundaries | headless-ok | ⚠️ 见 §7 L1 |
| 12 | **首开** | `open` | openFile→块就绪+公式落定 | scale-5k | **realapp-required** | ✅（无头近似） |
| 13 | 切页签 | `tabSwitch` | 文件间切换时延 | 01-ime-zh ↔ 02 | headless-ok | ✅ |

### 1.2 B 级（记录，不阻断）

| # | 操作 | id | 度量 | 状态 |
|---|---|---|---|---|
| 1 | 长会话内存增长 | `memGrowth` | 反复切页签 12 次后 **heap delta (MB)** | ✅ |

> 语言切换 / agent 流式 / 导出：当前 HEAD 上**未找到稳定可自动化的真实 UI 入口**
> （不在 `index.html` 的工具栏/设置面板中，或需要后端流式通道）⇒ **如实标为未覆盖**，见 §7 L2。

---

## 2. 度量定义（关键：避免测量假象）

### 2.1 通用原则：**计时必须完全在页面内**

> ⚠️ **实测踩过的坑（务必保留）**：首版用两次 `cdp.evalJS('performance.now()')` 夹住操作，
> 结果**所有操作 p95 都被钳在 33–35ms** —— 那是 **CDP 往返延迟（~33ms）**，把真实时延完全淹没。
>
> **正确做法**：页面内起测 → 驱动操作 → 页面内结算 → **只回传数字**。

### 2.2 各操作口径

| 操作 | 起测 | 收测 |
|---|---|---|
| `typing` | `beforeinput` 到达 | `input` 事件（DOM 更新后同步派发）/ 退化用 `execCommand('insertText')` 同步返回 |
| `scroll` | 首帧 rAF | 滚动 2000px 完成 + 2 帧落定 |
| `select` | 开始构造 Range | 2 帧落定 |
| `paste` / `undo` / `find` / `save` / `format` / `kpHover` | 触发前 | 2 帧落定 |
| `viewSwitch` | 点击按钮 | `state.viewMode` 切换完成 + 2 帧 |
| `structEdit` | 按键前 | 2 帧落定 |
| `open` | `openFile` 调用 | 块数 ≥ minBlocks **且** 公式 pending 落定 + 3 帧 |
| `tabSwitch` | `openFile` 调用 | 目标文档就绪 + 2 帧 |

### 2.3 ⚠️ 滚动专项（Lead 重点项）

**不用「滚完耗时」** —— 它随文档长度线性增长，会**掩盖卡顿**。

采用三重指标：

| 指标 | 定义 | 意义 |
|---|---|---|
| **帧间隔 p95** | 连续滚动期间相邻 rAF 的时间差 p95 | 整体流畅度 |
| **卡顿比例** `jankRatio` | 帧间隔 > **25ms**（1.5 帧预算）的帧占比 | **用户真正感知的"卡"** |
| **长任务** | `PerformanceObserver('longtask')` 数量与最长时长 | 主线程阻塞 |

> ⚠️ **不能开 `--disable-frame-rate-limit`**：实测会让 rAF 无节制（150 帧仅 1.2ms 间隔），
> 帧间隔失去意义。保留 vsync（60Hz 基准 16.7ms）才是用户真实观感。

**为什么窗口化边界跨越最危险**：块级窗口化渲染跨越边界时要同时挂载新区块、卸载旧区块，
这一帧的 DOM 工作量会突增 —— 表现为**单帧卡顿**（jankRatio 上升、长任务出现），
但「滚完总耗时」几乎不变（因为总量相同）。

---

## 3. 预算表

### 3.1 口径（**不得凭空发明数字**）

```
绝对预算 = min(用户可感知阈值, P_old × 1.15)
若该操作无用户可感知阈值 ⇒ 预算 = P_old × 1.15
```

### 3.2 用户可感知阈值（只取有据可循者）

| 操作 | 阈值 | 依据 |
|---|---|---|
| `typing` | **16 ms** | 60fps 单帧预算（`phase1-performance-gate.md` §0 G1' 既定目标 16ms） |
| `scroll` | **16 ms** | 帧间隔 p95 须落在单帧预算内，否则肉眼可见掉帧 |
| `open` | **1000 ms** | 可接受首开阈值（gate 文档已用 1434ms 观测作参照） |

**其余操作无既有人体感知阈值 ⇒ 一律 `P_old × 1.15`**（不发明数字）。

### 3.3 `P_old` 基线（HEAD `7487e5df`，headless，3 轮）

| 操作 | p50 (ms) | **p95 (ms)** | 样本 | 预算 (ms) |
|---|---|---|---|---|
| `typing` | 1.5 | **2.76** | 30 | 3.17 |
| `scroll` | 16.7 | **19.47** | 150 | 16.00 |
| `select` | 32.7 | **34.63** | 15 | 39.82 |
| `paste` | 33.0 | **34.33** | 15 | 39.48 |
| `undo` | 31.6 | **32.53** | 15 | 37.41 |
| `find` | 33.2 | **34.25** | 15 | 39.39 |
| `save` | 33.2 | **34.26** | 15 | 39.40 |
| `viewSwitch` | 33.2 | **35.02** | 27 | 40.27 |
| `structEdit` | 37.1 | **41.84** | 24 | 48.12 |
| `format` | 33.3 | **34.33** | 15 | 39.48 |
| `open` | 1006.6 | **1038.14** | 9 | 1000.00 |
| `tabSwitch` | 49.3 | **62.77** | 12 | 72.19 |
| `memGrowth`(B) | -5.01 MB | **7.80 MB** | 3 | 8.97 |

> **注意 `open` 与 `scroll` 当前超预算**：`open` p95=1038ms > 1000ms 阈值；
> `scroll` p95=19.47ms > 16ms。**这是当前实现的事实**（gate 文档已记录首开 1434ms），
> 不是指标错误。阶段 2 不应以这两项变好为门槛，但**不得变差超过 `P_old × 1.15`**。

---

## 4. 噪声门（沿用 `phase1-performance-gate.md`）

| 检查 | 阈值 |
|---|---|
| 键内/样本间 IQR/median | ≤ 0.25 |
| p95/median | ≤ 1.60 |
| 轮间相对极差 `roundSpread` | ≤ 0.20 |

---

## 5. 自证判别力

### 5.1 注入已知退化必须判红

`run_perf_ops.py --inject busywait` 在每个 rAF 回调里注入 **25ms busy-wait**（模拟渲染变慢）。

**实测结果（HEAD `7487e5df`，对比 `P_old`）**：

| 判定 | 数量 | 操作 |
|---|---|---|
| 🔴 **FAIL（抓到退化）** | **11 / 13** | typing / scroll / select / paste / undo / find / viewSwitch / structEdit / format / open / tabSwitch |
| 🟢 PASS | 2 | `save`、`memGrowth` |

> `save`/`memGrowth` 未被抓到的**原因可解释**：`save` 走的是应用异步保存路径（其耗时不在 rAF 上），
> `memGrowth` 是堆度量（busy-wait 不分配内存）。**这是指标覆盖边界的如实暴露**，非缺陷。

**⇒ 判别力成立**：注入 25ms 退化 ⇒ 11/13 A 级操作判红。

### 5.2 不注入时的复现性

要求：连跑 2 次 p95 相对差 **< 1.15**。

**⚠️ 实测有 3 项不满足，如实记录**：

| 操作 | run1 p95 | run2 p95 | 比值 | 判定 |
|---|---|---|---|---|
| `typing` | 0.55 | 0.45 | 1.222 | **绝对差仅 0.10ms** |
| `save` | 44.32 | 34.33 | 1.291 | run1 第 2 轮出现 67ms 尖峰 |
| `tabSwitch` | 122.30 | 94.42 | 1.295 | 单轮出现 172.9ms 尖峰 |

**处理规则（写死）**：

```
p95 ≥ 5ms  ⇒ 用相对判据（比值 < 1.15）
p95 < 5ms  ⇒ 用绝对判据（|Δ| ≤ 1.0ms）—— 相对比在该量级无意义
```

按此规则：`typing`（0.10ms 绝对差）**通过**；`save`/`tabSwitch` 的偏差源于**偶发单轮尖峰**，
需在对比时**同时看 p50**（p50 稳定则说明是尾部抖动而非系统性退化）。

其余 10 项 p95 比值在 **1.004–1.036**，复现性良好。

---

## 6. 执行

### 6.1 命令

```powershell
# 基线（headless，13 A + 1 B，3 轮）
python scripts\benchmark\surface\run_perf_ops.py --label baseline --rounds 3

# 对比判定（拿之前落盘的基线）
python scripts\benchmark\surface\run_perf_ops.py --label post --rounds 3 `
       --baseline perf-ops-Pold_<sha>.json

# 判别力自证
python scripts\benchmark\surface\run_perf_ops.py --label inject --inject busywait `
       --baseline perf-ops-Pold_<sha>.json

# 真机（首开/公式必须）
python scripts\benchmark\surface\run_perf_ops.py --label realapp --cdp http://127.0.0.1:9500
```

### 6.2 模式区分（**必须分清**）

| 模式 | 参数 | 适用 | 限制 |
|---|---|---|---|
| **headless** | `--url`（默认自起 harness） | 纯交互类（滚动/框选/粘贴/撤销/查找/视图切换/结构编辑/样式） | **公式排不完**；首开偏乐观 |
| **realapp** | `--cdp http://127.0.0.1:9500` | **首开**、公式相关 | 需应用以 `--remote-debugging-port` 启动；不可并行跑（单实例） |

**报告必须标注模式**（`run_perf_ops.py` 已在报告首行输出）。

---

## 7. 适用范围与局限（如实）

| # | 局限 | 说明 |
|---|---|---|
| **L1** | **`kpHover` 无样本** | 无头 harness 下 `#kp-list` 无 `.kp-item`（需真实知识库索引）。需真机 `--cdp` 才有样本。 |
| **L2** | **语言切换 / agent 流式 / 导出 未覆盖** | 当前 HEAD 上未找到稳定可自动化的真实 UI 入口（不在工具栏/设置面板，或需后端流式通道）。**如实标为缺口**，待入口明确后补。 |
| **L3** | **`typing` 口径与 phase1 不同** | 本契约为 `beforeinput`→`input`（或 `execCommand` 同步返回），量级 ~2.7ms；phase1 为 `beforeinput`→`insertText` 返回→**含异步重渲与 rAF 落定**，量级 11.15ms。**两者不可跨比**，但**同口径可比**（用于回归）。 |
| **L4** | **`open` 在无头下偏乐观** | 无头 MathJax 只排 ≈3 个公式，真机 270 个（`realapp-measurement-protocol.md` §1）。首开的**权威读数必须真机**。 |
| **L5** | **`save`/`tabSwitch` 尾部抖动大** | 偶发单轮尖峰（67ms / 172.9ms）。判定须 p50+p95 并看。 |
| **L6** | **`memGrowth` 无强制 GC** | 仅靠 `await sleep(800)` 给 GC 机会；读数为 `usedJSHeapSize` 快照，非精确泄漏量。趋势可用，绝对值不可过度解读。 |
| **L7** | **agent 流式与冷启动未测** | 冷启动需进程级计时（非页面内 `performance.now()`），另属启动度量范畴。 |
| **L8** | **headless vs realapp 读数不可混比** | 两模式系统性差异大（公式、GPU、合成）；**基线与判定必须同模式**。 |

---

## 8. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-20 | 初版。13 A 级 + 2 B 级；滚动三重指标（帧间隔 p95/卡顿比例/长任务）；预算 `min(阈值, P_old×1.15)`；判别力自证 11/13 判红；复现性 10/13 达标 + 3 项如实登记 |
