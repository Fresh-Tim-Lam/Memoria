# 前端 vendor 依赖（离线 bundled）

| 文件 | 用途 |
|------|------|
| `marked.min.js` | GFM Markdown 解析 |
| `mathjax/es5/tex-chtml-full.js` | MathJax 3 全量 TeX 组件（最高 LaTeX 兼容） |
| `mathjax/es5/output/chtml/fonts/woff-v2/*.woff` | 公式字体（离线渲染必需） |
| `mathjax/es5/input/tex/extensions/*.js` | 可选扩展（full bundle 已内置大部分） |

公式写法：行内 `$...$`，块级 `$$...$$` 或 `\[...\]`。

未包裹的伪公式（如 `α_i = ...`）会由 `m0/js/math-normalize.js` 自动转换。
