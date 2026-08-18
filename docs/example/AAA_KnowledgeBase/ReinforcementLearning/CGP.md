# Cross-Entropy Guided Policies (CGP) 完整报告

## 0. 论文来源

| 项目 | 内容 |
|------|------|
| **标题** | Q-Learning for Continuous Actions with Cross-Entropy Guided Policies |
| **作者** | Riley Simmons-Edler, Ben Eisner, Eric Mitchell, Sebastian Seung, Daniel Lee |
| **机构** | Princeton University |
| **发表** | 2019（arXiv预印本） |
| **核心贡献** | 提出CGP算法，使用交叉熵方法（CEM）采样动作来训练Q函数，同时训练确定性策略网络来模仿CEM的行为，兼顾训练稳定性与推理效率 |


## 1. 算法概述

### 1.1 一句话定位

**CGP (Cross-Entropy Guided Policies)** 是一种用于**连续动作空间**的异策略Q学习算法，其核心思想是：使用**交叉熵方法（CEM）**作为采样策略来训练Q函数，同时训练一个确定性神经网络策略来**模仿CEM的行为**，从而在推理时获得与策略网络方法相同的低计算成本，同时保留采样方法的稳定性和性能。

### 1.2 设计动机（Why）

**连续动作Q学习的挑战**：

1. **argmax不可计算**：在连续动作空间中，$\arg\max_a Q(s,a)$ 无法通过穷举求解，因为动作空间是无限的
2. **现有方法的局限**：

| 方法 | 优点 | 缺点 |
|------|------|------|
| **DDPG** | 推理快（单次网络前向） | 训练不稳定，对超参数敏感 |
| **CEM采样策略**（如Qt-Opt） | 训练稳定，性能好 | 推理慢（需多次迭代采样） |
| **SAC/TD3** | 较DDPG更稳定 | 仍有超参数敏感性问题 |

**CGP的设计目标**：

- 用**CEM采样**训练Q函数，获得采样方法的稳定性
- 用**策略网络模仿CEM**，获得网络方法的推理速度
- 两者结合，取长补短

### 1.3 核心洞察

如果CEM是一个好的策略（能有效近似$\arg\max_a Q(s,a)$），那么它的输出可以作为**监督信号**来训练一个确定性策略网络。这样：

- Q函数从CEM采样中获得稳定的训练信号
- 策略网络从CEM的"示范"中学习
- 推理时只用策略网络，无需CEM迭代

### 1.4 核心优势

1. **训练稳定性高**：CEM采样比梯度方法更稳定
2. **推理速度快**：策略网络单次前向，与DDPG/TD3相当
3. **超参数鲁棒**：在多种超参数配置下性能退化缓慢
4. **兼容性好**：可与TD3等Q学习改进结合


## 2. 数学框架

### 2.1 符号系统

| 符号 | 含义 |
|------|------|
| $\mathcal{S}$ | 状态空间 |
| $\mathcal{A} = \mathbb{R}^d$ | 连续动作空间，维度为$d$ |
| $\pi$ | 策略，$\pi: \mathcal{S} \to \mathcal{A}$ |
| $Q^*(s,a)$ | 最优动作价值函数 |
| $Q_\theta(s,a)$ | 参数为$\theta$的Q函数（神经网络） |
| $\pi_\phi(s)$ | 参数为$\phi$的确定性策略网络 |
| $\pi_{\text{CEM}}(s)$ | CEM采样策略 |
| $\gamma \in [0,1)$ | 折扣因子 |
| $r(s,a)$ | 即时奖励 |
| $\mathcal{B}$ | 经验回放缓冲区 |
| $\rho^\pi(s)$ | 策略$\pi$下的折扣状态分布 |

### 2.2 问题形式化

**MDP设定**：智能体在环境中采取动作$a_t \sim \pi(s_t)$，目标是最大化期望累积折扣奖励：

$$
J(\pi) = \mathbb{E}_{s,a \sim \pi} \left[ \sum_{t=1}^{T} \gamma^t r(s_t, a_t) \right]
$$

**最优Q函数**满足贝尔曼最优方程：

$$
Q^*(s_t, a_t) = r(s_t, a_t) + \gamma \max_{a_{t+1}} Q^*(s_{t+1}, a_{t+1})
$$

一旦$Q^*$已知，最优策略为：

$$
\pi^*(s) = \arg\max_{a} Q^*(s, a)
$$

**Q学习目标**：最小化贝尔曼残差：

$$
J(\theta) = \mathbb{E}_{s,a} \left[ \left( Q_\theta(s,a) - \left[ r(s,a) + \gamma \max_{a'} \hat{Q}(s', a') \right] \right)^2 \right]
$$

其中$\hat{Q}$是目标网络。

**连续动作的核心问题**：$\arg\max_a Q(s,a)$ 在连续空间中不可计算，因此需要近似方法。

### 2.3 交叉熵方法（CEM）策略

CEM是一种基于采样的迭代优化算法。对于给定的状态$s$和Q函数$Q_\theta$，CEM通过以下步骤近似$\arg\max_a Q_\theta(s,a)$：

**Algorithm 1: 用于Q学习的交叉熵方法策略 ($\pi_{\text{CEM}}$)**

| 步骤 | 操作 |
|------|------|
| **输入** | 状态$s$，Q函数$Q$，迭代次数$N$，样本数$n$，优胜者数$k$，动作维度$d$ |
| 1 | $\mu \leftarrow \mathbf{0}_d$ |
| 2 | $\sigma^2 \leftarrow \mathbf{1}_d$ |
| 3 | **for** $t = 1$ **to** $N$ **do** |
| 4 | $\quad \mathcal{A} \leftarrow \{ a_i \mid a_i \sim \mathcal{N}(\mu, \sigma^2) \}_{i=1}^n$ |
| 5 | $\quad \mathcal{A} \leftarrow \{ \tanh(a_i) \mid a_i \in \mathcal{A} \}$ |
| 6 | $\quad \mathcal{Q} \leftarrow \{ Q(a_i) \mid a_i \in \mathcal{A} \}$ |
| 7 | $\quad \mathcal{I} \leftarrow \text{sort}(\mathcal{Q})$ 中前$k$个的索引 |
| 8 | $\quad \mu \leftarrow \frac{1}{k} \sum_{i \in \mathcal{I}} a_i$ |
| 9 | $\quad \sigma^2 \leftarrow \text{Var}_{i \in \mathcal{I}}(a_i)$ |
| 10 | $\quad \sigma^2 \leftarrow \sigma^2$（保持方差） |
| 11 | **end for** |
| 12 | **return** $a^* \in \mathcal{A}$ 使得 $Q(a^*) = \max_{i \in \mathcal{I}} Q(a_i)$ |

**数学细节**：

- 第4行：从多元高斯分布采样$n$个动作向量
- 第5行：$\tanh$映射将动作限制在$[-1, 1]^d$（与常见连续控制环境的动作空间匹配）
- 第7行：选择Q值最高的$k$个动作
- 第8-9行：用优胜者重新估计均值和方差

### 2.4 使用采样策略的Q学习

定义采样策略$\pi_{\mathcal{S}_Q}(s) = \mathcal{S}_Q(s)$，其中$\mathcal{S}_Q$是近似$\arg\max_a Q(s,a)$的采样优化器。

Q学习目标变为：

$$
J(\theta) = \mathbb{E}_{s,a} \left[ \left( Q_\theta(s,a) - \left[ r(s,a) + \gamma \hat{Q}\left(s', \mathcal{S}_{Q_\theta}(s')\right) \right] \right)^2 \right]
$$

即用$\pi_{\text{CEM}}$采样bootstrap动作。


## 3. CGP完整算法

### 3.1 两种策略训练方法

**方法1：QGP（Q-Gradient Guided Policy）**

直接使用DDPG风格的梯度来优化策略网络：

$$
J(\phi) = \mathbb{E}_{s \sim \rho^{\pi_{\text{CEM}}}} \left[ Q_\theta(s, \pi_\phi(s)) \right]
$$

梯度：

$$
\nabla_\phi J(\phi) = \mathbb{E}_{s \sim \rho^{\pi_{\text{CEM}}}} \left[ \nabla_a Q_\theta(s, a) \big|_{a=\pi_\phi(s)} \cdot \nabla_\phi \pi_\phi(s) \right]
$$

**方法2：CGP（Cross-Entropy Guided Policy）**——论文主要方法

使用L2回归目标，让策略网络模仿$\pi_{\text{CEM}}$的输出：

$$
J(\phi) = \mathbb{E}_{s_t \sim \rho^{\pi_{\text{CEM}}}} \left[ \left\| \pi_\phi(s_t) - \pi_{\text{CEM}}(s_t) \right\|^2 \right]
$$

梯度：

$$
\nabla_\phi J(\phi) = \mathbb{E}_{s_t \sim \rho^{\pi_{\text{CEM}}}} \left[ 2 \left( \pi_\phi(s_t) - \pi_{\text{CEM}}(s_t) \right) \cdot \nabla_\phi \pi_\phi(s_t) \right]
$$

**为什么CGP比QGP更稳定？**

| 方面 | QGP | CGP |
|------|-----|-----|
| 监督信号 | Q函数的梯度 | CEM采样的动作 |
| 信号性质 | 可能非凸，有局部最优 | 直接模仿，目标明确 |
| 稳定性 | 较差 | 较好 |
| 理论基础 | 精确策略梯度 | 近似策略梯度 |

### 3.2 完整伪代码

```
Algorithm 2: CGP (Cross-Entropy Guided Policies)

┌─────────────────────────────────────────────────────────────────┐
│                      训练阶段                                  │
├─────────────────────────────────────────────────────────────────┤
│ 1:  用随机参数 θ₁, θ₂, φ 初始化 Q函数 Q_θ₁, Q_θ₂ 和策略 π_φ   │
│ 2:  初始化目标网络：θ₁' ← θ₁, θ₂' ← θ₂, φ' ← φ              │
│ 3:  初始化 CEM 策略 π_CEM^{Q_θ₁}, π_CEM^{Q_θ₂}               │
│ 4:  初始化经验回放缓冲区 B                                     │
│ 5:  定义 batch size b                                         │
│ 6:  for episode = 1 to E do                                   │
│ 7:      for t = 1 to T do                                    │
│ 8:          观察状态 s_t                                      │
│ 9:          用 π_CEM^{Q_θ₁}(s_t) 采样动作 a_t                │
│10:          执行动作，观察奖励 r_t 和新状态 s_{t+1}            │
│11:          存储 (s_t, a_t, r_t, s_{t+1}) 到 B               │
│12:          for j ∈ {1, 2} do                                │
│13:              从 B 采样 minibatch (s_i, a_i, r_i, s_{i+1}) │
│14:              用 π_CEM^{Q_j} 采样 ã_{i+1}                  │
│15:              q* = r_i + γ · min_{j∈{1,2}} Q_θ'_j(s_{i+1}, ã_{i+1}) │
│16:              ℓ_Qj = (Q_θ_j(s_i, a_i) - q*)²               │
│17:              θ_j ← θ_j - η_Q · ∇_{θ_j} ℓ_Qj              │
│18:          end for                                          │
│19:          策略损失（二选一）:                               │
│20:          CGP: ℓ_π = ||π_φ(s_i) - π_CEM(s_i)||²           │
│21:          QGP: ℓ_π = -Q_θ₁(s_i, π_φ(s_i))                 │
│22:          φ ← φ - η_π · ∇_φ ℓ_π                           │
│23:          软更新目标网络:                                   │
│24:          θ_j' ← τ θ_j + (1-τ) θ_j', j ∈ {1,2}            │
│25:          φ' ← τ φ + (1-τ) φ'                             │
│26:      end for                                              │
│27:  end for                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      推理阶段                                  │
├─────────────────────────────────────────────────────────────────┤
│28:  for t = 1 to T do                                        │
│29:      观察状态 s_t                                          │
│30:      用 π_φ(s_t) 采样动作 a_t（单次前向传播）              │
│31:      执行动作，观察奖励和下一状态                          │
│32:  end for                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 与TD3的结合

CGP的Q函数训练使用了TD3的两项改进：

1. **双Q函数**：使用两个Q函数 $Q_{\theta_1}$ 和 $Q_{\theta_2}$，target使用两者中较小的值：

$$
q^* = r_i + \gamma \min_{j \in \{1,2\}} Q_{\theta'_j}(s_{i+1}, \tilde{a}_{i+1})
$$

2. **目标策略平滑**：在target动作中加入裁剪噪声（通过CEM的随机性自然实现）


## 4. 关键理论分析

### 4.1 CEM的收敛性

CEM是一种基于**精英选择**的迭代优化算法。在每一步迭代中：

$$
\mu_{t+1} = \frac{1}{k} \sum_{i \in \mathcal{I}_t} a_i, \quad \sigma_{t+1}^2 = \frac{1}{k} \sum_{i \in \mathcal{I}_t} (a_i - \mu_{t+1})^2
$$

其中 $\mathcal{I}_t$ 是Q值最高的 $k$ 个样本的索引集合。

当 $N \to \infty$ 时，如果Q函数足够平滑，CEM收敛到局部最优：

$$
\lim_{N \to \infty} \pi_{\text{CEM}}^N(s) \in \arg\max_a Q(s,a)
$$

这是CGP作为监督信号有效性的理论基础。

### 4.2 CGP策略梯度

CGP的L2回归目标：

$$
J_{\text{CGP}}(\phi) = \mathbb{E}_{s \sim \rho^{\pi_{\text{CEM}}}} \left[ \| \pi_\phi(s) - \pi_{\text{CEM}}(s) \|^2 \right]
$$

如果 $\pi_{\text{CEM}}(s)$ 是 $\arg\max_a Q_\theta(s,a)$ 的一致估计，则优化 $J_{\text{CGP}}$ 等价于最小化策略网络与最优策略之间的差异。

### 4.3 推理时间分析

| 方法 | 训练时间 | 推理时间 | 说明 |
|------|----------|----------|------|
| CEM-2（2次迭代） | 7.1s | 6.3s | 需 $n \times N$ 次Q评估 |
| CEM-4（4次迭代） | 9.3s | 10.1s | 迭代次数翻倍，推理时间翻倍 |
| **CGP-2** | 11.0s | **2.35s** | 推理与CEM迭代次数**无关** |
| **CGP-4** | 14.4s | **2.35s** | 推理与CEM迭代次数**无关** |
| DDPG/TD3 | 5.7s | 2.35s | 单次网络前向 |


## 5. 实验与结果

### 5.1 实验设置

- **环境**：OpenAI Gym连续控制任务（MuJoCo）：HalfCheetah-v2, Hopper-v2, Walker2d-v2, Ant-v2, Reacher-v2
- **基线**：DDPG, TD3, SAC, CEM-only（无策略网络）
- **评估维度**：最终性能、训练稳定性、超参数鲁棒性、推理速度

### 5.2 超参数

| 类别 | 参数 | 值 |
|------|------|-----|
| CEM | 迭代次数 N | 2 |
| CEM | 样本数 n | 64 |
| CEM | 优胜者数 k | 6 |
| 网络 | 隐藏层单元数 | 256 |
| 训练 | Q学习率 | 0.001 |
| 训练 | 策略学习率 | 0.001 |
| 训练 | Batch size | 128 |
| 训练 | 折扣因子 γ | 0.99 |
| 训练 | 软更新系数 τ | 0.005 |
| 训练 | Target更新频率 | 2步 |

### 5.3 主要结果

**图2：性能对比**

| 环境 | CGP | TD3 | SAC | DDPG |
|------|-----|-----|-----|------|
| HalfCheetah | 最佳或次佳 | 竞争 | 竞争 | 不稳定 |
| Hopper | 最佳或次佳 | 表现差 | 表现差 | 失败 |
| Walker2d | 最佳或次佳 | 竞争 | 竞争 | 失败 |
| Ant | 最佳或次佳 | 竞争 | 竞争 | 失败 |
| Reacher | 最佳或次佳 | 竞争 | 竞争 | 失败 |

**关键发现**：CGP在所有任务中要么最佳要么次佳，而TD3和SAC在某些任务上表现差，DDPG在大多数任务上训练不稳定。

### 5.4 超参数鲁棒性分析

**图6：网络大小敏感性**

- 所有方法在32单元网络时性能下降
- CGP在网络大小变化时受影响最小

**图7：学习率和Batch Size敏感性**

- CGP在不同学习率和batch size组合下性能波动**最窄**
- 唯一例外：学习率0.01时CGP无法稳定训练（过高）

**图8：Replay Buffer初始随机样本数敏感性**

- TD3需要足够的初始随机样本（论文作者也指出这一点）
- CGP在不同初始样本数下表现相对稳定

### 5.5 推理速度

| 方法 | 推理时间（秒/episode） |
|------|----------------------|
| Random | 0.48 |
| DDPG | 2.32 |
| TD3 | 2.35 |
| SAC | 2.35 |
| CEM-2 | 6.3 |
| CEM-4 | 10.1 |
| **CGP-2** | **2.35** |
| **CGP-4** | **2.35** |

**关键结论**：CGP的推理时间与CEM迭代次数**完全无关**，与其他策略网络方法相当，但比CEM快3-4倍。


## 6. 核心结论

### 6.1 方法对比总结

| 维度 | DDPG | TD3 | SAC | CEM-only | **CGP** |
|------|------|-----|-----|----------|---------|
| 训练稳定性 | 差 | 中 | 中 | 好 | **好** |
| 推理速度 | 快 | 快 | 快 | 慢 | **快** |
| 超参数鲁棒性 | 差 | 中 | 中 | — | **好** |
| 最终性能 | 中 | 好 | 好 | 好 | **好** |

### 6.2 为什么CGP有效？

1. **CEM提供了稳定的监督信号**：CEM输出的动作虽然计算成本高，但质量高且稳定，作为策略网络的训练目标比Q梯度更可靠

2. **解耦Q训练和策略训练**：策略网络不参与Q函数的训练，避免了DDPG中策略网络梯度噪声对Q函数的影响

3. **QGP vs CGP的对比**：
   - QGP直接优化Q值，理论最优但实践中不稳定（Q函数非凸）
   - CGP模仿CEM，理论次优但实践中更稳定

4. **推理效率**：策略网络单次前向传播，与CEM迭代次数无关

### 6.3 与ERL的关联

| 维度 | ERL | CGP |
|------|-----|-----|
| 采样策略 | EA种群（参数空间） | CEM（动作空间） |
| 监督信号 | Fitness选择 | CEM采样的动作 |
| 策略训练 | DDPG风格（梯度） | 模仿学习（L2回归） |
| 推理效率 | 快（rl_actor） | 快（π_φ） |

两者都使用**采样方法**来生成高质量动作/策略，然后用**网络方法**来获得推理效率。


## 7. 参考文献

[1] Simmons-Edler, R., Eisner, B., Mitchell, E., Seung, S., & Lee, D. (2019). *Q-Learning for Continuous Actions with Cross-Entropy Guided Policies*. arXiv preprint.

[2] Lillicrap, T. P., Hunt, J. J., Pritzel, A., et al. (2015). *Continuous control with deep reinforcement learning*. ICLR 2015. (DDPG)

[3] Fujimoto, S., van Hoof, H., & Meger, D. (2018). *Addressing Function Approximation Error in Actor-Critic Methods*. ICML 2018. (TD3)

[4] Haarnoja, T., Zhou, A., Abbeel, P., & Levine, S. (2018). *Soft Actor-Critic: Off-Policy Maximum Entropy Deep Reinforcement Learning with a Stochastic Actor*. ICML 2018. (SAC)

[5] Kalashnikov, D., Irpan, A., Pastor, P., et al. (2018). *Scalable Deep Reinforcement Learning for Vision-Based Robotic Manipulation*. CoRL 2018. (Qt-Opt)

[6] Khadka, S., & Tumer, K. (2018). *Evolution-Guided Policy Gradient in Reinforcement Learning*. NeurIPS 2018. (ERL)

[7] Pourchot, A., & Sigaud, O. (2019). *CEM-RL: Combining evolutionary and gradient-based methods for policy search*. ICLR 2019. (CEM-RL)