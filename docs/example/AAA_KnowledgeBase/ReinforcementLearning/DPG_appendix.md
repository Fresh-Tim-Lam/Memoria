
式子
$$
J_2(\theta) = \mathbb{E}_{s\sim \rho^{\pi_\theta},a\sim \pi_\theta}\big[R(s,a)\big]
$$
**看上去没有时序求和，本质已经把无穷时序全部封装进 $\boldsymbol{\rho^{\pi_\theta}(s)}$（折扣平稳状态分布 / 占用度量 occupancy measure）里了。**

## 1.1 先写出标准时序目标（大家熟悉的形式）
带折扣的累积回报：
$$
V^\pi(s_0)=\mathbb{E}_\pi\left[\sum_{t=0}^{\infty}\gamma^t R(s_t,a_t)\,\bigg|\,s_0\right]
$$
定义一：对初始分布 $d_0(s_0)$ 求期望
$$
J_1=\mathbb{E}_{s_0\sim d_0}V^\pi(s_0)
=\mathbb{E}\left[\sum_{t=0}^\infty \gamma^t R(s_t,a_t)\right]
$$

## 1.2 $\rho^{\pi}(s)$ 到底是什么（关键！）
**折扣占用度量（discounted occupancy measure）定义：**
$$
\rho^{\pi}(s) \triangleq \sum_{t=0}^{\infty}\gamma^t \mathbb{P}(s_t=s\mid\pi,d_0)
$$
含义：
从初始分布 $d_0$ 出发，遵循策略 $\pi$，**所有时刻带折扣权重下访问状态 $s$ 的总概率**。
它天然已经对 $t=0,1,2,\dots,\infty$ 做了求和。

把期望展开交换求和与期望顺序：
$$
\begin{aligned}
J_1
&=\mathbb{E}\left[\sum_{t=0}^\infty \gamma^t R(s_t,a_t)\right]\\
&=\sum_{t=0}^\infty \gamma^t \iint \mathbb{P}(s_t=s)\,\pi(a|s)\,R(s,a)\,da\,ds\\
&=\iint \underbrace{\left(\sum_{t=0}^\infty\gamma^t\mathbb{P}(s_t=s)\right)}_{\rho^\pi(s)} \pi(a|s)R(s,a)\,da\,ds\\
&=\mathbb{E}_{s\sim\rho^\pi,a\sim\pi(\cdot|s)}[R(s,a)] = J_2
\end{aligned}
$$







---

## 2.1 问题的核心：算子范数的定义

### 2.1.1 什么是 \(\|\cdot\|_\infty\) 范数？

对于作用于函数空间 \(\mathcal{B}(\mathcal{S})\)（有界实值函数）上的线性算子 \(T\)，其**诱导上确界范数**定义为：

\[
\|T\|_\infty \triangleq \sup_{\|f\|_\infty \leq 1} \|T f\|_\infty
\]

其中对函数 \(f: \mathcal{S} \to \mathbb{R}\)，\(\|f\|_\infty = \sup_{s \in \mathcal{S}} |f(s)|\)。

**通俗理解**：\(\|T\|_\infty\) 表示算子 \(T\) 能将任意有界函数放大多少倍（最坏情况）。



## 2.2 证明 \(\|\mathcal{P}^{\mu_\theta}\|_\infty \leq 1\)

### 2.2.1 转移算子的定义

\[
(\mathcal{P}^{\mu_\theta} f)(s) = \int_{\mathcal{S}} P(s' \mid s, \mu_\theta(s)) f(s') \, ds'
\]

即：从状态 \(s\) 出发，按确定性策略 \(\mu_\theta\) 选择动作，转移到下一状态后，取函数 \(f\) 在该状态的期望值。



### 2.2.2 范数上界

对于**任意**有界函数 \(f\)（\(\|f\|_\infty \leq 1\)），在**任意**状态 \(s\) 下：

\[
|(\mathcal{P}^{\mu_\theta} f)(s)| = \left| \int_{\mathcal{S}} P(s' \mid s, \mu_\theta(s)) f(s') \, ds' \right|
\]

利用绝对值不等式（三角不等式）：

\[
|(\mathcal{P}^{\mu_\theta} f)(s)| \leq \int_{\mathcal{S}} P(s' \mid s, \mu_\theta(s)) \, |f(s')| \, ds'
\]

由于 \(|f(s')| \leq \|f\|_\infty\) 对所有 \(s'\) 成立：

\[
|(\mathcal{P}^{\mu_\theta} f)(s)| \leq \|f\|_\infty \int_{\mathcal{S}} P(s' \mid s, \mu_\theta(s)) \, ds'
\]

因为 \(\int_{\mathcal{S}} P(s' \mid s, \mu_\theta(s)) \, ds' = 1\)（概率测度归一化）：

\[
|(\mathcal{P}^{\mu_\theta} f)(s)| \leq \|f\|_\infty
\]

**对所有 \(s\) 取上确界**：

\[
\|\mathcal{P}^{\mu_\theta} f\|_\infty = \sup_s |(\mathcal{P}^{\mu_\theta} f)(s)| \leq \|f\|_\infty
\]

**对所有 \(\|f\|_\infty \leq 1\) 的函数取上确界**：

\[
\|\mathcal{P}^{\mu_\theta}\|_\infty = \sup_{\|f\|_\infty \leq 1} \|\mathcal{P}^{\mu_\theta} f\|_\infty \leq 1
\]

因此：

\[
\boxed{\|\mathcal{P}^{\mu_\theta}\|_\infty \leq 1} \tag{1}
\]


## 2.3 证明 \(\|\gamma \mathcal{P}^{\mu_\theta}\|_\infty \leq \gamma < 1\)

### 2.3.1 缩放性质

对于任意线性算子 \(T\) 和标量 \(c\)：

\[
\|c T\|_\infty = |c| \cdot \|T\|_\infty
\]

这个性质来源于范数的齐次性：

\[
\|c T\|_\infty = \sup_{\|f\|_\infty \leq 1} \|c T f\|_\infty = \sup_{\|f\|_\infty \leq 1} |c| \|T f\|_\infty = |c| \|T\|_\infty
\]


### 2.3.2 应用到我们的算子

令 \(T = \mathcal{P}^{\mu_\theta}\)，标量 \(c = \gamma\)。

\[
\|\gamma \mathcal{P}^{\mu_\theta}\|_\infty = \gamma \|\mathcal{P}^{\mu_\theta}\|_\infty
\]

代入 (1)：

\[
\|\gamma \mathcal{P}^{\mu_\theta}\|_\infty \leq \gamma \cdot 1 = \gamma
\]

由于 \(\gamma \in [0, 1)\)（折扣因子的定义）：

\[
\boxed{\|\gamma \mathcal{P}^{\mu_\theta}\|_\infty \leq \gamma < 1} \tag{2}
\]

---


问的是：**为什么满足 \(\|T\| < 1\) 后，\((I - T)^{-1}\) 就等于 Neumann 级数 \(\sum_{k=0}^{\infty} T^k\)？**

这本质上是一个**泛函分析**中的经典结论。下面我用纯代数推导和几何直观两种方式来解释。

## 3.1 代数证明（最严谨）

### 3.1.1 定义部分和

令 Neumann 级数的前 \(n+1\) 项部分和为：

\[
S_n \triangleq I + T + T^2 + \cdots + T^n = \sum_{k=0}^{n} T^k
\]

### 3.1.2 计算 \((I - T)S_n\)

展开：

\[
(I - T)S_n = (I - T)(I + T + T^2 + \cdots + T^n)
\]

逐项相乘：

\[
= I + T + T^2 + \cdots + T^n - T - T^2 - T^3 - \cdots - T^{n+1}
\]

中间的 \(T, T^2, \ldots, T^n\) 全部抵消，只剩下：

\[
(I - T)S_n = I - T^{n+1} \tag{1}
\]



### 3.1.3 取极限 \(n \to \infty\)

如果 \(\|T\| < 1\)，那么：

\[
\|T^{n+1}\| \le \|T\|^{n+1} \xrightarrow{n \to \infty} 0
\]

因此 \(T^{n+1} \to 0\)（零算子）。于是：

\[
\lim_{n \to \infty} (I - T)S_n = I - \lim_{n \to \infty} T^{n+1} = I
\]

即：

\[
(I - T) \lim_{n \to \infty} S_n = I
\]



### 3.1.4 同样地，验证右逆

同理：

\[
S_n(I - T) = I - T^{n+1}
\]

取极限：

\[
\lim_{n \to \infty} S_n (I - T) = I
\]

因此 \(\lim_{n \to \infty} S_n\) 既是 \(I - T\) 的左逆，也是右逆。



### 3.1.5 结论

\[
\boxed{(I - T)^{-1} = \sum_{k=0}^{\infty} T^k}
\]

**证毕。**



## 3.2 为什么 \(\|T\| < 1\) 保证了 \(T^{n+1} \to 0\)？

这是算子范数的一个重要性质：

\[
\|T^{n+1}\| \le \|T\|^{n+1}
\]

如果 \(\|T\| < 1\)，右边的 \(\|T\|^{n+1} \to 0\)，所以 \(\|T^{n+1}\| \to 0\)。

在 Banach 空间中，范数趋向于 0 意味着算子本身趋向于零算子。

> **类比**：实数中，如果 \(|x| < 1\)，那么 \(x^n \to 0\)。\(\|T\| < 1\) 就是这个条件的算子版本。

---
