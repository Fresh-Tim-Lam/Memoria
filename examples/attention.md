---
description: 注意力机制的数学基础
concepts:
- id: attention
  name: 注意力机制
  weight: 1.0
  tags:
  - deep-learning
  - mechanism
- id: qkv
  name: Query-Key-Value
  weight: 0.8
- id: softmax
  name: Softmax 归一化
  weight: 0.5
- id: qkv-scoring
  name: 相似度计算
  weight: 0.4
---
# 注意力机制

注意力机制（Attention Mechanism）是深度学习中最重要的创新之一。它允许模型在处理输入序列时，动态地将计算资源分配给最相关的部分，而非均匀地处理所有信息。

注意力机制的灵感来源于人类[[视觉系统]]——我们在观察场景时，并不会同时处理所有视觉信息，而是将注意力聚焦于关键区域。类似地，神经网络中的注意力机制让模型学会"在哪里看"。

在自然语言处理中，注意力机制最早被用于机器翻译任务（Bahdanau et al., 2014），用于解决长序列编码的信息瓶颈问题。随后，它成为 [[transformer]] 架构的核心组件，彻底改变了 NLP 乃至整个深度学习领域的格局。后续的 [[bert]] 和 GPT 都建立在这一基础之上。

## Query-Key-Value

注意力计算的核心框架是 Query-Key-Value（QKV）模型，它将注意力过程类比为信息检索系统：

- **Query（查询）**：当前需要被处理的位置生成的查询向量，表示"我在找什么"
- **Key（键）**：每个位置生成的键向量，表示"我有什么特征"
- **Value（值）**：每个位置生成的值向量，表示"我的实际内容"

计算过程分为三步：

### 相似度计算

相似度计算是注意力机制的第一步。Query 与所有 Key 的点积，得到相关性得分：

$$
\mathrm{score}(q, k_i) = q \cdot k_i^{\top}
$$

点积相似度计算简单高效，但它的输出范围不受限。这也正是后续需要 Softmax 归一化的原因——将无界的得分转化为概率分布。

除了点积相似度，还有其他常见的相似度计算方式：
- **加性注意力**（Additive Attention）：$\mathrm{score}(q, k) = v^{\top} \tanh(W_q q + W_k k)$
- **双线性注意力**（Bilinear Attention）：$\mathrm{score}(q, k) = q^{\top} W k$
- **缩放点积**（Scaled Dot-Product）：$\mathrm{score}(q, k) = q \cdot k^{\top} / \sqrt{d_k}$

其中缩放点积是 Transformer 使用的形式，在效果和效率之间取得了最佳平衡。

### 权重归一化

权重归一化通过 Softmax 将点积得分转化为概率分布：

$$
\alpha_i = \mathrm{softmax}(\mathrm{score}_i) = \frac{\exp(\mathrm{score}_i)}{\sum_j \exp(\mathrm{score}_j)}
$$

归一化的作用是把无界的点积得分映射到 $(0, 1)$ 区间，使得所有位置的权重之和为 1。这样，加权后的输出可以解释为"以注意力权重聚合的信息"。

Softmax 归一化有以下关键性质：
- **单调性**：得分越高，权重越大，保持原始排序
- **可微性**：梯度流畅，适合反向传播训练
- **概率解释**：输出可以解释为"模型关注位置 $i$ 的概率"

### 加权求和

加权求和是注意力计算的最后一步，将归一化后的注意力权重与对应的 Value 向量进行加权聚合：

$$
\mathrm{output} = \sum_i \alpha_i \cdot v_i
$$

加权求和的核心思想是：模型根据学到的注意力权重，从各个位置提取信息。权重 $\alpha_i$ 越大的位置，对输出的贡献越大。

这种机制的优雅之处在于：
- **端到端可微**：整个计算链可微，适合梯度反向传播
- **软对齐**：不同于硬对齐（如 argmax），软对齐保留了对齐的不确定性
- **全局视野**：聚合了所有位置的信息，没有局部视野限制

QKV 框架的优势在于它提供了一种统一而灵活的注意力计算范式，计算复杂度为 $O(n^2)$，其中 $n$ 是序列长度，这也是后续许多工作试图优化的方向。

## Softmax 归一化

Softmax 函数将实数向量转化为概率分布：

$$
\mathrm{softmax}(z_i) = \frac{\exp(z_i)}{\sum_j \exp(z_j)}
$$

在注意力中，Softmax 的作用是将 Q-K 点积的原始得分归一化为注意力权重。它有以下重要性质：

- **非负性**：所有输出 $\in (0, 1)$，保证权重可以解释为概率
- **归一化**：所有输出之和为 1，保证信息守恒
- **可微性**：梯度良好，适合反向传播

实践中，直接对原始得分做 Softmax 会导致数值不稳定。当维度 $d_k$ 较大时，点积的方差也大，梯度可能消失。因此 Transformer 引入了缩放因子：

$$
\alpha_i = \mathrm{softmax}\left(\frac{q \cdot k_i^{\top}}{\sqrt{d_k}}\right)
$$

这个缩放使得无论 $d_k$ 多大，点积的方差保持稳定。这一看似简单的技巧对训练稳定性至关重要。

Softmax 的温度参数是另一个重要概念。将分母 $\sqrt{d_k}$ 替换为温度 $\tau$，可以控制分布的尖锐程度：
- $\tau \to 0$：趋近 one-hot，注意力集中
- $\tau \to \infty$：趋近均匀，注意力分散

Transformer 将注意力机制推到了极致，去除了 RNN 结构，完全基于注意力进行序列建模。
