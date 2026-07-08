/**
 * Canvas 2D Renderer
 *
 * 使用 Canvas 2D API 绘制图谱，替代 SVG DOM 节点
 * 性能优势：1000节点只需一个画布，无 DOM 操作开销
 *
 * 功能：
 * 1. 绘制节点（圆环 + 文字）
 * 2. 绘制边（线 + 箭头）
 * 3. 高亮效果（节点环、边加粗）
 * 4. 视口控制（缩放/平移）
 * 5. 事件监听（点击、拖拽、悬停）
 */

export class Renderer2D {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.container = null;

        this.nodes = [];
        this.links = [];
        this.positions = new Map(); // nodeId → { x, y }

        this.transform = { x: 0, y: 0, scale: 1 }; // 视口变换
        this.width = 0;
        this.height = 0;

        // 高亮状态
        this.primaryHighlightId = null;
        this.secondaryHighlightIds = new Set();
        this.highlightLinkIds = new Set(); // 高亮的边

        // 交互状态
        this.hoveredNodeId = null;
        this.draggingNodeId = null;
        this.dragStartPos = null;

        // 事件回调
        this.onNodeClickCallback = null;
        this.onNodeDragCallback = null;
        this.onNodeDragEndCallback = null;
        this.onNodeHoverCallback = null;

        // 绘制参数
        this.nodeRadius = 14;
        this.nodeStrokeWidth = 2.5;
        this.linkWidth = 1.5;
        this.linkWidthHighlight = 2.5;

        this.edgeColors = {
            reference: '#007acc',
            prerequisite: '#ce9178',
            extend: '#4ec9b0',
            analogy: '#c586c0',
            contain: '#5cb85c',
        };
        this.edgeColorsLight = {
            reference: '#4da8e8',
            prerequisite: '#e8b8a0',
            extend: '#7ee0cc',
            analogy: '#dca8d8',
            contain: '#7ed47e',
        };

        // 渲染循环
        this.rafId = null;
        this.needsRender = true;
    }

    /**
     * 初始化
     */
    init(container) {
        this.container = container;
        this.width = container.clientWidth || 800;
        this.height = container.clientHeight || 600;

        // 创建 Canvas
        this.canvas = document.createElement('canvas');
        this.canvas.width = this.width;
        this.canvas.height = this.height;
        this.canvas.style.width = '100%';
        this.canvas.style.height = '100%';
        this.canvas.style.background = '#1e1e1e';
        container.appendChild(this.canvas);

        this.ctx = this.canvas.getContext('2d');

        // 视口居中（节点中心 (0,0) 显示在 Canvas 中心）
        this.transform = { x: this.width / 2, y: this.height / 2, scale: 1 };

        console.log('[Renderer2D] init done, width=', this.width, 'height=', this.height, 'transform=', JSON.stringify(this.transform));

        // 绑定事件
        this.bindEvents();

        // 启动渲染循环
        this.startRenderLoop();
    }

    /**
     * 加载图谱数据
     */
    loadGraph(graph) {
        this.nodes = graph.nodes || [];
        this.links = graph.links || [];
        this.needsRender = true;
    }

    /**
     * 更新节点位置
     */
    updatePositions(positions) {
        for (const [nodeId, pos] of positions) {
            if (nodeId !== this.draggingNodeId) {
                if (this.positions.has(nodeId)) {
                    const localPos = this.positions.get(nodeId);
                    localPos.x = pos.x;
                    localPos.y = pos.y;
                } else {
                    this.positions.set(nodeId, { x: pos.x, y: pos.y });
                }
            }
        }
        this.needsRender = true;
    }

    /**
     * 主高亮
     */
    highlightPrimary(nodeId) {
        this.primaryHighlightId = nodeId;
        this.secondaryHighlightIds.clear();
        this.highlightLinkIds.clear();

        // 收集相连节点和边
        for (const link of this.links) {
            const sId = link.source.id || link.source;
            const tId = link.target.id || link.target;

            if (sId === nodeId || tId === nodeId) {
                this.secondaryHighlightIds.add(sId === nodeId ? tId : sId);
                this.highlightLinkIds.add(`${sId}-${tId}`);
            }
        }

        this.needsRender = true;
    }

    /**
     * 次高亮
     */
    highlightSecondary(nodeIds) {
        this.primaryHighlightId = null;
        this.secondaryHighlightIds = new Set(nodeIds);
        this.highlightLinkIds.clear();
        this.needsRender = true;
    }

    /**
     * 重置高亮
     */
    resetHighlight() {
        this.primaryHighlightId = null;
        this.secondaryHighlightIds.clear();
        this.highlightLinkIds.clear();
        this.needsRender = true;
    }

    /**
     * 视口控制
     */
    setTransform(transform) {
        this.transform = transform;
        this.needsRender = true;
    }

    zoomTo(factor) {
        this.transform.scale *= factor;
        this.transform.scale = Math.max(0.2, Math.min(5, this.transform.scale));
        this.needsRender = true;
    }

    resetView() {
        this.transform = { x: 0, y: 0, scale: 1 };
        this.needsRender = true;
    }

    /**
     * 事件回调注册
     */
    onNodeClick(callback) {
        this.onNodeClickCallback = callback;
    }

    onNodeDrag(callback) {
        this.onNodeDragCallback = callback;
    }

    onNodeDragEnd(callback) {
        this.onNodeDragEndCallback = callback;
    }

    onNodeHover(callback) {
        this.onNodeHoverCallback = callback;
    }

    /**
     * 销毁
     */
    destroy() {
        if (this.rafId) {
            cancelAnimationFrame(this.rafId);
            this.rafId = null;
        }
        if (this.canvas) {
            this.canvas.remove();
            this.canvas = null;
        }
        this.ctx = null;
        this.container = null;
    }

    // ========== 内部方法 ==========

    /**
     * 绑定事件
     */
    bindEvents() {
        // 鼠标移动（悬停 + 拖拽）
        this.canvas.addEventListener('mousemove', (e) => {
            const pos = this.getMousePosition(e);

            if (this.draggingNodeId) {
                // 拖拽中
                this.handleDragMove(pos);
            } else {
                // 悬停检测
                this.handleHover(pos);
            }
        });

        // 鼠标按下（开始拖拽）
        this.canvas.addEventListener('mousedown', (e) => {
            const pos = this.getMousePosition(e);
            const nodeId = this.hitTestNode(pos);

            if (nodeId) {
                this.draggingNodeId = nodeId;
                this.dragStartPos = pos;
                e.preventDefault();
            }
        });

        // 鼠标抬起（结束拖拽 + 点击）
        this.canvas.addEventListener('mouseup', (e) => {
            const pos = this.getMousePosition(e);

            if (this.draggingNodeId) {
                // 判断是否为点击（未移动）
                const dx = pos.x - this.dragStartPos.x;
                const dy = pos.y - this.dragStartPos.y;
                const moved = Math.sqrt(dx * dx + dy * dy) > 5;

                if (!moved && this.onNodeClickCallback) {
                    this.onNodeClickCallback(this.draggingNodeId);
                }

                // 调用拖拽结束回调
                if (moved && this.onNodeDragEndCallback) {
                    this.onNodeDragEndCallback(this.draggingNodeId);
                }

                this.draggingNodeId = null;
                this.dragStartPos = null;
            }
        });

        // 鼠标离开
        this.canvas.addEventListener('mouseleave', () => {
            this.hoveredNodeId = null;
            if (this.onNodeHoverCallback) {
                this.onNodeHoverCallback(null);
            }
            this.needsRender = true;
        });

        // 滚轮缩放
        this.canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            const factor = e.deltaY > 0 ? 0.9 : 1.1;
            this.zoomTo(factor);
        });

        // 窗口大小变化
        window.addEventListener('resize', () => {
            if (this.container) {
                this.width = this.container.clientWidth || 400;
                this.height = this.container.clientHeight || 400;
                this.canvas.width = this.width;
                this.canvas.height = this.height;
                this.needsRender = true;
            }
        });
    }

    /**
     * 获取鼠标位置（转换到图谱坐标）
     */
    getMousePosition(e) {
        const rect = this.canvas.getBoundingClientRect();
        const px = e.clientX - rect.left;
        const py = e.clientY - rect.top;

        // 转换到图谱坐标（逆变换）
        const x = (px - this.transform.x) / this.transform.scale;
        const y = (py - this.transform.y) / this.transform.scale;

        return { x, y, px, py };
    }

    /**
     * 悬停检测
     */
    handleHover(pos) {
        const nodeId = this.hitTestNode(pos);

        if (nodeId !== this.hoveredNodeId) {
            this.hoveredNodeId = nodeId;
            if (this.onNodeHoverCallback) {
                this.onNodeHoverCallback(nodeId);
            }
            this.needsRender = true;
        }
    }

    /**
     * 拖拽移动
     */
    handleDragMove(pos) {
        // 立即更新本地位置（避免被 Worker tick 覆盖）
        if (this.positions.has(this.draggingNodeId)) {
            this.positions.get(this.draggingNodeId).x = pos.x;
            this.positions.get(this.draggingNodeId).y = pos.y;
        }

        // 发送给 Coordinator
        if (this.onNodeDragCallback) {
            this.onNodeDragCallback(this.draggingNodeId, pos);
        }
    }

    /**
     * 点击检测（返回节点 ID）
     */
    hitTestNode(pos) {
        for (const node of this.nodes) {
            const nodePos = this.positions.get(node.id);
            if (!nodePos) continue;

            const dx = pos.x - nodePos.x;
            const dy = pos.y - nodePos.y;
            const distance = Math.sqrt(dx * dx + dy * dy);

            if (distance < this.nodeRadius + 5) {
                return node.id;
            }
        }
        return null;
    }

    /**
     * 启动渲染循环
     */
    startRenderLoop() {
        const loop = () => {
            if (this.needsRender) {
                this.render();
                this.needsRender = false;
            }
            this.rafId = requestAnimationFrame(loop);
        };
        loop();
    }

    /**
     * 绘制
     */
    render() {
        if (!this.ctx) {
            console.warn('[Renderer2D] render called but ctx is null');
            return;
        }

        // 清空画布
        this.ctx.clearRect(0, 0, this.width, this.height);

        // 应用变换
        this.ctx.save();
        this.ctx.translate(this.transform.x, this.transform.y);
        this.ctx.scale(this.transform.scale, this.transform.scale);

        // 绘制边
        this.renderLinks();

        // 绘制节点
        this.renderNodes();

        this.ctx.restore();

        // 只在特定间隔输出日志
        this._renderCount = (this._renderCount || 0) + 1;
        if (this._renderCount <= 5 || this._renderCount % 60 === 0) {
            console.log('[Renderer2D] render #', this._renderCount, 'nodes=', this.nodes.length, 'positions=', this.positions.size);
        }
    }

    /**
     * 绘制边
     */
    renderLinks() {
        for (const link of this.links) {
            const sId = link.source.id || link.source;
            const tId = link.target.id || link.target;

            const sourcePos = this.positions.get(sId);
            const targetPos = this.positions.get(tId);

            if (!sourcePos || !targetPos) continue;

            const isHighlighted = this.highlightLinkIds.has(`${sId}-${tId}`);
            const type = link.type || 'reference';
            const color = isHighlighted ? this.edgeColorsLight[type] : this.edgeColors[type];
            const width = isHighlighted ? this.linkWidthHighlight : this.linkWidth;

            // 绘制线
            this.ctx.beginPath();
            this.ctx.moveTo(sourcePos.x, sourcePos.y);
            this.ctx.lineTo(targetPos.x, targetPos.y);
            this.ctx.strokeStyle = color;
            this.ctx.lineWidth = width;
            this.ctx.stroke();

            // 绘制箭头
            this.drawArrow(sourcePos, targetPos, color, isHighlighted);
        }
    }

    /**
     * 绘制箭头
     */
    drawArrow(source, target, color, isLarge) {
        const dx = target.x - source.x;
        const dy = target.y - source.y;
        const angle = Math.atan2(dy, dx);
        const length = Math.sqrt(dx * dx + dy * dy);

        const arrowLength = isLarge ? 8 : 6;
        const arrowWidth = isLarge ? 4 : 3;

        // 箭头位置（距离目标节点一定距离）
        const dist = this.nodeRadius + 4;
        const ax = target.x - dist * Math.cos(angle);
        const ay = target.y - dist * Math.sin(angle);

        this.ctx.save();
        this.ctx.translate(ax, ay);
        this.ctx.rotate(angle);

        this.ctx.beginPath();
        this.ctx.moveTo(0, 0);
        this.ctx.lineTo(-arrowLength, -arrowWidth);
        this.ctx.lineTo(-arrowLength, arrowWidth);
        this.ctx.closePath();

        this.ctx.fillStyle = color;
        this.ctx.fill();

        this.ctx.restore();
    }

    /**
     * 绘制节点
     */
    renderNodes() {
        for (const node of this.nodes) {
            const pos = this.positions.get(node.id);
            if (!pos) continue;

            // 视口变换后的屏幕坐标
            const screenX = pos.x * this.transform.scale + this.transform.x;
            const screenY = pos.y * this.transform.scale + this.transform.y;

            // 检查节点是否在屏幕内
            const inView = screenX >= -50 && screenX <= this.width + 50 &&
                          screenY >= -50 && screenY <= this.height + 50;

            // 如果节点在屏幕外，输出警告
            if (!inView && this._renderCount % 60 === 0) {
                console.warn('[Renderer2D] Node OUT OF VIEW:', node.id, 'world=(', pos.x.toFixed(2), ',', pos.y.toFixed(2), ')', 'screen=(', screenX.toFixed(2), ',', screenY.toFixed(2), ')', 'transform=', JSON.stringify(this.transform));
            }

            const isPrimary = this.primaryHighlightId === node.id;
            const isSecondary = this.secondaryHighlightIds.has(node.id);
            const isHovered = this.hoveredNodeId === node.id;
            const isHighlighted = isPrimary || isSecondary || isHovered;

            // 节点颜色
            const fileColor = this.nodeColor(node.file);
            const strokeColor = isHighlighted ? '#fff' : fileColor;
            const fillColor = isHighlighted ? '#3a3a4a' : '#2d2d2d';
            const strokeWidth = isPrimary ? 3.5 : (isHighlighted ? 2.5 : this.nodeStrokeWidth);

            // 绘制圆环
            this.ctx.beginPath();
            this.ctx.arc(pos.x, pos.y, this.nodeRadius, 0, Math.PI * 2);
            this.ctx.fillStyle = fillColor;
            this.ctx.fill();
            this.ctx.strokeStyle = strokeColor;
            this.ctx.lineWidth = strokeWidth;
            this.ctx.stroke();

            // 绘制缩写标签
            const abbr = this.makeAbbr(node.title);
            this.ctx.fillStyle = '#d4d4d4';
            this.ctx.font = '9px sans-serif';
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            this.ctx.fillText(abbr, pos.x, pos.y);

            // 绘制名称标签
            const label = node.title.length > 14 ? node.title.substring(0, 14) + '...' : node.title;
            this.ctx.fillStyle = '#808080';
            this.ctx.font = '10px sans-serif';
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'bottom';
            this.ctx.fillText(label, pos.x, pos.y - this.nodeRadius - 6);
        }
    }

    /**
     * 节点颜色（按文件哈希）
     */
    nodeColor(file) {
        const palette = ['#3a6ea5', '#3d8b7a', '#9b7a65', '#8a6b8a', '#4a7ab5', '#5a8a5a', '#9a9a6a', '#7a9a8a'];
        let h = 0;
        for (let i = 0; i < (file || '').length; i++) {
            h = ((h << 5) - h) + file.charCodeAt(i) | 0;
        }
        return palette[Math.abs(h) % palette.length];
    }

    /**
     * 缩写生成
     */
    makeAbbr(title) {
        if (!title) return '?';
        if (/[\u4e00-\u9fff]/.test(title)) return title.substring(0, 2);
        const words = title.split(/[\s_-]+/).filter(Boolean);
        if (words.length === 1) return words[0].substring(0, 3).toUpperCase();
        return words.map(w => w[0]).join('').toUpperCase().substring(0, 3);
    }
}