SciFact-style tiny retrieval benchmark (5 KPs, 3 queries). Used by CI; no download required.

Profiles:
- `kb_gold/` — checked-in sidecars with tags + description (default root)
- Run `python scripts/benchmark/build_scifact_kb.py --doc-limit 200` for full BEIR SciFact locally.

See `docs/design/search-retrieval-benchmark.md`.
