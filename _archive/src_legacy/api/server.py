"""Memoria Python-JS 桥接层

精简的 pywebview API，只做数据路由：
- 选择/设置知识库路径
- 触发构建
- 读取索引/图谱/文件
- 保存编辑
"""

import json
import os

import webview

from ..core.builder import build as core_build
from ..core.store import load_index, load_graph, read_file


class MemoriaAPI:
    """暴露给 JS 前端的 Python API"""

    def __init__(self):
        self.kb_path: str | None = None

    # ========== 知识库管理 ==========

    def select_directory(self) -> str:
        """打开目录选择对话框"""
        result = webview.windows[0].create_file_dialog(
            webview.FileDialog.FOLDER
        )
        if result:
            self.kb_path = result[0]
            return self.kb_path
        return ''

    def set_kb_path(self, path: str) -> dict:
        """设置知识库路径"""
        if not os.path.isdir(path):
            return {'status': 'error', 'message': f'目录不存在: {path}'}
        self.kb_path = path
        return {'status': 'ok', 'path': path}

    def get_kb_path(self) -> str:
        return self.kb_path or ''

    # ========== 构建 ==========

    def build_index(self) -> dict:
        """构建知识库索引"""
        if not self.kb_path:
            return {'status': 'error', 'message': '未设置知识库路径'}
        return core_build(self.kb_path)

    # ========== 读取 ==========

    def get_index(self) -> dict:
        """获取 index.json"""
        if not self.kb_path:
            return {}
        return load_index(self.kb_path) or {}

    def get_graph(self) -> dict:
        """获取 graph.json"""
        if not self.kb_path:
            return {}
        return load_graph(self.kb_path) or {}

    def get_file(self, rel_path: str) -> str:
        """读取文件内容"""
        if not self.kb_path:
            return ''
        return read_file(self.kb_path, rel_path) or ''

    # ========== 编辑 ==========

    def save_file(self, rel_path: str, content: str) -> dict:
        """保存文件"""
        if not self.kb_path:
            return {'status': 'error', 'message': '未设置知识库路径'}
        full_path = os.path.join(self.kb_path, rel_path)
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return {'status': 'ok'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def save_frontmatter(self, rel_path: str, fm_data: dict) -> dict:
        """保存文件的 frontmatter（保留正文不变）"""
        if not self.kb_path:
            return {'status': 'error', 'message': '未设置知识库路径'}

        full_path = os.path.join(self.kb_path, rel_path)
        if not os.path.isfile(full_path):
            return {'status': 'error', 'message': f'文件不存在: {rel_path}'}

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                raw = f.read()

            # 拆分 frontmatter 和 body
            lines = raw.split('\n')
            if lines and lines[0].strip() == '---':
                end = -1
                for i in range(1, len(lines)):
                    if lines[i].strip() == '---':
                        end = i
                        break
                if end > 0:
                    body = '\n'.join(lines[end + 1:])
                else:
                    body = raw
            else:
                body = raw

            import yaml
            fm_text = yaml.dump(fm_data, allow_unicode=True, default_flow_style=False)
            new_content = f'---\n{fm_text}---\n{body}'

            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            return {'status': 'ok'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
