---
description: Memoria 官方展示样例库——机器学习导论
---

# Memoria 官方展示样例库：机器学习导论

这是一个用于**完整展示 Memoria 能力**的官方样例知识库：内容丰富、排版多样、链接密集、带图片与搜索别名。把它当作“产品的说明书”，逐页点开即可体验。

## 快速开始

1. 在 Memoria 中把知识库根目录设为 **`examples/`**（本文件夹）。
2. 从任意一页开始阅读；点击正文中的蓝色链接在知识点之间跳转，左侧知识面板会同步高亮。
3. 打开“知识检查”面板执行一次完整性校验，或命令行运行：

```bash
python -m memoria.cli.main validate docs/example/showcase
```

## 内容地图（阅读路径）

| 页面 | 内容 | 覆盖的能力点 |
|---|---|---|
| [overview.md](./overview.md) | 机器学习总览与三大范式 | 入口概念、跨页链接、图片 |
| [supervised.md](./supervised.md) | 回归、分类、SVM、特征工程、评估 | 公式、图表、代码块 |
| [tree-ensemble.md](./tree-ensemble.md) | 决策树、随机森林、GBDT | Mermaid、表格、扩展关系 |
| [neural-network.md](./neural-network.md) | 感知机、MLP、激活、反向传播、损失 | 公式、图片属性 |
| [deep-learning.md](./deep-learning.md) | 词嵌入、CNN、RNN、注意力、Transformer | 架构图、多范式链接 |
| [unsupervised.md](./unsupervised.md) | 聚类、K-Means、层次聚类、PCA | 公式、嵌套列表 |
| [rl-intro.md](./rl-intro.md) | 强化学习：MDP、贝尔曼方程、策略梯度 | 公式、概念链 |
| [styles-gallery.md](./styles-gallery.md) | 功能图鉴：样式/图片/链接/搜索演示 | 高亮、嵌套、边模式、同义词 |

## 功能演示速查

- **样式文本**：高亮 `[[\h]]`、字色 `[[\c]]`、字号 `[[\s]]`、上下标、多级引用与嵌套列表 → [styles-gallery.md](./styles-gallery.md)「样式与文本演示」
- **图片模块**：默认 / 定宽 / 居中 / 右对齐 / 纯标题 / 隐藏名称 / Lightbox → 「图片样式演示」
- **链接设计**：reference / extend 边、多目标链接、环路、悬空虚链 → 「链接与关系模式」
- **模糊搜索**：别名（如“最小二乘”命中线性回归）→ 「搜索与同义词演示」

## 悬空虚链演示

下方两个链接指向**尚未建立知识点**的概念：预览中它们显示为灰色、点击不可跳转（broken 链接），且 Memoria 不会为悬空目标自动创建空文件：

- [[auto-ml|自动机器学习]]
- [[llm-agents|大模型智能体]]

## 与其它样例的关系

`examples/` 是本仓库的**官方展示样例**（随发布包分发到 `resources/examples/`）；`docs/example/` 下另有开发期测试与个人知识库（不入库展示）。

## 维护提示

- 知识点（KP）与链接记录在 `.memoria/sidecars/*.memoria.yaml`；正文段落顺序与侧车 `range.snippet` 锚句对应。
- 修改正文后运行上方 validate 命令自查；`.memoria/cache/` 等运行时产物不入库。
