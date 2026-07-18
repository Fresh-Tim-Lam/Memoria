# 连续控制中的深度强化学习：DDPG 算法完整报告

## 0. 论文来源

| 项目 | 内容 |
|------|------|
| **标题** | Continuous Control with Deep Reinforcement Learning |
| **作者** | Timothy P. Lillicrap, Jonathan J. Hunt, Alexander Pritzel, Nicolas Heess, Tom Erez, Yuval Tassa, David Silver, Daan Wierstra |
| **机构** | Google DeepMind |
| **会议** | ICLR 2016 |
| **arXiv** | arXiv:1509.02971v5 |
| **核心贡献** | 将 DQN 的成功经验（replay buffer + target network）推广到连续动作空间，提出 DDPG 算法 |

---

## 1. 算法概述

### 1.1 一句话定位

**DDPG (Deep Deterministic Policy Gradient)** 是一种 **无模型 (model-free)、异策略 (off-policy)** 的 actor-critic 算法，专门设计用于 **连续且高维的动作空间**。

### 1.2 设计动机（Why）

**DQN 的局限**：DQN 在 Atari 等离散动作空间任务上取得了巨大成功，但无法直接应用于连续动作空间，因为：

- DQN 的核心操作是 $a^* = \arg\max_a Q(s,a)$
- 在连续动作空间中，每一步都需要求解一个非凸优化问题，计算代价过高

**朴素离散化的缺陷**：

- 维度灾难：7-DOF 机械臂，每个关节 3 档离散化 $\Rightarrow 3^7 = 2187$ 个动作
- 细粒度控制需要更精细的离散化 $\Rightarrow$ 动作数指数级增长
- 丢弃了动作空间的结构信息

**DDPG 的核心思想**：将 DQN 的两大创新（replay buffer + target network）嫁接到 **DPG (Deterministic Policy Gradient)** 框架上，使深度神经网络能在连续动作空间上稳定地学习。

---

## 2. 数学基础

### 2.1 强化学习基本框架

考虑标准的强化学习设定：智能体与环境 $E$ 在离散时间步上交互。

| 符号 | 含义 |
|------|------|
| $x_t$ | 时间步 $t$ 的观测 |
| $a_t \in \mathbb{R}^N$ | 时间步 $t$ 的动作（连续实值） |
| $r_t$ | 标量奖励信号 |
| $s_t = (x_1, a_1, \ldots, a_{t-1}, x_t)$ | 状态（完整历史） |
| $\pi: \mathcal{S} \to \mathcal{P}(\mathcal{A})$ | 策略，状态到动作分布的映射 |
| $\gamma \in [0, 1]$ | 折扣因子 |

**假设**：环境完全可观测，即 $s_t = x_t$。

**折扣回报**：

$$R_t = \sum_{i=t}^{T} \gamma^{i-t} r(s_i, a_i)$$

**目标函数**（从起始状态分布的期望回报）：

$$J = \mathbb{E}_{r_i, s_i \sim E, a_i \sim \pi} [R_1]$$

**动作价值函数**（Q 函数）：

$$Q^\pi(s_t, a_t) = \mathbb{E}_{r_{i \ge t}, s_{i > t} \sim E, a_{i > t} \sim \pi} [R_t \mid s_t, a_t]$$

### 2.2 贝尔曼方程

**随机策略的贝尔曼方程**：

$$Q^\pi(s_t, a_t) = \mathbb{E}_{r_t, s_{t+1} \sim E} \left[ r(s_t, a_t) + \gamma \mathbb{E}_{a_{t+1} \sim \pi} [Q^\pi(s_{t+1}, a_{t+1})] \right]$$

**确定性策略** $\mu: \mathcal{S} \to \mathcal{A}$ **的贝尔曼方程**（消除了内层期望）：

$$Q^\mu(s_t, a_t) = \mathbb{E}_{r_t, s_{t+1} \sim E} \left[ r(s_t, a_t) + \gamma Q^\mu(s_{t+1}, \mu(s_{t+1})) \right] \tag{3}$$

> **关键洞察**：在确定性策略下，目标值的计算只依赖于环境动态，不依赖于策略分布。这使得 **异策略 (off-policy)** 学习成为可能——我们可以使用行为策略 $\beta$ 生成的 transitions 来学习 $Q^\mu$。

### 2.3 Q-Learning 的损失函数

使用函数近似器 $Q(s,a|\theta^Q)$，最小化 Bellman 残差：

$$L(\theta^Q) = \mathbb{E}_{s_t \sim \rho^\beta, a_t \sim \beta, r_t \sim E} \left[ \left( Q(s_t, a_t | \theta^Q) - y_t \right)^2 \right] \tag{4}$$

其中 TD 目标：

$$y_t = r(s_t, a_t) + \gamma Q(s_{t+1}, \mu(s_{t+1}) | \theta^Q) \tag{5}$$

> **注意**：虽然 $y_t$ 也依赖于 $\theta^Q$，但在计算梯度时通常忽略这一点（即 stop-gradient）。

---

## 3. DDPG 算法

### 3.1 核心挑战与解决方案

| 挑战 | DQN 的解决方案 | DDPG 的适配方案 |
|------|---------------|----------------|
| 样本非独立同分布 | Replay Buffer | 同样使用 Replay Buffer |
| TD 目标不稳定 | Target Network（硬更新） | Target Network（**软更新**，$\tau \ll 1$） |
| 连续动作空间的贪婪策略 | 不适用 | **Actor-Critic** 架构：Actor 直接输出最优动作 |
| 不同特征的尺度差异 | — | **Batch Normalization** |

### 3.2 Actor-Critic 架构

DDPG 维护四个网络：

| 网络 | 符号 | 角色 |
|------|------|------|
| **Actor (策略网络)** | $\mu(s|\theta^\mu)$ | 确定性策略：$s \mapsto a$ |
| **Critic (Q 网络)** | $Q(s,a|\theta^Q)$ | 动作价值函数：$(s,a) \mapsto \mathbb{R}$ |
| **Target Actor** | $\mu'(s|\theta^{\mu'})$ | 软更新副本，用于计算稳定目标 |
| **Target Critic** | $Q'(s,a|\theta^{Q'})$ | 软更新副本，用于计算稳定目标 |

### 3.3 Critic 更新（Q-Learning）

从 replay buffer $\mathcal{R}$ 中采样一个大小为 $N$ 的 minibatch $(s_i, a_i, r_i, s_{i+1})$。

**TD 目标**（使用目标网络）：

$$y_i = r_i + \gamma Q'(s_{i+1}, \mu'(s_{i+1} | \theta^{\mu'}) | \theta^{Q'})$$

**Critic 损失**（均方贝尔曼误差）：

$$L = \frac{1}{N} \sum_{i=1}^{N} \left( y_i - Q(s_i, a_i | \theta^Q) \right)^2$$

**梯度**：

$$\nabla_{\theta^Q} L = \frac{1}{N} \sum_{i=1}^{N} \left[ -2 \left( y_i - Q(s_i, a_i | \theta^Q) \right) \nabla_{\theta^Q} Q(s_i, a_i | \theta^Q) \right]$$

### 3.4 Actor 更新（确定性策略梯度）

目标：最大化 $J = \mathbb{E}_{s \sim \rho^\mu} [Q(s, \mu(s|\theta^\mu) | \theta^Q)]$。

**确定性策略梯度定理** (Silver et al., 2014)：

$$\nabla_{\theta^\mu} J \approx \mathbb{E}_{s_t \sim \rho^\beta} \left[ \nabla_{\theta^\mu} Q(s, a | \theta^Q) \big|_{s=s_t, a=\mu(s_t)} \right] \tag{6}$$

应用链式法则：

$$\nabla_{\theta^\mu} J \approx \mathbb{E}_{s_t \sim \rho^\beta} \left[ \nabla_a Q(s, a | \theta^Q) \big|_{s=s_t, a=\mu(s_t)} \cdot \nabla_{\theta^\mu} \mu(s | \theta^\mu) \big|_{s=s_t} \right] \tag{6}$$

**采样近似**：

$$\nabla_{\theta^\mu} J \approx \frac{1}{N} \sum_{i=1}^{N} \left[ \nabla_a Q(s, a | \theta^Q) \big|_{s=s_i, a=\mu(s_i)} \cdot \nabla_{\theta^\mu} \mu(s | \theta^\mu) \big|_{s=s_i} \right]$$

> **梯度流向**：`actor_loss = -Q(states, actor(states)).mean()` → 梯度从 Critic 的输出回传到 Actor 的输入，再回传到 Actor 的参数 $\theta^\mu$。

### 3.5 目标网络的软更新

与 DQN 每隔若干步硬拷贝权重不同，DDPG 使用 **软更新 (soft update)**：

$$\theta^{Q'} \leftarrow \tau \theta^Q + (1 - \tau) \theta^{Q'}$$

$$\theta^{\mu'} \leftarrow \tau \theta^\mu + (1 - \tau) \theta^{\mu'}$$

其中 $\tau \ll 1$（通常 $\tau = 10^{-3}$）。

> **优势**：目标网络缓慢变化，极大提高了学习的稳定性，使 TD 误差的优化更接近监督学习。

### 3.6 探索策略

DDPG 是异策略算法，可以将探索与学习解耦。构造探索策略：

$$\mu'(s_t) = \mu(s_t | \theta_t^\mu) + \mathcal{N}_t \tag{7}$$

其中 $\mathcal{N}$ 是一个噪声过程。

**为什么使用 [[Ornstein-Uhlenbeck 噪声]]？**

- 物理控制任务（如机器人）具有**惯性**和**动量**
- 时间相关的有色噪声（OU 过程）比独立高斯噪声更适合这类系统
- OU 过程模拟了带摩擦的布朗运动，产生围绕 0 的时间相关值

**OU 过程定义**：

$$dx_t = \theta(\mu - x_t) dt + \sigma dW_t$$

其中 $dW_t$ 是维纳过程，$\theta$ 是均值回归系数，$\mu$ 是均值，$\sigma$ 是波动率。

**DDPG 中使用的参数**：$\theta = 0.15$，$\sigma = 0.2$。

### 3.7 Batch Normalization

**问题**：低维观测的不同分量可能具有不同的物理单位（如位置 vs 速度），尺度差异大，使网络难以有效学习。

**解决方案**：在状态输入和 $\mu$ 网络的所有层，以及 $Q$ 网络在动作输入之前的所有层使用 **Batch Normalization**。

**Batch Normalization 的数学定义**（对 minibatch 中的每个维度）：

$$\hat{x}_k = \frac{x_k - \mu_B}{\sqrt{\sigma_B^2 + \epsilon}}$$

$$y_k = \gamma \hat{x}_k + \beta$$

其中 $\mu_B$ 和 $\sigma_B^2$ 是 minibatch 的均值和方差，$\gamma$ 和 $\beta$ 是可学习的缩放和平移参数。

> **效果**：使算法能在不同尺度的任务上使用相同的超参数，无需手动归一化特征。

---

## 4. 算法伪代码

```
Algorithm 1: DDPG (Deep Deterministic Policy Gradient)

 1: 随机初始化 critic 网络 Q(s,a|θ^Q) 和 actor 网络 μ(s|θ^μ)
 2: 初始化 target 网络 Q' 和 μ'：θ^Q' ← θ^Q, θ^μ' ← θ^μ
 3: 初始化 replay buffer R
 4: for episode = 1 to M do
 5:     初始化一个随机过程 N 用于动作探索
 6:     接收初始观测状态 s_1
 7:     for t = 1 to T do
 8:         根据当前策略和探索噪声选择动作：
             a_t = μ(s_t|θ^μ) + N_t
 9:         执行动作 a_t，观察奖励 r_t 和新状态 s_{t+1}
10:         将 transition (s_t, a_t, r_t, s_{t+1}) 存储到 R
11:         从 R 中随机采样一个大小为 N 的 minibatch (s_i, a_i, r_i, s_{i+1})
12:         计算 TD 目标：
             y_i = r_i + γ Q'(s_{i+1}, μ'(s_{i+1}|θ^μ') | θ^Q')
13:         更新 critic 最小化损失：
             L = 1/N Σ_i (y_i - Q(s_i, a_i|θ^Q))^2
14:         使用采样策略梯度更新 actor：
             ∇_{θ^μ} J ≈ 1/N Σ_i ∇_a Q(s,a|θ^Q)|_{s=s_i,a=μ(s_i)} ∇_{θ^μ} μ(s|θ^μ)|_{s_i}
15:         软更新 target 网络：
             θ^Q' ← τ θ^Q + (1-τ) θ^Q'
             θ^μ' ← τ θ^μ + (1-τ) θ^μ'
16:     end for
17: end for
```

---

## 5. 网络架构

### 5.1 低维观测的架构

| 网络 | 输入层 | 隐藏层 | 输出层 | 激活函数 |
|------|--------|--------|--------|----------|
| **Actor** | 状态 $s$ | 2 层: 400, 300 | 动作 $a$ | 隐藏层: ReLU; 输出层: tanh |
| **Critic** | 状态 $s$ + 动作 $a$ | 2 层: 400, 300 | Q 值 | 隐藏层: ReLU; 输出层: 线性 |

**关键设计细节**：

- **Actor 输出层使用 tanh**：将动作限制在 $[-1, 1]$ 范围内
- **Critic 中动作不参与第一层**：状态先经过第一层（400 个单元），动作在第二层（300 个单元）才加入
- 这种设计使状态特征和动作特征在更高层次融合

**网络参数量**（低维情况）：

| 组件 | 参数数量 |
|------|----------|
| Actor | ~130,000 |
| Critic | ~130,000 |

**Actor 网络结构图**：

```
输入: s (状态维度 d_s)
        │
        ▼
┌───────────────────────────────┐
│  Linear(d_s, 400)             │  W₁: [400, d_s], b₁: [400]
│  BatchNorm(400)               │
│  ReLU                         │
└───────────────┬───────────────┘
        │  h₁ ∈ ℝ⁴⁰⁰
        ▼
┌───────────────────────────────┐
│  Linear(400, 300)             │  W₂: [300, 400], b₂: [300]
│  BatchNorm(300)               │
│  ReLU                         │
└───────────────┬───────────────┘
        │  h₂ ∈ ℝ³⁰⁰
        ▼
┌───────────────────────────────┐
│  Linear(300, d_a)             │  W₃: [d_a, 300], b₃: [d_a]
│  tanh                         │  输出 ∈ [-1, 1]^d_a
└───────────────┬───────────────┘
        │
        ▼
输出: a = tanh(W₃ h₂ + b₃) ∈ ℝᵈᵃ
```

**Critic 网络结构图**：

```
输入: s (状态)             输入: a (动作)
        │                        │
        ▼                        ▼
┌───────────────┐        ┌───────────────┐
│ Linear(d_s,400)│        │ Linear(d_a,300)│
│ BatchNorm(400) │        │                │
│ ReLU          │        │                │
└───────┬───────┘        └───────┬───────┘
        │                        │
        └────────────┬───────────┘
                     ▼
              ┌───────────────┐
              │  Concat       │  [h_s; a] ∈ ℝ⁴⁰⁰⁺ᵈᵃ
              └───────┬───────┘
                     ▼
┌───────────────────────────────┐
│  Linear(400 + d_a, 300)       │  W₂: [300, 400+d_a], b₂: [300]
│  BatchNorm(300)               │
│  ReLU                         │
└───────────────┬───────────────┘
        │
        ▼
┌───────────────────────────────┐
│  Linear(300, 1)               │  W₃: [1, 300], b₃: [1]
│  （线性，无激活）              │
└───────────────┬───────────────┘
        │
        ▼
输出: Q(s,a) ∈ ℝ
```

### 5.2 像素观测的架构

| 组件 | 详细结构 |
|------|----------|
| **卷积层** | 3 层卷积，每层 32 个滤波器，无池化 |
| **全连接层** | 2 层，每层 200 个单元 |
| **总参数** | ~430,000 |

**像素输入的处理**：

- 每 3 个模拟时间步执行一次动作（action repeat）
- 观测包含 9 个特征图（3 帧 RGB，每帧 3 通道）
- 帧降采样到 64×64 像素
- RGB 值转换为浮点数并缩放到 $[0, 1]$

### 5.3 权重初始化

| 层 | 初始化方法 | 公式 |
|----|-----------|------|
| 隐藏层权重 | Xavier Uniform | $W \sim U[-1/\sqrt{f}, 1/\sqrt{f}]$，$f$ 为 fan-in |
| 隐藏层偏置 | 零初始化 | $b = 0$ |
| **低维输出层** | 小均匀分布 | $W_{\text{out}} \sim U[-3\times 10^{-3}, 3\times 10^{-3}]$ |
| **像素输出层** | 更小均匀分布 | $W_{\text{out}} \sim U[-3\times 10^{-4}, 3\times 10^{-4}]$ |

> **设计意图**：输出层使用小初始化，确保初始策略输出接近 0（动作接近 0），初始 Q 值接近 0，避免初期随机的大动作导致训练不稳定。

---

## 6. 超参数

### 6.1 完整超参数表

| 参数 | 符号 | 取值 | 说明 |
|------|------|------|------|
| Actor 学习率 | $\alpha_\mu$ | $10^{-4}$ | Adam 优化器 |
| Critic 学习率 | $\alpha_Q$ | $10^{-3}$ | Adam 优化器 |
| 折扣因子 | $\gamma$ | 0.99 | 未来奖励的衰减 |
| 软更新系数 | $\tau$ | $10^{-3}$ | 目标网络更新速率 |
| Replay Buffer 容量 | $\|\mathcal{R}\|$ | $10^6$ | FIFO 循环缓冲区 |
| **低维 minibatch** | $N$ | **64** | 采样批次大小 |
| **像素 minibatch** | $N$ | **16** | 采样批次大小 |
| Critic L2 正则化 | $\lambda$ | $10^{-2}$ | 权重衰减系数 |
| 隐藏层激活函数 | — | ReLU | 所有隐藏层 |
| Actor 输出激活 | — | tanh | 输出到 $[-1,1]$ |

### 6.2 OU 噪声参数

| 参数 | 取值 | 含义 |
|------|------|------|
| $\theta$ | 0.15 | 均值回归速度 |
| $\sigma$ | 0.2 | 波动率（噪声强度） |

### 6.3 各任务维度信息

| 任务名称 | dim(s) | dim(a) | dim(o) | 简要描述 |
|----------|--------|--------|--------|----------|
| blockworld1 | 18 | 5 | 43 | 2D 平面抓取块体并提升至目标 |
| cartpole | 4 | 1 | 4 | 经典倒立摆 |
| cheetah | 18 | 6 | 17 | 四足奔跑 |
| hopper | 14 | 4 | 14 | 单足跳跃 |
| walker2d | 18 | 6 | 41 | 双足行走 |
| pendulum | 2 | 1 | 3 | 摆杆起摆 |
| reacher | 10 | 3 | 23 | 3-DOF 机械臂到达随机目标 |
| reacher3da | 20 | 7 | 61 | 7-DOF 人形臂到达目标 |
| gripper | 18 | 5 | 43 | 抓取操作 |
| torcs | — | 3 | — | 赛车游戏（加速/刹车/转向） |

---

## 7. 实验与结果

### 7.1 评估协议

- 每个环境运行 5 个随机种子
- 定期评估策略（不加探索噪声）
- 归一化分数：随机策略 = 0，iLQG 规划器 = 1

### 7.2 关键发现

1. **Target Network 至关重要**：没有 target network 时，在大多数环境中学习非常差

2. **Batch Normalization 至关重要**：使算法能在不同尺度的问题上使用相同的超参数

3. **从像素学习**：在简单任务上，从像素学习与从低维状态学习一样快

4. **Q 值估计的准确性**：
   - 在简单任务（pendulum, cartpole）上，Q 值估计非常准确
   - 在复杂任务上，Q 值估计不太准确，但仍足以学习良好策略

5. **数据效率**：所有任务在 250 万步经验内解决，比 DQN 在 Atari 上的样本效率高约 20 倍

### 7.3 与 iLQG 规划器的比较

iLQG 是一个有完整模型访问权限的规划器，在所有任务上均达到 1 的归一化分数。DDPG 在许多任务上达到了可比甚至超越 iLQG 的性能，甚至在从像素学习时也是如此。

---

## 8. 与 ERL 报告的关联

ERL（Evolution-Guided Policy Gradient）以 DDPG 作为其 RL 核心组件。理解 DDPG 是理解 ERL 的前提：

| ERL 组件 | 对应 DDPG 概念 |
|----------|---------------|
| rl_actor 更新 | DDPG Actor 的确定性策略梯度更新 |
| rl_critic 更新 | DDPG Critic 的 Q-Learning 更新 |
| Target 网络软更新 | 与 DDPG 完全相同：$\theta' \leftarrow \tau\theta + (1-\tau)\theta'$ |
| OU 噪声探索 | 与 DDPG 相同 |
| Replay Buffer | 与 DDPG 相同，但 ERL 额外注入种群轨迹 |
| Batch Normalization | 与 DDPG 相同 |

**ERL 在 DDPG 基础上的核心扩展**：

1. 引入 EA 种群生成多样化轨迹注入 replay buffer
2. 周期性地将 rl_actor 参数复制到种群最差个体
3. 使用 episode-级 fitness 作为 EA 选择压力

---

## 9. 参考文献

[1] Lillicrap, T. P., Hunt, J. J., Pritzel, A., Heess, N., Erez, T., Tassa, Y., Silver, D., & Wierstra, D. (2016). *Continuous control with deep reinforcement learning*. ICLR 2016. arXiv:1509.02971.

[2] Silver, D., Lever, G., Heess, N., Degris, T., Wierstra, D., & Riedmiller, M. (2014). *Deterministic Policy Gradient Algorithms*. ICML 2014.

[3] Mnih, V., Kavukcuoglu, K., Silver, D., et al. (2015). *Human-level control through deep reinforcement learning*. Nature, 518(7540):529-533.

[4] Mnih, V., Kavukcuoglu, K., Silver, D., Graves, A., Antonoglou, I., Wierstra, D., & Riedmiller, M. (2013). *Playing Atari with Deep Reinforcement Learning*. NIPS Deep Learning Workshop. arXiv:1312.5602.

[5] Ioffe, S., & Szegedy, C. (2015). *Batch Normalization: Accelerating Deep Network Training by Reducing Internal Covariate Shift*. ICML 2015. arXiv:1502.03167.

[6] Uhlenbeck, G. E., & Ornstein, L. S. (1930). *On the theory of the Brownian motion*. Physical Review, 36(5):823.

[7] Todorov, E., Erez, T., & Tassa, Y. (2012). *MuJoCo: A physics engine for model-based control*. IROS 2012.

[8] Todorov, E., & Li, W. (2005). *A generalized iterative LQG method for locally-optimal feedback control of constrained nonlinear stochastic systems*. ACC 2005.

[9] Kingma, D., & Ba, J. (2014). *Adam: A method for stochastic optimization*. arXiv:1412.6980.

[10] Glorot, X., Bordes, A., & Bengio, Y. (2011). *Deep Sparse Rectifier Networks*. AISTATS 2011.