# 渲染保真度 · reg-final2（797d55dd）

> **mode = headless**（无头 harness）
> ⚠️ 真机与无头**不可混比**：真机 MathJax 排 270 个，无头只排 ≈3；跨模式比较 = 假 diff

> 指标：`scripts/benchmark/surface/fidelity.mjs` + `fidelity_cli.mjs`
> 文档：corpus/03-block-boundaries.md、corpus/04-non-editable.md、corpus/05-images.md、corpus/07-extremes.md、README.md

## A 级（硬门槛）整体：**🟢 全绿**

## 渲染就绪（task-31）

| 文档 | status | 等待 ms | 公式(已排/期望) | mermaid(有svg/容器) |
|---|---|---|---|---|
| `corpus/03-block-boundaries.md` | ⚪ `inconclusive` | 35.4 | - | - |
| `corpus/04-non-editable.md` | ⚪ `inconclusive` | 42.2 | 1/1 | 1/1 |
| `corpus/05-images.md` | ⚪ `inconclusive` | 41.9 | - | - |
| `corpus/07-extremes.md` | ⚪ `inconclusive` | 51.8 | 2/2 | - |
| `README.md` | ⚪ `inconclusive` | 49.2 | - | - |

> **只有 `ready` 的快照可信**；`timeout`/`failed` 表示快照可能早取或渲染异常；
> `inconclusive` = 无头环境（MathJax 排不完），**不据此判绿也不判红**。

| 文档 | A 级 | 块数(A/DOM) | 签名 | 可复现 |
|---|---|---|---|---|
| `corpus/03-block-boundaries.md` | 🟢 | 25/25 | `5b670efe6103…` | ✓ |
| `corpus/04-non-editable.md` | 🟢 | 29/29 | `3eb7e76ecea5…` | ✓ |
| `corpus/05-images.md` | 🟢 | 18/18 | `7bc42c8b3224…` | ✓ |
| `corpus/07-extremes.md` | 🟢 | 219/219 | `e5a36503f316…` | ✓ |
| `README.md` | 🟢 | 30/30 | `9766b2507d82…` | ✓ |

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
