---
description: MathJax 支持的 LaTeX 能力速查（分段、矩阵、偏导等）
---
# 数学公式能力速查

本页验证 Memoria 预览对常见 LaTeX 结构的支持。行内用 `$...$`，块级用 `$$...$$`。

## 分段函数（cases）

$$
f(x) = \begin{cases}
x^2 & x \geq 0 \\
-x & x < 0
\end{cases}
$$

## 矩阵

$$
\mathbf{A} = \begin{bmatrix}
1 & 2 & 3 \\
4 & 5 & 6 \\
7 & 8 & 9
\end{bmatrix},
\quad
\det(\mathbf{A}) = \sum_{\sigma \in S_n} \mathrm{sgn}(\sigma) \prod_i a_{i,\sigma(i)}
$$

## 偏导与[[梯度]]

$$
\frac{\partial L}{\partial w} = \frac{1}{N}\sum_{i=1}^{N} \frac{\partial \ell_i}{\partial w},
\qquad
\nabla_\theta J(\theta) = \mathbb{E}_{\pi_\theta}\!\left[\nabla \log \pi_\theta(a|s)\, Q^{\pi_\theta}(s,a)\right]
$$

## 多行对齐（align）

$$
\begin{align}
V^\pi(s) &= \mathbb{E}_\pi[R_{t+1} + \gamma V^\pi(S_{t+1}) \mid S_t = s] \\
Q^*(s,a) &= \mathbb{E}\!\left[R + \gamma \max_{a'} Q^*(S', a') \mid S=s, A=a\right]
\end{align}
$$

以上结构均由 **MathJax 3 tex-chtml-full** 渲染，与标准 LaTeX 数学环境兼容。
