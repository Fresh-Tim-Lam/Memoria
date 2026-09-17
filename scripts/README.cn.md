[English](README.md) | 中文

# scripts/ — 开发者工具

**正式可复用**的开发者工具目录。与 `packaging/` 职责分离：`scripts/` = 开发工具，`packaging/` = 打包发布。

## 内容

| 文件/目录 | 用途 |
|-----------|------|
| `run_dev.ps1` | 开发态启动：源码 + pywebview 壳 + DevTools + 无边框（`MEMORIA_MODE=dev`） |
| `graph_layout_benchmark.py` / `.mjs` | 图谱布局压力基准（2D/3D 布局 + 分组计算） |
| `benchmark/` | 检索评估工具集（lexical / embedding / rerank 评测跑批） |
| `screenshots/` | README / 文档截图采集：热键触发抓窗口客户区（带重复帧识别） |
| `bootstrap_example_sidecars.py` | 生成示例知识库 sidecar |
| `gen_example_boonie_sidecars.py` | 生成 boonie 示例知识库 sidecar |
| `scan_ui_strings.py` | UI 界面文案清单扫描器：刷新 `docs/reference/i18n-inventory.md`（i18n 盘点） |
| `i18n_selftest.js` | i18n 引擎自测：`node scripts/i18n_selftest.js`（默认语言/切换/缺键回退/参数填充） |
| `agent_llm_smoke.py` | 智能体 LLM 冒烟工具（dsh 移植 M1）：向已配置端点流式要一句回答并打印用量；`--mock` 起内置假 SSE 端点，**离线可跑**。配置读 `MEMORIA_AGENT_BASE_URL` / `MEMORIA_AGENT_API_KEY` / `MEMORIA_AGENT_MODEL`（密钥永不打印） |
| `agent_ask.py` | 智能体端到端问答工具（dsh 移植 M1）：`--kb <路径> "问题"` 跑**只读** agent 循环（检索 / 读文档 / 概览 / 校验四个工具），打印回答 + `文件:行号` 锚点 + 用量 + 会话文件；`--mock` 用脚本化假 provider（不联网）。**除 `<kb>/.memoria/agent/sessions/*.jsonl` 外不写知识库** |

## 规则

- 临时/一次性脚本禁止放这里 → `artifacts/`
- 检索评估数据与结果 → `benchmarks/`
- 打包相关脚本 → `packaging/`
