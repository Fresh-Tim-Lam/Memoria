"""Python 原生知识库构建器

取代 C++ builder，解析新数据模型（concepts/edges），
兼容旧 frontmatter（provides/tags/prerequisite/extend/analogy）自动迁移。

新 index.json 结构：
{
  "files": [{file, description, concepts:[{id?,name,weight}], edges:[{type,text?,targets}]}],
  "concepts": [{id, name, file, weight}],           # 全局知识点索引（仅有 id 的）
  "citations": [{source_file, text, line}],           # 正文 [[文本]] 引用
  "concept_locations": {id: {file, heading_line, heading_text}},  # id→标题位置
  "dangling_links": [...],                             # 虚链（无对应 reference 边）
  "duplicates": [...]                                  # 知识点 id 冲突
}
"""
import json
import os
import re

import yaml


# ---------- frontmatter 解析 ----------

def split_frontmatter(raw: str):
    """把 md 文件拆成 (frontmatter_dict, body_str)

    无 frontmatter 时返回 ({}, raw)
    """
    lines = raw.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, raw

    # 找闭合 ---
    end = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break

    if end == -1:
        return {}, raw

    fm_text = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1:])

    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, body


# ---------- 旧 frontmatter 迁移 ----------

def migrate_old_frontmatter(fm: dict) -> dict:
    """把旧 frontmatter（id/title/provides/tags/prerequisite/extend/analogy）
    迁移为新结构（description/concepts/edges）。

    已是新结构则原样返回。
    """
    if "concepts" in fm or "edges" in fm:
        # 新结构，补全默认值
        fm.setdefault("description", "")
        fm.setdefault("concepts", [])
        fm.setdefault("edges", [])
        return fm

    # 旧结构迁移
    concepts = []
    edges = []

    # provides → concepts（有 id 的知识点）
    old_provides = fm.get("provides") or []
    if isinstance(old_provides, list):
        for p in old_provides:
            if isinstance(p, dict):
                pid = p.get("id", "")
                if pid is not None and pid != "":
                    pid = str(pid)
                concepts.append({
                    "id": pid,
                    "name": str(p.get("title", p.get("id", ""))),
                    "weight": 1.0,
                })
            elif isinstance(p, str):
                concepts.append({"id": p, "name": p, "weight": 1.0})

    # 如果没有 provides 但有 id/title，用 id 作为知识点
    if not concepts and fm.get("id"):
        concepts.append({
            "id": str(fm["id"]),
            "name": str(fm.get("title", fm["id"])),
            "weight": 1.0,
        })

    # tags → concepts（无 id 的 tag）
    old_tags = fm.get("tags") or []
    if isinstance(old_tags, list):
        for t in old_tags:
            concepts.append({"name": str(t), "weight": 0.5})

    # prerequisite/extend/analogy → edges
    for rel_type in ("prerequisite", "extend", "analogy"):
        targets = fm.get(rel_type) or []
        if isinstance(targets, list) and targets:
            edges.append({"type": rel_type, "targets": [str(t) for t in targets]})

    # description：旧结构没有，留空
    return {
        "description": "",
        "concepts": concepts,
        "edges": edges,
    }


# ---------- 正文引用提取 ----------

CITATION_RE = re.compile(r'\[\[([^\]]+)\]\]')


def extract_citations(body: str):
    """提取正文 [[文本]] 引用

    [[文本]] 中的"文本"不是 id，是显示文本。
    支持 [[text]] 和 [[text|display]] 两种形式（取 | 之前作为 text）。

    Returns:
        [{text, line}, ...]
    """
    results = []
    for i, line in enumerate(body.split("\n"), 1):
        for m in CITATION_RE.finditer(line):
            raw = m.group(1)
            text = raw.split("|")[0].strip()
            # 去掉 #anchor（兼容旧格式 [[id#anchor]]）
            text = text.split("#")[0].strip()
            if text:
                results.append({"text": text, "line": i})
    return results


# ---------- 标题位置匹配 ----------

HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$')


def find_heading_lines(body: str):
    """提取正文所有标题行

    Returns:
        {heading_text: line_num, ...}  （heading_text 已 trim，转小写用于匹配）
    """
    headings = {}
    for i, line in enumerate(body.split("\n"), 1):
        m = HEADING_RE.match(line)
        if m:
            text = m.group(2).strip()
            # 去掉旧的 [:anchor:xxx] 标记
            text = re.sub(r'\[:anchor:[^\]]+\]', '', text).strip()
            headings.setdefault(text.lower(), i)  # 第一个匹配
    return headings


def build_concept_locations(concepts_with_id, headings, file_path):
    """为每个有 id 的 concept 匹配正文标题位置

    Returns:
        {concept_id: {file, heading_line, heading_text}}
    """
    locations = {}
    for c in concepts_with_id:
        name = c["name"]
        cid = c["id"]
        # 尝试精确匹配（大小写不敏感）
        line = headings.get(name.lower())
        if line:
            locations[cid] = {
                "file": file_path,
                "heading_line": line,
                "heading_text": name,
            }
        else:
            # 无匹配，记录文件但无行号（跳转到文件开头）
            locations[cid] = {
                "file": file_path,
                "heading_line": 0,
                "heading_text": name,
            }
    return locations


# ---------- 主构建流程 ----------

def build(kb_path: str, output: str = None) -> dict:
    """构建知识库索引（Python 原生，替代 C++ builder）

    Args:
        kb_path: 知识库根目录
        output: 输出目录（默认 kb_path/.build）

    Returns:
        {"status": "ok", "stats": {...}} 或 {"status": "error", "message": ...}
    """
    if output is None:
        output = os.path.join(kb_path, ".build")
    os.makedirs(output, exist_ok=True)

    # 收集所有 .md 文件（排除 .build）
    md_files = []
    for root, dirs, files in os.walk(kb_path):
        if ".build" in dirs:
            dirs.remove(".build")
        for fname in files:
            if fname.endswith(".md"):
                md_files.append(os.path.join(root, fname))

    if not md_files:
        return {"status": "error", "message": "知识库中没有 .md 文件"}

    files_data = []          # files 数组
    all_concepts = []         # 全局 concepts 索引（仅有 id 的）
    all_citations = []        # 正文引用
    concept_locations = {}    # id → 位置
    warnings = []

    # id → files 映射（冲突检测）
    id_to_files = {}

    for fpath in md_files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception as e:
            warnings.append(f"读取失败 {fpath}: {e}")
            continue

        # 统一存储相对 kb_path 的路径，前后端一致寻址
        rel_path = os.path.relpath(fpath, kb_path)

        fm, body = split_frontmatter(raw)
        fm = migrate_old_frontmatter(fm)

        description = fm.get("description", "")
        concepts = fm.get("concepts") or []
        edges = fm.get("edges") or []

        # 规范化 concepts
        norm_concepts = []
        for c in concepts:
            if isinstance(c, dict):
                cid = c.get("id", "")
                if cid is not None and cid != "":
                    cid = str(cid)
                # tags：字符串数组，便于搜索匹配
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
        for e in edges:
            if isinstance(e, dict):
                edge = {
                    "type": e.get("type", "reference"),
                    "targets": [str(t) for t in (e.get("targets") or [])],
                }
                if "text" in e:
                    edge["text"] = str(e["text"])
                norm_edges.append(edge)

        # 记录文件数据
        files_data.append({
            "file": rel_path,
            "description": description,
            "concepts": norm_concepts,
            "edges": norm_edges,
        })

        # 收集有 id 的 concepts 到全局索引
        for c in norm_concepts:
            if c["id"]:
                all_concepts.append({
                    "id": c["id"],
                    "name": c["name"],
                    "file": rel_path,
                    "weight": c["weight"],
                    "tags": c.get("tags", []),
                })
                id_to_files.setdefault(c["id"], []).append(rel_path)

        # 提取正文引用
        cites = extract_citations(body)
        for cite in cites:
            all_citations.append({
                "source_file": rel_path,
                "text": cite["text"],
                "line": cite["line"],
            })

        # 构建概念位置映射（标题匹配）
        concepts_with_id = [c for c in norm_concepts if c["id"]]
        headings = find_heading_lines(body)
        locs = build_concept_locations(concepts_with_id, headings, rel_path)
        concept_locations.update(locs)

    # 冲突检测：id 被多个文件声明
    duplicates = []
    for cid, files in id_to_files.items():
        if len(files) > 1:
            duplicates.append({"id": cid, "files": files})

    # 虚链检测：正文 [[文本]] 无对应 reference 边
    # 对每个文件，检查 citations 的 text 是否在 edges 有 reference 边
    dangling_links = []
    for fdata in files_data:
        ref_texts = {e.get("text") for e in fdata["edges"] if e["type"] == "reference"}
        file_cites = [c for c in all_citations if c["source_file"] == fdata["file"]]
        seen = set()
        for cite in file_cites:
            if cite["text"] not in ref_texts and cite["text"] not in seen:
                seen.add(cite["text"])
                dangling_links.append({
                    "text": cite["text"],
                    "source_file": fdata["file"],
                })

    # 组装 index.json
    # 兼容层：生成 nodes 数组（旧前端代码依赖 index.nodes）
    # 每个 concept（有 id 的）映射为一个 node
    nodes_compat = []
    for c in all_concepts:
        nodes_compat.append({
            "id": c["id"],
            "title": c["name"],
            "file": c["file"],
            "tags": [],
            "provides": [{"id": c["id"], "title": c["name"]}],
            "citations": [],  # 兼容字段，新模型用 index.citations
        })
    # 把正文引用挂到对应 node 上（兼容旧前端 _enrich_index 逻辑）
    for cite in all_citations:
        for node in nodes_compat:
            if node["file"] == cite["source_file"]:
                node["citations"].append({
                    "target": cite["text"],
                    "source": cite["source_file"],
                })

    index = {
        "files": files_data,
        "concepts": all_concepts,
        "nodes": nodes_compat,  # 兼容旧前端
        "citations": [{"source": c["source_file"], "target": c["text"], "line": c["line"]}
                      for c in all_citations],
        "concept_locations": concept_locations,
        "dangling_links": dangling_links,
        "duplicates": duplicates,
    }

    # 写 index.json
    with open(os.path.join(output, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    # 写 graph.json（D3 force-directed 格式，兼容旧图谱渲染）
    graph = _build_graph(files_data, all_concepts)
    with open(os.path.join(output, "graph.json"), "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)

    stats = {
        "files": len(files_data),
        "concepts": len(all_concepts),
        "citations": len(all_citations),
        "dangling": len(dangling_links),
        "duplicates": len(duplicates),
    }

    return {
        "status": "ok",
        "stats": stats,
        "warnings": warnings,
        "index": index,
        "graph": graph,
    }


def _build_graph(files_data, all_concepts):
    """构建 graph.json（D3 force-directed 格式）"""
    nodes = []
    for c in all_concepts:
        nodes.append({"id": c["id"], "title": c["name"]})

    links = []
    seen_links = set()
    for fdata in files_data:
        for edge in fdata["edges"]:
            if edge["type"] == "reference":
                continue  # reference 边不进图谱（太密集）
            for target in edge["targets"]:
                # 找源概念（文件中 weight 最高的有 id concept）
                source_concepts = [c for c in fdata["concepts"] if c.get("id")]
                if not source_concepts:
                    break
                source = max(source_concepts, key=lambda c: c.get("weight", 0))["id"]
                key = (source, target, edge["type"])
                if key not in seen_links:
                    seen_links.add(key)
                    links.append({
                        "source": source,
                        "target": target,
                        "type": edge["type"],
                    })

    return {"nodes": nodes, "links": links}
