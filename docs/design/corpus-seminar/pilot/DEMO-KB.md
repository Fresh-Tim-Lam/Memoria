# Demo KB（开发态示例库）— 看效果用

> **用途**：把 corpus pilot 的 Tier-A 章节 + 机器候选 KP/边变成 Memoria 可打开的示例库，用来看真实编辑器/图谱效果。
> **不是** gold，不是 C0 gate，不进发布包，不写用户库。

## 位置

`artifacts/demo-kb/corpus-pilot/`

- `chapter1.md`：OpenStax《Introduction to Business》Chapter 1（CC BY 4.0），126k 字符；
- `.memoria/sidecars/chapter1.memoria.yaml`：50 个 KP 候选 + 30 条边候选（`contain` 在 demo 中映射为 `reference`，因产品 sidecar 仅允许 reference/extend）；
- `.memoria/manifest.yaml`：示例库清单。

## 打开

```powershell
cd D:\AAA_Jupyter\Memoria
$env:MEMORIA_MODE='dev'
$env:MEMORIA_KB='D:\AAA_Jupyter\Memoria\artifacts\demo-kb\corpus-pilot'
python tools\dev-annotator\run_with_remote_debug.py
```

另开终端注入批注板：

```powershell
python tools\dev-annotator\inject_via_cdp.py 9222
```

批注板在右下角；Alt+Shift+A 开关点选；点元素后编辑文字/批注，导出 `memoria-annotations.jsonl`。

## 限制

- KPs/边是机器候选，不是人类 gold；
- `contain` 边在 demo sidecar 中映射为 `reference`（产品 sidecar 不支持 contain）；
- 示例库在 `artifacts/` 下，gitignore，不随发布交付；
- 0.5 仍 HOLD。
