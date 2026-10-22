# 交互契约测试：kp-s4

- 时间：2026-10-20T11:29:04.365449+00:00
- commit：`d4422efa`
- 语料：`tests\probe-kb`
- 剧本：`kp-scenario-s4.json`（1 个）
- 浏览器：Edg/155.0.4283.45

## 结论：❌ 1 个剧本报错

| 剧本 | 状态 | 快照数 | 选区摘要 |
|---|---|---|---|
| KP-S4-delete-line-end | ❌ 等待超时（S4-local-shift-1）: (function(){var m={};window.state.doc.knowledge_points.forEach(function(k){m[k.id]=k.range_resolved?k.range_resolved.start_line:null});return m.kpS4A===14&&m.kpS4B===20;})() | 0 | — |

> 快照明细见同名 `.json`。新实现落地后用同一剧本再跑一次，逐剧本 diff 快照即可判「交互是否一致」。
