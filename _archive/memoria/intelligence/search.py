"""语义检索：双模型融合搜索

根据查询语言动态加权：
- 中文查询：0.3×英文 + 0.7×中文
- 英文查询：0.7×英文 + 0.3×中文
- 混合查询：0.5×英文 + 0.5×中文

支持用户自定义相似度阈值过滤低质量结果。
"""
import json
import os
import re

import numpy as np

from .embeddings import (
    get_model_en, get_model_zh, load_embeddings, cosine_similarity
)


def _detect_language(text: str) -> str:
    """检测文本语言

    Returns:
        'zh' - 中文为主
        'en' - 英文为主
        'mix' - 混合
    """
    # 统计中文字符数
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    # 统计英文字母数
    english_chars = len(re.findall(r'[a-zA-Z]', text))
    total = chinese_chars + english_chars

    if total == 0:
        return 'mix'

    zh_ratio = chinese_chars / total
    if zh_ratio > 0.6:
        return 'zh'
    elif zh_ratio < 0.3:
        return 'en'
    else:
        return 'mix'


def _get_weights(lang: str) -> tuple:
    """根据语言返回 (英文权重, 中文权重)"""
    if lang == 'zh':
        return (0.3, 0.7)
    elif lang == 'en':
        return (0.7, 0.3)
    else:  # mix
        return (0.5, 0.5)


def _get_threshold(kb_path: str) -> float:
    """读取用户配置的相似度阈值，默认 0.2"""
    config_path = os.path.join(kb_path, ".build", "search_config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                return config.get("similarity_threshold", 0.2)
        except (json.JSONDecodeError, IOError):
            pass
    return 0.2


def semantic_search(query: str, kb_path: str, top_k: int = 5) -> list:
    """
    双模型融合语义搜索

    Args:
        query: 用户的自然语言问题
        kb_path: 知识库路径
        top_k: 返回前 N 个结果

    Returns:
        [{"id": ..., "title": ..., "score": 0.87, "score_en": ..., "score_zh": ...}, ...]
    """
    # 加载双模型向量索引
    embeddings_en, embeddings_zh, node_ids = load_embeddings(kb_path)
    if embeddings_en is None:
        return [{"error": "向量索引不存在，请先构建"}]

    # 加载 index.json 获取节点标题
    index_path = os.path.join(kb_path, ".build", "index.json")
    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)
    node_map = {n["id"]: n for n in index["nodes"]}

    # 检测查询语言 → 决定权重
    lang = _detect_language(query)
    w_en, w_zh = _get_weights(lang)

    # 编码查询（双模型）
    query_vec_en = get_model_en().encode([query])[0]
    if embeddings_zh is not None:
        query_vec_zh = get_model_zh().encode([query])[0]
    else:
        # 兼容旧版单模型索引
        w_en, w_zh = 1.0, 0.0
        query_vec_zh = None

    # 计算融合相似度
    threshold = _get_threshold(kb_path)
    scores = []
    for i, node_id in enumerate(node_ids):
        sim_en = cosine_similarity(query_vec_en, embeddings_en[i])
        if query_vec_zh is not None and embeddings_zh is not None:
            sim_zh = cosine_similarity(query_vec_zh, embeddings_zh[i])
            sim = w_en * sim_en + w_zh * sim_zh
        else:
            sim_zh = 0.0
            sim = sim_en

        scores.append((node_id, sim, sim_en, sim_zh))

    # 排序
    scores.sort(key=lambda x: x[1], reverse=True)

    # 阈值过滤 + 返回 top_k
    results = []
    for node_id, score, score_en, score_zh in scores[:top_k]:
        if score < threshold:
            continue  # 低于阈值过滤
        node = node_map.get(node_id, {})
        results.append({
            "id": node_id,
            "title": node.get("title", node_id),
            "score": float(score),
            "score_en": float(score_en),
            "score_zh": float(score_zh),
            "lang": lang,
        })

    return results
