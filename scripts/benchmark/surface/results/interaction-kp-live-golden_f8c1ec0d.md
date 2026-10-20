# KP 交互金标准（真机应用）

> 生成：`scripts/benchmark/surface/kp_golden_md.py`
> 场景：`scripts/benchmark/surface/scenarios/kp-interactions.json`
> 驱动：`interaction.mjs --scenarios … --cdp-port 9500`（attach **已在运行的真机应用**，非无头）
> 运行：2 次　｜　浏览器：Edg/155.0.4283.62　｜　target：Memoria v0.4.3

## 为什么补这一块

surface 契约 C6（落点）/C8（交互存活）**没有覆盖「知识点 ↔ 显示区域」的联动**，
而重构最可能静默弄坏的正是这里。本金标准把 4 条 KP 联动钉成可逐字比对的快照。

## 断言结果

| # | 断言 | 结果 | 实测值 |
|---|---|---|---|
| 1 | 悬停前：无任何区间高亮 | 🟢 通过 | `(0, 0, None)` |
| 2 | 悬停局部 KP(L45–60)：源码 16 行 in-range + kp-hover，预览带 45-60（非 error） | 🟢 通过 | `(16, 16, '45-60', False)` |
| 3 | 移出：高亮全部清除（无残留） | 🟢 通过 | `(0, None, None)` |
| 4 | （另测）悬停**不滚动**：scroll 应与 before-hover 相同 | 🟢 通过 | `6796` |
| 5 | 点击前：无高亮、无 active | 🟢 通过 | `(0, None)` |
| 6 | 点击局部 KP：16 行高亮+闪烁、带 45-60、active 置位、**预览已滚动**（scroll>500） | 🟢 通过 | `(16, 16, '45-60', 'kp-local-mid', 2821)` |
| 7 | 闪烁 2.5s 后自动淡出，active 保留（跳转态持久，高亮态短暂） | 🟢 通过 | `(0, 'kp-local-mid')` |
| 8 | 保存前：已有 16 行标记，视口在中部（scroll>500，非顶部） | 🟢 通过 | `(16, 2821)` |
| 9 | 保存后：标记仍在（16 行）且**滚动位置不变**（静默标记语义） | 🟢 通过 | `(16, 2821)` |
| 10 | 打开前：无错误高亮 | 🟢 通过 | `(0, None)` |
| 11 | 检查面板「打开」→ 7 行 kp-error-flash、预览带 94-100 且标 error、列表项 error-highlight+active | 🟢 通过 | `(7, True, '94-100', True, True)` |

合计 **11/11** 通过。

## 对比型断言（需要两个快照相减）

- **悬停不滚动**：before-hover scroll=6796 → during-hover scroll=6796 ⇒ 🟢 未滚动
- **保存不滚动**：before-save scroll=2821 → after-save scroll=2821 ⇒ 🟢 未滚动
- **保存不破标记**：before in-range=16 → after in-range=16 ⇒ 🟢 标记保持

## 两次运行一致性

- 快照总数：run1=10，run2=10
- **差异条目：0** ⇒ 🟢 两次完全一致（金标准可复现）

## 前置条件（复现必读）

1. 知识库副本：`docs/example/AAA_Vocab` → `artifacts/_kp_probe_kb`（**不污染源**）。
2. 侧车注入（仅副本）：
   - `kp-local-mid`：**注入的局部区间 L45–60**。源库 69/69 个 KP 都覆盖 L1–末行，
     那样「点了 KP 跳到区间」与「滚回顶部」不可区分 ⇒ 必须注入局部 KP 才能测出跳转。
   - `kp-err-probe`：注入的校验错误来源（配合检查面板的「打开」按钮）。
3. **改侧车后必须重启应用**：侧车在应用内存里按 rel_norm 缓存，切文件 / 构建知识库都不会失效。
4. 启动：`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9500`
   + `MEMORIA_KB=<副本>` + `python -m memoria.app.desktop`。
