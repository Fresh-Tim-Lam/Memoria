---
description: 用于连续动作空间的深度确定性策略梯度
concepts:
- id: ddpg
  name: DDPG
  weight: 1.0
  tags:
  - actor-critic
  - continuous-action
  - off-policy
- id: ddpg-actor
  name: Actor 网络
  weight: 0.7
- id: ddpg-critic
  name: Critic 网络
  weight: 0.7
- id: experience-replay
  name: 经验回放
  weight: 0.6
---
# DDPG

Deep Deterministic Policy Gradient（DDPG，Lillicrap et al., 2015）是一种用于连续动作空间的深度强化学习方法。它结合了 [[q-learning]] 的经验回放和目标网络技巧与 [[policy-gradient]] 的确定性策略梯度定理，实现了在连续控制任务上的高效学习。

DDPG 的提出解决了两个关键问题：
1. 如何将 DQN 的成功经验（经验回放、目标网络）迁移到连续动作空间
2. 如何在连续动作空间中高效计算 $\max_a Q(s,a)$

答案是确定性策略梯度（Deterministic Policy Gradient, DPG）。与随机策略梯度不同，DPG 的策略直接输出确定性动作 $a = \mu_\theta(s)$，梯度可以通过链式法则高效计算。

## Actor 网络

Actor 网络 $\mu(s|\theta^\mu)$ 接收状态 $s$，输出确定性动作 $a$。它是一个将状态映射到动作的函数近似器。

Actor 的更新目标：最大化 Q 值。通过链式法则：

$$
\nabla_\theta J \approx \mathbb{E}\!\left[\nabla_a Q(s, a|\theta^Q)\big|_{a=\mu(s)} \cdot \nabla_\theta \mu(s|\theta^\mu)\right]
$$

这个梯度的直觉是：先找到 Q 值关于动作的梯度方向（Critic 告诉 Actor 怎么改进动作），再通过 Actor 网络反传更新参数。

Actor 网络结构通常为：
- 输入层：状态维度
- 隐藏层：2-3 层全连接，ReLU 激活，Batch Normalization
- 输出层：动作维度，tanh 激活（将输出限制在 $[-1, 1]$）

Batch Normalization 对 DDPG 特别重要，因为状态和动作的量级差异很大，BN 可以稳定训练。

## Critic 网络

Critic 网络 $Q(s, a|\theta^Q)$ 接收状态-动作对 $(s, a)$，输出 Q 值估计。它负责评估当前策略下动作的好坏。

Critic 的更新类似 DQN：

$$
L = \mathbb{E}\!\left[\bigl(Q(s, a|\theta^Q) - y\bigr)^2\right]
$$

其中 $y = r + \gamma Q'\!\left(s', \mu'(s'|\theta^{\mu'})|\theta^{Q'}\right)$ 是 TD 目标，使用目标网络计算。

Critic 网络结构：
- 输入：状态和动作的拼接（先处理状态，中间层再混入动作）
- 隐藏层：2-3 层全连接 + ReLU + BN
- 输出：标量 Q 值

## 经验回放

经验回放（Experience Replay）将转移 $(s, a, r, s')$ 存入回放缓冲区 $\mathcal{R}$，训练时随机采样 mini-batch。

为什么需要经验回放？
1. **打破时序相关性**：连续样本高度相关，违反 i.i.d. 假设
2. **提高数据效率**：一条经验可以被多次使用
3. **稳定训练**：均匀采样避免最近经验主导梯度

回放缓冲区的大小通常为 $10^6$，mini-batch 大小为 64-256。

DDPG 的关键技巧：
- **目标网络 + 软更新**：$\theta' \leftarrow \tau\theta + (1-\tau)\theta'$，$\tau \ll 1$（通常 $0.001$）
- **探索噪声**：Ornstein-Uhlenbeck 过程或高斯噪声
- **梯度裁剪**：防止梯度爆炸

DDPG 基于 Q-Learning 和策略梯度的思想，是深度强化学习在连续控制领域的里程碑。后续改进包括 TD3（Twin Delayed DDPG）和 SAC（Soft Actor-Critic）。
