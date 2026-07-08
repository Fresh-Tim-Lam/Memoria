/**
 * Interaction Coordinator
 *
 * 协调 ForceEngine 和 Renderer，处理交互事件
 *
 *职责：
 * 1. 初始化 ForceEngine 和 Renderer2D/3D
 * 2. 处理 ForceEngine tick 回调，将位置传递给 Renderer
 * 3. 处理 Renderer 的拖拽事件，通知 ForceEngine
 * 4. 处理 Renderer 的悬停事件，触发高亮
 * 5. 处理外部高亮请求（文本链接悬停）
 * 6. 处理 2D/3D 模式切换
 */

import { ForceEngine } from './force-engine.js';
import { Renderer2D } from './renderer-2d.js';

export class InteractionCoordinator {
    constructor() {
        this.forceEngine = null;
        this.renderer2D = null;
        this.renderer3D = null; // 暂未实现
        this.currentMode = '2d';

        this.graph = null; // 原始图谱数据
        this.positions = new Map(); // 当前位置缓存

        // 拖拽状态
        this.isDragging = false;
        this.dragNodeId = null;

        // 高亮状态
        this.hoveredNodeId = null;
        this.textLinkHoverId = null;
    }

    /**
     * 初始化
     */
    init(container2D, container3D) {
        // 初始化 ForceEngine
        this.forceEngine = new ForceEngine();
        this.forceEngine.onTick((positions, alpha, perf) => {
            this.handleTick(positions, alpha, perf);
        });
        this.forceEngine.onDone(() => {
            this.handleDone();
        });

        // 初始化 Renderer2D
        this.renderer2D = new Renderer2D();
        this.renderer2D.init(container2D);

        // 绑定 Renderer2D 事件
        this.renderer2D.onNodeClick((nodeId) => {
            this.handleNodeClick(nodeId);
        });
        this.renderer2D.onNodeDrag((nodeId, position) => {
            this.handleNodeDrag(nodeId, position);
        });
        this.renderer2D.onNodeDragEnd((nodeId) => {
            this.handleNodeDragEnd();
        });
        this.renderer2D.onNodeHover((nodeId) => {
            this.handleNodeHover(nodeId);
        });

        // Renderer3D 暂未实现
        // this.renderer3D = new Renderer3D();
        // this.renderer3D.init(container3D);
    }

    /**
     * 加载图谱
     */
    loadGraph(graph) {
        this.graph = graph;

        // 加载到 ForceEngine
        this.forceEngine.loadGraph(graph);

        // 加载到 Renderer
        this.renderer2D.loadGraph(graph);

        // 启动力模拟
        this.forceEngine.start();
    }

    /**
     * 设置模式（2D/3D）
     */
    setMode(mode) {
        this.currentMode = mode;

        if (mode === '2d') {
            // 显示 2D，隐藏 3D
            // 实际切换逻辑在 app.js 中处理
        } else {
            // 显示 3D，隐藏 2D
            // 暂未实现
        }
    }

    /**
     * ForceEngine tick 回调
     */
    handleTick(positions, alpha, perf) {
        console.log('[InteractionCoordinator] handleTick called, positions.size=', positions.size, 'alpha=', alpha?.toFixed(4));

        // 拖拽时保留拖拽节点的本地位置（避免被 Worker 的 tick 覆盖）
        if (this.isDragging && this.dragNodeId) {
            const dragPos = positions.get(this.dragNodeId);
            if (dragPos) {
                // 从 Renderer 获取当前拖拽位置（最新）
                const rendererPos = this.renderer2D.positions.get(this.dragNodeId);
                if (rendererPos) {
                    // 用 Renderer 的位置覆盖 Worker 的位置
                    positions.set(this.dragNodeId, { x: rendererPos.x, y: rendererPos.y });
                    console.log('[InteractionCoordinator] preserved drag node position:', this.dragNodeId, rendererPos.x.toFixed(2), rendererPos.y.toFixed(2));
                }
            }
        }

        this.positions = positions;

        // 更新 Renderer
        if (this.currentMode === '2d') {
            this.renderer2D.updatePositions(positions);
            console.log('[InteractionCoordinator] renderer2D.updatePositions called');
        }

        // 性能数据可用于外部统计
        this._perf = perf;

        // 调用外部回调
        if (this.onTick) {
            this.onTick(positions, alpha, perf);
        }
    }

    /**
     * ForceEngine done 回调
     */
    handleDone() {
        console.log('[InteractionCoordinator] Force simulation done');
    }

    /**
     * Renderer 点击事件
     */
    handleNodeClick(nodeId) {
        // 点击节点 → 打开对应文件
        if (typeof openGraphNode === 'function') {
            openGraphNode(nodeId);
        }
    }

    /**
     * Renderer 拖拽事件
     */
    handleNodeDrag(nodeId, position) {
        console.log('[Interaction] handleNodeDrag, nodeId=', nodeId, 'position=', position.x.toFixed(2), position.y.toFixed(2));

        // 首次拖拽：通知 ForceEngine 开始
        if (!this.isDragging) {
            this.isDragging = true;
            this.dragNodeId = nodeId;
            this.forceEngine.dragStart(nodeId);
            console.log('[Interaction] dragStart sent to ForceEngine');
        }

        // 拖拽移动：通知 ForceEngine 更新固定位置
        this.forceEngine.dragMove(nodeId, position);
    }

    /**
     * Renderer 拖拽结束事件
     */
    handleNodeDragEnd() {
        if (this.isDragging && this.dragNodeId) {
            this.forceEngine.dragEnd(this.dragNodeId, false); // 不保持固定
            this.isDragging = false;
            this.dragNodeId = null;
        }
    }

    /**
     * Renderer 悬停事件
     */
    handleNodeHover(nodeId) {
        this.hoveredNodeId = nodeId;

        if (nodeId) {
            // 悬停在节点上 → 主高亮
            this.renderer2D.highlightPrimary(nodeId);
        } else {
            // 悬停离开 → 重置高亮（除非有文本链接悬停）
            if (this.textLinkHoverId) {
                this.renderer2D.highlightSecondary([this.textLinkHoverId]);
            } else {
                this.renderer2D.resetHighlight();
            }
        }
    }

    /**
     * 文本链接悬停（外部调用）
     */
    handleTextLinkHover(nodeId) {
        this.textLinkHoverId = nodeId;
        this.renderer2D.highlightSecondary([nodeId]);
    }

    /**
     * 文本链接离开（外部调用）
     */
    handleTextLinkLeave() {
        this.textLinkHoverId = null;

        // 如果有节点悬停，恢复主高亮；否则重置
        if (this.hoveredNodeId) {
            this.renderer2D.highlightPrimary(this.hoveredNodeId);
        } else {
            this.renderer2D.resetHighlight();
        }
    }

    /**
     * 缩放控制（外部调用）
     */
    zoom(factor) {
        if (this.currentMode === '2d') {
            this.renderer2D.zoomTo(factor);
        }
    }

    /**
     * 重置视口（外部调用）
     */
    resetView() {
        if (this.currentMode === '2d') {
            this.renderer2D.resetView();
        }
    }

    /**
     * 获取当前位置（外部调用）
     */
    getPositions() {
        return this.positions;
    }

    /**
     * 销毁
     */
    destroy() {
        if (this.forceEngine) {
            this.forceEngine.destroy();
            this.forceEngine = null;
        }
        if (this.renderer2D) {
            this.renderer2D.destroy();
            this.renderer2D = null;
        }
        // renderer3D 暂未实现

        this.graph = null;
        this.positions.clear();
    }
}