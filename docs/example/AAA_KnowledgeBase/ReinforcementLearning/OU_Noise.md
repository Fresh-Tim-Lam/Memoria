# 📊 Ornstein-Uhlenbeck 噪声

完整数学推导 | 统计性质 | 强化学习应用 | 代码实现


## 0. 📚 Ornstein-Uhlenbeck 过程的来源与背景

### 0.1 起源与命名

这个过程由荷兰物理学家 **Leonard Ornstein** 和 **George Eugene Uhlenbeck** 在 **1930年** 的论文 *On the Theory of the Brownian Motion* 中正式提出，因此以两人的名字命名。

它的诞生是为了解决早期布朗运动理论的局限性：爱因斯坦的经典模型只描述了粒子位置的扩散，而忽略了**速度的衰减（摩擦效应）**。Ornstein 和 Uhlenbeck 则直接对**布朗粒子的速度**建模，引入了均值回归和噪声项，从而得到了这一经典随机微分方程。

### 0.2 物理背景：从朗之万方程到 OU 过程

它本质上是**朗之万方程（Langevin Equation）**的线性形式，描述了在粘性介质中受随机力作用的粒子运动：

- 方程中的 $ \theta (\mu - x_t)dt $ 对应**摩擦力项**，驱动粒子速度向平衡均值 $ \mu $ 衰减（均值回归）；
- $ \sigma dW_t $ 对应**热噪声项**，即分子碰撞带来的随机冲击。

其物理意义是：粒子在粘性介质中运动时，一方面会因摩擦而减速、向平均速度回归，另一方面又会被周围分子的热运动随机推动。

### 0.3 数学性质与后续影响

OU 过程是唯一同时满足以下条件的非平凡随机过程：

- **高斯过程**：所有有限维分布都是正态分布
- **马尔可夫过程**：未来状态仅依赖当前状态
- **平稳过程**：统计特性不随时间变化

这些性质让它从物理领域迅速扩展到其他学科：

- **金融领域**：用于利率、汇率、商品价格的均值回归建模（如 Vasicek 利率模型就是 OU 过程的直接应用）
- **神经科学**：描述神经元膜电位的波动
- **时间序列分析**：构建平稳的均值回归序列模型

### 0.4 关键历史节点

| 时间 | 事件 |
|------|------|
| 1905年 | 爱因斯坦发表布朗运动理论，描述粒子位置扩散 |
| 1908年 | 朗之万提出含随机力的运动方程，开启随机动力学研究 |
| 1930年 | Ornstein & Uhlenbeck 发表论文，正式提出该过程 |
| 后续 | 被 Kolmogorov 等数学家完善，成为随机过程的经典模型 |


## 1. 📋 符号总表

| 符号 | 含义 | 典型值 |
|------|------|--------|
| $ x_t $ | 时刻 $ t $ 的噪声值（向量） | — |
| $ \theta $ | 均值回归速度 | 0.15 |
| $ \mu $ | 长期均值 | 0（通常） |
| $ \sigma $ | 波动率（噪声强度） | 0.2 |
| $ dW_t $ | 维纳过程增量 | $ \mathcal{N}(0, dt) $ |
| $ \Delta t $ | 离散时间步长 | 0.01 |


## 2. Ornstein-Uhlenbeck 过程的定义

**随机微分方程（SDE）形式**

$$
dx_t = \theta (\mu - x_t) dt + \sigma dW_t
$$

其中：
- $ \theta > 0 $：均值回归速度（strength of mean reversion）
- $ \mu $：长期均值（long-term mean）
- $ \sigma > 0 $：波动率（volatility）
- $ dW_t $：维纳过程增量（标准布朗运动）


## 3. SDE 的解析解推导

**Step 1: 齐次方程解**

考虑齐次方程 $ dx_t = -\theta x_t dt $（设 $ \mu = 0 $）：

$$
\frac{dx_t}{x_t} = -\theta dt \quad \Rightarrow \quad \ln x_t = -\theta t + C \quad \Rightarrow \quad x_t = x_0 e^{-\theta t}
$$

**Step 2: 常数变易法**

令 $ y_t = x_t e^{\theta t} $，则：

$$
dy_t = e^{\theta t} dx_t + \theta e^{\theta t} x_t dt
$$

代入原 SDE $ dx_t = \theta (\mu - x_t) dt + \sigma dW_t $：

$$
\begin{aligned}
dy_t &= e^{\theta t} [\theta (\mu - x_t) dt + \sigma dW_t] + \theta e^{\theta t} x_t dt \\
&= e^{\theta t} \theta \mu dt + e^{\theta t} \sigma dW_t
\end{aligned}
$$

**Step 3: 积分求解**

$$
y_t = y_0 + \theta \mu \int_0^t e^{\theta s} ds + \sigma \int_0^t e^{\theta s} dW_s
$$

计算积分 $ \int_0^t e^{\theta s} ds = \frac{e^{\theta t} - 1}{\theta} $，代入 $ y_0 = x_0 $：

$$
x_t e^{\theta t} = x_0 + \mu (e^{\theta t} - 1) + \sigma \int_0^t e^{\theta s} dW_s
$$

**Step 4: 最终解析解**

$$
x_t = x_0 e^{-\theta t} + \mu (1 - e^{-\theta t}) + \sigma \int_0^t e^{-\theta (t-s)} dW_s
$$


## 4. OU 过程的统计性质

### 4.1 期望

$$
\mathbb{E}[x_t] = x_0 e^{-\theta t} + \mu (1 - e^{-\theta t})
$$

**推导：**

由解析解：

$$
x_t = x_0 e^{-\theta t} + \mu (1 - e^{-\theta t}) + \sigma \int_0^t e^{-\theta (t-s)} dW_s
$$

对两边取期望。由于维纳积分 $ \int_0^t e^{-\theta (t-s)} dW_s $ 是鞅，其期望为 0：

$$
\mathbb{E}\left[ \sigma \int_0^t e^{-\theta (t-s)} dW_s \right] = 0
$$

因此：

$$
\mathbb{E}[x_t] = \mathbb{E}[x_0] e^{-\theta t} + \mu (1 - e^{-\theta t})
$$

若 $ x_0 $ 是确定性初始值，则 $ \mathbb{E}[x_0] = x_0 $，即得上述公式。

**极限：** $ \lim_{t \to \infty} \mathbb{E}[x_t] = \mu $

### 4.2 方差

$$
\text{Var}(x_t) = \frac{\sigma^2}{2\theta} (1 - e^{-2\theta t})
$$

**推导（利用 Itô 等距）：**

由解析解，确定性部分对方差无贡献，因此：

$$
\text{Var}(x_t) = \mathbb{E}\left[ \left( \sigma \int_0^t e^{-\theta (t-s)} dW_s \right)^2 \right]
$$

**Itô 等距（Itô Isometry）**：对于确定性被积函数 $ f(t) $，

$$
\mathbb{E}\left[ \left( \int_0^t f(s) dW_s \right)^2 \right] = \int_0^t f(s)^2 ds
$$

这是 Itô 积分的基本性质，来源于维纳过程的独立增量性和二次变差。

应用 Itô 等距，取 $ f(s) = \sigma e^{-\theta (t-s)} $：

$$
\begin{aligned}
\text{Var}(x_t) &= \int_0^t \sigma^2 e^{-2\theta (t-s)} ds \\
&= \sigma^2 \int_0^t e^{-2\theta u} du \quad (u = t-s) \\
&= \sigma^2 \cdot \frac{1 - e^{-2\theta t}}{2\theta} \\
&= \frac{\sigma^2}{2\theta} (1 - e^{-2\theta t})
\end{aligned}
$$

**极限：** $ \lim_{t \to \infty} \text{Var}(x_t) = \frac{\sigma^2}{2\theta} $

### 4.3 协方差（平稳状态）

$$
\text{Cov}(x_s, x_t) = \frac{\sigma^2}{2\theta} e^{-\theta |t-s|}, \quad s < t
$$

**推导：**

对于 $ s < t $，利用解析解和 Itô 等距可得上述指数衰减的相关性。这表明 OU 过程的记忆随时间指数衰减，是短期记忆过程。


## 5. 离散化（用于数值实现）

### 5.1 Euler-Maruyama 离散化

$$
x_{t+\Delta t} = x_t + \theta (\mu - x_t) \Delta t + \sigma \sqrt{\Delta t} \cdot \mathcal{N}(0, 1)
$$

### 5.2 简化形式（设 $ \mu = 0 $）

$$
x_{t+\Delta t} = x_t (1 - \theta \Delta t) + \sigma \sqrt{\Delta t} \cdot \mathcal{N}(0, 1)
$$

### 5.3 向量形式（多维度，各维度独立）

$$
\mathbf{x}_{t+\Delta t} = \mathbf{x}_t + \theta (\boldsymbol{\mu} - \mathbf{x}_t) \Delta t + \sigma \sqrt{\Delta t} \cdot \boldsymbol{\varepsilon}, \quad \boldsymbol{\varepsilon} \sim \mathcal{N}(\mathbf{0}, \mathbf{I})
$$


## 6. Python 代码实现

```python
import numpy as np

class OrnsteinUhlenbeckNoise:
    """
    Ornstein-Uhlenbeck 噪声生成器
    用于 DDPG / 强化学习 动作空间探索
    """
    def __init__(self, action_dim, theta=0.15, dt=1e-2, sigma=0.2, mu=0.0):
        self.action_dim = action_dim    # 动作维度
        self.theta = theta              # 回归速度
        self.dt = dt                    # 时间步长
        self.sigma = sigma              # 波动强度
        self.mu = mu * np.ones(action_dim)  # 长期均值（向量）
        self.reset()

    def reset(self):
        """重置噪声状态"""
        self.state = self.mu.copy()

    def sample(self):
        """生成下一个噪声值（向量）"""
        # Euler-Maruyama 离散化
        dx = self.theta * (self.mu - self.state) * self.dt + \
             self.sigma * np.sqrt(self.dt) * np.random.randn(self.action_dim)
        self.state += dx
        return self.state

# 使用示例
if __name__ == "__main__":
    ou = OrnsteinUhlenbeckNoise(action_dim=6, theta=0.15, dt=0.01, sigma=0.2)
    for _ in range(1000):
        noise = ou.sample()
```


## 7. 数值稳定条件

为保证数值稳定，需满足：

$$
0 < \theta \Delta t < 2
$$

典型取值：$ \theta = 0.15 $，$ \Delta t = 0.01 $，则 $ \theta \Delta t = 0.0015 \ll 1 $。


## 8. 与高斯白噪声的对比

| 维度 | 高斯白噪声 | OU 噪声 |
|------|-----------|---------|
| 时间相关性 | 无（独立同分布） | 有（指数衰减） |
| 均值 | 0 | $ \mu $（可设定） |
| 方差 | 常数 $ \sigma^2 $ | 有限值 $ \sigma^2/(2\theta) $ |
| 适用场景 | 无惯性系统 | 物理控制系统（机器人） |


## 9. 在强化学习中的应用

### 9.1 DDPG 中的使用

DDPG 原始论文（Lillicrap et al., 2015）使用 OU 噪声进行动作空间探索：

$$
a_t = \mu_\theta(s_t) + \mathcal{N}_t^{\text{OU}}
$$

OU 噪声提供**时间上相关的探索**，使连续动作变化更平滑，符合物理系统的惯性特性。

### 9.2 ERL 中的使用

原始 ERL（Khadka & Tumer, 2018）中：

- **种群 actor**：通过参数空间噪声（权重扰动）探索
- **RL actor**（rl_actor）：通过 OU 噪声在动作空间探索

### 9.3 CEM-RL 中的发现

CEM-RL（Pourchot & Sigaud, 2019）论文 Appendix C 指出：

- 在 CEM-TD3 中，OU 动作噪声**并非必需**
- CEM 的参数空间探索已足够，添加动作噪声甚至可能降低性能
- ERL 需要动作噪声的原因是：ERL 的 GA 种群易收敛到单一个体，多样性不足


## 10. 参数选择建议

| 参数 | 典型值 | 调参建议 |
|------|--------|----------|
| $ \theta $（回归速度） | 0.15 | 越大，噪声回归均值越快，探索持续时间越短 |
| $ \sigma $（波动强度） | 0.2 | 越大，探索幅度越大 |
| $ \Delta t $（时间步长） | 0.01 | 通常与环境交互步长一致 |
| $ \mu $（长期均值） | 0 | 通常设为 0，噪声围绕 0 均值回归 |


## 11. 总结

- OU 过程是一种**均值回归**随机过程，生成时间上相关的噪声
- 在 RL 中用于**动作空间探索**，使连续动作变化平滑
- DDPG 论文首次引入，ERL 中 rl_actor 使用
- CEM-RL 论文发现：参数空间探索充分时，OU 噪声非必需
- 与高斯白噪声相比，OU 噪声具有**时间相关性**和**有界方差**两大特性


📄 本报告基于 OU 过程数学定义、DDPG 原始论文 (Lillicrap et al., 2015)、ERL (Khadka & Tumer, 2018) 和 CEM-RL (Pourchot & Sigaud, 2019) 整理。包含完整 SDE 解析解推导、统计性质、离散化、代码实现及强化学习应用分析。