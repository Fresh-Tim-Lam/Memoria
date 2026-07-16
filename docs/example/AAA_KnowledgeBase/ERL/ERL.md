# Evolution-Guided Policy Gradient in Reinforcement Learning (ERL) 算法报告

## 0. 论文来源

| 项目 | 内容 |
|------|------|
| **标题** | Evolution-Guided Policy Gradient in Reinforcement Learning |
| **作者** | Shauharda Khadka, Kagan Tumer |
| **机构** | Collaborative Robotics and Intelligent Systems Institute, Oregon State University |
| **会议** | NeurIPS 2018（arXiv 首页标 "Preprint. Work in progress."） |
| **arXiv** | arXiv:1805.07917v2，2018-10-27 |
| **代码** | https://github.com/ShawK91/erl_paper_nips18 |

---

## 1. 算法概述

### 1.1 一句话定位

**ERL** 是将 **进化算法 (EA)** 的种群级 episode-级 fitness 优化与 **深度确定性策略梯度 (DDPG)** 的样本级梯度优化耦合在**同一经验池**之上的混合算法。

### 1.2 设计动机（Why）

作者列出 RL 与 EA 各自的硬约束：

**RL 痛点（特别是 off-policy DDPG）**

1. **时间信用分配**：稀疏奖励 / 长 horizon 下，TD bootstrapping 难以把回报传到早期动作；多步回报在 off-policy 下需重要性采样、Retrace、V-trace 等附加机制。
2. **探索不足**：高维状态/动作空间中，朴素 ε-greedy 或动作扰动不足以覆盖好策略。
3. **超参敏感、收敛脆弱**：replay buffer + bootstrapping + 深度非线性近似器三者组合下，DDPG 对学习率、批大小、噪声尺度等极敏感。

**EA 痛点**

- 不利用梯度信息，**样本复杂度高**；难以优化数百万级参数的深度网络。

**混合带来的收益**

1. **EA → RL**：种群产生**多样轨迹**全部写入 replay → DDPG 在更广分布上做梯度更新（样本效率↑）。
2. **RL → EA**：周期性地把 `rl_actor` **拷入种群**最差个体 → 把梯度信息注入进化搜索（避免 EA 长期盲搜）。
3. **episode-级 fitness** 对稀疏 / 欺骗性奖励更鲁棒；种群冗余降低单一策略崩溃的风险。

### 1.3 核心实验结论（论文主张）

- 在 **6 个 MuJoCo 连续控制任务**上 ERL **全部优于纯 DDPG**（Ant 任务上 DDPG 几乎学不动）。
- 相对 **PPO**，6 个中 4 个显著更优；**Hopper、Walker2d** 上 PPO 前期更快，但 ERL 最终追上并超过（这两个任务存在"原地不倒"的强局部最优，纯 EA 易收敛于此，ERL 靠 RL 部分跳出）。
- **去掉选择算子**（no-selection ablation）性能下降约 ~80%，验证 EA 选择压不可少。
- 运行时间相对 DDPG **仅多约 3%**（变异为额外开销，未做并行）。

---

## 2. 数学基础

### 2.1 强化学习背景

马尔可夫决策过程 $(\mathcal{S},\mathcal{A},P,R,\gamma)$：

- 状态空间 $\mathcal{S}$，连续动作空间 $\mathcal{A}$
- 转移 $P(s'|s,a)$，奖励 $R(s,a)$，折扣 $\gamma\in[0,1)$

目标是最大化期望回报：

$$J(\pi_\theta) = \mathbb{E}_{\pi_\theta}\!\left[\sum_{t=0}^{\infty}\gamma^t r_t\right],\qquad R_t = \sum_{n=0}^{\infty}\gamma^n r_{t+n}$$

### 2.2 DDPG（论文 §2.1）

DDPG 维护四个网络：

| 网络 | 符号 | 角色 |
|------|------|------|
| Actor | $\mu_{\theta_\pi}(s)$ | 确定性策略，直接输出动作 |
| Critic | $Q_{\theta_Q}(s,a)$ | 评估 $(s,a)$ 价值 |
| Target Actor | $\mu_{\theta_{\pi'}}$ | 软更新副本 |
| Target Critic | $Q_{\theta_{Q'}}$ | 软更新副本 |

**TD 目标**（one-step bootstrap）：

$$y_i = r_i + \gamma\,Q_{\theta_{Q'}}\!\bigl(s_{i+1},\,\mu_{\theta_{\pi'}}(s_{i+1})\bigr)$$

**Critic 损失**（MSBE，对 batch $T$ 个 transition 求平均）：

$$L(\theta_Q) = \frac{1}{T}\sum_{i=1}^{T}\bigl(y_i - Q_{\theta_Q}(s_i,a_i)\bigr)^2$$

**Actor 梯度**（确定性策略梯度定理，Silver et al. 2014）：

$$\nabla_{\theta_\pi} J \;\approx\; \frac{1}{T}\sum_{i=1}^{T} \nabla_a Q_{\theta_Q}(s,a)\Big|_{\substack{s=s_i\\a=\mu_{\theta_\pi}(s_i)}}\, \nabla_{\theta_\pi}\mu_{\theta_\pi}(s)\Big|_{s=s_i}$$

**推导关键步**：由链式法则，$\nabla_{\theta_\pi}Q(s,\mu_{\theta_\pi}(s)) = \nabla_a Q(s,a)|_{a=\mu(s)}\,\nabla_{\theta_\pi}\mu_{\theta_\pi}(s)$；对该项在 buffer 分布下求期望即得到上式。

**目标网络软更新**（$\tau\ll 1$）：

$$\theta_{\pi'} \leftarrow \tau\theta_\pi + (1-\tau)\theta_{\pi'},\quad \theta_{Q'} \leftarrow \tau\theta_Q + (1-\tau)\theta_{Q'}$$

**行为策略探索**：动作上叠加 **Ornstein-Uhlenbeck (OU) 噪声**（时间相关的色噪声，比独立高斯在惯性系统上探索更高效）：

$$dx_t = \theta(\mu-x_t)\,dt + \sigma\,dW_t,\quad a_t = \mu_{\theta_\pi}(s_t) + x_t$$

#### 2.2.1 梯度计算详解与代码映射

DDPG 的两路梯度更新（Critic 和 Actor）在代码中分别对应两个 optimizer，下面拆解每个梯度从数学公式到 PyTorch 自动微分的完整链路。

**Critic 梯度（TD 误差反向传播）**

$$\nabla_{\theta_Q} L = \nabla_{\theta_Q} \frac{1}{T} \sum_{i=1}^{T} \bigl(y_i - Q_{\theta_Q}(s_i, a_i)\bigr)^2$$

链式展开（以单个样本为例，省略求和与 $1/T$）：

$$\frac{\partial L}{\partial \theta_Q} = -2\,(y - Q(s,a)) \cdot \frac{\partial Q(s,a)}{\partial \theta_Q}$$

其中 $\partial Q(s,a)/\partial \theta_Q$ 进一步沿 Critic 网络逐层分解。状态和动作子网络分别求导：

$$\frac{\partial Q}{\partial W_s} = \frac{\partial Q}{\partial W_3} \cdot \frac{\partial \text{ELU}}{\partial h_2} \cdot \frac{\partial h_2}{\partial h_1} \cdot \frac{\partial h_1}{\partial f_s} \cdot \frac{\partial f_s}{\partial W_s}$$

$$\frac{\partial Q}{\partial W_a} = \frac{\partial Q}{\partial W_3} \cdot \frac{\partial \text{ELU}}{\partial h_2} \cdot \frac{\partial h_2}{\partial h_1} \cdot \frac{\partial h_1}{\partial f_a} \cdot \frac{\partial f_a}{\partial W_a}$$

其中 $h_1 = [f_s; f_a]$，$f_s = W_s s + b_s$，$f_a = W_a a + b_a$，$h_2 = \text{LN}(W_2 h_1 + b_2)$，$Q = W_3 h_2 + b_3$。代码对应：

| 数学项 | 代码行 |
|--------|--------|
| $L = \text{MSE}(Q, y)$ | `loss = nn.MSELoss()(current_q, target_q)` |
| $\partial L/\partial \theta_Q$ | `loss.backward()`（自动链式求导） |
| $\theta_Q \leftarrow \theta_Q - \alpha_Q \cdot \partial L/\partial \theta_Q$ | `self.critic_optimizer.step()` |

**Actor 梯度（确定性策略梯度）**

$$\nabla_{\theta_\pi} J \approx \frac{1}{T}\sum_{i=1}^{T} \nabla_a Q_{\theta_Q}(s,a)\Big|_{\substack{s=s_i\\a=\mu_{\theta_\pi}(s_i)}}\, \nabla_{\theta_\pi}\mu_{\theta_\pi}(s)\Big|_{s=s_i}$$

链式展开（从 loss 定义 $\mathcal{L} = -\frac{1}{T}\sum Q(s,\mu(s))$ 出发）：

$$\frac{\partial \mathcal{L}}{\partial \theta_\pi} = -\frac{1}{T}\sum_{i=1}^{T} \underbrace{\frac{\partial Q(s_i,a)}{\partial a}\Big|_{a=\mu(s_i)}}_{\text{通过 Critic 回传}} \cdot \underbrace{\frac{\partial \mu(s_i)}{\partial \theta_\pi}}_{\text{Actor 内部链式法则}}$$

其中 Actor 内部 $\partial \mu/\partial \theta_\pi$ 沿网络展开（令 $x_0 = s$）：

$$\frac{\partial \mu}{\partial \theta_\pi} = \frac{\partial}{\partial \theta_\pi}\bigl[\text{max\_action}\cdot\tanh(W_3 x_2 + b_3)\bigr] \cdot \frac{\partial x_2}{\partial \theta_\pi}$$

$$\frac{\partial x_2}{\partial \theta_\pi} = \frac{\partial}{\partial \theta_\pi}\bigl[\tanh(\text{LN}(W_2 x_1 + b_2))\bigr] \cdot \frac{\partial x_1}{\partial \theta_\pi}$$

$$\frac{\partial x_1}{\partial \theta_\pi} = \frac{\partial}{\partial \theta_\pi}\bigl[\tanh(\text{LN}(W_1 x_0 + b_1))\bigr]$$

三层 tanh 各贡献一个 $\text{sech}^2$ 因子（tanh 的导数：$\frac{d}{dx}\tanh(x) = 1 - \tanh^2(x) = \text{sech}^2(x)$），LayerNorm 贡献归一化统计量的偏导，所有因子通过链式连乘。代码对应：

| 数学项 | 代码行 |
|--------|--------|
| $\mathcal{L} = -\frac{1}{T}\sum Q(s,\mu(s))$ | `actor_loss = -self.critic(states, self.actor(states)).mean()` |
| $\partial \mathcal{L}/\partial \theta_\pi$ | `actor_loss.backward()` |
| Critic 端的 $\partial Q/\partial a$ 传入 | PyTorch autograd 自动沿 $Q \to a \to \mu$ 追溯 |
| $\theta_\pi \leftarrow \theta_\pi - \alpha_\pi \cdot \partial \mathcal{L}/\partial \theta_\pi$ | `self.actor_optimizer.step()` |

**梯度隔离原理**：Actor 和 Critic 各用独立 optimizer，$Q$ 值本应对 Actor 求导指导更新，但不希望这个梯度信号反传到 Critic 自己的参数。PyTorch 的 optimizer 机制天然保证这一点——`self.critic(states, actions)` 的计算图虽相连，但 `self.critic_optimizer.step()` 只更新 Critic 参数，`self.actor_optimizer.step()` 只更新 Actor 参数：

```
                        ┌──────────────────┐
states ──► Actor ──► a ──► Critic ──► Q ──► actor_loss = -Q.mean()
               │              │                    │
               │              │               actor_loss.backward()
               ▼              ▼                       │
        actor_optimizer  critic_optimizer              │
               │              │                 梯度流向：
        只更新 Actor     只更新 Critic         Actor ◄── Critic ◄── loss
        的参数           的参数               （Critic 参数有梯度，但 optimizer 不动它们）
```

**训练脚本中的实际更新量**：以 HalfCheetah 为例，每代 $50$ 次梯度更新，batch size $128$，$10^6$ 级 buffer 中均匀采样。每次 $L_Q$ 回传更新 Critic 的 $127{,}001$ 个参数，$J_\pi$ 回传更新 Actor 的 $20{,}102$ 个参数——互不重叠，互不干扰。

### 2.3 进化算法组件

#### 2.3.1 适应度（Algorithm 2 / Evaluate）

对个体 $\pi$，做 $\xi$ 次完整 episode（不加变异，不加 OU），fitness 取 **未折扣**累积奖励的平均：

$$\text{fitness}(\pi) = \frac{1}{\xi}\sum_{j=1}^{\xi}\sum_{t=0}^{T_j} r_t^{(j)}$$

> 注：论文 Algorithm 2 内层用 `fitness ← fitness + r_t`（不乘 $\gamma^t$），与 DDPG 的折扣回报不同——EA 评估的是真实 episode return，不带 RL 折扣。

#### 2.3.2 锦标赛选择（Tournament Selection）

从非精英中**有放回**抽取若干个体，取 fitness 最高者作为父代。论文未写死锦标赛规模 $k_{\text{tour}}$（实现一般取 3）：

$$\text{parent} = \arg\max_{i\in\text{tournament}}\text{fitness}_i$$

#### 2.3.3 交叉（Probabilistic Crossover）

从 **精英集合** 与 **选择得到的集合 $S$** 各取一个 $\pi$ 做交叉（论文未在 Algorithm 1 展开具体算子；实现上常用 **k-point** 或 **均匀交叉**）。一种典型形式：

$$\theta_{\text{child}}^{(j)} = \begin{cases} \theta_1^{(j)} & m^{(j)}=0\\ \theta_2^{(j)} & m^{(j)}=1 \end{cases},\quad m^{(j)}\sim\text{Bernoulli}(0.5)$$

#### 2.3.4 变异（Algorithm 3 / Mutate）

对每个权重矩阵 $M\in\theta_\pi$，随机选取 $\lceil\text{mutfrac}\cdot|M|\rceil$ 个元素位置 $(i,j)$，每个位置按以下三选一模式扰动：

$$M_{ij} \leftarrow \begin{cases} M_{ij}\cdot\mathcal{N}(0,\,100\cdot\text{mutstrength}) & r()<\text{supermutprob}\quad(\text{super mutation})\\[4pt] \mathcal{N}(0,\,1) & \text{else if } r()<\text{resetprob}\quad(\text{reset})\\[4pt] M_{ij}\cdot\mathcal{N}(0,\,\text{mutstrength}) & \text{otherwise}\quad(\text{small mutation}) \end{cases}$$

默认 $\text{mutfrac}=0.1,\ \text{mutstrength}=0.1,\ \text{supermutprob}=0.05,\ \text{resetprob}=0.05$。

#### 2.3.5 精英保留

按 fitness 降序排序，前 $e=\lfloor\psi k\rfloor$ 个体作为精英 **直接进入下一代**且 **不参与变异**：

$$\text{Elites} = \{\pi_{(1)},\pi_{(2)},\ldots,\pi_{(e)}\}$$

### 2.4 混合机制（RL ↔ EA）

- **EA → RL（隐式 / 数据通路）**：所有种群个体 + `rl_actor` 与环境交互产生的 $(s_t,a_t,r_t,s_{t+1})$ 全部写入**同一个 cyclic replay buffer** $\mathcal{D}$（容量 $10^6$，FIFO）。`rl_actor`/`rl_critic` 从中均匀采样训练。
- **RL → EA（显式 / 参数注入）**：每 $\omega$ 代，把 `rl_actor` 的权重**复制到当前种群 fitness 最差个体**上：

$$\text{generation}\bmod\omega=0\;\Rightarrow\;\theta_{\pi_{\text{worst}}}\leftarrow\theta_{\pi_{rl}}$$

若 `rl_actor` 实际较差，下一代选择自然把它淘汰；若较好，其基因通过交叉扩散到整个种群。

---

## 3. 网络架构

ERL 同时维护两组神经网络：

1. **RL Actor / Critic**（及对应的 target 网络）—— 用于梯度更新的 DDPG 主网络
2. **种群 Actors** —— EA 维护的 $k$ 个 $\pi$ 个体，架构与 RL Actor **完全相同**

两组网络共享同一架构定义，区别仅在于参数来源（梯度更新 vs 遗传操作）。

### 3.1 Actor 网络（确定性策略 $\mu_\theta(s)$）

#### 3.1.1 网络结构

```
输入: s ∈ ℝᵈˢ                    shape: [batch, d_s]
        │
        ▼
┌───────────────────────────────┐
│  Linear(d_s, 128)             │  W₁: [128, d_s], b₁: [128]
│  LayerNorm(128)               │  γ₁: [128], β₁: [128]
│  tanh                         │
└───────────────┬───────────────┘
        │  h₁ ∈ ℝ¹²⁸              shape: [batch, 128]
        ▼
┌───────────────────────────────┐
│  Linear(128, 128)             │  W₂: [128, 128], b₂: [128]
│  LayerNorm(128)               │  γ₂: [128], β₂: [128]
│  tanh                         │
└───────────────┬───────────────┘
        │  h₂ ∈ ℝ¹²⁸              shape: [batch, 128]
        ▼
┌───────────────────────────────┐
│  Linear(128, dₐ)              │  W₃: [dₐ, 128], b₃: [dₐ]
│  tanh (× max_action)          │  输出映射至 [-max_action, +max_action]
└───────────────┬───────────────┘
        │
        ▼
输出: a ∈ ℝᵈₐ                    shape: [batch, dₐ]
                 a = max_action · tanh(W₃ h₂ + b₃)
```

完整的数学表达式（逐层计算，$x_0 = s$）：

$$ \begin{aligned} x_1 &= \tanh\!\bigl(\text{LN}(W_1 x_0 + b_1)\bigr) \\ x_2 &= \tanh\!\bigl(\text{LN}(W_2 x_1 + b_2)\bigr) \\ \mu_\theta(s) &= \text{max_action} \cdot \tanh(W_3 x_2 + b_3) \end{aligned} $$

其中 LayerNorm 定义为：

$$\text{LN}(x) = \gamma \odot \frac{x - \mu_x}{\sqrt{\sigma_x^2 + \varepsilon}} + \beta,\quad \mu_x = \frac{1}{128}\sum_{i=1}^{128} x_i,\quad \sigma_x^2 = \frac{1}{128}\sum_{i=1}^{128} (x_i - \mu_x)^2$$

#### 3.1.2 参数量计算（以 HalfCheetah: $d_s=17, d_a=6$ 为例）

| 层 | 权重形状 | 偏置形状 | 参数量 |
|----|----------|----------|--------|
| Linear₁ | [128, 17] | [128] | $128 \times 17 + 128 = 2{,}304$ |
| LayerNorm₁ | [128] | [128] | $128 + 128 = 256$ |
| Linear₂ | [128, 128] | [128] | $128 \times 128 + 128 = 16{,}512$ |
| LayerNorm₂ | [128] | [128] | $128 + 128 = 256$ |
| Linear₃ | [6, 128] | [6] | $6 \times 128 + 6 = 774$ |
| **总计** | | | **20,102** |

> 参数量不依赖 $d_s, d_a$ 之外的环境维度。对于 Ant ($d_s=105, d_a=8$)：Linear₁ → $128 \times 105 + 128 = 13{,}568$，Linear₃ → $8 \times 128 + 8 = 1{,}032$，总计约 $15{,}384$（总参数量随状态维增加而增长）。

---

### 3.2 Critic 网络（Q 值函数 $Q_\phi(s,a)$）

#### 3.2.1 网络结构

Critic 与 Actor 的关键区别：**状态和动作通过独立的子网络处理后再拼接**，而不是直接拼接原始输入。

```
输入: s ∈ ℝᵈˢ, a ∈ ℝᵈᵃ          shape: [batch, d_s], [batch, d_a]
        │              │
        ▼              ▼
┌──────────────┐ ┌──────────────┐
│ Linear(d_s,200)│ │ Linear(d_a,200)│  W_s: [200, d_s], W_a: [200, d_a]
└──────┬───────┘ └──────┬───────┘
       │ f_s ∈ ℝ²⁰⁰     │ f_a ∈ ℝ²⁰⁰     各自独立映射至 200 维
       └───────┬────────┘
               ▼
         ┌───────────┐
         │ 拼接 concat  │  x_cat = [f_s; f_a] ∈ ℝ⁴⁰⁰
         └─────┬─────┘
               ▼
┌───────────────────────────────┐
│  LayerNorm(400)               │  γ₁: [400], β₁: [400]
│  ELU                          │
└───────────────┬───────────────┘
        │  h₁ ∈ ℝ⁴⁰⁰
        ▼
┌───────────────────────────────┐
│  Linear(400, 300)             │  W₂: [300, 400], b₂: [300]
│  LayerNorm(300)               │  γ₂: [300], β₂: [300]
│  ELU                          │
└───────────────┬───────────────┘
        │  h₂ ∈ ℝ³⁰⁰
        ▼
┌───────────────────────────────┐
│  Linear(300, 1)               │  W₃: [1, 300], b₃: [1]
└───────────────┬───────────────┘
        │
        ▼
输出: Q(s,a) ∈ ℝ                  shape: [batch, 1]
```

完整的数学表达式：

$$ \begin{aligned} f_s &= W_s s + b_s \quad (\text{状态子网络}) \\ f_a &= W_a a + b_a \quad (\text{动作子网络}) \\ x_1 &= \text{ELU}\bigl(\text{LN}_1([f_s; f_a])\bigr) \\ x_2 &= \text{ELU}\bigl(\text{LN}_2(W_2 x_1 + b_2)\bigr) \\ Q_\phi(s,a) &= W_3 x_2 + b_3 \end{aligned} $$

> **设计原理**：状态和动作分两路映射的原因是状态维度和动作维度在物理意义上分属不同空间（状态描述系统配置，动作描述控制输入），独立编码后再拼接可以让网络更灵活地学习两者的交互关系。

#### 3.2.2 参数量计算（以 HalfCheetah: $d_s=17, d_a=6$ 为例）

| 层 | 权重形状 | 偏置形状 | 参数量 |
|----|----------|----------|--------|
| State Sub (Linear) | [200, 17] | [200] | $200 \times 17 + 200 = 3{,}600$ |
| Action Sub (Linear) | [200, 6] | [200] | $200 \times 6 + 200 = 1{,}400$ |
| LayerNorm₁ | [400] | [400] | $400 + 400 = 800$ |
| Linear₂ | [300, 400] | [300] | $300 \times 400 + 300 = 120{,}300$ |
| LayerNorm₂ | [300] | [300] | $300 + 300 = 600$ |
| Linear₃ (输出) | [1, 300] | [1] | $1 \times 300 + 1 = 301$ |
| **总计** | | | **127,001** |

> Critic 参数量远大于 Actor（约 6.3 倍），因为拼接层 $400 \to 300$ 是主要的参数量瓶颈。

---

### 3.3 权重初始化策略

所有层统一使用 **Xavier Uniform**（Glorot 初始化），输出层额外缩小：

| 层类型 | 初始化方法 | 公式 |
|--------|------------|------|
| 隐藏层权重 | `xavier_uniform_` | $W \sim U\!\bigl(-\sqrt{6/(\text{fan\_in} + \text{fan\_out})},\ +\sqrt{6/(\text{fan\_in} + \text{fan\_out})}\bigr)$ |
| 隐藏层偏置 | `zeros_` | $b = 0$ |
| 输出层权重 | `uniform_(-3e-3, 3e-3)` | $W_{\text{out}} \sim U(-3\times 10^{-3},\ 3\times 10^{-3})$ |
| 输出层偏置 | `zeros_` | $b_{\text{out}} = 0$ |
| LayerNorm $\gamma$ | 默认（全 1） | $\gamma = 1$ |
| LayerNorm $\beta$ | 默认（全 0） | $\beta = 0$ |

> 输出层用小范围初始化（$3\times 10^{-3}$）是 DDPG 原文的技巧，确保训练初期 Actor 输出接近 0 的动作（避免初期大动作导致 episode 立刻失败），Critic 输出接近 0 的 Q 值。

---

### 3.4 激活函数对比

| 网络 | 隐藏层激活 | 输出层激活 | 选择理由 |
|------|------------|------------|----------|
| **Actor** | tanh | tanh | tanh 输出范围 $(-1, 1)$，与动作空间匹配；梯度平滑，适合策略网络 |
| **Critic** | ELU | 线性（无激活） | ELU 在负半轴有软饱和，比 ReLU 更稳定；线性输出层不限制 Q 值范围 |

---

### 3.5 经验回放缓冲区

$$\mathcal{D} = \{(s_t,a_t,r_t,s_{t+1}, done_t)\}$$

- 容量 $10^6$（cyclic / FIFO）
- 采样批量 $T=128$
- 所有个体（包括 `rl_actor`）共享同一 buffer
- 存储格式：每个 transition 是一个 5 元组 $(s_t, a_t, r_t, s_{t+1}, done_t)$，其中 $done_t$ 标志 episode 是否终止。TD target 计算中使用 $(1-done_t)$ 截断 bootstrap，避免 terminated 状态后的 Q 值过高估计（见 Algorithm 1 line 20）

---

## 4. 算法伪代码

### 4.1 Algorithm 1：主循环（按论文逐行还原）

```
Algorithm 1 Evolutionary Reinforcement Learning

 1: Initialize actor πrl and critic Qrl with weights θπ and θQ, respectively
 2: Initialize target actor π′rl and critic Q′rl with weights θπ′ and θQ′, respectively
 3: Initialize a population of k actors popπ and an empty cyclic replay buffer R
 4: Define a Ornstein-Uhlenbeck noise generator O and a random number generator r() ∈ [0, 1)
 5: for generation = 1, ∞ do
 6:     for actor π ∈ popπ do
 7:         fitness, R = Evaluate(π, R, noise=None, ξ)
 8:     end for
 9:     Rank the population based on fitness scores
10:     Select the first e actors π ∈ popπ as elites where e = int(ψ*k)
11:     Select (k−e) actors π from popπ, to form Set S using tournament selection with replacement
12:     while |S| < (k−e) do
13:         Use crossover between a randomly sampled π ∈ e and π ∈ S and append to S
14:     end while
15:     for Actor π ∈ Set S do
16:         if r() < mutprob then
17:             Mutate(θπ)
18:         end if
19:     end for
20:     _, R = Evaluate(πrl, R, noise = O, ξ = 1)
21:     Sample a random minibatch of T transitions (si, ai, ri, si+1) from R
22:     Compute yi = ri + γ Q′rl(si+1, π′rl(si+1|θπ′)|θQ′)
23:     Update Qrl by minimizing the loss: L = 1/T Σ_i (yi − Qrl(si, ai|θQ))^2
24:     Update πrl using the sampled policy gradient
            ∇θπ J ∼ 1/T Σ ∇a Qrl(s, a|θQ)|_{s=si, a=ai} ∇θπ π(s|θπ)|_{s=si}
25:     Soft update target networks: θπ′ ⇐ τθπ + (1−τ)θπ′ and θQ′ ⇐ τθQ + (1−τ)θQ′
26:     if generation mod ω = 0 then
27:         Copy the RL actor into the population: for weakest π ∈ popπ : θπ ⇐ θπrl
28:     end if
29: end for
```

### 4.2 Algorithm 2：Evaluate（适应度评估子过程）

```
Algorithm 2 Function Evaluate

 1: procedure EVALUATE(π, R, noise, ξ)
 2:     fitness = 0
 3:     for i = 1:ξ do
 4:         Reset environment and get initial state s0
 5:         while env is not done do
 6:             Select action at = π(st|θπ) + noiset
 7:             Execute action at and observe reward rt and new state st+1
 8:             Append transition (st, at, rt, st+1) to R
 9:             fitness ← fitness + rt and s = st+1
10:         end while
11:     end for
12:     Return fitness/ξ, R
13: end procedure
```

### 4.3 Algorithm 3：Mutate（变异子过程）

```
Algorithm 3 Function Mutate

 1: procedure MUTATE(θπ)
 2:     for Weight Matrix M ∈ θπ do
 3:         for iteration = 1, mutfrac ∗ |M| do
 4:             Randomly sample indices i and j from M's first and second axis, respectively
 5:             if r() < supermutprob then
 6:                 M[i, j] = M[i, j] * N(0, 100 ∗ mutstrength)
 7:             else if r() < resetprob then
 8:                 M[i, j] = N(0, 1)
 9:             else
10:                 M[i, j] = M[i, j] * N(0, mutstrength)
11:             end if
12:         end for
13:     end for
14: end procedure
```

---

## 5. 超参数

### 5.1 通用超参（论文 Appendix A，全任务相同）

| 参数 | 符号 | 取值 | 说明 |
|------|------|------|------|
| 种群大小 | $k$ | 10 | EA 个体数 |
| 软更新系数 | $\tau$ | $10^{-3}$ | Target 网络平滑 |
| 折扣因子 | $\gamma$ | 0.99 | RL 折扣 |
| Replay 容量 | $|\mathcal{D}|$ | $10^6$ | Cyclic FIFO |
| Batch | $T$ | 128 | DDPG 采样批量 |
| Actor 学习率 | $\alpha_\theta$ | $5\times10^{-5}$ | Adam |
| Critic 学习率 | $\alpha_\phi$ | $5\times10^{-4}$ | Adam |
| 梯度裁剪 | — | 10 | 全局梯度范数上限 |
| 变异概率 | $\text{mutprob}$ | 0.9 | 非精英整体变异触发 |
| 变异元素比例 | $\text{mutfrac}$ | 0.1 | 单矩阵中扰动比例 |
| 变异强度 | $\text{mutstrength}$ | 0.1 | 普通乘性扰动 $\sigma$ |
| Super-mut 概率 | $\text{supermutprob}$ | 0.05 | 大幅扰动分支 |
| Reset 概率 | $\text{resetprob}$ | 0.05 | 重置到 $\mathcal{N}(0,1)$ 分支 |

### 5.2 逐环境超参（论文 Table 2）

| 环境 | 精英比例 $\psi$ | Trials $\xi$ | 同步周期 $\omega$ | 调参直觉 |
|------|----------------|--------------|------------------|----------|
| HalfCheetah-v2 | 0.1 | 1 | 10 | 低随机性，单次评估足够 |
| Swimmer-v2 | 0.1 | 1 | 10 | 低随机性，单次评估足够 |
| Reacher-v2 | 0.2 | 5 | 10 | 中等随机性，多次评估降方差 |
| Ant-v2 | 0.3 | 1 | 1 | 高接触点 → 高 fitness 方差 → 高精英比例；同步频繁 |
| Hopper-v2 | 0.3 | 5 | 1 | 高接触点 → 高精英比例；多次评估 |
| Walker2d-v2 | 0.2 | 3 | 10 | 中等接触点，三次评估降方差 |

**调参直觉**（论文给出的解释）：

- $\psi$ 越大 → 精英保留越多 → 应对 **fitness 方差大**（动力学随机、接触多）的环境
- $\xi$ 越大 → 每个体多次评估取平均，**降低 fitness 估计方差**；注意所有 trials 步数都算入总 environment steps
- $\omega$ 越大 → 种群更长时间独立进化，更广探索；$\omega$ 越小 → 梯度信息更频繁注入，搜索更局部

---

## 6. 实验设置

### 6.1 环境与协议

- **6 个 MuJoCo 连续控制任务**：HalfCheetah, Swimmer, Reacher, Ant, Hopper, Walker2d（均为 OpenAI Gym v2）
- **Episode 长度**：HalfCheetah 1000 步（其它使用 Gym 默认 horizon）
- **横轴**：environment steps（种群中所有个体的步数累加）
- **评估**：每代取 fitness 最高的 champion，做 5 个独立 rollout 取均值；与 baselines 比较时同样去掉探索噪声
- **种子**：5 个随机种子