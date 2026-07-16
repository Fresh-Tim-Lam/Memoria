# 知识库级元数据目录 `.memoria/`

与 `designV0.md` §6.3 一致，与 Markdown 正文分离存放。

```
examples/
├── mdp.md                          # 正文（仅链接标记 + 可选 frontmatter 摘要）
├── attention.md
└── .memoria/
    ├── sidecars/                   # 侧车：镜像 md 相对路径
    │   ├── mdp.memoria.yaml
    │   └── attention.memoria.yaml
    │   └── module/foo.memoria.yaml # 若 md 在子目录 module/foo.md
    ├── manifest.yaml               # (M3+) 增量索引清单
    ├── pending.yaml                # (M3+) 未确认候选 KP
    └── cache/                      # (M4+) 检索缓存，可删可重建
```

**配对规则**：`notes/rl.md` ↔ `.memoria/sidecars/notes/rl.memoria.yaml`

移动/重命名 md 时，侧车文件与 `file:` 字段需同步更新（M3 实现级联）。
