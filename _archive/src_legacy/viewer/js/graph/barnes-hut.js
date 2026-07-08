/**
 * Barnes-Hut 四叉树实现
 *
 * 用于加速斥力计算，将 O(n²) 降至 O(n log n)
 *
 * 原理：将空间递归划分为四个子区域，每个区域存储：
 * - 总质量（节点数量）
 * - 质心位置（节点平均位置）
 *
 * 当计算某个节点的斥力时：
 * - 远距离区域：用质心近似，避免遍历所有节点
 * - 近距离区域：精确计算每个节点
 *
 * 判断标准：θ = distance / regionSize
 * - θ > 阈值（如 0.5）：近似计算
 * - θ < 阈值：递归进入子区域
 */

/**
 * 四叉树节点
 */
class QuadNode {
    constructor(x, y, size, depth = 0) {
        this.x = x;          // 区域中心 x
        this.y = y;          // 区域中心 y
        this.size = size;    // 区域尺寸
        this.depth = depth;  // 递归深度（防止过深）

        this.mass = 0;       // 总质量（节点数量）
        this.cx = 0;         // 质心 x
        this.cy = 0;         // 质心 y

        this.children = null; // 四个子节点 [NW, NE, SW, SE] 或 null
        this.node = null;    // 单个节点（叶子节点时）
    }

    /**
     * 判断是否为叶子节点（无子节点）
     */
    isLeaf() {
        return this.children === null;
    }

    /**
     * 判断是否为空节点（无节点、无质量）
     */
    isEmpty() {
        return this.mass === 0 && this.node === null;
    }

    /**
     * 获取子区域索引 (0-3)
     * NW(0) | NE(1)
     * ------|------
     * SW(2) | SE(3)
     */
    getQuadrant(px, py) {
        const dx = px - this.x;
        const dy = py - this.y;
        const half = this.size / 2;

        if (dx < 0 && dy < 0) return 0; // NW
        if (dx >= 0 && dy < 0) return 1; // NE
        if (dx < 0 && dy >= 0) return 2; // SW
        return 3; // SE
    }

    /**
     * 获取子区域中心坐标和尺寸
     */
    getChildBounds(quadrant) {
        const half = this.size / 2;
        const quarter = this.size / 4;

        switch (quadrant) {
            case 0: return { x: this.x - quarter, y: this.y - quarter, size: half }; // NW
            case 1: return { x: this.x + quarter, y: this.y - quarter, size: half }; // NE
            case 2: return { x: this.x - quarter, y: this.y + quarter, size: half }; // SW
            case 3: return { x: this.x + quarter, y: this.y + quarter, size: half }; // SE
        }
    }

    /**
     * 插入节点
     */
    insert(node) {
        // 空节点：直接存储
        if (this.isEmpty()) {
            this.node = node;
            this.mass = 1;
            this.cx = node.x;
            this.cy = node.y;
            return;
        }

        // 深度限制：防止递归过深导致浏览器卡死
        if (this.depth > 20) {
            // 超过最大深度，不再分裂，直接累加质量
            this.mass += 1;
            this.cx = (this.cx * (this.mass - 1) + node.x) / this.mass;
            this.cy = (this.cy * (this.mass - 1) + node.y) / this.mass;
            return;
        }

        // 已有单个节点：需要分裂
        if (this.isLeaf()) {
            // 创建子节点
            this.children = [0, 1, 2, 3].map(q => {
                const bounds = this.getChildBounds(q);
                return new QuadNode(bounds.x, bounds.y, bounds.size, this.depth + 1);
            });

            // 将原节点移到子节点
            const oldNode = this.node;
            this.node = null;
            const oldQuadrant = this.getQuadrant(oldNode.x, oldNode.y);
            this.children[oldQuadrant].insert(oldNode);
        }

        // 插入新节点到对应子区域
        const quadrant = this.getQuadrant(node.x, node.y);
        this.children[quadrant].insert(node);

        // 更新质心
        this.mass += 1;
        this.cx = (this.cx * (this.mass - 1) + node.x) / this.mass;
        this.cy = (this.cy * (this.mass - 1) + node.y) / this.mass;
    }
}

/**
 * Barnes-Hut 四叉树
 */
export class BarnesHutTree {
    constructor(nodes, theta = 0.5) {
        this.theta = theta; // 近似阈值
        this.root = null;

        if (nodes && nodes.length > 0) {
            this.build(nodes);
        }
    }

    /**
     * 构建四叉树
     */
    build(nodes) {
        // 计算边界框
        let minX = Infinity, maxX = -Infinity;
        let minY = Infinity, maxY = -Infinity;

        for (const node of nodes) {
            if (node.x < minX) minX = node.x;
            if (node.x > maxX) maxX = node.x;
            if (node.y < minY) minY = node.y;
            if (node.y > maxY) maxY = node.y;
        }

        // 扩展边界框（防止节点正好在边界上）
        const margin = Math.max(maxX - minX, maxY - minY) * 0.1 || 10;
        minX -= margin;
        maxX += margin;
        minY -= margin;
        maxY += margin;

        // 创建根节点
        const centerX = (minX + maxX) / 2;
        const centerY = (minY + maxY) / 2;
        const size = Math.max(maxX - minX, maxY - minY);

        this.root = new QuadNode(centerX, centerY, size);

        // 插入所有节点
        for (const node of nodes) {
            this.root.insert(node);
        }
    }

    /**
     * 计算节点受到的斥力
     * @param node 目标节点
     * @returns { fx: number, fy: number } 斥力向量
     */
    calculateRepulsion(node, strength) {
        return this._visit(node, this.root, strength);
    }

    /**
     * 递归访问四叉树节点，累加斥力
     */
    _visit(targetNode, quadNode, strength) {
        if (quadNode.isEmpty()) return { fx: 0, fy: 0 };

        const dx = quadNode.cx - targetNode.x;
        const dy = quadNode.cy - targetNode.y;
        const distance = Math.sqrt(dx * dx + dy * dy) || 1; // 防止距离为 0

        // 计算 θ = distance / size
        const theta = distance / quadNode.size;

        // 远距离：近似计算（用质心代表整个区域）
        if (quadNode.isLeaf() || theta > this.theta) {
            // 防止自斥力（同一节点）
            if (quadNode.isLeaf() && quadNode.node === targetNode) {
                return { fx: 0, fy: 0 };
            }

            // 斥力公式：F = strength * mass / distance²
            // 方向：从质心指向目标节点（排斥）
            const force = strength * quadNode.mass / (distance * distance);
            const fx = -force * dx / distance;
            const fy = -force * dy / distance;

            return { fx, fy };
        }

        // 近距离：递归访问子节点
        let fx = 0, fy = 0;
        for (const child of quadNode.children) {
            const childForce = this._visit(targetNode, child, strength);
            fx += childForce.fx;
            fy += childForce.fy;
        }

        return { fx, fy };
    }

    /**
     * 批量计算所有节点的斥力
     */
    calculateAllRepulsions(nodes, strength) {
        const forces = new Map();

        for (const node of nodes) {
            const { fx, fy } = this.calculateRepulsion(node, strength);
            forces.set(node.id, { fx, fy });
        }

        return forces;
    }
}

/**
 * 创建四叉树并计算斥力（便捷函数）
 */
export function calculateRepulsions(nodes, strength, theta = 0.5) {
    const tree = new BarnesHutTree(nodes, theta);
    return tree.calculateAllRepulsions(nodes, strength);
}