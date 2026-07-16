---
description: 策略梯度方法
concepts:
- id: policy-gradient
  name: 策略梯度
  weight: 1.0
  tags:
  - on-policy
  - actor-critic
- id: reinforce
  name: REINFORCE 算法
  weight: 0.7
- id: actor-critic
  name: Actor-Critic 框架
  weight: 0.8
---
# 策略梯度

策略梯度（Policy Gradient）方法直接参数化策略 $\pi_\theta(a|s)$，通过梯度上升最大化期望累积奖励 $J(\theta)$。与基于价值的方法（如 [[q-learning]]）不同，策略梯度直接优化策略本身。策略梯度的理论前提是 [[rl]]。[[ddpg]] 是策略梯度在连续动作空间上的扩展。

策略梯度的核心优势：
- **连续动作**：天然支持连续动作空间，无需离散化
- **随机策略**：可以学习真正的随机策略，有利于探索
- **策略不变性**：策略参数化后，策略的变化更加平滑

策略梯度定理（Sutton et al., 1999）是策略梯度方法的理论基础：

$$
\nabla J(\theta) = \mathbb{E}_{\pi_\theta}\!\left[\nabla \log \pi_\theta(a|s) \cdot Q^{\pi_\theta}(s, a)\right]
$$

这个定理告诉我们：策略梯度的方向，就是让好动作概率增大、坏动作概率减小的方向。

## REINFORCE 算法

REINFORCE（Williams, 1992）是最基础的策略梯度方法，使用蒙特卡洛采样估计梯度：

$$
\nabla J(\theta) \approx \frac{1}{N} \sum \nabla \log \pi_\theta(a_t|s_t) \cdot G_t
$$

其中 $G_t$ 是从时间步 $t$ 开始的实际累积回报。

REINFORCE 的特点：
- **无偏**：使用真实回报，梯度估计无偏
- **高方差**：不同轨迹的回报差异很大，导致梯度估计方差极高
- **在线学习**：必须等一条轨迹结束才能更新

降低方差的技术：
1. **基线（Baseline）**：从回报中减去基线 $b(s)$

$$
\nabla J(\theta) \approx \sum \nabla \log \pi_\theta(a_t|s_t) \cdot \bigl(G_t - b(s_t)\bigr)
$$

合理的基线选择：状态价值函数 $V(s)$

2. **优势函数**：用优势函数 $A(s,a) = Q(s,a) - V(s)$ 替代原始回报，等价于使用 $V(s)$ 作为基线

3. **因果性**：只使用从 $t$ 时刻开始的回报，不使用 $t$ 之前的回报

## Actor-Critic 框架

Actor-Critic 框架结合了策略梯度和价值函数方法的优点：

- **Actor（演员）**：学习策略 $\pi_\theta(a|s)$，负责选择动作
- **Critic（评论家）**：学习价值函数 $V_\phi(s)$ 或 $Q_\phi(s,a)$，负责评估动作的好坏

Critic 的作用是提供更准确的梯度估计。在 REINFORCE 中，我们用蒙特卡洛回报 $G_t$ 作为梯度的权重，方差很大。Actor-Critic 用 Critic 的估计替代 $G_t$，显著降低方差，但引入了偏差。

典型的 Actor-Critic 更新：
1. 用当前策略采样转移 $(s, a, r, s')$
2. 计算 TD 误差：$\delta = r + \gamma V(s') - V(s)$
3. 更新 Critic：$V(s) \leftarrow V(s) + \alpha_v \cdot \delta$
4. 更新 Actor：$\theta \leftarrow \theta + \alpha_\pi \cdot \nabla \log \pi(a|s) \cdot \delta$

Actor-Critic 的变体：
- **A2C/A3C**：使用 n-step 或 GAE 估计优势
- **PPO**：限制策略更新幅度，保证稳定性
- **SAC**：加入熵正则化，鼓励探索

DDPG 是 Actor-Critic 在连续动作空间上的扩展，使用确定性策略梯度而非随机策略梯度。
