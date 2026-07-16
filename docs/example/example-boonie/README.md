# 熊出没样例知识库

独立于 `examples/`（RL/NLP 开发样例）的叙事型 KB，设计说明见 [`docs/description_of_kb.md`](../docs/description_of_kb.md)。

## 快速开始

1. 在 Memoria 中将知识库根目录设为 **`example-boonie/`**（本文件夹）。
2. 打开 Hub：`dog-xiong-ridge.md`，按「阅读路径」依次点击 wikilink。
3. 侧车位于 `.memoria/sidecars/`。

## 目录结构

```
example-boonie/
├── dog-xiong-ridge.md      # Hub 入口
├── guang-tou-qiang.md
├── bear-brothers.md
├── inventions-and-events.md
├── minor-characters.md
├── _nothing-here.md        # 无 KP 边界样例
└── .memoria/sidecars/*.memoria.yaml
```

## 维护侧车

修改正文 KP 范围或 wikilink 后，在仓库根目录执行：

```bash
python scripts/gen_example_boonie_sidecars.py
```

## 与 design 文档的关系

- **E / F 节**：完整设计草稿（长正文 + 设计侧车），保留在 `docs/description_of_kb.md`。
- **本目录**：可运行的精简实现（含 `[[wikilink]]`、15 个 KP、Hub 阅读路径与虚链演示）。
