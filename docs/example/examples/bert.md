---
description: BERT 预训练语言模型
concepts:
- id: bert
  name: BERT
  weight: 1.0
  tags:
  - nlp
  - pre-training
  - encoder
- id: mlm
  name: 掩码语言模型
  weight: 0.8
- id: nsp
  name: 下一句预测
  weight: 0.7
---
# BERT

BERT（Bidirectional Encoder Representations from Transformers，Devlin et al., 2018）是一种双向预训练语言模型。它仅使用 [[transformer]] 的 Encoder 部分，通过在大规模无标注语料上的自监督预训练，学习深层双向语言表示。

BERT 的出现标志着 NLP 领域预训练-微调范式的成熟。在 BERT 之前，ELMo 提供了上下文相关的词表示，GPT 展示了单向预训练的潜力，而 BERT 证明了双向预训练的巨大优势。

BERT 的模型结构非常简洁：
- **BERT-Base**：12 层 Transformer Encoder，768 隐藏维度，12 注意力头，110M 参数
- **BERT-Large**：24 层 Transformer Encoder，1024 隐藏维度，16 注意力头，340M 参数

输入表示使用 WordPiece 分词，加上 [CLS] 和 [SEP] 特殊标记。位置编码采用可学习的方式，而非原始 Transformer 的正弦编码。

## 掩码语言模型

掩码语言模型（Masked Language Model, MLM）是 BERT 的核心预训练任务。它随机遮蔽输入中 $15\%$ 的 token，让模型根据上下文预测被遮蔽的词。

MLM 的训练过程：
1. 随机选择 $15\%$ 的输入 token
2. 对选中的 token：
   - $80\%$ 替换为 [MASK]
   - $10\%$ 替换为随机词
   - $10\%$ 保持不变
3. 只对被遮蔽的位置计算交叉熵损失

这种设计的精妙之处：
- **双向性**：不像 GPT 只能看前文，MLM 可以同时利用左右上下文
- **随机替换**：$10\%$ 的随机替换让模型学到更多的词汇关系
- **保持不变**：$10\%$ 的保持不变缓解了预训练和微调之间的差异

$15\%$ 的遮蔽率是经过实验验证的平衡点——太高则上下文信息不足，太低则训练信号太少。

## 下一句预测

下一句预测（Next Sentence Prediction, NSP）是 BERT 的第二个预训练任务，旨在帮助模型学习句子间的关系。

NSP 是一个二分类任务：
- **正例**：句子 B 确实是句子 A 的下一句（$50\%$）
- **负例**：句子 B 是从语料库中随机采样的（$50\%$）

模型使用 [CLS] 标记的输出表示进行分类。

NSP 的直觉是：许多下游任务（如问答、自然语言推理）需要理解句子间的关系，而不仅仅是词级别的关系。

然而，后续研究（ALBERT、RoBERTa）发现 NSP 任务可能并不如预期重要。RoBERTa 移除了 NSP 任务后性能反而更好，可能是因为 NSP 作为一个相对简单的任务，提供的训练信号有限。

BERT 在 11 项 NLP 基准测试上达到了 SOTA，开创了"预训练-微调"的范式。它的成功催生了大量后续工作，包括 RoBERTa、ALBERT、ELECTRA 等。
