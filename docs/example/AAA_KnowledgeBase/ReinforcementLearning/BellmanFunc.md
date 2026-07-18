抱歉，这是 LaTeX 渲染问题。我重新用纯文本形式写第七部分，保证所有公式清晰可读，并保证整个报告公式严格渲染。

# 贝尔曼方程完整推导（公式渲染修复版）

## 符号约定

| 符号 | 含义 |
|------|------|
| S_t | 时间步 t 的状态（随机变量） |
| A_t | 时间步 t 的动作（随机变量） |
| R_{t+1} | 在 S_t 执行 A_t 后获得的即时奖励（随机变量） |
| R(s,a) | 在状态 s 执行动作 a 后的即时奖励（确定性函数） |
| P(s' | s, a) | 状态转移概率：Pr(S_{t+1}=s' | S_t=s, A_t=a) |
| pi(a | s) | 策略：在状态 s 下选择动作 a 的概率 |
| gamma in [0,1) | 折扣因子 |
| G_t | 从时间步 t 开始的折扣累积回报 |
| E_pi[·] | 在策略 pi 和环境动态下的期望 |

---

## 第一部分：折扣回报的递归结构

### 定义

折扣累积回报（return）是从时间步 t 开始，未来所有折扣奖励的总和：

$$
G_t = R_{t+1} + \gamma R_{t+2} + \gamma^2 R_{t+3} + \cdots = \sum_{k=0}^{\infty} \gamma^k R_{t+k+1}
$$

### 递归性质

将第一项奖励与后续奖励分离：

$$
G_t = R_{t+1} + \gamma \underbrace{(R_{t+2} + \gamma R_{t+3} + \gamma^2 R_{t+4} + \cdots)}_{G_{t+1}}
$$

因此：

$$
\boxed{G_t = R_{t+1} + \gamma G_{t+1}} \tag{0}
$$

> 这个递归关系是确定性的恒等式，不涉及任何期望或策略。

---

## 第二部分：状态价值函数 V^π(s) 的贝尔曼方程

### 定义

状态价值函数 V^π(s) 表示：从状态 s 出发，此后一直遵循策略 π，所获得的期望折扣累积回报。

$$
V^\pi(s) = \mathbb{E}_\pi \left[ G_t \mid S_t = s \right] \tag{1}
$$

### 推导

将递归关系 G_t = R_{t+1} + \gamma G_{t+1} 代入 (1)：

$$
V^\pi(s) = \mathbb{E}_\pi \left[ R_{t+1} + \gamma G_{t+1} \mid S_t = s \right] \tag{2}
$$

利用期望的线性性质：

$$
V^\pi(s) = \mathbb{E}_\pi \left[ R_{t+1} \mid S_t = s \right] + \gamma \mathbb{E}_\pi \left[ G_{t+1} \mid S_t = s \right] \tag{3}
$$

### 处理第一项：E_pi[R_{t+1} | S_t = s]

给定当前状态 S_t = s，动作 A_t 由策略 π 采样：

$$
\mathbb{E}_\pi \left[ R_{t+1} \mid S_t = s \right] = \sum_{a} \pi(a \mid s) \cdot \mathbb{E}_\pi \left[ R_{t+1} \mid S_t = s, A_t = a \right]
$$

给定 (S_t, A_t) = (s, a)，即时奖励由 R(s, a) 决定：

$$
\mathbb{E}_\pi \left[ R_{t+1} \mid S_t = s \right] = \sum_{a} \pi(a \mid s) \, R(s, a) \tag{4}
$$

### 处理第二项：E_pi[G_{t+1} | S_t = s]

先对下一状态 S_{t+1} 取条件：

$$
\mathbb{E}_\pi \left[ G_{t+1} \mid S_t = s \right] = \sum_{s'} \Pr(S_{t+1}=s' \mid S_t=s) \cdot \mathbb{E}_\pi \left[ G_{t+1} \mid S_{t+1} = s' \right]
$$

其中：

- Pr(S_{t+1}=s' | S_t=s) = sum_a pi(a|s) P(s'|s,a)
- E_pi[G_{t+1} | S_{t+1}=s'] = V^π(s')

因此：

$$
\mathbb{E}_\pi \left[ G_{t+1} \mid S_t = s \right] = \sum_{s'} \left( \sum_a \pi(a \mid s) P(s' \mid s, a) \right) V^\pi(s') \tag{5}
$$

### 合并 (3)(4)(5)

交换求和顺序，得到最终形式：

$$
\boxed{V^\pi(s) = \sum_{a} \pi(a \mid s) \sum_{s'} P(s' \mid s, a) \left[ R(s, a) + \gamma V^\pi(s') \right]} \tag{6}
$$

### 算子形式

定义 Bellman 算子 T^π：

$$
(\mathcal{T}^\pi V)(s) = \sum_a \pi(a \mid s) \sum_{s'} P(s' \mid s, a) \left[ R(s, a) + \gamma V(s') \right]
$$

则贝尔曼方程写成紧凑形式：

$$
\boxed{V^\pi = \mathcal{T}^\pi V^\pi} \tag{7}
$$

---

## 第三部分：动作价值函数 Q^π(s,a) 的贝尔曼方程

### 定义

动作价值函数 Q^π(s,a) 表示：从状态 s 出发，强制执行动作 a（不一定由策略 π 选择），此后一直遵循策略 π，所获得的期望折扣累积回报。

$$
Q^\pi(s, a) = \mathbb{E}_\pi \left[ G_t \mid S_t = s, A_t = a \right] \tag{8}
$$

### 推导

将 G_t = R_{t+1} + \gamma G_{t+1} 代入 (8)：

$$
Q^\pi(s, a) = \mathbb{E}_\pi \left[ R_{t+1} + \gamma G_{t+1} \mid S_t = s, A_t = a \right] \tag{9}
$$

$$
Q^\pi(s, a) = \mathbb{E}_\pi \left[ R_{t+1} \mid S_t = s, A_t = a \right] + \gamma \mathbb{E}_\pi \left[ G_{t+1} \mid S_t = s, A_t = a \right] \tag{10}
$$

### 处理第一项

给定 (S_t, A_t) = (s, a)，即时奖励由 R(s,a) 决定：

$$
\mathbb{E}_\pi \left[ R_{t+1} \mid S_t = s, A_t = a \right] = R(s, a) \tag{11}
$$

### 处理第二项

对下一状态 S_{t+1} 取条件：

$$
\mathbb{E}_\pi \left[ G_{t+1} \mid S_t = s, A_t = a \right] = \sum_{s'} P(s' \mid s, a) \cdot \mathbb{E}_\pi \left[ G_{t+1} \mid S_{t+1} = s' \right]
$$

根据 V^π 的定义：

$$
\mathbb{E}_\pi \left[ G_{t+1} \mid S_{t+1} = s' \right] = V^\pi(s')
$$

因此：

$$
\mathbb{E}_\pi \left[ G_{t+1} \mid S_t = s, A_t = a \right] = \sum_{s'} P(s' \mid s, a) V^\pi(s') \tag{12}
$$

### 合并 (10)(11)(12)

$$
\boxed{Q^\pi(s, a) = \sum_{s'} P(s' \mid s, a) \left[ R(s, a) + \gamma V^\pi(s') \right]} \tag{13}
$$

### 用 Q^π 表达 V^π

$$
V^\pi(s) = \sum_a \pi(a \mid s) Q^\pi(s, a) \tag{14}
$$

### 将 (14) 代入 (13)

$$
\boxed{Q^\pi(s, a) = \sum_{s'} P(s' \mid s, a) \left[ R(s, a) + \gamma \sum_{a'} \pi(a' \mid s') Q^\pi(s', a') \right]} \tag{15}
$$

---

## 第四部分：V^π 与 Q^π 的贝尔曼方程对比

| 维度 | V^π 的贝尔曼方程 | Q^π 的贝尔曼方程 |
|------|-----------------|-----------------|
| 未知函数 | V^π(s) | Q^π(s,a) |
| 定义域 | 状态空间 S | 状态-动作空间 S × A |
| 贝尔曼方程 | V^π(s) = sum_a pi(a|s) sum_{s'} P(s'|s,a) [R(s,a) + gamma V^π(s')] | Q^π(s,a) = sum_{s'} P(s'|s,a) [R(s,a) + gamma sum_{a'} pi(a'|s') Q^π(s',a')] |
| V^π 与 Q^π 的关系 | V^π(s) = sum_a pi(a|s) Q^π(s,a) | Q^π(s,a) = R(s,a) + gamma sum_{s'} P(s'|s,a) V^π(s') |
| 推导起点 | V^π(s) = E_pi[G_t | S_t=s] | Q^π(s,a) = E_pi[G_t | S_t=s, A_t=a] |
| 应用场景 | 策略评估、策略迭代 | Q-Learning、SARSA、Actor-Critic |

---

## 第五部分：确定性策略的贝尔曼方程

当策略是确定性的，即存在函数 mu: S -> A 使得 pi(a|s) = 1{a = mu(s)}。

### 状态价值函数

$$
V^\mu(s) = \sum_{s'} P(s' \mid s, \mu(s)) \left[ R(s, \mu(s)) + \gamma V^\mu(s') \right] \tag{16}
$$

### 动作价值函数

$$
\boxed{Q^\mu(s, a) = \sum_{s'} P(s' \mid s, a) \left[ R(s, a) + \gamma Q^\mu(s', \mu(s')) \right]} \tag{17}
$$

> (17) 正是 DDPG 论文中的公式 (3)。关键洞察：目标值 R(s,a) + gamma Q^mu(s', mu(s')) 的期望只对环境动态 P 取，不对策略分布取期望 → 可以用任意行为策略 beta 生成的 transitions 来学习 Q^mu → 异策略学习的理论基础。

---

## 第六部分：最优贝尔曼方程

### 最优状态价值函数

$$
V^*(s) = \max_\pi V^\pi(s)
$$

$$
\boxed{V^*(s) = \max_a \sum_{s'} P(s' \mid s, a) \left[ R(s, a) + \gamma V^*(s') \right]} \tag{18}
$$

### 最优动作价值函数

$$
Q^*(s, a) = \max_\pi Q^\pi(s, a)
$$

$$
\boxed{Q^*(s, a) = \sum_{s'} P(s' \mid s, a) \left[ R(s, a) + \gamma \max_{a'} Q^*(s', a') \right]} \tag{19}
$$

> (19) 是 DQN 算法试图逼近的目标。

### V^* 与 Q^* 的关系

$$
V^*(s) = \max_a Q^*(s, a)
$$

$$
Q^*(s, a) = R(s, a) + \gamma \sum_{s'} P(s' \mid s, a) V^*(s')
$$

---

## 第七部分：压缩映射证明

### Bellman 算子定义

定义 T^π: B(S) -> B(S)：

$$
(\mathcal{T}^\pi V)(s) = \sum_a \pi(a \mid s) \sum_{s'} P(s' \mid s, a) \left[ R(s, a) + \gamma V(s') \right]
$$

其中 B(S) 是 S 上的有界实值函数空间，配备 sup 范数 ||V||_∞ = sup_s |V(s)|。

### gamma-收缩性

对于任意 V_1, V_2 in B(S)，在任意状态 s：

$$
|(\mathcal{T}^\pi V_1)(s) - (\mathcal{T}^\pi V_2)(s)|
$$

展开：

$$
= \left| \sum_a \pi(a|s) \sum_{s'} P(s'|s,a) \gamma [V_1(s') - V_2(s')] \right|
$$

利用绝对值不等式（三角不等式）：

$$
\le \gamma \sum_a \pi(a|s) \sum_{s'} P(s'|s,a) \cdot |V_1(s') - V_2(s')|
$$

由于 |V_1(s') - V_2(s')| ≤ ||V_1 - V_2||_∞ 对所有 s' 成立：

$$
\le \gamma \cdot \|V_1 - V_2\|_\infty \cdot \sum_a \pi(a|s) \sum_{s'} P(s'|s,a)
$$

因为 sum_a pi(a|s) = 1，sum_{s'} P(s'|s,a) = 1，所以：

$$
\le \gamma \|V_1 - V_2\|_\infty
$$

对所有 s 取 sup：

$$
\boxed{\|\mathcal{T}^\pi V_1 - \mathcal{T}^\pi V_2\|_\infty \le \gamma \|V_1 - V_2\|_\infty} \tag{20}
$$

### 结论

由于 gamma < 1，T^π 是 B(S) 上的压缩映射 (contraction mapping)。

根据 Banach 不动点定理 (Banach Fixed-Point Theorem)：

1. T^π 存在唯一的不动点 V^π
2. 从任意 V_0 in B(S) 出发，迭代 V_{k+1} = T^π V_k 都会收敛到 V^π

### 收敛速度

由压缩映射性质进一步得到线性收敛速率：

$$
\|V_k - V^\pi\|_\infty \le \gamma^k \|V_0 - V^\pi\|_\infty
$$

这保证了策略评估的数值迭代算法会指数级收敛。

---

## 第八部分：完整公式汇总表

| 名称 | 公式 | 编号 |
|------|------|------|
| 回报递归 | G_t = R_{t+1} + γ G_{t+1} | (0) |
| V 的定义 | V^π(s) = E_pi[G_t | S_t=s] | (1) |
| Q 的定义 | Q^π(s,a) = E_pi[G_t | S_t=s, A_t=a] | (8) |
| V 的贝尔曼方程 | V^π(s) = sum_a pi(a|s) sum_{s'} P(s'|s,a) [R(s,a) + γ V^π(s')] | (6) |
| Q 的贝尔曼方程 | Q^π(s,a) = sum_{s'} P(s'|s,a) [R(s,a) + γ sum_{a'} pi(a'|s') Q^π(s',a')] | (15) |
| V 与 Q 的关系 | V^π(s) = sum_a pi(a|s) Q^π(s,a) | (14) |
| V 与 Q 的关系 | Q^π(s,a) = R(s,a) + γ sum_{s'} P(s'|s,a) V^π(s') | (13) |
| 确定性 Q 贝尔曼方程 | Q^μ(s,a) = sum_{s'} P(s'|s,a) [R(s,a) + γ Q^μ(s', μ(s'))] | (17) |
| 最优 V 贝尔曼方程 | V^*(s) = max_a sum_{s'} P(s'|s,a) [R(s,a) + γ V^*(s')] | (18) |
| 最优 Q 贝尔曼方程 | Q^*(s,a) = sum_{s'} P(s'|s,a) [R(s,a) + γ max_{a'} Q^*(s',a')] | (19) |
| 压缩映射 | ||T^π V_1 - T^π V_2||_∞ ≤ γ ||V_1 - V_2||_∞ | (20) |

---

## 第九部分：在 DDPG 中的具体应用

DDPG 算法直接利用确定性策略的贝尔曼方程 (17) 来更新 Critic：

$$
y_i = r_i + \gamma Q'(s_{i+1}, \mu'(s_{i+1}))
$$

然后通过最小化贝尔曼残差来训练 Critic：

$$
L = \frac{1}{N} \sum_i \left( y_i - Q(s_i, a_i) \right)^2
$$

Actor 则沿着使 Q 值增大的方向更新：

$$
\nabla_{\theta^\mu} J \approx \frac{1}{N} \sum_i \nabla_a Q(s,a) \big|_{a=\mu(s_i)} \nabla_{\theta^\mu} \mu(s_i)
$$

这等价于对最优贝尔曼方程 (19) 的近似求解。