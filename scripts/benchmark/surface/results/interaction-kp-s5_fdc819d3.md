# 交互契约测试：kp-s5

- 时间：2026-10-20T11:33:46.412849+00:00
- commit：`fdc819d3`
- 语料：`artifacts\_kp_fixture_kb`
- 剧本：`kp-scenario-s5.json`（1 个）
- 浏览器：Edg/155.0.4283.45

## 结论：❌ 1 个剧本报错

| 剧本 | 状态 | 快照数 | 选区摘要 |
|---|---|---|---|
| KP-S5-commitRange | ❌ 等待超时（S5-local-shift）: (function(){var d=window.__kpAfter.lines-window.__kpBefore.lines;return d<0&&window.__kpAfter.kp.kpS5C===21+d&&window.__kpAfter.kp.kpS5D===31+d;})() | 0 | — |

> 快照明细见同名 `.json`。新实现落地后用同一剧本再跑一次，逐剧本 diff 快照即可判「交互是否一致」。
