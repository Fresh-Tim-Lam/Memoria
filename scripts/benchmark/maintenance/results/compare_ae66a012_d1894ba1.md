# A/B 对比（交错多轮，抗机器漂移）

- 时间：2026-09-09T10:43:49.703469+00:00
- base：`ae66a012`（tag maint-base） vs head：`d1894ba12dc2b5497bec73cf50cc9516884b6908`
- 方法：rounds=2、sample=20 文件、runs=3；每轮 base/head 交替，轮间颠倒
- 样本：语料 200 文件（digest 见 run json，生成确定性）

| round | base median | head median |
|---|---|---|
| 1 | 176.41 | 192.37 |
| 2 | 140.74 | 168.59 |

- base 各轮 median：[176.41, 140.74] → 中位 158.575
- head 各轮 median：[192.37, 168.59] → 中位 180.48000000000002
- Δ = 13.8%
- **结论：回退需查**

> 说明：多轮一致时 Δ 才可信；单轮波动大时需增加 rounds。
