"""图谱分析：纯图算法，找缺口、孤岛、密度统计"""
import json
import os
from collections import defaultdict


def analyze(kb_path: str) -> dict:
    """
    分析知识图谱结构

    Returns:
        {
            "domains": [{"name": ..., "node_count": ...}, ...],
            "orphans": ["node_id", ...],
            "gaps": ["referenced_but_undefined_id", ...],
            "stats": {"total_nodes": ..., "total_links": ..., "density": ...}
        }
    """
    index_path = os.path.join(kb_path, ".build", "index.json")
    graph_path = os.path.join(kb_path, ".build", "graph.json")

    if not os.path.exists(index_path):
        return {"error": "index.json 不存在"}

    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)
    with open(graph_path, "r", encoding="utf-8") as f:
        graph = json.load(f)

    nodes = index.get("nodes", [])
    citations = index.get("citations", [])
    graph_nodes = graph.get("nodes", [])
    graph_links = graph.get("links", [])

    # 1. 统计
    total_nodes = len(graph_nodes)
    total_links = len(graph_links)

    # 2. 缺口检测：被引用但未定义的 id
    defined_ids = {n["id"] for n in nodes}
    referenced_ids = set()
    for cite in citations:
        referenced_ids.add(cite["target"])
    for link in graph_links:
        referenced_ids.add(link["source"])
        referenced_ids.add(link["target"])

    gaps = list(referenced_ids - defined_ids)

    # 3. 孤岛检测：没有任何连接的节点
    connected_ids = set()
    for link in graph_links:
        connected_ids.add(link["source"])
        connected_ids.add(link["target"])

    orphans = [n["id"] for n in graph_nodes if n["id"] not in connected_ids]

    # 4. 领域聚类（基于 tags 的简单分组）
    tag_groups = defaultdict(list)
    for node in nodes:
        tags = node.get("tags", [])
        if tags:
            # 用第一个 tag 作为领域
            tag_groups[tags[0]].append(node["id"])
        else:
            tag_groups["uncategorized"].append(node["id"])

    domains = [{"name": tag, "node_count": len(ids), "nodes": ids}
               for tag, ids in sorted(tag_groups.items(), key=lambda x: -len(x[1]))]

    # 5. 密度计算
    max_possible_links = total_nodes * (total_nodes - 1) if total_nodes > 1 else 1
    density = total_links / max_possible_links if max_possible_links > 0 else 0

    return {
        "stats": {
            "total_nodes": total_nodes,
            "total_links": total_links,
            "density": round(density, 4),
        },
        "domains": domains,
        "orphans": orphans,
        "gaps": gaps,
        "suggestions": _generate_suggestions(gaps, orphans, domains),
    }


def _generate_suggestions(gaps: list, orphans: list, domains: list) -> list:
    """生成优化建议"""
    suggestions = []

    for gap in gaps:
        suggestions.append({
            "type": "gap",
            "message": f"知识点 '{gap}' 被引用但尚未创建。建议创建该节点。",
        })

    for orphan in orphans:
        suggestions.append({
            "type": "orphan",
            "message": f"知识点 '{orphan}' 没有任何连接。考虑添加 prerequisite 或 extend 关系。",
        })

    # 如果有多个领域，建议跨领域连接
    if len(domains) >= 2:
        large_domains = [d for d in domains if d["node_count"] >= 2]
        if len(large_domains) >= 2:
            suggestions.append({
                "type": "cross-domain",
                "message": f"检测到 {len(domains)} 个领域分组。"
                           f"考虑在 '{large_domains[0]['name']}' 和 "
                           f"'{large_domains[1]['name']}' 之间建立连接。",
            })

    return suggestions
