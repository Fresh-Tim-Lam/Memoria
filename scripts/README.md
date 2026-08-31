# scripts/ — 开发者工具

**正式可复用**的开发者工具目录。与 `packaging/` 职责分离：`scripts/` = 开发工具，`packaging/` = 打包发布。

## 内容

| 文件/目录 | 用途 |
|-----------|------|
| `run_dev.ps1` | 开发态启动：源码 + pywebview 壳 + DevTools + 无边框（`MEMORIA_MODE=dev`） |
| `graph_layout_benchmark.py` / `.mjs` | 图谱布局压力基准（2D/3D 布局 + 分组计算） |
| `benchmark/` | 检索评估工具集（lexical / embedding / rerank 评测跑批） |
| `bootstrap_example_sidecars.py` | 生成示例知识库 sidecar |
| `gen_example_boonie_sidecars.py` | 生成 boonie 示例知识库 sidecar |

## 规则

- 临时/一次性脚本禁止放这里 → `artifacts/`
- 检索评估数据与结果 → `benchmarks/`
- 打包相关脚本 → `packaging/`
