# 范德蒙德行列式证明

$$
V_n=
\begin{vmatrix}
1 & z_0 & z_0^2 & \dots & z_0^{n-1}\
1 & z_1 & z_1^2 & \dots & z_1^{n-1}\
1 & z_2 & z_2^2 & \dots & z_2^{n-1}\
\vdots & \vdots & \vdots & &\vdots\
1 & z_{n-1} & z_{n-1}^2 & \dots & z_{n-1}^{n-1}
\end{vmatrix}
=\prod_{0\le i<j\le n-1}(z_j-z_i)
$$

用**数学归纳法**证明。

### 基例 $(n=2)$

$$
V_2=
\begin{vmatrix}
1 & z_0\
1 & z_1
\end{vmatrix}
=z_1-z_0
$$
乘积公式：$\displaystyle\prod_{0\le i<j\le 1}(z_j-z_i)=z_1-z_0$，等式成立。

---

## 归纳步骤

假设对于 $(n=k)$，$k$ 阶范德蒙德行列式成立：
$$
V_k=\prod_{0\le i<j\le k-1}(z_j-z_i)
$$

现在看 $(n=k)+1$ 阶 $V_{k+1}$：
$$
V_{k+1}=
\begin{vmatrix}
1 & z_0 & z_0^2 & \dots & z_0^{k}\
1 & z_1 & z_1^2 & \dots & z_1^{k}\
\vdots&\vdots&\vdots&&\vdots\
1 & z_{k} & z_{k}^2 & \dots & z_{k}^{k}
\end{vmatrix}
$$

**行列式行变换：第 $i$ 行减去第 $0$ 行乘以 $1$**（$i=k,k-1,\dots,1$，从下往上做，避免覆盖）

> 
> 行列式性质：某行减去另一行倍数，行列式值不变。

$$
V_{k+1}=
\begin{vmatrix}
1 & z_0 & z_0^2 & \dots & z_0^{k}\
0 & z_1-z_0 & z_1^2-z_0z_1 & \dots & z_1^k-z_0 z_1^{k-1}\
0 & z_2-z_0 & z_2^2-z_0z_2 & \dots & z_2^k-z_0 z_2^{k-1}\
\vdots&\vdots&\vdots&&\vdots\
0 & z_k-z_0 & z_k^2-z_0 z_k & \dots & z_k^k-z_0 z_k^{k-1}
\end{vmatrix}
$$

按第一列展开，只剩下左上角 $1$ 乘右下角子式：
$$
V_{k+1}=
\begin{vmatrix}
z_1-z_0 & z_1(z_1-z_0) & \dots & z_1^{k-1}(z_1-z_0)\
z_2-z_0 & z_2(z_2-z_0) & \dots & z_2^{k-1}(z_2-z_0)\
\vdots & \vdots & & \vdots\
z_k-z_0 & z_k(z_k-z_0) & \dots & z_k^{k-1}(z_k-z_0)
\end{vmatrix}
$$

每一行提取公因子 $(z_j-z_0),\ j=1,2,\dots,k$：
$$
V_{k+1}=\left[\prod_{j=1}^k (z_j-z_0)\right]
\cdot
\begin{vmatrix}
1 & z_1 & z_1^2 & \dots & z_1^{k-1}\
1 & z_2 & z_2^2 & \dots & z_2^{k-1}\
\vdots & \vdots & &\vdots\
1 & z_k & z_k^2 & \dots & z_k^{k-1}
\end{vmatrix}
$$

右下角就是 $k$ 阶范德蒙德行列式，对变量 $z_1,z_2,\dots,z_k$。
由归纳假设：
$$
\begin{vmatrix}
1 & z_1 & \dots & z_1^{k-1}\
\vdots&&&\vdots\
1 & z_k & \dots & z_k^{k-1}
\end{vmatrix}
=\prod_{1\le i<j\le k}(z_j-z_i)
$$

代入：
$$
V_{k+1}=
\Big(\prod_{j=1}^k(z_j-z_0)\Big)\cdot \prod_{1\le i<j\le k}(z_j-z_i)
=\prod_{0\le i<j\le k}(z_j-z_i)
$$

归纳成立。

✅ 所以对任意 $n\ge 2$
$$
\boldsymbol{
\det(V_n)=\prod_{0\le i<j\le n-1}(z_j-z_i)
}
$$


