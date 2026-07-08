/**
 * GraphEngine - 统一入口
 *
 * 将 ForceEngine、Renderer2D、InteractionCoordinator 整合
 * 提供简洁的 API 供 app.js 调用
 *
 * 使用方式：
 *   const engine = new GraphEngine();
 *   engine.init('graph-2d', 'graph-3d');
 *   engine.loadGraph(graphData);
 *   engine.highlightPrimary(nodeId);
 */

import { InteractionCoordinator } from './interaction.js';

export class GraphEngine {
    constructor() {
        this.coordinator = null;
    }

    /**
     * 初始化
     * @param containerId2D - 2D 容器元素 ID
     * @param containerId3D - 3D 容器元素 ID（暂未实现）
     */
    init(containerId2D, containerId3D) {
        const container2D = document.getElementById(containerId2D);
        const container3D = document.getElementById(containerId3D);

        if (!container2D) {
            console.error('[GraphEngine] Container 2D not found:', containerId2D);
            return;
        }

        this.coordinator = new InteractionCoordinator();
        this.coordinator.init(container2D, container3D);
    }

    /**
     * 加载图谱数据
     */
    loadGraph(graphData) {
        if (!this.coordinator) {
            console.error('[GraphEngine] Not initialized');
            return;
        }
        this.coordinator.loadGraph(graphData);
    }

    /**
     * 主高亮
     */
    highlightPrimary(nodeId) {
        if (!this.coordinator) return;
        this.coordinator.renderer2D.highlightPrimary(nodeId);
    }

    /**
     * 次高亮
     */
    highlightSecondary(nodeIds) {
        if (!this.coordinator) return;
        this.coordinator.renderer2D.highlightSecondary(nodeIds);
    }

    /**
     * 重置高亮
     */
    resetHighlight() {
        if (!this.coordinator) return;
        this.coordinator.renderer2D.resetHighlight();
    }

    /**
     * 文本链接悬停
     */
    handleTextLinkHover(nodeId) {
        if (!this.coordinator) return;
        this.coordinator.handleTextLinkHover(nodeId);
    }

    /**
     * 文本链接离开
     */
    handleTextLinkLeave() {
        if (!this.coordinator) return;
        this.coordinator.handleTextLinkLeave();
    }

    /**
     * 缩放
     */
    zoom(factor) {
        if (!this.coordinator) return;
        this.coordinator.zoom(factor);
    }

    /**
     * 重置视口
     */
    resetView() {
        if (!this.coordinator) return;
        this.coordinator.resetView();
    }

    /**
     * 获取位置
     */
    getPositions() {
        if (!this.coordinator) return new Map();
        return this.coordinator.getPositions();
    }

    /**
     * 设置模式
     */
    setMode(mode) {
        if (!this.coordinator) return;
        this.coordinator.setMode(mode);
    }

    /**
     * 销毁
     */
    destroy() {
        if (this.coordinator) {
            this.coordinator.destroy();
            this.coordinator = null;
        }
    }
}

// 全局实例（兼容旧版 API）
let _globalEngine = null;

/**
 * 初始化图谱（兼容旧版 API）
 */
export function initGraphEngine(containerId2D, containerId3D) {
    if (!_globalEngine) {
        _globalEngine = new GraphEngine();
    }
    _globalEngine.init(containerId2D, containerId3D);
    return _globalEngine;
}

/**
 * 获取全局引擎
 */
export function getGraphEngine() {
    return _globalEngine;
}