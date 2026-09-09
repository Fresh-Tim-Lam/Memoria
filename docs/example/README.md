[中文](README.cn.md) | English

# Examples and Local Knowledge Bases

`docs/example/` is the unified container for the repository's "example knowledge bases" (see `docs/conventions/docs-management.md`).

| Path | Purpose | Kept in the repo for display? |
|---|---|---|
| `showcase/` | **Official showcase sample**: Introduction to Machine Learning (a full demo of styling / images / links / search) | ✅ |
| `import-test/` | Import test fixtures (regression tests for the flat / md-dir / kb-bundle flows of import) | ✅ (test asset) |
| `rename-test/` | Rename test KB: KPs with ranges/tags/aliases, `[[kp-id]]` jumps, a pure-file (stem) reference and image refs, laid out across root / 2-level / 3-level / same-dir / empty-dir structures, to verify file & folder rename self-maintenance | ✅ (test asset) |
| `AAA_*`, `example-boonie/`, `example-english-kb/`, `examples/` (legacy), `rich-content-test/`, `人工智能导论知识点汇总/`, `description_of_kb.md`, etc. | Old samples / personal knowledge bases / development-time tests | Kept locally, not committed to the repo |

To try the official showcase library in Memoria:

1. Open a Knowledge Base → choose the directory `docs/example/showcase/`
2. Start from `README.md` or `overview.md` and roam along the links
3. Integrity self-check: `python -m memoria.cli.main validate docs/example/showcase`
