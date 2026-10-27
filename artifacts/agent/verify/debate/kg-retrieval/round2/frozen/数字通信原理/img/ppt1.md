## 信号的定义

(1)数学表达式——函数

广义：x(t)、x[k]

具体： ${ \boldsymbol x } ( t ) { = } \sin ( t )$ 、 $\mathbf { \boldsymbol { x } } [ k ] { = } \mathbf { 0 } . 5 ^ { k }$

本课中“信号”与“函数”混用

---

## 信号的分类

确定信号与随机信号

连续时间信号与离散时间信号

周期信号与非周期信号

能量信号与功率信号

---

# 1. 确定信号与随机信号

➢ 确定信号：信号在定义域上的每一点都有确定值。

![](.memoria/images/233c54d2880e7e06ac4a4c7578ae5505274ecf50b88d07dc854c143b42aa64fa.jpg "width=490")

| t | x(t) |
| --- | --- |
| -3 | 0 |
| -2 | 0 |
| -1 | 0 |
| 0 | 1 |
| 1 | 0 |
| 2 | 0 |
| 3 | 0 |

---

# 1. 确定信号与随机信号

# ➢ 随机信号：不满足确定信号定义的信号。

随机信号是指在任意时刻的取值具有不确定性，无法用确定性的时间函数精确描述，其未来值不能完全预测，只能通过概率统计特性来表征用的信号。

![](.memoria/images/29d8127d3ab1d3e4f28a18e87c7b8dc8a87a28869e1f5f9c67d4e88bee1f6152.jpg)

| Time | Value |
| --- | --- |
| 0.00 | ~0.1 |
| 0.05 | ~0.2 |
| 0.10 | ~0.1 |
| 0.15 | ~0.3 |
| 0.20 | ~0.2 |
| 0.25 | ~0.1 |
| 0.30 | ~0.2 |
| 0.35 | ~0.1 |
| 0.40 | ~0.1 |

语音信号

![](.memoria/images/0be75f1359bb7c56adf7516bb7c197690c6633bf430d18b05f127834de6cd9e8.jpg)

随机信号的一个样本
噪声信号

---

# 2. 连续时间信号与离散时间信号

连续时间信号：信号的定义域为连续区间，通常以 $x(t)$ 表示， $t\in \mathbf{R}$

![](.memoria/images/e19113fbe3b2d32a721102aa43dac169de1e0f27f07fc024464a50795dd01b5a.jpg)

| t | x(t) |
| --- | --- |
| 0 | 0 |
| ~0.1 | 110 |
| ~0.2 | 0 |
| ~0.3 | -110 |
| ~0.4 | 0 |
| ~0. |

定义域为连续区间

![](.memoria/images/18aa0b13ae176241f294cb5a043829fd941999f275eb9b1eb5a61b4a9c9ff3ad.jpg)

允许在其定义域上存在有限个间断点。

---

## 2. 连续时间信号与离散时间信号

离散时间信号：信号的定义域为一些离散点通常以x[k]表示,k∈I。

![](.memoria/images/e8bf840b28830e21ab1ba637c388992293e8e4f2ad5068d9095dd84e3e973391.jpg)

定义域为离散点

![](.memoria/images/d01b8ba67a550f8e5c76c1a3091777bb8404e5258a3575956330ceddb006e861.jpg)

定义域为离散点

(画波形图时，纵轴也可以省略)

---

## 2. 连续时间信号与离散时间信号

## 离散时间信号：信号的定义域为一些离散点。

![](.memoria/images/2c68797ff44ab140efd1926330688963f8bfb52e63c0498cd86d8a207d450aec.jpg)

居民消费价格指数

![](.memoria/images/017006f017fe482d318bf90116412117024f87efe196fd4c80bd104fcc96813c.jpg)

![](.memoria/images/f77328965b17d21cfcf17d5122f6e5113c1143fc2e9102d3560454960de7dead.jpg)

成绩分布

上证指数

![](.memoria/images/7ad6f83abccaf89fbdd2d219a3a940130870edd545c3a1ed357061e292ac9258.jpg)

北京市常住人口

---

# 2. 连续时间信号与离散时间信号

两者关系

![](.memoria/images/74d64e1f493fe11d0ffa33e6f9caea39f520e2b323ea91651fb54e7b44670b83.jpg)

---

## 2. 连续时间信号与离散时间信号

## 模拟信号和数字信号

·模拟信号：幅度连续的连续时间信号（连续信号）。

·数字信号：幅度离散的离散时间信号（离散信号）。

![](.memoria/images/2d0265e4ebe1f0db591eefc69423460c996646d6dd078bf22cf4b6c7df8904be.jpg)

模拟信号

![](.memoria/images/b2e98448f5df70c7427e5ab44ded18a949be2f6471c71c8efdd81b0906a3dfec.jpg)

离散信号

![](.memoria/images/d9ad2b0121e3dcd9dc79c1d6146469c0c02513cb59601e8326755888609c1066.jpg)

数字信号
✓严谨来说：离散信号的幅度可以是连续也可以是离散的。
✓很多经典教材中，为了强调“数字化”的关键步骤，经常把“离散时间信号”这个术语特指为“尚未量化的采样信号”，而把“数字信号”单独拎出来作为量化后的产物。

---

# 3. 周期信号与非周期信号

连续时间周期信号： $\forall t\in \mathbb{R}$ ，存在正数 $T$ ，使得

$x(t + T) = x(t)$ 成立, 则 $x(t) = x(t)) = 1$ ，满足上述条件的最小正数 $T$ ，称为信号的基本周期。

➢离散时间周期信号： $\forall k\in I$ ，存在正整数N，使得

$x[k+N]=x[k]$ 成立，则 $x[k]$ 为周期信号。

---

# 3. 周期信号与非周期信号

![](.memoria/images/b07028999cc8d38d22d02c5f0a2f7191a408f47362674ea114e157e997f8dae9.jpg)

H34560 128Hz
H34570 256Hz
H34580 512Hz
H34590 1024Hz
H34600 2048Hz

测听力音叉

![](.memoria/images/09c0aff9bd111383b354d533ddc87a8956882f77807d4bfd87534f0d46868651.jpg)

| Segment | Waveform Description |
| --- | --- |
| 1 | Periodic wave with peak at 1 and trough at -1 |
| 2 | Periodic wave with peak at 1 and trough at -1 |
| 3 | Periodic wave with peak at 1 and trough at -1 |
| 4 | Periodic wave with peak at 1 and trough at -1 |
| 5 | Periodic wave with peak at 1 and trough at -1 |

音叉发出信号对应波形

---

# 3. 周期信号与非周期信号

例1：判断正弦信号 $x(t) = \sin (\omega_0t)$ 是否是周期信号。

解：因为 $x(t + T) = \sin \omega_0(t + T) = \sin (\omega_0t + \omega_0T)$

要使其为周期信号，必须有

![](.memoria/images/678fff9c03d1f1c3aaf43bba8e9745559fee8c93b5742d66e19956999ae8249b.jpg)

ω₀ T = m2π, m = 整数
T = m(2π/ω₀), m = 整数

连续正弦信号是周期信号

因此， $\sin(\omega_{0}t)$ 是周期为 $2\pi/|\omega_{0}|$ 的周期信号。

---

# 3. 周期信号与非周期信号

例2：判断离散正弦信号 $x[k] = \sin (\Omega_0k)$ 是否是周期信号。

解：因为 $x[k + N] = \sin \Omega_0(k + N) = \sin (\Omega_0k + \Omega_0N$

要使其为周期信号，必须有

$$
\begin{array}{c} \Omega_ {0} N = m 2 \pi , \quad m = \text {整数} \\ \ \ \ \text {有理数，} m \text {和} N \text {为正整数} \end{array}
$$

因此，只有当 $\left|\Omega_{0}\right|/2\pi$ 可表示为有理数时才为周期信号。

---

# 3. 周期信号与非周期信号

判断信号 \( x\left\lbrack  k\right)  = \sin \left( {\frac{\pi k}{3} - \frac{\pi }{4}}\right) 是否为周期。

A. 非周期信号
B. 周期信号，周期为6
C. 周期信号，周期为24

---

## 4. 能量信号与功率信号

能量信号：能量为非零的有限值，平均功率为零。

功率信号：能量为无限值，平均功率为非零有限值。

连续信号

离散信号

能量W

$$
W = \operatorname* { l i m } _ { T \to \infty } \int _ { - T } ^ { T } \left| x ( t ) \right| ^ { 2 } \mathrm { d } t
$$

$$
W = \operatorname* { l i m } _ { N \to \infty } \sum _ { - N } ^ { N } \bigl | x [ k ] \bigr | ^ { 2 }
$$

平均功率P

$$
P = \operatorname* { l i m } _ { T \to \infty } \frac { 1 } { 2 T } { \int _ { - T } ^ { T } \left| x ( t ) \right| ^ { 2 } \mathrm { d } t }
$$

$$
P = \operatorname* { l i m } _ { N \to \infty } \frac { 1 } { 2 N + 1 } \sum _ { - N } ^ { N } \bigl | x [ k ] \bigr | ^ { 2 }
$$

---

# 4. 能量信号与功率信号

能量信号：能量为非零的有限值，平均功率为零。
功率信号：能量为无限值，平均功率为非零有限值。

| 信号类型 | 总能量E | 平均功率P | 典型 |  |
|---|---|---|---|---|
| 能量信号 | 有限 | 等于0 | 等于0 |  |
| 功率信号 | 无穷大 | 等于0 | 等于0 |  |
| 非零能信号 | 无穷大 | 等于0 | 等于0 |  |

划分信号类型的“黄金法则”：

(1) 能量有限 $\Rightarrow$ 功率为 0

(2) 功率有限且不为 $0 \Rightarrow$ 能量无穷

---

## 4. 能量信号与功率信号

例3：计算周期信号 $x ( t ) = A \cos ( \omega _ { \scriptscriptstyle 0 } t )$ 的功率，A为非零的有限值。

解： $A \cos ( \omega _ { 0 } t )$ 是基本周期 $\scriptstyle { T _ { 0 } = 2 \pi / | \omega _ { 0 } | }$ 的周期信号。

由于周期信号有无限个周期，所以能量E为无限值。

其在一个基本周期内的能量为

$$
E _ { 0 } = \int _ { 0 } ^ { T _ { 0 } } \lvert \ x ( t ) \rvert ^ { 2 } \mathrm { d } t = \int _ { 0 } ^ { T _ { 0 } } A ^ { 2 } \cos ^ { 2 } ( \omega _ { 0 } t ) \mathrm { d } t = \frac { A ^ { 2 } T _ { 0 } ^ { \prime } } { 2 }
$$

对于周期信号，其平均功率可由一个周期内的能量除以周期而获得

$$
P = { \frac { { \cal { E } } _ { 0 } } { T _ { 0 } } } = { \frac { A ^ { 2 } } { 2 } }
$$

P是非零的有限值，因此是功率信号，且功率P只与幅值A有关。

---

## 4. 能量信号与功率信号

例4：判断直流信号x(t)=C是能量信号还是功率信号，C为非零的有限常数。

解：直流信号的能量为

$$
E = \operatorname* { l i m } _ { T \to \infty } \int _ { - T } ^ { T } | \ : x ( t ) | ^ { 2 } \mathrm { d } t \ = \operatorname* { l i m } _ { T \to \infty } \int _ { - T } ^ { T } C ^ { 2 } \mathrm { d } t = \infty
$$

平均功率为

$$
P = \operatorname* { l i m } _ { T \to \infty } \frac { 1 } { 2 T } \int _ { - T } ^ { T } \lvert x ( \iota ) \rvert ^ { 2 } \mathrm { d } \iota = \operatorname* { l i m } _ { T \to \infty } \frac { 1 } { 2 T } \int _ { - T } ^ { T } C ^ { 2 } \mathrm { d } \iota \ = \operatorname* { l i m } _ { T \to \infty } \frac { 2 C ^ { 2 } T } { 2 T } \ = C ^ { 2 }
$$

E是无限值，而P是非零的有限值，因此是功率信号。

幅值有限的周期信号和直流信号都是功率信号

---

## 4. 能量信号与功率信号

例5：判断信号 $\cdot x [ k ] { = } 0 . 5 ^ { k }$ 是能量信号还是功率信号。

解：信号的能量为

$$
\_ E = \operatorname* { l i m } _ { \stackrel { N \to \infty } { - } } \sum _ { k = - N } ^ { N } | x [ k ] | ^ { 2 } = \operatorname* { l i m } _ { N \to \infty } \sum _ { k = - N } ^ { N } ( 0 . 5 ) ^ { 2 k } = \infty
$$

信号的平均功率为

$$
P = \operatorname* { l i m } _ { N  \infty } { \frac { 1 } { 2 N + 1 } } \sum _ { k = - N } ^ { N } ( 0 . 5 ) ^ { 2 k } \quad = \infty
$$

E和P都是无限值，因此既不是能量信号也不是功率信号。

注意:一个信号可以既不是能量信号也不是功率信号，但不可能既是能量信号又是功率信号。

---

# 信号的分类小结

$\spadesuit$ 确定信号与随机信号
$\spadesuit$ 连续时间信号与离散时间信号
周期信号与非周期信号
$\spadesuit$ 能量信号与功率信号

---

# 系统的定义与分类

# 目录

√ 系统的定义
√ 实际的系统
√ 系统的描述
√ 系统的分类

---

## 系统的定义

英文中系统(system)一词来源于古代希腊文(systεma)意为由多个部分而组成的整体。

系统论创始人贝塔朗菲定义：系统是相互联系且相互作用的诸元素的综合体。

本课程定义：

系统是指由相互作用和依赖的若干单元组合而成的、具有特定功能的有机整体。

---

# 系统的定义

系统是指由相互作用和依赖的若干单元组成的、具有特定功能的整体。

![](.memoria/images/6ff22a65ac0f853c47ac03cc29eb5cd580b8f5e15058b48420211b3a9a31df1d.jpg)

```mermaid
graph LR
  A["信息源"] --> B["传感器"]
  B --> C["发送设备"]
  C --> D["信道"]
  D --> E["接收设备"]
  E --> F["传感器"]
  F --> G["有用信息"]
```

电视广播通信系统框图

---

# 系统的定义

系统是指由相互作用和依赖的若干单元组成的、具有特定功能的整体。

![](.memoria/images/8d57210bf8ba28198047bc38cf8965ebb0ca849fd5fdbdb60ee024fd122ffc22.jpg)

```mermaid
graph LR
  A["输入x(t)"] --> B["抗混滤波器"]
  B --> C["A/D"]
  C --> D["数字处理系统"]
  D --> E["D/A"]
  E --> F["平滑滤波器"]
  F --> G["输出"]
```

---

## 实际的系统

## 简单电路系统

![](.memoria/images/4e0b329c23d4b5b08355f2b2218d1673f8b79e721042a65bac2dead664b59f6c.jpg)

分压器

![](.memoria/images/13aad341756d967afe5de54b33ffa1e758572a0a3d7e22197378d4be28f7f567.jpg)

分流器

$$
\nu _ { { \mathrm { R } } 2 } ( t ) = { \frac { R _ { 2 } } { R _ { 1 } + R _ { 2 } } } \mathsf { u } ( t )
$$

---

# 实际的系统

# 简单电路系统

$$
\begin{array}{c} 1 = G \frac {A}{4} \\ 1 2 3 4 | 5 6 7 \dot {1}
$$

![](.memoria/images/78f2b411f031e28d574de4bcae238d6cf423da131193bbd822e1b87423b28329.jpg)

u(t)
R
C
v_c(t)

低通滤波器

![](.memoria/images/892312890fb262920f211fe38c21e2a83f94cd96c4ef0f49065e43bf6d06f2f2.jpg)

高通滤波器

---

# 系统的定义与分类

# 目录

√ 系统的定义
√ 实际的系统
√ 系统的描述
√ 系统的分类

---

# 系统的描述

系统描述：建立描述系统基本特性的数学模型

![](.memoria/images/59b9df9c80fec4bc6887e667a8c569f6e9f2bfa76630c108e3b5ec8bed3a10ad.jpg)

```mermaid
graph TD
  A["系统描述"] --> B["输入输出描述"]
  A --> C["状态变量描述"]
```

---

# 系统的描述

# 输入输出描述

![](.memoria/images/583e7ecee9f36ec2ebadab20fa4be494fbd8152ec076ddbfea5dde3095a5e57c.jpg)

x(t)
iR(t)
R
iL(t)
L
iC(t)
C
vC(t)
-

RLC并联电路

若输入为 $x(t)$ ，输出为 $v_{\mathrm{C}}(t)$ ，则输入和输出的关系为

$$
\frac {\mathrm{d} v _ {\mathrm{C}} ^ {2} (t)}{\mathrm{d} t ^ {2}} + \frac {v} \frac {\mathrm{d} v _ {\mathrm{C}} ^ {2}}{\mathrm{d} t} + \frac {1}{2} \frac {\mathrm{d} v _ {\mathrm{C}} ^ {2}}{\mathrm{d} t} + \frac {1}{2} \frac {\mathrm{d} v _ {\mathrm{C}} ^ {2}}{\mathrm{d} t} + \frac {1}{2} \frac {\mathrm{d} v _ {\mathrm{C}} ^ {2}}{\mathrm{d} t} + \frac {1}{2} v _ {\mathrm{C}} ^ {2} + \frac {1}{2} v _ {\mathrm{C}} ^ {2} + \frac {1}{2} v _ {\mathrm{C}} ^ {2} + \frac {1}{2} v _ {\mathrm{C}}{\mathrm{d} t ^ {2}} + \frac {1}{R C} \frac {\mathrm{d} v _ {\mathrm{C}} ^ {2}} + \frac {1}{2} v _ {\mathrm{C}} ^ {2} + \frac {1}{2} v _ {\mathrm{C}} ^ {2} + \frac {1}{2} v _ {\mathrm{C}} ^ {2} + \frac {1}{2} v _ {\mathrm{C}} ^ {2} + \frac {1}{2} v _ {\mathrm{C}} ^ {2} + \frac {1}{2} v _ {\mathrm{C}} ^ {2} + \frac {2}{2} v _ {\mathrm{C}} ^ {2} + \frac {2}{2} v _ {\mathrm{C}} ^ {2} + \frac {2}{2} v _ {\mathrm{C}} ^ {2} + \frac {2}{2} v _ {\mathrm{C}} ^ {2} + \frac {2}{2} v _ {\mathrm{C}} ^ {2} + \frac {2}{2} v ^ {2} + \frac {2}{2} v ^ {2} + \mathrm{d} t
$$

输入输出描述

$N$ 阶系统的数学模型： $N$ 阶微分方程或 $N$ 阶差分方程

---

## 系统的描述

## >状态变量描述

若输入为x(t)，计算 $i _ { \mathrm { R } } ( i ) , \ i _ { \mathrm { C } } ( i )$ ，则可先建立状态变量 $i _ { \mathrm { L } } ( t )$ $\nu _ { \mathrm { C } } ( \iota )$ 与输 $\lambda x ( t )$ 的关系

![](.memoria/images/048b1be0ad2b2797635a5306266a8f5de3f82e3fa79622957aeed88fac528fd8.jpg)

RLC并联屯路

$$
\begin{array} { l } { \displaystyle \frac { \mathrm { d } i _ { \mathrm { t } } ( t ) } { \mathrm { d } t } = \frac { 1 } { L } \nu _ { \mathrm { c } } ( t ) } \\ { \displaystyle \frac { \mathrm { d } \nu _ { \mathrm { c } } ( t ) } { \mathrm { d } t } = - \frac { 1 } { C } i _ { \mathrm { t . } } ( t ) - \frac { 1 } { R C } \nu _ { \mathrm { c } } ( t ) + \frac { 1 } { C } x ( t ) } \end{array}
$$

状态变量描述

N阶系统的数学模型：N个一阶微分方程组或一阶差分方程组

---

# 系统的分类

1. 连续时间系统与离散时间系统
2. 线性系统与非线性系统
3. 非时变系统 与时变系统
4. 因果系统与非因果系统
5. 稳定系统与非稳定系统

---

# 1. 连续时间系统与离散时间系统

连续时间系统:

系统的输入激励与输出响应均为连续时间信号

![](.memoria/images/35bca3884f0c5dfc6a0c3600bc54d7ebb0f7e96ab6422ae95da07efa528f826f.jpg)

```mermaid
graph LR
  A["x(t)"] --> B["连续时间系统"]
  B --> C["y(t)"]
```

离散时间系统：

系统的输入激励与输出响应均为离散时间信号

![](.memoria/images/cc17f1efa9d9021cc4199426b97740bfd1e045d33337863eb18b5977a50e395b.jpg)

```mermaid
graph LR
  A["&quot;x[k"]"] --> B["离散时间系统"]
  B --> C["&quot;y[k"]"]
```

---

离散时间系统

## 1. 连续时间系统与离散时间系统

## 连续时间系统和离散时间系统举例

![](.memoria/images/1e53c28f05a38e2abd8df72f3790de7b115ef2680461488b17f08f6cd18c7cb0.jpg)

由电阻、电容、电感、二极管、三极管、模拟放大器等模拟器件组成的电路

![](.memoria/images/3908780a1d44db529a2be3b171ef08a7b9e0a5f180eef7f4b5c413aa081dc074.jpg)

由门电路、触发器、计数器、寄存器、编码器、译码器、比较器等数字元件组成的电路

---

# 1. 连续时间系统与离散时间系统

连续时间系统和离散时间系统举例

![](.memoria/images/c20bb81a27c644873768376c8a573ebfbd0a38af230a8aa29fa8e7c37c4a9d47.jpg)

Portrait of a man with a beard, holding a small object (no visible text or symbols)

大哥大

![](.memoria/images/fd126f1932fa1f93aaeee83b7eb1f0e76936450f7e51529d17b5dc28de2b2add.jpg)

Abstract wave pattern with wavy lines, no text or symbols present

1G通信系统（连续时间系统）

---

## 2. 线性系统与非线性系统

线性系统：具有线性特性的系统。

均匀性也称为齐次性、比例性；
叠加性也称为可加性。

均匀特性与叠加特性

均匀特性可表示为

若 $x ( t ) \longrightarrow y ( t ) ,$ 则Kx(t) Ky(t)叠加特性可表示为

![](.memoria/images/ac341926896957d0102d68eb470dd8f53c14d71f475b12bd8aa510433e0ce9d1.jpg)

若

则

$$
\begin{array} { r l } { ~ } & { { } \xrightarrow { ~ x _ { 1 } ( t ) \longrightarrow y _ { 1 } ( t ) , ~ x _ { 2 } ( t ) \longrightarrow y _ { 2 } ( t ) } } \\ { ~ } & { { } \xrightarrow { ~ x _ { 1 } ( t ) + x _ { 2 } ( t ) ~ } \xrightarrow { ~ y _ { 1 } ( t ) + y _ { 2 } ( t ) ~ } } \end{array}
$$

---

# 2. 线性系统与非线性系统

线性系统：具有线性特性的系统。

均匀特性与叠加特性

同时具有均匀特性与叠加特性才称线性特性，可表示为

若 $x_{1}(t)\longrightarrow y_{1}(t),x_{2}(t)\longrightarrow y_{2}(t)$

则 $\alpha x_{1}(t)+\beta x_{2}(t)\longrightarrow\alpha y_{1}(t)+\beta y_{2}(t)$

其中 $\alpha$ 、 $\beta$ 为任意常数

---

# 2. 线性系统与非线性系统

# 线性系统举例

![](.memoria/images/7abaeaddceb94045ad27ce43d7f17781c179a795532a8885ef08d300d5a8e28c.jpg)

R₁-1Ω
x(t)
R₂-2Ω
vᵣ₂(t)

分压器

$$
\begin{array}{r l} v _ {R 2} (t) & = \frac {R _ {1}} \frac {R _ {2}}{R _ {1} + R _ {2}} \quad \text {或} \quad x (t) \\ & = \frac {2}{3} x (t) \end{array}
$$

当 $x(t) = 3\mathrm{V}$

$$
v _ {\mathrm{R2}} (t) = \frac {2}{3} x (t) = 2 \mathrm{V}
$$

当 $x(t)=2\times3V$ 时，

$$
v _ {\mathrm{R2}} (t) = \frac {2}{3} x (t) = 2 \times 2
$$

满足均匀性

---

## 2. 线性系统与非线性系统

## 线性系统举例

![](.memoria/images/61059a80335cfa8e18ac214cc5329a8905753a5dd309df39f311e7dd2d29966b.jpg)

分压器

$$
\begin{array} { c } { \displaystyle \nu _ { \mathrm { R 2 } } ( t ) = \frac { R _ { 2 } } { R _ { 1 } + R _ { 2 } } x ( t ) } \\ { \displaystyle = \frac { 2 } { 3 } x ( t ) } \end{array}
$$

若 $x ( t ) = x _ { 1 } ( t ) + x _ { 2 } ( t )$

当 $x _ { 1 } ( t )$ 单独作用时，

$$
\nu _ { { \scriptscriptstyle \mathrm { R } } 2 _ { - } 1 } ( t ) = \frac { 2 } { 3 } x _ { 1 } ( t )
$$

当 $x _ { 2 } ( t )$ 单独作用时，

$$
\nu _ { { \scriptscriptstyle \mathrm { R } } 2 _ { - } 2 } ( t ) = \frac { 2 } { 3 } x _ { 2 } ( t )
$$

当两者共同作用时，

![](.memoria/images/0f2ad8d26fcc4c75eb52471fade34c97b5ef72a135600c7898769ffd21ba0c03.jpg)

$$
\nu _ { { \scriptscriptstyle \mathrm { R } } 2 } ( t ) = \frac { 2 } { 3 } x ( t ) = \frac { 2 } { 3 } [ x _ { \scriptscriptstyle \perp } ( t ) + x _ { 2 } ( t ) ] = \nu _ { { \scriptscriptstyle \mathrm { R } } 2 } { \bf \nabla } _ { 1 } ( t ) + \nu _ { { \scriptscriptstyle \mathrm { R } } 2 } { \bf \nabla } _ { 2 } ( t )
$$

---

# 2. 线性系统与非线性系统

线性系统举例

电流作为输入，电压作为输出，系统是否线性？

![](.memoria/images/4ba8a30486f3495b58a2e8a79d89cdf0c74a7f3804a6e7fa6677e33a95d887fc.jpg)

Electrical circuit diagram with resistor R, with input voltage v_R(t) and output voltage v_R(t) labeled.

![](.memoria/images/4e6b481562d8b6ce67014cbc0059fcb0f99787c034567ee0f0916b3bdd003284.jpg)

Electrical circuit diagram with capacitor with input and output terminals labeled.

![](.memoria/images/1c79b9d449140fb08f10f794661a4d4540d82bb3f21ddd56f5e4542a75d4a071.jpg)

Electrical circuit diagram with inductance and voltage, with input voltage and output voltage labeled.

对于电容C，设 $i_{\mathrm{C}}(t) = \alpha i_{\mathrm{C1}}(t) + \beta i_{\mathrm{C}$

则 $v_{\mathrm{C}}(t) = \frac{1}{C}\int_{-\infty}^{t}[\alpha i_{\mathrm{C1}}(\tau$ )
则 $v_{\mathrm{C}}(t) = \frac{1}{C}\int_{-\infty}^{t}\left[\alpha i_{\mathrm{C1}}(\tau)\right]d\tau$

---

## 2. 线性系统与非线性系统

线性系统举例

电流作为输入，电压作为输出，系统是否线性？

![](.memoria/images/73e919d39045a36bb79a49478f1be32330cf7bbba69dff4dfe5b61963d1f2057.jpg)

![](.memoria/images/64cc15223cb1b9c82b5a8d2a054258dd22114ba3eb5d617e4d5f6860ae81a640.jpg)

![](.memoria/images/e0386d8cfa55bd5f05421f07a239445b4e5a2681b09f97c4ad8b4ac421e40607.jpg)

$$
\nu _ { \mathrm { { R } } } ( \iota ) = R i _ { \mathrm { { R } } } ( \iota )
$$

$$
\nu _ { \mathrm { c } } ( t ) = \frac { 1 } { C } \int _ { - \infty } ^ { t } i _ { \mathrm { c } } ( \tau ) \mathrm { d } \tau
$$

$$
\nu _ { \mathrm { l . } } ( t ) = L \frac { \mathrm { d } i _ { \mathrm { L } } ( t ) } { \mathrm { d } t }
$$

对于电感L，设 $i _ { \mathrm { L } } ( t ) = \alpha i _ { \mathrm { L 1 } } ( t ) + \beta i _ { \mathrm { L 2 } } ( t )$

则 $\nu _ { \mathrm { { l . } } } ( t ) = L \frac { \mathrm { d } [ \alpha i _ { \mathrm { L 1 } } ( t ) + \beta i _ { \mathrm { L 2 } } ( t ) ] } { \mathrm { d } t } = \alpha L \frac { \mathrm { d } i _ { \mathrm { L 1 } } ( t ) } { \mathrm { d } t } + \beta L \frac { \mathrm { d } i _ { \mathrm { L 2 } } ( t ) } { \mathrm { d } t }$ $= \alpha \nu _ { { \scriptscriptstyle 1 , 1 } } ( \iota ) + \beta \nu _ { { \scriptscriptstyle 1 , 2 } } ( \iota )$ 具有线性特性

电感是线性元件

---

# 2. 线性系统与非线性系统

# 线性系统举例

由线性元件（电阻、电容、电感等）、独立源构成的电路都是线性系统。

![](.memoria/images/c22c39adc4163d042fadff97c27199a48d9f225d8cd91d94e8f6327fef338613.jpg)

线性系统

---

## 2. 线性系统与非线性系统

[例1]已知连续时间系统的输入x(t)与输出y(t)约束关系如下，试判断这些系统是否为线性系统。(1) $y ( t ) = \frac { 3 x ( t ) + 4 } { 0 }$ (2) $y ( t ) = 4 x ^ { 2 } ( t )$ (3) $y ( t ) = 2 { \frac { \mathrm { d } x ( t ) } { \mathrm { d } t } } + x ( t )$ 解：(1)考察均匀特性$x ( t )  y ( t ) = 3 x ( t ) + 4$ $\frac { K x ( t ) } { \cosh } \to \frac { 3 K x ( t ) + 4 } { 6 } \neq \underline { { K y ( t ) } }$ 不满足均匀特性，该系统为非线性系统。

---

# 2. 线性系统与非线性系统

[例1]已知连续时间系统的输入 $x(t)$ 与输出 $y(t)$ 约束关系如下，试判断这些系统是否为线性系统。

$$
(1) y (t) = 3 x (t) + 4 \quad (2) y (t) = 4 x ^ {2} (t) \quad (3) y (t) = 2 \frac {\mathrm{d} x (t(1) (2) (3) (4) (5) (6) (7) (8) (9) (10) (11) (12) (13) (14) (15) (16) (17) (18) (19) (20) (21) (22) (23) (24) (25) (26) (27) (28) (29) (30) (31) (32) (33) (t) + x (t)) + (t) + x (t))}
$$

解：(2) 考察均匀特性

$$
x (t) \rightarrow y (t) = 4 x ^ {2} (t)
$$

$$
K x (t) \rightarrow 4 [ K x (t) ] ^ {2} = K ^ {2} [ 4 x ^ {2} (t) ] \neq K y (t)
$$

---

# 此题未设置答案，请点击右侧设置按钮

判断系统 $y(t) = 2x(t) \frac{\mathrm{d}x(t)}{\mathrm{d}t} + 3x(t)$ 是否为线性系统。

A 非线性系统

B 线性系统

√ 输入信号之间相乘、平方、开方，可直接判定非线性；
√ 微分、积分、常数倍才是线性运算。

# 线性系统需要同时满足两个条件

1. 可加性： $x_{1}(t) \rightarrow y_{1}(t)$ ， $x_{2}(t) \rightarrow y_{2}(t)$ ，则输入 $x_{1} + x_{2}$ ，输出必须为 $y_{1} + y_{2}$

2. 齐次性（比例性）：输入 $a x(t)$ ，输出必须

提交

---

# 2. 线性系统与非线性系统

[例2] 判断积分器、延时器是否为线性系统。

![](.memoria/images/1810c84b6091412221d869961c40a718d0e8bc15f9fe620b9131c067e0a7792c.jpg)

```mermaid
graph LR
  A["x(t)"] --> B["∫"]
  B --> C["y(t) = ∫_{-t}^t x(τ) dτ"]
  C --> D["&quot;x[k"]"]
  D --> E["D"]
  E --> F["&quot;y[k"] = x["k-1"]"]
```

解：设 $x[k] = \alpha x_{1}[k] + \beta x_{2}[k]$

则 $y[k] = x[k - 1] = \alpha x_{1}[k - 1] + \beta x_{2}[k - 1]$

$$
= \alpha y _ {1} [ k ] + \beta y _ {2} [ k ]
$$

延时器是线性系统

---

# 2. 线性系统与非线性系统

# 含有初始状态的线性系统

可分解性：系统输出可以分解为零输入响应和零状态响应之和

零输入响应 \( y\_{zi}(t) \) ：仅由初始状态 \( \{y(0)\} \) 产生的响应， \( y\_{zi}(t)=0

零输入响应线性：对所有的初始状态 $\{y(0)\}$ 线性

零状态响应线性：对输入信号 $\{x(t)\}$ 线性

---

# 2. 线性系统与非线性系统

[例1] 试判断下列系统是否为线性系统。

$$
(1) y (t) = 4 y (0) x (t) + 2 x (t) \quad (2) y (t) = 4 y (0) + 2 \sin (t) \frac {\mathrm{d} x (t)}{\mathrm{d} t}
$$

解：(1) 考察可分解性

$$
y _ {\mathrm{zi}} (t) = y (t) \big | _ {x (t) = 0} = 0
$$

$$
y (t) \neq y _ {z i} (t) + y _ {z s} (t)
$$

$$
y _ {z s} (t) = y (t) \big | _ {y (0) 0} = 2 x (t)
$$

由于不满足可分解性，该系统为非线性系统。

---

# 2. 线性系统与非线性系统

[例1] 试判断下列系统是否为线性系统。

(1) $y(t) = 4y(0)x(t) + 2x(t)$ (2) $y(t) = 4y(0) + 2\sin (t)$

解：(2) 考察可分解性

$$
y _ {\mathrm{zi}} (t) = y (t) \big | _ {x (t) = 0} = 4 y (0)
$$

$$
y _ {z s} (t) = y (t) \big | _ {y (0) = 0} = 2 \sin (t) \frac {\mathrm{d}} \frac {\mathrm{d} x}{\mathrm{d} t} \tag {2}
$$

---

# 2. 线性系统与非线性系统

[例1] 试判断下列系统是否为线性系统。

(1) $y(t) = 4y(0)x(t) + 2x(t)$ (2) $y(t) = 4y(0) + 2\sin(t)\frac{\mathrm{d}x(t)}{\mathrm{d}t}$

解：(2) 考察零输入响应对初始状态 $y(0)$ 是否具有线性特性

$$
y _ {z i} (t) = 4 y (0) \quad \text {线性}
$$

考察零状态响应对输入 $x(t)$ 是否具有线性特性

$$
y _ {z s} (t) = 2 \sin (t) \frac {\mathrm{d} x (t)}{\mathrm{d} t} \quad \text {线性}
$$

该系统为线性系统。

---

# 3. 非时变系统与时变系统

非时变系统：在零状态条件下，系统的输出响应与输入激励的关系不随输入激励作用于系统的起点而改变。

非时变的连续时间系统表示为

Zero State(零状态)

若 $x(t)\longrightarrow y_{\mathrm{ZS}}(t)$

则 $x(t - t_0)\longrightarrow y_{\mathrm{zs}}(t - t_0)$

非时变的离散时间系统表示为

若 $x[k] \longrightarrow y_{\mathrm{zs}}[k]$

则 $x[k - n]\longrightarrow y_{\mathrm{zs}}[k - n]$

---

# 2. 线性系统与非线性系统

# 含有初始状态的线性系统

可分解性：系统输出可以分解为零输入响应和零状态响应之和

零输入响应 $y_{zi}(t)$ ：仅由初始状态 $\{y(0)\}$ 产生的响应， $y_{zi}(t)$ 零状态响应 $y_{zs}(t)$ ：仅由输入信号 $(x,t)$ 产生的响应， $y_{zs}(t)=y_{ts}(t)$ 产生的响应， $y_{zs}(t)=y_{ts}(t)$ 产生的响应。

---

# 3. 非时变系统与时变系统

非时变系统：在零状态条件下，若系统的输入发生延时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时，输出时间

![](.memoria/images/0ed7642c80cb9f3456003d8388337f481654838ebcae871fa7244fdb7d8cce35.jpg)

```mermaid
x(t)
1
0
2
t
x(t-t0)
1
0
2 t
t
非时变系统
y(t)
1
0
2 t
t
y(t-t0)
1
0
2 t
t
非时变系统图示
```

时变系统：不满足非时变特性的系统。

---

# 3. 非时变系统与时变系统

➢ 非时变系统举例 输入为电流，输出为电压

![](.memoria/images/fdcf2c2cd831ff5a7808750a21d4711c6ae6ebbbf8119c5d87c59506cf17157b.jpg)

Electrical circuit diagram with resistor and voltage source

![](.memoria/images/86e8d97c1272e2b24ec8006ffb75b2a5a19a49da15584b7664b20136d36dd762.jpg)

Electrical circuit diagram with capacitor and voltage source labels

![](.memoria/images/8a4db7685f46071f44207acd907a939538df3ae22cad83015dbb1e364635a437.jpg)

Electrical circuit diagram with inductor and voltage source

对于电阻R，若 $x(t)=i_{\mathrm{R}}(t-t_{0})$

则 $y(t) = Ri_{\mathrm{R}}(t - t_0)$

$$
= v _ {\mathrm{R}} (t - t _ {0})
$$

具有非时变特性

若电阻值为 $R(t)$ ，随时间变化，即 $\nu_{\mathrm{R}}(t) = R(t)i_{\mathrm{R}}(t)$ 则当电流为 $x(t)$ 时，

$$
y (t) = R (t) i _ {\mathrm{R}} (t - t _ {0}) \neq v _ {\mathrm{R}} (t - t _ {0})
$$

不具有非时变特性

---

# 3. 非时变系统与时变系统

非时变系统举例

元件参数不随时间变化的RLC电路均为非时变系统

![](.memoria/images/d0200b6fe03e98cbf62add862e63724adbe03a1c223f61daaba57300e56d20a5.jpg)

---

# 3. 非时变系统与时变系统

![](.memoria/images/275cb905e0281a89f405aab675ad6fcc88d4c0a33e7f8bbb8a4ff9bd33db4282.jpg)

```mermaid
graph LR
  A["连续系统"] --> B["连续系统"]
  B --> C["连续系统"]
  C --> D["离散系统"]
  D --> E["离散系统"]
  E --> F["离散系统"]
```

系统的输入输出关系如下，试判断是否为非时变系统。

(1) \( y(t)=2x(t) \)  (2) \( y(t)=\cos(t)x(t) \)  (3) \( y[k]=k

解：

(1) $x(t - t_0)\longrightarrow y_1(t) = 2x(t - t_0) = y(t - t_0)$ �变系统
(2) $x(t - t_0)\longrightarrow y_1(t) = \cos (t)\cdot x(t - t_0)\neq y(t - t_t$ 时变系统
(3) $x[k - k_0]\longrightarrow y_1[k] = k\cdot x[k - k_0]\neq y[k - k_0]$ 时变系统

一般，若在系统的输入输出关系中，除输入和输出外，还含有与t、k有关的变量，则为时变系统。

---

# 3. 非时变系统与时变系统

[例4] 试判断积分器、延时器是否为非时变系统。

![](.memoria/images/82e3193cd3fde3aea2590f2f0f39a34d688194a2ebb813654eb5f5d9c0dee913.jpg)

```mermaid
graph LR
  A["x(t)"] --> B["∫"]
  B --> C["y(t) = \int_{-\infty}^{t} x(\tau) \mathrm{d}\tau"]
```

解: 设 $x_{1}(t)=x(t-t_{0})$

![](.memoria/images/09506ea8548f32abc42196ed0aca9236a4a10086a8a90f66c7a7f5dd54a83ac3.jpg)

则 $y_{1}(t) = \int_{-\infty}^{t}x(\tau -t_{0})\mathrm{d}\tau$

$$
= \int_ {- \infty} ^ {t - t _ {0}} x (\tau) \mathrm{d} \tau = y (t - t _ {0})
$$

![](.memoria/images/1878ee270b807812eacbc6cd8774fc0431acf7a73f1b51d2e46460fc810d4795.jpg)

```mermaid
graph LR
  A["&quot;x[k"]]"] --> B["D"]
  B --> C["&quot;y[k"]=x["k-1"]"]
```

设 $x_{1}[k] = x[k - k_{0}]$

![](.memoria/images/4c9d8705f165a9f6cc9ad7912f57751dce14f4625c057d0cffbe1b503b9ea335.jpg)

则 $y_{1}[k] = x[k - k_{0} - 1]$

$$
= y [ k - k _ {0} ]
$$

积分器、延时器是非时变系统

---

# 4. 因果系统与非因果系统

非因果系统：不具有因果特性的系统称为非因果系统。

![](.memoria/images/f0f908ca21c5f657fdc338ea4320398f65bb92a26192ce9c2c54ad3365a3a1e4.jpg)

```mermaid
graph LR
  A["Input Signal x(t)"] -->|t| B["Non-inclusive System"]
  B --> C["Output y(t)"]
```

非因果系统示意图

---

![](.memoria/images/76d891e6523db423e8a6388abbc210376d34845a496ff94e6b758e435c2534de.jpg)