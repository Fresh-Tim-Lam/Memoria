# Retrieval benchmarks

权威 IR 数据集 → Memoria 知识库 → SearchKernel 量化评测。

**代码位置**：`scripts/benchmark/`（开发工具，不随 Memoria 运行时发布）

**设计文档**：[`docs/design/search-retrieval-benchmark.md`](../docs/design/search-retrieval-benchmark.md)

## Quick start

```bash
# 全量 SciFact（需网络，~5k 文档）
python scripts/benchmark/build_scifact_kb.py

# 快速抽样（200 文档）
python scripts/benchmark/build_scifact_kb.py --doc-limit 200 --query-limit 50

# Lexical 评测
python scripts/benchmark/run_search_benchmark.py \
  --kb benchmarks/beir_scifact/kb_gold \
  --queries benchmarks/beir_scifact/eval/queries.json \
  --qrels benchmarks/beir_scifact/eval/qrels.json

# 对比三档 KP 刻画（gold / minimal / skeleton）
for p in gold minimal skeleton; do
  echo "=== kb_$p ==="
  python scripts/benchmark/run_search_benchmark.py \
    --kb benchmarks/beir_scifact/kb_$p \
    --queries benchmarks/beir_scifact/eval/queries.json \
    --qrels benchmarks/beir_scifact/eval/qrels.json
done
```

## CI

无需下载：`pytest tests/unit/benchmark/ -q`

Fixture：`tests/fixtures/benchmark_retrieval_tiny/`（5 KP，3 queries）
