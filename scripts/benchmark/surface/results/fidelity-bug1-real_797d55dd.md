# 渲染保真度 · bug1-real（797d55dd）

> **mode = real**（真机 CDP：http://127.0.0.1:9500）
> ⚠️ 真机与无头**不可混比**：真机 MathJax 排 270 个，无头只排 ≈3；跨模式比较 = 假 diff

> 指标：`scripts/benchmark/surface/fidelity.mjs` + `fidelity_cli.mjs`
> 文档：corpus/02-inline-edges.md、scale/scale-5k.md

## A 级（硬门槛）整体：**🟢 全绿**

## 渲染就绪（task-31）

| 文档 | status | 等待 ms | 公式(已排/期望) | mermaid(有svg/容器) |
|---|---|---|---|---|
| `corpus/02-inline-edges.md` | ✅ `ready` | 33.9 | 1/1 | - |
| `scale/scale-5k.md` | ✅ `ready` | 24.2 | 270/270 | 135/135 |

> **只有 `ready` 的快照可信**；`timeout`/`failed` 表示快照可能早取或渲染异常；
> `inconclusive` = 无头环境（MathJax 排不完），**不据此判绿也不判红**。

| 文档 | A 级 | 块数(A/DOM) | 签名 | 可复现 |
|---|---|---|---|---|
| `corpus/02-inline-edges.md` | 🟢 | 21/21 | `b50aa61271fc…` | ✓ |
| `scale/scale-5k.md` | 🟢 | 3110/3110 | `7e784156f42a…` | ✓ |

### `corpus/02-inline-edges.md`

- A1 块数：PASS
- A2 块序+类型：PASS（orderOk=True，typeMismatch=0 处）
- A3 公式：PASS（块 None/0，行内 1/1，残留 0）
- A4 看门狗：W1=PASS（0 空文本越界）W2=PASS（0 classless）
- B5 文本（warn）：diff 11 块　B6 结构（warn）：diff 0 处

### `scale/scale-5k.md`

- A1 块数：PASS
- A2 块序+类型：PASS（orderOk=True，typeMismatch=0 处）
- A3 公式：PASS（块 None/135，行内 135/135，残留 0）
- A4 看门狗：W1=PASS（0 空文本越界）W2=PASS（0 classless）
- B5 文本（warn）：diff 1760 块　B6 结构（warn）：diff 135 处
