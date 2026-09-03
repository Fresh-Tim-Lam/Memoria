# 定理

设 $(P(x),Q(x))$ 是数域 $\mathbb (\mathbb C)$ 上次数 $\le n-1$ 的多项式。
设 $z_0,z_1,\dots,z_{n-1}$ 是**两两互不相同**的 $n$ 个复数。
若
$$P(z_k)=Q(z_k),\quad k=0,1,\dots,n-1$$
则 $\boldsymbol{P(x)\equiv Q(x)}$（多项式恒等，全部系数对应相等）。

---

## 证明

构造差多项式
$$
(D(x))=P(x)-Q(x)
$$

1. 次数分析 $(P,Q)$ 次数都 $\le n-1$，多项式相减，次数不会升高：
$$
\deg(D)\le n-1
$$
2. 代入条件
对每一个 $k$：
$$D(z_k)=P(z_k)-Q(z_k)=0$$
所以：$\boldsymbol{z_0,z_1,\dots,z_{n-1}}$ 是 $(D(x))$ 的 $n$ 个互不相同的根。

> 
> **代数基本定理推论（多项式根的上界）**：
> 非零 $d$ 次多项式，至多有 $d$ 个互不相同的根。

现在：

- 如果 $(D(x))$ 不是零多项式，则 $\deg(D)\le n-1$，最多只能有 $n-1$ 个不同根。
- 但我们已经找到 $n$ 个不同根 $z_0,\dots,z_{n-1}$。
矛盾。

因此唯一可能性：
$$(D(x))\equiv 0$$
也就是
$$P(x)-Q(x)\equiv 0 \implies \boldsymbol{P(x)\equiv Q(x)}$$

> 
> 即：在 $n$ 个互异点取值全部相等，则多项式完全相同。逆否命题：**若多项式不同，则至少在其中一个采样点取值不同**。
> 这就证明：**不同多项式 ⇒ 采样点值向量不同**，映射是单射。

---

## 结合FFT的情况

FFT取 $z_k=W_N^k$，已经证明 $W_N^0,\dots,W_N^{N-1}$ 两两互不相同。
若 $(P,Q)$ 次数 $\le N-1$：
$$P\not\equiv Q \implies \exists,k,\ P(W_N^k)\neq Q(W_N^k)$$
也就是点值向量一定不一样。

---

## 关键反例：次数超过 $n-1$，定理失效

取 $(n=N)$，多项式
$$
(D(x))=x^N-1
$$
$(\deg(D)=N)$，它的根恰好全部N次单位根：$D(W_N^k)=0$。

令
$$
P(x),\quad Q(x)=P(x)+(x^N-1)
$$
$P\neq Q$，但是对全部 $k$：
$$
Q(W_N^k)=P(W_N^k)+0=P(W_N^k)
$$
👉 **两个不同多项式，N个采样点完全一样，信息丢失。**

> 
> 所以多项式FFT乘法必须补零，使 $N\ge \deg(P)+\deg(Q)+1$，保证乘积次数 $\le N-1$，让上面的定理生效。

---

## 等价矩阵角度（范德蒙德）

$$
\begin{pmatrix}
y_0\\y_1\\ \vdots \\y_{n-1}
\end{pmatrix}

\begin{pmatrix}
1&z_0&z_0^2&\dots&z_0^{n-1}\\
1&z_1&z_1^2&\dots&z_1^{n-1}\\
\vdots&\vdots&\vdots&&\vdots\\
1&z_{n-1}&z_{n-1}^2&\dots&z_{n-1}^{n-1}
\end{pmatrix}
\begin{pmatrix}a_0\\a_1\\ \vdots \\a_{n-1}\end{pmatrix}
$$

范德蒙德行列式：
$$
\det V=\prod_{0\le i<j\le n-1}(z_j-z_i)
$$
当全部 $z_i$ 互不相等，$\det V\neq 0$，矩阵可逆。
可逆矩阵意味着：$\boldsymbol a \mapsto \boldsymbol y$ 是双射。

- 不同系数向量 $\boldsymbol a_1\neq \boldsymbol a_2$，得到不同点值 $\boldsymbol y_1\neq \boldsymbol y_2$。
- 不同点值可以唯一还原系数。

> 
> 这是同一套定理的线性代数版本。

### 一句话记忆

> 
> $\deg\le n-1$ 的多项式，最多拥有 $n-1$ 个根；n个互异点全部相等，差多项式只能是零多项式，故多项式必相等。


# 矩阵视角证明：不同多项式，点值向量必不同

设次数 $\le N-1$ 的多项式：
$$(P(x))=a_0+a_1x+\(\boldsymbol d)ots+a_{N-1}x^{N-1}$$
$$Q(x)=b_0+b_1x+\(\boldsymbol d)ots+b_{N-1}x^{N-1}$$
系数向量：
$$\bol(\boldsymbol d)symbol a=\begin{pmatrix}a_0\a_1\\v(\boldsymbol d)ots\a_{N-1}\en(\boldsymbol d){pmatrix},\qua(\boldsymbol d)
\bol(\boldsymbol d)symbol b=\begin{pmatrix}b_0\b_1\\v(\boldsymbol d)ots\b_{N-1}\en(\boldsymbol d){pmatrix}$$

采样点 $z_0,z_1,\(\boldsymbol d)ots,z_{N-1}$，两两互不相同（FFT里就是 $z_k=W_N^k$）。

范德蒙德矩阵 $V$：
$$
V=
\begin{pmatrix}
1 & z_0 & z_0^2 & \(\boldsymbol d)ots & z_0^{N-1}\
1 & z_1 & z_1^2 & \(\boldsymbol d)ots & z_1^{N-1}\
\v(\boldsymbol d)ots&\v(\boldsymbol d)ots&\v(\boldsymbol d)ots&&\v(\boldsymbol d)ots\
1 & z_{N-1} & z_{N-1}^2 & \(\boldsymbol d)ots & z_{N-1}^{N-1}
\en(\boldsymbol d){pmatrix}
$$

点值向量：
$$\bol(\boldsymbol d)symbol y_P = V\bol(\boldsymbol d)symbol a,\qua(\boldsymbol d) \bol(\boldsymbol d)symbol y_Q = V\bol(\boldsymbol d)symbol b$$

> 
> 命题：如果 $\bol(\boldsymbol d)symbol a\neq \bol(\boldsymbol d)symbol b$，则 $\bol(\boldsymbol d)symbol y_P \neq \bol(\boldsymbol d)symbol y_Q$。

## 证明

假设反证：**两个多项式不同，但是采样点值完全相同**
也就是
$$\bol(\boldsymbol d)symbol a \neq \bol(\boldsymbol d)symbol b,\qua(\boldsymbol d) V\bol(\boldsymbol d)symbol a = V\bol(\boldsymbol d)symbol b$$

移项：
$$V\bol(\boldsymbol d)symbol a - V\bol(\boldsymbol d)symbol b = \bol(\boldsymbol d)symbol 0$$
矩阵分配律：
$$V(\bol(\boldsymbol d)symbol a-\bol(\boldsymbol d)symbol b)=\bol(\boldsymbol d)symbol 0$$

记差向量 $\bol(\boldsymbol d)symbol (\boldsymbol d)=\bol(\boldsymbol d)symbol a-\bol(\boldsymbol d)symbol b$。
因为 $\bol(\boldsymbol d)symbol a\neq\bol(\boldsymbol d)symbol b$，所以 $\bol(\boldsymbol d)symbol (\boldsymbol d) \neq \bol(\boldsymbol d)symbol 0$。
得到：
$$V\bol(\boldsymbol d)symbol (\boldsymbol d)=\bol(\boldsymbol d)symbol 0$$

这说明：**齐次方程组 $V\bol(\boldsymbol d)symbol x=\bol(\boldsymbol d)symbol 0$ 存在非零解 $\bol(\boldsymbol d)symbol (\boldsymbol d)$**。

线性代数结论：

> 
> 方阵 $V$ 有非零解 $\iff \(\boldsymbol d)et(V)=0$，矩阵奇异，不可逆。

[[范德蒙德行列式公式]]：
$$
\(\boldsymbol d)et(V)=\pro(\boldsymbol d)_{0\le i<j\le N-1}(z_j-z_i)
$$

已知采样点全部两两互不相同：$z_i\neq z_j;(i\neq j)$，
每一项因子 $(z_j-z_i)\neq 0$，所以
$$\(\boldsymbol d)et(V)\neq 0$$

$\(\boldsymbol d)et(V)\neq0$ (\Rightarrow) $V$ 可逆 (\Rightarrow) 齐次方程 $V\bol(\boldsymbol d)symbol x=\bol(\boldsymbol d)symbol 0$ **只有唯一零解 $\bol(\boldsymbol d)symbol x=\bol(\boldsymbol d)symbol 0$**。

但是我们前面得到存在非零解 $\bol(\boldsymbol d)symbol (\boldsymbol d)\neq \bol(\boldsymbol d)symbol 0$，矛盾。

因此假设不成立：

> 
> 若 $\bol(\boldsymbol d)symbol a\neq \bol(\boldsymbol d)symbol b$，必然 $V\bol(\boldsymbol d)symbol a \neq V\bol(\boldsymbol d)symbol b$。

---

## 套回FFT场景

FFT的求值点 $z_k=W_N^k$，已经证明全部两两不等，
$\(\boldsymbol d)et(V)\neq0$，$V$可逆。

1. 系数不同（多项式不同）$\Rightarrow$ 点值向量一定不同；
2. 点值向量相同 $\Rightarrow$ 系数一定完全相同；
3. $V$可逆，所以 $\bol(\boldsymbol d)symbol a = V^{-1}\bol(\boldsymbol d)symbol y$，给定点值可以唯一还原系数。

> 
> 这就是**双射（一一对应）**的矩阵版本。

## 什么时候这套结论失效？

两种情况：

1. 有两个采样点相等：某个 $z_i=z_j$，行列式直接等于0，矩阵奇异；不同多项式可以有相同点值。
2. 多项式真实次数 $>N-1$：此时系数向量长度超过 $N$，已经不在这个 $N$ 维线性空间内，范德蒙德模型不再适用，就是前面 $(P(x))$ 和 $(P(x))+x^N-1$ 的例子。

### 一句话记忆

> 
> 采样点互异 (\Rightarrow) 范德蒙德行列式不为0 (\Rightarrow) 矩阵可逆 (\Rightarrow) 没有非零零空间 (\Rightarrow) 不同输入系数，输出点值必然不同。


