# 交互契约测试：s11-ambient

- 时间：2026-10-21T14:29:44.961075+00:00
- commit：`1415051a`
- 语料：`artifacts\baseline-kb\数字通信原理`
- 剧本：`s11-only.json`（1 个）
- 浏览器：Edg/155.0.4283.45

## 结论：❌ 1 个剧本报错

| 剧本 | 状态 | 快照数 | 选区摘要 |
|---|---|---|---|
| S11-find-highlight | ❌ 等待超时（suggest-items）: document.querySelectorAll('#toolbar-search-panel .-suggest-item').length > 0 | 1 | `` | a=None@None f=None@None collapsed=True |

> 快照明细见同名 `.json`。新实现落地后用同一剧本再跑一次，逐剧本 diff 快照即可判「交互是否一致」。
