# 渲染保真度 · p2a-legacy-base（98ea6236）

> 指标：`scripts/benchmark/surface/fidelity.mjs` + `fidelity_cli.mjs`
> 文档：corpus/01-ime-zh.md、corpus/03-block-boundaries.md

## A 级（硬门槛）整体：**🟢 全绿**

| 文档 | A 级 | 块数(A/DOM) | 签名 | 可复现 |
|---|---|---|---|---|
| `corpus/01-ime-zh.md` | 🟢 | 15/15 | `ecc25265fd82…` | ✓ |
| `corpus/03-block-boundaries.md` | 🟢 | 26/26 | `047e5e2fe0b6…` | ✓ |

### `corpus/01-ime-zh.md`

- A1 块数：PASS
- A2 块序+类型：PASS（orderOk=True，typeMismatch=0 处）
- A3 公式：PASS（块 None/0，行内 0/0，残留 0）
- A4 看门狗：W1=PASS（0 空文本越界）W2=PASS（0 classless）
- B5 文本（warn）：diff 8 块　B6 结构（warn）：diff 0 处

### `corpus/03-block-boundaries.md`

- A1 块数：PASS
- A2 块序+类型：PASS（orderOk=True，typeMismatch=0 处）
- A3 公式：PASS（块 None/0，行内 0/0，残留 0）
- A4 看门狗：W1=PASS（0 空文本越界）W2=PASS（0 classless）
- B5 文本（warn）：diff 14 块　B6 结构（warn）：diff 0 处
