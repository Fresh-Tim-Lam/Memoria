# hw-003 频率响应：$h(t)=\mathrm{e}^{-3t}u(t)$，$x(t)=\mathrm{e}^{-t}u(t)$

**录入**：2026-10-09　**主题**：连续LTI系统 · 频率响应 $H(\mathrm{j}\omega)$

<!-- ⚠ 来源待核实：题面来自用户提供的作业截图（2026-10-09，可见部分止于「求系统的频率响应 H(jω)」）；求解过程由助手归纳整理，依据指向库内知识点（见文中 [[…]]）。 -->

## 1. 题面

已知连续时间 LTI 系统的冲激响应为

$$h(t)=\mathrm{e}^{-3t}u(t)$$

输入为

$$x(t)=\mathrm{e}^{-t}u(t)$$

求系统的频率响应 $H(\mathrm{j}\omega)$。

题面虽给了 $x(t)$，求 $H(\mathrm{j}\omega)$ 却用不到它 —— 该条件应是留给后续小问的，故本文件 §5 把「求零状态响应」一并做掉。

## 2. 答案

$$H(\mathrm{j}\omega)=\frac{1}{3+\mathrm{j}\omega}$$

| 量 | 表达式 | 备注 |
|---|---|---|
| $H(\mathrm{j}\omega)$ | $\dfrac{1}{3+\mathrm{j}\omega}$ | 一阶低通 |
| 幅度响应 | $\lvert H(\mathrm{j}\omega)\rvert=\dfrac{1}{\sqrt{9+\omega^{2}}}$ | $\omega$ 的偶函数 |
| 相位响应 | $\varphi(\omega)=-\arctan\dfrac{\omega}{3}$ | $\omega$ 的奇函数 |
| 直流增益 | $H(\mathrm{j}0)=\dfrac{1}{3}$ | $\omega=0$ |
| 半功率点 | $\omega_{c}=3\ \mathrm{rad/s}$ | $\lvert H\rvert^{2}$ 减半处 |
| 极点 | $s=-3$ | 左半平面 ⇒ 稳定 |

## 3. 求解：$H(\mathrm{j}\omega)$ 是 $h(t)$ 的 Fourier 变换

依据（[[img-ch2-3-97-连续时间LTI系统的频率响应]]，`img/ch02-3_信号的频域分析.md:2673-2690`）：

$$H(\mathrm{j}\omega)=\mathcal{F}\{h(t)\}=\int_{-\infty}^{\infty}h(t)\mathrm{e}^{-\mathrm{j}\omega t}\,\mathrm{d}t$$

（另一条等价口径 $H(\mathrm{j}\omega)=Y_{\mathrm{zs}}(\mathrm{j}\omega)/X(\mathrm{j}\omega)$ 见 §4。）

### 3.1 从定义硬算

$u(t)$ 把积分下限改成 $0$：

$$H(\mathrm{j}\omega)=\int_{0}^{\infty}\mathrm{e}^{-3t}\mathrm{e}^{-\mathrm{j}\omega t}\,\mathrm{d}t=\int_{0}^{\infty}\mathrm{e}^{-(3+\mathrm{j}\omega)t}\,\mathrm{d}t$$

被积函数的实部指数为 $-3<0$ ⇒ 积分收敛，$\infty$ 端趋于零：

$$H(\mathrm{j}\omega)=\left[\frac{\mathrm{e}^{-(3+\mathrm{j}\omega)t}}{-(3+\mathrm{j}\omega)}\right]_{t=0}^{\infty}=0-\frac{1}{-(3+\mathrm{j}\omega)}$$

$$H(\mathrm{j}\omega)=\frac{1}{3+\mathrm{j}\omega}$$

### 3.2 查表（一行）

库内变换对（$\alpha>0$）（[[img-ch2-3-54-常见连续时间信号的频谱]]，`img/ch02-3_信号的频域分析.md:1384-1394`）：

$$\mathcal{F}\left[\mathrm{e}^{-\alpha t}u(t)\right]=\frac{1}{\mathrm{j}\omega+\alpha}$$

取 $\alpha=3$ 即得 $\dfrac{1}{\mathrm{j}\omega+3}$，与 §3.1 一致。

同型课件例题（两项之和，用线性特性逐项变换）（[[img-ch2-3-100-连续LTI系统频率响应的计算]]，`img/ch02-3_信号的频域分析.md:2818-2831`）：

$$h(t)=(3\mathrm{e}^{-2t}+2\mathrm{e}^{-4t})u(t)\ \Longrightarrow\ H(\mathrm{j}\omega)=\frac{3}{\mathrm{j}\omega+2}+\frac{2}{\mathrm{j}\omega+4}$$

### 3.3 前置条件：先判存在性

「对于稳定的连续LTI系统，其冲激响应一定存在Fourier变换」（[[img-ch2-3-99-连续LTI系统的频率响应计算]]，`img/ch02-3_信号的频域分析.md:2799-2816`）。本题先验证：

$$\int_{-\infty}^{\infty}\lvert h(t)\rvert\,\mathrm{d}t=\int_{0}^{\infty}\mathrm{e}^{-3t}\,\mathrm{d}t=\frac{1}{3}<+\infty$$

⇒ BIBO 稳定（判据 [[img-ch2-2-72-4-冲激响应与LTI系统稳定性]]）；又 $h(t)=0\,(t<0)$ ⇒ 因果（[[img-ch2-2-71-3-冲激响应与LTI系统因果性]]）。

稳定是 $H(\mathrm{j}\omega)$ 存在的前提：换成 $h(t)=\mathrm{e}^{3t}u(t)$，$\int\lvert h\rvert=\infty$，Fourier 变换不存在。

## 4. 别混：$H(\mathrm{j}\omega)$ 与输入无关

$H(\mathrm{j}\omega)=\dfrac{Y_{\mathrm{zs}}(\mathrm{j}\omega)}{X(\mathrm{j}\omega)}$ 只是「给一个输入就能反推 $H$」的**测量式**；$H$ 本身是系统属性 ——「$H(\mathrm{j}\omega)$ 与系统的输入和输出无关」（[[img-ch2-3-98-连续时间LTI系统的频域描述]]，`img/ch02-3_信号的频域分析.md:2783`）。

⇒ 本题的 $x(t)$ 对第 1 问是[[\h:#FDEBD0:#A04000|冗余条件]]；走 $Y/X$ 反而要先知道 $y_{\mathrm{zs}}(t)$，绕远。

## 5. 延伸：若下一小问是「求零状态响应」

输入 $x(t)=\mathrm{e}^{-t}u(t)$ ⇒ $X(\mathrm{j}\omega)=\dfrac{1}{1+\mathrm{j}\omega}$。先乘、再部分分式、再查表（$Y_{\mathrm{zs}}=HX$ 见 [[img-ch2-3-108-非周期信号通过连续LTI系统的零状态响应]]；同型解法见 [[img-ch2-3-109-例-已知描述某稳定的连续LTI系统的微分方程为]]）：

$$Y_{\mathrm{zs}}(\mathrm{j}\omega)=\frac{1}{(\mathrm{j}\omega+1)(\mathrm{j}\omega+3)}=\frac{1/2}{\mathrm{j}\omega+1}-\frac{1/2}{\mathrm{j}\omega+3}$$

$$y_{\mathrm{zs}}(t)=\frac{1}{2}\left(\mathrm{e}^{-t}-\mathrm{e}^{-3t}\right)u(t)$$

**时域核对**（卷积公式见 [[img-ch2-2-57-例-计算-x-t-h-t-x-t-2-bf-e-2-t-bf-u-t-h]]，`img/ch02-2_信号与系统的时域分析.md:1412`）：

$$\mathrm{e}^{\alpha t}u(t)*\mathrm{e}^{\beta t}u(t)=\frac{1}{\beta-\alpha}\left(\mathrm{e}^{\beta t}-\mathrm{e}^{\alpha t}\right)u(t),\quad \alpha\neq\beta$$

取 $\alpha=-1,\ \beta=-3$：$\dfrac{1}{-3-(-1)}\left(\mathrm{e}^{-3t}-\mathrm{e}^{-t}\right)u(t)=\dfrac{1}{2}\left(\mathrm{e}^{-t}-\mathrm{e}^{-3t}\right)u(t)$ ✓

> 频域法的前提是 $X(\mathrm{j}\omega)$ 存在。课件反例：输入 $x(t)=\mathrm{e}^{2t}u(t)$ 的 Fourier 变换不存在，**不能用频域法**（`img/ch02-3_信号的频域分析.md:3085-3089`）。

## 6. 易错点

- [[\h:#FADBD8:#922B21|符号]]：结果是 $\dfrac{1}{3+\mathrm{j}\omega}$，不是 $\dfrac{1}{\mathrm{j}\omega-3}$。$\mathrm{e}^{-3t}$ 配 $+3$ —— 衰减指数对应 $\alpha>0$，极点落在负实轴。
- [[\h:#FADBD8:#922B21|模漏根号]]：$\lvert 3+\mathrm{j}\omega\rvert=\sqrt{9+\omega^{2}}$，不是 $9+\omega^{2}$。
- [[\h:#FDEBD0:#A04000|先判存在性]]：不稳定系统没有 Fourier 变换，$H(\mathrm{j}\omega)$ 无从定义；「稳定 ⇒ 存在」是单向的。
- [[\h:#FDEBD0:#A04000|只管零状态]]：$H(\mathrm{j}\omega)$ 描述零状态响应；由初始状态引起的零输入响应不归它管（[[img-ch2-2-42-零状态响应]]）。
- [[\h:#D9EAD3:#1E5631|一阶低通]]的特征：$\lvert H\rvert$ 随 $\omega$ 单调下降，$\omega_{c}=3$ 处降 3 dB，高频段每十倍频程 −20 dB。

## 7. 自检

- 极限：$H(\mathrm{j}0)=1/3$ ✓；$\omega\to\infty\Rightarrow H\to0$ ✓（一阶低通）
- 共轭对称：$h(t)$ 为实信号 ⇒ $H(-\mathrm{j}\omega)=H^{*}(\mathrm{j}\omega)$，$\lvert H\rvert$ 偶、$\varphi$ 奇 ✓（[[img-ch2-3-95-幅度响应与相位响应]]）
- 变换对前提：$\alpha=3>0$ ✓
- 延伸解：$y_{\mathrm{zs}}(0^{+})=0$ ✓、$t\to\infty$ 时 $y\to0$ ✓，与时域卷积公式结果一致 ✓

<!-- 来源：题面来自用户提供的作业截图（2026-10-09）；求解过程由助手归纳。变换对依据 [[img-ch2-3-54-常见连续时间信号的频谱]]（img/ch02-3_信号的频域分析.md:1384-1394），定义与存在性依据 [[img-ch2-3-97-连续时间LTI系统的频率响应]]（:2673-2690）、[[img-ch2-3-99-连续LTI系统的频率响应计算]]（:2799-2816），同型例题 [[img-ch2-3-100-连续LTI系统频率响应的计算]]（:2818-2831），卷积公式 [[img-ch2-2-57-例-计算-x-t-h-t-x-t-2-bf-e-2-t-bf-u-t-h]]（img/ch02-2_信号与系统的时域分析.md:1403-1412）。 -->
