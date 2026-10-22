# 交互契约测试：e33-postfix7

- 时间：2026-10-22T17:41:47.655131+00:00
- commit：`9feb84ab`
- 语料：`artifacts\baseline-kb\数字通信原理`
- 剧本：`e33_probe.json`（4 个）
- 浏览器：Edg/155.0.4283.62

## 结论：❌ 1 个剧本报错

| 剧本 | 状态 | 快照数 | 选区摘要 |
|---|---|---|---|
| E33-drop-text | ✅ | 0 | — |
| E33-drop-no-text | ✅ | 0 | — |
| E33-drop-rerender | ❌ 等待超时（rerender contains dropped text）: document.getElementById('preview').textContent.indexOf('E33RERENDER') >= 0 | 0 | — |
| E33-drag-move-undo | ✅ | 0 | — |

> 快照明细见同名 `.json`。新实现落地后用同一剧本再跑一次，逐剧本 diff 快照即可判「交互是否一致」。
