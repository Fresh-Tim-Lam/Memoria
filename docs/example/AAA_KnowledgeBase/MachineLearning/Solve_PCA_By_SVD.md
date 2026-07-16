

## 第一层：PCA要解决什么问题

**【条件】**
- 有 $ n $ 个样本，每个样本 $ d $ 维，组成数据矩阵 $ X $（$ n \times d $）
- 想降到 $ k $ 维（$ k \ll d $），同时尽可能保留原始数据的信息
- “信息”用方差来度量：方差大 → 数据分散 → 信息丰富；方差小 → 数据集中 → 信息冗余

**【推导】**
要把数据投影到一个方向 $ w $ 上，投影后的数据是 $ y = Xw $。投影后的方差是：
$$
\text{Var}(y) = \frac{1}{n-1} y^T y = w^T \left( \frac{1}{n-1} X^T X \right) w = w^T \Sigma w
$$
所以PCA要最大化 $ w^T \Sigma w $，同时要求 $ w $ 是单位向量（$ w^T w = 1 $）。

**【结论】**
PCA的优化问题就是：
$$
\max_w \quad w^T \Sigma w \quad \text{s.t.} \quad w^T w = 1
$$


## 第二层：用拉格朗日乘子法求解PCA

**【条件】**
优化问题：$ \max_w w^T \Sigma w $，约束 $ w^T w = 1 $

**【推导】**
构造拉格朗日函数：
$$
\mathcal{L}(w, \lambda) = w^T \Sigma w - \lambda (w^T w - 1)
$$
对 $ w $ 求偏导并令为0：
$$
\frac{\partial \mathcal{L}}{\partial w} = 2\Sigma w - 2\lambda w = 0
$$
$$
\Sigma w = \lambda w
$$

**【结论】**
- $ w $ 是协方差矩阵 $ \Sigma $ 的**特征向量**
- $ \lambda $ 是对应的**特征值**
- 代入目标函数：$ w^T \Sigma w = w^T (\lambda w) = \lambda $，所以特征值 $ \lambda $ 就是投影后的方差
- 要选前 $ k $ 个最大特征值对应的特征向量作为投影方向


## 第三层：直接做PCA的计算瓶颈

**【条件】**
- 协方差矩阵 $ \Sigma = \frac{1}{n-1} X_c^T X_c $，大小是 $ d \times d $
- 需要对它做特征分解，得到特征向量和特征值

**【推导】**
当特征维度 $ d $ 很大时（如图像：$ d = 10000 $）：
- $ \Sigma $ 有 $ 10000 \times 10000 = 1 $ 亿个元素
- 特征分解复杂度 $ O(d^3) = O(10^{12}) $，内存和时间都不可接受

**【结论】**
直接对 $ d \times d $ 的协方差矩阵做特征分解，在 $ d $ 很大时**不可行**。


## 第四层：引入SVD——改变分解对象

**【条件】**
SVD可以对任意矩阵 $ X_c $（$ n \times d $）分解为：
$$
X_c = U \Sigma_{svd} V^T
$$

**【推导】**
计算 $ X_c^T X_c $：
$$
X_c^T X_c = (U \Sigma_{svd} V^T)^T (U \Sigma_{svd} V^T) = V \Sigma_{svd}^T U^T U \Sigma_{svd} V^T = V \Sigma_{svd}^T \Sigma_{svd} V^T
$$
因为 $ U^T U = I $。

所以：
$$
X_c^T X_c = V \begin{bmatrix} \sigma_1^2 & & \\ & \ddots & \\ & & \sigma_d^2 \end{bmatrix} V^T
$$

**【结论】**
- 协方差矩阵 $ \Sigma = \frac{1}{n-1} X_c^T X_c $ 的特征向量 = **右奇异矩阵 $ V $ 的列向量**
- 协方差矩阵的特征值 = **$ \sigma_i^2 / (n-1) $**
- **PCA要找的 $ w $ = SVD的右奇异向量 $ V $**


## 第五层：SVD仍然要面对 $ d \times d $

**【条件】**
上面推导出 $ V $ 是 $ X_c^T X_c $ 的特征向量。

**【推导】**
$ X_c^T X_c $ 的大小是 $ d \times d $，如果直接求 $ V $，还是要分解 $ d \times d $ 的矩阵，问题依然没有解决。

**【结论】**
SVD如果直接从 $ X_c^T X_c $ 出发求 $ V $，同样面临 $ d \times d $ 的困难。


## 第六层：SVD的“曲线救国”——从 $ U $ 出发

**【条件】**
- 除了 $ X_c^T X_c $（$ d \times d $），还可以计算 $ X_c X_c^T $（$ n \times n $）
- 当 $ n \ll d $ 时，$ n \times n $ 远小于 $ d \times d $

**【推导】**
从 $ X_c = U \Sigma_{svd} V^T $ 出发，计算 $ X_c X_c^T $：
$$
X_c X_c^T = U \Sigma_{svd} V^T V \Sigma_{svd}^T U^T = U \Sigma_{svd} \Sigma_{svd}^T U^T
$$
因为 $ V^T V = I $。

所以：
$$
X_c X_c^T = U \begin{bmatrix} \sigma_1^2 & & \\ & \ddots & \\ & & \sigma_n^2 \end{bmatrix} U^T
$$

**【结论】**
- $ U $ 是 $ X_c X_c^T $（$ n \times n $）的特征向量
- **$ U $ 可以在 $ n \times n $ 的规模上直接求得，不需要碰 $ d \times d $**


## 第七层：从 $ U $ 反推 $ V $（最终关卡）

**【条件】**
- 已有：$ U $（从 $ n \times n $ 的 $ X_c X_c^T $ 分解得到）
- 已有：$ \Sigma_{svd} $（从 $ X_c X_c^T $ 的特征值开方得到，即 $ \sigma_i $）
- 已有：$ X_c = U \Sigma_{svd} V^T $

**【推导】**
从 $ X_c = U \Sigma V^T $ 两边同时左乘 $ U^T $：
$$
U^T X_c = U^T U \Sigma V^T = \Sigma V^T
$$
得到：
$$
U^T X_c = \Sigma V^T
$$

两边同时取转置：
$$
(U^T X_c)^T = (\Sigma V^T)^T
$$
$$
X_c^T U = V \Sigma^T
$$
因为 $ \Sigma $ 是对角矩阵，$ \Sigma^T = \Sigma $，所以：
$$
X_c^T U = V \Sigma
$$

两边同时右乘 $ \Sigma^{-1} $：
$$
X_c^T U \Sigma^{-1} = V \Sigma \Sigma^{-1} = V
$$

**【结论】**
$$
\boxed{V = X_c^T U \Sigma^{-1}}
$$
只要算出 $ U $（通过分解 $ n \times n $），再代入公式，就能得到 $ V $（即PCA的投影方向 $ w $）。


## 第八层：SVD加速PCA的完整逻辑链

| 步骤 | 操作 | 矩阵大小 | 复杂度 |
| :--- | :--- | :--- | :--- |
| **1** | 中心化 $ X \to X_c $ | $ n \times d $ | $ O(nd) $ |
| **2** | 构造小矩阵 $ M = X_c X_c^T $ | $ n \times n $ | $ O(n^2 d) $ |
| **3** | 对 $ M $ 做特征分解，得到 $ U $ | $ n \times n $ | $ O(n^3) $ |
| **4** | 从 $ U $ 反推 $ V = X_c^T U \Sigma^{-1} $ | — | $ O(nd \cdot n) $ |
| **5** | 取 $ V $ 的前 $ k $ 列作为投影方向 $ W $ | — | — |
| **6** | 降维 $ Y = X_c W $ | $ n \times k $ | $ O(ndk) $ |

**当 $ n \ll d $ 时：**  
直接PCA需要 $ O(d^3) $，SVD路径需要 $ O(n^3 + n^2 d) $，**加速比约为 $ (d/n)^3 $**。


## 最终一句话总结

> **PCA要找的是特征向量 $ w $（来自 $ d \times d $ 的 $ X_c^T X_c $）。**
>
> **SVD加速的原理是：**
> 当 $ n \ll d $ 时，不直接分解 $ d \times d $ 的 $ X_c^T X_c $，而是先分解 $ n \times n $ 的 $ X_c X_c^T $ 得到 $ U $，再用公式 $ V = X_c^T U \Sigma^{-1} $ 反推出 $ V $（即 $ w $）。
>
> **计算结果完全相同，但计算量从 $ O(d^3) $ 降到了 $ O(n^3 + n^2 d) $。**