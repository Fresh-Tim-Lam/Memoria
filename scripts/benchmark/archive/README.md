# scripts/benchmark/archive/ —— 一次性探针归档（2026-10-24）

## 为什么在这里
这些脚本是**一次性验证探针**：为某一次具体的修复/优化提供证据，验完即完成使命。
它们不再被任何代码、测试、文档或 CI 引用（`dead_path_edit` 机检实测 `external_refs=0`）。

## 为什么归档而不是删除
- 部分脚本是**真机基线工具**（如 `realapp_humanlike.mjs`），将来复测可能需要
- 归档保留可回溯性，同时让 `scripts/benchmark/` 下的"当前有效工具"边界清楚
- `git log --follow` 仍能追到完整历史

## 清单
| 归档文件 | 原位置 | 何时产出 | 使命 |
|---|---|---|---|
| `maintenance/executor_coalesce_assert.py` | `maintenance/` | 2026-10-24 `26fa9bc6` | 验证 `submit(coalesce_running=True)` 的 `executed 2→1` |
| `maintenance/lexical_index_cache_bench.py` | `maintenance/` | 2026-10-24 `14290c3b` | 验证词法索引缓存 `13259.6ms → 47.5ms` |
| `maintenance/nested_list_edit_test.mjs` | `maintenance/` | 2026-10-23 `842a08ba` | 0.4.7 任务4 嵌套列表编辑 |
| `maintenance/nested_list_test.mjs` | `maintenance/` | 2026-10-23 `c09b4a09` | 多级列表解析 |
| `maintenance/_bugc_doc_check.js` | `maintenance/` | 2026-10-23 `80b93415` | Bug C 文档检查 |
| `surface/run_block_count.py` | `surface/` | 2026-10-23 `9bdb1211` | 块计数探针 |
| `surface/perf_tail_ab.mjs` | `surface/` | 2026-10-23 `b92c58a7` | W3.3 批尾布局 A/B |
| `surface/perf_tail_drift.mjs` | `surface/` | 2026-10-23 `b92c58a7` | W3.3 批尾漂移 |
| `surface/perf_tail_edit_l5.mjs` | `surface/` | 2026-10-23 `b92c58a7` | W3.3 批尾编辑 L5 |
| `surface/selcol_ask_probe.mjs` | `surface/` | 2026-10-21 `81ae5fb8` | 选区/光标探针 |
| `surface/realapp_humanlike.mjs` | `surface/` | 2026-10-20 `1ba90d88` | 真机类人基线 |

> `make_link_fixture.py` 在机检输出里被列为候选，但该路径**不存在**（工作区未跟踪）——
> 已确认无此文件，未归档。

## 如果要复活某个脚本
`git mv scripts/benchmark/archive/<group>/<file> scripts/benchmark/<group>/` 并在使用处加 `@entry` 标记，
避免 `dead_path_edit` 再报它。
