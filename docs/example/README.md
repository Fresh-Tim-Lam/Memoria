# 示例与本地知识库

`docs/example/` 是仓库「示例知识库」的统一容器（见 `docs/conventions/docs-management.md`）。

| 路径 | 用途 | 是否入库展示 |
|---|---|---|
| `showcase/` | **官方展示样例**：机器学习导论（样式/图片/链接/搜索全功能演示） | ✅ |
| `import-test/` | 导入测试夹具（import-flow 的 flat/md-dir/kb-bundle 回归用） | ✅（测试资产） |
| `AAA_*`、`example-boonie/`、`example-english-kb/`、`examples/`(旧)、`rich-content-test/`、`人工智能导论知识点汇总/`、`description_of_kb.md` 等 | 旧版样例 / 个人知识库 / 开发期测试 | 本地保留，不入库 |

在 Memoria 中试用官方展示库：

1. 打开知识库 → 选择目录 `docs/example/showcase/`
2. 从 `README.md` 或 `overview.md` 开始，沿链接漫游
3. 完整性自查：`python -m memoria.cli.main validate docs/example/showcase`
