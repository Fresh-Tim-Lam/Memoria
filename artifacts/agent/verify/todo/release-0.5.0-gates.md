
# 0.5.0 发版门禁证据（Lead 亲跑，2026-10-25 12:17:32)

## 门禁结果
| # | 门禁 | 结果 | 证据 |
|---|---|---|---|
| 1 | 全量 pytest | **1464 passed / 0 failed** | 本次输出 |
| 2 | py_compile 全部 src | **0 失败** | 逐文件跑 |
| 3 | node --check 前端 JS | N/A（presentation 下 0 个 .js 文件） | - |
| 4 | 活跃 node 内核测试 | **全 PASS**（agent_stream_buffer / blockquote_roundtrip / blockquote_typing_sequence / block_index） | 本次输出 |
| 5 | S1-S5 全部验收夹具（11 个） | **11/11 PASS** | 逐个跑 |
| 6 | 12 个交互剧本 | **未跑（登记为门禁缺口）** | 见下 |

## 门禁 6 的诚实说明（不谎称 12/12）
12 个交互剧本（`scripts/benchmark/surface/scenarios/`）需要**运行中的 app + CDP 端口**（`openfile-race.mjs` 里 `http://127.0.0.1:\/json/list`），属真机交互门禁。

**本轮未跑的理由（可验证）**：
- `git diff --name-only v0.4.6..HEAD` 中**前端源文件（js/mjs/css/html）改动数 = 0**
- `src/memoria/presentation` 只有 1 个文件改动：`api/ui.py`（Python，仅加 `origin="human"` 参数），不涉及渲染/选区/块
- 12 剧本测的是选区 anchor/focus + 块文本 + KP 联动 —— 本版**完全未触碰**这些路径

⇒ 判定：不在影响面内。但**这是"判定"不是"实测"**，如实登记为发版已知缺口，
下个版本若动前端必须补跑。

## 排除的 2 个"失败"
`nested_list_test.mjs` / `nested_list_edit_test.mjs` 实际位于 `scripts/benchmark/archive/maintenance/`
（commit `f5c3fcbb` 已归档的 12 个无入口一次性探针），不是活跃门禁。首次门禁脚本用
`-match "maintenance"` 误捞到归档路径，故显示 MODULE_NOT_FOUND。**非真实失败。**