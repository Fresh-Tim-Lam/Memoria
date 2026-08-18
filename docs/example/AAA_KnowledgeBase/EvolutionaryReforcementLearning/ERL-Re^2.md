# ERL-Re² 算法报告

## 0. 论文来源

| 项目 | 内容 |
|------|------|
| **标题** | ERL-Re²: Efficient Evolutionary Reinforcement Learning with Shared State Representation and Individual Policy Representation |
| **作者** | Jianye Hao, Pengyi Li, Hongyao Tang, Yan Zheng, Xian Fu, Zhaopeng Meng |
| **机构** | College of Intelligence and Computing, Tianjin University |
| **会议** | **ICLR 2023** |
| **arXiv** | arXiv:2210.17375v2，2023-06-30 |
| **代码** | <https://github.com/yeshenpy/ERL-Re2> |

> **命名**：论文里写作 *ERL-Re2*。 "Re²" 在 §3 标题中被解读为 **Two-scale State Representation and Policy Representation**（双尺度：共享状态表示 + 个体策略表示），亦可读作"representational reuse"——所有 EA/RL 个体复用同一非线性状态编码器 $Z_\phi$，并在其诱导的线性策略空间中演化。

---

## 1. 算法概述

### 1.1 一句话定位

**ERL-Re²** 是把"标准 ERL 的非线性策略种群"替换为"**共享状态编码器 $Z_\phi$ + 个体线性策略矩阵 $W_i$**"的三阶段混合优化算法，并配合 **行为级遗传操作** 与 **PeVFA 替代适应度** 大幅提升样本效率。

### 1.2 设计动机（Why Re²）

相对标准 ERL 类工作（ERL/PDERL/CERL/CEM-RL），作者指出三个核心问题：

1. **知识不共享**
    - RL Actor 与每个 EA 个体都独立学一套非线性状态特征
    - 任何一个体学到的有用表示**无法直接传递**给其他个体
    - 个体间靠 replay 隐式共享，耦合极弱

2. **参数级遗传，行为语义不清**
    - 标准 ERL 在权重矩阵元素上做 k-point 交叉 / 高斯变异
    - 非线性网络下，权重小扰动 ↛ 行为小变化；常出现 **policy crash**
    - 交叉得到的子代行为不可解释（"交换第 3 层第 5 个神经元"无物理意义）

3. **EA 样本效率瓶颈**
    - 每代对种群做 **MC 完整 episode 评估**
    - 评估成本随 episode 长度线性增长，与 RL 部分的样本利用率不匹配

### 1.3 三个核心创新

| 创新 | 解决了什么 |
|------|-----------|
| **共享状态表示 $Z_\phi$ + 个体线性策略 $W_i$** | 共享非线性特征学习；个体只在低维线性空间演化；显式知识共享 |
| **行为级遗传操作 b-Crossover / b-Mutation（$\otimes_d$）** | 在 $W$ 的"动作维度行"上操作；语义清晰；不干扰其它动作维 |
| **PeVFA + Partial Rollout 替代适应度 $\hat{f}(W_i)$** | 用 $H$ 步部分轨迹 + PeVFA bootstrap 估算 fitness，降低评估成本 |

---

## 2. 数学基础与符号说明

### 2.1 主要符号（论文 §4 与附录 E）

| 符号 | 含义 | 维度 / 类型 |
|------|------|-----------|
| $Z_\phi$ | 共享状态编码器（非线性 MLP） | $Z_\phi:\mathbb{R}^{|\mathcal{S}|}\to\mathbb{R}^d,\ d=300$ |
| $z_t = Z_\phi(s_t)$ | 状态 $s_t$ 的共享特征 | $z_t\in\mathbb{R}^d$ |
| $W_i$ | 第 $i$ 个体的线性策略矩阵 | $W_i\in\mathbb{R}^{(d+1)\times|\mathcal{A}|}$ |
| $W_{i,[1:d]}$ | $W_i$ 的前 $d$ 行（权重） | $\mathbb{R}^{d\times|\mathcal{A}|}$ |
| $W_{i,[d+1]}$ | $W_i$ 的第 $d{+}1$ 行（偏置） | $\mathbb{R}^{|\mathcal{A}|}$ |
| $\pi_i(s)$ | 个体 $i$ 的策略函数 | $\mathbb{R}^{|\mathcal{A}|}\in[-1,1]$ |
| $\pi_{rl}$ | RL 智能体策略（同一形式） | 同上 |
| $\mathbb{P}$ | EA 种群 | $\mathbb{P}=\{W_1,\ldots,W_n\},\ n=5$ |
| $\mathbb{Q}_\theta(s,a,W)$ | **PeVFA**（策略扩展值函数）| 见 §3.2 |
| $Q_\psi(s,a)$ | RL Critic | 标准双 Q（TD3 实现） |
| $\mathcal{D}$ | 共享经验回放 | 由 EA 与 RL 共同填充 |
| $H$ | 部分 rollout 步长 | $H\in\{50, 200\}$（按任务）|
| $p$ | 用 MC（完整 episode）的概率 | 与 surrogate 互补，$1-p$ 用 $\hat{f}$ |
| $K$ | 更新 $Z_\phi$ 时从种群采样的个体数 | $K\in\{1,3\}$ |
| $\alpha$ | b-Mutation 中动作维被选中概率 | **固定 $\alpha=1.0$** |
| $\beta$ | 被选维内参数扰动比例 | 按任务，0.2 ~ 1.0 |
| $\gamma$ | 折扣因子 | 0.99（Swimmer 例外用 0.999）|
| $e$ | 精英数量 | **$e=1$**（固定）|

### 2.0 预备知识：基础 RL 与 EA 公式

**（论文第 2-3 页 / 附录 E.1）**

以下为基础 RL 与 EA 公式，构成 ERL-Re² 算法的理论基础。

**期望回报（折扣累积奖励）：**

$$
\boxed{R_t = \sum_{i=t}^{T} \gamma^{i-t} r_i}
$$

> 这是 RL 中最基本的定义：从时间步 $t$ 开始的折扣累积奖励，$\gamma \in [0,1)$ 为折扣因子，平衡近期与远期奖励的重要性。

**DDPG Critic 损失函数（第 2 页）：**

$$
\boxed{\mathcal{L}(\psi) = \mathbb{E}_{\mathcal{D}} \left[ \left( r + \gamma Q_{\psi'}(s', \pi_{\omega'}(s')) - Q_{\psi}(s,a) \right)^2 \right]}
$$

> Critic 通过最小化 TD 误差来学习动作值函数 $Q_\psi(s,a)$。其中 $\psi'$ 和 $\omega'$ 为目标网络参数，$\pi_{\omega'}$ 为目标策略。

**DDPG Actor 损失函数（第 2 页）：**

$$
\boxed{\mathcal{L}(\omega) = -\mathbb{E}_{\mathcal{D}} \left[ Q_{\psi}(s, \pi_{\omega}(s)) \right]}
$$

> Actor 通过最大化 Critic 给出的 $Q$ 值来更新策略 $\pi_\omega$。负号将最大化转为最小化，便于梯度下降优化。其梯度为 $\nabla_\omega \mathcal{L} = -\mathbb{E}[\nabla_a Q_\psi(s,a)|_{a=\pi_\omega(s)} \cdot \nabla_\omega \pi_\omega(s)]$。

**EA 适应度定义（第 3 页）：**

$$
\boxed{f(\pi) = \frac{1}{e} \sum_{i=1}^{e} \left[ \sum_{t=0}^{T} r_t \mid \pi \right]}
$$

> 适应度 $f(\pi)$ 衡量策略 $\pi$ 在环境中 $e$ 条完整 episode 的平均累积回报。ERL-Re² 的替代适应度 $\hat{f}(W_i)$（式 3）是对此的近似加速版本。

### 2.2 个体策略的构造（论文 §4.1）

每个智能体(包括ea个体和RLagent)的策略为 **共享非线性特征 → 个体线性映射 → 激活** 的两阶段结构：

$$
\boxed{\pi_i(s) = \mathrm{act}\bigl(Z_\phi(s)^\top W_{i,[1:d]} + W_{i,[d+1]}\bigr)}
$$

其中 $\mathrm{act}$ 为 $\tanh$（确定性策略；论文脚注说明可推广到随机策略）。

**维度链**：

$$
\underbrace{Z_\phi(s_t)}_{1\times d}\cdot\underbrace{W_{i,[1:d]}}_{d\times|\mathcal{A}|}\;+\;\underbrace{W_{i,[d+1]}}_{1\times|\mathcal{A}|}\;\xrightarrow{\mathrm{act}}\;\underbrace{\pi_i(s_t)}_{1\times|\mathcal{A}|}
$$

**参数节省**：标准 ERL 个体是完整 MLP（数十万到数百万参数）；ERL-Re² 个体仅 $(d+1)\times|\mathcal{A}|$ 个参数（例如 $|\mathcal{A}|=6$ 时为 $301\times 6=1806$）。EA 在更低维空间搜索，效率显著提升。

### 2.3 行为级交叉算子 $\otimes_d$（论文 Eq.(4)）

给定 $A,B\in\mathbb{R}^{(d+1)\times|\mathcal{A}|}$ 与动作维度子集 $d\subseteq\{1,\ldots,|\mathcal{A}|\}$（每维以 50% 概率被选中）：

$$
\boxed{(A\otimes_d B)_{[:,i]} = \begin{cases}B_{[:,i]} & i\in d\\ A_{[:,i]} & i\notin d\end{cases}}
$$

> 注意：交换的是**列**——即"对应某个动作维度的整列参数"（含偏置元素）。**语义**："子代继承父代 A 控制大多数动作的策略，但借用父代 B 控制 $d$ 中那些动作维的策略"。例如交换关节 2 的列 = "我借用你控制关节 2 的方法"。

一对子代写作：

$$
(W_{c_1}, W_{c_2}) = (W_{p_1}\otimes_{d_1} W_{p_2},\ W_{p_2}\otimes_{d_2} W_{p_1})
$$

**b-Mutation 公式（论文 Eq.(4)）：**

行为级变异在动作维度上施加扰动，保持语义完整性：

$$
\boxed{W_{m_1} = W_{p_1} \otimes_{\hat{d}_1} P_1 = b\text{-Mutation}(W_{p_1})} \tag{Eq.4}
$$

其中 $\hat{d}_1 \subseteq \{1,\ldots,|\mathcal{A}|\}$ 是以概率 $\alpha=1.0$ 选中的动作维子集，$P_1$ 为扰动矩阵（从三选一分布采样：90% 加性小噪声 $W_{ij} \mathrel{+}= \mathcal{N}(0,\,0.1 \cdot |W_{ij}|)$、5% 加性大噪声 $W_{ij} \mathrel{+}= \mathcal{N}(0,\,10 \cdot |W_{ij}|)$、5% 重置为 $\mathcal{N}(0,1)$）。变异的语义为："对 $W_{p_1}$ 中被选动作维的整列参数施加扰动，保持未选中维不变"。

> **注**：源代码中三种变异均为**加性**（$W \mathrel{+}= \sigma |W| \cdot \mathcal{N}(0,1)$），且噪声强度**依赖于当前权重绝对值** $|W_{ij}|$，这与论文 Algorithm 3 中 ERL 的乘性变异 $M_{ij} \cdot \mathcal{N}(0, \sigma)$ 形式不同但效果相似——两者都保证大权重扰动大、小权重扰动小。

### 2.4 替代适应度 $\hat{f}(W_i)$（论文 Eq.(3)）

$$
\boxed{\hat{f}(W_i) = \underbrace{\sum_{t=0}^{H-1}\gamma^t r_t}_{\text{H 步部分回报}} + \underbrace{\gamma^H\,\mathbb{Q}_\theta\bigl(s_H,\pi_i(s_H),W_i\bigr)}_{\text{PeVFA 估计的剩余价值}}} \tag{Eq.3}
$$

**推导**：从无穷期回报展开

$$
G_0 = \sum_{t=0}^{\infty}\gamma^t r_t = \sum_{t=0}^{H-1}\gamma^t r_t + \gamma^H\!\sum_{t=H}^{\infty}\gamma^{t-H}r_t = \sum_{t=0}^{H-1}\gamma^t r_t + \gamma^H\, Q^{\pi_i}(s_H,\pi_i(s_H))
$$

把无法直接拿到的 $Q^{\pi_i}$ 用 **PeVFA** 近似。PeVFA 把策略表示 $W_i$ 作为输入，用同一网络同时维护多个策略的 $Q$ 值。

**优势**：
1. **速度**：$H$ 步 rollout（通常 50~200）vs 完整 episode（可能 1000+ 步）
2. **样本效率**：PeVFA 复用历史数据
3. **理论保证**：PeVFA 精确时 $\hat{f}(W_i)\approx f(W_i)$

### 2.5 双 Critic 损失（论文 Eq.(1)）

**PeVFA 损失**（为 EA 种群服务，对策略表示 $W$ 同时建模）：

$$
\mathcal{L}_\mathbb{Q}(\theta) = \mathbb{E}_{(s,a,r,s')\sim\mathcal{D},\,W_i\sim\mathbb{P}}\!\left[\bigl(r+\gamma\,\mathbb{Q}_{\theta'}(s',\pi_i(s'),W_i) - \mathbb{Q}_\theta(s,a,W_i)\bigr)^2\right] \tag{Eq.1}
$$

**RL Critic 损失**（为 RL 智能体服务）：

$$
\mathcal{L}_Q(\psi) = \mathbb{E}_{(s,a,r,s')\sim\mathcal{D}}\!\left[\bigl(r+\gamma\,Q_{\psi'}(s',\pi_{rl}'(s')) - Q_\psi(s,a)\bigr)^2\right] \tag{Eq.1}
$$

> **实现细节（附录 E.2）**：[[PeVFA]] 与 RL Critic **均用原始 $s$ 作为输入**（不经 $Z_\phi$），避免 actor-critic 共享表示带来的相互干扰；TD3 实现使用 **clipped double Q**。

### 2.6 共享表示更新（论文 Eq.(2)）

**核心思想**：$Z_\phi$ 应让 **RL 智能体与 $K$ 个采样到的 EA 个体** 的总 $Q$ 值同时变大。

$$
\boxed{\mathcal{L}_Z(\phi) = -\mathbb{E}_{s\sim\mathcal{D},\,\{W_{j_m}\}_{m=1}^{K}\sim\mathbb{P}}\!\left[Q_\psi(s,\pi_{rl}(s)) + \sum_{m=1}^{K}\mathbb{Q}_\theta\bigl(s,\pi_{j_m}(s),W_{j_m}\bigr)\right]} \tag{Eq.2}
$$

**梯度反向传播路径**：对每个 $Q(s,\pi(s),\cdot)$ 项使用链式法则：

$$
\nabla_\phi Q\bigl(s,\pi(s)\bigr) = \underbrace{\nabla_a Q(s,a)\big|_{a=\pi(s)}}_{\text{Critic 局部梯度}}\cdot\underbrace{\nabla_\phi \pi(s)}_{\text{策略对 }\phi\text{ 的梯度}}
$$

而 $\pi(s)=\mathrm{act}(Z_\phi(s)^\top W+b)$，所以：

$$
\nabla_\phi \pi(s) = \mathrm{diag}\bigl(1-\mathrm{act}^2(\cdot)\bigr)\cdot W^\top \cdot \nabla_\phi Z_\phi(s)
$$

$K$ 个 EA 个体 + RL 共 $K{+}1$ 项的梯度求和，构成"统一方向"。

> **实现细节（源代码）**：Actor 更新与 $Z_\phi$ 更新是**耦合**的。源代码中 Actor loss $-\mathbb{E}[Q_\psi(s,\pi_{rl}(s))]$ 与 PeVFA 项 $-\sum\mathbb{Q}_\theta(s,\pi_i(s),W_i)$ 加权求和为 `total_loss`，通过**一次 `backward()` 同时更新** Actor 参数 $W_{rl}$ 和 $Z_\phi$ 参数 $\phi$。这种耦合使得 Actor loss 的梯度也流向 $Z_\phi$，反之亦然。此外，Critic 和 PeVFA 的输入使用**原始状态 $s$**（不经 $Z_\phi$），避免 actor-critic 共享表示导致的相互干扰。

### 2.7 RL Actor 损失（论文 Eq.(5)）

$$
\mathcal{L}_{\mathrm{RL}}(W_{rl}) = -\mathbb{E}_{s\sim\mathcal{D}}\bigl[Q_\psi(s,\pi_{rl}(s))\bigr],\quad \pi_{rl}(s) = \mathrm{act}\bigl(Z_\phi(s)^\top W_{rl,[1:d]} + W_{rl,[d+1]}\bigr) \tag{Eq.5}
$$

**策略梯度**（与 DDPG 同构）：

$$
\nabla_{W_{rl}}\mathcal{L}_{\mathrm{RL}} = -\mathbb{E}_s\!\left[\nabla_a Q_\psi(s,a)\big|_{a=\pi_{rl}(s)}\cdot\nabla_{W_{rl}}\pi_{rl}(s)\right]
$$

### 2.8 目标网络软更新

$$
\theta'\leftarrow(1-\tau)\theta'+\tau\theta,\quad \psi'\leftarrow(1-\tau)\psi'+\tau\psi,\quad W_{rl}'\leftarrow(1-\tau)W_{rl}'+\tau W_{rl},\quad \phi'\leftarrow(1-\tau)\phi'+\tau\phi
$$

> **注**：$Z_\phi$ 的目标网络 $\phi'$ 同样需要软更新，论文虽未在公式中显式列出，但源代码中明确实现了 `state_embedding_target` 的软更新。

---

## 3. 网络架构（论文附录 E.2 / Table 4-5）

### 3.1 共享状态编码器 $Z_\phi$

$$
Z_\phi:\ s\xrightarrow{\text{FC}(|\mathcal{S}|,400)\to\tanh}h_1\xrightarrow{\text{FC}(400,300)\to\tanh}z\in\mathbb{R}^{300}
$$

- 两层全连接：`(|S| → 400) → (400 → 300)`
- 激活：tanh（确保输出有界，便于线性策略 + tanh 输出）
- 输出维度 $d=300$（全文固定）

### 3.2 PeVFA $\mathbb{Q}_\theta(s,a,W)$ 的实现结构

PeVFA 需要把策略矩阵 $W\in\mathbb{R}^{301\times|\mathcal{A}|}$ 编码成定长嵌入：

1. **策略编码器**：对 $W$ 的每一列（$\mathbb{R}^{301}$，对应一个动作维度），用 **3 层 FC（论文宽 64，源代码默认宽 pr=128）+ LeakyReLU** 编码为对应维度嵌入
2. **动作维度池化**：在 $|\mathcal{A}|$ 个嵌入向量上做 **mean pooling**，得到 policy embedding $\bar{e}_W$
3. **价值网络**：把 $(s, a, \bar{e}_W)$ 拼接（输入维 $|\mathcal{S}|+|\mathcal{A}|+\text{pr}$）→ `400 → 300 → 1`

实现上采用 **TD3 双 Q**（clipped double Q）。

> **论文 vs 源代码差异**：论文 Table 5 给出策略编码器宽度为 64，但源代码命令行默认 `pr=128`。此外，论文明确写了编码器最后一层**无激活函数**（仅前两层用 LeakyReLU），源代码中 `policy_w_l3` 也无激活，一致。

### 3.3 RL Critic $Q_\psi(s,a)$

标准 TD3 双 Q 结构，**输入 $s,a$ 不经 $Z_\phi$**（避免与 actor 表示耦合）。激活函数为 **LeakyReLU** + LayerNorm。

---

## 4. 算法伪代码

### 4.1 Algorithm 1：ERL-Re² 主循环

```text
Algorithm 1  ERL with Two-scale State and Policy Representation (ERL-Re²)

Input:  EA 种群大小 n=5；MC 概率 p；H 步 partial rollout 长度
Init:   共享编码器 Z_φ（参数 φ）；RL 线性策略 W_rl ∈ R^{(d+1)×|A|}
        EA 种群 P = {W_1, ..., W_n}（随机初始化）
        RL Critic Q_ψ；PeVFA Q_θ；目标网络 θ', ψ', W_rl'
        共享回放 D = ∅

repeat
  # ─── Phase 1: 数据收集与适应度评估 ───
  if Random() > p then
      对每个 W_i ∈ P，在 Z_φ 下做 H 步 rollout，用 surrogate 适应度 \hat{f}(W_i)   (Eq.3)
  else
      对每个 W_i ∈ P，在 Z_φ 下做完整 episode，用 MC 回报作为 f(W_i)
  end if
  对 RL 智能体（W_rl + Z_φ）做完整 episode（OU 噪声），收集经验
  把上述所有轨迹存入 D

  # ─── Phase 2: 个体尺度优化 ───
  从 D 采样 mini-batch B
  更新 PeVFA Q_θ（Eq. 1）和 RL Critic Q_ψ（Eq. 1）
  对种群 P 做 GA：选择 + b-Crossover + b-Mutation（Algorithm 2） (Eq.4)
  if generation mod ω == 0 then
      用 W_rl 替换 P 中适应度最低的个体
  end if

  # ─── Phase 3: 共同尺度优化（Actor 与 Z_φ 耦合更新）───
  从 D 采样 mini-batch B
  计算 total_loss = α_actor · L_RL(W_rl) + α_EA · Σ L_PeVFA(W_{j_m})  （Eq. 5 + Eq. 2）
  一次 backward() 同时更新 W_rl 和 Z_φ
  从 P 采样 K 个 {W_{j_1}, ..., W_{j_K}}
  软更新目标网络: θ', ψ', W_rl', φ'
until 达到最大环境步数

return (best W_i in P, Z_φ)
```

```text
Algorithm 1 ERL-Re²

Input: the EA population size n, the probability p of using MC estimate, the partial rollout length H
Initialize: a replay buffer D, the shared state representation function Z_φ, the RL agent W_rl,
          the EA population P = {W_1, ..., W_n}, the RL critic Q_ψ and the PeVFA Q_θ
          (target networks are omitted here)
repeat
    # Rollout the EA and RL agents with Z_φ and estimate the (surrogate) fitness
    if Random Number > p then
        Rollout each agent in P for H steps and evaluate its fitness by the surrogate f^(W)    ▷ Eq. (3)
    else
        Rollout each agent in P for one episode and evaluate its fitness by MC estimate
    Rollout the RL agent for one episode
    Store the experiences generated by P and W_rl to D

    # Individual scale: evolution and reinforcement in the policy space
    Train PeVFA Q_θ and RL critic Q_ψ with D                                     ▷ Eq. (1)
    Optimize the EA population: perform the genetic operators (i.e., selection, crossover and mutation)
        at the behavior level for P = {W_1, ..., W_n}                           ▷ Eq. (4)
    Optimize the RL agent: update W_rl (by e.g., DDPG and TD3) according to Q_ψ ▷ Eq. (5)
    Inject RL agent to the population P periodically

    # Common scale: improving the policy space through optimizing Z_φ
    Update the shared state representation: optimize Z_φ with a unifying gradient direction
        derived from value function maximization regarding Q_θ and Q_ψ          ▷ Eq. (2)
until reaching maximum steps;
```

### 4.2 Algorithm 2：行为级遗传操作（PDERL-style 选择 + b-Crossover / b-Mutation）

```text
Algorithm 2  Behavioral Genetic Operations

Input:  种群 P = {W_1, ..., W_n}；适应度 {f_i}；α, β

# 选择
按 f_i 对 P 降序排序
精英 E = {W_(1)}                        ▷ e = 1
生成获胜者 Win：重复 (n − 1) 次:
    从非精英中随机抽 3 个，取适应度最高者加入 Win
丢弃者 Dis = P \ (E ∪ Win)

# b-Crossover
while Dis ≠ ∅ do
    从 Dis 取 W_{d_1}, W_{d_2}
    从 E 与 Win 各随机取 W_e, W_w
    克隆: W_{p_1} ← W_e；W_{p_2} ← W_w
    对每个动作维 i ∈ {1, ..., |A|}：
        以 0.5 概率把 W_{p_1} 的第 i 列换为 W_{p_2} 的第 i 列
        反之亦然
    用 (W_{p_1}, W_{p_2}) 替换 (W_{d_1}, W_{d_2})
end while

# b-Mutation
for each W ∈ P \ E do
    if r() < 0.9 then                    ▷ 整体变异概率
        for each 动作维 i ∈ {1, ..., |A|} do
            if r() < α then              ▷ α = 1.0
                对 W 的第 i 列：随机选 β 比例的元素，
                按以下三选一扰动（均为加性、权重依赖）：
                    90% : W += N(0, 0.1·|W|)   ▷ 小变异
                    5%  : W += N(0, 10·|W|)    ▷ 大变异（super mutation）
                    5%  : W = N(0, 1)           ▷ 重置
            end if
        end for
    end if
end for
```

### 4.3 Algorithm 3：CEM 变体（论文附录 F.1，可替换 GA）

ERL-Re² 也可用 **CEM** 替换 Algorithm 2 的种群生成：维护 $(\mu,\Sigma)$，每代从 $\mathcal{N}(\mu,\Sigma)$ 采 $n$ 个个体；用前 $n/2$ 精英更新分布。Phase 1/2/3 其余结构不变。

---

## 5. 超参数

### 5.1 通用超参（论文附录 E.3）

| 参数 | 符号 | 取值 |
|------|------|------|
| 种群大小 | $n$ | **5** |
| 特征维度 | $d$ | **300** |
| 精英数 | $e$ | **1** |
| 折扣因子 | $\gamma$ | 0.99（Swimmer 用 **0.999**）|
| 整体变异概率 | — | 0.9 |
| 动作维选中概率 | $\alpha$ | **1.0** |
| 小/大/重置扰动比例 | — | 90% / 5% / 5% |
| 小变异强度 | $\sigma_{\text{norm}}$ | 0.1（加性：$W \mathrel{+}= \mathcal{N}(0, 0.1 \cdot |W|)$）|
| 大变异强度 | $\sigma_{\text{super}}$ | 10（加性：$W \mathrel{+}= \mathcal{N}(0, 10 \cdot |W|)$）|
| 重置分布 | — | $\mathcal{N}(0, 1)$ |
| 变异列比例 | $\beta$ | 逐环境不同，0.2 ~ 1.0（见 Table 6/7）|
| Actor/Critic lr | — | 1e-3（源代码默认，非论文指定）|
| PeVFA lr | — | 1e-3（源代码默认）|
| Z_φ lr | — | 1e-3（源代码默认）|
| 梯度裁剪 | — | 10（所有网络）|
| 训练步数 | — | $1\times 10^6$（部分长尾实验 $3\times 10^6$）|
| 种子数 | — | 5（95% 置信带）|
| RL→EA 同步频率 | $\omega$ | 1（大部分环境），Swimmer 为 10 |

### 5.2 逐环境超参（论文 Table 6: TD3 版，Table 7: DDPG 版）

| 环境 | TD3: $(p, \beta, H, K)$ | DDPG: $(p, \beta, H, K)$ |
|------|------------------------|--------------------------|
| HalfCheetah | (0.3, 1.0, 200, 1) | (0.5, 1.0, 200, 1) |
| Walker2d | (0.8, 0.2, 50, 1) | (0.8, 0.2, 50, 1) |
| Swimmer | (0.3, 1.0, 200, 3) | (0.3, 0.5, 200, 3) |
| Hopper | (0.8, 0.2, 50, 3) | (0.8, 0.7, 50, 3) |
| Ant | (0.5, 0.7, 200, 1) | (0.7, 0.5, 200, 1) |
| Humanoid | (0.5, 0.5, 200, 1) | (0.7, 0.5, 200, 1) |

**调参直觉**：

- 稳定 locomotion（Walker、Hopper）：$\beta$ 小、$H$ 短 → 避免行为剧烈变化
- 高动作维 / 探索强（HalfCheetah、Swimmer）：$\beta$ 大、$H$ 长 → 鼓励多样性
- 关键观察：附录 E.3 说明即使 **$p=1$（始终 MC，关闭 surrogate）也能与现有 baseline 竞争**

---

## 6. 实验设置

### 6.1 环境

**6 个 MuJoCo v2**：HalfCheetah, Walker2d, Hopper, Swimmer, Ant, Humanoid

> **重要**：ERL-Re² 论文实验**不包含 Reacher**（先前版本笔记有误）。

### 6.2 基线

- **纯 RL**：DDPG, TD3, SAC, PPO
- **ERL 系**：ERL (Khadka 2018), CERL, PDERL, CEM-RL
- 每个方法都报告 DDPG 与 TD3 两个 RL 主干版本
- 实现：基于官方代码 + stable-baselines3；ERL-Re² 基于 **PDERL** 代码库

### 6.3 评估

- 训练步数 $1\times 10^6$（部分 $3\times 10^6$）
- 5 个随机种子，报告均值 + 95% 置信带
- 种群规模：每方法在 $\{5,10\}$ 中取最优；ERL-Re² 固定 5

---

## 7. 关键实验结论

### 7.1 整体性能

- ERL-Re²-TD3 / ERL-Re²-DDPG 相对所有 baselines **收敛速度提升约 5×**（达到同等性能所需步数）
- 在 6 个 MuJoCo 任务上**全面优于** ERL/CERL/PDERL/CEM-RL

### 7.2 关键 Ablation（论文 Fig.6, Fig.10）

| Ablation | 效果 |
|----------|------|
| 只保留 Eq.(2) 中 Critic 项（无 PeVFA 项更新 $Z_\phi$） | 性能下降 |
| 只保留 PeVFA 项（无 Critic 项） | 性能下降 |
| $K$ 取 1 vs 3 | 任务相关，需调 |
| 用参数级遗传（标准 ERL 做法）替换 b-Crossover/Mutation | 显著变差 — 行为级操作是关键 |
| 关掉 surrogate（$p=1$，始终 MC） | 仍优于多数 baseline，但失去样本效率优势 |
| 仅 b-Crossover 或仅 b-Mutation | 都各有贡献，组合最佳 |

### 7.3 相对标准 ERL 的提升

| 指标 | 提升 | 原因 |
|------|------|------|
| 样本效率 | 2-3× | $\hat{f}$ 减少 rollout 步数 |
| 收敛速度 | 30-50% | 行为级操作 + 共享表示加速学习 |
| 可解释性 | 显著 | 线性策略可直接可视化、按动作维分析 |
| 计算开销 | 降低 | 线性策略前向比深度 MLP 快 |
| 参数效率 | 100~1000× | 个体只需 $(d+1)|\mathcal{A}|$ 参数，标准 ERL 需要数十万 |

### 7.4 三种核心机制的语义对比

| 维度 | 标准 ERL | ERL-Re² |
|------|---------|---------|
| 个体策略结构 | 完整非线性 MLP $\pi(\cdot\mid\theta^\pi)$ | $\pi_i(s)=\mathrm{act}(Z_\phi(s)^\top W_{i,[1:d]}+W_{i,[d+1]})$ |
| 交叉操作对象 | 网络权重矩阵片段交换 | 动作维度整列交换 $A\otimes_d B$ |
| 变异操作对象 | 权重矩阵元素级噪声 | 动作维度整列扰动 |
| 知识共享 | 仅通过 replay 间接共享 | $Z_\phi$ 显式共享 + replay 间接共享 |
| EA 值估计 | MC 回报 $f(\pi)=\sum r_t$ | MC 或 PeVFA 替代 $\hat{f}(W)$ |
| Critic 结构 | 单 $Q_\psi$（仅 RL）| $Q_\psi$（RL）+ $\mathbb{Q}_\theta(s,a,W)$（EA） |
| 状态表示学习 | 无显式机制 | 通过 Eq.(2) 显式联合优化 |

---

## 8. 项目实现说明

### 8.1 仓库目录结构

```text
EX2_ERL-Re^2/
├── erl_re2/                      # 核心算法包
│   ├── algorithm.py              # ERL-Re² 主算法
│   ├── networks.py               # StateEncoder / PeVFA / RLCritic
│   ├── linear_policy.py          # 线性策略 (LinearPolicy, RLPolicy)
│   ├── genetic_ops.py            # 行为级遗传算子
│   └── replay_buffer.py          # 共享经验回放
├── experiments/
│   ├── locomotion/
│   │   ├── train_halfcheetah.py
│   │   └── train_ant.py
│   └── manipulation/
│       └── train_reacher.py      # 自定义扩展实验（非论文环境）
├── outputs/
├── docs/                         # 本报告与论文 PDF
└── README.md
```

### 8.2 快速开始

```bash
pip install torch numpy gymnasium "gymnasium[mujoco]"

cd experiments/locomotion
python train_halfcheetah.py --gens 50 --pop-size 5
```

---

## 9. 参考文献

[1] Hao, J., Li, P., Tang, H., Zheng, Y., Fu, X., & Meng, Z. (2023). *ERL-Re²: Efficient Evolutionary Reinforcement Learning with Shared State Representation and Individual Policy Representation*. **ICLR 2023**. arXiv:2210.17375.

[2] Khadka, S., & Tumer, K. (2018). *Evolution-Guided Policy Gradient in Reinforcement Learning* (ERL). NeurIPS 2018.

[3] Khadka, S., Majumdar, S., Nassar, T., et al. (2019). *Collaborative Evolutionary Reinforcement Learning* (CERL). ICML 2019.

[4] Bodnar, C., Day, B., & Lió, P. (2020). *Proximal Distilled Evolutionary Reinforcement Learning* (PDERL). AAAI 2020.

[5] Pourchot, A., & Sigaud, O. (2019). *CEM-RL: Combining Evolutionary and Gradient-Based Methods for Policy Search*. ICLR 2019.

[6] Tang, H., Meng, Z., Hao, J., et al. (2022). *Policy-Extended Value Function Approximator* (PeVFA). AAAI 2022.

[7] Lillicrap, T. P., Hunt, J. J., Pritzel, A., et al. (2016). *Continuous Control with Deep Reinforcement Learning* (DDPG). ICLR 2016.

[8] Fujimoto, S., van Hoof, H., & Meger, D. (2018). *Addressing Function Approximation Error in Actor-Critic Methods* (TD3). ICML 2018.

[9] Haarnoja, T., Zhou, A., Abbeel, P., & Levine, S. (2018). *Soft Actor-Critic* (SAC). ICML 2018.

[10] Schulman, J., Wolski, F., Dhariwal, P., et al. (2017). *Proximal Policy Optimization Algorithms* (PPO). arXiv:1707.06347.

[11] Sigaud, O. (2022). *Combining Evolution and Deep Reinforcement Learning for Policy Search: a Survey*. arXiv:2203.14009.

[12] Gangwani, T., & Peng, J. (2018). *Policy Optimization by Genetic Distillation*. ICLR 2018.

[13] Todorov, E., Erez, T., & Tassa, Y. (2012). *MuJoCo: A Physics Engine for Model-Based Control*. IROS 2012.