# 维护基线（改造前锚定）

- 基线 commit：`ae66a012`（tag `maint-base`）
- 记录时间：2026-09-09T06:25:25.537224+00:00
- 语料：200 文件 / 599 KP / 333 links（digest `756f3cc3d473d86c`），生成命令 `gen_maintenance_kb.py --files 200`
- 环境：python 3.12.4 / nt
- 方法：外部计时 `save_document`（含 registry+resync 维护），样本 20 文件 × 3 次 = 60 次保存；旧代码无内部分项（registry/resync）计时，改造后对比时以新增 bench_ms 分项对齐口径
- 结果（ms）：mean=136.06 median=123.14 p95=200.1
