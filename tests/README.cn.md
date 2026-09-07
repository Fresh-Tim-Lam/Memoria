[English](README.md) | 中文

# tests/ — 单元/集成测试

pytest 测试目录（`pyproject.toml` 中 `testpaths = ["tests"]`）。

## 结构

| 路径 | 职责 |
|------|------|
| `fixtures/` | 测试夹具（示例知识库、检索基准小型语料等） |
| `.memoria/` | 测试用知识库元数据（manifest/pending/cache） |

## 运行

```powershell
pytest
```

## 规则

- 正式测试代码放这里；一次性调试脚本放 `artifacts/`
- 涉及检索评估的跑批脚本放 `scripts/benchmark/`，数据与结果放 `benchmarks/`
