# 交互契约测试：legacy-golden-r2

- 时间：2026-10-20T01:40:41.599421+00:00
- commit：`d2120e6b`
- 语料：`artifacts\baseline-kb\数字通信原理`
- 剧本：`interactions.json`（11 个）
- 浏览器：Edg/155.0.4283.45

## 结论：❌ 11 个剧本报错

| 剧本 | 状态 | 快照数 | 选区摘要 |
|---|---|---|---|
| S0-open-and-ready | ❌ 等待超时（blocks）: document.querySelectorAll('#preview .-src-block').length > 3 | 0 | — |
| S1-drag-select-same-block | ❌ 等待超时: document.querySelectorAll('#preview .-src-block').length > 3 | 0 | — |
| S2-drag-select-cross-block | ❌ 等待超时: document.querySelectorAll('#preview .-src-block').length > 3 | 0 | — |
| S3-double-click-word | ❌ 等待超时: document.querySelectorAll('#preview .-src-block').length > 3 | 0 | — |
| S4-shift-arrow-extend | ❌ 等待超时: document.querySelectorAll('#preview .-src-block').length > 3 | 0 | — |
| S5-ctrl-shift-arrow-word | ❌ 等待超时: document.querySelectorAll('#preview .-src-block').length > 3 | 0 | — |
| S6-shift-home-end | ❌ 等待超时: document.querySelectorAll('#preview .-src-block').length > 3 | 0 | — |
| S7-ctrl-a | ❌ 等待超时: document.querySelectorAll('#preview .-src-block').length > 3 | 0 | — |
| S8-shift-click-extend | ❌ 等待超时: document.querySelectorAll('#preview .-src-block').length > 3 | 0 | — |
| S9-ime-compose-commit | ❌ 等待超时: document.querySelectorAll('#preview .-src-block').length > 3 | 0 | — |
| S10-brush-highlight-drag | ❌ 等待超时: document.querySelectorAll('#preview .-src-block').length > 3 | 0 | — |

> 快照明细见同名 `.json`。新实现落地后用同一剧本再跑一次，逐剧本 diff 快照即可判「交互是否一致」。
