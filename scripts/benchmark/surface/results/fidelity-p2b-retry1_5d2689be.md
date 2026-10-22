# 渲染保真度 · p2b-retry1（5d2689be）

> 指标：`scripts/benchmark/surface/fidelity.mjs` + `fidelity_cli.mjs`
> 文档：corpus/05-images.md

## A 级（硬门槛）整体：**🟢 全绿**

| 文档 | A 级 | 块数(A/DOM) | 签名 | 可复现 |
|---|---|---|---|---|
| `corpus/05-images.md` | 🟢 | 17/17 | `10916b2c8a02…` | ✓ |

### `corpus/05-images.md`

- A1 块数：PASS
- A2 块序+类型：PASS（orderOk=True，typeMismatch=0 处）
- A3 公式：PASS（块 None/0，行内 0/0，残留 0）
- A4 看门狗：W1=PASS（0 空文本越界）W2=PASS（0 classless）
- B5 文本（warn）：diff 10 块　B6 结构（warn）：diff 0 处
