# 交互契约测试：bugc-head

- 时间：2026-10-23T04:58:52.130085+00:00
- commit：`d9c2cbcc`
- 语料：`artifacts\baseline-kb\数字通信原理`
- 剧本：`interactions.json`（12 个）
- 浏览器：Edg/155.0.4283.62

## 结论：❌ 10 个剧本报错

| 剧本 | 状态 | 快照数 | 选区摘要 |
|---|---|---|---|
| S0-open-and-ready | ✅ | 1 | `` | a=None@None f=None@None collapsed=True |
| S1-drag-select-same-block | ❌ 找不到文本块（auto） | 0 | — |
| S2-drag-select-cross-block | ❌ 找不到视口内成对正文块（pairA/pairB） | 0 | — |
| S3-double-click-word | ❌ 找不到文本块（auto） | 0 | — |
| S4-shift-arrow-extend | ❌ 找不到文本块（auto） | 0 | — |
| S5-ctrl-shift-arrow-word | ❌ 找不到文本块（auto） | 0 | — |
| S6-shift-home-end | ❌ 找不到文本块（auto） | 0 | — |
| S7-ctrl-a | ❌ 找不到文本块（auto） | 0 | — |
| S8-shift-click-extend | ❌ 找不到视口内成对正文块（pairA/pairB） | 0 | — |
| S9-ime-compose-commit | ❌ 找不到文本块（auto） | 0 | — |
| S10-brush-highlight-drag | ❌ 找不到文本块（auto） | 1 | `` | a=None@None f=None@None collapsed=True |
| S11-find-highlight | ✅ | 3 | `` | a=None@1 f=None@1 collapsed=True |

> 快照明细见同名 `.json`。新实现落地后用同一剧本再跑一次，逐剧本 diff 快照即可判「交互是否一致」。
