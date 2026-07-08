---
description: Q-Learning 时序差分算法
concepts:
- id: q-learning
  name: Q-Learning 算法
  weight: 1.0
  tags:
  - td-learning
  - value-function
  - off-policy
- id: epsilon-greedy
  name: ε-greedy 探索策略
  weight: 0.6
- name: td-learning
  weight: 0.5
---
# Q-Learning 算法

Q-Learning（Watkins, 1989）是一种 off-policy 的时序差分（TD）控制方法。它通过学习动作价值函数 $Q(s, a)$ 来找到最优策略，不需要环境模型，也不需要完整的轨迹。

Q-Learning 是强化学习中最著名的算法之一，它简洁、有效、理论保证强。DeepMind 在 2015 年将 Q-Learning 与深度学习结合（DQN），实现了在 Atari 游戏上达到人类水平的突破，开启了深度强化学习时代。Q-Learning 的数学基础来自 [[mdp]] 和 [[rl]]。Q-Learning 是 [[ddpg]] 等深度强化学习方法的基础。

Q-Learning 的核心创新是 off-policy 学习：它直接学习最优 Q 函数，而不管智能体实际遵循什么策略。这意味着即使使用随机探索策略，也能收敛到最优值。

## 更新规则

Q-Learning 的更新规则：

$$
Q(s, a) \leftarrow Q(s, a) + \alpha \left[r + \gamma \max_{a'} Q(s', a') - Q(s, a)\right]
$$

其中：
- $\alpha$ 是学习率
- $\gamma$ 是折扣因子
- $r + \gamma \max_{a'} Q(s', a')$ 是 TD 目标
- $\max_{a'} Q(s', a')$ 是对下一状态的最优动作价值的估计

这个更新规则的直觉是：用"一步前瞻"的最优估计来改进当前估计。如果 TD 目标大于当前 Q 值，说明这个状态-动作对比预期更好，应该上调；反之则下调。

收敛性保证：在满足以下条件时，Q-Learning 收敛到最优 $Q^*$：
1. 所有状态-动作对被无限次访问
2. 学习率 $\alpha$ 满足 Robbins-Monro 条件：$\sum \alpha = \infty$，$\sum \alpha^2 < \infty$

实践中，常使用固定学习率（如 $\alpha = 0.1$），在有限迭代中获得足够好的近似。

## ε-greedy 探索策略

为了平衡探索与利用，Q-Learning 通常配合 $\varepsilon$-greedy 策略使用：

- 以概率 $\varepsilon$ 随机选择动作（探索）
- 以概率 $1-\varepsilon$ 选择当前 Q 值最大的动作（利用）

$\varepsilon$ 的选择很关键：
- $\varepsilon = 0$：纯利用，可能陷入局部最优
- $\varepsilon = 1$：纯探索，无法利用已学知识
- 常见做法：$\varepsilon$ 从 1.0 线性衰减到 0.1

更高级的探索策略包括：
- **Boltzmann 探索**：按 Q 值的 Softmax 分布选择动作
- **UCB**：选择不确定性最高的动作
- **Noisy Networks**：在网络参数中注入噪声

Q-Learning 的特点：
- **Off-policy**：学习目标策略与行为策略可以不同。即使行为策略是随机的，也能学到最优策略
- **Model-free**：不需要知道 $P(s'|s,a)$ 和 $R(s,a)$
- **收敛保证**：在表格情况下可证明收敛到最优 Q 函数

DQN 将 Q-Learning 与深度网络结合，而 DDPG 将其扩展到连续动作空间。
