#!/usr/bin/env python3
"""Memoria 桌面应用入口

启动 pywebview 窗口，加载 viewer/index.html，
通过 js_api 桥接 Python 后端和 JS 前端。
"""
import json
import os
import re
import sys
from pathlib import Path

import webview

from memoria.builder import build as python_build


class MemoriaAPI:
    """暴露给 JS 前端的 Python API"""

    def __init__(self):
        self.kb_path = None  # 当前知识库路径

    # ========== 知识库管理 ==========

    def select_directory(self) -> str:
        """打开目录选择对话框"""
        import webview.platforms.winforms as winforms  # type: ignore
        result = webview.windows[0].create_file_dialog(
            webview.FOLDER_DIALOG
        )
        if result:
            self.kb_path = result[0]
            return self.kb_path
        return ""

    def set_kb_path(self, path: str) -> dict:
        """设置知识库路径

        判定标准：目录存在即可。用户可以导入一个全新的空文件夹，
        也可以导入已有 .md 文件的文件夹。
        """
        if not os.path.isdir(path):
            return {"status": "error", "message": f"目录不存在: {path}"}
        self.kb_path = path
        return {"status": "ok", "path": path}

    def get_kb_path(self) -> str:
        """获取当前知识库路径"""
        return self.kb_path or ""

    # ========== 编译器 ==========

    def _collect_md_files(self):
        """收集知识库内所有 .md 文件（排除 .build 目录）

        Returns:
            list[str]: 绝对路径列表
        """
        md_files = []
        for root, dirs, files in os.walk(self.kb_path):
            if ".build" in dirs:
                dirs.remove(".build")
            for fname in files:
                if fname.endswith(".md"):
                    md_files.append(os.path.join(root, fname))
        return md_files

    def _is_cache_valid(self) -> bool:
        """检测 .build/ 缓存是否有效

        判定标准：
        1. index.json 存在
        2. index.json 的 mtime >= 所有 .md 文件的最大 mtime
        3. .md 文件数量与 index.json 中 nodes 数量一致（防止增删文件后缓存过期）

        Returns:
            bool
        """
        index_path = os.path.join(self.kb_path, ".build", "index.json")
        if not os.path.exists(index_path):
            return False

        try:
            idx_mtime = os.path.getmtime(index_path)
        except OSError:
            return False

        md_files = self._collect_md_files()
        if not md_files:
            return False

        # 检测任一 md 文件比 index.json 新
        for f in md_files:
            try:
                if os.path.getmtime(f) > idx_mtime:
                    return False
            except OSError:
                return False

        # 检测 md 文件数量与 files 数量一致（新数据模型）
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index = json.load(f)
            if len(index.get("files", index.get("nodes", []))) != len(md_files):
                return False
        except (OSError, json.JSONDecodeError):
            return False

        return True

    def load_index(self) -> dict:
        """快速加载已持久化的索引缓存（不重建）

        首次导入后，.build/ 下已持久化 index.json / graph.json /
        embeddings_extracted.json。再次打开时调用此方法可直接复用，
        跳过 C++ 编译器和 sentence-transformers 模型加载，实现秒开。

        缓存有效性由 _is_cache_valid() 判定：
        - 有效：返回 {"status": "ok", ...} 含完整索引数据
        - 无效：返回 {"status": "stale"} 由前端 fallback 到 build_index()
        """
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}

        if not self._is_cache_valid():
            return {"status": "stale"}

        output = os.path.join(self.kb_path, ".build")
        result = {"status": "ok", "_from_cache": True}

        # 加载 index.json
        index_path = os.path.join(output, "index.json")
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                result["index"] = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            return {"status": "stale", "message": f"index.json 读取失败: {e}"}

        # 加载 graph.json
        graph_path = os.path.join(output, "graph.json")
        if os.path.exists(graph_path):
            try:
                with open(graph_path, "r", encoding="utf-8") as f:
                    result["graph"] = json.load(f)
            except (OSError, json.JSONDecodeError):
                pass

        # 新 builder 已在 index.json 中内置 dangling_links / duplicates / warnings
        idx = result.get("index") or {}
        warnings = []
        for d in idx.get("dangling_links", []):
            warnings.append(f"Broken citation: [[{d['text']}]] in {os.path.basename(d.get('source_file', ''))}")
        for d in idx.get("duplicates", []):
            warnings.append(f"Duplicate id: {d['id']} in {len(d.get('files', []))} files")
        result["warnings"] = warnings

        # stats：从 index 直接统计
        result["stats"] = {
            "nodes": len(idx.get("concepts", idx.get("nodes", []))),
            "relations": len((result.get("graph") or {}).get("links", [])),
            "citations": len(idx.get("citations", [])),
        }

        # 问题文件检测（轻量，纯文件扫描）
        inspection = self.inspect_files()
        if inspection.get("status") == "ok":
            result["issues"] = inspection["issues"]

        return result

    def build_index(self) -> dict:
        """构建知识库索引（Python 原生 builder，替代 C++）"""
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}

        output = os.path.join(self.kb_path, ".build")
        result = python_build(self.kb_path, output)

        if result.get("status") == "ok":
            # index 和 graph 已由 builder 写入 .build/，直接加载
            index_path = os.path.join(output, "index.json")
            if os.path.exists(index_path):
                with open(index_path, "r", encoding="utf-8") as f:
                    result["index"] = json.load(f)

            graph_path = os.path.join(output, "graph.json")
            if os.path.exists(graph_path):
                with open(graph_path, "r", encoding="utf-8") as f:
                    result["graph"] = json.load(f)

            # 自动构建向量索引
            try:
                from memoria.intelligence.embeddings import build as build_embeddings
                emb_result = build_embeddings(self.kb_path)
                if emb_result.get("status") == "ok":
                    result["embeddings_count"] = emb_result.get("count", 0)
                else:
                    result["embeddings_error"] = emb_result.get("message", "")
            except Exception as e:
                result["embeddings_error"] = str(e)

            # 从 index 中提取 warnings（虚链 + 冲突）
            idx = result.get("index") or {}
            warnings = []
            for d in idx.get("dangling_links", []):
                warnings.append(f"Broken citation: [[{d['text']}]] in {os.path.basename(d.get('source_file', ''))}")
            for d in idx.get("duplicates", []):
                warnings.append(f"Duplicate id: {d['id']} in {len(d.get('files', []))} files")
            result["warnings"] = warnings

        # 附带问题文件检测
        inspection = self.inspect_files()
        if inspection.get("status") == "ok":
            result["issues"] = inspection["issues"]

        return result

    def _detect_orphan_nodes(self, index: dict, graph: dict) -> list:
        """检测孤立节点：没有任何 prerequisite/extend/analogy/citation 关系的节点

        Returns:
            ["Orphan node: <id> (<title>)", ...]
        """
        if not index or not graph:
            return []

        # 收集所有有连边的节点 id
        connected = set()
        for link in graph.get("links", []):
            connected.add(link.get("source"))
            connected.add(link.get("target"))

        # 收集所有有 citation 的节点 id（正文中用了 [[id]]）
        for node in index.get("nodes", []):
            if node.get("citations"):
                connected.add(node.get("id"))

        orphans = []
        for node in index.get("nodes", []):
            nid = node.get("id", "")
            if nid not in connected:
                title = node.get("title", nid)
                orphans.append(f"Orphan node: {nid} ({title})")

        return orphans

    def _enrich_index(self, index: dict) -> dict:
        """后处理 index.json：
        - 收集虚链（citations 中 target 不在 nodes 里的）
        - 检测冗余 provides（同一 id 被多个文件声明）
        - 构造 id→files 映射（支持多匹配弹窗）
        """
        if not index:
            return None

        nodes = index.get("nodes", [])
        citations = index.get("citations", [])

        # 已定义的 id 集合（含 provides 子 id）
        defined_ids = set()
        # id → 持有该 id 的文件列表（用于冗余检测）
        id_to_files = {}
        for node in nodes:
            nid = node.get("id", "")
            if not nid:
                continue
            defined_ids.add(nid)
            f = node.get("file", "")
            id_to_files.setdefault(nid, []).append({
                "file": f,
                "title": node.get("title", nid),
            })

        # 虚链：citations 中 target 不在 defined_ids
        dangling = []
        dangling_set = set()
        for cite in citations:
            target = cite.get("target", "")
            if target and target not in defined_ids and target not in dangling_set:
                dangling_set.add(target)
                dangling.append({
                    "id": target,
                    "referenced_by": cite.get("source", ""),
                })

        # 冗余：id 被多个文件声明
        duplicates = []
        for nid, files in id_to_files.items():
            if len(files) > 1:
                duplicates.append({
                    "id": nid,
                    "files": files,
                })

        index["dangling_links"] = dangling
        index["duplicates"] = duplicates
        index["id_to_files"] = id_to_files
        return index

    def check_index(self) -> dict:
        """检查知识库（不构建）- 基于 Python builder 的虚链/冲突检测"""
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}

        index_path = os.path.join(self.kb_path, ".build", "index.json")
        if not os.path.exists(index_path):
            return {"status": "error", "message": "请先构建索引"}

        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)

        warnings = []
        # 虚链
        for d in index.get("dangling_links", []):
            warnings.append(f"Broken citation: [[{d['text']}]] in {os.path.basename(d.get('source_file',''))}")
        # 冲突
        for d in index.get("duplicates", []):
            warnings.append(f"Duplicate id: {d['id']} in {len(d.get('files',[]))} files")

        output_lines = "\n".join(warnings) if warnings else "检查通过，无问题"

        # 附带问题文件检测
        inspection = self.inspect_files()
        issues = inspection.get("issues", []) if inspection.get("status") == "ok" else []

        return {
            "status": "ok" if not warnings else "error",
            "output": output_lines,
            "errors": "",
            "issues": issues,
        }

    # ========== 内容读取 ==========

    def create_node(self, node_id: str, title: str = None,
                    content: str = "", tags: str = "") -> dict:
        """创建新节点文件

        Args:
            node_id: 节点 id（作为文件名）
            title: 节点标题（默认用 node_id）
            content: 正文内容（默认占位提示）
            tags: 逗号分隔的标签字符串
        """
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}
        if not node_id:
            return {"status": "error", "message": "节点 id 不能为空"}
        # 校验 id 不能含空格和 []{}
        if re.search(r'[\s\[\]{}]', node_id):
            return {"status": "error", "message": "id 不能含空格或 []{}"}

        final_title = (title or node_id).strip()
        file_name = f"{node_id}.md"
        file_path = os.path.join(self.kb_path, file_name)
        if os.path.exists(file_path):
            return {"status": "error", "message": f"文件已存在: {file_name}"}

        # 解析 tags → concepts（无 id 的标签）
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        concepts_yaml = [f'  - id: {node_id}', f'    name: {final_title}', '    weight: 1.0']
        for t in tag_list:
            concepts_yaml.append(f'  - name: {t}')
            concepts_yaml.append('    weight: 0.5')

        body = content.strip() or f"# {final_title}\n\n*新节点，请补充内容。*\n"

        file_content = f"""---
description: ""
concepts:
{chr(10).join(concepts_yaml)}
edges: []
---

{body}
"""

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(file_content)
            return {
                "status": "ok",
                "node_id": node_id,
                "file_path": file_name,
                "message": f"已创建 {file_name}",
            }
        except Exception as e:
            return {"status": "error", "message": f"创建失败: {e}"}

    def get_node_content(self, node_id: str) -> str:
        """读取指定节点的 Markdown 正文（从源文件读，剥 Frontmatter）"""
        if not self.kb_path:
            return ""

        # 从 index.json 查 node 的 file 字段
        index_path = os.path.join(self.kb_path, ".build", "index.json")
        if not os.path.exists(index_path):
            return ""
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)

        node = None
        for n in index.get("nodes", []):
            if n.get("id") == node_id:
                node = n
                break
        if not node:
            return ""

        # 从源文件读，剥 Frontmatter
        from memoria.intelligence.embeddings import read_node_body
        return read_node_body(node, self.kb_path)

    def get_node_raw(self, node_id: str) -> dict:
        """读取节点完整源文件（含 frontmatter）

        用于前端编辑链接时读写文件。
        """
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库"}
        index_path = os.path.join(self.kb_path, ".build", "index.json")
        if not os.path.exists(index_path):
            return {"status": "error", "message": "请先构建索引"}
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
        node = None
        for n in index.get("nodes", []):
            if n.get("id") == node_id:
                node = n
                break
        if not node:
            return {"status": "error", "message": f"未找到节点 {node_id}"}
        file_path = node.get("file", "")
        if not file_path or not os.path.exists(file_path):
            return {"status": "error", "message": "源文件不存在"}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return {"status": "ok", "content": content, "file": file_path}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def save_node_raw(self, node_id: str, content: str) -> dict:
        """保存节点完整源文件（含 frontmatter）

        用于前端编辑链接后写回文件。
        """
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库"}
        index_path = os.path.join(self.kb_path, ".build", "index.json")
        if not os.path.exists(index_path):
            return {"status": "error", "message": "请先构建索引"}
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
        node = None
        for n in index.get("nodes", []):
            if n.get("id") == node_id:
                node = n
                break
        if not node:
            return {"status": "error", "message": f"未找到节点 {node_id}"}
        file_path = node.get("file", "")
        if not file_path:
            return {"status": "error", "message": "文件路径为空"}
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_index(self) -> dict:
        """读取 index.json"""
        if not self.kb_path:
            return {}
        index_path = os.path.join(self.kb_path, ".build", "index.json")
        if os.path.exists(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def get_graph(self) -> dict:
        """读取 graph.json"""
        if not self.kb_path:
            return {}
        graph_path = os.path.join(self.kb_path, ".build", "graph.json")
        if os.path.exists(graph_path):
            with open(graph_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    # ========== 智能层（板块 7，后续实现） ==========

    def ai_search(self, query: str) -> dict:
        """语义搜索"""
        try:
            from memoria.intelligence.search import semantic_search
            results = semantic_search(query, self.kb_path)
            return {"status": "ok", "results": results}
        except ImportError:
            return {"status": "error", "message": "智能层未安装。请 pip install sentence-transformers"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def content_search(self, query: str) -> dict:
        """内容搜索：在节点正文里搜字符串（大小写不敏感）

        返回所有命中节点，按命中次数排序。
        """
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}
        if not query.strip():
            return {"status": "ok", "results": []}

        index_path = os.path.join(self.kb_path, ".build", "index.json")
        if not os.path.exists(index_path):
            return {"status": "error", "message": "请先构建索引"}

        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)

        from memoria.intelligence.embeddings import read_node_body

        q_lower = query.lower()
        results = []
        for node in index.get("nodes", []):
            try:
                content = read_node_body(node, self.kb_path)
            except Exception:
                continue
            if not content:
                continue
            content_lower = content.lower()
            count = content_lower.count(q_lower)
            if count == 0:
                continue
            # 提取首个命中附近的片段作为预览
            idx = content_lower.find(q_lower)
            start = max(0, idx - 30)
            end = min(len(content), idx + len(query) + 30)
            snippet = content[start:end].replace("\n", " ").strip()
            if start > 0:
                snippet = "..." + snippet
            if end < len(content):
                snippet = snippet + "..."

            results.append({
                "id": node.get("id", ""),
                "title": node.get("title", node.get("id", "")),
                "score": float(count),
                "snippet": snippet,
            })

        # 按命中次数降序
        results.sort(key=lambda x: x["score"], reverse=True)
        return {"status": "ok", "results": results}

    def ai_suggest_links(self, node_id: str) -> dict:
        """链接建议"""
        try:
            from memoria.intelligence.linker import suggest_links
            results = suggest_links(node_id, self.kb_path)
            return {"status": "ok", "results": results}
        except ImportError:
            return {"status": "error", "message": "智能层未安装"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def suggest_redirect(self, dangling_id: str) -> dict:
        """为虚链推荐重定向目标

        用字符串相似度（difflib）匹配已有节点的 id/title/tags，
        返回按相似度排序的候选列表。用户可选择重定向或创建新文件。

        Args:
            dangling_id: 虚链的 id（如 [[unknown]] 中的 unknown）

        Returns:
            {
                "status": "ok",
                "dangling_id": "unknown",
                "candidates": [
                    {"id": "ddpg", "title": "Deep DPG", "similarity": 0.85, "reason": "title 相似"},
                    ...
                ]
            }
        """
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}
        if not dangling_id:
            return {"status": "error", "message": "dangling_id 不能为空"}

        index_path = os.path.join(self.kb_path, ".build", "index.json")
        if not os.path.exists(index_path):
            return {"status": "error", "message": "请先构建索引"}

        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)

        from difflib import SequenceMatcher

        def sim(a, b):
            return SequenceMatcher(None, a.lower(), b.lower()).ratio()

        candidates = []
        query = dangling_id.lower()
        seen_ids = set()

        for node in index.get("nodes", []):
            nid = node.get("id", "")
            if not nid or nid in seen_ids:
                continue
            seen_ids.add(nid)

            title = node.get("title", nid)
            tags = node.get("tags", []) or []

            # 计算多维度相似度，取最大值
            best_sim = sim(query, nid.lower())
            reason = "id 相似"

            title_sim = sim(query, title.lower())
            if title_sim > best_sim:
                best_sim = title_sim
                reason = "title 相似"

            for tag in tags:
                tag_sim = sim(query, str(tag).lower())
                if tag_sim > best_sim:
                    best_sim = tag_sim
                    reason = f"tag 相似 ({tag})"

            # 子串匹配加分（如 ddpg 包含 dpg）
            if query in nid.lower() or nid.lower() in query:
                best_sim = max(best_sim, 0.75)
                reason = "id 包含关系"

            if best_sim >= 0.4:
                candidates.append({
                    "id": nid,
                    "title": title,
                    "file": node.get("file", ""),
                    "similarity": round(best_sim, 3),
                    "reason": reason,
                })

        # 去重（按 id）并按相似度降序
        candidates.sort(key=lambda x: -x["similarity"])
        candidates = candidates[:10]  # 最多返回 10 个

        return {
            "status": "ok",
            "dangling_id": dangling_id,
            "candidates": candidates,
        }

    def redirect_dangling(self, dangling_id: str, target_id: str) -> dict:
        """把所有源文件中的 [[dangling_id]] 替换为 [[target_id]]

        用户在重定向推荐对话框中确认后调用。

        Args:
            dangling_id: 虚链 id
            target_id: 已存在的目标 id
        """
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}
        if not dangling_id or not target_id:
            return {"status": "error", "message": "参数不能为空"}
        if dangling_id == target_id:
            return {"status": "error", "message": "源 id 和目标 id 相同"}

        index_path = os.path.join(self.kb_path, ".build", "index.json")
        if not os.path.exists(index_path):
            return {"status": "error", "message": "请先构建索引"}

        # 收集所有引用 dangling_id 的文件
        affected_files = set()
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
        for cite in index.get("citations", []):
            if cite.get("target") == dangling_id:
                # 通过 source id 找到文件
                source_id = cite.get("source", "")
                for node in index.get("nodes", []):
                    if node.get("id") == source_id:
                        affected_files.add(node.get("file", ""))
                        break

        if not affected_files:
            return {"status": "ok", "replaced": 0, "message": "没有文件引用此虚链"}

        # 替换所有 [[dangling_id...]] → [[target_id...|原渲染文本]]
        # 设计哲学：id 是隐式的，渲染文本与关键字绑定。
        # 修改 id 前后用户看到的链接文字必须完全一致。
        #   [[dangling_id]]             → [[target_id|dangling_id]]   （原渲染=dangling_id，补 |dangling_id 保留）
        #   [[dangling_id#anchor]]      → [[target_id#anchor|dangling_id]]
        #   [[dangling_id|text]]        → [[target_id|text]]          （原渲染=text，不变）
        #   [[dangling_id#anchor|text]] → [[target_id#anchor|text]]
        pattern = re.compile(
            r'\[\[' + re.escape(dangling_id) + r'(#[^\]|]*)?(\|([^\]]*))?\]\]'
        )
        replaced_total = 0
        errors = []

        def _preserve_text_repl(m):
            anchor = m.group(1) or ''
            text = m.group(3)  # | 后的 text，可能为 None
            # 保留原渲染文本：有 |text 用 text；否则 [[dangling_id]] 默认渲染 dangling_id
            preserved_text = text if (text is not None and text != '') else dangling_id
            return f'[[{target_id}{anchor}|{preserved_text}]]'

        for file_path in affected_files:
            if not file_path or not os.path.exists(file_path):
                continue
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                new_content, n = pattern.subn(_preserve_text_repl, content)
                if n > 0:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    replaced_total += n
            except Exception as e:
                errors.append(f"{file_path}: {e}")

        return {
            "status": "ok",
            "replaced": replaced_total,
            "files_affected": len(affected_files),
            "errors": errors,
        }

    def delete_dangling(self, dangling_id: str) -> dict:
        """删除虚链：把所有源文件中的 [[dangling_id]] 解除包裹，保留内部 id 文本

        例如 "根据[[ddpg]]配比" → "根据ddpg配比"

        Args:
            dangling_id: 虚链 id
        """
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}
        if not dangling_id:
            return {"status": "error", "message": "dangling_id 不能为空"}

        index_path = os.path.join(self.kb_path, ".build", "index.json")
        if not os.path.exists(index_path):
            return {"status": "error", "message": "请先构建索引"}

        # 收集所有引用 dangling_id 的文件
        affected_files = set()
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
        for cite in index.get("citations", []):
            if cite.get("target") == dangling_id:
                source_id = cite.get("source", "")
                for node in index.get("nodes", []):
                    if node.get("id") == source_id:
                        affected_files.add(node.get("file", ""))
                        break

        if not affected_files:
            return {"status": "ok", "removed": 0, "message": "没有文件引用此虚链"}

        # 把 [[dangling_id]] 和 [[dangling_id#anchor]] 替换为内部 id 文本
        # 保留 id 文本，只去掉 [[ ]] 包裹和 #anchor 部分
        pattern = re.compile(r'\[\[' + re.escape(dangling_id) + r'(#([^\]]+))?\]\]')
        removed_total = 0
        errors = []

        for file_path in affected_files:
            if not file_path or not os.path.exists(file_path):
                continue
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                # 替换为 dangling_id（去掉 [[ ]] 和 #anchor）
                new_content, n = pattern.subn(dangling_id, content)
                if n > 0:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    removed_total += n
            except Exception as e:
                errors.append(f"{file_path}: {e}")

        return {
            "status": "ok",
            "removed": removed_total,
            "files_affected": len(affected_files),
            "errors": errors,
        }

    def suggest_auto_links(self, node_id: str = None) -> dict:
        """自动解析知识点并建议链接

        扫描节点（全部或单个）的关键词和正文，识别三种关系机会：
          - link_existing: 关键词匹配已有节点 id/title → 建议 prerequisite/extend
          - wrap_link:    正文出现已有节点 id/title（但未用 [[id]] 包裹）→ 建议包装为 [[id]] 链接
          - create_node:  正文有候选新知识点（高频术语，但无对应节点）→ 建议创建新节点

        Args:
            node_id: 指定单个节点 id 解析；None 表示全局解析所有节点

        Returns:
            {"status": "ok", "suggestions": [
                {"type": "link_existing",
                 "node_id": "222", "node_title": "测试",
                 "target_id": "ddpg", "target_title": "DDPG",
                 "suggest_as": "prerequisite",  # prerequisite | extend
                 "keyword": "ddpg"},
                {"type": "wrap_link",
                 "node_id": "333", "node_title": "地平线6",
                 "target_id": "ddpg", "target_title": "DDPG",
                 "keyword": "ddpg",
                 "preview": "ddpg 是一个基于强化学习的智能体..."},
                {"type": "create_node",
                 "node_id": "333", "node_title": "地平线6",
                 "candidate_id": "policy-gradient",  # 推断的候选 id
                 "candidate_title": "Policy Gradient",
                 "keyword": "policy-gradient",
                 "frequency": 3,
                 "preview": "..."},
                ...
            ]}
        """
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}

        index_path = os.path.join(self.kb_path, ".build", "index.json")
        if not os.path.exists(index_path):
            return {"status": "error", "message": "请先构建索引"}

        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)

        all_nodes = index.get("nodes", [])
        # 单文件模式：只解析指定节点
        if node_id:
            nodes = [n for n in all_nodes if n.get("id") == node_id]
            if not nodes:
                return {"status": "error", "message": f"节点 {node_id} 不存在"}
        else:
            nodes = all_nodes

        # 建立 id → node 和 title → node 的映射
        id_map = {n["id"]: n for n in all_nodes}
        title_map = {}
        for n in all_nodes:
            if n.get("title"):
                title_map[n["title"].lower()] = n

        # 加载提取的关键词
        extracted_map = {}
        ext_path = os.path.join(self.kb_path, ".build", "embeddings_extracted.json")
        if os.path.exists(ext_path):
            with open(ext_path, "r", encoding="utf-8") as f:
                extracted_map = json.load(f)

        from memoria.intelligence.embeddings import read_node_body

        suggestions = []
        # 全局候选新知识点统计：keyword → list of (node_id, frequency_in_body)
        global_candidates = {}

        for node in nodes:
            nid = node.get("id", "")
            if not nid:
                continue

            already_linked = set()
            for key in ("prerequisite", "extend", "analogy"):
                already_linked.update(node.get(key, []))
            already_linked.add(nid)

            # 关键词（来自 provides/tags/jieba）
            keywords = []
            if nid in extracted_map:
                ext = extracted_map[nid]
                keywords = ext.get("all_keywords", [])

            try:
                body = read_node_body(node, self.kb_path)
            except Exception:
                body = ""

            # === 类型 1: link_existing ===
            # 关键词匹配已有节点 id/title（但未建立关系）
            matched_existing = {}  # target_id → keyword
            for kw in keywords:
                kw_lower = kw.lower().strip()
                if not kw_lower or len(kw_lower) < 2:
                    continue
                if kw_lower in id_map and kw_lower not in already_linked:
                    matched_existing[kw_lower] = kw
                elif kw_lower in title_map:
                    target = title_map[kw_lower]
                    if target["id"] not in already_linked:
                        matched_existing[target["id"]] = kw

            for target_id, kw in matched_existing.items():
                target_node = id_map.get(target_id, {})
                target_ref_count = sum(
                    1 for n in all_nodes if target_id in n.get("prerequisite", [])
                )
                suggest_as = "prerequisite" if target_ref_count > 0 else "extend"
                suggestions.append({
                    "type": "link_existing",
                    "node_id": nid,
                    "node_title": node.get("title", nid),
                    "target_id": target_id,
                    "target_title": target_node.get("title", target_id),
                    "suggest_as": suggest_as,
                    "keyword": kw,
                })

            # === 类型 2: wrap_link ===
            # 正文出现已有节点 id/title（未用 [[]] 包裹）
            # 先把已有的 [[id]] 部分屏蔽（用占位符替换避免重复匹配）
            body_masked = body
            existing_citations = re.findall(r'\[\[([^\]]+)\]\]', body)
            for i, c in enumerate(existing_citations):
                body_masked = body_masked.replace(f"[[{c}]]", f"\x00CITE{i}\x00", 1)

            body_lower = body_masked.lower()
            wrapped_targets = set()
            for other_id, other_node in id_map.items():
                if other_id == nid or other_id in already_linked:
                    continue
                # 检查 id 是否作为独立词出现在正文中（前后非字母数字）
                pattern_id = re.compile(r'(?<![a-zA-Z0-9_])' + re.escape(other_id) + r'(?![a-zA-Z0-9_])', re.IGNORECASE)
                if pattern_id.search(body_masked):
                    # 找到一处出现
                    m = pattern_id.search(body_masked)
                    preview_start = max(0, m.start() - 20)
                    preview_end = min(len(body_masked), m.end() + 30)
                    preview = body_masked[preview_start:preview_end].replace("\n", " ").strip()
                    if preview_start > 0:
                        preview = "..." + preview
                    if preview_end < len(body_masked):
                        preview = preview + "..."

                    suggestions.append({
                        "type": "wrap_link",
                        "node_id": nid,
                        "node_title": node.get("title", nid),
                        "target_id": other_id,
                        "target_title": other_node.get("title", other_id),
                        "keyword": other_id,
                        "preview": preview,
                    })
                    wrapped_targets.add(other_id)

            # 检查 title 是否在正文中
            for other_title, other_node in title_map.items():
                other_id = other_node["id"]
                if other_id == nid or other_id in already_linked or other_id in wrapped_targets:
                    continue
                if len(other_title) < 3:
                    continue
                pattern_title = re.compile(re.escape(other_title), re.IGNORECASE)
                if pattern_title.search(body_masked):
                    m = pattern_title.search(body_masked)
                    preview_start = max(0, m.start() - 20)
                    preview_end = min(len(body_masked), m.end() + 30)
                    preview = body_masked[preview_start:preview_end].replace("\n", " ").strip()
                    if preview_start > 0:
                        preview = "..." + preview
                    if preview_end < len(body_masked):
                        preview = preview + "..."

                    suggestions.append({
                        "type": "wrap_link",
                        "node_id": nid,
                        "node_title": node.get("title", nid),
                        "target_id": other_id,
                        "target_title": other_node.get("title", other_id),
                        "keyword": other_title,
                        "preview": preview,
                    })

            # === 类型 3: create_node ===
            # 收集正文中可能的候选新知识点（jieba 术语 + 已用 [[id]] 但不存在的 id）
            # 已用 [[id]] 但不存在的（虚链）→ 强候选
            for c in existing_citations:
                cid = c.split("#")[0]
                if cid and cid not in id_map and cid != nid:
                    # 在正文中找位置
                    pattern_c = re.compile(r'\[\[' + re.escape(c) + r'\]\]')
                    m = pattern_c.search(body)
                    preview = ""
                    if m:
                        ps = max(0, m.start() - 20)
                        pe = min(len(body), m.end() + 30)
                        preview = body[ps:pe].replace("\n", " ").strip()
                        if ps > 0:
                            preview = "..." + preview
                        if pe < len(body):
                            preview = preview + "..."

                    suggestions.append({
                        "type": "create_node",
                        "node_id": nid,
                        "node_title": node.get("title", nid),
                        "candidate_id": cid,
                        "candidate_title": cid.replace("-", " ").title(),
                        "keyword": cid,
                        "frequency": 1,
                        "preview": preview,
                        "reason": "正文中已用 [[id]] 引用但节点不存在",
                    })

            # jieba 高频术语但无对应节点（全局聚合后判断）
            jieba_terms = []
            if nid in extracted_map:
                jieba_terms = extracted_map[nid].get("jieba_terms", [])
            for term in jieba_terms:
                term_lower = term.lower().strip()
                if not term_lower or len(term_lower) < 3:
                    continue
                # 已是已有节点 id/title，跳过
                if term_lower in id_map or term_lower in title_map:
                    continue
                # 已通过 [[id]] 引用
                if term_lower in [c.split("#")[0].lower() for c in existing_citations]:
                    continue
                # 在正文中出现频率
                count = len(re.findall(r'(?<![a-zA-Z0-9_])' + re.escape(term) + r'(?![a-zA-Z0-9_])', body_masked))
                if count == 0:
                    continue
                # 聚合到全局
                if term_lower not in global_candidates:
                    global_candidates[term_lower] = {
                        "term": term,
                        "total_count": 0,
                        "appearances": [],  # (node_id, preview, count)
                    }
                # 找一处出现位置
                m = re.search(r'(?<![a-zA-Z0-9_])' + re.escape(term) + r'(?![a-zA-Z0-9_])', body_masked)
                preview = ""
                if m:
                    ps = max(0, m.start() - 20)
                    pe = min(len(body_masked), m.end() + 30)
                    preview = body_masked[ps:pe].replace("\n", " ").strip()
                    if ps > 0:
                        preview = "..." + preview
                    if pe < len(body_masked):
                        preview = preview + "..."

                global_candidates[term_lower]["total_count"] += count
                global_candidates[term_lower]["appearances"].append({
                    "node_id": nid,
                    "node_title": node.get("title", nid),
                    "preview": preview,
                    "count": count,
                })

        # 全局候选新知识点：单文件模式 frequency>=1，全局模式 >=2
        min_freq = 1 if node_id else 2
        for term_lower, info in global_candidates.items():
            if info["total_count"] < min_freq:
                continue
            # 取第一次出现作为预览
            first = info["appearances"][0]
            # 候选 id：用原术语（保留大小写），转小写连字符
            candidate_id = term_lower.replace(" ", "-")
            suggestions.append({
                "type": "create_node",
                "node_id": first["node_id"],  # 第一次出现的节点（用于定位）
                "node_title": first["node_title"],
                "candidate_id": candidate_id,
                "candidate_title": info["term"],
                "keyword": info["term"],
                "frequency": info["total_count"],
                "preview": first["preview"],
                "reason": f"高频术语（共出现 {info['total_count']} 次）",
                "appearances": info["appearances"],
            })

        return {"status": "ok", "suggestions": suggestions, "node_id": node_id}

    def apply_auto_links(self, links: list) -> dict:
        """应用自动链接建议到文件

        Args:
            links: 每项 type 可为：
                - link_existing: {"type": "link_existing", "node_id": "222", "target_id": "ddpg", "suggest_as": "prerequisite"}
                - wrap_link:    {"type": "wrap_link", "node_id": "333", "target_id": "ddpg", "keyword": "ddpg"}
                - create_node:  {"type": "create_node", "candidate_id": "policy-gradient", "candidate_title": "Policy Gradient", "appearances": [{"node_id": "333", "keyword": "policy-gradient"}, ...]}
                                 (创建新文件 + 在所有引用处包装 [[id]])
        """
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}

        import re
        applied = 0
        errors = []

        # 读 index 一次（多次复用）
        index_path = os.path.join(self.kb_path, ".build", "index.json")
        if not os.path.exists(index_path):
            return {"status": "error", "message": "请先构建索引"}
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)

        def find_node_file(node_id):
            for n in index.get("nodes", []):
                if n["id"] == node_id:
                    return n
            return None

        def read_file(file_path):
            full_path = file_path if os.path.isabs(file_path) else os.path.join(self.kb_path, file_path)
            if not os.path.exists(full_path):
                return None
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()

        def write_file(file_path, content):
            full_path = file_path if os.path.isabs(file_path) else os.path.join(self.kb_path, file_path)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

        def update_frontmatter_relation(content, rel_type, target_id):
            """在 Frontmatter 中添加关系"""
            lines = content.split("\n")
            if not lines or lines[0].strip() != "---":
                return content, False
            fm_end = -1
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    fm_end = i
                    break
            if fm_end == -1:
                return content, False
            fm_text = "\n".join(lines[1:fm_end])
            pattern = re.compile(rf"^({rel_type}):\s*(.*)$", re.MULTILINE)
            m = pattern.search(fm_text)
            if m:
                current_val = m.group(2).strip()
                if current_val.startswith("["):
                    items = [s.strip().strip('"').strip("'") for s in current_val[1:-1].split(",") if s.strip()]
                    if target_id in items:
                        return content, True  # 已存在
                    items.append(target_id)
                    new_val = "[" + ", ".join(items) + "]"
                else:
                    if current_val == target_id:
                        return content, True
                    new_val = f"[{current_val}, {target_id}]"
                new_fm = pattern.sub(f"{rel_type}: {new_val}", fm_text)
            else:
                new_fm = fm_text.rstrip() + f"\n{rel_type}: [{target_id}]"
            new_lines = lines[:1] + new_fm.split("\n") + lines[fm_end:]
            return "\n".join(new_lines), True

        def wrap_keyword_with_link(content, keyword, target_id):
            """把正文里出现的 keyword 包装为 [[target_id|keyword]]（保留原文本，仅第一次出现）

            使用 [[id|text]] 语法，渲染时显示原 keyword 文本而非 id，
            避免"番茄炒蛋"被替换为"tomato-egg"的问题。
            """
            lines = content.split("\n")
            if not lines or lines[0].strip() != "---":
                return content, False
            fm_end = -1
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    fm_end = i
                    break
            if fm_end == -1:
                return content, False

            body_lines = lines[fm_end + 1:]
            body = "\n".join(body_lines)

            # 屏蔽已有的 [[...]]
            masked = body
            existing = re.findall(r'\[\[[^\]]+\]\]', body)
            for i, c in enumerate(existing):
                masked = masked.replace(c, f"\x00CITE{i}\x00", 1)

            # 替换第一次出现：保留 keyword 文本，用 [[id|keyword]] 语法
            pattern = re.compile(r'(?<![a-zA-Z0-9_\[])' + re.escape(keyword) + r'(?![a-zA-Z0-9_\]])')
            m = pattern.search(masked)
            if not m:
                return content, False
            # 若 keyword 与 target_id 相同，用简单 [[id]] 语法即可
            if keyword == target_id:
                replacement = f"[[{target_id}]]"
            else:
                replacement = f"[[{target_id}|{keyword}]]"
            new_masked = masked[:m.start()] + replacement + masked[m.end():]
            # 还原其他 [[...]]
            for i, c in enumerate(existing):
                new_masked = new_masked.replace(f"\x00CITE{i}\x00", c, 1)

            new_body = new_masked
            new_lines = lines[:fm_end + 1] + new_body.split("\n")
            return "\n".join(new_lines), True

        # === 处理每条建议 ===
        for link in links:
            link_type = link.get("type")

            if link_type == "link_existing":
                node_id = link.get("node_id")
                target_id = link.get("target_id")
                rel_type = link.get("suggest_as", "prerequisite")
                node = find_node_file(node_id)
                if not node:
                    errors.append(f"节点 {node_id} 不存在")
                    continue
                file_path = node.get("file", "")
                content = read_file(file_path)
                if content is None:
                    errors.append(f"文件不存在: {file_path}")
                    continue
                new_content, ok = update_frontmatter_relation(content, rel_type, target_id)
                if ok:
                    write_file(file_path, new_content)
                    applied += 1

            elif link_type == "wrap_link":
                node_id = link.get("node_id")
                target_id = link.get("target_id")
                keyword = link.get("keyword") or target_id
                node = find_node_file(node_id)
                if not node:
                    errors.append(f"节点 {node_id} 不存在")
                    continue
                file_path = node.get("file", "")
                content = read_file(file_path)
                if content is None:
                    errors.append(f"文件不存在: {file_path}")
                    continue
                new_content, ok = wrap_keyword_with_link(content, keyword, target_id)
                if ok:
                    write_file(file_path, new_content)
                    applied += 1
                else:
                    errors.append(f"{file_path}: 未找到关键词 '{keyword}'")

            elif link_type == "create_node":
                # 虚链悬空设计：不创建文件，只在正文中插入 [[candidate_id]] 虚链
                # 用户日后补充对应文件时，重建索引会自动让虚链变实链
                # 若用户希望立即创建文件，应通过"新建节点"对话框手动操作
                candidate_id = link.get("candidate_id")
                if not candidate_id:
                    errors.append("create_node 缺少 candidate_id")
                    continue

                # 在所有引用处插入 [[candidate_id]] 虚链（仅当正文有候选关键词时）
                appearances = link.get("appearances") or [{
                    "node_id": link.get("node_id"),
                    "keyword": link.get("keyword"),
                }]
                for app in appearances:
                    node_id = app.get("node_id")
                    keyword = app.get("keyword") or candidate_id
                    node = find_node_file(node_id)
                    if not node:
                        continue
                    file_path = node.get("file", "")
                    content = read_file(file_path)
                    if content is None:
                        continue
                    new_content, ok = wrap_keyword_with_link(content, keyword, candidate_id)
                    if ok:
                        write_file(file_path, new_content)
                        applied += 1
                    else:
                        errors.append(f"{file_path}: 未找到关键词 '{keyword}'")

        return {"status": "ok", "applied": applied, "errors": errors}

    def ai_graph_analysis(self) -> dict:
        """图谱分析"""
        try:
            from memoria.intelligence.analyzer import analyze
            results = analyze(self.kb_path)
            return {"status": "ok", "results": results}
        except ImportError:
            return {"status": "error", "message": "智能层未安装"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ========== 知识点审核（板块 7 扩展） ==========

    def get_extracted_keywords(self) -> dict:
        """获取上次构建时提取的知识点（供审核 UI 使用）"""
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}

        ext_path = os.path.join(self.kb_path, ".build", "embeddings_extracted.json")
        if not os.path.exists(ext_path):
            return {"status": "error", "message": "请先构建索引"}

        try:
            with open(ext_path, "r", encoding="utf-8") as f:
                extracted = json.load(f)
        except json.JSONDecodeError:
            return {"status": "error", "message": "提取结果文件损坏，请重新构建索引"}

        # 加载已有审核配置
        config_path = os.path.join(self.kb_path, ".build", "embeddings_config.json")
        user_config = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)

        return {
            "status": "ok",
            "extracted": extracted,
            "user_config": user_config,
        }

    def reparse_keywords(self, node_id: str = None) -> dict:
        """增量重新解析关键字

        - 不覆盖用户已添加/修改的关键字，只增量补充新提取的
        - 若指定 node_id，只解析该节点；否则解析全部
        - 写回 .build/embeddings_extracted.json

        Args:
            node_id: 可选，指定节点 id
        """
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}

        try:
            from memoria.intelligence.extractor import extract_from_node

            ext_path = os.path.join(self.kb_path, ".build", "embeddings_extracted.json")
            # 加载现有数据（保留用户修改）
            existing = {}
            if os.path.exists(ext_path):
                with open(ext_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)

            # 加载索引获取节点列表
            index_path = os.path.join(self.kb_path, ".build", "index.json")
            if not os.path.exists(index_path):
                return {"status": "error", "message": "请先构建索引"}
            with open(index_path, "r", encoding="utf-8") as f:
                index = json.load(f)

            # 筛选要解析的节点
            target_nodes = index.get("nodes", [])
            if node_id:
                target_nodes = [n for n in target_nodes if n.get("id") == node_id]
                if not target_nodes:
                    return {"status": "error", "message": f"未找到节点: {node_id}"}

            # 增量提取
            added_count = 0
            for node in target_nodes:
                nid = node.get("id", "")
                file_path = node.get("file", "")
                if not file_path or not os.path.exists(file_path):
                    continue

                # 读取文件内容并分离 frontmatter
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        raw = f.read()
                    # 去除 frontmatter
                    content = raw
                    if raw.startswith("---"):
                        end = raw.find("\n---", 3)
                        if end != -1:
                            content = raw[end + 4:]

                    # 用 extractor 提取
                    new_data = extract_from_node(node, content)
                except Exception as e:
                    continue

                # 增量合并：保留用户修改，只补充新关键字
                old_data = existing.get(nid, {})
                user_provides = old_data.get("provides", [])
                user_tags = old_data.get("tags", [])
                new_provides = new_data.get("provides", [])
                new_tags = new_data.get("tags", [])
                new_jieba = new_data.get("jieba_terms", [])

                merged_provides = list(user_provides)
                for p in new_provides:
                    if p not in merged_provides:
                        merged_provides.append(p)
                        added_count += 1

                merged_tags = list(user_tags)
                for t in new_tags:
                    if t not in merged_tags:
                        merged_tags.append(t)
                        added_count += 1

                all_keywords = list(merged_provides) + list(merged_tags) + list(new_jieba)
                seen = set()
                deduped = []
                for w in all_keywords:
                    if w not in seen:
                        seen.add(w)
                        deduped.append(w)
                all_keywords = deduped

                existing[nid] = {
                    "provides": merged_provides,
                    "tags": merged_tags,
                    "jieba_terms": new_jieba,
                    "all_keywords": all_keywords,
                }

            # 写回
            with open(ext_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)

            # 加载 user_config 返回
            config_path = os.path.join(self.kb_path, ".build", "embeddings_config.json")
            user_config = {}
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    user_config = json.load(f)

            return {
                "status": "ok",
                "extracted": existing,
                "user_config": user_config,
                "added": added_count,
                "node_id": node_id,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def save_keyword_review(self, node_id: str, user_added: list,
                            user_removed: list, user_edited: dict) -> dict:
        """保存用户对某节点关键词的审核结果"""
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}

        config_path = os.path.join(self.kb_path, ".build", "embeddings_config.json")

        # 加载已有配置
        user_config = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)

        # 更新该节点的配置
        user_config[node_id] = {
            "user_added": user_added,
            "user_removed": user_removed,
            "user_edited": user_edited,
        }

        # 保存
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(user_config, f, ensure_ascii=False, indent=2)

        return {"status": "ok"}

    def rebuild_embeddings(self) -> dict:
        """重新构建向量索引（应用审核后）"""
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}

        try:
            from memoria.intelligence.embeddings import build
            result = build(self.kb_path)
            return result
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ========== 高级设置 ==========

    def get_search_config(self) -> dict:
        """读取搜索配置（含相似度阈值、主题色）"""
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}

        config_path = os.path.join(self.kb_path, ".build", "search_config.json")
        config = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        return {
            "status": "ok",
            "config": {
                "similarity_threshold": config.get("similarity_threshold", 0.2),
                "theme_color": config.get("theme_color", "#007acc"),
            },
        }

    def save_search_config(self, similarity_threshold: float,
                           theme_color: str = "#007acc") -> dict:
        """保存搜索配置（含主题色）"""
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}

        # 校验阈值范围
        try:
            threshold = float(similarity_threshold)
            if not 0.0 <= threshold <= 1.0:
                return {"status": "error", "message": "阈值必须在 0.0~1.0 之间"}
        except (TypeError, ValueError):
            return {"status": "error", "message": "阈值必须是数字"}

        # 校验主题色格式
        if not isinstance(theme_color, str) or not theme_color.startswith("#"):
            theme_color = "#007acc"

        config_path = os.path.join(self.kb_path, ".build", "search_config.json")

        config = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        config["similarity_threshold"] = threshold
        config["theme_color"] = theme_color

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        return {"status": "ok", "threshold": threshold, "theme_color": theme_color}

    # ========== 问题文件检测与自动修复 ==========

    def inspect_files(self) -> dict:
        """检测知识库中的问题文件

        检测项：
        - no_frontmatter: 无 Frontmatter（不会产生节点）
        - unclosed_frontmatter: Frontmatter 未闭合
        - missing_id: 缺少 id 字段
        - missing_title: 缺少 title 字段
        - duplicate_id: id 重复
        - invalid_id: id 含非法字符（非小写英文+连字符）
        """
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}

        import re

        issues = []
        id_to_file = {}

        for root, dirs, files in os.walk(self.kb_path):
            # 排除 .build 目录
            if ".build" in dirs:
                dirs.remove(".build")
            for fname in sorted(files):
                if not fname.endswith(".md"):
                    continue
                fpath = os.path.join(root, fname)
                relpath = os.path.relpath(fpath, self.kb_path)

                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                except Exception:
                    continue

                lines = content.split("\n")
                stem = os.path.splitext(fname)[0]

                # 1. 无 Frontmatter
                if not lines or lines[0].strip() != "---":
                    # 推断 id 和 title
                    title = stem
                    for line in lines:
                        stripped = line.strip()
                        if stripped.startswith("# "):
                            title = stripped[2:].strip()
                            break

                    issues.append({
                        "file": fpath,
                        "relpath": relpath,
                        "type": "no_frontmatter",
                        "message": "文件没有 Frontmatter，不会被识别为节点",
                        "suggestion_id": stem,
                        "suggestion_title": title,
                        "fixable": True,
                    })
                    continue

                # 找 Frontmatter 结束
                fm_end = -1
                for i in range(1, len(lines)):
                    if lines[i].strip() == "---":
                        fm_end = i
                        break

                if fm_end == -1:
                    issues.append({
                        "file": fpath,
                        "relpath": relpath,
                        "type": "unclosed_frontmatter",
                        "message": "Frontmatter 未闭合（缺少结尾的 ---）",
                        "suggestion_id": stem,
                        "suggestion_title": stem,
                        "fixable": False,
                    })
                    continue

                # 解析 Frontmatter
                fm_text = "\n".join(lines[1:fm_end])

                id_match = re.search(r"^id:\s*(.+)$", fm_text, re.MULTILINE)
                doc_id = id_match.group(1).strip() if id_match else ""

                title_match = re.search(r"^title:\s*(.+)$", fm_text, re.MULTILINE)
                doc_title = title_match.group(1).strip() if title_match else ""

                # 2. 缺 id
                if not doc_id:
                    issues.append({
                        "file": fpath,
                        "relpath": relpath,
                        "type": "missing_id",
                        "message": "Frontmatter 缺少 id 字段",
                        "suggestion_id": stem,
                        "suggestion_title": doc_title or stem,
                        "fixable": True,
                    })

                # 3. 缺 title
                if not doc_title:
                    issues.append({
                        "file": fpath,
                        "relpath": relpath,
                        "type": "missing_title",
                        "message": "Frontmatter 缺少 title 字段",
                        "suggestion_id": doc_id or stem,
                        "suggestion_title": stem,
                        "fixable": True,
                    })

                # 4. id 重复
                if doc_id:
                    if doc_id in id_to_file:
                        issues.append({
                            "file": fpath,
                            "relpath": relpath,
                            "type": "duplicate_id",
                            "message": f'id "{doc_id}" 已在 {id_to_file[doc_id]} 中定义',
                            "suggestion_id": "",
                            "suggestion_title": "",
                            "fixable": False,
                        })
                    else:
                        id_to_file[doc_id] = relpath

                # 5. id 格式问题（含中文/空格/大写）
                if doc_id and not re.match(r"^[a-z0-9][a-z0-9\-]*$", doc_id):
                    issues.append({
                        "file": fpath,
                        "relpath": relpath,
                        "type": "invalid_id",
                        "message": f'id "{doc_id}" 含非法字符（建议用小写英文+连字符）',
                        "suggestion_id": "",
                        "suggestion_title": "",
                        "fixable": False,
                    })

        return {"status": "ok", "issues": issues}

    def auto_fix_file(self, file_path: str, custom_id: str = None,
                      custom_title: str = None) -> dict:
        """自动修复文件：插入推断的 Frontmatter

        从文件名推断 id，从正文第一个 # 标题推断 title。
        如果文件已有 Frontmatter 但缺字段，则补全缺失字段。
        可通过 custom_id / custom_title 覆盖推断值。
        """
        if not os.path.exists(file_path):
            return {"status": "error", "message": f"文件不存在: {file_path}"}

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return {"status": "error", "message": f"读取失败: {e}"}

        lines = content.split("\n")
        fname = os.path.basename(file_path)
        stem = os.path.splitext(fname)[0]

        # 推断 title：从正文第一个 # 标题
        inferred_title = stem
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# "):
                inferred_title = stripped[2:].strip()
                break

        # 用户自定义值优先，否则用推断值
        final_id = (custom_id or stem).strip()
        final_title = (custom_title or inferred_title).strip()

        # 情况 1：无 Frontmatter → 在文件头插入
        if not lines or lines[0].strip() != "---":
            frontmatter = (
                "---\n"
                f"id: {final_id}\n"
                f"title: {final_title}\n"
                "provides:\n"
                f"  - id: {final_id}\n"
                f"    title: {final_title}\n"
                "prerequisite: []\n"
                "extend: []\n"
                "tags: []\n"
                "---\n\n"
            )
            new_content = frontmatter + content
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            return {"status": "ok", "action": "inserted", "id": final_id, "title": final_title}

        # 情况 2：有 Frontmatter 但缺字段 → 补全
        import re

        fm_end = -1
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                fm_end = i
                break

        if fm_end == -1:
            return {"status": "error", "message": "Frontmatter 未闭合，无法自动修复"}

        fm_text = "\n".join(lines[1:fm_end])
        has_id = bool(re.search(r"^id:\s*\S", fm_text, re.MULTILINE))
        has_title = bool(re.search(r"^title:\s*\S", fm_text, re.MULTILINE))

        # 构造要插入的行（使用 final_id / final_title）
        insert_lines = []
        if not has_id:
            insert_lines.append(f"id: {final_id}")
        if not has_title:
            insert_lines.append(f"title: {final_title}")

        if not insert_lines:
            return {"status": "ok", "action": "no_change", "id": "", "title": ""}

        # 在 Frontmatter 最后一行后插入
        new_lines = lines[:fm_end] + insert_lines + lines[fm_end:]
        new_content = "\n".join(new_lines)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return {
            "status": "ok",
            "action": "patched",
            "id": final_id if not has_id else "",
            "title": final_title if not has_title else "",
        }

    # ========== 统一搜索内核（阶段2） ==========

    def search(self, query: str, scope: str = "all", limit: int = 10) -> dict:
        """统一搜索内核

        聚合向量相似度 + jieba 分词 + 模糊匹配，返回知识点级结果。

        Args:
            query: 搜索查询
            scope: "all" | "concepts" | "files"
            limit: 返回数量上限
        """
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}
        if not query.strip():
            return {"status": "ok", "results": []}

        try:
            from memoria.intelligence.search_kernel import unified_search
            results = unified_search(query, self.kb_path, scope=scope, limit=limit)
            return {"status": "ok", "results": results}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ========== 配置窗口 API（阶段4） ==========

    def get_all_files(self) -> dict:
        """获取知识库中所有文件列表（用于配置窗口文件树）"""
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}

        index_path = os.path.join(self.kb_path, ".build", "index.json")
        if not os.path.exists(index_path):
            return {"status": "error", "message": "请先构建索引"}

        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)

        files = []
        for fdata in index.get("files", []):
            fpath = fdata["file"]
            files.append({
                "file": fpath,
                "relpath": os.path.relpath(fpath, self.kb_path),
                "description": fdata.get("description", ""),
                "concept_count": len([c for c in fdata.get("concepts", []) if c.get("id")]),
                "edge_count": len(fdata.get("edges", [])),
            })
        return {"status": "ok", "files": files}

    def get_file_config(self, file_path: str) -> dict:
        """获取指定文件的 concepts 和 edges 配置

        返回的 concepts 每个带 `line` 字段（正文行号，0 表示未匹配到标题），
        用于前端按"知识点区域"划分链接归属。
        """
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}

        from memoria.builder import split_frontmatter, migrate_old_frontmatter, HEADING_RE

        full_path = file_path if os.path.isabs(file_path) else os.path.join(self.kb_path, file_path)
        if not os.path.exists(full_path):
            return {"status": "error", "message": f"文件不存在: {file_path}"}

        with open(full_path, "r", encoding="utf-8") as f:
            raw = f.read()

        fm, body = split_frontmatter(raw)
        fm = migrate_old_frontmatter(fm)

        # 收集正文 [[文本]] 引用（用于"链接管理"面板）
        from memoria.builder import extract_citations
        citations = extract_citations(body)

        # 规范化 concepts（保证 tags 字段存在）
        norm_concepts = []
        for c in (fm.get("concepts") or []):
            if isinstance(c, dict):
                cid = c.get("id", "")
                if cid is not None and cid != "":
                    cid = str(cid)
                raw_tags = c.get("tags", [])
                if isinstance(raw_tags, str):
                    raw_tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
                tags = [str(t) for t in raw_tags] if raw_tags else []
                norm_concepts.append({
                    "id": cid,
                    "name": str(c.get("name", c.get("id", ""))),
                    "weight": c.get("weight", 0.5),
                    "tags": tags,
                })
            elif isinstance(c, str):
                norm_concepts.append({"id": "", "name": c, "weight": 0.5, "tags": []})

        # 规范化 edges
        norm_edges = []
        for e in (fm.get("edges") or []):
            if isinstance(e, dict):
                edge = {
                    "type": e.get("type", "reference"),
                    "targets": [str(t) for t in (e.get("targets") or [])],
                }
                if "text" in e:
                    edge["text"] = str(e["text"])
                norm_edges.append(edge)

        # 计算每个 concept 在正文中的行号（通过 name 匹配标题）和 heading 深度
        # 用于前端按"知识点区域"划分链接归属，及树形嵌套结构
        body_lines = body.split("\n")
        heading_map = {}  # (line, depth, title)
        for i, ln in enumerate(body_lines, 1):
            m = HEADING_RE.match(ln)
            if m:
                depth = len(m.group(1))  # #=1, ##=2, ###=3
                title = m.group(2).strip()
                clean = re.sub(r'\[\[([^\]]+)\]\]', '', title).strip()
                heading_map[i] = (depth, clean)

        for c in norm_concepts:
            c["line"] = 0
            c["depth"] = 0
            cname = c.get("name", "").strip()
            if cname:
                for ln, (dep, title) in heading_map.items():
                    if title == cname:
                        c["line"] = ln
                        c["depth"] = dep
                        break

        return {
            "status": "ok",
            "file": full_path,
            "description": fm.get("description", ""),
            "concepts": norm_concepts,
            "edges": norm_edges,
            "links": citations,  # 正文所有 [[]] 链接（含 line 字段）
            "raw": raw,
        }

    def save_file_config(self, file_path: str, description: str,
                         concepts: list, edges: list) -> dict:
        """保存文件的 concepts 和 edges 配置

        重写文件的 frontmatter，保留正文不变。
        """
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}

        full_path = file_path if os.path.isabs(file_path) else os.path.join(self.kb_path, file_path)
        if not os.path.exists(full_path):
            return {"status": "error", "message": f"文件不存在: {file_path}"}

        from memoria.builder import split_frontmatter
        import yaml as _yaml

        with open(full_path, "r", encoding="utf-8") as f:
            raw = f.read()

        _, body = split_frontmatter(raw)

        # 构造新 frontmatter
        new_fm = {
            "description": description or "",
            "concepts": concepts or [],
            "edges": edges or [],
        }
        fm_yaml = _yaml.dump(new_fm, allow_unicode=True, default_flow_style=False, sort_keys=False)

        new_content = f"---\n{fm_yaml}---\n\n{body}"

        try:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ========== 链接 ID 修改联动（阶段6） ==========

    def replace_link_id(self, old_id: str, new_id: str) -> dict:
        """修改知识点 id 并联动所有引用

        - 修改 frontmatter 中 concepts 的 id
        - 修改正文 [[old_id|text]] → [[new_id|text]]（保留显示文本）
        - 修改 edges 中 targets 的 old_id → new_id

        Returns:
            {"status": "ok", "modified_files": [...]}
        """
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}
        if not old_id or not new_id:
            return {"status": "error", "message": "old_id 和 new_id 不能为空"}
        if re.search(r'[\s\[\]{}|]', new_id):
            return {"status": "error", "message": "new_id 含非法字符"}

        from memoria.builder import split_frontmatter, migrate_old_frontmatter
        import yaml as _yaml

        modified_files = []
        md_files = self._collect_md_files()

        for fpath in md_files:
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    raw = f.read()
            except Exception:
                continue

            fm, body = split_frontmatter(raw)
            fm = migrate_old_frontmatter(fm)

            changed = False

            # 1. 修改 concepts 中的 id
            for c in fm.get("concepts", []):
                if c.get("id") == old_id:
                    c["id"] = new_id
                    changed = True

            # 2. 修改 edges 中 targets 的 old_id
            for e in fm.get("edges", []):
                if old_id in (e.get("targets") or []):
                    e["targets"] = [new_id if t == old_id else t for t in e["targets"]]
                    changed = True

            # 3. 修改正文 [[old_id]] 和 [[old_id|text]] → [[new_id]] 和 [[new_id|text]]
            # 使用 replaceLinkIdPreservingText 逻辑：保留显示文本
            def _replace_link(m):
                nonlocal changed
                inner = m.group(1)
                if "|" in inner:
                    link_id, display = inner.split("|", 1)
                else:
                    link_id, display = inner, ""
                if link_id == old_id:
                    changed = True
                    if display:
                        return f"[[{new_id}|{display}]]"
                    return f"[[{new_id}]]"
                return m.group(0)

            new_body = re.sub(r'\[\[([^\]]+)\]\]', _replace_link, body)

            if not changed:
                continue

            # 重写文件
            fm_yaml = _yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
            new_content = f"---\n{fm_yaml}---\n\n{new_body}"

            with open(fpath, "w", encoding="utf-8") as f:
                f.write(new_content)
            modified_files.append(fpath)

        return {
            "status": "ok",
            "modified_files": modified_files,
            "old_id": old_id,
            "new_id": new_id,
        }

    def delete_concept(self, concept_id: str) -> dict:
        """删除知识点（从 frontmatter 移除，正文引用变虚链）

        Returns:
            {"status": "ok", "modified_files": [...]}
        """
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}

        from memoria.builder import split_frontmatter, migrate_old_frontmatter
        import yaml as _yaml

        modified_files = []
        md_files = self._collect_md_files()

        for fpath in md_files:
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    raw = f.read()
            except Exception:
                continue

            fm, body = split_frontmatter(raw)
            fm = migrate_old_frontmatter(fm)

            changed = False

            # 1. 从 concepts 中移除
            old_concepts = fm.get("concepts", [])
            new_concepts = [c for c in old_concepts if c.get("id") != concept_id]
            if len(new_concepts) != len(old_concepts):
                fm["concepts"] = new_concepts
                changed = True

            # 2. 从 edges targets 中移除
            for e in fm.get("edges", []):
                targets = e.get("targets") or []
                if concept_id in targets:
                    e["targets"] = [t for t in targets if t != concept_id]
                    changed = True
            # 移除空 targets 的边
            fm["edges"] = [e for e in fm.get("edges", []) if e.get("targets")]

            if not changed:
                continue

            fm_yaml = _yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
            new_content = f"---\n{fm_yaml}---\n\n{body}"

            with open(fpath, "w", encoding="utf-8") as f:
                f.write(new_content)
            modified_files.append(fpath)

        return {
            "status": "ok",
            "modified_files": modified_files,
            "concept_id": concept_id,
        }

    def extract_concept_suggestions(self, file_path: str) -> dict:
        """自动解析文件中可能的知识点候选

        返回：
        - candidates: [{text, line, exists: bool, matched_id: str}]
          其中 exists=true 表示已与现有知识点匹配
        - edge_suggestions: [{text, line, candidate_targets: [id]}]
          文本中可能可作为边的 [[链接]] 文本

        触发时机：用户在配置窗口点击"自动解析知识点"按钮
        """
        if not self.kb_path:
            return {"status": "error", "message": "未选择知识库目录"}

        full_path = file_path if os.path.isabs(file_path) else os.path.join(self.kb_path, file_path)
        if not os.path.exists(full_path):
            return {"status": "error", "message": f"文件不存在: {file_path}"}

        from memoria.builder import split_frontmatter, extract_citations, HEADING_RE

        # 延迟导入 jieba（首次调用较慢）
        try:
            import jieba
            import jieba.analyse
        except ImportError:
            jieba = None

        with open(full_path, "r", encoding="utf-8") as f:
            raw = f.read()

        _, body = split_frontmatter(raw)

        # 加载全局 concepts 索引（用于判断是否存在）
        index = None
        index_path = os.path.join(self.kb_path, ".build", "index.json")
        if os.path.exists(index_path):
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    index = json.load(f)
            except Exception:
                index = None
        all_concepts = (index or {}).get("concepts", []) if index else []
        id_set = {c.get("id") for c in all_concepts if c.get("id")}
        name_to_id = {c.get("name"): c.get("id") for c in all_concepts if c.get("id") and c.get("name")}

        candidates = []
        seen_texts = set()

        # 1. 从标题中提取（标题通常是知识点）
        for i, line in enumerate(body.split("\n"), 1):
            m = HEADING_RE.match(line)
            if m:
                title = m.group(2).strip()
                # 去掉行内链接 [[xxx]]
                clean = re.sub(r'\[\[([^\]]+)\]\]', '', title).strip()
                if clean and clean not in seen_texts and len(clean) <= 30:
                    seen_texts.add(clean)
                    matched_id = name_to_id.get(clean, "")
                    candidates.append({
                        "text": clean,
                        "line": i,
                        "source": "heading",
                        "exists": bool(matched_id),
                        "matched_id": matched_id,
                    })

        # 2. 从正文中用 jieba 提取关键词
        if jieba:
            try:
                keywords = jieba.analyse.extract_tags(body, topK=15, withWeight=False)
            except Exception:
                keywords = []
            for kw_text in keywords:
                if not kw_text or kw_text in seen_texts or len(kw_text) < 2:
                    continue
                seen_texts.add(kw_text)
                matched_id = name_to_id.get(kw_text, "")
                candidates.append({
                    "text": kw_text,
                    "line": 0,
                    "source": "keyword",
                    "exists": bool(matched_id),
                    "matched_id": matched_id,
                })

        # 3. 边建议：正文中所有 [[文本]] 链接
        cites = extract_citations(body)
        edge_suggestions = []
        seen_cite = set()
        for cite in cites:
            text = cite["text"]
            if text in seen_cite:
                continue
            seen_cite.add(text)
            matched_id = name_to_id.get(text, "")
            edge_suggestions.append({
                "text": text,
                "line": cite["line"],
                "matched_id": matched_id,
                "exists": bool(matched_id) or text in id_set,
            })

        return {
            "status": "ok",
            "candidates": candidates,
            "edge_suggestions": edge_suggestions,
        }


def main():
    api = MemoriaAPI()

    # 确定 viewer/index.html 的路径
    viewer_path = Path(__file__).parent / "viewer" / "index.html"
    if not viewer_path.exists():
        print(f"Error: viewer not found at {viewer_path}", file=sys.stderr)
        sys.exit(1)

    # 创建窗口
    webview.create_window(
        title="Memoria - AI 知识库",
        url=str(viewer_path),
        js_api=api,
        width=1200,
        height=800,
        min_size=(800, 600),
    )

    # 启动
    webview.start(debug=True)


if __name__ == "__main__":
    main()
