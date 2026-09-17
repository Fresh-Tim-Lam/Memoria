# 第三方声明（Third-Party Notices）

> **用途**：登记 Memoria 中包含或**派生于**第三方代码的部分及其许可与版权声明。
> **规则**：① 每引入/移植一块第三方代码，必须在此追加条目（来源仓库 + **pin 的 commit** + 许可 + 移植了什么）；② 相应源文件头部必须带来源注释；③ 许可原文**逐字保留**，不得改写或翻译；④ 若同一上游存在多处许可声明不一致，按**最严格者**处理。
> **本仓库自身许可**：MIT —— 见 [LICENSE](./LICENSE)（`Copyright (c) 2026 FreshTim`）。

---

## 1. DeepSeek Harness（`dsh`）

| 项 | 值 |
|---|---|
| 来源仓库 | <https://github.com/deepseek-ai/deepseek-harness> |
| 锁定版本 | commit `0d1f50007f9bca3f52b06e1c3074fa14d5fb0720`（`master`，2026-09-15T03:16:06Z） |
| 上游仓库许可 | **MIT**（仓库根 `LICENSE`，`Copyright (c) 2026 DeepSeek`）—— 原文见 §1.2 |
| 包元数据许可 | npm `@deepseek-ai/dsh` 的 `license` 字段声明 **BSD-3-Clause**；PyPI `deepseek-harness-sdk` 声明 MIT ⇒ 两处不一致，故**并行遵守 BSD-3-Clause 的额外要求**（§1.3） |
| 使用方式 | **语义移植（Python 重写）**，非逐行复制；**不包含**上游品牌资产（logo、`BRAND_GUIDELINES*`） |
| 不背书声明 | 本项目与 DeepSeek 无隶属或合作关系；不使用 `DeepSeek` / `dsh` 的名义为 Memoria 或其派生作品做背书或推广 |

### 1.1 已移植清单

| 上游路径 | 本地落点 | 阶段 | 移植内容 |
|---|---|---|---|
| `packages/llm/llm` | `src/memoria/services/agent/llm/` | M1 | provider 中立的模型调用语义（请求 / 流式 / 用量 / 取消） |
| `packages/llm/llm-pi-ai`（仅 OpenAI 兼容部分） | `src/memoria/services/agent/llm/providers/openai_compatible.py` | M1 | OpenAI 兼容端点适配 |
| `packages/llm/llm-retry` | `src/memoria/services/agent/llm/retry.py` | M1 | 重试 / 退避语义 |
| `packages/llm/token-meter` | `src/memoria/services/agent/llm/usage.py` | M1 | 用量计量语义 |
| `packages/core/*`、`packages/session/*`、`packages/context/*`、`packages/interaction/*`、`packages/credentials/*` | 待定（见 `docs/design/dsh-agent-port.md` §5–§6） | M1 后续 | 每吃一块在此追加一行 |

### 1.2 上游许可原文（MIT，逐字保留）

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

### 1.3 BSD-3-Clause 额外要求（因 npm 字段声明而并行遵守）

> Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

（即：不得用 `DeepSeek` 或其贡献者的名义为 Memoria 或派生作品背书或推广。）

---

## 2. 其它第三方组件（待补）

| 组件 | 许可 | 位置 | 备注 |
|---|---|---|---|
| MathJax | 待核 | `src/memoria/ui/static/vendor/mathjax/**` | 前端公式渲染 |
| mermaid | 待核 | `src/memoria/ui/static/app/vendor/mermaid.min.js` | 图表渲染 |
| three.js | 待核 | `src/memoria/ui/static/app/lib/three.min.js` | 3D 图谱 |
| Python 依赖（`requirements.txt`） | 待核 | `requirements.txt` | 各自许可需登记 |

> 本节为既有组件的补登记清单，非本次移植引入；核对后逐行补全（含各许可原文或指向其分发页的链接）。

---

## 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-17 | 初版：登记 DeepSeek Harness（pin `0d1f5000`；MIT 原文逐字保留；npm 字段 `BSD-3-Clause` 差异说明与并行遵守条款；已移植清单）；建立"其它第三方组件"待补表 |
