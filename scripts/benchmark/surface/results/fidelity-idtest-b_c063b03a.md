# 渲染保真度 · idtest-b（c063b03a）

> 指标：`scripts/benchmark/surface/fidelity.mjs` + `fidelity_cli.mjs`
> 文档：corpus/03-block-boundaries.md、corpus/04-non-editable.md、corpus/05-images.md、corpus/07-extremes.md、README.md

## A 级（硬门槛）整体：**🟢 全绿**

| 文档 | A 级 | 块数(A/DOM) | 签名 | 可复现 |
|---|---|---|---|---|
| `corpus/03-block-boundaries.md` | 🟢 | 25/25 | `452de98fb776…` | ✓ |
| `corpus/04-non-editable.md` | 🟢 | 29/29 | `0703c95f7729…` | ✓ |
| `corpus/05-images.md` | 🟢 | 18/18 | `6e5a2c8ca03d…` | ✓ |
| `corpus/07-extremes.md` | 🟢 | 219/219 | `8fb45c1167b4…` | ✓ |
| `README.md` | 🟢 | 30/30 | `e9ab38632685…` | ✓ |

### `corpus/03-block-boundaries.md`

- A1 块数：PASS
- A2 块序+类型：PASS（orderOk=True，typeMismatch=0 处）
- A3 公式：PASS（块 None/0，行内 0/0，残留 0）
- A4 看门狗：W1=PASS（0 空文本越界）W2=PASS（0 classless）
- B5 文本（warn）：diff 14 块　B6 结构（warn）：diff 0 处

### `corpus/04-non-editable.md`

- A1 块数：PASS
- A2 块序+类型：PASS（orderOk=True，typeMismatch=0 处）
- A3 公式：PASS（块 None/1，行内 0/0，残留 0）
- A4 看门狗：W1=PASS（0 空文本越界）W2=PASS（0 classless）
- B5 文本（warn）：diff 14 块　B6 结构（warn）：diff 1 处

### `corpus/05-images.md`

- A1 块数：PASS
- A2 块序+类型：PASS（orderOk=True，typeMismatch=0 处）
- A3 公式：PASS（块 None/0，行内 0/0，残留 0）
- A4 看门狗：W1=PASS（0 空文本越界）W2=PASS（0 classless）
- B5 文本（warn）：diff 10 块　B6 结构（warn）：diff 0 处

### `corpus/07-extremes.md`

- A1 块数：PASS
- A2 块序+类型：PASS（orderOk=True，typeMismatch=0 处）
- A3 公式：PASS（块 None/0，行内 1/2，残留 0）
- A4 看门狗：W1=PASS（0 空文本越界）W2=PASS（0 classless）
- B5 文本（warn）：diff 11 块　B6 结构（warn）：diff 0 处

### `README.md`

- A1 块数：PASS
- A2 块序+类型：PASS（orderOk=True，typeMismatch=0 处）
- A3 公式：PASS（块 None/0，行内 0/0，残留 0）
- A4 看门狗：W1=PASS（0 空文本越界）W2=PASS（0 classless）
- B5 文本（warn）：diff 21 块　B6 结构（warn）：diff 0 处
