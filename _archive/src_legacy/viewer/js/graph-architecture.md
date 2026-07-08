# 图谱渲染引擎架构设计

## 目标

- 支持 1000+ 节点流畅交互（60fps）
- 统一架构支持 2D（Canvas）和 3D（WebGL）
- 分离关注点：力计算、渲染、交互

---

## 三层架构

```
┌─────────────────────────────────────────────────────────┐
│                    Interaction Layer                      │
│  (主线程) - 拖拽、悬停、点击、缩放、高亮                      │
└─────────────────────┬───────────────────────────────────┘
                      │ 事件 → ForceEngine
                      │ 高亮 → Renderer
┌─────────────────────┴───────────────────────────────────┐
│                    ForceEngine Layer                      │
│  (Worker 线程) - Barnes-Hut 力模拟                         │
│  - 弹簧力：链接的节点互相拉近                               │
│  - 斥力：所有节点互相排斥（Barnes-Hut O(n log n)）          │
│  - 边界约束：防止节点飞出画布                               │
└─────────────────────┬───────────────────────────────────┘
                      │ tick → positions[]
┌─────────────────────┴───────────────────────────────────┐
│                    Renderer Layer                         │
│  (主线程) - Canvas 2D / WebGL 3D                          │
│  - 绘制节点（圆 + 文字）                                    │
│  - 绘制边（线 + 箭头）                                      │
│  - 高亮效果（节点环、边加粗）                               │
└─────────────────────────────────────────────────────────┘
```

---

## 层间通信协议

### ForceEngine → Renderer

每次 tick 计算（约 16ms）发送位置更新：

```typescript
interface TickMessage {
  type: 'tick';
  positions: Map<string, { x: number; y: number }>;  // nodeId → position
  alpha: number;  // 模拟器活跃度 (0-1)
}
```

### Interaction → ForceEngine

拖拽开始/移动/结束，锁定节点位置：

```typescript
interface DragMessage {
  type: 'drag-start' | 'drag-move' | 'drag-end';
  nodeId: string;
  position?: { x: number; y: number };  // drag-move 时提供
  fixed: boolean;  // 是否固定节点（drag-end 后保持固定）
}
```

缩放/平移画布（可选，力引擎可忽略）：

```typescript
interface ViewportMessage {
  type: 'viewport-change';
  transform: { x: number; y: number; scale: number };
}
```

### Interaction → Renderer

高亮请求（不经过力引擎）：

```typescript
interface HighlightMessage {
  type: 'highlight-primary' | 'highlight-secondary' | 'highlight-reset';
  nodeId?: string;
  nodeIds?: string[];
}
```

---

## ForceEngine 接口协议

```typescript
interface ForceEngine {
  // 初始化
  init(graph: { nodes: Node[]; links: Link[] }): void;

  // 启动/停止模拟
  start(): void;
  stop(): void;

  // 拖拽控制
  fixNode(nodeId: string, position: { x: number; y: number }): void;
  unfixNode(nodeId: string): void;

  // 参数调整
  setParams(params: {
    linkStrength?: number;      // 弹簧强度 (0-1)
    linkDistance?: number;      // 弹簧长度
    repulsionStrength?: number; // 斥力强度
    centerStrength?: number;    // 中心引力
  }): void;

  // 获取当前状态
  getPositions(): Map<string, { x: number; y: number }>;
  getAlpha(): number;

  // 事件监听
  onTick(callback: (positions: Map<string, Position>) => void): void;
}
```

---

## Renderer 接口协议

```typescript
interface Renderer {
  // 初始化
  init(container: HTMLElement): void;

  // 绘制
  render(nodes: Node[], links: Link[], positions: Map<string, Position>): void;

  // 高亮
  highlightPrimary(nodeId: string): void;
  highlightSecondary(nodeIds: string[]): void;
  resetHighlight(): void;

  // 视口控制
  setTransform(transform: { x: number; y: number; scale: number }): void;
  zoomTo(factor: number): void;
  resetView(): void;

  // 销毁
  destroy(): void;

  // 事件监听
  onNodeClick(callback: (nodeId: string) => void): void;
  onNodeDrag(callback: (nodeId: string, position: Position) => void): void;
  onNodeHover(callback: (nodeId: string | null) => void): void;
}
```

---

## Interaction 协调器

```typescript
interface InteractionCoordinator {
  // 初始化
  init(forceEngine: ForceEngine, renderer2D: Renderer, renderer3D: Renderer): void;

  // 模式切换
  setMode(mode: '2d' | '3d'): void;

  // 图谱数据加载
  loadGraph(graph: { nodes: Node[]; links: Link[] }): void;

  // 拖拽协调
  handleDragStart(nodeId: string): void;
  handleDragMove(nodeId: string, position: Position): void;
  handleDragEnd(nodeId: string): void;

  // 高亮协调
  handleHover(nodeId: string | null): void;
  handleTextLinkHover(nodeId: string): void;
  handleTextLinkLeave(): void;

  // 销毁
  destroy(): void;
}
```

---

## Barnes-Hut 算法（斥力加速）

传统斥力计算 O(n²)，Barnes-Hut 降至 O(n log n)：

```
┌────────────────────────────────────┐
│  四叉树划分空间                      │
│                                    │
│  ┌─────────┬─────────┐             │
│  │ Q1      │ Q2      │             │
│  │  子节点  │  子节点  │             │
│  ├─────────┼─────────┤             │
│  │ Q3      │ Q4      │             │
│  │  子节点  │  子节点  │             │
│  └─────────┴─────────┘             │
│                                    │
│  远距离节点：用四叉树节点近似        │
│  近距离节点：精确计算                │
└────────────────────────────────────┘
```

**阈值 θ**：当节点距离 / 四叉树节点尺寸 > θ 时，使用近似计算。典型 θ = 0.5。

---

## 实现顺序

1. **Phase 1：ForceEngine Worker**
   - 实现 Barnes-Hut 四叉树
   - 实现弹簧力 + 斥力计算
   - 实现 Worker 通信协议

2. **Phase 2：Canvas 2D Renderer**
   - 实现 Canvas 绘制循环
   - 实现节点/边绘制
   - 实现高亮效果
   - 实现拖拽事件监听

3. **Phase 3：Interaction Coordinator**
   - 协调 ForceEngine + Renderer
   - 处理拖拽/悬停/高亮
   - 处理 2D/3D 模式切换

4. **Phase 4：WebGL 3D Renderer**
   - 实现 WebGL 绘制
   - 实现 3D 高亮效果
   - 实现 3D 交互（OrbitControls）

---

## 性能指标

| 节点数 | 目标帧率 | Barnes-Hut | Canvas 2D | WebGL 3D |
|--------|----------|------------|-----------|----------|
| 100    | 60fps    | ✓          | ✓         | ✓        |
| 500    | 60fps    | ✓          | ✓         | ✓        |
| 1000   | 60fps    | ✓          | ✓         | ~30fps   |
| 5000   | 30fps    | ✓          | ~30fps    | ~15fps   |

---

## 文件结构

```
src/viewer/js/
  graph/
    force-engine.worker.js    # Worker 线程力模拟
    force-engine.js           # Worker 桥接层（主线程）
    barnes-hut.js             # 四叉树实现
    renderer-2d.js            # Canvas 2D 渲染器
    renderer-3d.js            # WebGL 3D 渲染器（复用 Three.js）
    interaction.js            # 交互协调器
    graph-engine.js           # 统一入口
  graph-2d.js                 # 旧版兼容入口（调用新架构）
  graph-3d.js                 # 旧版兼容入口（调用新架构）
```

---

## 兼容策略

保留 `graph-2d.js` / `graph-3d.js` 作为入口，内部调用新架构：

```javascript
// graph-2d.js（兼容层）
function initGraph2D(graphData) {
  if (!window._graphEngine) {
    window._graphEngine = new GraphEngine();
  }
  window._graphEngine.init(graphData, '2d');
}

function primaryHighlight2D(nodeId) {
  window._graphEngine.highlightPrimary(nodeId);
}
```

这样前端其他代码无需修改。