"""向量索引构建与管理（双模型融合）

使用两个模型分别编码中英文：
- all-MiniLM-L6-v2 (80MB, 384维) - 英文模型
- BAAI/bge-small-zh-v1.5 (95MB, 512维) - 中文模型

输入文本构造（基于知识点提取，带权重）：
- provides (信号A): 高权重 - 文档显式声明"我提供这个知识"
- tags (信号C): 高权重 - 用户定义的主题标签
- user_added: 高权重 - 用户审核时手动添加的关键词
- jieba术语 (信号D): 中权重 - 正文术语
- [[id]]引用 (信号B): 极低权重 - 文档只是提及，不是主体
"""
import json
import os

# 设置 HuggingFace 离线模式，避免每次启动都去检查模型更新导致网络超时卡顿
# 模型已缓存到本地后就不再需要联网
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import numpy as np

from .extractor import extract_from_node, build_embedding_text, apply_user_review


# 全局模型实例（避免重复加载）
_model_en = None  # 英文模型
_model_zh = None  # 中文模型


def get_model_en():
    """懒加载英文模型"""
    global _model_en
    if _model_en is None:
        from sentence_transformers import SentenceTransformer
        _model_en = SentenceTransformer('all-MiniLM-L6-v2')
    return _model_en


def get_model_zh():
    """懒加载中文模型"""
    global _model_zh
    if _model_zh is None:
        from sentence_transformers import SentenceTransformer
        _model_zh = SentenceTransformer('BAAI/bge-small-zh-v1.5')
    return _model_zh


def get_model():
    """兼容旧接口：返回英文模型"""
    return get_model_en()


def read_node_body(node: dict, kb_path: str) -> str:
    """读取节点正文（从源文件读，剥掉 Frontmatter）

    node 必须含 'file' 字段（index.json 提供）。
    """
    file_path = node.get("file", "")
    if not file_path:
        return ""

    # file 字段可能是绝对路径或相对 kb_path 的路径
    if not os.path.isabs(file_path):
        file_path = os.path.join(kb_path, file_path)

    if not os.path.exists(file_path):
        return ""

    with open(file_path, "r", encoding="utf-8") as f:
        raw = f.read()

    # 剥 Frontmatter：第一行是 --- 才处理
    lines = raw.split("\n")
    if not lines or lines[0].strip() != "---":
        return raw

    # 找下一个 ---
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            # 返回 --- 之后的正文
            return "\n".join(lines[i + 1:]).lstrip("\n")

    # 没找到结束 ---，返回原文件
    return raw


def build(kb_path: str) -> dict:
    """
    为知识库构建双模型向量索引

    输出:
        build/embeddings_en.npy        - 英文向量矩阵
        build/embeddings_zh.npy        - 中文向量矩阵
        build/embeddings_index.json    - node_id 列表
        build/embeddings_extracted.json - 提取结果（供审核 UI 使用）

    Returns:
        {"status": "ok", "count": N, "extracted": {...}} 或 {"status": "error", ...}
    """
    build_dir = os.path.join(kb_path, ".build")
    index_path = os.path.join(build_dir, "index.json")

    if not os.path.exists(index_path):
        return {"status": "error", "message": "index.json 不存在，请先构建索引"}

    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    nodes = index.get("nodes", [])
    if not nodes:
        return {"status": "error", "message": "知识库中没有节点"}

    # 加载用户审核配置（如有）
    config_path = os.path.join(build_dir, "embeddings_config.json")
    user_configs = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            user_configs = json.load(f)

    # 对每个节点提取知识点
    extracted_map = {}
    texts = []
    node_ids = []

    for node in nodes:
        # 从源文件读正文（剥 Frontmatter）
        content = read_node_body(node, kb_path)

        # 提取知识点信号
        extracted = extract_from_node(node, content)
        extracted_map[node["id"]] = extracted

        # 应用用户审核
        if node["id"] in user_configs:
            extracted = apply_user_review(extracted, user_configs[node["id"]])
            extracted_map[node["id"]] = extracted

        # 构造 Embedding 输入
        text = build_embedding_text(extracted)
        texts.append(text)
        node_ids.append(node["id"])

    # 双模型分别编码
    model_en = get_model_en()
    model_zh = get_model_zh()
    embeddings_en = model_en.encode(texts, show_progress_bar=False)
    embeddings_zh = model_zh.encode(texts, show_progress_bar=False)

    # 保存两套向量
    np.save(os.path.join(build_dir, "embeddings_en.npy"), embeddings_en)
    np.save(os.path.join(build_dir, "embeddings_zh.npy"), embeddings_zh)
    with open(os.path.join(build_dir, "embeddings_index.json"), "w", encoding="utf-8") as f:
        json.dump(node_ids, f, ensure_ascii=False)

    # 保存提取结果（供审核 UI 使用）
    ext_path = os.path.join(build_dir, "embeddings_extracted.json")
    with open(ext_path, "w", encoding="utf-8") as f:
        json.dump(extracted_map, f, ensure_ascii=False, indent=2)

    return {"status": "ok", "count": len(node_ids), "extracted": extracted_map}


def load_embeddings(kb_path: str):
    """加载双模型向量索引

    Returns:
        (embeddings_en, embeddings_zh, node_ids)
        如果不存在返回 (None, None, None)
    """
    build_dir = os.path.join(kb_path, ".build")
    emb_en_path = os.path.join(build_dir, "embeddings_en.npy")
    emb_zh_path = os.path.join(build_dir, "embeddings_zh.npy")
    idx_path = os.path.join(build_dir, "embeddings_index.json")

    # 兼容旧版单模型索引
    old_emb_path = os.path.join(build_dir, "embeddings.npy")
    if not os.path.exists(emb_en_path) and os.path.exists(old_emb_path):
        embeddings_en = np.load(old_emb_path)
        embeddings_zh = None
    else:
        if not os.path.exists(emb_en_path) or not os.path.exists(idx_path):
            return None, None, None
        embeddings_en = np.load(emb_en_path)
        embeddings_zh = np.load(emb_zh_path) if os.path.exists(emb_zh_path) else None

    with open(idx_path, "r", encoding="utf-8") as f:
        node_ids = json.load(f)

    return embeddings_en, embeddings_zh, node_ids


def cosine_similarity(a, b):
    """计算余弦相似度"""
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)
