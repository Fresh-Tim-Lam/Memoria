# 渲染保真度 · mut-reorder（19971759）

> 指标：`scripts/benchmark/surface/fidelity.mjs` + `fidelity_cli.mjs`
> 文档：corpus/03-block-boundaries.md、corpus/04-non-editable.md、corpus/07-extremes.md
> **变异测试**：`reorder`（必须判 FAIL）

## A 级（硬门槛）整体：**🟢 全绿**

## 变异判别力：`reorder` → **PASS**

| 文档 | 变异后 A 级 | 期望 | 结果 |
|---|---|---|---|
| `corpus/03-block-boundaries.md` | 🔴 抓到 | 🔴 必须红 | ✓ 有判别力 |
| `corpus/04-non-editable.md` | 🔴 抓到 | 🔴 必须红 | ✓ 有判别力 |
| `corpus/07-extremes.md` | 🔴 抓到 | 🔴 必须红 | ✓ 有判别力 |

- 抓到（判红）：**3 / 3** 文档

| 文档 | A 级 | 块数(A/DOM) | 签名 | 可复现 |
|---|---|---|---|---|
| `corpus/03-block-boundaries.md` | 🟢 | 25/25 | `6071cc337566…` | ✓ |
| `corpus/04-non-editable.md` | 🟢 | 29/29 | `9ce1e9c13ffe…` | ✓ |
| `corpus/07-extremes.md` | 🟢 | 219/219 | `5edc6c8e06ea…` | ✓ |

### `corpus/03-block-boundaries.md`

- A1 块数：PASS
- A2 块序+类型：PASS（orderOk=True，typeMismatch=0 处）
- A3 公式：PASS（块 None/0，行内 0/0，残留 0）
- A4 看门狗：W1=PASS（0 空文本越界）W2=PASS（0 classless）
- B5 文本（warn）：diff 14 块　B6 结构（warn）：diff 0 处
- **变异 `reorder` 后 ok=False**（期望 False ⇒ 判红）

### `corpus/04-non-editable.md`

- A1 块数：PASS
- A2 块序+类型：PASS（orderOk=True，typeMismatch=0 处）
- A3 公式：PASS（块 None/1，行内 0/0，残留 0）
- A4 看门狗：W1=PASS（0 空文本越界）W2=PASS（0 classless）
- B5 文本（warn）：diff 14 块　B6 结构（warn）：diff 1 处
- **变异 `reorder` 后 ok=False**（期望 False ⇒ 判红）

### `corpus/07-extremes.md`

- A1 块数：PASS
- A2 块序+类型：PASS（orderOk=True，typeMismatch=0 处）
- A3 公式：PASS（块 None/0，行内 1/2，残留 0）
- A4 看门狗：W1=PASS（0 空文本越界）W2=PASS（0 classless）
- B5 文本（warn）：diff 11 块　B6 结构（warn）：diff 0 处
- **变异 `reorder` 后 ok=False**（期望 False ⇒ 判红）
