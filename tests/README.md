[中文](README.cn.md) | English

# tests/ — Unit / integration tests

pytest test directory (`testpaths = ["tests"]` in `pyproject.toml`).

## Structure

| Path | Responsibility |
|------|----------------|
| `fixtures/` | Test fixtures (sample knowledge bases, small retrieval-benchmark corpora, etc.) |
| `.memoria/` | Knowledge-base metadata for tests (manifest/pending/cache) |

## Run

```powershell
pytest
```

## Rules

- Official test code goes here; one-off debug scripts go in `artifacts/`
- Batch scripts involving retrieval evaluation go in `scripts/benchmark/`, with data and results in `benchmarks/`
