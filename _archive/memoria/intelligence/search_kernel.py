"""统一搜索内核

聚合三种检索策略：
1. 向量相似度（sentence-transformers，双模型）
2. jieba 分词匹配（中文术语）
3. 模糊匹配（编辑距离）

返回知识点级结果，支持 scope 过滤（all/concepts/files）。

两级向量：
- 文件级向量：粗筛，快速定位候选文件
- 知识点级向量：精排，在候选文件内排序具体知识点
"""
import json
import os
import re

import numpy as np


def unified_search(query: str, kb_path: str, scope: str = "all", limit: int = 10) -> list:
    """统一搜索

    Args:
        query: 搜索查询
        kb_path: 知识库路径
        scope: "all" | "concepts" | "files"
        limit: 返回数量上限

    Returns:
        [{"type": "concept"|"file", "id", "name"|"file", "score", "source": ...}, ...]
    """
    if not query.strip():
        return []

    # 加载索引
    index_path = os.path.join(kb_path, ".build", "index.json")
    if not os.path.exists(index_path):
        return []
    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    # 1. 向量相似度（如果向量索引存在）
    vec_results = _vector_search(query, kb_path, index, limit * 3)

    # 2. jieba 分词匹配
    jieba_results = _jieba_search(query, kb_path, index, limit * 3)

    # 3. 模糊匹配（编辑距离）
    fuzzy_results = _fuzzy_search(query, index, limit * 3)

    # 融合结果
    merged = _merge_results(vec_results, jieba_results, fuzzy_results, scope)

    return merged[:limit]


def _vector_search(query, kb_path, index, limit):
    """向量相似度搜索（复用已有 embeddings）"""
    try:
        from memoria.intelligence.search import semantic_search
        results = semantic_search(query, kb_path, top_k=limit)
        if results and isinstance(results, list) and "error" not in results[0]:
            return [
                {
                    "type": "concept",
                    "id": r.get("id", ""),
                    "name": r.get("title", r.get("id", "")),
                    "score": r.get("score", 0),
                    "source": "vector",
                }
                for r in results
            ]
    except Exception as e:
        print(f"vector search fallback: {e}")
    return []


def _jieba_search(query, kb_path, index, limit):
    """jieba 分词匹配

    把 query 分词后，在每个 concept 的 name 和 keywords 中匹配。
    """
    try:
        import jieba
    except ImportError:
        return []

    # 加载已提取的关键词
    ext_path = os.path.join(kb_path, ".build", "embeddings_extracted.json")
    extracted = {}
    if os.path.exists(ext_path):
        try:
            with open(ext_path, "r", encoding="utf-8") as f:
                extracted = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    # 分词
    query_terms = set()
    for word in jieba.cut(query):
        word = word.strip()
        if len(word) >= 2:
            query_terms.add(word.lower())
    if not query_terms:
        query_terms = {query.lower()}

    results = []
    concepts = index.get("concepts", [])
    for concept in concepts:
        cid = concept.get("id", "")
        name = concept.get("name", "")
        name_lower = name.lower()

        # 匹配 concept name
        score = 0.0
        for term in query_terms:
            if term in name_lower:
                score += 0.5

        # 匹配 extracted keywords（用 cid 查）
        if cid in extracted:
            keywords = extracted[cid].get("all_keywords", [])
            kw_lower = [k.lower() for k in keywords]
            for term in query_terms:
                for kw in kw_lower:
                    if term in kw or kw in term:
                        score += 0.3
                        break

        if score > 0:
            results.append({
                "type": "concept",
                "id": cid,
                "name": name,
                "score": min(score, 1.0),
                "source": "jieba",
                "file": concept.get("file", ""),
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def _fuzzy_search(query, index, limit):
    """模糊匹配（编辑距离）"""
    query_lower = query.lower().strip()

    results = []
    concepts = index.get("concepts", [])

    for concept in concepts:
        cid = concept.get("id", "")
        name = concept.get("name", "")

        # 编辑距离匹配 name 和 id
        name_score = _similarity_ratio(query_lower, name.lower())
        id_score = _similarity_ratio(query_lower, cid.lower())
        score = max(name_score, id_score * 0.8)

        if score > 0.3:
            results.append({
                "type": "concept",
                "id": cid,
                "name": name,
                "score": score,
                "source": "fuzzy",
                "file": concept.get("file", ""),
            })

    # 也匹配文件
    for fdata in index.get("files", []):
        fpath = fdata.get("file", "")
        fname = os.path.basename(fpath).lower()
        score = _similarity_ratio(query_lower, fname)
        desc = fdata.get("description", "").lower()
        if query_lower in desc:
            score = max(score, 0.6)

        if score > 0.3:
            results.append({
                "type": "file",
                "id": fpath,
                "name": os.path.basename(fpath),
                "score": score,
                "source": "fuzzy",
                "file": fpath,
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def _similarity_ratio(a: str, b: str) -> float:
    """计算两个字符串的相似度比率（基于编辑距离）"""
    if not a or not b:
        return 0.0
    # 快速路径：完全包含
    if a in b or b in a:
        return min(len(a), len(b)) / max(len(a), len(b))

    # 编辑距离
    dist = _levenshtein(a, b)
    max_len = max(len(a), len(b))
    return 1.0 - dist / max_len if max_len > 0 else 0.0


def _levenshtein(a: str, b: str) -> int:
    """计算编辑距离"""
    if len(a) < len(b):
        a, b = b, a
    if len(b) == 0:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            insert = prev[j + 1] + 1
            delete = curr[j] + 1
            substitute = prev[j] + (ca != cb)
            curr.append(min(insert, delete, substitute))
        prev = curr

    return prev[-1]


def _merge_results(vec_results, jieba_results, fuzzy_results, scope):
    """融合三种搜索结果

    策略：
    - 向量结果权重 0.5
    - jieba 结果权重 0.3
    - 模糊结果权重 0.2
    - 同一 id 取最高分，来源标注主要贡献者
    """
    merged = {}

    def _add(results, weight):
        for r in results:
            # scope 过滤
            if scope == "concepts" and r["type"] != "concept":
                continue
            if scope == "files" and r["type"] != "file":
                continue

            key = (r["type"], r.get("id", ""))
            if key not in merged:
                merged[key] = {
                    "type": r["type"],
                    "id": r.get("id", ""),
                    "name": r.get("name", ""),
                    "score": 0,
                    "sources": [],
                    "file": r.get("file", ""),
                }
            merged[key]["score"] += r["score"] * weight
            merged[key]["sources"].append(r["source"])

    _add(vec_results, 0.5)
    _add(jieba_results, 0.3)
    _add(fuzzy_results, 0.2)

    # 排序
    results = list(merged.values())
    results.sort(key=lambda x: x["score"], reverse=True)
    return results
