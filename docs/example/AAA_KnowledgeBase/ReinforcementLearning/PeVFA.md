# PeVFA（Policy-extended Value Function Approximator）完整解析

---

## 0. 论文来源

| 项目 | 内容 |
|------|------|
| **标题** | What About Inputing Policy in Value Function: Policy Representation and Policy-extended Value Function Approximator |
| **作者** | Hongyao Tang, Zhaopeng Meng, Jianye Hao, Chen Chen, Daniel Graves, Dong Li, Changmin Yu, Hangyu Mao, Wulong Liu, Yaodong Yang, Wenyuan Tao, Li Wang |
| **机构** | 天津大学、华为诺亚方舟实验室、伦敦大学学院 |
| **发表** | AAAI 2022 |
| **核心贡献** | 提出PeVFA，将**策略表示**作为额外输入引入价值函数，实现**策略间的值泛化**；并提出完整的策略表示学习框架 |


## 1. 一句话定位

**PeVFA (Policy-extended Value Function Approximator)** 是一种**扩展的价值函数近似器**。与传统的价值函数 $ V(s) $ 或 $ Q(s,a) $ 只输入状态（和动作）不同，PeVFA **额外接收一个显式的策略表示 $ \chi_\pi $** 作为输入：

$$
\mathbb{V}_\theta(s, \chi_\pi) \quad \text{或} \quad \mathbb{Q}_\theta(s, a, \chi_\pi)
$$

这使得 **一个 PeVFA 网络能够同时近似多个策略的价值**，并在策略之间实现**值泛化**。


## 2. 设计动机（Why PeVFA？）

### 2.1 传统价值函数的局限

在标准强化学习中，价值函数 $ V^\pi(s) $ 是针对**一个特定策略** $\pi$ 定义的：

$$
V^\pi(s) = \mathbb{E}_\pi \left[ \sum_{t=0}^{\infty} \gamma^t r_t \mid s_0 = s \right]
$$

在策略迭代过程中，每次策略更新后，旧策略的价值函数就被**丢弃**了，网络参数被新策略的值覆盖。这意味着：

- **历史知识被遗忘**：旧策略的"经验"无法被保留和复用
- **每次从头学习**：对新策略的值估计从随机初始化或旧参数开始，没有利用历史信息的"预热"

### 2.2 PeVFA 的核心洞察

如果我们能让价值函数**记住多个策略的值**，那么：

1. **值泛化**：从已学策略的值可以"推断"未学策略的值
2. **更高效的策略评估**：在 GPI（广义策略迭代）中，新策略的值估计可以从旧策略的值**泛化**得到，而不是从零开始

这正是 PeVFA 的设计目标：**通过显式的策略表示输入，让价值函数在策略空间中泛化**。


## 3. 数学定义

### 3.1 核心定义

给定一个策略表示函数 $ g: \Pi \to \mathcal{X} \subseteq \mathbb{R}^n $，将任意策略 $ \pi $ 映射到 $ n $ 维表示 $ \chi_\pi = g(\pi) $。

**策略扩展价值函数（PeVFA）**：

$$
\mathbb{V}_\theta(s, \chi_\pi) \approx V^\pi(s) \quad \forall s \in \mathcal{S}, \forall \pi \in \Pi
$$

类似地，策略扩展动作价值函数：

$$
\mathbb{Q}_\theta(s, a, \chi_\pi) \approx Q^\pi(s, a) \quad \forall s \in \mathcal{S}, a \in \mathcal{A}, \forall \pi \in \Pi
$$

### 3.2 逼近目标

PeVFA 的目标是**同时近似多个策略的值**。其逼近误差定义为：

$$
F_{\mu, \rho}(\theta, g, \Pi) = \sum_{\pi \in \Pi} \mu(\pi) \left\| \mathbb{V}_\theta(\chi_\pi) - V^\pi \right\|_{p, \rho}
$$

其中：
- $ \mu $ 是策略空间上的分布（决定我们关注哪些策略）
- $ \rho $ 是状态空间上的分布
- $ \| \cdot \|_{p, \rho} $ 是 $ \rho $-加权 $ L_p $ 范数

### 3.3 训练方式

PeVFA 通过标准的 TD 或 MC 方法训练：

$$
\mathcal{L}_{\mathbb{Q}}(\theta) = \mathbb{E}_{(s,a,r,s') \sim \mathcal{D}, \pi \sim \mu} \left[ \left( r + \gamma \mathbb{Q}_{\theta'}(s', a', \chi_\pi) - \mathbb{Q}_\theta(s, a, \chi_\pi) \right)^2 \right]
$$

关键点：同一个 $ \theta $ 被用于**所有策略**的值近似，通过不同的 $ \chi_\pi $ 输入来区分不同的策略。


## 4. 值泛化的两种形式

### 4.1 全局泛化（Global Generalization）

从**已知策略集**的值泛化到**未知策略集**：

- 训练集：$\Pi_0$（已收集数据的策略）
- 测试集：$\Pi_1$（未见过的策略）
- PeVFA 在 $\Pi_0$ 上训练后，能够对 $\Pi_1$ 中的新策略给出合理的值估计

### 4.2 局部泛化（Local Generalization）

沿着**策略改进路径**的值泛化（GPI 过程中的关键）：

- $\pi_t \to \pi_{t+1}$：策略在改进
- PeVFA 可以用 $\pi_t$ 的值来**泛化估计** $\pi_{t+1}$ 的值
- 这使得每一步的策略评估有一个**更好的起点**（更接近真实值）


## 5. 理论分析

### 5.1 关键定义

**定义 1（$\pi$-值近似）**：值近似过程 $\mathcal{P}_\pi: \Theta \to \Theta$ 是一个关于策略 $\pi$ 的 $\gamma$-压缩映射：

$$
f_{\hat{\theta}}(\pi) \leq \gamma f_\theta(\pi), \quad \gamma \in [0, 1)
$$

其中 $ f_\theta(\pi) = \| \mathbb{V}_\theta(\chi_\pi) - V^\pi \| $ 是近似损失。

**定义 2（L-连续性）**：如果 $ f_\theta $ 在策略 $\pi$ 处是 $L$-Lipschitz 连续的：

$$
|f_\theta(\pi) - f_\theta(\pi')| \leq L \cdot d(\pi, \pi')
$$

### 5.2 核心引理

**Lemma 1（两策略情形）**：对于 $\theta \xrightarrow{\mathcal{P}_{\pi_1}} \hat{\theta}$，若 $f_\theta$ 在 $\pi_1$ 处是 $\hat{L}$-连续的，则：

$$
f_{\hat{\theta}}(\pi_2) \leq \gamma f_\theta(\pi_2) + \hat{L} \cdot d(\pi_1, \pi_2)
$$

**解释**：只对 $\pi_1$ 做值近似后，$\pi_2$ 的近似损失被一个"广义压缩项 + 局部性余项"所上界约束。

**Corollary 1**：当 $ f_\theta(\pi_2) > \frac{\hat{L} \cdot d(\pi_1, \pi_2)}{1 - \gamma} $ 时，$\mathcal{P}_{\pi_1}$ 对 $\pi_2$ 也是 $\gamma_g$-压缩的。

**直观含义**：
- 对 $\pi_1$ 的压缩越紧（$\gamma$ 越小）
- 两个策略越接近（$d(\pi_1, \pi_2)$ 越小）
- 损失函数越平滑（$\hat{L}$ 越小）

则对 $\pi_2$ 的值泛化效果越好。

### 5.3 关键定理

**Theorem 1**：沿策略改进路径 $\theta_{-1} \xrightarrow{\mathcal{P}_{\pi_0}} \theta_0 \xrightarrow{\mathcal{P}_{\pi_1}} \theta_1 \xrightarrow{\mathcal{P}_{\pi_2}} \cdots $，若：

$$
f_{\theta_t}(\pi_t) + f_{\theta_t}(\pi_{t+1}) \leq \| V^{\pi_t} - V^{\pi_{t+1}} \|
$$

则：

$$
f_{\theta_t}(\pi_{t+1}) \leq \| \mathbb{V}_{\theta_t}(\pi_t) - V^{\pi_{t+1}} \|
$$

**解读**：PeVFA 对 $\pi_{t+1}$ 的泛化值估计，比传统 VFA 的 $\mathbb{V}_{\theta_t}(\pi_t)$ 更接近 $\pi_{t+1}$ 的真实值。这意味着：
- GPI 中每一步策略评估的**起点更好**
- 可能用**更少的样本**达到相同的近似精度


## 6. 策略表示学习

### 6.1 两种策略表示

| 表示类型 | 数据来源 | 方法 |
|----------|----------|------|
| **OPR（Origin Policy Representation）** | 策略网络的**权重和偏置** | 对网络参数进行编码 |
| **SPR（Surface Policy Representation）** | 策略的**状态-动作对** | 从交互轨迹中提取 |

### 6.2 三种训练方式

| 方式 | 损失函数 | 说明 |
|------|----------|------|
| **E2E（End-to-End）** | PeVFA 的值近似损失 | 策略表示由价值监督信号直接训练 |
| **CL（Contrastive Learning）** | InfoNCE 对比损失 | 相似策略靠近，不同策略远离 |
| **AUX（Auxiliary Policy Recovery）** | 行为克隆损失 | 从表示中恢复动作分布 |

### 6.3 实验效果

| 方法 | 平均归一化回报 | 相对 PPO 提升 |
|------|---------------|--------------|
| PPO（基线） | 1.00 | — |
| PPO-PeVFA + OPR (E2E) | 1.20 | +20% |
| PPO-PeVFA + SPR (E2E) | 1.20 | +20% |
| PPO-PeVFA + OPR (CL) | 1.35 | +35% |
| PPO-PeVFA + SPR (CL) | 1.35 | +35% |
| PPO-PeVFA + OPR (AUX) | 1.40 | +40% |
| PPO-PeVFA + SPR (AUX) | 1.40 | +40% |


## 7. PeVFA 与 ERL-Re² 的关系

ERL-Re² 是 PeVFA 的**直接下游应用**：

| 维度 | PeVFA | ERL-Re² 中的应用 |
|------|-------|-----------------|
| **核心功能** | 值泛化到多个策略 | 用 PeVFA 估计 EA 种群中每个个体的 fitness |
| **策略表示** | OPR 或 SPR | 使用**线性策略表示 W**（政策向量） |
| **训练方式** | 离线/在线均可 | **离线训练**：用种群经验训练 PeVFA |
| **应用场景** | 提高策略评估效率 | 构建**代理适应度**，减少 EA 的样本开销 |
| **关键创新** | 值泛化理论分析 | 首次**离线训练 PeVFA**（原论文只做了在线/on-policy） |

在 ERL-Re² 中：

$$
\hat{f}(W_i) = \sum_{t=0}^{H-1} \gamma^t r_t + \gamma^H \mathbb{Q}_\theta(s_H, \pi_i(s_H), W_i)
$$

这里的 $\mathbb{Q}_\theta$ 就是 PeVFA——它接收策略表示 $W_i$，为**任意 EA 个体**估计剩余 $H$ 步后的价值，从而实现**无偏的代理适应度估计**。