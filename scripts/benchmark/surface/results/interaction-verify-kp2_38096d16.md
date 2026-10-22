# 交互契约测试：verify-kp2

- 时间：2026-10-20T11:41:15.288170+00:00
- commit：`38096d16`
- 语料：`artifacts\baseline-kb\数字通信原理`
- 剧本：`kp-interactions.json`（4 个）
- 浏览器：Edg/155.0.4283.45

## 结论：❌ 4 个剧本报错

| 剧本 | 状态 | 快照数 | 选区摘要 |
|---|---|---|---|
| KP1-hover-highlights-range | ❌ 等待超时（open vocab/imperative.md）: window.state.currentPath === "vocab/imperative.md" && !!window.state.doc | 0 | — |
| KP2-click-jumps-to-range | ❌ 等待超时（open vocab/imperative.md）: window.state.currentPath === "vocab/imperative.md" && !!window.state.doc | 0 | — |
| KP3-saveupdates-marks-without-scroll | ❌ 等待超时（open vocab/imperative.md）: window.state.currentPath === "vocab/imperative.md" && !!window.state.doc | 0 | — |
| KP4-error-highlight-via-check-panel | ❌ 等待超时（open vocab/imperative.md）: window.state.currentPath === "vocab/imperative.md" && !!window.state.doc | 0 | — |

> 快照明细见同名 `.json`。新实现落地后用同一剧本再跑一次，逐剧本 diff 快照即可判「交互是否一致」。
