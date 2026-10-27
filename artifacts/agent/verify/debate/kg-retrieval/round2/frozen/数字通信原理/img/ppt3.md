# 数字通信原理 课件三

> 来源：img/ppt3（68 页课件）
> 说明：由 MinerU（pipeline，OCR 路线）解析的版面分析 + 公式识别 + 插图裁切结果；页眉页脚等版式元素已剔除，图片统一落位 `.memoria/images/`。

信号的时域分析  
✓连续时间基本信号  
A 系统的时域分析  
✓线性非时变系统的时域描述  
✓连续LTI系统响应的时域分析  
✓冲激响应表示的连续系统特性

## 目录

## 系统的时域分析

### 理工AI助教信号与系统

系统时域分析的主要内容是什么？

![](.memoria/images/c1898bc6c122533d4e94774047bbde079b718dd2eba50e8276495ca6146e6771.jpg)

12/25 10:39

![](.memoria/images/7d92a7dcd860de67ab87043fd5483c58abca9b23ade7fed9e186613bf646ef83.jpg)

### 一、系统描述

对于连续时间线性时不变系统，可通过常系数线性微分方程描述；离散时间线性时不变系统则通过差分方程描述。

还可通过系统的冲激响应（连续系统）或单位脉冲响应（离散系统）来描述系统的时域特性。

### 二、揭示相互作用机理

揭示信号与系统在时域相互作用的机理，如连续系统输出的零状态响应等于输入信号和系统冲激响应的卷积；离散系统输出的零状态响应等于输入信号和系统单位脉冲响应的卷积和。

## 线性非时变系统的时域描述

![](.memoria/images/4f34de69a11de0b4f3b83c173cb8698177553241acd337ce170c27502c720393.jpg)

时域描述：建立系统输出与输入之间的约束关系

## 1. 连续LTI系统的时域描述

![](.memoria/images/bca6a65777a668aec2d2ca6d5ea736066eb29fcf47cd2490fb5411144d7bb1ca.jpg)

输入：x(t);

输出：i(t)

根据KVL，可得

$$
L \frac { \mathrm { d } i ( t ) } { \mathrm { d } t } + R i ( t ) = x ( t )
$$

LR一阶电路系统的输入-输出关系，可由一阶微分方程描述

![](.memoria/images/af221bb97885f834a54e1d2543d6cb2417cacb6ece8be9f6a52f96e5d74c5bda.jpg)

输入：x(t)；输出：y(t)

根据电路基本理论，可得:

$$
3 { \frac { \mathrm { d } ^ { 2 } y ( t ) } { \mathrm { d } t ^ { 2 } } } + 3 { \frac { \mathrm { d } y ( t ) } { \mathrm { d } t } } + y ( t ) = 2 { \frac { \mathrm { d } x ( t ) } { \mathrm { d } t } }
$$

LRC二阶电路系统的输入-输出关系，用由二阶微分方程描述

描述不同连续时间系统的数学模型是相似的，其输入-输出关系都可利用微分方程进行描述

连续时间LTI系统的输入-输出关系

可由线性常系数微分方程进行描述

$$
\begin{array} { c } { { y ^ { ( n ) } ( t ) + a _ { n - 1 } y ^ { ( n - 1 ) } ( t ) + \cdots + a _ { 1 } y ^ { \prime } ( t ) + a _ { 0 } y ( t ) } } \\ { { \ } } \\ { { = b _ { m } x ^ { ( m ) } ( t ) + b _ { m - 1 } x ^ { ( m - 1 ) } ( t ) + \cdots + b _ { 1 } x ^ { \prime } ( t ) + b _ { 0 } x ( t ) } } \end{array}
$$

连续LTI系统具有线性特性和非时变特性，因此有：

微分特性

若 $x ( t ) \longrightarrow y ( t )$

积分特性

若 $x ( t ) \longrightarrow y ( t )$

则有

$$
\frac { \mathrm { d } x ( t ) } { \mathrm { d } t } \longrightarrow \frac { \mathrm { d } y ( t ) } { \mathrm { d } t }
$$

则有 $\int _ { - \infty } ^ { t } x ( \tau ) \mathrm { d } \tau \longrightarrow \int _ { - \infty } ^ { t } y ( \tau ) \mathrm { d } \tau$

【例】已知某连续LTI系统在 $x _ { 1 } ( t )$ 激励下产生的响应为 $y _ { 1 } ( t )$ 试求该系统在 $x _ { 2 } ( t )$ 激励下产生的响应 $y _ { 2 } ( t )$

![](.memoria/images/d4be1bd049e4fe602b3cc7df47a3894843f881cc89ad2637d0a0524ff7fd68f9.jpg)

![](.memoria/images/8fee8e87c202e342f8632c7a86c5e5a1b29f666081b9dd74076397b133d08fc8.jpg)

![](.memoria/images/36ecc3589ab94064ed102ac69440721e9286054124a5a4efa6f15ee22b534649.jpg)

解： $\mathcal { N } x _ { 1 } ( t )$ 和 $| x _ { 2 } ( t )$ 图形可以看得出， $x _ { 2 } ( t )$ 与 $x _ { 1 } ( t )$ 存在以下关系

$$
x _ { 2 } ( t ) = x _ { 1 } ^ { \scriptscriptstyle ( - 1 ) } ( t ) = \int _ { - \infty } ^ { t } x _ { 1 } ( \tau ) \mathrm { d } \tau
$$

因此， $y _ { 2 } ( t )$ 与 $y _ { 1 } ( t )$ 之间也存在同样的关系

$$
y _ { 2 } ( t ) = y _ { 1 } ^ { ( - 1 ) } ( t ) = \int _ { \bar { y } - \infty } ^ { t } y _ { 1 } ( \tau ) \mathrm { d } \tau
$$

【例】已知信号 $\cdot x _ { 1 } ( t ) { = } \mathrm { u } ( t ) { - } \mathrm { u } ( t { - } 1 )$ 通过某连续LTI系统的零状态响应为$y _ { 1 } ( t ) = 8 ( t - 1 ) - 8 ( t - 2 )$ ，试求该系统在 $x _ { 2 } ( t )$ 激励下产生的响应 $y _ { 2 } ( t )$

![](.memoria/images/38cd1e3cf1526e0103843e80654dbea3fc33079ae489db4f2adbee27307f9beb.jpg)

![](.memoria/images/9bcf8c3ef16acb987cf4e15dc0b403817e02f5670dd04de652f94bf75f58681e.jpg)

![](.memoria/images/254ddefec7574975794e3f9a0e9bf5357673fd34a07354554c3fc65e2230ce0f.jpg)

解： $x _ { 2 } ( t ) = x _ { 1 } ^ { { \scriptscriptstyle ( - 1 ) } } ( t - 1 ) = \int _ { - \infty } ^ { t - 1 } \ x _ { 1 } ( \tau ) \mathrm { d } \tau$ $y _ { 2 } ( t ) = y _ { 1 } ^ { ( - 1 ) } ( t - 1 ) = \int _ { - \infty } ^ { t - 1 } y _ { 1 } ( \tau ) \mathrm { d } \tau = \mathbf { u } ( t - 2 ) - \mathbf { u } ( t - 3 )$ y3(t)=?

## 2. 离散LTI系统的时域描述

![](.memoria/images/26090ed2e879316cb14f3a8752d14d57b83e531979a85bd57c8821ca8252bb9d.jpg)

3点滑动平均系统

$$
\begin{array} { r } { y [ k ] = \displaystyle \frac { 1 } { 3 } \{ x [ k ] + x [ k - 1 ] + x [ k - 2 ] \} } \\ { ( \sharp \sharp x [ - 2 ] = 0 ~ , ~ x [ - 1 ] = 0 ) } \end{array}
$$

不同离散时间系统的数学模型是相似的，都可用差分方程描述。

可以用前向差分方程和后向差分方程描述离散系统，若输入/输出信号是因果信号，一般用后向差分方程。

离散LTI系统一般用线性常系数差分方程描述

$$
\begin{array} { l } { { a _ { 0 } y [ k ] + a _ { 1 } y [ k - 1 ] + \dots + a _ { n - 1 } y [ k - n + 1 ] + a _ { n } y [ k - n ] } } \\ { { \ } } \\ { { = b _ { 0 } x [ k ] + b _ { 1 } x [ k - 1 ] + \dots + b _ { m - 1 } x [ k - m + 1 ] + b _ { m } x [ k - m ] } } \end{array}
$$

离散LTI系统一般用线性常系数差分方程描述

$$
\begin{array} { l } { { a _ { 0 } y [ k ] + a _ { 1 } y [ k - 1 ] + \dots + a _ { n - 1 } y [ k - n + 1 ] + a _ { n } y [ k - n ] } } \\ { { \ } } \\ { { = b _ { 0 } x [ k ] + b _ { 1 } x [ k - 1 ] + \dots + b _ { m - 1 } x [ k - m + 1 ] + b _ { m } x [ k - m ] } } \end{array}
$$

或简写成

$$
\sum _ { i = 0 } ^ { n } a _ { i } y [ k - i ] = \sum _ { j = 0 } ^ { m } b _ { j } x [ k - j ]
$$

离散LTI系统具有线性特性和非时变特性，因此有：

差分特性

$$
\begin{array} { r } { \frac { \# \mathbb { R } } { \# } ~ x [ k ] \longrightarrow y [ k ] ~ \# \mathbb { I } \mathbb { I } \mathbb { I } \mathbb { I } \longrightarrow \nabla x [ k ] \longrightarrow \nabla y [ k ] } \end{array}
$$

求和特性

若 $x [ k ] { \longrightarrow } y [ k ]$

则有

$$
\sum _ { n = - \infty } ^ { k } x [ n ] \longrightarrow \sum _ { n = - \infty } ^ { k } y [ n ]
$$

【例】已知离散时间LTI系统在 $x _ { 1 } [ k ]$ 激励下产生的响应为 $y _ { \mathrm { 1 } } [ k ]$ 试求该系统在 $x _ { 2 } [ k ]$ 激励下产生的响应 $y _ { 2 } [ k ]$

![](.memoria/images/52e8e797b202af1b3a7b41b4b5f0ea9f6ce94bace5f5c47eb5c5919332f31343.jpg)

![](.memoria/images/225adc7a84cd656000c289640f4ac0f0c6eba47af5fa30009243e67c5b6ec657.jpg)

![](.memoria/images/af3349c340cd429088038bb8b13348a1b4b487bc52d188389280cbc947a8a6fe.jpg)

解：从 $x _ { 1 } [ k ]$ 和 $| x _ { 2 } [ k ]$ 图形可以看得出， $x _ { 2 } [ k ]$ 与 $x _ { 1 } [ k ]$ 存在以下关系

$$
x _ { 2 } [ k ] = \nabla x _ { 1 } [ k ] = x _ { 1 } [ k ] - x _ { 1 } [ k - 1 ]
$$

因此， $y _ { 2 } [ k ]$ 与 $y _ { 1 } [ k ]$ 之间也存在同样的关系

$$
y _ { 2 } [ k ] = \nabla y _ { 1 } [ k ] = y _ { 1 } [ k ] - y _ { 1 } [ k - 1 ] = \{ 1 , 1 , 1 , - 1 , - 1 , - 1 ; k = 1 , 2 , 3 , 4 , 5 , 6 \}
$$

【例】利用M点的滑动平均系统滤除信号噪声。

解：M点的滑动平均系统的输入-输出关系为（[[证明]]）

$$
y [ k ] = { \frac { 1 } { M } } \sum _ { n = 0 } ^ { M - 1 } \ x [ k - n ]
$$

原始信号：

$$
s [ k ] = 5 + 2 \cos ( 0 . 0 2 \pi k ) + ( 2 k ) 0 . 9 ^ { k }
$$

噪声信号：

$$
n [ k ]
$$

加噪信号：

$$
x [ k ] { = } s [ k ] { + } n [ k ]
$$

利用M点的滑动平均系统从信号 $x [ k ]$ 中滤除噪声信号 $n [ k ]$

【例】利用M点的滑动平均系统滤除信号噪声。

## 目录

信号的时域分析  
✓连续时间基本信号  
A 系统的时域分析  
✓线性非时变系统的时域描述  
✓连续LTI系统响应的时域分析  
✓冲激响应表示的连续系统特性

## 连续LTI系统响应的时域分析

输入信号x(t)

输出信号y(t)

连续LTI系统

基于求解线性常系数微分方程的方法

基于零输入响应与零状态响应的方法

连续LTI系统的时域特性—冲激响应

## 1. 基于求解线性常系数微分方程的方法

连续LTI系统可由线性常系数微分方程描述

$$
\begin{array} { c } { { y ^ { ( n ) } ( t ) + a _ { n - 1 } y ^ { ( n - 1 ) } ( t ) + \cdots + a _ { 1 } y ^ { \prime } ( t ) + a _ { 0 } y ( t ) } } \\ { { \ } } \\ { { = b _ { m } x ^ { ( m ) } ( t ) + b _ { m - 1 } x ^ { ( m - 1 ) } ( t ) + \cdots + b _ { 1 } x ^ { * } ( t ) + b _ { 0 } x ( t ) } } \end{array}
$$

微分方程的全解由齐次解 $y _ { \mathrm { h } } ( t )$ 和特解 $y _ { \mathrm { p } } ( t )$ 组成

$$
y ( t ) = y _ { \mathrm { h } } \left( t \right) + y _ { \mathrm { p } } \left( t \right)
$$

√齐次解 $y _ { \mathrm { h } } ( t )$ 的形式由微分方程对应的特征根确定

✓特解 $y _ { \mathrm { p } } ( t )$ 的形式由方程右边激励信号的形式确定

[例]已知描述某连续LTI系统的微分方程为

$$
y " ( t ) + 6 y " ( t ) + 8 y ( t ) = x ( t ) , t > 0
$$

初始条件 ${ } \cdot y ( 0 ^ { + } ) { = } 1 , y ^ { \prime } ( 0 ^ { + } ) { = } 2 .$ 输入信号 $\mathtt { \Delta } x ( t ) { \mathrm { = } } \mathrm e ^ { - 1 } \mathrm { \ u { u } } ( t )$ ，求全解y(t)。

解:（1）确定齐次方程 $y ^ { * } ( t ) + 6 y ^ { * } ( t ) + 8 y ( t ) = 0$ 的齐次解 $y _ { \mathrm { h } } ( t )$ 的形式特征方程为 $s ^ { 2 } + 6 s + 8 = 0$ 特征根为 $s _ { 1 } = - 2 , s _ { 2 } = - 4$ 齐次解 $y _ { \mathrm { h } } ( t )$ $y _ { \mathrm { h } } ( t ) = A  { \mathrm { e } } ^ { - 2 t } + B  { \mathrm { e } } ^ { - 4 t }$ t>04

[例]已知描述某连续LTI系统的微分方程为

$$
y " ( t ) + 6 y " ( t ) + 8 y ( t ) = x ( t ) , t > 0
$$

初始条件 ${ } \cdot y ( 0 ^ { + } ) { = } 1 , y ^ { \prime } ( 0 ^ { + } ) { = } 2 .$ 输入信号 $\mathtt { \Delta } x ( t ) { \mathrm { = } } \mathrm e ^ { - 1 } \mathrm { \ u { u } } ( t )$ ，求全解y(t)。

解：(2) 求微分方程 $y " ( t ) + 6 y " ( t ) + 8 y ( t ) = x ( t )$ 的特解 $y _ { \mathsf { p } } ( t )$

由输入x(t)的形式，设方程的特解为

$$
y _ { \mathrm { p } } ( t ) = C \mathrm { e } ^ { - t } \qquad t > 0
$$

将特解带入原微分方程即可求得待定系数 $C { = } 1 / 3$ o

[例]已知描述某连续LTI系统的微分方程为

$$
y " ( t ) + 6 y " ( t ) + 8 y ( t ) = x ( t ) , t > 0
$$

初始条件 ${ \bf \nabla } \cdot { \bf \boldsymbol { y } } ( 0 ^ { + } ) { = } 1 , { \bf \nabla } { \bf { \boldsymbol { y } } } ^ { \prime } ( 0 ^ { + } ) { = } 2 .$ 输入信号 $\mathtt { \Delta } x ( t ) { \mathrm { = } } \mathrm e ^ { - 1 } \mathrm { \ u { u } } ( t )$ ，求全解y(t)。

解:(3) 求微分方程的全解

$$
\begin{array} { c } { { y ( t ) = y _ { \mathrm { h } } ( t ) + y _ { \mathrm { p } } ( t ) = A \mathrm { e } ^ { - 2 t } + B \mathrm { e } ^ { - 4 t } + \mathrm { e } ^ { - t } / 3 } } \\ { { y ( 0 ^ { + } ) = A + B + 1 / 3 = 1 } } \\ { { y ^ { \prime } ( 0 ^ { + } ) = - 2 A - 4 B - 1 / 3 = 2 } } \\ { { y ( t ) = \displaystyle \frac { 5 } { 2 } \mathrm { e } ^ { - 2 t } - \displaystyle \frac { 1 1 } { 6 } \mathrm { e } ^ { - 4 t } + \displaystyle \frac { 1 } { 3 } \mathrm { e } ^ { - t } , t > 0 } } \end{array}
$$

## 基于求解常系数微分方程的方法不足之处

若输入信号发生变化，须全部重新求解

若初始条件发生变化，须全部重新求解

若微分方程激励项较复杂，则难以处理

难以体现信号与LTI系统的内在作用机理

## 2.基于零输入响应与零状态响应的方法

根据LTI系统的线性特性，将系统响应看作是由系统的初始状态与输入信号分别作用于系统而产生的响应之叠加。

![](.memoria/images/42a10490411914152f07bbbb126b0f4a3ed4ac02bffd84ecd0af1e6dd0333760.jpg)

完全响应 $y ( 1 ) = \sum \limits _ { k = 4 } ^ { \infty } \frac { 1 } { n ! } \lambda$ 响应 $y _ { \mathrm { z i } } ( t )$ +零状态响应 $y _ { _ \mathrm { / s } } ( t )$

## 零输入响应

输入信号为零，仅由系统的初始状态单独作用于系统而产生的响应称为零输入响应，记为 $y _ { \mathrm { z i } } ( t )$ o

![](.memoria/images/1b47c197b73815baa58cf5eec68cdad20e440dbbfc2422762f8465a4819d1839.jpg)

屯容放屯系统

## 2. 基于零输入响应与零状态响应的方法

## 零输入响应

输入信号为零，仅由系统的初始状态单独作用于系统而产生的响应称为零输入响应，记为 $y _ { \mathrm { z i } } ( t )$ o

系统没有外部的输入，只有电容的初始储能。

![](.memoria/images/c8ba538d69a124cb2b17b12de26651acc2c3f4307d4580826bb2a1a7e86f02fe.jpg)

屯容放电系统

## 2. 基于零输入响应与零状态响应的方法

## 零输入响应

描述连续LTI系统的线性常系数微分方程为

$$
\begin{array} { c } { { y ^ { ( n ) } ( t ) + a _ { n - 1 } y ^ { ( n - 1 ) } ( t ) + \cdots + a _ { 1 } y ^ { \ast } ( t ) + a _ { 0 } y ( t ) } } \\ { { = b _ { m } x ^ { ( m ) } ( t ) + b _ { m - 1 } x ^ { ( m - 1 ) } ( t ) + \cdots + b _ { 1 } x ^ { \ast } ( t ) + b _ { 0 } x ( t ) } } \\ { { \nmid \lambda x ( t ) = 0 } } \end{array}
$$

当输

$$
y ^ { ( n ) } ( t ) + a _ { n - 1 } y ^ { ( n - 1 ) } ( t ) + \cdots + a _ { 1 } y ^ { \prime } ( t ) + a _ { 0 } y ( t ) = 0
$$

上式为齐次方程，因此零输入响应具有齐次解的形式

## 2. 基于零输入响应与零状态响应的方法

## 零状态响应

初始状态为零，仅由系统的外部信号x(t)产生的响应称为系统的零状态响应，用 $y _ { \mathrm { z s } } ( t )$ 表示。

电容的初始储能为零，仅由外部输入作用而产生的输出。

![](.memoria/images/272806f29c73c747c96be25e9f17ca152c79f07f48d1e0e0101705a96e2020c1.jpg)

屯容充电系统

![](.memoria/images/9307ecf94cb74eba760dbe1e8c5b61da79b15b362e83ab85220b31ecc195c9b0.jpg)

电容电压示总图

## 2. 基于零输入响应与零状态响应的方法

## 零状态响应分析方法

(1) 输入信号x(t)表示为单位冲激信号δ(t)的线性组合

(2) 分析δ(t)作用于LTI系统的零状态响应—冲激响应h(t)

(3) 利用LTI系统的特性，即可得系统的零状态响应 $y _ { \mathrm { z s } } ( t )$

## 2. 基于零输入响应与零状态响应的方法

## 零状态响应

![](.memoria/images/46114f75587513e9dae379d112164e086ff213ad36529a46597a1cd8403a7a99.jpg)

## 2. 基于零输入响应与零状态响应的方法

系统响应y(t) = 零输入响应 $y _ { \mathrm { { _ \mathrm { i } } } } ( t ) +$ 零状态响应 $y _ { 7 s } ( t )$

求解齐次微分方程

$$
y _ { \tau s } ( t ) = x ( t ) * h ( t )
$$

信号与系统作用机理

$$
\nu _ { \mathrm { z i } } ( t )
$$

$$
h ( t )
$$

$$
\nu _ { \mathrm { z s } } ( t )
$$

## 连续LTI系统的零输入响应

输入信号为零，仅由系统的初始状态单独作用而产生的响应称为零输入响应，记为 $y _ { \mathrm { z i } } ( t )$ 。

数学模型:

$$
y ^ { ( n ) } ( t ) + a _ { n - 1 } y ^ { ( n - 1 ) } ( t ) + \cdots + a _ { 1 } y ^ { \prime } ( t ) + a _ { 0 } y ( t ) = 0
$$

求解过程

1. 求出微分方程对应的特征根

2. 根据特征根确定零输入响应的形式

3. 代入系统的初始状态，解出待定系数

零输入响 $\dot { \operatorname { W } } \dot { \boldsymbol { y } } _ { \mathrm { z i } } ( t )$ 的形式

(1) 特征根出现不等实根 $s _ { 1 } , s _ { 2 } , . . . , s _ { n }$

$$
y _ { \mathrm { z i } } ( t ) = K _ { \mathrm { l } } \mathrm { e } ^ { s _ { 1 } t } + K _ { 2 } \mathrm { e } ^ { s _ { 2 } t } + \cdots + K _ { n } \mathrm { e } ^ { s _ { n } t }
$$

(2) 特征根出现相等实根 $s _ { 1 } { = } s _ { 2 } { = } . . . { = } s _ { n } { = } s$

$$
y _ { \mathrm { z i } } ( t ) = K _ { \mathrm { l } } \mathrm { e } ^ { s t } + K _ { \mathrm { 2 } } t \mathrm { e } ^ { s t } + \cdots + K _ { n } t ^ { n - 1 } \mathrm { e } ^ { s t }
$$

(3) 特征根出现成对共轭复根 $s _ { i } = \sigma _ { _ i } \pm \mathrm { j } \omega _ { { i } }$

$$
y _ { \mathrm { z i } } ( t ) = \mathrm { e } ^ { \sigma _ { i } t } ( K _ { 1 } \cos { \omega _ { i } t } + K _ { 2 } \sin { \omega _ { i } t } )
$$

【例】已知描述某连续LTI系统的微分方程为

$$
y " ( t ) + 6 y " ( t ) + 8 y ( t ) = x ( t ) , t > 0
$$

初始状态 $\scriptstyle \gamma ( 0 ^ { - } ) = 1 , \gamma ^ { \prime } ( 0 ^ { - } ) = 2$ ，求零输入响应 $y _ { \mathrm { \Omega / i } } \left( t \right)$ U

解：特征方程为

$$
s ^ { 2 } + 6 s + 8 = 0
$$

特征根为

$$
s _ { 1 } = - 2 , s _ { 2 } = - 4
$$

(两不等实根)

$$
y _ { \gamma _ { \mathrm { i } } } ( t ) = K _ { 1 } \mathrm { e } ^ { - 2 t } + K _ { 2 } \mathrm { e } ^ { - 4 t }
$$

$$
y ( 0 ^ { - } ) { = } y _ { \mathrm { z i } } ( 0 ^ { - } ) { = } K _ { 1 } { + } K _ { 2 } { = } 1 ;
$$

$$
y ^ { \prime } ( 0 ^ { - } ) { = } y ^ { \prime } { _ { z \mathrm { i } } ( 0 ^ { - } ) } = - 2 K _ { 1 } { - } 4 K _ { 2 } { = } 2
$$

【例】已知描述某连续LTI系统的微分方程为

$$
y " ( t ) + 6 y " ( t ) + 8 y ( t ) = x ( t ) , t > 0
$$

初始状态 $\scriptstyle \gamma ( 0 ^ { - } ) = 1 , \gamma ^ { \prime } ( 0 ^ { - } ) = 2$ ，求零输入响应 $y _ { \mathrm { \Omega / i } } \left( t \right)$ U

解：特征方程为

$$
s ^ { 2 } + 6 s + 8 = 0
$$

特征根为

$$
s _ { 1 } = - 2 , s _ { 2 } = - 4
$$

(两不等实根)

$$
y _ { \gamma _ { \mathrm { i } } } ( t ) = K _ { 1 } \mathrm { e } ^ { - 2 t } + K _ { 2 } \mathrm { e } ^ { - 4 t }
$$

$$
y ( 0 ^ { - } ) { = } y _ { \mathrm { z i } } ( 0 ^ { - } ) { = } K _ { 1 } { + } K _ { 2 } { = } 1 ;
$$

$$
y ^ { \prime } ( 0 ^ { - } ) { = } y ^ { \prime } { _ { z \mathrm { i } } ( 0 ^ { - } ) } = - 2 K _ { 1 } { - } 4 K _ { 2 } { = } 2
$$

【例】已知描述某连续LTI系统的微分方程为：

$$
y ^ { \prime \prime } \left( t \right) + 4 y ^ { \prime } \left( t \right) + 4 y \left( t \right) = 3 x ( t ) , t > 0
$$

初始状态为 $y ( 0 ^ { - } ) = 2 , ~ y ^ { \prime } ( 0 ^ { - } ) = - 1$ ，求零输入响应 $y _ { \mathrm { z i } } ( t )$ o

解：特征方程为

$$
s ^ { 2 } + 4 s + 4 = 0
$$

特征根为

$$
s _ { 1 } = s _ { 2 } = - 2
$$

$$
y _ { \scriptscriptstyle \angle \mathrm { i } } ( t ) = K _ { 1 } \mathrm { e } ^ { - 2 t } + K _ { 2 } t \mathrm { e } ^ { - 2 t }
$$

(两相等实根)

## 2. 基于零输入响应与零状态响应的方法

目录  
✓连续LTI系统零输入响应 $\mathbf { y } _ { \mathrm { z i } } ( t )$   
√连续LTI系统的冲激响应h(t)  
✓连续LTI系统零状态响应 $\nu _ { \mathrm { z s } } ( t )$

## 连续LTI系统的冲激响应

在系统初始状态为零的条件下，以冲激信号δ(t)激励系统所产生的输出响应，称为系统的冲激响应，以符号h(t)表示。

![](.memoria/images/68d17d38aa0c54f03ad42822ea92f3b3a7471b086f94a34bd364f68b3866aded.jpg)

系统的冲激响应h(t)反映了连续LTI系统的时域特性。  
其只与系统本身特性有关，而与系统的输入和输出无关。

### 理工AI助教信号与系统

12/25 10:39

为何引入系统的冲激响应？

![](.memoria/images/6063878f0f8efe8a42ee490af6e2b92967e1343ad1f0a8a03b1539730f79849a.jpg)

### 一、求解零状态响应

在连续时间线性非时变系统中，为求解零状态响应，必须知道系统的冲激响应。因为零状态响应等于输入信号和系统冲激响应的卷积。

### 二、描述系统特性

冲激响应能反映系统的时域特性。不同的系统，其冲激响应不同，通过冲激响应可以区分不同的系统。

冲激响应与系统的因果性、稳定性等特性相关。例如，通过冲激响应是否满足绝对可积的条件，可以判断系统是否稳定

若描述连续LTI系统的线性常系数微分方程为

$$
\begin{array} { c } { { y ^ { ( n ) } ( t ) + a _ { n - 1 } y ^ { ( n - 1 ) } ( t ) + \cdots + a _ { 1 } y ^ { \prime } ( t ) + a _ { 0 } y ( t ) } } \\ { { = b _ { m } \underline { { { x ^ { ( m ) } ( t ) } } } + b _ { m - 1 } x ^ { ( m - 1 ) } ( t ) + \cdots + b _ { 1 } x ^ { \prime } ( t ) + b _ { 0 } x ( t ) } } \end{array}
$$

则连续LTI系统的冲激响应h(t)应满足

$$
\begin{array}{c} = \frac { h ^ { ( n ) } \left( { \iota } \right) + } { b _ { m } \delta ^ { ( m ) } \left( { \iota } \right) + b _ { m - 1 } \delta ^ { ( m - 1 ) } \left( { \iota } \right) + \cdots + b _ { 1 } \delta ^ { \prime } \left( { \iota } \right) + a _ { \circ } h \left( { \iota } \right) }  \\ { = \underbrace { \frac { h ^ { ( n ) } \left( { \iota } \right) + } { \left( { \iota } \right) + { \iota } } \frac { h ^ { ( n - 1 ) } \left( { \iota } \right) + \cdots + { \iota } } { \left( { \iota } \right) + { \iota } \left( { \iota } \right) + { \iota } \left( { \iota } \right) + { \iota } \left( { \iota } \right) + b _ { 0 } \delta \left( { \iota } \right) } } _ { \underline { { \mathrm { { u b } } } } \underline { { \mathrm { { \Sigma } } } } \underline { { \mathrm { { \Sigma } } } } } } \\ { = \underbrace { \mathrm { { u b } } _ { m } \delta ^ { ( m ) } \left( { \iota } \right) + b _ { m - 1 } \delta ^ { ( m - 1 ) } \left( { \iota } \right) + \cdots + { \iota } \frac { { \iota } \delta \left( { \iota } \right) + { \iota } \left( { \iota } \right) + { \iota } \left( { \iota } \right) } _ { \underline { { \mathrm { { u b } } } } \underline { { \mathrm { { \Sigma } } } } \underline { { \mathrm { { \Sigma } } } } } } _ { \underline { { \mathrm { { \Sigma } } } } } } \end{array}
$$

【例】描述某连续LTI系统的微分方程为 $y ^ { \prime } ( \iota ) + 3 y ( \iota ) = 2 x ( \iota )$ $\iota > 0$ 试求该系统的冲激响应h(t)。

分析：当系统输入信号x(t)为δ(t)，输出信号y(t)则为h(t)描述系统的微分方程为h'(t) + 3h(t) = 2δ(t)当 $t > 0$ 时， $\delta ( t ) = 0$ ，描述系统的微分方程为h'(t) + 3 h(t) = 0.

【例】描述某连续LTI系统的微分方程为 $y ^ { \prime } ( t ) + 3 y ( t ) = 2 x ( t )$ $t > 0$ 试求系统的冲激响应。

如何确定齐次解的待定系数?

将齐次解代入微分方程 $h ^ { \prime } ( t ) + 3 h ( t ) = 2 8 ( t )$

使方程两边同类项平衡，求出待定系数，得到 $h ( t )$ o

【例】描述某连续LTI系统的微分方程为

$\boxed { y ^ { * } ( t ) + 3 y ( t ) = 2 x ( t ) , t > 0 }$ 试求系统的冲激响应。

若 $y ^ { \prime } ( t ) + 3 y ( t ) = 2 x ( t ) + x ^ { \prime } ( t )$ ，t>0 则冲激响应有何变 $\# ?$

连续LTI系统的冲激响应h(t)满足微分方程

$$
{ \begin{array} { r l } & { \qquad h ^ { ( n ) } ( t ) + a _ { n - 1 } h ^ { ( n - 1 ) } ( t ) + \cdots + a _ { 1 } h ^ { \prime } ( t ) + a _ { 0 } h ( t ) } \\ & { = b _ { m } \delta ^ { ( m ) } ( t ) + b _ { m - 1 } \delta ^ { ( m - 1 ) } ( t ) + \cdots + b _ { 1 } \delta ^ { * } ( t ) + b _ { 0 } \delta ( t ) } \end{array} }
$$

(1) 当 $\scriptstyle n > m$ 时(假设特征根为不等实根)

$$
h ( t ) = ( \sum _ { i = 1 } ^ { n } K _ { i } \mathbf { e } ^ { s _ { i } t } ) \mathsf { u } ( t )
$$

(2) 当 $\pmb { n } \leq \pmb { m }$ 时,h(t)应含有冲激及其高阶导数

连续LTI系统的冲激响应h(t)满足微分方程

$$
{ \begin{array} { r } { h ^ { ( n ) } ( \iota ) + a _ { n - 1 } h ^ { ( n - 1 ) } ( \iota ) + \dots + a _ { 1 } h ^ { \ast } ( \iota ) + a _ { \mathfrak { o } } h ( \iota ) } \\ { = b _ { m } \delta ^ { ( m ) } ( \iota ) + b _ { m - 1 } \delta ^ { ( m - 1 ) } ( \iota ) + \dots + b _ { 1 } \delta ^ { \ast } ( \iota ) + b _ { 0 } \delta ( \iota ) } \end{array} }
$$

$$
h ( t ) = ( \sum _ { i = 1 } ^ { n } K _ { i } \mathrm { e } ^ { s _ { i } t } ) \mathrm { u } ( t ) + \sum _ { j = 0 } ^ { m - n } \ A _ { j } \delta _ { \cdot \cdot } ^ { ( j ) } ( t )
$$

由微分方程的特征根确定u(t)前的指数形式（假设为不等实根)

由微分方程δ(t)的最高阶导数与h(t)的最高阶导数确定 $8 ^ { \circ } \mathcal { H } ( 1 )$ 项。

## 2. 基于零输入响应与零状态响应的方法

目录  
√连续LTI系统零输入响应 $\mathrm { y } _ { \mathrm { z i } } ( t )$   
✓连续LTI系统的冲激响应 h(t)  
√连续LTI系统零状态响应 $\gamma _ { _ { \mathrm { { Z S } } } } ( t )$

## 连续LTI系统的零状态响应

若输入信号为x(t)，连续时间LTI系统的冲激响应为h(t)，则系统的零状态响应 $\gamma _ { \mathrm { z s } } ( t )$ 为：

$$
y _ { z s } ( t ) = \overbrace { \sum ( \underbrace { x ( t ) * h ( t ) } } ^ { = } ) = \int _ { - \infty } ^ { \infty } x ( \tau ) h ( t - \overbrace { \tau ) \mathrm { d } \tau } ^ { = } \quad \overbrace { ( \frac { \mathrm { d } \mathrm { d } } { \mathrm { d } \tau } \mathrm { d } \tau ) } ^ { = \infty }
$$

由此可见，连续LTI系统的零状态响应是输入信号与系统冲激响应的卷积积分，此揭示了信号与LTI系统在时域的内在作用机理。

## 信号卷积积分的计算

解析方法：

直接按照卷积积分的表达式进行计算

$$
y ( \iota ) = \widehat { \vert x ( \iota ) \vert } ^ { * } h ( \iota ) = \int _ { - \infty } ^ { \infty } x ( \tau ) h ( \iota - \tau ) \mathrm { d } \tau
$$

若信号x(t)与h(t)可用解析函数式表达，则可以利用解析方法来计算卷积积分。

【例】计算 $x ( t ) ^ { \ast } h ( t ) , x \Big ( t ) = { \mathrm e } ^ { - t } { \mathrm u } ( t ) , \Big ( \underbrace { h ( t ) = \mathrm u ( t ) } _ { \displaystyle \sqrt { \mathrm { ~ e ~ n ~ e ~ } } }$

解：由卷积定义

$$
\begin{array} { r l } { x ( t ) * h ( \underline { { t } } ) = \displaystyle \int _ { - \infty } ^ { \infty } } & { { } x ( \tau ) \cdot \underbrace { h ( t - \tau ) } _ { = \underline { { \tau } } } \mathrm { d } \tau } \\ { = \displaystyle \int _ { - \infty } ^ { \infty } } & { { } \mathrm { e } ^ { - \tau } \mathbf { u } ( \tau ) \cdot \mathbf { u } ( t - \tau ) \mathrm { d } \tau } \end{array} \qquad \Longrightarrow { }
$$

由 $\mathrm { u } ( \tau ) \mathrm { u } ( t - \tau )$ 得到

$$
= \left\{ \begin{array} { l l } { \displaystyle \int _ { 0 } ^ { t } \ e ^ { - \tau } \mathrm { d } \tau = \underbrace { 1 - \mathrm { e } ^ { - \tau } , } _ { \displaystyle t < 0 } , } \end{array} \right.
$$

由此可得 $x ( t ) ^ { * } h ( t ) = ( 1 - \mathrm { e } ^ { - t } ) \mathsf { u } ( t )$

【例】计算 $x ( t ) \ast h ( t ) , x ( t ) = \underbrace { 2 \mathrm { e } ^ { - 2 t } \mathrm { u } \left( t \right) } _ { \mathrm { ~ } } h ( t ) = \underbrace { 3 \mathrm { e } ^ { - t } \mathrm { u } } _ { \mathrm { ~ } }$ (t)

解:

$$
\begin{array}{c} \begin{array} { r l } { { } } & { { 2 } \mathrm { e } ^ { - 2 \tau } \mathrm { u } \left( t \right) \ast 3 \mathrm { e } ^ { - \tau } \mathrm { u } \left( t \right) } \\ { } & { { } = \displaystyle \int _ { - \infty } ^ { + \infty } 2 \mathrm { e } ^ { - 2 \tau } \mathrm { u } \left( \tau \right) \cdot 3 \mathrm { e } ^ { - ( t - \tau ) } \mathrm { u } \left( t - \tau \right) \mathrm { d } \tau } \\ { } & { { } = \displaystyle \left. 6 \int _ { 0 } ^ { t } \mathrm { e } ^ { - 2 \tau } \mathrm { e } ^ { - ( t - \tau ) } \mathrm { d } \tau , \quad t > 0 \right.} \\ { } & { { } \quad t < 0 } \end{array}   \end{array}
$$

$$
\overbrace { \int ^ { \alpha t } \mathbf { u } ( t ) \ast \mathrm { e } ^ { \beta t } \mathbf { u } ( t ) } ^ { \left( \alpha t \right) } = \left\{ \begin{array} { l l } { \displaystyle \frac { 1 } { \beta - \alpha } ( \mathrm { e } ^ { \beta t } - \mathrm { e } ^ { \alpha t } ) \mathrm { u } ( t ) , } & { \alpha \neq \beta } \\ { t \mathrm { e } ^ { \alpha t } \mathrm { u } ( t ) , } & { \alpha = \beta } \end{array} \right.
$$

图形方法: $y ( t ) = x ( t ) * h ( t ) = \int _ { - \infty } ^ { \infty } x ( \tau ) h ( t - \tau ) \mathrm { d } \tau$ 图形法计算卷积积分的步骤：

(1)将x(t)和h(t)中的自变量由t改为τ;

(2)将其中一个信号翻转得h(-τ)，再平移t得到h(t一τ);$h ( \tau ) \xrightarrow { \frac { \# \# \mathcal { H } } { \# \mathcal { H } } } h ( - \tau ) \xrightarrow { \# \# \mathcal { H } } h ( - ( \tau - \iota ) ) = h ( \iota - \tau )$

(3) 将x(t)与h(t-τ)相乘，对乘积后信号进行积分。

(4)不断改变平移量t，分别计算x(t) h(t=)的积分。

![](.memoria/images/6e0fb3591d5e3acb02d7b4bc9267d0df1d425ff0126dfb6630f8c5d7bd9a63b7.jpg)

【例】计算 $y ( t ) = x ( t ) ^ { * } h ( t )$ 。

$$
y ( t ) = \int _ { - \infty } ^ { \infty } x ( \tau ) h ( t - \tau ) \mathrm { d } \tau
$$

解：

![](.memoria/images/ca768d2078479774fb61d272994d9ad792e6819a553810a8821035524d989be0.jpg)

![](.memoria/images/65169a3a856efeed4b070b307fece659a5b9ff5f516e77c4f2db199dbceecb7a.jpg)

![](.memoria/images/bc1684e8141910a92e9ed19635e98632336ff1b2060055ce83739a29f476bc72.jpg)

![](.memoria/images/68c5d3040b05136c2f16155f0783de75cadb99f0bcca6136b5e0e8ce65c73506.jpg)

【例】计算 $y ( t ) = x ( t ) ^ { * } h ( t )$ 。

$$
y ( t ) = \int _ { - \infty } ^ { \infty } x ( \tau ) h ( t - \tau ) \mathrm { d } \tau
$$

解：

![](.memoria/images/016c2073b905a997a610c05dcfe5dfbc22db7820b49970c1ee54271e024b9e09.jpg)

![](.memoria/images/1c538587699d43b89201bfe5df469df4c4df34cd54ba44412963e46d2e14e161.jpg)

![](.memoria/images/7a7e10566d41fd3a8fff9254b586daf15c557952660543e419aeb18a48fe74f6.jpg)

![](.memoria/images/5738f771216fc6f69f511255b69a8ae6c06b9229bec8dce99c9a8907b74b134e.jpg)

(2) $0 \leq t < 1$

![](.memoria/images/f557328f5c132a7a79cb894f3dd1aa553ea3bc3429e1f95f8869055ffb98ac88.jpg)

$$
\begin{array} { l } { { \displaystyle y ( { \boldsymbol { \dot { \iota } } } ) = \int _ { - \infty } ^ { \infty } x ( { \boldsymbol { \tau } } ) h ( { \boldsymbol { \iota } } - { \boldsymbol { \tau } } ) \mathrm { d } { \boldsymbol { \tau } } } } \\ { { \displaystyle \ = \int _ { 0 } ^ { \tau } 1 \times 1 \mathrm { ~ d } { \boldsymbol { \tau } } = { \boldsymbol { \iota } } } } \end{array}
$$

【例】计算 $y ( t ) = x ( t ) ^ { * } h ( t )$ 。

$$
y ( t ) = \int _ { - \infty } ^ { \infty } x ( \tau ) h ( t - \tau ) \mathrm { d } \tau
$$

解：综上可得：

![](.memoria/images/4fd953a07ff3eaa4e71e643f2dab434590e681c1a92ff849bb679028b6533443.jpg)

![](.memoria/images/fc2b6f8344425e6cc1b5e4e51349b7eda67290f0ac5554de7223fd2d1f13ee6a.jpg)

![](.memoria/images/b6c6a485013159716dc27844f86a4e213735d65c63fe6db6256e0863d33803d9.jpg)

两不等宽矩形的卷积为等腰梯形，下底为两信号宽度之和，上底为两信号宽度之差，高为两信号最大重合时的面积。

## 信号卷积积分的性质

(1) 交换律： $x _ { 1 } ( t ) \ast x _ { 2 } ( t ) = \underline { { x _ { 2 } ( t ) } } \ast \underline { { x _ { 1 } ( t ) } }$

(2)分配律： $[ x _ { 1 } ( t ) + x _ { 2 } ( t ) ~ ] ^ { * } x _ { 3 } ( t ) = x _ { 1 } ( t ) ^ { * } x _ { 3 } ( t ) + x _ { 2 } ( t ) ^ { * } x _ { 3 } ( t )$

(3)结合律： $[ x _ { 1 } ( t ) ^ { * } x _ { 2 } ( t ) \ : ] ^ { * } x _ { 3 } ( t ) = x _ { 1 } ( t ) ^ { * } [ \ : x _ { 2 } ( t ) ^ { * } \ : x _ { 3 } ( t ) \ : ]$

平移特性：

若

则

$$
x _ { 1 } ( \iota ) \ast x _ { 2 } ( \iota ) = y ( \iota )
$$

$$
x _ { 1 } ( t \underset {  } { - } t _ { 1 } ) ^ { * } x _ { 2 } ( t \underset {  } { - } t _ { 2 } ) { = } \big \langle \underset {  } { - } ( t { - } t _ { 1 } { - } t _ { 2 } ) \big \rangle
$$

$$
x _ { 1 } ( t - 2 ) \div x _ { 2 } ( t - 2 ) \neq y ( t - 2 )
$$

等效特性： $\underbrace { x _ { 1 } ( t ) * x _ { 2 } ( t ) } _ { \substack { \longrightarrow } } = \underbrace { x _ { 1 } ^ { ( \star \bigtriangledown ) } ( t ) } _ { \substack { \longrightarrow } } * \underbrace { x _ { 2 } ^ { ( \star ) } ( t ) } _ { \substack { \longrightarrow } } = \widehat { x _ { 1 } ^ { ( \star ) } ( t ) } * \widehat { x _ { 2 } ^ { ( \star ) } ( t ) }$

微分特性：

若x(t) $* h ( t ) = y ( t )$ ，则 $x ^ { \prime } ( t ) \ast h ( t ) = x ( t ) \ast \underline { { h ^ { \prime } ( t ) } } = y ^ { \prime } ( t )$

$$
x ( t ) \xrightarrow { * } \delta ( t ) = x ( t ) \implies \underbracket { x ( t ) ^ { * } \delta ^ { * } ( t ) = x ^ { * } ( t ) }
$$

积分特性：

若x $( t ) ^ { * } h ( t ) = y ( t )$ ，则 $\underline { { { x } } } ^ { ( - 1 ) } ( t ) * h ( t ) = x ( t ) * \widetilde { h ^ { ( - 1 ) } } ( t ) = \widehat { { y } } ^ { ( - 1 ) } ( t )$

$$
x ( t ) ^ { * } \textrm { \& } ( t ) = x ( t ) \implies x ( t ) ^ { * } \textrm { u } ( t ) = \int _ { \infty } ^ { t } x ( \tau ) \textrm { d } \tau = x ^ { ( - 1 ) } ( t )
$$

![](.memoria/images/b7520687029672975913e057c1203a1ec89ad805ebaca35af373fdc19fccbe4b.jpg)

三角波

![](.memoria/images/3337eef3c9ca256a696c547da4dac58ff81f03ca652ae96f4c5f568653885835.jpg)

周期冲激串信号

解：周期冲激串信号 $\tilde { x } _ { 2 } ( \iota ) = \cdots + \delta ( \iota + T ) + \delta ( \iota ) + \delta ( \iota - T ) + \cdots$ 利用卷积的平移特性 $x ( t ) \ast \delta \left( t - T \right) = \underline { { x ( t - T ) } }$ 求出三角波分别与 $\widetilde { x } _ { 2 } ( t )$ 中各冲激信号的卷积，利用卷积分配律将各个卷积结果相加即可。

【例】计算信号 ${ \bf \ddot { \boldsymbol { x } } } _ { 1 } ( t )$ 与 $\widetilde { x } _ { 2 } ( t )$ 当 $T { = } 2$ 和 $T { = } 1$ 时的卷积。

![](.memoria/images/56fc182eff55a08b009363a4f682dc75e3c18d8597ea637f07092d86c665c03b.jpg)

三角波

![](.memoria/images/864375f5e5c92104899d599f880bf7490c7a865726ab0342a7e5dea35199cf19.jpg)

周期冲激串信号

解：周期冲激串 $\tilde { x } _ { 2 } ( \iota ) = \cdots + \delta ( \iota + 2 ) + \delta ( \iota ) + \delta ( \iota - 2 ) + \cdots$

![](.memoria/images/a5eb73607d2aeb05d3600a7bbb291c812e09f315387499677ce6f4b374aea055.jpg)

![](.memoria/images/92ad7ab129ec562c1283697a079ebc8e41506f19614b722c49316e130ada5604.jpg)

![](.memoria/images/e590523db0d44ef19f41a4ed7c0e3b0ab2135708ac102ea6cbba3a10c679bdf6.jpg)

$$
x ( t ) ^ { * } \ \& ( t - 2 ) = x ( t - 2 )
$$

【例】计算信号 $x _ { 1 } ( t )$ 与 $\widetilde { x } _ { 2 } ( t )$ 当T=2和T=1时的卷积。

![](.memoria/images/b8faa5c6698d7ccc26f2feb69dfb1eeb2e8825cbca1ee02d86dea89f39ea16ac.jpg)

三角波

![](.memoria/images/256bfe29d436f06c74e43717c016c2440e6557baa9c793b95504e4abf4e5dae4.jpg)

T=2 周期冲激串信号

解：周期冲激串 $\tilde { x } _ { 2 } ( t ) = \cdots + \delta ( t + 2 ) + \delta ( t ) + \delta ( t - 2 ) + \cdots$

![](.memoria/images/70e12427f7534468b184b2b760200838844fec4c8347720b658e55fe72fe0ea5.jpg)

![](.memoria/images/b7c0e26e1845be5c6eadc96b27da67781bf515ce6f48cf7b8900f7bc8278fd27.jpg)

![](.memoria/images/ef33cfb54ecccc712712ca23aeedb034d0e1dc0d43deb6d4feb81506a292c59e.jpg)

![](.memoria/images/d1a63285622d9674fc66452138fbc1e591a50e87c5db39de82aa509bcf0aef11.jpg)

【例】计算信号 $x _ { 1 } ( t )$ 与 $\widetilde { x } _ { 2 } ( t )$ 当T=2和T=1时的卷积。

![](.memoria/images/7ed863326d4b5bf5b1ee320ce31c1a6e8e9e5f4a3610ea372c1d79cc9264dbf0.jpg)

三角波

![](.memoria/images/ae0218744023f118482515e32b39b123e254af61f50c3eb668cac8068415157d.jpg)

周期冲激串信号

解：周期冲激串 $\tilde { x } _ { 2 } ( t ) = \cdots + \delta ( t + 1 ) + \delta ( t ) + \delta ( t - 1 ) + \cdots$

![](.memoria/images/1f8c9ac3c8616e64726f02760347b08642e7b3b5e8d5cb526fa872b6e085cfef.jpg)

【例】利用平移特性及 ${ \mathrm { u } } ( t ) ^ { * } { \mathrm { u } } ( t ) { = } r ( t )$ ，计算 $\nu ( t ) = x ( t ) \ast h ( t )$ 。

![](.memoria/images/ce1a3a9d01093f649aa130360d941d936216cfc6c8fa9d6b85ce2f693f39f217.jpg)

![](.memoria/images/e3271ecfef93b342b7e041bb4173dfd7034713f3efb1d093eac0ed3383a76749.jpg)

解: $y ( t ) = x ( t ) ^ { * } h ( t ) = [ \mathrm { ~ u ( } t ) - \mathrm { u ( } t - 1 ) ] ^ { * } [ \mathrm { ~ u ( } t ) - \mathrm { u ( } t - 2 ) ]$ $= \mathrm { u } ( t ) ^ { \ast } \mathrm { u } ( t ) - \mathrm { u } ( t - 1 ) ^ { \ast } \mathrm { u } ( t ) - \mathrm { u } ( t ) ^ { \ast } \mathrm { u } ( t - 2 ) + \mathrm { u } ( t - 1 ) ^ { \ast } \mathrm { u } ( t - 2 )$ $= r ( t ) - r ( t - 1 ) - r ( t - 2 ) + r ( t - 3 )$

【例】利用信号卷积的等效特性，计算 $y ( t ) = x ( t ) ^ { * } h ( t )$ o

![](.memoria/images/1a5254d927aac07e40346ac89fd449770e6f011a56780abb68da859546b4b352.jpg)

![](.memoria/images/40c2cf39ff9fa042376ba9cadf0d8cc3898e268430fc16b0ec556edf58784905.jpg)

解: $x \ ^ { \prime } ( t ) = 8 \ ( t ) - 8 \ ( t { - } 1 )$

$$
y ^ { \prime } \left( t \right) = x ^ { * } ( t ) ^ { * } h ( t ) = h ( t ) - h ( t - 1 )
$$

$$
y ( t ) = \int _ { - \infty } ^ { t } ~ [ h ( t ) - h ( t - 1 ) ] \mathrm { d } t
$$

![](.memoria/images/f06db6c466a94937373538b29be391b0c2386b7405c0ce84b12e3619e29c2827.jpg)

![](.memoria/images/c4f44c8796c3d32754fd4e7749147615fe8e502e3020d37467d142bc6c72cf39.jpg)
