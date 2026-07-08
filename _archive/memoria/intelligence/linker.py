"""链接建议：基于向量相似度推荐关联节点"""
import json
import os
import numpy as np

from .embeddings import load_embeddings, cosine_similarity


def suggest_links(node_id: str, kb_path: str, top_k: int = 3) -> list:
    """
    为指定节点建议关联链接

    Args:
        node_id: 目标节点 id
        kb_path: 知识库路径
        top_k: 返回前 N 个建议

    Returns:
        [{"id": ..., "title": ..., "score": 0.91, "suggest_as": "prerequisite"}, ...]
    """
    embeddings, node_ids = load_embeddings(kb_path)
    if embeddings is None:
        return [{"error": "向量索引不存在，请先构建"}]

    # 检查节点是否存在
    if node_id not in node_ids:
        return [{"error": f"节点 '{node_id}' 不存在"}]

    # 加载 index.json
    index_path = os.path.join(kb_path, ".build", "index.json")
    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)
    node_map = {n["id"]: n for n in index["nodes"]}

    # 获取该节点的已有连接
    node = node_map.get(node_id, {})
    existing = set()
    existing.update(node.get("prerequisite", []))
    existing.update(node.get("extend", []))
    existing.update(node.get("analogy", []))
    existing.add(node_id)  # 排除自身

    # 找到该节点的向量位置
    node_pos = node_ids.index(node_id)
    node_vec = embeddings[node_pos]

    # 与所有其他节点计算相似度
    scores = []
    for i, other_id in enumerate(node_ids):
        if other_id in existing:
            continue
        sim = cosine_similarity(node_vec, embeddings[i])
        scores.append((other_id, sim))

    # 排序
    scores.sort(key=lambda x: x[1], reverse=True)

    # 返回 top_k 建议
    results = []
    for other_id, score in scores[:top_k]:
        other = node_map.get(other_id, {})
        # 推断关系类型
        suggest_as = _infer_relation_type(node, other, score)
        results.append({
            "id": other_id,
            "title": other.get("title", other_id),
            "score": float(score),
            "suggest_as": suggest_as,
        })

    return results


def _infer_relation_type(node_a: dict, node_b: dict, score: float) -> str:
    """根据相似度分数推断关系类型"""
    if score > 0.7:
        return "prerequisite"  # 高相似度 → 可能是前置知识
    elif score > 0.5:
        return "extend"  # 中等相似度 → 可能是扩展阅读
    else:
        return "analogy"  # 低相似度 → 可能是类比
