"""Memoria 核心数据模型

知识点 (KnowledgePoint) 是最小单元。
文件是知识点的容器。
边是知识点之间的关系。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------- 枚举 ----------

class EdgeType(Enum):
    """边类型"""
    REFERENCE = "reference"       # 引用（正文 [[链接]] 自动生成）
    PREREQUISITE = "prerequisite" # 前置知识
    EXTEND = "extend"             # 扩展延伸
    ANALOGY = "analogy"           # 类比关系
    CONTAIN = "contain"           # 包含（标题层级自动推导，不存储）


class EdgeStrength(Enum):
    """边强度"""
    STRONG = "strong"   # 强边：实线，节点靠近
    WEAK = "weak"       # 弱边：虚线，节点远离


# ---------- 核心模型 ----------

@dataclass
class KnowledgePoint:
    """知识点 —— 系统最小单元

    三种状态：
    - 正式节点 (candidate=False, id 非空)：在 frontmatter 中声明的知识点，出现在图谱中
    - 候选知识点 (candidate=True, id 为空)：正文标题自动发现的区域，需要用户确认
    - 关键词 (candidate=False, id 为空)：frontmatter 中声明的无 id 标签
    """
    id: str = ""                            # 唯一标识（空=候选或关键词）
    name: str = ""                          # 名称（与标题文字一致）
    file: str = ""                          # 所属文件（相对路径）
    depth: int = 0                          # 标题层级（#=1, ##=2, ###=3）
    line: int = 0                           # 标题所在行号（0=未定位）
    end_line: int = 0                       # 区域结束行号（0=未计算）
    weight: float = 0.5                     # 权重 0~1，影响图谱引力
    tags: list[str] = field(default_factory=list)
    candidate: bool = False                 # 是否为候选知识点（正文标题自动发现）

    # ---- 运行时属性（构建时填充，不序列化到 JSON） ----
    parent_id: Optional[str] = None         # 包含关系的父知识点 id
    children_ids: list[str] = field(default_factory=list)

    @property
    def is_node(self) -> bool:
        """是否有资格成为图谱节点（正式知识点 + 有 id）"""
        return bool(self.id) and not self.candidate

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "file": self.file,
            "depth": self.depth,
            "line": self.line,
            "end_line": self.end_line,
            "weight": self.weight,
            "tags": self.tags,
            "candidate": self.candidate,
            "parent_id": self.parent_id,
            "children_ids": self.children_ids,
        }

    @classmethod
    def from_dict(cls, d: dict) -> KnowledgePoint:
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            file=d.get("file", ""),
            depth=d.get("depth", 0),
            line=d.get("line", 0),
            end_line=d.get("end_line", 0),
            weight=d.get("weight", 0.5),
            tags=d.get("tags", []),
            candidate=d.get("candidate", False),
            parent_id=d.get("parent_id"),
            children_ids=d.get("children_ids", []),
        )


@dataclass
class Edge:
    """边 —— 知识点之间的关系

    source_id 和 target_id 都是知识点的 id。
    CONTAIN 类型的边由构建器自动从标题层级推导，不存入 frontmatter。
    """
    source_id: str = ""                     # 源知识点 id
    target_id: str = ""                     # 目标知识点 id
    type: EdgeType = EdgeType.REFERENCE     # 边类型
    strength: EdgeStrength = EdgeStrength.STRONG  # 边强度
    text: str = ""                          # 引用文本（reference 类型时记录 [[text]]）

    def to_dict(self) -> dict:
        return {
            "source": self.source_id,
            "target": self.target_id,
            "type": self.type.value,
            "strength": self.strength.value,
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Edge:
        return cls(
            source_id=d.get("source", ""),
            target_id=d.get("target", ""),
            type=EdgeType(d.get("type", "reference")),
            strength=EdgeStrength(d.get("strength", "strong")),
            text=d.get("text", ""),
        )


@dataclass
class FileDescriptor:
    """文件描述 —— 知识点的容器

    一个 .md 文件包含多个知识点。
    frontmatter 中声明该文件的 concepts 和 edges。
    """
    path: str = ""                          # 相对路径
    description: str = ""                   # 文件简短描述
    concepts: list[KnowledgePoint] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "file": self.path,
            "description": self.description,
            "concepts": [c.to_dict() for c in self.concepts],
            "edges": [e.to_dict() for e in self.edges],
        }


# ---------- 构建产物 ----------

@dataclass
class BuildIndex:
    """构建产物 —— .build/index.json 的完整结构

    这是系统运行时的唯一数据源，前端所有模块都从这里读取。
    """
    files: list[FileDescriptor] = field(default_factory=list)
    concepts: list[KnowledgePoint] = field(default_factory=list)   # 全局知识点索引（仅有 id 的）
    edges: list[Edge] = field(default_factory=list)                # 全局边索引
    concept_tree: dict = field(default_factory=dict)               # 知识点包含树
    dangling_links: list[dict] = field(default_factory=list)       # 虚链
    duplicates: list[dict] = field(default_factory=list)           # id 冲突

    def to_dict(self) -> dict:
        return {
            "files": [f.to_dict() for f in self.files],
            "concepts": [c.to_dict() for c in self.concepts],
            "edges": [e.to_dict() for e in self.edges],
            "concept_tree": self.concept_tree,
            "dangling_links": self.dangling_links,
            "duplicates": self.duplicates,
        }

    def to_graph_dict(self) -> dict:
        """生成 graph.json 格式（D3/Three.js 通用）

        nodes: [{id, title, file, weight, tags}]
        links: [{source, target, type, strength}]
        """
        nodes = []
        for c in self.concepts:
            if c.is_node:
                nodes.append({
                    "id": c.id,
                    "title": c.name,
                    "file": c.file,
                    "weight": c.weight,
                    "tags": c.tags,
                })

        links = []
        seen = set()
        node_ids = {n["id"] for n in nodes}
        for e in self.edges:
            if e.source_id not in node_ids or e.target_id not in node_ids:
                continue  # 跳过引用不存在节点的边
            key = (e.source_id, e.target_id, e.type.value)
            if key not in seen:
                seen.add(key)
                links.append(e.to_dict())

        return {"nodes": nodes, "links": links}
