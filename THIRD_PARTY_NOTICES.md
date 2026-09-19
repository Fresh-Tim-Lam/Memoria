# THIRD PARTY NOTICES

本仓库包含（或移植自）第三方开源软件的代码与语义。逐条登记如下；**每移植一块上游代码，在此追加一条**
（登记约定见 [docs/design/dsh-agent-port.md](docs/design/dsh-agent-port.md) §4）。

---

## deepseek-harness（`dsh`）

- 上游：<https://github.com/deepseek-ai/deepseek-harness>
- 本仓库跟随的 commit：**`0d1f50007f9bca3f52b06e1c3074fa14d5fb0720`**（`master`，2026-09-15T03:16:06Z；
  本文写作时 = pin `0d1f5000`）
- 上游仓库 `LICENSE`：**MIT**（原文见下）。注意：npm 包 `@deepseek-ai/dsh` 的 `license` 字段标为
  `BSD-3-Clause`，与仓库根 `LICENSE` 不一致；本仓库按**仓库 `LICENSE` = MIT** 处理，且只在
  "语义移植（按上游行为重写为 Python / 原生 JS）" 的范围内使用，不整体搬运 npm 产物。

### 移植落点（本地 → 上游包）

| 本地 | 上游包 |
|---|---|
| `src/memoria/services/agent/llm/**`（含 `providers/openai_compatible.py`、`retry.py`、`usage.py`） | `llm/llm`、`llm/llm-pi-ai`（OpenAI 兼容形态）、`llm/llm-retry`、`llm/token-meter` |
| `src/memoria/services/agent/loop.py` | `core/agent-loop` |
| `src/memoria/services/agent/prompt.py` | `core/system-prompt`、`context/agent-instructions`、`context/file-reference` |
| `src/memoria/services/agent/tools/**` | `core/tools` |
| `src/memoria/services/agent/session/**`（`store.py`、`history.py`、`query.py`、`title.py`、`reference.py`） | `core/session`、`core/scope`、`session/session-persistence-jsonl`、`session-query/*`、`session-title*`、`context/session-reference` |
| `src/memoria/services/agent/approvals.py` | `interaction/user-approval` |
| `src/memoria/services/agent/llm/config.py`（密钥"引用不落明文"部分） | `credentials/credentials-local` |
| `src/memoria/services/agent/compaction.py`、`pruner.py` | `compaction/compaction`、`compaction-basic`、`compaction-tool-result-pruner` |
| `src/memoria/ui/static/app/js/agent-panel.js` 中的 `@路径` / `dsh-session:` mention 语义 | `context/file-reference`、`context/session-reference`（`uri.ts`） |

**未移植**：`api/*`、`sdk/*`、`bundle/*`、`sandbox/*`、`shell/*`、`terminal/*`、`subprocess/*`、`ssh/*`、
`lsp/*`、`mcp/*`、`browser-use/*`、`computer-use/*`、`subagent/*`、`workflow/*`、`jobs/*`、`schedule/*`、
`native/*`、`skill/*`、`hooks/*`、`guard/*`、`plan/*`、`goal/*`、`todo/*`（逐条理由见
[docs/design/dsh-agent-port.md](docs/design/dsh-agent-port.md) §5）。

### 上游许可证原文（MIT，逐字保留）

```
MIT License

Copyright (c) 2026 DeepSeek

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 第三方运行时（随包分发，非源码移植）

| 组件 | 许可 | 说明 |
|---|---|---|
| MathJax（`src/memoria/ui/static/vendor/mathjax/**`） | Apache-2.0 | 预览区公式渲染 |
| marked / mermaid 等 `vendor/**` 前端库 | 见各目录随附文件 | 预览与图谱渲染 |
