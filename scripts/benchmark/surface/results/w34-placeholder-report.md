# W3.4 占位高度估值准确性 —— 实测证据与结论

- 仓库：`D:\AAA_Jupyter\Memoria`；分支 HEAD：`7ef27bb0`（占位校准本身在 `bbab57ed`）
- 被测文档：`教材/08_第8章_差错控制编码.md`（4001 块：blank 1889 / paragraph 1398 / math 567 / image 53 / heading 42 / table 33 / mermaid 19）
- 窗口：1256×774、dpr=1、无头 Edge 155（同一页内先全量、再惰性；同一缩放）
- 测量可信门：空转 rAF p50=16.65 ms ≤20 ms ⇒ 可信

## 1. 整篇高度：+3.41% → **+1.04%**

| 版本 | 全量真值 | 惰性占位 | 偏差 | 备注 |
|---|---:|---:|---:|---|
| 旧（`9feb84ab`） | 175,616 px | 181,601 px | **+3.41%** | 两头错抵消：段落 −49.7%、公式 +83%、图片 +744% |
| 新（`7ef27bb0`） | 175,616 px | 177,441 px | **+1.04%** | 逐类型全部收敛（见下表） |

复跑：

```powershell
python scripts/benchmark/surface/run_placeholder_probe.py --label w34-head
```

证据：`results/placeholder-w34-head_7ef27bb0.json` / `.txt`（基线：`placeholder-ph-diag3_7d796dbb.json`）

## 2. 逐类型误差表（估值均值 vs 真实均值，真实=布局贡献含块间外边距）

| 类型 | 块数 | 真实均值 | 旧估值 | 旧偏差 | 新估值 | 新偏差 |
|---|---:|---:|---:|---:|---:|---:|
| paragraph | 1398 | 49.63 | 24.97 | −49.69% | 51.24 | **+3.24%** |
| math_block | 567 | 62.11 | 113.85 | +83.31% | 62.00 | **−0.17%** |
| image | 53 | 41.58 | 351.00 | +744.06% | 46.00 | **+10.62%** |
| mermaid（`code_block[lang=mermaid]`） | 19 | 211.61 | 450.21 | +112.76% | 213.74 | **+1.01%** |
| table | 33 | 398.33 | 360.94 | −9.39% | 401.15 | **+0.71%** |
| heading | 42 | 32.00 | 33.86 | +5.80% | 32.00 | **0.00%** |
| blank_line | 1889 | 26.59 | 22.01 | −17.22% | 26.21 | **−1.46%** |

> image：真实均值 41.58、中位 46.39（53 张全部未加载/失败，块高≈46.39）。估值 46.00 对准典型失败块；
> 均值被少数更矮的块拉低，整篇影响 0.13%。blank 的 26.59 含「公式 1em 上外边距塌陷到前一个空行」，
> 该外边距已按邻居归属记到空行上（`_pvBlockH`），故 blank/math 两者同时收敛。

## 3. 滚动期 scrollHeight 变化（跳动）未恶化

| 版本 | 整轮滚动极差 | 占全量 |
|---|---:|---:|
| 旧（4 次独立运行） | 2,504–2,782 px | 1.37–1.53% |
| 新（HEAD，2 次） | 2,629–2,719 px | 1.46–1.51% |

同一量级、落在旧版自身波动区间内；未用「缩小估值」换跳动。

## 4. 交互门禁（HEAD 亲跑）

```
L0 idle-raf            PASS  p50=16.65ms
L1 open-first-screen   PASS  首块可见 103.6ms, 3662 块中 36 物化/3626 占位
L2 positions           PASS  drift = 0,0,0,0 行
L3 back-to-top         PASS  |Δ| = 1.1 行 (≤5)
L4 long-scroll         PASS  maxMaterialized=98 ≤248; evictTotal=3170
L5 edit-protect        PASS
```

- `run_lazy_gate.py --label w34-head --with-existing-12`：**6/6 PASS**，既有 **12/12 PASS**
- `blockquote_roundtrip_test.js`：**80/80 PASS**
- `trailing_space_input_test.js`：**62/62 PASS**
- `scheduler_vm_test.js`：全 PASS
- `check_scheduler_discipline.py`：PASS（62 文件 / 白名单 30 条全命中）
- `node --check`（app.js、探针）与 `py_compile`（runner）：0 错误

证据：`results/lazy-gate-w34-head_7ef27bb0.md`、`raw-lazy-gate-w34-head_7ef27bb0.json`、
`raw-interaction-lazy-gate-existing12_7ef27bb0.json`。

## 5. 其它窗口宽度（鲁棒性，非验收口径）

| 视口 | 全量 | 惰性 | 偏差 | 滚动极差 |
|---|---:|---:|---:|---:|
| 1000×700 | 223,976 | 222,327 | **−0.74%** | 0.68% |
| 1600×900 | 158,187 | 158,645 | **+0.29%** | 3.56%* |

\* 1600×900 只验了高度准确度；该宽度下旧/新滚动极差的 A/B **未做**（临时改回旧 `app.js` 有污染共享仓
的风险，已放弃）。1600 宽的 3.56% 是当前版本绝对值，不能据此断言「比旧版差」。

## 6. 改了什么

`src/memoria/ui/static/app/js/app.js`：

1. **`_probeTypeMetrics(host)`**（新）：在已挂载宿主上一次性插隐藏探针，量段落行高
   （`.markdown-body p` 实测 23.8px，不是全局 22.4）、h1–h3 单行高、图片 caption 高/上边距。
   随字体/UI 缩放/窗口宽度自动跟随，无硬编码 px。
2. **paragraph**：`srcLine×lh×1.05` → 按 inline AST 的**视觉宽度 ÷ 可用宽度**估折行数 × 实测段落行高
   （CJK 0.95em / ASCII 0.6em / 空白 0.3em / 标点 0.35em；08 章 1398 段行数命中 ≈87%）。
3. **image**：`max(4lh, paneW×9/16≈351px)` → **未加载/失败兜底 = pLh + caption高 + caption上边距
   ≈46px**（实测失败块 46.39px 中位）；`_pvWatchImage` 在图片块物化时挂 load/error，
   成功则把 naturalWidth/Height 记入会话级 `_pvImgSizes`（内容寻址 URL，无需失效；>4000 条清空），
   之后同 URL 的占位按真实宽高比 × 可用宽度估。**不再假设 9:16。**
4. **math_block**：`lines×lh×1.7`（源码恒 3 行 ⇒ 114px）→ 按**公式源长度**：
   `lh×(1.105 + 0.0071×len)`（实测 h≈24.76+0.1595×len，源长度相关 0.83；旧 textContent 口径 0.74）；MathJax 的 1em **上**外边距
   在布局中塌陷到前一个空行块，由 `_pvBlockH(doc,idx)` 按邻居归属给空行（两边同时收敛）。
5. **table**：1.35 → 1.5×lh/源行（实测 33.4px/行）。
6. **mermaid**：parser 产 `code_block[lang=mermaid]`（原 `mermaid` 分支从未命中）；改为
   `max(4lh, lines×lh×0.45)`（实测 402 源行→4021px，旧式给 450px/块）。
7. **heading**：按实测 h1–h3 单行高（h2=32px），不再统一 1.5×lh。
8. 未改动无实测数据的类型（code_block 普通、list、blockquote、hr、default），避免无证据翻动。

## 7. 未验证 / 限制

- **图片能正常加载的文档**未实测：占位阶段一律先按失败骨架（≈46px），首屏图片物化后自然加载；
  远处置信与全量渲染的 `loading=lazy` 行为一致，但未做 A/B。
- `_probeTypeMetrics` 在**不同字体 / UI 缩放档位**下设计上跟随（全部实测），但未逐档验证。
- 1600×900 的滚动跳动 A/B 未做（见 §5）。
- 长会话浏览 >4000 张不同图片的内存行为未压测（上限为保守估计）。
- 探针脚本的 `--viewport` / `--dump-blocks` 小改动仍在工作区未提交（app.js 已由 Lead 提交）。
