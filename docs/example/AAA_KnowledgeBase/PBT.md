# Population Based Training (PBT) 完整报告

## 0. 论文来源

| 项目 | 内容 |
|------|------|
| **标题** | Population Based Training of Neural Networks |
| **作者** | Max Jaderberg, Valentin Dalibard, Simon Osindero, Wojciech M. Czarnecki, Jeff Donahue, Ali Razavi, Oriol Vinyals, Tim Green, Iain Dunning, Karen Simonyan, Chrisantha Fernando, Koray Kavukcuoglu |
| **机构** | DeepMind, London, UK |
| **发表** | arXiv:1711.09846, 2017 |
| **核心贡献** | 提出一种异步并行超参数优化算法，在固定计算预算下同时优化模型参数和超参数，自动发现超参数调度策略 |


## 1. 算法概述

### 1.1 一句话定位

**PBT (Population Based Training)** 是一种**异步并行**的元优化算法，通过维护一个模型种群，在训练过程中周期性地利用种群表现信息，同步优化模型权重（$\theta$）和超参数（$h$），实现超参数的**在线自适应调度**。

### 1.2 设计动机（Why）

**传统超参数优化的困境**：

1. **并行搜索（Parallel Search）**如网格搜索、随机搜索：同时训练多个模型，每个模型使用固定超参数。优点：墙钟时间短；缺点：计算资源需求大，且无法利用训练过程中的信息来调整超参数。

2. **序列优化（Sequential Optimisation）**如贝叶斯优化：逐步根据前一次训练结果选择下一组超参数。优点：计算资源需求小；缺点：需要多次串行训练，墙钟时间长。

3. **超参数调度的必要性**：许多场景下最优超参数是**非平稳的**——例如强化学习中学习率需要衰减，Dropout 率需要随训练进程调整。固定超参数或预定义调度策略往往不是最优的。

**PBT 的核心设计**：

- 同时训练 $N$ 个模型（种群），每个模型有独立的权重 $\theta^i$ 和超参数 $h^i$
- 周期性评估每个模型的表现 $p^i$
- **Exploit**：表现差的模型复制表现好的模型的权重和超参数
- **Explore**：复制后对超参数进行随机扰动，产生新的超参数配置
- 整个过程异步并行，墙钟时间与单次训练相当

### 1.3 核心优势

1. **墙钟效率高**：运行时间不超过单次训练时间
2. **超参数自适应**：自动发现训练过程中的超参数调度策略
3. **模型选择**：优秀模型（"幸运"的探索）被复制传播，计算资源聚焦于有希望的区域
4. **广泛应用**：RL、机器翻译、GAN 训练均取得显著提升


## 2. 数学框架

### 2.1 符号系统

| 符号 | 含义 | 类型 |
|------|------|------|
| $\theta$ | 模型可训练参数（权重） | 向量 |
| $h$ | 超参数（如学习率、Dropout率等） | 向量或标量 |
| $\mathcal{Q}(\theta)$ | 我们真正关心的性能度量（目标函数） | 标量函数 |
| $\hat{\mathcal{Q}}(\theta \mid h)$ | 训练中使用的代理目标函数（可微） | 标量函数 |
| $\text{eval}(\theta)$ | 评估函数，返回 $\mathcal{Q}(\theta)$ | 函数 |
| $\text{step}(\theta \mid h)$ | 一步参数更新（如 SGD 步） | 函数 |
| $T$ | 总训练步数 | 正整数 |
| $h_t$ | 第 $t$ 步的超参数 | 向量 |
| $\pmb{h} = (h_t)_{t=1}^T$ | 完整超参数序列 | 序列 |
| $N$ | 种群大小 | 正整数 |
| $\mathcal{P} = \{(\theta^i, h^i, p^i, t^i)\}_{i=1}^N$ | 种群 | 集合 |

### 2.2 问题形式化

**标准训练过程**：

给定初始参数 $\theta$ 和超参数序列 $\pmb{h} = (h_1, h_2, \ldots, h_T)$，训练过程是迭代应用参数更新：

$$
\theta \gets \text{step}(\theta \mid h_t), \quad t = 1, 2, \ldots, T
$$

完整训练过程可写为函数复合：

$$
\text{optimise}(\theta \mid \pmb{h}) = \text{step}(\text{step}(\cdots \text{step}(\theta \mid h_1) \cdots \mid h_{T-1}) \mid h_T)
$$

**最优参数**：

$$
\theta^* = \text{optimise}(\theta \mid \pmb{h}^*)
$$

**超参数优化问题**：

$$
\pmb{h}^* = \arg\max_{\pmb{h} \in \mathcal{H}^T} \text{eval}\bigl(\text{optimise}(\theta \mid \pmb{h})\bigr)
$$

其中 $\mathcal{H}^T$ 是所有可能超参数序列构成的空间，规模随 $T$ 指数增长。实践中通常限制 $h_t$ 为常数或预定义简单调度，即 $h_t = h$ 或 $h_t = \text{schedule}(t, h)$。

**PBT 的视角**：

PBT 不直接求解上述全局优化问题，而是通过种群并行搜索，在训练过程中动态调整超参数：

$$
\underset{\theta, \pmb{h}}{\arg\max} \; \text{eval}\bigl(\text{optimise}(\theta \mid \pmb{h})\bigr)
$$

### 2.3 PBT 的两个核心操作

**Exploit（剥削）**：根据种群表现决定是否放弃当前解，转向更有希望的解。

对于第 $i$ 个成员，给定当前表现 $p^i$ 和种群表现集合 $\{p^j\}_{j=1}^N$：

$$
(\theta^i, h^i) \gets \text{exploit}(\theta^i, h^i, p^i, \mathcal{P})
$$

**Explore（探索）**：对复制来的解产生新的超参数：

$$
h^i \gets \text{explore}(h'^i, \theta'^i, \mathcal{P})
$$

其中 $(h'^i, \theta'^i)$ 是 exploit 阶段获得的解。

两个操作共同构成了超参数空间的**局部搜索与全局探索**的平衡。


## 3. 完整算法

### 3.1 伪代码

```
Algorithm 1: Population Based Training (PBT)

 1:  procedure TRAIN(P)
 2:      初始化种群 P = {(θ^i, h^i, p^i, t^i)}_{i=1}^N
 3:      for (θ, h, p, t) ∈ P do          ▷ 异步并行执行
 4:          while not end of training do
 5:              θ ← step(θ | h)          ▷ 一次梯度下降更新
 6:              p ← eval(θ)              ▷ 评估当前模型
 7:              if ready(p, t, P) then   ▷ 达到就绪条件
 8:                  (h', θ') ← exploit(h, θ, p, P)
 9:                  if θ ≠ θ' then       ▷ 发生复制
10:                      (h, θ) ← explore(h', θ', P)
11:                      p ← eval(θ)     ▷ 更新评估
12:                  end if
13:              end if
14:              更新种群 P 中的 (θ, h, p, t+1)
15:          end while
16:      end for
17:      return argmax_{θ ∈ P} eval(θ)
18:  end procedure
```

### 3.2 各组件详细说明

#### 3.2.1 step：参数更新函数

$$
\theta \gets \text{step}(\theta \mid h)
$$

具体形式取决于任务。典型实现：

- **RL (A3C/UNREAL/FuN)**：RMSProp 梯度下降
- **机器翻译 (Transformer)**：Adam 梯度下降
- **GAN**：Adam 梯度下降，判别器和生成器交替更新

数学形式（以 SGD 为例）：

$$
\theta_{t+1} = \theta_t - \eta_t \nabla_\theta \mathcal{L}(\theta_t)
$$

其中 $\eta_t$ 是超参数 $h$ 的组成部分（学习率）。

#### 3.2.2 eval：评估函数

$$
p = \text{eval}(\theta)
$$

返回当前模型的性能度量 $\mathcal{Q}(\theta)$：

- **RL**：最近 10 个 episode 的平均累积奖励
- **机器翻译**：验证集上的 BLEU 分数
- **GAN**：CIFAR Inception Score（使用较小的分类器，避免直接优化测试指标）

> **关键点**：$\mathcal{Q}$ 不需要可微，也不需要与 $\hat{\mathcal{Q}}$ 相同。这使得 PBT 可以优化非可微的最终目标（如 BLEU、Inception Score）。

#### 3.2.3 ready：就绪条件

决定何时触发 exploit-and-explore 过程：

- **RL**：自上次就绪以来，经过 $[1\times 10^6, 10\times 10^6]$ 个 agent 步
- **机器翻译**：每 $2\times 10^3$ 步
- **GAN**：每 $5\times 10^3$ 步

就绪条件的目的是确保每次复制之间有足够的梯度下降学习发生。

#### 3.2.4 exploit：剥削策略

**策略 1：T-test Selection（t检验选择）**

1. 从种群中均匀采样另一个 Agent $j$
2. 比较当前 Agent $i$ 和 $j$ 最近 10 个 episode 的奖励
3. 使用 Welch's t-test 判断 $j$ 是否显著优于 $i$
4. 若显著，复制 $j$ 的权重和超参数

数学形式：

$$
\text{copy if } \mu_j > \mu_i \text{ and } p_{\text{ttest}}(\mu_i, \sigma_i, n_i, \mu_j, \sigma_j, n_j) < \alpha
$$

其中 $\mu$ 为均值，$\sigma$ 为标准差，$n$ 为样本数，$\alpha$ 为显著性水平。

**策略 2：Truncation Selection（截断选择）**

1. 按表现排名所有 Agent
2. 若当前 Agent 在底部 $20\%$（表现最差），则从顶部 $20\%$ 均匀采样一个 Agent
3. 复制其权重和超参数

数学形式：

$$
\text{copy if } \text{rank}(p^i) \le \lfloor \alpha N \rfloor \quad \text{（底部 α 比例）}
$$

其中 $\alpha = 0.2$ 为截断比例，从顶部 $\alpha$ 比例中均匀采样。

#### 3.2.5 explore：探索策略

**策略 1：Perturb（扰动）**

每个超参数独立地以 0.5 概率乘以 1.2 或以 0.5 概率乘以 0.8：

$$
h'_k = \begin{cases}
h_k \cdot 1.2 & \text{with probability } 0.5 \\
h_k \cdot 0.8 & \text{with probability } 0.5
\end{cases}
$$

对于 GAN，使用更激进的扰动因子（2.0 或 0.5）。

**策略 2：Resample（重采样）**

以一定概率将超参数从原始先验分布中重新采样：

$$
h'_k \sim \text{Prior}_k
$$

### 3.3 信息流架构

PBT 的异步并行架构：

```
┌─────────────────────────────────────────────────────────────┐
│                      共享数据存储（Key-Value Store / 文件系统）        │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐      │
│  │ Agent 1 │  │ Agent 2 │  │ Agent 3 │  │ Agent N │      │
│  │ θ¹, h¹  │  │ θ², h²  │  │ θ³, h³  │  │ θᴺ, hᴺ  │      │
│  │ p¹, t¹  │  │ p², t²  │  │ p³, t³  │  │ pᴺ, tᴺ  │      │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘      │
└─────────────────────────────────────────────────────────────┘
        ▲              ▲              ▲              ▲
        │ read/write   │ read/write   │ read/write   │ read/write
        │              │              │              │
   ┌────┴────┐   ┌────┴────┐   ┌────┴────┐   ┌────┴────┐
   │ Worker1 │   │ Worker2 │   │ Worker3 │   │ WorkerN │
   │ step()  │   │ step()  │   │ step()  │   │ step()  │
   │ eval()  │   │ eval()  │   │ eval()  │   │ eval()  │
   │ ready() │   │ ready() │   │ ready() │   │ ready() │
   │exploit()│   │exploit()│   │exploit()│   │exploit()│
   │explore()│   │explore()│   │explore()│   │explore()│
   └─────────┘   └─────────┘   └─────────┘   └─────────┘
        │              │              │              │
        └──────────────┴──────────────┴──────────────┘
                  异步并行执行，无同步屏障
```

**关键特性**：

- **无中心协调器**：每个 Worker 独立决定何时 exploit/explore
- **异步读写**：无同步屏障，允许 Worker 以不同速度运行
- **最小化开销**：仅需共享存储，无需复杂的通信机制


## 4. 三种不同领域的 PBT 实例化

### 4.1 深度强化学习（Deep RL）

**目标**：最大化期望 episode 累积奖励 $\mathbb{E}_\pi[R]$

**step**：使用 RMSProp 进行梯度下降（A3C / UNREAL / FuN）

**eval**：最近 10 个 episode 的平均奖励

**ready**：自上次就绪后经过 $[1\times 10^6, 10\times 10^6]$ 个 agent 步

**exploit**：Truncation Selection 或 T-test Selection

**explore**：Perturb（因子 1.2 / 0.8）

**超参数**：

| 领域 | 超参数 |
|------|--------|
| UNREAL (DeepMind Lab) | 学习率, 熵代价, unroll length |
| FuN (Atari) | 学习率, 熵代价, 内在奖励权重 |
| A3C (StarCraft II) | 学习率 |

### 4.2 机器翻译（Machine Translation）

**目标**：最大化 BLEU 分数

**模型**：Transformer 网络（WMT 2014 En→De）

**step**：使用 Adam 进行梯度下降

**eval**：在 newstest2012 上的 BLEU 分数

**ready**：每 $2\times 10^3$ 步

**exploit**：T-test Selection

**explore**：Perturb（因子 1.2 / 0.8）

**超参数**：学习率, attention dropout, layer dropout, ReLU dropout

### 4.3 生成对抗网络（GAN）

**目标**：最大化 Inception Score

**step**：$K=5$ 步判别器更新 + 1 步生成器更新（WGAN-GP 目标）

**eval**：CIFAR Inception Score

**ready**：每 $5\times 10^3$ 步

**exploit**：Truncation Selection

**explore**：Perturb（因子 2.0 / 0.5）

**超参数**：判别器学习率, 生成器学习率（分别优化）


## 5. 关键结果

| 领域 | 基线 | PBT 结果 | 提升 |
|------|------|----------|------|
| DeepMind Lab (UNREAL) | 93% 人类水平 | 106% 人类水平 | +13% |
| Atari (FuN) | 147% 人类水平 | 181% 人类水平 | +34% |
| StarCraft II (A3C) | 36% 人类水平 | 39% 人类水平 | +3% |
| 机器翻译 (Transformer) | 23.71 BLEU | 24.23 BLEU | +0.52 |
| GAN (CIFAR-10) | 6.39 CIFAR-IS | 6.80 CIFAR-IS | +0.41 |


## 6. 设计空间分析

### 6.1 种群大小 $N$

- $N$ 过小（≤10）：方差大，易陷入局部最优
- $N$ 在 20-40：足够稳定且改进明显
- $N$ 增大：性能继续提升，但边际收益递减

### 6.2 剥削策略选择

- Truncation Selection 比 Binary Tournament 更稳定
- 建议：Truncation Selection 作为默认选择

### 6.3 超参数自适应的重要性

比较三种设置：

| 设置 | 描述 | 性能 |
|------|------|------|
| 完整 PBT | 权重复制 + 超参数扰动 | 最高 |
| 仅超参数 PBT | 超参数扰动，但**不复制权重** | 中等 |
| 仅权重 PBT | 权重复制，但**超参数不变化** | 中等 |

**结论**：模型选择（权重复制）和超参数自适应（扰动）共同贡献于性能提升。


## 7. 总结

| 维度 | 描述 |
|------|------|
| **核心思想** | 种群并行训练 + 周期性的 exploit/explore |
| **时间复杂度** | 与单次训练相同（异步并行） |
| **关键创新** | 超参数在线自适应调度，而非固定搜索 |
| **适用场景** | 训练代价高、超参数敏感、非平稳学习问题 |
| **主要局限** | 贪婪算法可能陷入局部最优；需足够大的种群 |
| **扩展性** | 可结合更复杂的进化算子（如交叉、更精细的自适应机制） |

PBT 提供了一种实用的超参数优化范式，在三个截然不同的领域（RL、机器翻译、GAN）均验证了其有效性。其核心优势在于：通过在线自适应调度，自动发现超越人类专家设计的复杂超参数演化策略。