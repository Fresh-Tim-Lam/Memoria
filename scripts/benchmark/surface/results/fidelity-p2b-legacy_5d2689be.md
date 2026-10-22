# 渲染保真度 · p2b-legacy（5d2689be）

> 指标：`scripts/benchmark/surface/fidelity.mjs` + `fidelity_cli.mjs`
> 文档：docs/error_log_format.md、docs/ref/ppt/ocr.md

## A 级（硬门槛）整体：**🔴 有红**

| 文档 | A 级 | 块数(A/DOM) | 签名 | 可复现 |
|---|---|---|---|---|
| `docs/error_log_format.md` | 🟢 | 49/49 | `98d12c605e1b…` | ✓ |
| `docs/ref/ppt/ocr.md` | 🔴 | 316/316 | `e3968b4955ef…` | ✓ |

### `docs/error_log_format.md`

- A1 块数：PASS
- A2 块序+类型：PASS（orderOk=True，typeMismatch=0 处）
- A3 公式：PASS（块 None/0，行内 0/0，残留 0）
- A4 看门狗：W1=PASS（0 空文本越界）W2=PASS（0 classless）
- B5 文本（warn）：diff 26 块　B6 结构（warn）：diff 0 处

### `docs/ref/ppt/ocr.md`

- A1 块数：PASS
- A2 块序+类型：FAIL（orderOk=True，typeMismatch=1 处）
- A3 公式：PASS（块 None/0，行内 0/0，残留 0）
- A4 看门狗：W1=FAIL（6 空文本越界）W2=PASS（0 classless）
- B5 文本（warn）：diff 144 块　B6 结构（warn）：diff 0 处
