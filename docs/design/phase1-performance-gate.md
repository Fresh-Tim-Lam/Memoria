# 阶段 1 性能闸 · 判定契约与执行流程（G1–G5）

> 状态：**生效中**（2026-10-20）　｜　执行者：`metrics-agent`
> 触发：**task-19（清 148 次空操作）＋ P2（BlockIndex.upsert 接入）落地后**执行最终判定
> 上位口径：[benchmark-measurement-protocol.md](benchmark-measurement-protocol.md)（warmup / 多轮 / 离散度 / 三态）
> 　　　　　[realapp-measurement-protocol.md](realapp-measurement-protocol.md)（真机 attach + 页面内打点）
> 证据（gitignored，只作本文件的引用底稿）：
> 　基线 `artifacts/agent/verify/typing-dom-write-baseline.md`
> 　执行底稿 `artifacts/agent/verify/phase1-performance-gate.md`
> 　脚本 `scripts/benchmark/surface/realapp_domwrites.mjs` ＋ `dom_write_counter.mjs`

---

## 0. 闸门目标（Lead 已定）

> **阶段 1 后打字不得变慢。**

两个数字**必须分开报、分开判**：

| | 判据 | 性质 |
|---|---|---|
| **G1** | 相对新基线 **≤ 1.15×** | **「不退步」**——不要求做到目标，只要求别更差 |
| **G1'** | 绝对 **≤ 16 ms** | **「该做到」**——契约 §3.3 / C9 的目标值 |

> 混淆这两者会导致两种错误结论：拿 16 ms 当"退步判据"⇒ 阶段 1 明明没退步也判失败；
> 拿 1.15× 当"目标"⇒ 明明离契约还差很远也宣布达标。

---

## 1. **首条规则：读写指标与时延必须同看**（比 G3 更强）

> ### R0：`upsert()` 的 DOM 写是**幂等**的 ⇒ **M1 正常也可能是病。**

依据（读码，`src/memoria/ui/static/app/js/block-index.js:262-274`）：

```js
if (_el.getAttribute("data-block-id")      !== handle.id)  _el.setAttribute("data-block-id", handle.id);
if (_el.getAttribute("data--src-line")     !== _start)     _el.setAttribute("data--src-line", _start);
if (_el.getAttribute("data--src-line-end") !== _end)       _el.setAttribute("data--src-line-end", _end);
```

**先读后写**：值没变就**不写**。由此推出两条反直觉结论：

1. **全量重扫（每键遍历 3110 块）时，M1 几乎不涨**——因为所有值都没变、全部被幂等跳过；
   但 CPU 照烧、**时延会暴涨**。⇒ **只看 M1 会把灾难判成"没问题"。**
2. **多余写（写重复值）时，M1 会涨，但时延几乎不变**——浏览器处理极快。
   ⇒ **只看时延会把浪费判成"没问题"。**

**⇒ 任何单一指标都不足以下结论。M1/M2 与时延必须成对判定。**

### 1.1 判定矩阵（**先查此矩阵，再看 G1–G5**）

| # | M1 | M2 attributes | 时延 | 判定 | 处置 |
|---|---|---|---|---|---|
| **P** | 低（≈3–6） | 正常（2–6） | 正常（≤1.15×） | **PASS** | 放行 |
| **A** | 低（≈3–6） | 正常 | **涨（>1.15×）** | **FAIL · 全量重扫嫌疑** | 查 `upsert()` 每键调用次数：若是「每键遍历全部块」⇒ 设计错误，回退到「只 upsert 被编辑块」 |
| **B** | **高** | **低** | 正常 | **WARN · 冗余写** | 记录并在 G4 归因；若写点可合并则建议优化，**不阻断** |
| **C** | **高** | **高** | 正常/涨 | **FAIL · 结构性写** | 查 `innerHTML` / 节点替换（M1 hook 看不见的那类），以及是否与 `stampBlockLines` 重复写同一属性 |
| **D** | 低 | 高 | 涨 | FAIL | 结构性写 + 全量重扫叠加，按 A、C 两条同时查 |
| **E** | 任意 | 任意 | 噪声门不过 | **不确定** | 重测（见 §4），不得给 PASS/FAIL |

> 矩阵中的「高/低」以 §6 的分档表为准；「正常」= 未超过 G1/G2 阈值。

---

## 2. 判据全文（G1–G5）

| # | 判据 | 通过条件 | 不通过时 |
|---|---|---|---|
| **G1** | **时延不劣化**（相对**新**基线） | 见 §2.1 的双条件 | FAIL：时延回归 |
| **G1'** | **绝对目标** | median ≤ **16 ms** | 单独记为「超预算」，**不与 G1 混判** |
| **G2** | **M2 attributes 不显著涨** | 每键 attributes ≤ 新基线 + 预期新增 × 1.2 | FAIL：DOM 代价上涨 |
| **G3** | **M1 只作解释，不作否决** | — | 不单独判 FAIL；须在 §5 归因表解释（但见 **R0**：M1 正常也不代表没问题） |
| **G4** | **M1/M2 增长必须归因到具体写点** | 每个增长项都有「函数 + 属性名 + 次数」 | 无法归因 ⇒ 判「不可归因」⇒ 闸门 **不确定** |
| **G5** | **时延必须以分布报** | 报 **min / median / p95** ＋ 每轮 median 全部列出 | 只给点估计的报告 **不合格**，不予采纳 |

### 2.1 G1 的双重 FAIL 条件（Lead 裁决，防单轮不稳定被中位掩盖）

```
FAIL  ⇐  新 median > 1.15 × 基线 median
       或  任一单轮 median > 1.3 × 基线 median        ← 加严条
PASS  ⇐  两条都不触发
```

**为什么要有第二条**：中位数能吸收个别轮次的抖动，但也可能**掩盖"某一轮整体变慢"**。
若某一轮 median 超过基线的 1.3×，说明该轮机器状态异常或存在周期性卡顿（GC/后台任务/重扫），
**即便中位看起来正常也必须判 FAIL 并归因**——那正是用户会感知到的"偶发卡顿"。

### 2.2 为什么 G1 的基准要**换**（不是用本文 §7 的旧基线）

task-19 会删掉**每键 148 次空操作**（`app.js` 的 `_updateAtomicSelectionHighlight` 每帧遍历全部 `.-math`）。
这同时改变：M1（151 → ≈3）与**机器状态**（少 148 次函数调用 + 属性读写 ⇒ 时延分布本身会变）。

⇒ **旧基线的 1.15× 参照失去意义**，必须在 task-19 之后**重取**（§4.1），同机、同日、同文档。

---

## 3. 统计量与取数规则（G5 的具体化）

一次「测量」= 一个版本的一个数据点：

```
轮数 R = 5     每轮 keysPerRound = 10      warmup = 5（丢弃）
⇒ 每版本 50 个正式键样本
```

**每版本跑 ≥ 3 次独立运行**（不同进程/冷启动），点估计 = **3 次运行 median 的中位**。

**必须报的量**：

| 量 | 用途 |
|---|---|
| `min` | 最好情况（有噪声时看下限是否变差） |
| **`median`** | **G1 / G1' 判定** |
| `p95` | 尾部（卡顿感）；G2 也看 |
| `max` | 只记录，不判 |
| **每轮 median 全部列出（3 次运行 × 5 轮 = 15 个值）** | G1 加严条 + 轮间漂移 |
| `IQR/median` | 噪声门（>0.25 ⇒ 本次无效） |

> **只给一个点估计 = 不合格报告**（G5）。必须同时给出 15 个轮次 median 与 p95。

---

## 4. 执行流程

### 4.0 前置：启动真机应用

```powershell
$env:MEMORIA_MODE='dev'; $env:MEMORIA_FRAMELESS='0'
$env:MEMORIA_KB='D:\AAA_Jupyter\Memoria\tests\probe-kb'
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS='--remote-debugging-port=9500'
python -m memoria.app.desktop
```

环境要求（缺一项则读数不可与基线比）：同一台机器；接电源、非省电；关闭其它重负载；
窗口保持默认（实测 1264×821）；**每次改代码必须重启应用**（前端资源带 `?v=` 缓存）。

### 4.1 取新基线（task-19 之后、P2 之前）

```powershell
1..3 | ForEach-Object {
  node scripts\benchmark\surface\realapp_domwrites.mjs --port 9500 `
       --file-a scale\scale-5k.md --rounds 5 --keys 10 --warmup-keys 5 `
       --out "scripts\benchmark\surface\results\raw-domwrites-post19-run$_.json"
}
```

**新基线验收**（任一不满足 ⇒ 不能当基准）：
- 3 次运行 M1 **必须一致**（写入计数是确定的，IQR 应为 0）；
- **M1 应从 151 降到 ≈3**（仍 ≈151 ⇒ task-19 未生效，**停工排查**，不要继续）；
- 每轮 `truncated = 0`；
- 3 次运行 median 相对极差 < 1.15（否则环境不稳，重测）。

### 4.2 取 P2 后读数

同机、同日、同 KB、同文档，重复 §4.1，输出改到 `raw-domwrites-p2-run{1..3}.json`。

### 4.3 判定

```
① 过噪声门（§4.4）—— 不过 ⇒ 不确定，重测，结束
② 查判定矩阵（§1.1）—— 定出候选处置
③ 逐条判 G1（双条件）→ G1'（独立）→ G2 → G4 归因
④ 填 §5 判定表，给 PASS / FAIL / 不确定
```

### 4.4 噪声门（先证明"这次测量算不算数"）

| 检查 | 阈值 |
|---|---|
| 每轮样本数 | = 10（不许丢键） |
| `truncated` 键数 | = 0 |
| 单次运行内 `IQR/median` | ≤ 0.25 |
| 单次运行内 `roundSpread` | ≤ 0.20 |
| 3 次运行 median 相对极差 | < 1.15 |
| 环境取证 | GPU renderer / viewport / 文档行数·块数·公式数与基线一致 |

---

## 5. G4 归因方法（涨了必须说清涨在哪）

### 5.1 先用计数器自带的逐键细分

`raw-domwrites-*.json` 每个键都有：`setAttribute / removeAttribute / classAdd / classRemove / classToggle / styleSet`
与 M2 的 `m2.attr / m2.childList / m2.characterData`。先定位是**哪一类**涨。

### 5.2 需要具体到「函数 + 属性」时：临时加 call-site 归因

```js
// 页面内临时 patch（跑完即卸；不放进交付脚本）
const EP = Element.prototype, orig = EP.setAttribute;
const tally = {};
EP.setAttribute = function (n, v) {
  const el = this;
  const key = `${el.tagName}${el.id ? '#' + el.id : ''}@${n}`;
  tally[key] = (tally[key] || 0) + 1;
  return orig.apply(this, arguments);
};
// 跑一组按键后读 window.__tally
```

**归因表（判定时必填）**：

| 增长项 | 元素 | 属性/类名 | 每键次数 | 来源函数（栈首帧 `file:line`） |
|---|---|---|---|---|
| 例：`classToggle` +3 | `.-src-block` | `-sel-covered` | 3 | `app.js:_updateAtomicSelectionHighlight` |

> 本仓定位"每键 148 次空操作"就是靠这个方法（`toggle("-sel-covered")` ×1485 / 10 键 ≈ 148）。
> **没有这张表 ⇒ G4 不过 ⇒ 闸门判"不确定"，不能放行。**

---

## 6. M1 分档表（读矩阵 §1.1 时的"高/低"以此为准）

**基线实测构成**（从 raw 逐键分解，非估算）：M1 = 151 = `classToggle("-sel-covered")` **148** + `setAttribute` 1 + `classRemove` 2。
⇒ task-19 清掉那 148 次后，**残余 M1 = 3**（区间 3–6），这就是新基线的落点。

| 档位 | 每键 M1 | 含义 |
|---|---|---|
| **低** | **3 – 6** | 正常（形态 A：只 upsert 被编辑块，行数不变） |
| 正常上限 | **≤ 12** | 可接受（容忍 `data-block-id` 首次写入 + 一条辅助属性） |
| **高** | **> 20** | **必须解释**；查矩阵 B/C |
| 设计问题 | **> 50** | 大概率是全块回写 ⇒ 判 FAIL |

**每键 upsert 调用次数的三种形态**（决定数量级的唯一变量）：

| 形态 | 每键 upsert 数 | 预期 M1 | 备注 |
|---|---|---|---|
| **A 单块**（只 upsert 被编辑块） | 1 | 3–6 | **正确设计**（打字行数不变） |
| **B 小范围平移**（Enter 拆行等） | 1 + k | 3–15 | 行数变化才触发，可接受 |
| **C 全量重扫**（每键遍历全部块） | 3110 | **≈3（幂等跳过！）** | **最危险**：M1 正常但时延暴涨 ⇒ 命中矩阵 **A** |

**M2 attributes 合理区间：2 – 6**（现有 2 + `upsert` 实际产生 0–3 条变更记录；幂等时可能仍是 2）。

> **必须核对**：`data--src-line` 是否被写了两遍（旧 `stampBlockLines` + `upsert`）。
> 若 P2 后 attributes 从 2 涨到 5–6 且**每个键**都涨 ⇒ 两套写都在跑，应合并。

---

## 7. 判定表（执行时填）

| 项 | 新基线（task-19 后，3 次） | P2 后（3 次） | 比值/差值 | 判定 |
|---|---|---|---|---|
| M1（每键，3 次是否一致） | | | | 查矩阵 |
| M2 records | | | | 参考 |
| **M2 attributes** | | | | **G2** |
| **时延 min** | | | | G5 |
| **时延 median（点估计）** | | | ≤1.15× | **G1 条件①** |
| **15 个轮次 median 的最大值** | | | ≤1.3× | **G1 条件②** |
| **时延 p95** | | | | G5 |
| 是否 ≤16 ms | — | | | **G1'（独立报）** |
| **判定矩阵命中项** | — | | | P / A / B / C / D / E |
| **总判定** | — | | | **PASS / FAIL / 不确定** |

**总判定规则**：

```
噪声门不过                        ⇒ 不确定
G1 任一条件触发                   ⇒ FAIL（时延回归；若 M1 正常 ⇒ 全量重扫嫌疑）
G2 不过                          ⇒ FAIL（DOM 代价上涨）
G4 无法完成归因                   ⇒ 不确定（增量无法解释，不能放行）
其余                              ⇒ PASS（另按 G1' 单独报是否达 16 ms 目标）
```

---

## 8. 边界情况

| 情况 | 处置 |
|---|---|
| task-19 后 M1 仍 ≈151 | task-19 未生效 ⇒ **停工**排查 |
| P2 后时延涨但 M1/M2 没变 | 归因到 CPU（重扫/重建）而非 DOM ⇒ 矩阵 **A**；G4 需给**非 DOM 归因** |
| P2 后 M1 涨但时延正常 | 矩阵 **B**（冗余写）⇒ 记录 + 归因，不阻断 |
| 三次运行波动 > 1.15× | 环境不稳 ⇒ 重测；连续两次不稳 ⇒ 判「不确定」并记录环境 |
| 应用版本/文档规模与基线不符 | 读数不可比 ⇒ 重建基线 |
| 怀疑跑的是旧前端 | 每次改代码**重启应用**；必要时核 `MemoriaBlockIndex` 的 `globalPresent` |

---

## 9. 执行产物

- 判定结果：`artifacts/agent/verify/phase1-performance-gate-result.md`（判定表 + 归因表 + 3 次运行 raw 路径）
- raw：`scripts/benchmark/surface/results/raw-domwrites-{post19,p2}-run{1,2,3}.json`

---

## 10. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-20 | 初版。**R0 首条规则**（幂等写 ⇒ M1 正常也可能是病）+ 判定矩阵；G1 加严为双条件（中位 + 单轮）；G1'/G1 分离；G4 归因表；G5 分布报；M1 分档表（3–6 / ≤12 / >20 / >50）与形态 A/B/C |
