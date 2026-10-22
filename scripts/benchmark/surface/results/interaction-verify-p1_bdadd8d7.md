# 交互契约测试：verify-p1

- 时间：2026-10-20T14:30:39.353686+00:00
- commit：`bdadd8d7`
- 语料：`artifacts\baseline-kb\数字通信原理`
- 剧本：`interactions.json`（11 个）
- 浏览器：Edg/155.0.4283.45

## 结论：✅ 全部剧本跑通

| 剧本 | 状态 | 快照数 | 选区摘要 |
|---|---|---|---|
| S0-open-and-ready | ✅ | 1 | `` | a=None@None f=None@None collapsed=True |
| S1-drag-select-same-block | ✅ | 1 | `-003 频率响` | a=None@2 f=None@10 collapsed=False |
| S2-drag-select-cross-block | ✅ | 1 | `03 频率响应：$h(t)=\mathrm{e}` | a=None@4 f=None@5 collapsed=False |
| S3-double-click-word | ✅ | 1 | `hw` | a=None@0 f=None@2 collapsed=False |
| S4-shift-arrow-extend | ✅ | 2 | `03 ` | a=None@4 f=None@7 collapsed=False |
| S5-ctrl-shift-arrow-word | ✅ | 1 | `-003` | a=None@2 f=None@6 collapsed=False |
| S6-shift-home-end | ✅ | 2 | `hw-003` | a=None@0 f=None@6 collapsed=False |
| S7-ctrl-a | ✅ | 1 | `hw-003 频率响应：$h(t)=\mathr` | a=None@0 f=None@0 collapsed=False |
| S8-shift-click-extend | ✅ | 2 | `-003 频率响应：$h(t)=\mathrm{` | a=None@2 f=None@5 collapsed=False |
| S9-ime-compose-commit | ✅ | 2 | `` | a=None@4 f=None@4 collapsed=True |
| S10-brush-highlight-drag | ✅ | 2 | `-003 频率` | a=None@2 f=None@7 collapsed=False |

> 快照明细见同名 `.json`。新实现落地后用同一剧本再跑一次，逐剧本 diff 快照即可判「交互是否一致」。
