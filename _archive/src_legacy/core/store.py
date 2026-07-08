"""Memoria 索引存储

读写 .build/ 目录下的索引文件。
前端通过 API 层间接调用，不直接操作文件系统。
"""

import json
import os
from typing import Optional

from .models import BuildIndex


def load_index(kb_path: str) -> Optional[dict]:
    """加载 index.json

    Returns:
        dict 或 None（文件不存在时）
    """
    path = os.path.join(kb_path, '.build', 'index.json')
    if not os.path.isfile(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def load_graph(kb_path: str) -> Optional[dict]:
    """加载 graph.json

    Returns:
        dict 或 None（文件不存在时）
    """
    path = os.path.join(kb_path, '.build', 'graph.json')
    if not os.path.isfile(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def read_file(kb_path: str, rel_path: str) -> Optional[str]:
    """读取知识库中的文件内容

    Args:
        kb_path: 知识库根目录
        rel_path: 相对路径

    Returns:
        文件内容字符串，或 None
    """
    full_path = os.path.join(kb_path, rel_path)
    if not os.path.isfile(full_path):
        return None
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            return f.read()
    except OSError:
        return None


def build_output_exists(kb_path: str) -> bool:
    """检查 .build/ 目录是否存在"""
    return os.path.isdir(os.path.join(kb_path, '.build'))
