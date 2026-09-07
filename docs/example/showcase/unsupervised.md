---
description: 无监督学习：聚类、K-Means、层次聚类与主成分分析
concepts:
  - id: unsupervised
    name: 无监督学习概览
    weight: 1.0
    tags: [无监督, 概览]
  - id: clustering
    name: 聚类
    weight: 0.9
    tags: [无监督, 任务]
  - id: kmeans
    name: K-Means 聚类
    weight: 0.8
    tags: [聚类, 算法]
  - id: hierarchical
    name: 层次聚类
    weight: 0.6
    tags: [聚类, 算法]
  - id: pca
    name: 主成分分析
    weight: 0.9
    tags: [降维, 算法]
---

## 无监督学习概览

无监督学习在没有标签的数据上寻找结构，两大任务是 [[clustering|聚类]]（把样本分群）与[[pca|降维]]（压缩数据但仍保信息）。它常作为监督任务的预处理，也用于探索性分析。

无监督并非“没有标准答案就无从评估”，而是换了一套评估口径：簇内紧、簇间散，或降维后的信息保留率。

## 聚类

聚类把相似的样本归为一类，目标是“类内距离小、类间距离大”。难点在于相似度度量与簇数 K 的选择——肘部法则通过看损失曲线拐点来选 K。

代表算法有中心式的 [[kmeans|K-Means]] 与层次式的 [[hierarchical|层次聚类]]。聚类结果的“正确性”常依赖业务解释，这也是无监督问题的通性。

## K-Means 聚类

K-Means 交替执行两步：把每个样本分给最近的质心，再让质心移动到所属簇的均值。目标函数是类内平方和：

$$
\arg\min_{C} \sum_{j=1}^{k} \sum_{x \in C_j} \left\lVert x - \mu_j \right\rVert^2
$$

K-Means 简单高效，但初值敏感、假设簇近似球形；实践上用 K-Means++ 初始化并多次运行取最优。

## 层次聚类

层次聚类不预设簇数，而是不断合并（凝聚式）或分裂最近的两簇，生成一棵“树”即树状图；沿着树在任意高度切一刀，就得到对应粒度的聚类。

相比 K-Means，层次聚类能揭示簇的嵌套结构，代价是 $O(n^2)$ 起步的复杂度，不适合超大数据。

## 主成分分析

主成分分析寻找方差最大的正交投影方向，把高维数据压到低维。前 r 个主成分尽量保留原始方差：

$$
X \approx U_r \Sigma_r V_r^{\top}, \qquad \text{保留率} = \frac{\sum_{i=1}^{r}\sigma_i^2}{\sum_{i=1}^{n}\sigma_i^2}
$$

PCA 常用于可视化（降到 2/3 维）与去相关。它与[[linear-regression|线性回归]]同属线性模型，但一个是找方差方向、一个是拟合标签，用途不同。

无监督得到的低维表示也常作为 [[supervised|监督学习]] 的输入特征。
