"""Memoria 知识库构建器

以知识点 (KnowledgePoint) 为最小单元，解析 Markdown 文件：
1. 解析 frontmatter → concepts + edges（唯一格式）
2. 扫描正文标题 → 候选知识点（candidate=True）
3. 将 frontmatter concepts 与标题匹配 → 填充 line/depth/end_line
4. 提取正文 [[链接]] → 自动生成 reference 边
5. 标题层级推导 → 自动生成 contain 边 + 父子关系
"""

import json
import os
import re
from typing import Optional

import yaml

from .models import (
    BuildIndex, Edge, EdgeStrength, EdgeType,
    FileDescriptor, KnowledgePoint,
)


# ---------- 正则 ----------

_FM_DELIMITER = re.compile(r'^---\s*$')
_HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$')
_CITATION_RE = re.compile(r'\[\[([^\]]+)\]\]')


# ---------- frontmatter 解析 ----------

def _split_frontmatter(raw: str) -> tuple[dict, str]:
    """拆分 frontmatter 和正文

    Returns:
        (frontmatter_dict, body_str)
    """
    lines = raw.split('\n')
    if not lines or not _FM_DELIMITER.match(lines[0]):
        return {}, raw

    end = -1
    for i in range(1, len(lines)):
        if _FM_DELIMITER.match(lines[i]):
            end = i
            break

    if end == -1:
        return {}, raw

    fm_text = '\n'.join(lines[1:end])
    body = '\n'.join(lines[end + 1:])

    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, body


# ---------- 正文解析 ----------

def _scan_headings(body: str) -> list[dict]:
    """扫描正文所有标题行

    Returns:
        [{text, depth, line}, ...]
    """
    headings = []
    for i, line in enumerate(body.split('\n'), 1):
        m = _HEADING_RE.match(line)
        if m:
            depth = len(m.group(1))
            text = m.group(2).strip()
            headings.append({'text': text, 'depth': depth, 'line': i})
    return headings


def _extract_citations(body: str) -> list[dict]:
    """提取正文 [[文本]] 引用

    支持 [[id#type]] 语法指定边类型，例如 [[mdp#prerequisite]]。
    不指定 #type 时默认为 reference。

    Returns:
        [{text, line, edge_type}, ...]
    """
    results = []
    for i, line in enumerate(body.split('\n'), 1):
        for m in _CITATION_RE.finditer(line):
            raw = m.group(1)
            # 支持 [[id#type]] — # 后为边类型
            parts = raw.split('#')
            text = parts[0].split('|')[0].strip()
            edge_type = parts[1].strip() if len(parts) > 1 else 'reference'
            if text:
                results.append({'text': text, 'line': i, 'edge_type': edge_type})
    return results


def _compute_end_lines(headings: list[dict], total_lines: int) -> None:
    """为每个标题计算区域结束行

    规则：当前标题区域到下一个同级或更浅标题的前一行。
    """
    for i, h in enumerate(headings):
        end = total_lines + 1
        for j in range(i + 1, len(headings)):
            if headings[j]['depth'] <= h['depth']:
                end = headings[j]['line'] - 1
                break
        h['end_line'] = end


def _build_concept_tree(kps: list[KnowledgePoint]) -> dict:
    """从知识点列表构建包含树

    按 line 排序后，用栈推导父子关系。
    只处理 is_node 的知识点（正式 + 候选）。
    """
    tree = {}
    # 正式知识点和候选知识点都参与包含关系
    eligible = [kp for kp in kps if kp.id or kp.candidate]
    stack: list[KnowledgePoint] = []

    sorted_kps = sorted(eligible, key=lambda k: k.line)

    for kp in sorted_kps:
        while stack and stack[-1].depth >= kp.depth:
            stack.pop()

        if stack:
            kp.parent_id = stack[-1].id or None
            stack[-1].children_ids.append(kp.id or f"@candidate:{kp.name}")

        tree[kp.id or f"@candidate:{kp.name}"] = {
            'parent': kp.parent_id,
            'children': kp.children_ids,
        }
        stack.append(kp)

    return tree


# ---------- 单文件解析 ----------

def _parse_file(file_path: str, rel_path: str) -> FileDescriptor:
    """解析单个 .md 文件

    流程：
    1. 拆 frontmatter + body
    2. 扫描正文标题 → 候选知识点列表
    3. frontmatter concepts 与标题匹配 → 正式知识点
    4. 未匹配标题 → 保留为候选（candidate=True）
    5. 提取正文引用 → 生成 reference 边
    6. 解析 frontmatter edges → 显式边
    7. 标题层级推导 → contain 边
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw = f.read()
    except Exception:
        return FileDescriptor(path=rel_path)

    fm, body = _split_frontmatter(raw)

    # ---- 扫描标题 ----
    headings = _scan_headings(body)
    total_lines = len(body.split('\n'))
    _compute_end_lines(headings, total_lines)

    # 标题查找表：name.lower() → heading（取第一个匹配）
    heading_by_name: dict[str, dict] = {}
    for h in headings:
        heading_by_name.setdefault(h['text'].lower(), h)

    # ---- 构建正式 concepts（来自 frontmatter） ----
    concepts: list[KnowledgePoint] = []
    matched_headings: set[str] = set()

    for c_def in fm.get('concepts') or []:
        if isinstance(c_def, str):
            c_def = {'name': c_def}

        cid = str(c_def['id']) if c_def.get('id') else ''
        name = str(c_def.get('name', cid))
        weight = float(c_def.get('weight', 1.0 if cid else 0.5))
        raw_tags = c_def.get('tags', [])
        if isinstance(raw_tags, str):
            raw_tags = [t.strip() for t in raw_tags.split(',') if t.strip()]
        tags = [str(t) for t in raw_tags] if raw_tags else []

        # 匹配正文标题
        heading = heading_by_name.get(name.lower())
        kp = KnowledgePoint(
            id=cid,
            name=name,
            file=rel_path,
            depth=heading['depth'] if heading else 0,
            line=heading['line'] if heading else 0,
            end_line=heading.get('end_line', 0) if heading else 0,
            weight=weight,
            tags=tags,
            candidate=False,  # frontmatter 声明的 = 正式
        )
        concepts.append(kp)
        if heading:
            matched_headings.add(name.lower())

    # ---- 候选知识点：正文中未在 frontmatter 声明的标题 ----
    for h in headings:
        if h['text'].lower() not in matched_headings:
            concepts.append(KnowledgePoint(
                id='',
                name=h['text'],
                file=rel_path,
                depth=h['depth'],
                line=h['line'],
                end_line=h.get('end_line', 0),
                weight=0.3,
                candidate=True,  # 正文自动发现 = 候选
            ))

    # 按 line 排序
    concepts.sort(key=lambda k: k.line if k.line > 0 else 999999)

    # ---- 构建包含关系 ----
    _build_concept_tree(concepts)

    # ---- 边 ----
    edges: list[Edge] = []

    # 引用边：只从 [[id]] 链接生成，支持 [[id#type]] 语法
    citations = _extract_citations(body)
    for cite in citations:
        source_kp = _find_kp_at_line(concepts, cite['line'])
        if not source_kp or not source_kp.is_node:
            continue
        try:
            edge_type = EdgeType(cite['edge_type'])
        except ValueError:
            edge_type = EdgeType.REFERENCE
        edges.append(Edge(
            source_id=source_kp.id,
            target_id=cite['text'],
            type=edge_type,
            strength=EdgeStrength.WEAK,
            text=cite['text'],
        ))

    return FileDescriptor(
        path=rel_path,
        description=fm.get('description', ''),
        concepts=concepts,
        edges=edges,
    )


def _find_kp_at_line(concepts: list[KnowledgePoint], line: int) -> Optional[KnowledgePoint]:
    """找到包含指定行号的最深知识点"""
    best = None
    for kp in concepts:
        if kp.line > 0 and kp.line <= line:
            if kp.end_line > 0 and line > kp.end_line:
                continue
            if best is None or kp.depth > best.depth:
                best = kp
    return best


# ---------- 主构建流程 ----------

def build(kb_path: str, output: str = None) -> dict:
    """构建知识库索引

    Args:
        kb_path: 知识库根目录
        output: 输出目录（默认 kb_path/.build）

    Returns:
        {"status": "ok", "stats": {...}} 或 {"status": "error", "message": ...}
    """
    if output is None:
        output = os.path.join(kb_path, '.build')
    os.makedirs(output, exist_ok=True)

    # 收集 .md 文件
    md_files = []
    for root, dirs, files in os.walk(kb_path):
        if '.build' in dirs:
            dirs.remove('.build')
        for fname in files:
            if fname.endswith('.md'):
                md_files.append(os.path.join(root, fname))

    if not md_files:
        return {'status': 'error', 'message': '知识库中没有 .md 文件'}

    # 解析每个文件
    file_descriptors: list[FileDescriptor] = []
    all_concepts: list[KnowledgePoint] = []
    all_edges: list[Edge] = []
    id_to_files: dict[str, list[str]] = {}

    for fpath in md_files:
        rel_path = os.path.relpath(fpath, kb_path)
        fd = _parse_file(fpath, rel_path)
        file_descriptors.append(fd)

        for kp in fd.concepts:
            all_concepts.append(kp)
            if kp.is_node:
                id_to_files.setdefault(kp.id, []).append(rel_path)

        all_edges.extend(fd.edges)

    # ---- 全局包含树（按文件构建后合并） ----
    concepts_by_file: dict[str, list[KnowledgePoint]] = {}
    concept_tree: dict = {}
    for c in all_concepts:
        if c.is_node or c.candidate:
            concepts_by_file.setdefault(c.file, []).append(c)
    for file_concepts in concepts_by_file.values():
        file_tree = _build_concept_tree(file_concepts)
        concept_tree.update(file_tree)

    # ---- 从包含树生成 CONTAIN 边 ----
    contain_edges_added = 0
    for file_key, file_concepts in concepts_by_file.items():
        file_tree = _build_concept_tree(file_concepts)
        for node_id, info in file_tree.items():
            for child_id in info['children']:
                # 只在两个都是正式节点时才生成边
                source_is_node = any(c.id == node_id and c.is_node for c in file_concepts)
                if not source_is_node:
                    continue
                child_is_node = any(c.id == child_id and c.is_node for c in file_concepts)
                if not child_is_node:
                    continue
                all_edges.append(Edge(
                    source_id=node_id,
                    target_id=child_id,
                    type=EdgeType.CONTAIN,
                    strength=EdgeStrength.STRONG,
                    text='',
                ))
                contain_edges_added += 1

    # ---- 虚链检测 ----
    defined_ids = {c.id for c in all_concepts if c.is_node}
    dangling_links = []
    seen_dangling = set()
    for e in all_edges:
        if e.type == EdgeType.REFERENCE and e.target_id not in defined_ids:
            key = (e.source_id, e.target_id)
            if key not in seen_dangling:
                seen_dangling.add(key)
                dangling_links.append({
                    'source': e.source_id,
                    'text': e.target_id,
                })

    # ---- id 冲突检测 ----
    duplicates = []
    for cid, files in id_to_files.items():
        if len(files) > 1:
            duplicates.append({'id': cid, 'files': files})

    # ---- 候选统计 ----
    candidate_count = sum(1 for c in all_concepts if c.candidate)

    # ---- 输出 ----
    index = BuildIndex(
        files=file_descriptors,
        concepts=all_concepts,
        edges=all_edges,
        concept_tree=concept_tree,
        dangling_links=dangling_links,
        duplicates=duplicates,
    )

    with open(os.path.join(output, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(index.to_dict(), f, ensure_ascii=False, indent=2)

    graph = index.to_graph_dict()
    with open(os.path.join(output, 'graph.json'), 'w', encoding='utf-8') as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)

    stats = {
        'files': len(file_descriptors),
        'concepts': len([c for c in all_concepts if c.is_node]),
        'candidates': candidate_count,
        'edges': len(all_edges),
        'dangling': len(dangling_links),
        'duplicates': len(duplicates),
    }

    return {
        'status': 'ok',
        'stats': stats,
    }
