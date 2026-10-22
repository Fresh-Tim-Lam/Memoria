# 交互契约测试：p62-closure

- 时间：2026-10-22T00:38:24.258457+00:00
- commit：`d078c3e3`
- 语料：`artifacts\baseline-kb\数字通信原理`
- 剧本：`interactions.json`（12 个）
- 浏览器：Edg/155.0.4283.45

## 结论：✅ 全部剧本跑通

| 剧本 | 状态 | 快照数 | 选区摘要 |
|---|---|---|---|
| S0-open-and-ready | ✅ | 1 | `` | a=None@None f=None@None collapsed=True |
| S1-drag-select-same-block | ✅ | 1 | `虽给了 ` | a=None@2 f=None@6 collapsed=False |
| S2-drag-select-cross-block | ✅ | 1 | `03 频率响应： ，  录入：202` | a=None@4 f=None@4 collapsed=False |
| S3-double-click-word | ✅ | 1 | `面` | a=None@1 f=None@2 collapsed=False |
| S4-shift-arrow-extend | ✅ | 2 | `给了 ` | a=None@3 f=None@6 collapsed=False |
| S5-ctrl-shift-arrow-word | ✅ | 1 | `虽给了` | a=None@2 f=None@5 collapsed=False |
| S6-shift-home-end | ✅ | 2 | `题面虽给了 ` | a=None@0 f=None@6 collapsed=False |
| S7-ctrl-a | ✅ | 1 | `hw-003 频率响应： ，  录入：2026-` | a=None@0 f=None@0 collapsed=False |
| S8-shift-click-extend | ✅ | 2 | `003 频率响应： ，  录入：202` | a=None@3 f=None@4 collapsed=False |
| S9-ime-compose-commit | ✅ | 2 | `` | a=None@4 f=None@4 collapsed=True |
| S10-brush-highlight-drag | ✅ | 2 | `虽给了` | a=None@2 f=None@3 collapsed=False |
| S11-find-highlight | ✅ | 3 | `` | a=None@1 f=None@1 collapsed=True |

> 快照明细见同名 `.json`。新实现落地后用同一剧本再跑一次，逐剧本 diff 快照即可判「交互是否一致」。
