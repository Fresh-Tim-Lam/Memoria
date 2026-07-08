---
description: Transformer 自注意力架构
concepts:
- id: transformer
  name: Transformer 架构
  weight: 1.0
  tags:
  - nlp
  - attention
  - deep-learning
  - sequence-modeling
- id: self-attention
  name: 自注意力机制
  weight: 0.9
- id: positional-encoding
  name: 位置编码
  weight: 0.6
- id: multi-head-attention
  name: 多头注意力
  weight: 0.8
---
# [[Transformer]] 架构

Transformer（Vaswani et al., "Attention Is All You Need", 2017）是一种基于自注意力机制的序列建模架构。它完全摒弃了 RNN 和 CNN 的循环与卷积结构，仅依赖注意力机制进行全局依赖建模，实现了前所未有的并行化能力。Transformer 的理论基础来[[Transformer]]mer 是 [[bert]] 和 GPT 的基础架构。

[[Transformer]] 的核心思想是：用注意力替代递归。RNN 必须逐步处理序列，难以并行化；而 Transformer 的自注意力可以同时关注序列中的所有位置，天然支持并行计算。

架构由 Encoder 和 Decoder 两部分组成：
- **Encoder**：6 层相同结构，每层包含自注意力子层 + 前馈网络子层
- **Decoder**：6 层相同结构，在 Encoder 基础上增加交叉注意力子层

每个子层都使用残差连接和 Layer Normalization：

$$
\mathrm{output} = \mathrm{LayerNorm}\bigl(x + \mathrm{Sublayer}(x)\bigr)
$$

## 自注意力机制

自注意力（Self-Attention）是 [[Transformer]] 的核心操作。它让序列中的每个位置都能直接关注到其他所有位置，从而捕获任意距离的依赖关系。

$$
\mathrm{Attention}(Q, K, V) = \mathrm{softmax}\!\left(\frac{QK^{\top}}{\sqrt{d_k}}\right) V
$$

其中 $Q$、$K$、$V$ 均来自同一输入序列的线性变换：

$$
Q = XW_Q,\quad K = XW_K,\quad V = XW_V
$$

缩放因子 $\sqrt{d_k}$ 的作用是防止点积值过大导致 Softmax 梯度消失。当 $d_k = 64$ 时，点积的方差为 64，除以 $\sqrt{64} = 8$ 后方差回到 1。

自注意力的计算复杂度为 $O(n^2 d)$，其中 $n$ 是序列长度，$d$ 是维度。对于长序列，这会成为瓶颈。后续工作如 Linformer、Performer 等试图将复杂度降到线性。

## 多头注意力

多头注意力将注意力空间划分为多个子空间，每个头学习不同的注意力模式。直觉上，不同的头可以关注不同类型的关系——语法关系、语义关系、位置关系等。

$$
\mathrm{MultiHead}(Q, K, V) = \mathrm{Concat}(\mathrm{head}_1, \ldots, \mathrm{head}_h) W_O
$$

其中每个头：

$$
\mathrm{head}_i = \mathrm{Attention}(QW_i^Q, KW_i^K, VW_i^V)
$$

典型设置：$h = 8$ 头，$d_k = d_v = d_{\mathrm{model}} / h = 64$。

多头注意力的关键优势：
1. **多样性**：不同头可以关注不同子空间的信息
2. **稳定性**：多个小注意力比一个大注意力更稳定
3. **效率**：总计算量与单头全维度注意力相当

在实践中，注意力头的可视化显示，不同的头确实学到了不同的模式：有的头关注相邻词，有的头关注语法结构，有的头关注长距离依赖。

## 位置编码

由于 [[Transformer]] 完全没有循环和卷积结构，它对序列中元素的顺序是不敏感的。为了让模型利用位置信息，必须显式注入位置编码。

原始 [[Transformer]] 使用正弦/余弦位置编码：

$$
\mathrm{PE}(\mathrm{pos}, 2i) = \sin\!\left(\mathrm{pos} / 10000^{2i/d}\right)
$$

$$
\mathrm{PE}(\mathrm{pos}, 2i+1) = \cos\!\left(\mathrm{pos} / 10000^{2i/d}\right)
$$

这种编码有两个重要特性：
1. **确定性**：不需要学习，适用于任意长度序列
2. **相对位置**：对于任意固定偏移 $k$，$\mathrm{PE}(\mathrm{pos}+k)$ 可以表示为 $\mathrm{PE}(\mathrm{pos})$ 的线性函数

后来的工作提出了可学习的位置编码（如 BERT）和旋转位置编码（RoPE），各有优劣。

BERT 和 GPT 是 [[Transformer]] 的两大应用方向。BERT 使用 Encoder 部分，擅长理解任务；GPT 使用 Decoder 部分，擅长生成任务。
