/**
 * ForceEngine 主线程桥接层
 *
 * 负责：
 * 1. 创建和管理 Worker
 * 2. 发送命令到 Worker
 * 3. 接收 Worker 的 tick 结果并转发给 Renderer
 * 4. 提供同步 API 供 Interaction Layer 调用
 */

export class ForceEngine {
    constructor() {
        this.worker = null;
        this.positions = new Map(); // nodeId → { x, y }
        this.alpha = 0;
        this.tickCallback = null;
        this.doneCallback = null;
        this._lastTickStart = 0; // 用于测量耗时
    }

    /**
     * 初始化 Worker
     */
    init() {
        if (this.worker) return;

        // 创建 Worker（使用 Blob URL，避免模块导入问题）
        // Worker 代码会内联加载 barnes-hut.js
        this.worker = new Worker(
            new URL('./force-engine.worker.js', import.meta.url),
            { type: 'module' }
        );

        this.worker.onmessage = (event) => {
            const { type, data } = event.data;

            switch (type) {
                case 'tick':
                    this.handleTick(data);
                    break;
                case 'done':
                    this.handleDone();
                    break;
                case 'debug':
                    console.log('[ForceEngine] Worker debug:', data);
                    break;
                case 'perf':
                    // 性能数据
                    if (data.tickTime) {
                        this._lastTickTime = data.tickTime;
                    }
                    break;
            }
        };

        this.worker.onerror = (event) => {
            console.error('[ForceEngine] Worker error:', event.message, 'filename:', event.filename, 'lineno:', event.lineno, 'colno:', event.colno);
            event.preventDefault(); // 阻止默认错误传播
        };

        this.worker.onmessageerror = (error) => {
            console.error('[ForceEngine] Worker message error:', error);
        };

        console.log('[ForceEngine] Worker created successfully');
    }

    /**
     * 加载图谱数据
     */
    loadGraph(graph, initialPositions = null) {
        this.init();

        console.log('[ForceEngine] loadGraph called, nodes=', graph.nodes.length, 'links=', graph.links.length);

        this.worker.postMessage({
            type: 'init',
            data: {
                nodes: graph.nodes,
                links: graph.links,
                positions: initialPositions,
            },
        });
    }

    /**
     * 启动模拟
     */
    start() {
        if (!this.worker) return;
        console.log('[ForceEngine] start called');
        this.worker.postMessage({ type: 'start' });
    }

    /**
     * 停止模拟
     */
    stop() {
        if (!this.worker) return;
        this.worker.postMessage({ type: 'stop' });
    }

    /**
     * 重启模拟（重新激活 alpha）
     */
    restart() {
        if (!this.worker) return;
        this.worker.postMessage({ type: 'restart' });
    }

    /**
     * 拖拽开始
     */
    dragStart(nodeId) {
        if (!this.worker) return;
        this.worker.postMessage({
            type: 'drag-start',
            data: { nodeId },
        });
    }

    /**
     * 拖拽移动
     */
    dragMove(nodeId, position) {
        if (!this.worker) return;
        this.worker.postMessage({
            type: 'drag-move',
            data: { nodeId, position },
        });
    }

    /**
     * 拖拽结束
     */
    dragEnd(nodeId, fixed = false) {
        if (!this.worker) return;
        this.worker.postMessage({
            type: 'drag-end',
            data: { nodeId, fixed },
        });
    }

    /**
     * 设置参数
     */
    setParams(params) {
        if (!this.worker) return;
        this.worker.postMessage({
            type: 'params',
            data: params,
        });
    }

    /**
     * 获取当前位置（同步，返回缓存）
     */
    getPositions() {
        return this.positions;
    }

    /**
     * 获取当前 alpha
     */
    getAlpha() {
        return this.alpha;
    }

    /**
     * 注册 tick 回调
     */
    onTick(callback) {
        this.tickCallback = callback;
    }

    /**
     * 注册 done 回调（模拟完成）
     */
    onDone(callback) {
        this.doneCallback = callback;
    }

    /**
     * 处理 Worker tick 结果
     */
    handleTick(data) {
        // 更新位置缓存
        this.positions.clear();
        for (const [id, pos] of Object.entries(data.positions)) {
            this.positions.set(id, pos);
        }
        this.alpha = data.alpha;

        // 性能数据
        if (data.perf) {
            this._perf = data.perf;
        }

        // 只在特定间隔输出日志
        this._tickReceiveCount = (this._tickReceiveCount || 0) + 1;
        if (this._tickReceiveCount % 20 === 0 || this.alpha < 0.01) {
            console.log('[ForceEngine] tick #', this._tickReceiveCount, 'alpha=', this.alpha.toFixed(4));
        }

        // 调用回调
        if (this.tickCallback) {
            this.tickCallback(this.positions, this.alpha, data.perf);
        } else {
            console.warn('[ForceEngine] No tickCallback registered');
        }
    }

    /**
     * 处理模拟完成
     */
    handleDone() {
        if (this.doneCallback) {
            this.doneCallback();
        }
    }

    /**
     * 销毁
     */
    destroy() {
        if (this.worker) {
            this.worker.terminate();
            this.worker = null;
        }
        this.positions.clear();
        this.tickCallback = null;
        this.doneCallback = null;
    }
}