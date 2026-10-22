# 交互契约测试：e27e29-repro

- 时间：2026-10-22T13:32:17.939052+00:00
- commit：`5d6bb8b7`
- 语料：`artifacts\_space-input-kb`
- 剧本：`space_input_e27_e29.json`（3 个）
- 浏览器：Edg/155.0.4283.45

## 结论：✅ 全部剧本跑通

| 剧本 | 状态 | 快照数 | 选区摘要 |
|---|---|---|---|
| E29-plain-word-trailing-space | ✅ | 1 | `` | a=None@77 f=None@77 collapsed=True |
| E27-highlight-trailing-space | ✅ | 1 | `` | a=None@77 f=None@77 collapsed=True |
| E27b-bold-trailing-space | ✅ | 0 | — |

> 快照明细见同名 `.json`。新实现落地后用同一剧本再跑一次，逐剧本 diff 快照即可判「交互是否一致」。
