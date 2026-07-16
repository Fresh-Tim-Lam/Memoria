---
description: 强化学习的数学基础
concepts:
- id: mdp
  name: 马尔可夫决策过程
  weight: 1.0
  tags:
  - reinforcement-learning
  - markov
  - fundamentals
- id: bellman
  name: 贝尔曼方程
  weight: 0.8
  tags:
  - dynamic-programming
- name: markov-property
  weight: 0.5
---
# 马尔可夫决策过程

马尔可夫决策过程（Markov Decision Process, MDP）是强化学习的数学基础框架，由五元组 $(S, A, P, R, \gamma)$ 定义。它为序贯决策问题提供了严格的数学描述。

MDP 的历史可以追溯到 1950 年代 Bellman 的工作，它是动态规划、最优控制理论的基础。[[bellman]] 描述了价值函数的递归结构，是 MDP 求解的核心。在强化学习中，MDP 提供了问题建模的标准形式——几乎所有 RL 问题都可以表述为 MDP 或其变体。

MDP 的关键假设是马尔可夫性：未来只取决于当前状态，与历史无关。这个假设极大地简化了问题，同时在许多实际问题中也是合理的近似。

## 核心要素

MDP 由以下要素定义：

- **S（状态空间）**：环境可能处于的所有状态的集合。状态应该包含做出最优决策所需的全部信息（马尔可夫性）。
  - 有限 MDP：$|S|$ 有限，如棋盘游戏
  - 连续 MDP：$S \subseteq \mathbb{R}^n$，如机器人控制

- **A（动作空间）**：智能体可以采取的所有动作的集合。
  - 离散动作：如上下左右
  - 连续动作：如关节力矩

- **P（状态转移概率）**：$P(s'|s,a)$ 定义了在状态 $s$ 执行动作 $a$ 后转移到 $s'$ 的概率。这是环境的"物理法则"。

- **R（奖励函数）**：$R(s,a)$ 或 $R(s,a,s')$ 定义了即时奖励。它编码了智能体的目标。

- **γ（折扣因子）**：$\gamma \in [0, 1)$ 控制对未来奖励的重视程度。$\gamma = 0$ 表示只关心即时奖励，$\gamma \to 1$ 表示越来越重视长远。

策略 $\pi(a|s)$ 定义了在每个状态选择每个动作的概率。最优策略 $\pi^*$ 使得期望累积奖励最大化。

## 贝尔曼方程

贝尔曼方程描述了价值函数的递归关系，是强化学习算法的理论基石。

**状态价值函数** $V^\pi(s)$：从状态 $s$ 出发、遵循策略 $\pi$ 的期望回报：

$$
V^\pi(s) = \mathbb{E}_\pi[G_t \mid S_t = s] = \mathbb{E}_\pi[R_{t+1} + \gamma V^\pi(S_{t+1}) \mid S_t = s]
$$

贝尔曼期望方程将价值函数分解为即时奖励和下一状态的价值：

$$
V^\pi(s) = \sum_a \pi(a|s) \sum_{s'} P(s'|s,a) \left[R(s,a) + \gamma V^\pi(s')\right]
$$

**最优价值函数** $V^*(s)$ 是所有策略中最大的价值函数：

$$
V^*(s) = \max_\pi V^\pi(s)
$$

贝尔曼最优方程：

$$
V^*(s) = \max_a \sum_{s'} P(s'|s,a) \left[R(s,a) + \gamma V^*(s')\right]
$$

类似地，**动作价值函数** $Q^*(s,a)$：

$$
Q^*(s,a) = \sum_{s'} P(s'|s,a) \left[R(s,a) + \gamma \max_{a'} Q^*(s',a')\right]
$$

贝尔曼方程之所以重要，是因为：
1. 它提供了价值函数的计算方法
2. 它是动态规划和时序差分方法的理论基础
3. 它揭示了价值的递归结构，使得迭代求解成为可能




的方式倒萨倒萨倒萨倒萨倒萨倒萨打算乱码去8u*（YHEO（LDWUIGDKUSB




[[q-learning]] 和 [[policy-gradient]] 都建立在贝尔曼方程的理论框架之上。Q-Learning 直接学习 $Q^*$ 函数，策略梯度则通过梯度优化策略参数。
