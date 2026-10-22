# 交互契约测试：kp-golden-after-s9s5c

- 时间：2026-10-20T11:50:45.896181+00:00
- commit：`743a4aec`
- 语料：`artifacts\_kp_probe_kb`
- 剧本：`kp-interactions.json`（4 个）
- 浏览器：Edg/155.0.4283.45

## 结论：✅ 全部剧本跑通

| 剧本 | 状态 | 快照数 | 选区摘要 |
|---|---|---|---|
| KP1-hover-highlights-range | ✅ | 3 | `` | a=None@None f=None@None collapsed=True |
| KP2-click-jumps-to-range | ✅ | 3 | `` | a=None@0 f=None@0 collapsed=True |
| KP3-saveupdates-marks-without-scroll | ✅ | 2 | `` | a=None@None f=None@None collapsed=True |
| KP4-error-highlight-via-check-panel | ✅ | 2 | `` | a=None@None f=None@None collapsed=True |

> 快照明细见同名 `.json`。新实现落地后用同一剧本再跑一次，逐剧本 diff 快照即可判「交互是否一致」。
