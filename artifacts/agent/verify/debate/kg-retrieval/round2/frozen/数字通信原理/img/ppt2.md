# 系统的分类

■ 连续时间系统与离散时间系统
■ 线性系统与非线性系统
■ 非时变系统 与时变系统
因果系统与非因果系统
■ 稳定系统与非稳定系统

---

# 目录

信号的时域分析

√ 连续时间基本信号

系统的时域分析

√ 线性非时变系统的时域描述
√ 连续LTI系统响应的时域分析
√ 冲激响应表示的连续系统特性

参考教程：陈后金等，信号与系统（第4版），高等教育出版社

---

## 连续时间基本信号

普通信号

奇异信号

✓直流信号

✓阶跃信号

✓正弦信号

✓ 冲激信号

✓ 指数类信号

√斜坡信号

✓抽样信号

✓ 冲激偶信号

---

# 连续时间基本信号

普通信号:

信号 \( x(t) \) 本身及其导数 \( x'(t) \) 或高阶导数 \( x^{(n)}

![](.memoria/images/059ae90b3e8c9aa3dcfe6bdc1089990712adbb36b4eb8a716f35e93331031768.jpg)

---

## 连续时间基本信号

奇异信号：

信号x(t)本身或其导数或高阶导数具有不连续点（跳变点)

![](.memoria/images/0c229a75cab3fa3cc6f3029ee2ec6d42533984797524aa4afe9b0e28083d4c95.jpg)

信号本身具有不连续点

![](.memoria/images/06010e733e3eb10d80a0de5b0e35b7f3ae8d6789c0a2dd0105a828ad82ffc1fb.jpg)

信号的导数具有不连续点

---

# 连续时间基本信号：普通信号

# ◆ 普通信号

√ 直流信号
√ 正弦信号
√ 指数类信号
√ 抽样信号

---

# 1. 直流信号

$$
x (t) = A, \quad - \inj
$$

![](.memoria/images/3bfb74dbb6dd231fee5b1d03e7c05abe3c3e4630fc5d50e88033a09be8b84324.jpg)

x(t)=A
A
O
t

---

# 2. 正弦信号

$$
x (t) = A = 0
$$

![](.memoria/images/b600731c57da5982aec78479d4a914becb03298b735c95c72c7beeb97f990298.jpg)

| t | x(t) |
| --- | --- |
| 0 | 0 |
| ~0.25 | A |
| ~0.5 | 0 |
| ~0.75 | A |
| 1 | 0 |

$A$ (振幅)

$$
x (t) = x t = 0
$$

周期： \( T\_{0} \]

频率： \( {f}\_{0

---

## 2. 正弦信号

![](.memoria/images/ed6905e7c965cf769a0d38ff8d0237e5174fb5eb3a7bf732dd7e81a85b71edca.jpg)

---

# 3. 指数类信号

➢ 实指数信号  \( x(t)=A\mathrm{e^{αt}

![](.memoria/images/6b9a3bc5a66155f570fcd88f4f056106cd147bc7f3e5cbb138b057fcb156e509.jpg)

---

## 3. 指数类信号

虚指数信号 $x ( t ) = { \mathrm { e } } ^ { { \mathrm { j } } \omega _ { 0 } t } = \cos ( \omega _ { 0 } t ) + { \mathrm { j } } \sin ( \omega _ { 0 } t )$

![](.memoria/images/15ddac9545740df03fa2007a6bc9cc4b1522050533af1f27230ccf540b0d7f4f.jpg)

周期性： $x ( t ) = x ( t + T _ { 0 } )$

$$
{ \bf e } ^ { \mathrm { j } \omega _ { 0 } t } = { \bf e } ^ { \mathrm { j } \omega _ { 0 } ( t + T _ { 0 } ) }
$$

$$
\omega _ { 0 } T _ { 0 } = 2 \pi n , n = \pm 1 , \pm 2 \cdots
$$

基本周期： $T _ { \phantom { } _ { 0 } } = \frac { 2 \pi } { \left| \omega _ { } \right| }$

---

# 3. 指数类信号

➢ 虚指数信号 $x(t)=\mathrm{x}}=1.0\text{时}$

Euler公式:

$$
\cos (\omega_ {0} t) = \frac{1}{2} = 1
$$

$$
\sin (\omega_ {0} t) = \frac{1}{2} = 0
$$

Euler公式建立了正、余弦信号与虚指数信号的关系。

---

# 莱昂哈德·欧拉(Leonhard, Euler)

![](.memoria/images/f1bbbd70f03791d769517e42e30a31efef289a97a5043a14a00b24c285c3e719.jpg)

Portrait of a man in historical attire holding a book, seated in a chair (no visible text or symbols)

(1707\~1783)

瑞士数学家、物理学家，近代数学前驱之一。

欧拉平均每年写出八百多页的论文，还撰写大量的力学、分析学、几何问题。

在众多数学的分支中，经常见到以欧拉命名的重要公式和定理，例如欧拉式、欧拉式、流体力学中的欧拉式等。最著名的是欧拉式首次使用“函数”概念来描述包含各种参数的表达式，记为 $f(x)$ 。

---

## 3. 指数类信号

复指数信号

$$
x ( t ) = A \mathbf { e } ^ { s t }
$$

$$
s = \sigma + \mathrm { j } \omega _ { \mathrm { 0 } }
$$

$$
x ( t ) = A  { \mathrm { e } } ^ { \sigma t }  { \mathrm { e } } ^ {  { \mathrm { i } } \omega _ { 0 } t } = A  { \mathrm { e } } ^ { \sigma t } \cos \omega _ { 0 } t +  { \mathrm { j } } A  { \mathrm { e } } ^ { \sigma t } \sin \omega _ { 0 } t
$$

![](.memoria/images/78916b71f1ff4f861afaed1c1dc08b7e0e48c62660469b4159e11aa92ef7e006.jpg)

![](.memoria/images/d6a20c8095c5d9c1f558301e40332b789362be5c8e4dc774a80d25066122344b.jpg)

---

# 3. 指数类信号

➢ 指数类信号 — 复指数信号 $x(t)=A\mathrm{e}^{st}\quad s=\sigma+\mathrm{j}\omega_{0}$

当 $\sigma \neq 0$ 且 $\omega_0 \neq 0$ 时，复指数信号

当 $\sigma = 0$ 且 $\omega_0\neq 0$ 时，虚指数信号

当 $\sigma \neq 0$ 且 $\omega_0 = 0$ 时，实指数信号

当 $\sigma = 0$ 且 $\omega_0 = 0$ 时，直流信号

![](.memoria/images/f28d9f5ebcebdcbe8d75b42702d6003c4da0e7e26f87966bdef499900b4f2fce.jpg)

Simple line drawing of a wave or signal with increasing amplitude over time (no text or symbols)

![](.memoria/images/e6bc10f5f5e6c33bc659fada8a10c8491d52ddb59118143860e48c787ac4194a.jpg)

Simple blue sine wave line drawing with no text or symbols

![](.memoria/images/67b3517e9994d97d43567bcc0d4af8cf5dab63692d9f32de174ea1fcf0fa1dec.jpg)

Simple curved line drawing with no text, numbers, or symbols

---

## 4. 抽样信号

$$
\mathrm { S a } ( t ) = { \frac { \sin t } { t } }
$$

![](.memoria/images/667e3e4cbac6172473f6a19a453c003128503b6a1051b1a4026d0da3029af6bd.jpg)

## 理工AI助教信号与系统

×

12/11 15:59

![](.memoria/images/8388d337804cbaf119ed8cf7c936075aa7028c00d5d6ed492002cb8fdfd986e1.jpg)

![](.memoria/images/182dc725f92a78bbb144f7acec8804c3b6c7b8b4c3e5caaee88812599861499f.jpg)

信号sa(t)有何作用?

12/11 16:37

![](.memoria/images/9bec2a3aa6e4cecffeede6d0fff497b23781f41a3abb0207780b26c03907d705.jpg)

## 一、信号分析方面

Sa(t)在频域分析中有重要意义。它与矩形脉冲信号的频谱相关，是一对傅里叶变换对，有助于理解信号在频域和时域的转换关系。

## 二、系统分析方面

在系统输入输出关系中，当输入输出频谱关系涉及到特定形式时， $S a ( t )$ 可能会作为输出信号的时域波形出现，有助于分析信号通过系统后的变化。

## 三、数学特性方面

其具有特殊的数学性质，如 $S a ( 0 ) = 1 , \ S a ( k \pi ) = 0 , k = \pm 1 , \pm 2 , . . .$ $\begin{array} { r } { \int _ { - \infty } ^ { \infty } S a ( t ) d t = \pi } \end{array}$ 这些性质在信号处理和数学计算中有一定的应用。

---

# 1. 单位阶跃信号

$$
\mathrm{u} (t) = \left\{u \right\} = \left\{ \begin{array}{l l} 1 & t > 0 \\ 0 & t <   0 \end{array} \right.
$$

$$
\mathrm{u} (t - t _ {0}) = \left\{\begin{array}{l l}1&t > t _ {0}\\0&t <   t _ {0}\end{array}\right.\left. \right.
$$

实际问题：开关电路

![](.memoria/images/ec7c5a2518f0889d47deee408d0a6b3ba1f1c641101dec92cb111d1eb558c0a5.jpg)

注意：
在跳变点0处，u(0)未定义。

![](.memoria/images/686bb777dea5d08cdbb45175c18c6771d5c71848049cb99514752c5232401ae2.jpg)

![](.memoria/images/f41ea537f684dea01dc3a73cc621db8f3ee6870ec0b0c3fb3b45963a0b44a8f8.jpg)

---

# 1. 单位阶跃信号

作用：(1) 表示任意的矩形脉冲信号

![](.memoria/images/7fd805f3c6b49d1c935bfc225ff85773112f84edd25ff343cc76f1d5354a216a.jpg)

![](.memoria/images/05ef83f3e3c3aa8ef7743cc33ba4b28b6ae3c6ddf3a6d5b7e136bfbed24e8759.jpg)

---

# 1. 单位阶跃信号

作用：(2)利用阶跃信号的单边性表示的单边性表示的单边性表示的单边性表示的单边性表示的单边性表示的单边性表示的单边性表示的单边性表示的单边性表示的单边性表示的单边性表示的单边性表示的单边性表示的单边性表示的单边性表示的单边性表示的单边性表示的单边性表示的单边性表示的单边性。

![](.memoria/images/0f3fa216da96966be56dbf05430118f78817d4c461298f4771afb8e506950a20.jpg)

---

# 2. 单位冲激信号

实际问题：力学中瞬间作用的冲击力、自然界中的闪电等

![](.memoria/images/3a03c69360199343c587f4ef49a076767c722c8ac415026c8ba74723a9929f9d.jpg)

子弹击穿苹果

![](.memoria/images/26dad13f2a00044a56bd21ae7a00a2710bab976726674f9c989539b75d89143c.jpg)

Night scene with a large lightning bolt striking the sky above a cityscape (no visible text or symbols)

闪电

特点：作用时间极短，而幅值极大。

---

# 2. 单位冲激信号

狄拉克(Dirac)定义

![](.memoria/images/a72b4dececf171f07bb0dcd0506bea0bbecfb3676aec3ffad97780dd8e35192b.jpg)

$$
\delta (t) = 0, t \neq t = 0
$$

$$
\int_ {- \infty} ^ + \infty
$$

冲激信号具有强度，其强度就是冲激信号对t的定积分值。在图中用括号符号表示，以积分符号表示的积分值为

---

## 2. 单位冲激信号

## 狄拉克(Dirac)定义

![](.memoria/images/83da1dd9db78428c4cb34e06a2909268d5eb54c8317333fc8ae1f1a4095a57eb.jpg)

## AI助教

为何引入冲激信号?

![](.memoria/images/65030c08db90f5a510e053c0b4bffc0b19e3d52df9e51be6adca9f9e58e56ac4.jpg)

![](.memoria/images/9f18d197a4d48cb49dec06da9055cf568d78ec0c4718672ba4c956be89276c66.jpg)

## 一、在导数方面的意义

对于存在间断点的函数，引入冲激信号后，间断点处的导数可以用冲激信号表示，其强度等于该点的跳跃值。

## 二、信号关系构建方面

它有助于构建不同信号之间的关系，例如冲激信号、阶跃信号、斜坡信号和冲激偶信号之间存在微分关系。

可以用冲激信号来表示其他信号，在时域中将所有的连续时间信号表示为冲激信号的组合，这有助于对信号进行分析和处理。

## 三、系统分析方面

冲激响应是系统在冲激信号作用下的输出响应，通过冲激响应能够分析系统的特性，如系统的稳定性、因果性等

求解连续时间线性非时变系统的零状态响应，需要先知道系统的冲激响应，因为零状态响应等于输入信号和系统冲激响应的卷积。

---

# 2. 单位冲激信号

狄拉克(Dirac)定义

![](.memoria/images/b0900d8210178cd6b7adbe389541c235c80c682c81d668ab5f4bcff98c40f22d.jpg)

δ(t - t₀)
(1)
O
t₀
t

$$
\delta (t - t _ {0}) = 0 \quad t \neq t _ {0}
$$

$$
\int_ {- \infty} ^ {\infty} \delta (t - t _ {0}) \mathrm{d} t = \int_ {t _ {0} - \Delta} ^ {t _ {0} + \Delta} \delta (t - t _ {0}) \mathrm{d} t = 1
$$

---

# 2. 单位冲激信号

# 极限模型

![](.memoria/images/bc5400a9f5a461940db26b4df83499509c613e6d6e6d03a2eac6333bffbe0b77.jpg)

$$
\delta (t) = \lim _ {\Delta \to 0} f _ {\Delta} (t) = \lim _ {\Delta \to 0} \left\{g _ {\Delta} (t) \right\}
$$

---

2. 单位冲激信号

冲激信号δ(t)的广义函数定义

![](.memoria/images/4181c379c75bb35db0f4ea028ae9a49e152bb7a419aba3cd95fb0d6b834f719f.jpg)

φ(t)为测试函数，是任意的连续信号若某信号与任意连续信号φ(t)在(-∞,∞)上的积分等于φ(t)在0时刻的值，则该信号为冲激信号。

---

# 2. 单位冲激信号

性质1：筛选特性

$$
x (t) \delta (t - t _ {0}) = x (t _ {0}) \delta (t - t _ {0})
$$

![](.memoria/images/cc7c1c7f53615e59ddc97be135a46228a74e69fc9227f8bf8272a9cf236cbc90.jpg)

---

# 2. 单位冲激信号

性质2：抽样特性

![](.memoria/images/6d5e7a2d5a1cf22d8968a17619467bec58917d6e96c3bcbf04695d8ec22bd7d3.jpg)

$$
\begin{array}{r l} \text {证明:} & \int_ {- \infty} ^ {\mathrm{证明}} = \int_ {- \infty} ^ {\infty} x (t) \delta (t - t _ {0}) \mathrm{d} t \quad \text {利用筛选特性} \\ & = \int_ {- \infty} ^ {\infty} x (t _ {0}) \delta (t - t _ {0}) \mathrm{d} t \end{array}
$$

---

## 2. 单位冲激信号

性质3：展缩特性

$$
\delta ( a t ) = { \frac { 1 } { \left| a \right| } } \delta ( t ) \left( a \neq 0 \right)
$$

$$
\int _ { - \infty } ^ { \infty } \varphi ( t ) \delta ( t ) \mathrm { d } t = \varphi ( 0 )
$$

$$
\int _ { - \infty } ^ { \infty } \varphi ( t ) \delta ( a t ) \mathrm { d } t = \frac { 1 } { | a | } \varphi ( 0 )
$$

(1)取 $a = - 1$ ，可得 $\delta ( t ) = \delta ( - t )$ 推论：冲激信号是偶函数

$$
\frac { \ b u = \ b a t } { \ b a > 0 }  \int _ { - \infty } ^ { \infty } \ \varphi ( \ b u / \ b u ) \delta ( \ b u ) \mathrm { d } t / \ a = \frac { 1 } { a } \varphi ( 0 )
$$

$$
\frac { \ b u = \ b u } { \ b u < 0 }  \int _ { \infty } ^ { - \infty } \ \varphi ( \ b u / a ) \ S ( \ b u ) \mathrm { d } t / a = - \frac { 1 } { a } \varphi ( 0 )\tag{2}
$$

$$
\delta ( a t + b ) = { \frac { 1 } { \left| a \right| } } \delta ( t + b / a )
$$

$$
( a \neq 0 )
$$

---

# 2. 单位冲激信号

性质：冲激信号与阶跃信号的关系

$$
\frac {\mathrm{du} (t)}{\mathrm{d} t} = \delta (t)
$$

$$
\int_ {- \infty} ^ {t} \delta (\tau) \mathrm{d} \tau = \left\{u _ {t} \right. = \mathrm{u} (t)
$$

![](.memoria/images/b3524d0d4b5887aac6387fa238bcac156f07514895bfaf43c0204b1f01514dd3.jpg)

---

# 2. 单位冲激信号

$$
\frac {\mathrm{du} (t)}{\mathrm{d} t} = \delta (t)
$$

信号在不连续点的导数为冲激信号或延时的冲激信号，冲激信号的强度是不连续点的跳变值。

---

## [例] 计算下列各式

$\int _ { - \infty } ^ { + \infty } \sin ( t ) \cdot \delta ( t - \frac { \pi } { 4 } ) \mathrm { d } t = \sin ( \frac { \pi } { 4 } ) = \sqrt { 2 } / 2$

(2) $\int _ { - 2 } ^ { + 3 } \mathrm { e } ^ { - 5 t } \cdot \delta ( t - 1 ) \mathrm { d } t = \mathrm { e } ^ { - 5 \times 1 } = 1 / \mathrm { e } ^ { 5 }$

(3) $\int _ { - 4 } ^ { + 6 } \mathbf { e } ^ { - 2 t } \cdot \delta ( t + 8 ) \mathrm { d } t \ = 0$

$$
\int _ { - \infty } ^ { + \infty } \mathrm { e } ^ { - t } \cdot \delta ( 2 - 2 t ) \mathrm { d } t = \int _ { - \infty } ^ { + \infty } \mathrm { e } ^ { - t } \cdot \frac { 1 } { 2 } \delta ( t - 1 ) \mathrm { d } t = \frac { 1 } { 2 \mathrm { e } }
$$

(5) $\int _ { - 2 } ^ { + 2 } ( t ^ { 2 } + 3 t ) \cdot \delta ( \frac { t } { 3 } - 1 ) \mathrm { d } t \ = \int _ { - 2 } ^ { + 2 } ( t ^ { 2 } + 3 t ) \cdot 3 \delta ( t - 3 ) \mathrm { d } t = 0$

$$
\mathbf { e } ^ { - 4 t } \cdot \delta ( 2 + 2 t ) = \mathbf { e } ^ { - 4 t } \cdot \frac { 1 } { 2 } \delta ( t + 1 ) = \frac { 1 } { 2 } \mathbf { e } ^ { - 4 \times ( - 1 ) } \delta ( t + 1 ) = \frac { 1 } { 2 } \mathbf { e } ^ { 4 } \delta ( t + 1 )
$$

---

# 2. 单位冲激信号

1. 在冲激信号的抽样特性中，其在冲激信号的大小下，但其在冲激信号的大小下，其在冲激信号的大小下，其在冲激信号的大小下，其在冲激信号的大小下，其在冲激信号的大小下，其在冲激信号的大小下，其在冲激信号的大小下，其在冲激信号的大小下，其在冲激信号的大小不等，但只要积分区间不包括冲激信号的大小，其在冲激信号的大小，其在冲激信号的大小，其在冲激信号的大小，其在冲激信号的大小，其在冲激信号的大小，其在冲激信号的大小，其在冲激信号的大小，其在冲激信号的大小，其在冲激信号的大小，其在冲激信号的大小，其在冲激信号的大小，其在冲激信号的大小，其在冲激信号下的大小，其在冲激信号下的大小，其在冲激信号下的大小，其在冲激信号下的大小，其在冲激信号下的大小，其在冲激信号下的大小，其在冲激信号下的大小，其在冲激信号 $\delta(t - t_0)$ 的 $t = t_0$ 时刻，则积分结果为零。

2. 对于 $\delta(at+b)$ 形式后，方可利用冲激信号的特性。

---

## 3. 单位斜坡信号

$$
r ( t ) = \left\{ \begin{array} { c c } { { t } } & { { t \geq 0 } } \\ { { 0 } } & { { t < 0 } } \end{array} \right. \Leftrightarrow r ( t ) = t \cdot { \bf u } ( t )
$$

![](.memoria/images/61fb60b1cba79f4491e04ed4c7c5acce937776f52b8c75b1deb6cd0088d503e8.jpg)

---

# 3. 单位斜坡信号

斜坡信号与阶跃信号之间的关系

$$
\frac {\mathrm{d} r (t)}{\mathrm{d} t} = \mathrm{u} (t)
$$

![](.memoria/images/77e26325021bf07529aed76d0a9aad5a8325f3f0855dfed574fbd70b0d9a2952.jpg)

---

# 3. 单位斜坡信号

# 表示任意的三角脉冲信号

![](.memoria/images/7faeb2d4a639e7aac44f45d797d6dd874a587fa87fd269ca7792dafade783700.jpg)

$$
x (t) = r (t + 1) - 2 r (t) + r (t - 1)
$$

---

# 4. 单位冲激偶信号

![](.memoria/images/58121809372ef61c3173e78962904c30b6261a17df93719350708ba71eaabf69.jpg)

定义:

$$
\delta^ {\prime} (t) = \frac \mathrmd
$$

冲激偶信号的图形表示

![](.memoria/images/ec3e6757d60193264a6fb509eea1c04db700641b500ca3d8fe997ba5073b961e.jpg)

δ'(t)
(1)
O
t

---

# 4. 单位冲激偶信号

冲激偶信号的性质:

$$
x (t) \delta^ {\prime} (t - t _ {0}) \tag {筛选特性}
$$

$$
\int_ {- \infty} ^ {\infty} x (t) \text {抽样特性)}
$$

$$
\delta^ {\prime} (a t) = \frac {1}a _ {|} a | \delta^ {\prime} (t) \quad (a \neq 0) \tag {展缩特性}
$$

$$
\delta^ {\prime} (t) = - \delta^ {\prime} (- t) \mathrm{d} t))
$$

---

# 四种奇异信号之间的关系

![](.memoria/images/8ef360d26928367cad58a1d124e6cb0206b6a607c88ac2344f0dc1a9dddb9039.jpg)

r(t)
1
0
1
u(t)
1
0
δ(t)
(1)
0
t
δ'(t)
(1)
0
t

导数关系

$$
r (t) \xrightarrow {\frac {\mathrm{d} ()}{\mathrm{d} t}} \mathrm{u} (t) \xrightarrow {\frac {\mathrm{d} ()}{\mathrm{d} t}} \delta (t) \xrightarrow {\frac {\mathrm{d} ()}{\mathrm{d} t}} \delta^ {\prime} (t)
$$

积分关系

$$
\delta^ {\prime} (t) \xrightarrow [ \int_ {- \infty} ^ {t} () \mathrm{d} \tau ]{} \delta (t) \xrightarrow [ \int_ {- \infty} ^ {t} () \mathrm{d} \tau ]{} \mathrm{u} (t) \xrightarrow [ \int_ {- \infty} ^ {t} () \mathrm{d} \tau ]{} r (t)
$$