# 渲染保真度 · p2b-links-legacy（b2e4fcfc）

> 指标：`scripts/benchmark/surface/fidelity.mjs` + `fidelity_cli.mjs`
> 文档：corpus/06-links-and-kp.md

## A 级（硬门槛）整体：**🔴 有红**

| 文档 | A 级 | 块数(A/DOM) | 签名 | 可复现 |
|---|---|---|---|---|
| `corpus/06-links-and-kp.md` | 🔴 | 33/33 | `37cdbc353f98…` | ✓ |

### `corpus/06-links-and-kp.md`

- A1 块数：PASS
- A2 块序+类型：PASS（orderOk=True，typeMismatch=0 处）
- A3 公式：PASS（块 None/0，行内 0/0，残留 0）
- A4 看门狗：W1=PASS（0 空文本越界）W2=PASS（0 classless）
- B5 文本（warn）：diff 17 块　B6 结构（warn）：diff 0 处
