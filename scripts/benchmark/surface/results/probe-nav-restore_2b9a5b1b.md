# 导航位置记忆探针报告（前进/后退 + 按文件）

> label `nav-restore` ｜ git `2b9a5b1b` ｜ 生成 2026-10-06T08:06:12Z
> 驱动：CDP 真机 Edge + harness（`_harness.py`）；**端到端（应用级集成）**，非单元级。
> 语料：`tests/probe-kb` 的副本 `D:\AAA_Jupyter\Memoria\artifacts\_nav_probe_kb`（源目录未被改动）

## 环境

| 项 | 值 |
|---|---|
| browser | Edg/154.0.4258.53 |
| edge | C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe |
| node | v24.19.0 |
| kbServed | D:\AAA_Jupyter\Memoria\artifacts\_nav_probe_kb |
| kbSource | D:\AAA_Jupyter\Memoria\tests\probe-kb |
| kbSourceHasMemoria | 否（已用副本让应用自初始化） |
| fileA | scale/scale-1k.md |
| fileB | scale/scale-5k.md |
| durationMs | 34886 |
| consoleErrors | 0 |

## 结论

| # | 断言 | 结论 | 读数 |
|---|---|---|---|
| S1a | 后退回到 A 的离开位置（命中 L±1） | 🟢 通过 | A 行数=1000，目标 L=504，离开时锚点=504 ⇒ 后退后首屏首块=[504,504] 顶部=504 |
| S1b | 前进回到 B 的离开位置（命中 L±1） | 🟢 通过 | B 行数=5000，目标 L=2000，离开时锚点=1999 ⇒ 前进后首屏首块=[1999,1999] 顶部=1999 |
| S2a | 同文件：后退 1 次命中 L2 | 🟢 通过 | L1=504 / L2=749 ⇒ 后退#1 首屏首块=[749,749] 顶部=749 |
| S2b | 同文件：后退 2 次命中 L1 | 🟢 通过 | ⇒ 后退#2 首屏首块=[504,504] 顶部=504 |
| S3 | 文件树点开也回原处（命中 L±1） | 🟢 通过 | L=504，锚点=504，选择器 `.-tree-item[data-path="scale/scale-1k.md"]`，点击=True ⇒ 首屏首块=[504,504] 顶部=504 |

- 总判定：**🟢 全部通过**

## 备注（口径）

- 顶栏按钮 / 文件树项走 **CDP 真实鼠标点按**；内容打开走真实入口 `MemoriaApp.openFile`。
- 目标行 L：**从实际已渲染的块中按比例挑（~50% / ~75%）**取该块起始行（保证 L 必被某块覆盖）。因 `scale-*.md` 含 mermaid，首次预览渲染可能被 mermaid/初始化并发挡成半截 ⇒ 运行器先做一次 B→A **预热**并 settle 后再测。
- 「文件树双击」：该树绑定的是 `click`（`.-tree-item`），双击=连续两次 click、行为幂等；本探针用**真实鼠标单击**驱动同一条真实入口。
- 落点读数在初始恢复后 ~2s（越过落点二次校准 350ms/1400ms）稳定时采集；命中判据 = 首屏第一块 `data--src-line..data--src-line-end` 覆盖 L±1。
- S2 用 `openFile(fileA,{kpId})` 在同一文件上进新导航帧（这是 `jumpToTarget` 走的同一条真实入栈路径）。
- 诊断（不改应用行为）：页内对 `MemoriaNavStack.push/clear/navBack/navForward` 做**透传包装**记录调用（`navDiagLog`/`navPushLog`），用于定位早期一次「探针与 `initKb` 竞态」。
- 探针等待口径：`app-ready` 需 `state.files.length>0`（`initKb` 会在其后再 `NavStack.clear()`；过早操作会被清栈——这是探针自身的竞态，不是产品缺陷）。
