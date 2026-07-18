# 策略梯度定理完整推导汇报

## 0. 摘要

本报告系统推导**策略梯度定理 (Policy Gradient Theorem)**，该定理是深度强化学习中所有策略梯度方法（REINFORCE、Actor-Critic、PPO、TRPO、DDPG 等）的数学基石。我们从策略梯度定理的原始形式出发，给出从目标函数定义到最终定理形式的完整、逐行、无跳步的数学推导。

**核心结论**：

$$
\boxed{\nabla_\theta J(\pi_\theta) = \mathbb{E}_{s \sim \rho^\pi, a \sim \pi_\theta} \left[ \nabla_\theta \log \pi_\theta(a|s) \cdot Q^\pi(s,a) \right]}
$$

---

## 1. 符号与设定

| 符号 | 含义 |
|------|------|
| $\mathcal{S}$ | 状态空间 |
| $\mathcal{A}$ | 动作空间（离散或连续） |
| $\pi_\theta(a \mid s)$ | 参数为 $\theta$ 的随机策略 |
| $\gamma \in [0,1)$ | 折扣因子 |
| $P(s' \mid s, a)$ | 状态转移概率 |
| $R(s, a)$ | 即时奖励函数 |
| $d_0(s)$ | 初始状态分布 |
| $\rho^\pi(s)$ | 折扣状态分布：$\sum_{t=0}^{\infty} \gamma^t \Pr(s_t = s \mid \pi)$ |
| $Q^\pi(s, a)$ | 动作价值函数 |
| $V^\pi(s)$ | 状态价值函数 |
| $A^\pi(s, a) = Q^\pi(s,a) - V^\pi(s)$ | 优势函数 |
| $\eta(\pi)$ 或 $J(\pi_\theta)$ | 策略性能目标 |

---

## 2. 目标函数的定义

### 2.1 三种等价定义

强化学习的目标是最大化期望累积折扣回报。以下三种定义在文献中均被使用，它们本质等价：

**定义一（基于初始状态分布）**：

$$
J_1(\theta) = \mathbb{E}_{s_0 \sim d_0} \left[ V^{\pi_\theta}(s_0) \right] = \int_{\mathcal{S}} d_0(s) V^{\pi_\theta}(s) ds \tag{1}
$$

**定义二（[[基于折扣状态分布]]）**：

$$
J_2(\theta) = \mathbb{E}_{s \sim \rho^{\pi_\theta}, a \sim \pi_\theta} \left[ R(s,a) \right] = \int_{\mathcal{S}} \rho^{\pi_\theta}(s) \int_{\mathcal{A}} \pi_\theta(a|s) R(s,a) \, da \, ds \tag{2}
$$

**定义三（基于平均回报，适用于无折扣情形）**：

$$
J_3(\theta) = \lim_{T \to \infty} \frac{1}{T} \mathbb{E} \left[ \sum_{t=0}^{T-1} R(s_t, a_t) \right] \tag{3}
$$

> **说明**：本报告使用定义一 $J(\theta) = \mathbb{E}_{s_0 \sim d_0}[V^{\pi_\theta}(s_0)]$，这是 Sutton 等人在原始策略梯度定理论文中使用的形式，也是后续推导中最方便的形式。

---

## 3. 预备知识

### 3.1 策略梯度的链式结构

策略梯度方法的核心思想是：**直接对策略参数 $\theta$ 求梯度，而不是对价值函数求梯度**。

目标函数 $J(\theta)$ 对 $\theta$ 的依赖关系是一个复杂的递归结构：

$$
J(\theta) = \mathbb{E}_{s_0 \sim d_0} \left[ \underbrace{\mathbb{E}_{a_0 \sim \pi_\theta(\cdot|s_0)} \left[ R(s_0, a_0) + \gamma \underbrace{\mathbb{E}_{s_1 \sim P(\cdot|s_0,a_0)} \left[ V^{\pi_\theta}(s_1) \right]}_{依赖于\theta} \right]}_{依赖于\theta} \right]
$$

**核心难点**：$V^{\pi_\theta}(s)$ 本身通过贝尔曼方程隐式依赖于 $\theta$，且这种依赖通过未来的所有时间步递归传播。策略梯度定理的作用就是**消除这种递归依赖**，将梯度表示为一个简洁的期望形式。

---

## 4. 策略梯度定理：原始形式与证明

### 4.1 定理陈述

**策略梯度定理 (Sutton et al., 2000)**：

对于可微分的策略 $\pi_\theta(a|s)$，目标函数 $J(\theta) = \mathbb{E}_{s_0 \sim d_0}[V^{\pi_\theta}(s_0)]$ 的梯度为：

$$
\boxed{\nabla_\theta J(\theta) = \mathbb{E}_{s \sim \rho^{\pi_\theta}, a \sim \pi_\theta} \left[ \nabla_\theta \log \pi_\theta(a|s) \cdot Q^{\pi_\theta}(s,a) \right]} \tag{4}
$$

其中 $\rho^{\pi_\theta}(s) = \sum_{t=0}^{\infty} \gamma^t \Pr(s_t = s \mid s_0 \sim d_0, \pi_\theta)$ 是折扣状态分布。

---

### 4.2 证明：逐行推导

#### Step 1：定义性能目标

$$
J(\theta) = \int_{\mathcal{S}} d_0(s) V^{\pi_\theta}(s) \, ds \tag{5}
$$

对 $\theta$ 求梯度：

$$
\nabla_\theta J(\theta) = \int_{\mathcal{S}} d_0(s) \nabla_\theta V^{\pi_\theta}(s) \, ds \tag{6}
$$

> 至此，问题转化为：**如何计算 $\nabla_\theta V^{\pi_\theta}(s)$？**

---

#### Step 2：对 $V^{\pi_\theta}(s)$ 求梯度——第一步展开

利用贝尔曼方程 $V^{\pi_\theta}(s) = \int_{\mathcal{A}} \pi_\theta(a|s) Q^{\pi_\theta}(s,a) \, da$：

$$
\nabla_\theta V^{\pi_\theta}(s) = \nabla_\theta \int_{\mathcal{A}} \pi_\theta(a|s) Q^{\pi_\theta}(s,a) \, da \tag{7}
$$

被积函数 $\pi_\theta(a|s) Q^{\pi_\theta}(s,a)$ 同时通过 $\pi_\theta$ 和 $Q^{\pi_\theta}$ 依赖于 $\theta$（$Q^{\pi_\theta}$ 又通过贝尔曼方程递归依赖于 $\theta$）。应用乘积法则：

$$
\nabla_\theta V^{\pi_\theta}(s) = \int_{\mathcal{A}} \left[ \nabla_\theta \pi_\theta(a|s) Q^{\pi_\theta}(s,a) + \pi_\theta(a|s) \nabla_\theta Q^{\pi_\theta}(s,a) \right] da \tag{8}
$$

---

#### Step 3：展开 $\nabla_\theta Q^{\pi_\theta}(s,a)$

利用 $Q^{\pi_\theta}(s,a)$ 的贝尔曼方程：

$$
Q^{\pi_\theta}(s,a) = R(s,a) + \gamma \int_{\mathcal{S}} P(s'|s,a) V^{\pi_\theta}(s') \, ds' \tag{9}
$$

求梯度（$R(s,a)$ 不依赖于 $\theta$，导数为 0）：

$$
\nabla_\theta Q^{\pi_\theta}(s,a) = \gamma \int_{\mathcal{S}} P(s'|s,a) \nabla_\theta V^{\pi_\theta}(s') \, ds' \tag{10}
$$

---

#### Step 4：代回 (8)

$$
\nabla_\theta V^{\pi_\theta}(s) = \int_{\mathcal{A}} \nabla_\theta \pi_\theta(a|s) Q^{\pi_\theta}(s,a) \, da + \gamma \int_{\mathcal{A}} \pi_\theta(a|s) \int_{\mathcal{S}} P(s'|s,a) \nabla_\theta V^{\pi_\theta}(s') \, ds' \, da \tag{11}
$$

---

#### Step 5：定义算子 $\mathcal{P}^{\pi_\theta}$

定义**状态转移算子** $\mathcal{P}^{\pi_\theta}$，作用于任意函数 $f: \mathcal{S} \to \mathbb{R}$：

$$
(\mathcal{P}^{\pi_\theta} f)(s) \triangleq \int_{\mathcal{A}} \pi_\theta(a|s) \int_{\mathcal{S}} P(s'|s,a) f(s') \, ds' \, da = \mathbb{E}_{a \sim \pi_\theta, s' \sim P} [f(s') \mid s] \tag{12}
$$

同时定义：

$$
\psi(s) \triangleq \int_{\mathcal{A}} \nabla_\theta \pi_\theta(a|s) Q^{\pi_\theta}(s,a) \, da \tag{13}
$$

则 (11) 可写成算子形式：

$$
\nabla_\theta V^{\pi_\theta} = \psi + \gamma \mathcal{P}^{\pi_\theta} \nabla_\theta V^{\pi_\theta} \tag{14}
$$

---

#### Step 6：求解算子方程

(14) 是一个线性算子方程。移项：

$$
(I - \gamma \mathcal{P}^{\pi_\theta}) \nabla_\theta V^{\pi_\theta} = \psi \tag{15}
$$

由于 $\|\gamma \mathcal{P}^{\pi_\theta}\|_\infty \le \gamma < 1$（[[原因]]），算子 $I - \gamma \mathcal{P}^{\pi_\theta}$ [[可逆]]，其逆为 Neumann 级数：

$$
\nabla_\theta V^{\pi_\theta} = (I - \gamma \mathcal{P}^{\pi_\theta})^{-1} \psi = \sum_{k=0}^{\infty} (\gamma \mathcal{P}^{\pi_\theta})^k \psi \tag{16}
$$

---

#### Step 7：展开 $\psi$ 的定义

将 $\psi$ 的定义 (13) 代入 (16)：

$$
\nabla_\theta V^{\pi_\theta}(s) = \sum_{k=0}^{\infty} (\gamma \mathcal{P}^{\pi_\theta})^k \int_{\mathcal{A}} \nabla_\theta \pi_\theta(a|s) Q^{\pi_\theta}(s,a) \, da \tag{17}
$$

---

#### Step 8：代入目标函数的梯度 (6)

$$
\nabla_\theta J(\theta) = \int_{\mathcal{S}} d_0(s) \sum_{k=0}^{\infty} (\gamma \mathcal{P}^{\pi_\theta})^k \int_{\mathcal{A}} \nabla_\theta \pi_\theta(a|s) Q^{\pi_\theta}(s,a) \, da \, ds \tag{18}
$$

交换求和与积分：

$$
\nabla_\theta J(\theta) = \int_{\mathcal{S}} \sum_{k=0}^{\infty} \gamma^k \Pr(s_k = s \mid s_0 \sim d_0, \pi_\theta) \int_{\mathcal{A}} \nabla_\theta \pi_\theta(a|s) Q^{\pi_\theta}(s,a) \, da \, ds \tag{19}
$$

---

#### Step 9：识别折扣状态分布

定义折扣状态分布：

$$
\rho^{\pi_\theta}(s) \triangleq \sum_{k=0}^{\infty} \gamma^k \Pr(s_k = s \mid s_0 \sim d_0, \pi_\theta) \tag{20}
$$

则 (19) 简化为：

$$
\nabla_\theta J(\theta) = \int_{\mathcal{S}} \rho^{\pi_\theta}(s) \int_{\mathcal{A}} \nabla_\theta \pi_\theta(a|s) Q^{\pi_\theta}(s,a) \, da \, ds \tag{21}
$$

---

#### Step 10：对数导数技巧（核心步骤）

利用恒等式 $\nabla_\theta \pi_\theta(a|s) = \pi_\theta(a|s) \nabla_\theta \log \pi_\theta(a|s)$（因为 $\nabla_\theta \log \pi = \nabla_\theta \pi / \pi$）：

$$
\nabla_\theta J(\theta) = \int_{\mathcal{S}} \rho^{\pi_\theta}(s) \int_{\mathcal{A}} \pi_\theta(a|s) \nabla_\theta \log \pi_\theta(a|s) Q^{\pi_\theta}(s,a) \, da \, ds \tag{22}
$$

---

#### Step 11：写成期望形式

将 (22) 写为期望形式：

$$
\boxed{\nabla_\theta J(\theta) = \mathbb{E}_{s \sim \rho^{\pi_\theta}, a \sim \pi_\theta} \left[ \nabla_\theta \log \pi_\theta(a|s) \cdot Q^{\pi_\theta}(s,a) \right]} \tag{23}
$$

**证毕。**

---

## 5. 关键步骤详解

### 5.1 为什么 $\|\gamma \mathcal{P}^{\pi_\theta}\|_\infty < 1$？

对于任意有界函数 $f$：

$$
|(\gamma \mathcal{P}^{\pi_\theta} f)(s)| = \gamma \left| \mathbb{E}_{a \sim \pi_\theta, s' \sim P} [f(s') \mid s] \right| \le \gamma \mathbb{E}_{a \sim \pi_\theta, s' \sim P} [|f(s')| \mid s] \le \gamma \|f\|_\infty
$$

因此 $\|\gamma \mathcal{P}^{\pi_\theta}\|_\infty \le \gamma < 1$。这保证了 Neumann 级数收敛。

### 5.2 交换求和与积分的合法性

(18) 到 (19) 的步骤涉及交换 $\sum_{k=0}^{\infty}$ 与 $\int_{\mathcal{S}}$。对于有限状态空间或满足适当可积性条件的无限状态空间，这是合法的。在折扣因子 $\gamma < 1$ 的保证下，级数绝对收敛。

### 5.3 对数导数技巧的几何意义

$$
\nabla_\theta \log \pi_\theta(a|s) = \frac{\nabla_\theta \pi_\theta(a|s)}{\pi_\theta(a|s)}
$$

这个技巧将策略梯度从“绝对变化量”转化为“相对变化量”（即得分函数），消除了 $\pi_\theta(a|s)$ 在分母中可能为零的问题（在支撑集内 $\pi_\theta(a|s) > 0$）。

### 5.4 与有限差分梯度的关系

策略梯度定理可以理解为**对策略参数的扰动 $\delta\theta$ 如何影响期望回报的线性响应**：

$$
J(\theta + \delta\theta) - J(\theta) \approx \delta\theta^\top \mathbb{E}_{s,a} [\nabla_\theta \log \pi_\theta(a|s) Q^\pi(s,a)]
$$

这为策略梯度方法提供了直观解释：每个状态-动作对 $(s,a)$ 对目标函数的贡献正比于该动作被选中的概率的对数梯度乘以该动作的价值。

---

## 6. 策略梯度定理的变体

### 6.1 使用优势函数的等价形式

由于 $\mathbb{E}_{a \sim \pi_\theta} [\nabla_\theta \log \pi_\theta(a|s)] = 0$，可以将 $Q^\pi$ 替换为优势函数 $A^\pi$：

$$
\nabla_\theta J(\theta) = \mathbb{E}_{s \sim \rho^{\pi_\theta}, a \sim \pi_\theta} \left[ \nabla_\theta \log \pi_\theta(a|s) \cdot A^{\pi_\theta}(s,a) \right] \tag{24}
$$

**证明**：$\mathbb{E}_{a \sim \pi}[\nabla_\theta \log \pi(a|s)] \cdot V^\pi(s) = V^\pi(s) \cdot \nabla_\theta \int \pi(a|s) da = V^\pi(s) \cdot \nabla_\theta 1 = 0$。

> 使用优势函数可以显著降低梯度估计的方差，是 Actor-Critic 方法中常用的技巧。

### 6.2 添加基线的通用形式

更一般地，可以减去任意与动作无关的基线 $b(s)$：

$$
\nabla_\theta J(\theta) = \mathbb{E}_{s \sim \rho^{\pi_\theta}, a \sim \pi_\theta} \left[ \nabla_\theta \log \pi_\theta(a|s) \cdot \left( Q^{\pi_\theta}(s,a) - b(s) \right) \right] \tag{25}
$$

其中 $b(s)$ 可以是任意函数或随机变量，只要不依赖于动作 $a$。

### 6.3 确定性策略梯度 (DPG)

当策略退化为确定性映射 $\mu_\theta: \mathcal{S} \to \mathcal{A}$ 时，策略梯度定理变为：

$$
\nabla_\theta J(\mu_\theta) = \mathbb{E}_{s \sim \rho^{\mu_\theta}} \left[ \nabla_\theta \mu_\theta(s) \cdot \nabla_a Q^{\mu_\theta}(s,a) \big|_{a=\mu_\theta(s)} \right] \tag{26}
$$

这是 [[DDPG 算法]]的理论基础（Silver et al., 2014）。

---

## 7. 从定理到算法：梯度估计

### 7.1 蒙特卡洛估计（REINFORCE）

直接从定义 (23) 出发，使用采样来估计梯度：

$$
\nabla_\theta J(\theta) \approx \frac{1}{N} \sum_{i=1}^{N} \nabla_\theta \log \pi_\theta(a_i|s_i) \cdot G_i \tag{27}
$$

其中 $G_i$ 是从 $(s_i, a_i)$ 开始的实际累积回报（使用 $Q^\pi$ 的无偏样本估计）。

**REINFORCE 算法的梯度**：

$$
\nabla_\theta J(\theta) = \mathbb{E}_{s \sim \rho^\pi, a \sim \pi_\theta} \left[ \nabla_\theta \log \pi_\theta(a|s) \cdot G_t \right] \tag{28}
$$

### 7.2 Actor-Critic 估计

使用参数化的 Critic $Q_w(s,a)$ 来近似 $Q^\pi(s,a)$：

$$
\nabla_\theta J(\theta) \approx \mathbb{E}_{s,a} \left[ \nabla_\theta \log \pi_\theta(a|s) \cdot Q_w(s,a) \right] \tag{29}
$$

Critic 通过 TD 学习来更新参数 $w$。

---

## 8. 定理的应用条件与局限性

### 8.1 应用条件

| 条件 | 说明 |
|------|------|
| 策略可微 | $\pi_\theta(a|s)$ 对 $\theta$ 连续可微 |
| 适当正则性 | 积分与求导可交换（Sutton 等人在原始证明中假设了这一点） |
| $\gamma < 1$ | 保证折扣状态分布 $\rho^\pi$ 有定义且可归一化 |

### 8.2 注意事项

**状态分布的 $\theta$ 依赖性消失**：这是策略梯度定理最令人惊讶的结论——尽管状态分布 $\rho^{\pi_\theta}$ 本身依赖于 $\theta$，但最终的梯度表达式中，我们不需要计算 $\nabla_\theta \rho^{\pi_\theta}$。这正是“策略梯度定理”名称的由来，也是其强大之处。

**证明中的关键洞察**：

$$
\nabla_\theta J = \int \nabla_\theta \rho^\pi V^\pi + \int \rho^\pi \nabla_\theta V^\pi
$$

其中 $\int \nabla_\theta \rho^\pi V^\pi$ 项在适当边界条件下为 0（或可通过折扣重新解释消除）。这使得最终的梯度表达式只包含 $\nabla_\theta \log \pi$ 和 $Q^\pi$ 的期望。

---

## 9. 完整公式汇总

| 编号 | 公式 | 名称 |
|------|------|------|
| (23) | $\nabla_\theta J = \mathbb{E}_{s \sim \rho^\pi, a \sim \pi} [\nabla_\theta \log \pi(a|s) Q^\pi(s,a)]$ | **策略梯度定理（原始形式）** |
| (24) | $\nabla_\theta J = \mathbb{E}_{s \sim \rho^\pi, a \sim \pi} [\nabla_\theta \log \pi(a|s) A^\pi(s,a)]$ | 优势函数形式 |
| (25) | $\nabla_\theta J = \mathbb{E}_{s \sim \rho^\pi, a \sim \pi} [\nabla_\theta \log \pi(a|s) (Q^\pi(s,a) - b(s))]$ | 带基线形式 |
| (28) | $\nabla_\theta J = \mathbb{E}_{s \sim \rho^\pi, a \sim \pi} [\nabla_\theta \log \pi(a|s) G_t]$ | REINFORCE（蒙特卡洛） |
| (29) | $\nabla_\theta J \approx \mathbb{E}_{s,a} [\nabla_\theta \log \pi(a|s) Q_w(s,a)]$ | Actor-Critic（函数近似） |
| (26) | $\nabla_\theta J = \mathbb{E}_{s \sim \rho^\mu} [\nabla_\theta \mu(s) \cdot \nabla_a Q^\mu(s,a)]$ | 确定性策略梯度（DPG） |

