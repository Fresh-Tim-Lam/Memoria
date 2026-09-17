# site/ — 公开指引页（GitHub Pages 站点源）

> **职责**：存放**可直接部署的静态站点**——目前是《IELTS 词汇教练 · 上手与部署指引》的中英双版页面。
> 与 `docs/` 的区别：`docs/` 是仓库文档（读）；这里是**发布物**（会被 GitHub Actions 原样上传成站点）。

| 文件 | 说明 |
|---|---|
| `index.html` | 站点落地页：中文 / English / 「这页怎么部署的」三段，样式内联、无外部依赖 |
| `GUIDE.md` | 同一份内容的 Markdown 版（便于 diff、也可在 GitHub 上直接读） |
| `images/` | 页面配图 12 张，一律用相对路径 `images/xxx.png` 引用 |

## 部署

```powershell
# 一次设置（人工，仅需一次）
仓库 Settings → Pages → Source = GitHub Actions
# 之后：改 site/** 并 push → workflow 自动重建
# 站点：https://fresh-tim-lam.github.io/Memoria/
```

- 发布由 [.github/workflows/pages.yml](../.github/workflows/pages.yml) 完成：`actions/upload-pages-artifact` 的 `path:` 指向本目录，**只有本目录**上站。
- **改内容要改两处**：`index.html` 与 `GUIDE.md` 内容一致，改一份记得同步另一份。
- 词汇库本体不在这里，在 [`docs/example/AAA_Vocab/`](../docs/example/AAA_Vocab/)。
