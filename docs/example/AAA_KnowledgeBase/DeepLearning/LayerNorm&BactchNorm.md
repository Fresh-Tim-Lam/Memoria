# LayerNorm 与 BatchNorm 完整对比报告

## 0. 论文来源

| 方法 | 论文 | 作者 | 发表 |
|------|------|------|------|
| **BatchNorm** | Batch Normalization: Accelerating Deep Network Training by Reducing Internal Covariate Shift | Sergey Ioffe, Christian Szegedy | ICML 2015 |
| **LayerNorm** | Layer Normalization | Jimmy Lei Ba, Jamie Ryan Kiros, Geoffrey E. Hinton | arXiv:1607.06450, 2016 |


## 1. 算法概述

### 1.1 Batch Normalization

**一句话定位**：BatchNorm 通过对**同一个 batch 内所有样本的同一特征通道**进行归一化，使每层输入保持稳定分布，从而加速深度网络训练。

**设计动机**：解决深度网络训练中的**内部协变量偏移（Internal Covariate Shift）**问题——即网络参数更新导致每层输入分布发生变化，迫使后层网络不断适应前层分布变化，拖慢训练。

### 1.2 Layer Normalization

**一句话定位**：LayerNorm 通过对**同一样本的所有特征通道**进行归一化，使每层输入保持稳定分布，特别适用于 RNN 等可变长度序列数据。

**设计动机**：BatchNorm 依赖于 batch 维度，在 batch size 较小或处理可变长度序列（如 RNN/LSTM）时效果不佳。LayerNorm 不依赖 batch 维度，对**单个样本**的所有特征进行归一化，天然适用于这些场景。


## 2. 数学定义

### 2.1 Batch Normalization 的数学定义

对于 mini-batch $\mathcal{B} = \{x_1, x_2, \ldots, x_m\}$，其中每个样本 $x_i \in \mathbb{R}^d$：

**Step 1: 计算 batch 均值和方差**（沿 batch 维度 $m$）

$$
\mu_{\mathcal{B}} = \frac{1}{m} \sum_{i=1}^{m} x_i
$$

$$
\sigma_{\mathcal{B}}^2 = \frac{1}{m} \sum_{i=1}^{m} (x_i - \mu_{\mathcal{B}})^2
$$

**Step 2: 归一化**

$$
\hat{x}_i = \frac{x_i - \mu_{\mathcal{B}}}{\sqrt{\sigma_{\mathcal{B}}^2 + \epsilon}}
$$

**Step 3: 缩放和平移**（可学习参数）

$$
y_i = \gamma \hat{x}_i + \beta
$$

其中 $\gamma$ 和 $\beta$ 是每个特征维度独立学习的参数，$\epsilon$ 是为数值稳定性添加的小常数。

**训练时**：使用当前 batch 的均值和方差。

**推理时**：使用训练阶段累积的**全局均值和方差**（指数移动平均）。

### 2.2 Layer Normalization 的数学定义

对于单个样本 $x \in \mathbb{R}^d$：

**Step 1: 计算样本内均值和方差**（沿特征维度 $d$）

$$
\mu = \frac{1}{d} \sum_{i=1}^{d} x_i
$$

$$
\sigma^2 = \frac{1}{d} \sum_{i=1}^{d} (x_i - \mu)^2
$$

**Step 2: 归一化**

$$
\hat{x}_i = \frac{x_i - \mu}{\sqrt{\sigma^2 + \epsilon}}
$$

**Step 3: 缩放和平移**（可学习参数）

$$
y_i = \gamma \hat{x}_i + \beta
$$

其中 $\gamma$ 和 $\beta$ 是每个特征维度独立学习的参数，与 BatchNorm 相同。

**训练和推理**：LayerNorm 使用**当前样本**的均值和方差，训练和推理完全一致。

### 2.3 核心区别：归一化维度

| 维度 | BatchNorm | LayerNorm |
|------|-----------|-----------|
| 归一化方向 | 沿 **batch 维度**（跨样本） | 沿 **特征维度**（样本内） |
| 依赖 batch size | 是（batch size 越大越稳定） | 否 |
| 训练/推理行为 | 不同（训练用 batch 统计，推理用全局统计） | 相同 |
| 适用于 RNN | 否（序列长度变化时困难） | 是 |


## 3. 详细对比示例

### 3.1 示例设定

假设一个 mini-batch 包含 3 个样本，每个样本有 4 个特征维度：

$$
X = \begin{bmatrix}
x_{11} & x_{12} & x_{13} & x_{14} \\
x_{21} & x_{22} & x_{23} & x_{24} \\
x_{31} & x_{32} & x_{33} & x_{34}
\end{bmatrix} = \begin{bmatrix}
2.0 & 3.0 & 4.0 & 5.0 \\
1.0 & 0.0 & 1.0 & 2.0 \\
3.0 & 4.0 & 2.0 & 1.0
\end{bmatrix}
$$

其中行 $i$ 表示第 $i$ 个样本，列 $j$ 表示第 $j$ 个特征维度。

### 3.2 Batch Normalization 的计算过程

**Step 1: 计算每个特征维度（列）的均值和方差**

对第 1 列：$\mu_1 = \frac{2.0 + 1.0 + 3.0}{3} = 2.0$，$\sigma_1^2 = \frac{(2.0-2.0)^2 + (1.0-2.0)^2 + (3.0-2.0)^2}{3} = \frac{0 + 1 + 1}{3} = 0.667$

对第 2 列：$\mu_2 = \frac{3.0 + 0.0 + 4.0}{3} = 2.333$，$\sigma_2^2 = \frac{(3.0-2.333)^2 + (0.0-2.333)^2 + (4.0-2.333)^2}{3} = 2.889$

对第 3 列：$\mu_3 = \frac{4.0 + 1.0 + 2.0}{3} = 2.333$，$\sigma_3^2 = \frac{(4.0-2.333)^2 + (1.0-2.333)^2 + (2.0-2.333)^2}{3} = 1.556$

对第 4 列：$\mu_4 = \frac{5.0 + 2.0 + 1.0}{3} = 2.667$，$\sigma_4^2 = \frac{(5.0-2.667)^2 + (2.0-2.667)^2 + (1.0-2.667)^2}{3} = 2.889$

**Step 2: 归一化（以第 1 列为例，$\epsilon = 0$）**

对第 1 列三个值进行归一化：

$$
\hat{x}_{11} = \frac{2.0 - 2.0}{\sqrt{0.667}} = 0.0
$$

$$
\hat{x}_{21} = \frac{1.0 - 2.0}{\sqrt{0.667}} = -1.225
$$

$$
\hat{x}_{31} = \frac{3.0 - 2.0}{\sqrt{0.667}} = 1.225
$$

**完整归一化结果**（每列均值为 0，方差为 1）：

$$
\hat{X}_{\text{BN}} = \begin{bmatrix}
0.0 & 0.392 & 1.337 & 1.372 \\
-1.225 & -1.372 & -1.070 & -0.392 \\
1.225 & 0.980 & -0.267 & -0.980
\end{bmatrix}
$$

**Step 3: 缩放和平移**（以 $\gamma=1, \beta=0$ 为例）

最终输出与归一化结果相同。

### 3.3 Layer Normalization 的计算过程

**Step 1: 计算每个样本（行）的均值和方差**

对第 1 行：$\mu_1 = \frac{2.0 + 3.0 + 4.0 + 5.0}{4} = 3.5$，$\sigma_1^2 = \frac{(-1.5)^2 + (-0.5)^2 + (0.5)^2 + (1.5)^2}{4} = 1.25$

对第 2 行：$\mu_2 = \frac{1.0 + 0.0 + 1.0 + 2.0}{4} = 1.0$，$\sigma_2^2 = \frac{0 + (-1.0)^2 + 0 + (1.0)^2}{4} = 0.5$

对第 3 行：$\mu_3 = \frac{3.0 + 4.0 + 2.0 + 1.0}{4} = 2.5$，$\sigma_3^2 = \frac{(0.5)^2 + (1.5)^2 + (-0.5)^2 + (-1.5)^2}{4} = 1.25$

**Step 2: 归一化（以第 1 行为例，$\epsilon = 0$）**

对第 1 行四个值进行归一化：

$$
\hat{x}_{11} = \frac{2.0 - 3.5}{\sqrt{1.25}} = -1.342
$$

$$
\hat{x}_{12} = \frac{3.0 - 3.5}{\sqrt{1.25}} = -0.447
$$

$$
\hat{x}_{13} = \frac{4.0 - 3.5}{\sqrt{1.25}} = 0.447
$$

$$
\hat{x}_{14} = \frac{5.0 - 3.5}{\sqrt{1.25}} = 1.342
$$

**完整归一化结果**（每行均值为 0，方差为 1）：

$$
\hat{X}_{\text{LN}} = \begin{bmatrix}
-1.342 & -0.447 & 0.447 & 1.342 \\
0.0 & -1.414 & 0.0 & 1.414 \\
0.447 & 1.342 & -0.447 & -1.342
\end{bmatrix}
$$

**Step 3: 缩放和平移**（以 $\gamma=1, \beta=0$ 为例）

最终输出与归一化结果相同。

### 3.4 直观对比：归一化方向

**BatchNorm 视角**（按列归一化）：

对第 1 列（红色标注），BatchNorm 使用样本1、样本2、样本3在该列的值计算均值和方差。每列有自己的均值和方差。

$$
X = \begin{bmatrix}
\color{red}{2.0} & 3.0 & 4.0 & 5.0 \\
\color{red}{1.0} & 0.0 & 1.0 & 2.0 \\
\color{red}{3.0} & 4.0 & 2.0 & 1.0
\end{bmatrix}
$$

**LayerNorm 视角**（按行归一化）：

对第 1 行（红色标注），LayerNorm 使用样本1的所有四个特征值计算均值和方差。每行有自己的均值和方差。

$$
X = \begin{bmatrix}
\color{red}{2.0} & \color{red}{3.0} & \color{red}{4.0} & \color{red}{5.0} \\
1.0 & 0.0 & 1.0 & 2.0 \\
3.0 & 4.0 & 2.0 & 1.0
\end{bmatrix}
$$


## 4. 训练与推理行为差异

### 4.1 Batch Normalization

| 阶段 | 使用统计量 | 说明 |
|------|-----------|------|
| **训练** | 当前 batch 的 $\mu_{\mathcal{B}}, \sigma_{\mathcal{B}}^2$ | 每 batch 不同，依赖 batch 内样本 |
| **推理** | 全局 $\mu_{\text{global}}, \sigma_{\text{global}}^2$ | 训练时用 EMA 累积，固定不变 |
| **dropout 冲突** | 有 | dropout 改变 batch 统计量，需调整 |

**推理时固定统计量**：

$$
y = \gamma \cdot \frac{x - \mu_{\text{global}}}{\sqrt{\sigma_{\text{global}}^2 + \epsilon}} + \beta
$$

### 4.2 Layer Normalization

| 阶段 | 使用统计量 | 说明 |
|------|-----------|------|
| **训练** | 当前样本的 $\mu, \sigma^2$ | 每个样本独立计算 |
| **推理** | 当前样本的 $\mu, \sigma^2$ | 与训练完全一致 |
| **dropout 冲突** | 无 | 不依赖 batch |

**训练和推理完全一致**：

$$
y = \gamma \cdot \frac{x - \mu}{\sqrt{\sigma^2 + \epsilon}} + \beta
$$

其中 $\mu = \frac{1}{d}\sum_{i=1}^{d} x_i$，$\sigma^2 = \frac{1}{d}\sum_{i=1}^{d} (x_i - \mu)^2$ 来自当前样本。


## 5. 适用场景对比

### 5.1 BatchNorm 适用场景

| 场景 | 说明 |
|------|------|
| **CNN 图像分类** | 原始设计场景，效果最佳 |
| **固定 batch size 的训练** | 如 ImageNet 训练（batch size 256） |
| **大 batch size** | batch size ≥ 32 效果稳定 |
| **需要训练速度** | 加速收敛效果明显 |
| **深层网络（ResNet等）** | 标准配置，被广泛验证 |

**不适用场景**：

- batch size 过小（如 1-8）：统计量不稳定
- RNN/LSTM：序列长度变化，不同时间步统计量不同
- 在线学习/增量学习：每步 batch 统计量变化大

### 5.2 LayerNorm 适用场景

| 场景 | 说明 |
|------|------|
| **RNN/LSTM/Transformer** | 序列长度变化不影响归一化 |
| **batch size 很小** | 不依赖 batch 维度 |
| **在线学习/增量学习** | 每步独立计算 |
| **生成式模型** | 如 GPT 系列使用 LayerNorm |
| **需要训练/推理一致** | 行为完全一致 |

**不适用场景**：

- 特征维度太小：样本内统计量不可靠
- CNN 深层网络（可替代，但不如 BatchNorm 常用）


## 6. 核心差异总结

| 对比维度 | Batch Normalization | Layer Normalization |
|----------|---------------------|---------------------|
| **归一化方向** | 沿 batch 维度（跨样本归一化） | 沿特征维度（样本内归一化） |
| **均值和方差来源** | batch 内所有样本 | 单个样本的所有特征 |
| **依赖 batch size** | 是（需足够大） | 否 |
| **训练/推理一致性** | 不一致（训练用 batch 统计，推理用全局统计） | 一致（始终使用当前样本统计） |
| **RNN 适用性** | 差（序列长度变化） | 好 |
| **CNN 适用性** | 好（标准配置） | 一般 |
| **需要运行统计量** | 是（EMA 存储） | 否 |
| **batch size=1 时** | 失效（方差为0） | 有效 |


## 7. 参考文献

[1] Ioffe, S., & Szegedy, C. (2015). *Batch Normalization: Accelerating Deep Network Training by Reducing Internal Covariate Shift*. ICML 2015.

[2] Ba, J. L., Kiros, J. R., & Hinton, G. E. (2016). *Layer Normalization*. arXiv:1607.06450.