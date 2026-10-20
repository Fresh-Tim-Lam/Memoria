# 真机应用度量协议（real-app measurement protocol）

> 状态：**生效中**（2026-10-20）　｜　协议版本：`1`
> 适用：在**真实 Memoria 应用**（pywebview + WebView2，有 GPU、非无头）里量三项性能指标
> 上位口径：[benchmark-measurement-protocol.md](benchmark-measurement-protocol.md)（warmup / 多轮 / 离散度 / 三态判据 —— **本协议沿用同一套判据**，只换测量环境）
> 实现：`scripts/benchmark/surface/realapp_probe.mjs`（attach 验证）、`realapp_measure.mjs`（打点驱动 + 人工模式）
> 报告：`artifacts/agent/verify/realapp-measure-report.md`

---

## 1. 为什么要有这份协议（无头探针的有效性问题）

既有 surface 探针跑在 **无头 Edge + Python harness** 上。它能复现、能自动化，但与人的真实体验有系统性差距：

| 差距 | 无头 | 真机 |
|---|---|---|
| GPU | `--disable-gpu`，SwiftShader 软光栅 | NVIDIA + Direct3D11（实测 `ANGLE (NVIDIA, NVIDIA GeForce RTX 5060 Ti …)`） |
| 窗口/合成 | 无真实窗口、无 DWM 合成 | 真实窗口、有 DWM 合成与真实 vsync |
| 输入 | CDP 合成（`isTrusted=true`，但非 OS 输入栈） | 同一 CDP 通道 **或** 真人键盘 |
| 公式排版 | **实测排不完**（`mjx-container` ≈ 3，宽限耗尽也等不到） | **实测排得完**（270 个 `mjx-container`，~1.2–1.5 s） |

> 结论：**无头读数不能直接代表人的体验**，尤其「首开→公式可读」这类含排版/合成的指标。
> 本协议把度量搬进真机应用，并且**让读数与输入来源无关**（§3）。

---

## 2. 怎么启动被测量的应用（先决条件）

只在**已经装好依赖、有桌面会话**的机器上做。三件事缺一不可：

### 2.1 打开 WebView2 的远程调试端口

```powershell
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = '--remote-debugging-port=9500'
```

> 这条是 **WebView2 官方支持的启动开关**：它把参数透传给内核 ⇒ 内核在本机 `127.0.0.1:9500` 上
> 暴露 CDP（`/json/version`、`/json/list`）。**不需要改 `src/**`**。
> 端口可换（建议 9500–9599，避开 9222 以免与无头探针冲突）。

### 2.2 指定要测量的知识库

```powershell
$env:MEMORIA_KB = 'D:\AAA_Jupyter\Memoria\tests\probe-kb'
$env:MEMORIA_MODE = 'dev'      # 开发态（默认开 DevTools；也便于确认窗口）
$env:MEMORIA_FRAMELESS = '0'   # 有系统标题栏，人工操作时更好定位窗口
```

### 2.3 启动应用

```powershell
python -m memoria.app.desktop
```

### 2.4 确认 CDP 通了

```powershell
node scripts/benchmark/surface/realapp_probe.mjs --port 9500
```

期望输出（节选）：

```jsonc
{ "cdpWorks": true,
  "target": { "title": "Memoria v0.4.3", "url": "http://127.0.0.1:36515/" },
  "appReady": true,
  "state": { "kbPath": "...\\tests\\probe-kb", "currentPath": "README.md", "viewMode": "source", "docLines": 45 },
  "gpu": { "webgl": true, "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 5060 Ti …, D3D11)" } }
```

**`gpu.webgl` 必须为 `true`** —— 这是「这是真机、不是软光栅」的凭证；为 `false` 说明跑错了环境，读数作废。

### 2.5 已知的四个坑（启动阶段）

| # | 坑 | 现象 | 处置 |
|---|---|---|---|
| ① | 应用默认是**源码视图** | `#preview` 为空、`blocks=0` | 必须先切预览（脚本里 `ensurePreviewView`） |
| ② | 打开文件后视图被**按文件视图偏好**复位 | 刚切好预览，一开文件又回源码 | 每次打开后再确保一次 |
| ③ | 启动期**异步自动打开默认文件**并恢复上次视图 | 刚 attach 时 `currentPath` 会变 | 等 `currentPath` 稳定 + `state.doc` 已加载（`waitAppReady`） |
| ④ | `/json/list` 里混着 **DevTools 自己的页面** | 按 `type=page` 取第一个可能拿到 devtools:// | 必须按 URL 过滤掉 `devtools://` 与 `about:blank` |

---

## 3. 三项指标的定义（读数与输入来源无关）

**全部时间戳用页面内 `performance.now()`**，埋点在页面里（`window.__ram`）。脚本只在**事件前后**发指令，
**不把 CDP 往返 / 轮询间隔**算进读数 —— 这是「脚本读数」与「人工读数」能直接比较的前提。

| 指标 | 字段 | 起点 | 终点（完成判据） | 预算 |
|---|---|---|---|---|
| **A** 按键→真源 | `key_to_source_ms` | 页面 `beforeinput`（本键到达） | `MemoriaEditSync.insertText` **返回**（真源已更新） | **16 ms** |
| **B** 首开→可见 | `open_render_ms` | `openFile` 调用那一刻（页面内） | 块 ≥5 **且** 不在 loading **且** `currentPath` 已是目标文件 **且** **公式排版队列已清空** **且** 再连续 3 次采样（每 60 ms）块数/公式数都不变 | **3000 ms** |
| **C** 切页签 | `tab_switch_ms` | 开始 A→B→A 的那次「打开 A」 | 与 B 同构（回到 A 后可预览可用） | **800 ms** |

### 3.1 指标 B/C 的完成判据为什么这么绕（**必须按这个来，否则读数全是假的**）

实测（真机，`scale/scale-5k.md` = **3111 块 / 270 个公式**）踩过两次假完成：

1. **旧块冒充新块**：`t≈0.1–0.3 ms` 时 `#preview` 里还有**上一份文档的旧块（实测 16 个）**，
   若只判 `blocks >= minBlocks` ⇒ 立刻"完成"，读数 0.1 ms。**必须等 `currentPath` 变成目标文件**。
2. **公式没排完就报完成**：块数早已稳定（3111），但公式还在排。探测 `MathJax.startup.document.state()`
   在 v3 SVG 输出下**恒不返回 ready**（实测不可用）。
   ⇒ 唯一可靠信号是应用自己的 `state._mathPending`（`app.js` 的 `queuePreviewMathTypeset` 把每轮排版串到这个 Promise 上）：
   **该 Promise 已 settle = 排版真的做完了**。

> 判据顺序（脚本已实现，人工也照此理解）：`currentPath 正确` → `blocks≥N 且非 loading` →
> `state._mathPending 已 settle` → `块数/公式数连续 3 次不变`。

### 3.2 指标 A 的度量位置

与既有 C9 口径一致：包 `MemoriaEditSync.insertText`，记 `beforeinput 到达 → insertText 返回`。
`insertMs`（仅 insertText 本身）同时报出，作对照。

---

## 4. 判据（三态，沿用上位协议 §6）

```
① 噪声门：n ≥ 5；IQR/median ≤ 0.25；p95/median ≤ 1.60   —— 任一不过 ⇒ gray（inconclusive）
② 预算判：中位（多轮的 median-of-medians） ≤ 预算        —— 通过 ⇒ green / 否则 red
```

**`gray` 是「本次测量无效」，不是「通过」也不是「失败」**；处置 = 重测（同机、关掉后台负载、别边跑边切别的应用）。

---

## 5. 人工兜底 SOP（**给不做技术的操作者**，照做即可）

> 目的：当脚本驱动拿不到数（或想独立验证脚本读数）时，由人照此操作，最后**读一个表**。
> 全程只需要「按顺序点、按顺序敲、最后跑一条命令」。

### 准备（每次开始都做）

1. **关掉所有不相干的程序**（尤其浏览器大页、视频、下载、杀毒全盘扫描、Teams/会议）。
2. 插好电源（**不要用电池**），别开省电模式。
3. 按 §2 启动应用（可以让技术同学帮你把三条环境变量设好并启动）。
4. 让应用窗口**最大化**，别去动它的大小。
5. 告诉技术同学「我要开始人工测量了」⇒ 他会运行：
   ```
   node scripts/benchmark/surface/realapp_measure.mjs --port 9500 --driver manual --stage all
   ```
   看到 `埋点已武装` 字样后才继续。**脚本不会替你操作，全靠你手动。**

### 步骤 1：确认在「预览」视图

- 看应用右上角的视图按钮，点 **「预览」**。
- **合格标志**：中间区域显示的是**排版好的文章**（不是源码文本）。

### 步骤 2：量「首开」（指标 B）

1. 在左侧文件树里点开 **`corpus/01-ime-zh.md`**（随便一份小文件，只为切走），等它显示出来。
2. 再点开 **`scale/scale-5k.md`**（大文件）。
3. **从你点下去的那一刻开始，到文章和所有公式都"不再跳动"为止** —— 脚本在后台自动记时，你不用掐表。
4. 重复 **5 次**（点走 → 点回，算一次）。
   > 每次都要等上一次**完全静止**再点下一次（大约 1–2 秒），不要连点。

### 步骤 3：量「按键」（指标 A）

1. 确保当前是 `scale/scale-5k.md`、且是**预览**视图。
2. 用鼠标**点一下正文里的任意一段文字**（把光标放进去）。若没反应，双击进入编辑态。
   > **合格标志**：能看到光标在文字里闪。
3. 然后**正常速度敲字**：连续敲 **50 个字母 `z`**（不用快，就日常打字速度）。
4. 再重复上面「点进正文 → 敲 50 个 z」**共 4 次**（合计 5 轮）。
   > 敲完不用管，脚本自己记录每一键。

### 步骤 4：量「切页签」（指标 C）

1. 在文件树点 **`corpus/01-ime-zh.md`**，等它显示完。
2. 点 **`scale/scale-5k.md`** 回到大文件。
3. 等它**完全静止**（公式不再跳）。
4. 重复第 1–3 步 **5 次**。

### 步骤 5：读表（唯一需要"看数字"的一步）

告诉技术同学「做完了」⇒ 他运行：

```
node scripts/benchmark/surface/realapp_measure.mjs --port 9500 --driver manual --read
```

输出里三个数（**只看这三个**，单位毫秒）：

| 看哪个字段 | 含义 | 合格线 |
|---|---|---|
| `stages.read.key.arriveToReturn.median` | 敲一个字到文字真正进去 | **≤ 16** |
| `stages.read.open.totalMs` | 点开大文件到公式排完 | **≤ 3000** |
| `stages.read.tab.totalMs` | 从别处切回大文件到能看 | **≤ 800** |

> 若 `n`（样本数）小于 5 ⇒ 视为**没测成**，重来一遍，不要说"合格"。

### 步骤 6：记录

把三个数抄进 §6 的表（或直接截图给技术同学）。**记录形如 `26.5 / 1434 / 1292`**。

---

## 6. 记录表模板

| 日期 | 机器 / GPU | 文件 | B 首开(ms) ×5 | A 按键(ms) ×5/轮 | C 切页签(ms) ×5 | 操作者 |
|---|---|---|---|---|---|---|
|  |  | scale-5k (3111 块 / 270 公式) |  |  |  |  |

---

## 7. 偏差校验方法（脚本驱动 vs 人手操作）

**目的**：证明「脚本读数」没有系统性偏离真实体验。这是本协议作为「科学可靠」度量的一部分，不是可选项。

### 7.1 协议

1. **同一指标、同一台机器、同一天**，两种输入源各测一次：
   - `--driver auto`：脚本用 CDP `Input` 域派发（受信任事件）；
   - `--driver manual`：真人操作，脚本**只记录不驱动**。
2. 两种模式**测的是同一段页面内代码**（`beforeinput → insertText 返回` / 同一套完成判据），
   所以差值只来自**输入通道 + 人为时序**，可以直接比较。
3. **偏差定义**：
   ```
   bias_i = (manual_i − auto_i) / auto_i        # 带符号的相对偏差
   |bias| ≤ 0.15  → 一致（脚本读数可代表人工）
   0.15 < |bias| ≤ 0.50 → 有可解释差异（必须在报告里写清原因）
   |bias| > 0.50 → 不可比（说明两条路径已经不是同一个阶段，须定位）
   ```
4. **样本量**：每项 ≥5 个读数，比较各自**中位数**（不比较单个值）。
5. **结论写进报告**：`artifacts/agent/verify/realapp-measure-report.md` 的对照表，**偏差必须逐个列出**。

### 7.2 已知会产生的偏差来源（预期内，报告需说明）

| 来源 | 影响方向 | 量级（估计） |
|---|---|---|
| 人打字会有思考/停顿 | 只影响 A 的**到达间隔**，不影响 `beforeinput→返回` 的差 | ≈0 |
| 人点击/切文件比脚本慢 | 不影响页面内计时（起点也在页面内） | ≈0 |
| 人手操作时其它窗口被激活 | 可能触发一次额外重绘 | 偏高 |
| 脚本连续无间隔操作 | 可能命中缓存/连续重渲优化 | 偏低 |
| **预热程度不同** | 脚本有 5 键 warmup；人没有（但人前几次敲也会自然预热） | 人偏高 |

---

## 8. 可复现性边界（如实）

| # | 边界 | 说明 |
|---|---|---|
| R1 | **只有 Windows + WebView2** | 协议依赖 `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS`；其它壳（PyQt6）不适用 |
| R2 | **`--remote-debugging-port` 开着就有风险** | 同机任意进程都能 attach 并执行页面 JS ⇒ **只在测量时开，测完关掉应用** |
| R3 | 读数绑定机器与文档规模 | 引用必须带 GPU 型号 + 行数/块数（本协议默认 `scale-5k.md` = 3111 块 / 270 公式） |
| R4 | 窗口尺寸影响布局耗时 | 默认 1264×821（实测）；改窗口大小后读数不可与默认比 |
| R5 | 服务器端口每次随机 | `http://127.0.0.1:<随机>/` 是应用自己的静态服务端口，**不代表** CDP 端口 |
| R6 | 人工模式依赖操作者纪律 | 连点/边做边切窗口会污染样本 | 

---

## 9. 与其它文档的关系

| 文档 | 关系 |
|---|---|
| [benchmark-measurement-protocol.md](benchmark-measurement-protocol.md) | **上位口径**：warmup/多轮/离散度/三态判据。本协议是它在「真机环境」下的特化 |
| [view-surface-contract.md](view-surface-contract.md) §3.3 / §5 C9 | 预算来源（按键→真源 ≤16 ms） |
| `scripts/benchmark/surface/cdp.mjs` | 无头探针（保留，用于**快速回归**；代表不了真机体验，见 §1） |
| `scripts/benchmark/surface/interaction.mjs` | 交互原语来源（Input 域、修饰键、IME） |

---

## 10. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-20 | 1 | 初版：真机启动（`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS`）、三项指标定义、**B/C 完成判据的两个假完成陷阱**（旧块冒充 + 公式未排完）、人工 SOP（6 步）、偏差校验公式与阈值、可复现性边界 |
