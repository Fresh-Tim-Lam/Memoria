# Dev annotation board

开发态专用：给 Memoria 页面注入一个「点选元素 → 编辑文字/批注 → 导出 JSONL」的批注板。**不属于产品构建**，不改 `src/**`。

## 启动（Windows / 当前 demo）

```powershell
cd D:\AAA_Jupyter\Memoria
$env:MEMORIA_MODE='dev'
$env:MEMORIA_KB='D:\AAA_Jupyter\Memoria\artifacts\demo-kb\corpus-pilot'
python tools\dev-annotator\run_with_remote_debug.py
```

另开一个终端注入：

```powershell
python tools\dev-annotator\inject_via_cdp.py 9222
```

- 批注板在右下角；按 **Alt+Shift+A** 开关点选模式；
- 点选任意元素 → 自动填 CSS selector / 原文，可编辑批注与原文；
- **导出 JSONL** 会下载 `memoria-annotations.jsonl`（可直接发回）；
- 数据同时保存在 localStorage `memoria.dev.annotations.v1`；
- 这是 dev-only 注入：WebView2 远程调试端口 + CDP，不写产品代码、不写用户库。

## 示例库

`scripts/corpus/build_demo_kb.py` 会从 pilot 的 Tier-A 章节 + 50 KP/30 边候选生成：

```
artifacts/demo-kb/corpus-pilot/
  chapter1.md
  .memoria/sidecars/chapter1.memoria.yaml
  .memoria/manifest.yaml
```

只用于看效果，不是 gold，也不进发布包。
