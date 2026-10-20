# 交互契约测试：debug3

- 时间：2026-10-20T01:34:49.628844+00:00
- commit：`d2120e6b`
- 语料：`artifacts\baseline-kb\数字通信原理`
- 剧本：`_debug.json`（1 个）
- 浏览器：Edg/155.0.4283.45

## 结论：❌ 1 个剧本报错

| 剧本 | 状态 | 快照数 | 选区摘要 |
|---|---|---|---|
| D1-drag-blocked | ❌ eval 异常: Uncaught (in promise) TypeError: Failed to fetch TypeError: Failed to fetch
    at Proxy.<anonymous> (http://127.0.0.1:8645/:53:16)
    at call (http://127.0.0.1:8645/app/js/app.js:399:23)
    at Object.openFile (http://127.0.0.1:8645/app/js/app.js:1445:23)
    at <anonymous>:1:19 | 0 | — |

> 快照明细见同名 `.json`。新实现落地后用同一剧本再跑一次，逐剧本 diff 快照即可判「交互是否一致」。
