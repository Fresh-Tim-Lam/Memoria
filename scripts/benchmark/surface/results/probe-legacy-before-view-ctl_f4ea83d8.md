# 显示子系统探针报告 · legacy 契约基线

> 插头 `legacy` ｜ label `before-view-ctl` ｜ git `f4ea83d8` ｜ 生成 2026-10-03T17:10:56Z
> 契约：[view-surface-contract.md §5](../../../docs/design/view-surface-contract.md)
> 语料：`tests/probe-kb/`（cases.json + corpus + scale）

## 环境与口径

| 项 | 值 |
|---|---|
| browser | Edg/154.0.4258.37 |
| edge | C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe |
| node | v24.19.0 |
| kbServed | D:\AAA_Jupyter\Memoria\artifacts\_probe_kb |
| kbSource | D:\AAA_Jupyter\Memoria\tests\probe-kb |
| kbSourceHasMemoria | 否（已用副本让应用自初始化） |
| casesFile | tests/probe-kb/cases/cases.json |
| scaleDoc | tests/probe-kb/scale/scale-5k.md |
| scaleDocLines | 5000 |
| appReady | True |
| runDurationMs | 10194 |

- **绿/红按契约判**（真源文本 + 行为契约），不按「与老实现一致」判。
- **性能读数绑定文档规模**：本运行 C9 用 `scale/scale-5k.md`，其真实行数见下表（**不等于**契约基准文档的 5900 行，读数须与档位一起引用）。
- **未测的 C 一律标「未测」并写明原因**，不默认成绿。
- 打字一律走 CDP `Input.dispatchKeyEvent`（受信任输入），非 `el.value=` 伪造。

## 复现

```powershell
node scripts\benchmark\surface\cdp.mjs --selftest
python scripts\benchmark\surface\run_probe.py --kb tests\probe-kb --label before-view-ctl
```

## C1–C12 逐条结论

| # | 断言 | 结论 | 读数 / 原因 |
|---|---|---|---|
| C1 | 块 id 稳定 | ⚪ 未测 | legacy 无 RenderCore「块 id」概念（`data--block-index` 是**位置下标**、随块序重编，非稳定 id）⇒ 契约 C1 在 legacy 无对应实现，无法测。 |
| C2 | 文本保真 | 🟢 绿 | 打开 01-ime-zh.md 不编辑：state.doc.body 逐字等于 磁盘文件（len body=485 / disk=485） |
| C3 | 打字当帧可见 | 🟢 绿 | 受信任输入 keyDown(text='a') 后**不等 rAF** 立刻读 DOM：块文本 已含 'a' |
| C4 | 真源不落后 | 🟢 绿 | 同一次按键后立刻读真源：state.doc.lines[L] 已含字符；caret→块映射 正确（行号取自编辑前捕获：增量重渲后新块节点不带 data--src-line） |
| C5 | 冻结不破 | ⚪ 未测 | 需「块编辑中（textarea 在文档内）+ 触发块级重渲」两步：双击进块编辑可用，但驱动块级重渲需要一个**未暴露的应用入口**；本次未实现 ⇒ 未测。 |
| C6 | 落点准确 | 🔴 红 | 目标-头 L=5 首屏块=[5,5] ✓；目标-中 L=19 首屏块=[18,18] ✓；目标-尾 L=29 首屏块=[26,26] ✗（文档末尾滚动钳制：目标块[29,29]已渲染且可见，但无法置顶） |
| C7 | 切模式不漂 | 🔴 红 | 锚点行 preview#0=7 → preview#1=4，Δ=3（≤1 判绿） |
| C8 | 交互存活 | ⚪ 未测 | 需断言 onLinkActivate 回调、图片双击进编辑、KP band 定位三件交互存活；回调断言需在页面侧挂测试钩子，本次未实现 ⇒ 未测。 |
| C9 | 性能预算 | 🔴 红 | 文档 scale-5k.md（5000 行）键入 30 字：按键→真源 median=17.1 ms / p95=20.9 ms / max=26.2 ms（预算 ≤16 ms） |
| C10 | 两消费者一致 | ⚪ 未测 | 两消费者一致需同时渲染「预览栏（可编辑）」与「对话栏气泡（只读流式）」并比对块序列；气泡渲染驱动成本高，本次未实现 ⇒ 未测。 |
| C11 | 插头等价 | ⚪ 未测 | `new` 插头尚不存在（契约 §4 双插头未施工）⇒ 无法跑 legacy vs new 等价对比。 |
| C12 | 无损切换 | ⚪ 未测 | `SurfaceRegistry.switchTo('new')` 不存在（`new` 插头未施工）⇒ 无损切换无法测。 |

## 覆盖率

- 🟢 绿：C2、C3、C4
- 🔴 红：C6、C7、C9
- ⚪ 未测：C1、C5、C8、C10、C11、C12

## 关键原始读数

### C3/C4 打字（受信任输入，同一任务内）
- 目标块 blockIndex=4，srcLine=5，caret→块映射=True
- 打字前 DOM：`这是加粗之前可以打字的一句。这是加粗这是加粗之后也可以打字的一句。`
- 打字后 DOM：`a这是加粗之前可以打字的一句。这是加粗这是加粗之后也可以打字的一句。`（含 'a'=True）
- 打字后真源行：`a这是加粗之前可以打字的一句。**这是加粗**这是加粗之后也可以打字的一句。`（含 'a'=True）

### C6 跳转落点
- 入口：`MemoriaApp.openFile(file,{lineHint}) -> highlightRange -> highlightPreviewRange`
- 目标-头（L=5）→ 首屏首块 [5, 5] ✓
- 目标-中（L=19）→ 首屏首块 [18, 18] ✓
- 目标-尾（L=29）→ 首屏首块 [26, 26] ✗

### C7 切模式锚点
- preview#0  preview top=7  source top=1  scrollTop=473
- split      preview top=5  source top=6  scrollTop=757
- source     preview top=1  source top=5  scrollTop=0
- preview#1  preview top=4  source top=1  scrollTop=345

### C9 性能（scale-5k.md，5000 行；键 30 个）
- 按键→真源(ms)：median=17.1 p95=20.9 max=26.2 min=3.5 n=31
- 仅 insertText(ms)：median=16.5 p95=20.3 max=25.7
- 页面 `[EDIT]`（>20ms 才打）日志条数：2

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
- C9 读数有运行间波动（同机同档多次实测落在 budget 之上；引用须连同档位/运行环境一起）。
- 跳转入口用等价真实入口 openFile(file,{lineHint}) 代替闭包 revealRange。
- 语料在 artifacts/_probe_kb 副本上运行，tests/probe-kb 未被改动。
- 观察项（非本次断言）：增量重渲（reRenderBlock→renderRange 换节点 + keepLineMap 跳过 stamp）后，被编辑块节点**瞬时不带** data--src-line，可能影响按该属性定位的入口。
