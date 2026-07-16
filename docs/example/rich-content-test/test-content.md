---
description: 富内容测试文件，涵盖图片、图表、公式、荧光笔等。
concepts:
  - id: image-test
    name: 图片渲染测试
    weight: 1.0
    tags: [测试, 图片]
  - id: chart-test
    name: 图表渲染测试
    weight: 1.0
    tags: [测试, 图表, mermaid]
  - id: formula-test
    name: 公式渲染测试
    weight: 1.0
    tags: [测试, 公式, LaTeX]
  - id: highlight-test
    name: 荧光笔测试
    weight: 1.0
    tags: [测试, 高亮, 荧光笔]
---

## 图片渲染测试

### 网络图片

![Memoria Logo](https://upload.wikimedia.org/wikipedia/commons/thumb/4/48/Markdown-mark.svg/208px-Markdown-mark.svg.png)

### 本地相对路径图片

![本地图片](./images/sample.png)

### 带标题的图片

![带标题](https://upload.wikimedia.org/wikipedia/commons/thumb/4/48/Markdown-mark.svg/208px-Markdown-mark.svg.png "Markdown Logo")

## 图表渲染测试

### 流程图（Mermaid 语法）

```mermaid
graph TD
    A[行政主体] --> B[行政行为]
    B --> C[行政处罚]
    B --> D[行政许可]
    B --> E[行政强制]
    C --> F[行政处罚的设定]
    D --> G[行政许可的设定]
```

### 序列图

```mermaid
sequenceDiagram
    participant 申请人
    participant 行政机关
    participant 复议机关
    申请人->>行政机关: 提出许可申请
    行政机关->>申请人: 作出许可决定
    申请人->>复议机关: 不服，申请复议
    复议机关->>行政机关: 审查
    复议机关->>申请人: 复议决定
```

### 甘特图

```mermaid
gantt
    title 行政复议时间线
    dateFormat  YYYY-MM-DD
    section 申请
    提交申请     :a1, 2024-01-01, 60d
    section 审理
    书面审理     :a2, after a1, 30d
    section 决定
    作出决定     :a3, after a2, 15d
```

## 公式渲染测试

### 行内公式

贝叶斯公式：$P(A|B) = \frac{P(B|A) \cdot P(A)}{P(B)}$

欧拉恒等式：$e^{i\pi} + 1 = 0$

### 块级公式

$$
\mathcal{L}(\theta) = -\frac{1}{N} \sum_{i=1}^{N} \left[ y_i \log h_\theta(x_i) + (1 - y_i) \log(1 - h_\theta(x_i)) \right]
$$

$$
\nabla_\theta J(\theta) = \frac{1}{m} \sum_{i=1}^{m} \left( h_\theta(x^{(i)}) - y^{(i)} \right) x^{(i)}
$$

### 矩阵

$$
\mathbf{A} = \begin{pmatrix} a_{11} & a_{12} & \cdots & a_{1n} \\ a_{21} & a_{22} & \cdots & a_{2n} \\ \vdots & \vdots & \ddots & \vdots \\ a_{m1} & a_{m2} & \cdots & a_{mn} \end{pmatrix}
$$

## 荧光笔测试

这是一段普通文本，其中==重要内容应该被高亮显示==，而普通文本保持不变。

行政法的六大原则：==依法行政==、==合理行政==、==程序正当==、==诚实信用==、==高效便民==、==权责统一==。

==整段高亮测试：这段话全部应该被荧光笔标记。==
