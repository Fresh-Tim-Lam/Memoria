# 维护机制基准（maintenance benchmark）

> 位置与还原标记（对应 `docs/design/maintenance-benchmark.md`）。

## 基准测试知识库（生成式，不入库）

- **位置（标记）**：`artifacts/_bench_maintenance/kb/`（仓库根下 artifacts，gitignore，不入库；需要时随时重新生成）
- 生成器：`scripts/benchmark/maintenance/gen_maintenance_kb.py`
  ```
  python scripts/benchmark/maintenance/gen_maintenance_kb.py --out artifacts/_bench_maintenance/kb --files 200
  ```
- 默认档：200 文件 / ~599 KP / 333 链接 / 确定性（同参两次内容一致）；默认不含图片与 embedding（`--images` 可选）

## 基线记录（已入库，改造前锚点）

- 记录文件：`results/baseline_ae66a012.{json,md}`（语料 digest `756f3cc3…`，save median≈123ms / p95≈200ms）
- 锚点 tag：`maint-base`（`ae66a012`，改造前）、`maint-sched`（`f5be88bf`，scheduler 内核）
- 还原开发前数据：`git checkout maint-base`；锚定/复跑：`python scripts/benchmark/maintenance/anchor_baseline.py --sha <commit>`

## A/B 对照

- 改后采集（L1，后续 B3 脚本）：同语料、同机、同方法，产出 `results/run_<sha>.json`
- 汇总：`results/summary.md`（指标 | 改前 | 改后 | 变化% | 结论）
- 门禁：改善类提交须附对照；关键指标回退 → 打回（见 to-dolist §12 阶段门禁）
