# 显示子系统探针报告 · legacy 契约基线

> 插头 `legacy` ｜ label `verify-p1` ｜ git `bdadd8d7` ｜ 生成 2026-10-20T14:30:28Z
> 契约：[view-surface-contract.md §5](../../../docs/design/view-surface-contract.md)
> 语料：`tests/probe-kb/`（cases.json + corpus + scale）

## 环境与口径

| 项 | 值 |
|---|---|
| browser | Edg/155.0.4283.45 |
| edge | C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe |
| node | v24.19.0 |
| kbServed | D:\AAA_Jupyter\Memoria\artifacts\_probe_kb |
| kbSource | D:\AAA_Jupyter\Memoria\tests\probe-kb |
| kbSourceHasMemoria | 是 |
| casesFile | tests/probe-kb/cases/cases.json |
| scaleDoc | tests/probe-kb/scale/scale-5k.md |
| scaleDocLines | 5000 |
| c9Protocol | v1 / docs/design/benchmark-measurement-protocol.md |
| c9Params | warmup=5, R=5, keysPerRound=10, settleTimeout=1500ms |
| c9NoiseThresholds | IQR/median<=0.25, p95/median<=1.6, roundSpread<=0.2, minKeys>=20 |
| appReady | True |
| runDurationMs | 34791 |

- **绿/红按契约判**（真源文本 + 行为契约），不按「与老实现一致」判。
- **性能读数绑定文档规模**：本运行 C9 用 `scale/scale-5k.md`，其真实行数见下表（**不等于**契约基准文档的 5900 行，读数须与档位一起引用）。
- **未测的 C 一律标「未测」并写明原因**，不默认成绿。
- 打字一律走 CDP `Input.dispatchKeyEvent`（受信任输入），非 `el.value=` 伪造。

## 复现

```powershell
node scripts\benchmark\surface\cdp.mjs --selftest
python scripts\benchmark\surface\run_probe.py --kb tests\probe-kb --label verify-p1
```

## C1–C12 逐条结论

| # | 断言 | 结论 | 读数 / 原因 |
|---|---|---|---|
| C1 | 块 id 稳定 | 🟢 绿 | 4 例（mid、head、tail、last-block）全部：被编辑块 id 可变（允许变化 0 次）、**其余块 id 全部不变**、块数保持 21。 |
| C2 | 文本保真 | 🟢 绿 | 打开 01-ime-zh.md 不编辑：state.doc.body 逐字等于 磁盘文件（len body=485 / disk=485） |
| C3 | 打字当帧可见 | 🟢 绿 | 受信任输入 keyDown(text='a') 后**不等 rAF** 立刻读 DOM：块文本 已含 'a' |
| C4 | 真源不落后 | 🟢 绿 | 同一次按键后立刻读真源：state.doc.lines[L] 已含字符；caret→块映射 正确 |
| C5 | 冻结不破 | ⚪ 未测 | 需「块编辑中（textarea 在文档内）+ 触发块级重渲」两步：双击进块编辑可用，但驱动块级重渲需要一个**未暴露的应用入口**；本次未实现 ⇒ 未测。 |
| C6 | 落点准确 | 🔴 红 | 目标-头 L=5 首屏块=[4,4] ✓；目标-中 L=19 首屏块=[19,19] ✓；目标-尾 L=29 首屏块=[25,25] ✗（文档末尾滚动钳制：目标块[29,29]已渲染且可见，但无法置顶） |
| C7 | 切模式不漂 | 🟢 绿 | 锚点行 preview#0=1 → preview#1=1，Δ=0（≤1 判绿） |
| C8 | 交互存活 | ⚪ 未测 | 需断言 onLinkActivate 回调、图片双击进编辑、KP band 定位三件交互存活；回调断言需在页面侧挂测试钩子，本次未实现 ⇒ 未测。 |
| C9 | 性能预算 | 🟢 绿 | 文档 scale-5k.md（5000 行）逐键采样：n=50（R=5 × 10 键）× warmup 5；min 11.9 ms / median 13.3 ms / p95 15.1 ms / max 15.7 ms；IQR 0.98 ms，IQR/median 0.074，p95/median 1.137，轮间极差 0.061；预算 ≤16 ms ⇒ median-of-medians 13.3 ms ⇒ 在预算内。噪声门通过（噪声在阈值内，判据可判）；对照口径 fromKeyMs 的键内最小值 17.0 ms（仅参考，**不作判据**）；干净键 50 个给出**下界** 19.0 ms（真值，§6.6）。 |
| C10 | 两消费者一致 | ⚪ 未测 | 两消费者一致需同时渲染「预览栏（可编辑）」与「对话栏气泡（只读流式）」并比对块序列；气泡渲染驱动成本高，本次未实现 ⇒ 未测。 |
| C11 | 插头等价 | ⚪ 未测 | **不确定（inconclusive）—— 不作绿/红。** new 已注册（占位，方法抛 NotImplemented） ⇒ 新旧等价对比**尚不可判**；合成坏插头 `__broken`（块数少 2）被正确判红 ⇒ 探针机制有鉴别力。（机制自证不等于 new 等价通过。） |
| C12 | 无损切换 | 🟢 绿 | legacy 往返后 6 项状态（state.doc / currentPath / viewMode / 滚动 / 选区 / KP band）逐项一致；且合成丢状态插头 `__lossy` 被正确判红 ⇒ 探针有鉴别力。 |

## 覆盖率

- 🟢 绿：C2、C3、C4、C7、C9、C1、C12
- 🔴 红：C6
- ⚪ 未测：C5、C8、C11、C10

## 关键原始读数

### C3/C4 打字（受信任输入，同一任务内）
- 目标块 blockIndex=4，srcLine=5，caret→块映射=True
- 打字前 DOM：`这是加粗之前可以打字的一句。这是加粗这是加粗之后也可以打字的一句。`
- 打字后 DOM：`a这是加粗之前可以打字的一句。这是加粗这是加粗之后也可以打字的一句。`（含 'a'=True）
- 打字后真源行：`a这是加粗之前可以打字的一句。**这是加粗**这是加粗之后也可以打字的一句。`（含 'a'=True）

### C6 跳转落点
- 入口：`MemoriaApp.openFile(file,{lineHint}) -> highlightRange -> highlightPreviewRange`
- 目标-头（L=5）→ 首屏首块 [4, 4] ✓
- 目标-中（L=19）→ 首屏首块 [19, 19] ✓
- 目标-尾（L=29）→ 首屏首块 [25, 25] ✗

### C7 切模式锚点
- preview#0  preview top=1  source top=1  scrollTop=26
- split      preview top=1  source top=1  scrollTop=26
- source     preview top=1  source top=1  scrollTop=0
- preview#1  preview top=1  source top=1  scrollTop=26

### C9 性能（协议 v1：逐键 / warmup / 多轮）
- **采集参数**：R=5 轮 × 10 键，warmup=5（丢弃），单键落定超时 1500 ms；输入通道 `CDP Input.dispatchKeyEvent(keyDown+keyUp, text)`
- **样本**：正式 n=50，落定 55，死键 0，落定超时 0
- **主口径 `appendMs`（按键→真源落定，逐键百分位估计）**：min 11.9 ms / median 13.3 ms / p95 15.1 ms / max 15.7 ms
- **离散度**：IQR 0.98 ms ｜ IQR/median 0.074 ｜ p95/median 1.137 ｜ 轮间相对极差 0.061
- **每轮 median**：12.9 ms / 13.7 ms / 13.8 ms / 13.3 ms / 13.1 ms ⇒ **median-of-medians 13.3 ms**（预算 ≤16 ms）
- **对照口径**（不作判据）：`fromKeyMs` median 19.0 ms ｜ **干净键** 50 个 ⇒ 单键成本**下界** 19.0 ms（真值）｜ 键内最小值 17.0 ms
- 口径对账（§6.6 自校验）：cleanMedian 19.0 ms / appendMedian 13.3 ms = **1.429**（期望 ≈1.429）
- **结论**：`green` （噪声在阈值内，判据可判） —— 达标
- 口径契约：[benchmark-measurement-protocol.md](../../../docs/design/benchmark-measurement-protocol.md)

- 页面 `[EDIT]`（>20ms 才打）日志条数：5

## 未能做到的事（如实）

- **C1/C5/C8/C10**：见上表原因；均因 legacy 缺对应概念或驱动成本/入口缺失，未测。
- **C11/C12**：`new` 插头不存在 ⇒ 必然未测。
- **C9 只覆盖「按键→真源」这一半**：契约另一半「滚动 200 次无长任务 > 50 ms」本次未采（需 PerformanceObserver longtask 采样），故 C9 结论仅对按键预算成立。
- **跳转入口**：契约名义 `revealRange(L,L)`；legacy 中该函数为闭包、未导出 ⇒ 本次改调用**等价真实入口** `MemoriaApp.openFile(file,{lineHint:L})`（→ `highlightRange` → `highlightPreviewRange(scroll)`），落点语义一致。
- **C6 用平滑滚动**：`scrollIntoView({behavior:'smooth'})` 是异步动画，读数在 `scrollTop` 稳定后采集。
- **kb 副本**：`tests/probe-kb` 无 `.memoria/`，直接服务会让应用在源目录生成 sidecar/manifest ⇒ 本次将语料整树复制到 `artifacts/_probe_kb/` 由应用自行初始化，**未改动 `tests/probe-kb/**`**。

## 备注（口径；机器可读见 .json 的 `notes`）

- 绿/红按契约判，不按与老实现一致判。
- 未测项已写明原因，未默认成绿。
- C9 只覆盖「按键→真源」半条；滚动长任务半条未采。
- C9 口径 v2：逐键采样（非一次性连发）+ warmup 丢弃 + R 轮 median-of-medians；判绿/红前先过噪声门（键间 IQR/p95、轮间极差、样本量、死键），不过则标「不确定」而非绿/红。
- C9 的「不确定」是**度量状态**而非性能结论：不得据此说达标或退化；处置 = 同机同档位重测。
- 跳转入口用等价真实入口 openFile(file,{lineHint}) 代替闭包 revealRange。
- 语料在 artifacts/_probe_kb 副本上运行，tests/probe-kb 未被改动。
- 观察项（非本次断言）：增量重渲（reRenderBlock→renderRange 换节点 + keepLineMap 跳过 stamp）后，被编辑块节点**瞬时不带** data--src-line，可能影响按该属性定位的入口。
