# 渲染保真度 · a6mut-broken-as-resolved（797d55dd）

> **mode = headless**（无头 harness）
> ⚠️ 真机与无头**不可混比**：真机 MathJax 排 270 个，无头只排 ≈3；跨模式比较 = 假 diff

> 指标：`scripts/benchmark/surface/fidelity.mjs` + `fidelity_cli.mjs`
> 文档：corpus/03-block-boundaries.md、corpus/04-non-editable.md、corpus/05-images.md、corpus/07-extremes.md、README.md
> **变异测试**：`broken-as-resolved`（必须判 FAIL）

## A 级（硬门槛）整体：**🟢 全绿**

## 渲染就绪（task-31）

| 文档 | status | 等待 ms | 公式(已排/期望) | mermaid(有svg/容器) |
|---|---|---|---|---|
| `corpus/03-block-boundaries.md` | ⚪ `inconclusive` | 39.6 | - | - |
| `corpus/04-non-editable.md` | ⚪ `inconclusive` | 50.9 | - | 1/1 |
| `corpus/05-images.md` | ⚪ `inconclusive` | 41 | - | - |
| `corpus/07-extremes.md` | ⚪ `inconclusive` | 30011.6 | 2/4 | - |
| `README.md` | ⚪ `inconclusive` | 47.1 | - | - |

> **只有 `ready` 的快照可信**；`timeout`/`failed` 表示快照可能早取或渲染异常；
> `inconclusive` = 无头环境（MathJax 排不完），**不据此判绿也不判红**。

## 变异判别力：`broken-as-resolved` → **FAIL**

| 文档 | 变异后 A 级 | 期望 | 结果 |
|---|---|---|---|
| `corpus/03-block-boundaries.md` | 🟢 仍绿 | 🔴 必须红 | ❌ 无判别力 |
| `corpus/04-non-editable.md` | 🟢 仍绿 | 🔴 必须红 | ❌ 无判别力 |
| `corpus/05-images.md` | 🟢 仍绿 | 🔴 必须红 | ❌ 无判别力 |
| `corpus/07-extremes.md` | 🟢 仍绿 | 🔴 必须红 | ❌ 无判别力 |
| `README.md` | 🟢 仍绿 | 🔴 必须红 | ❌ 无判别力 |

- 抓到（判红）：**0 / 5** 文档
- ⚠️ **未被抓到**：`corpus/03-block-boundaries.md`、`corpus/04-non-editable.md`、`corpus/05-images.md`、`corpus/07-extremes.md`、`README.md` ⇒ 该变异类型在这些文档上无判别力

| 文档 | A 级 | 块数(A/DOM) | 签名 | 可复现 |
|---|---|---|---|---|
| `corpus/03-block-boundaries.md` | 🟢 | 25/25 | `1ad8f6b1187f…` | ✓ |
| `corpus/04-non-editable.md` | 🟢 | 29/29 | `43eff37f611d…` | ✓ |
| `corpus/05-images.md` | 🟢 | 18/18 | `e793b78c88b5…` | ✓ |
| `corpus/07-extremes.md` | 🟢 | 219/219 | `606475025b6f…` | ✓ |
| `README.md` | 🟢 | 30/30 | `3c43564b837b…` | ✓ |

### `corpus/03-block-boundaries.md`

- A1 块数：PASS
- A2 块序+类型：PASS（orderOk=True，typeMismatch=0 处）
- A3 公式：PASS（块 None/0，行内 0/0，残留 0）
- A4 看门狗：W1=PASS（0 空文本越界）W2=PASS（0 classless）
- B5 文本（warn）：diff 14 块　B6 结构（warn）：diff 0 处
- **变异 `broken-as-resolved` 后 ok=True**（期望 False ⇒ 判红）

### `corpus/04-non-editable.md`

- A1 块数：PASS
- A2 块序+类型：PASS（orderOk=True，typeMismatch=0 处）
- A3 公式：PASS（块 None/1，行内 0/0，残留 0）
- A4 看门狗：W1=PASS（0 空文本越界）W2=PASS（0 classless）
- B5 文本（warn）：diff 14 块　B6 结构（warn）：diff 1 处
- **变异 `broken-as-resolved` 后 ok=True**（期望 False ⇒ 判红）

### `corpus/05-images.md`

- A1 块数：PASS
- A2 块序+类型：PASS（orderOk=True，typeMismatch=0 处）
- A3 公式：PASS（块 None/0，行内 0/0，残留 0）
- A4 看门狗：W1=PASS（0 空文本越界）W2=PASS（0 classless）
- B5 文本（warn）：diff 10 块　B6 结构（warn）：diff 0 处
- **变异 `broken-as-resolved` 后 ok=True**（期望 False ⇒ 判红）

### `corpus/07-extremes.md`

- A1 块数：PASS
- A2 块序+类型：PASS（orderOk=True，typeMismatch=0 处）
- A3 公式：PASS（块 None/0，行内 1/2，残留 0）
- A4 看门狗：W1=PASS（0 空文本越界）W2=PASS（0 classless）
- B5 文本（warn）：diff 11 块　B6 结构（warn）：diff 0 处
- **变异 `broken-as-resolved` 后 ok=True**（期望 False ⇒ 判红）

### `README.md`

- A1 块数：PASS
- A2 块序+类型：PASS（orderOk=True，typeMismatch=0 处）
- A3 公式：PASS（块 None/0，行内 0/0，残留 0）
- A4 看门狗：W1=PASS（0 空文本越界）W2=PASS（0 classless）
- B5 文本（warn）：diff 21 块　B6 结构（warn）：diff 0 处
- **变异 `broken-as-resolved` 后 ok=True**（期望 False ⇒ 判红）
