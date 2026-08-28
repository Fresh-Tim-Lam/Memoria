"""R11 平面文件导入引擎：将 --- 分隔的 .txt 文件转换为结构化知识库。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from memoria.graph.kb_build import build_knowledge_base
from memoria.services.kp_index import build_kp_index
from memoria.storage.constants import SIDECAR_SCHEMA_VERSION
from memoria.storage.markdown import compose_markdown
from memoria.storage.sidecar import save_sidecar_for_md


# ── 数据结构 ──────────────────────────────────────────────────────────


@dataclass
class ImportSection:
    frontmatter: dict
    body: str
    kp_ids: list[str]
    source_name: str
    segment_index: int


@dataclass
class ImportConflict:
    kp_id: str
    import_source: str
    import_line: int
    existing_file: str
    existing_name: str


@dataclass
class ImportScanResult:
    total_files: int
    total_sections: int
    total_kp_declarations: int
    conflicts: list[ImportConflict]
    has_conflicts: bool
    conflict_report: str


@dataclass
class ImportResult:
    status: str
    files_written: int
    sidecars_written: int
    kp_imported: int
    kp_skipped: int
    kp_renamed: int
    kp_overwritten: int
    errors: list[str] = field(default_factory=list)
    build_report: dict | None = None


# ── 1. 解析平面文件 ──────────────────────────────────────────────────


def parse_flat_file(content: str, source_name: str = "") -> list[ImportSection]:
    """将平面文件内容解析为 ImportSection 列表。

    使用状态机在 ``---`` 行之间切换 frontmatter / body。
    自动剥离首/尾 Markdown 代码围栏（角色 A 手册允许用 ```text 包裹
    平面文件内容展示；导入时若原样粘贴，围栏不应混入正文）。
    """
    content = _normalize_flat_content(content)
    lines = content.splitlines()
    sections: list[ImportSection] = []

    # 状态：0 = 在段外（寻找第一个 ---），1 = 在 frontmatter 中，2 = 在 body 中
    state = 0
    fm_lines: list[str] = []
    body_lines: list[str] = []
    seg_idx = 0

    for line in lines:
        stripped = line.strip()

        if state == 0:
            # 等待第一个 ---
            if stripped == "---":
                state = 1
                fm_lines = []
                body_lines = []
            # 忽略 --- 之前的行

        elif state == 1:
            # 在 frontmatter 中，等待第二个 ---
            if stripped == "---":
                # 结束 frontmatter，进入 body
                state = 2
            else:
                fm_lines.append(line)

        elif state == 2:
            # 在 body 中，等待第三个 ---（即下一段的 frontmatter 开始）
            if stripped == "---":
                # 保存当前 section
                sections.append(_build_section(fm_lines, body_lines, source_name, seg_idx))
                seg_idx += 1
                # 开始新 section 的 frontmatter
                state = 1
                fm_lines = []
                body_lines = []
            else:
                body_lines.append(line)

    # 文件末尾，保存最后一个 section
    if state == 2 and (fm_lines or body_lines):
        sections.append(_build_section(fm_lines, body_lines, source_name, seg_idx))

    return sections


def _normalize_flat_content(content: str) -> str:
    """规范化导入前的平面文件内容：

    1. 提取包裹用代码围栏（``` / ```text）块并拼接——角色 A 手册允许把
       平面文件放在代码块中输出，分批交付时每批各包一个围栏、批间夹杂
       对话/进度标记；此时平面文件 = 所有包裹围栏块内容的拼接，围栏外的
       总览表、批次标记、对话均为噪音。正文内部语言标记代码块（```python
       等）不属于包裹围栏，原样保留。
    2. 丢弃第一个独立 ``---`` 之前的全部前置内容（纯文本场景的总览表/链接表）。
    3. 若末尾残留包裹用代码围栏收标记 `` ``` ``（``` 计数为奇数，说明它是
       未配对的包裹围栏而非正文代码块），去掉它，避免混入最后一段 body。
    """
    extracted = _extract_wrapper_blocks(content)
    if extracted is not None:
        content = extracted

    lines = content.splitlines()

    # 1) 丢弃第一个 --- 之前的前置内容
    first_sep = next(
        (i for i, l in enumerate(lines) if l.strip() == "---"), None
    )
    if first_sep is not None:
        lines = lines[first_sep:]

    # 2) 末尾代码围栏收标记（奇数计数 = 包裹围栏，非正文代码块）
    if lines and lines[-1].strip() == "```":
        fence_count = sum(1 for l in lines if l.strip() == "```")
        if fence_count % 2 == 1:
            lines.pop()

    return "\n".join(lines)


def _extract_wrapper_blocks(content: str) -> str | None:
    """若内容含包裹用代码围栏（````` 或 ```text````），返回所有包裹块的拼接。

    返回 None 表示不存在包裹围栏，应整体按纯文本处理。
    注意：包裹围栏与正文代码块存在固有歧义（正文的裸 ``` 会提前关闭
    包裹块），约定正文代码块使用语言标记围栏（```python 等）规避。
    """
    lines = content.splitlines()
    out: list[str] = []
    in_block = False
    saw_wrapper = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            lang = stripped[3:].strip().lower()
            if not in_block:
                if lang in ("", "text"):
                    in_block = True
                    saw_wrapper = True
                else:
                    out.append(line)  # 正文语言代码块开标记，保留
            else:
                in_block = False
        elif in_block:
            out.append(line)
        # 围栏外内容一律丢弃
    if saw_wrapper:
        return "\n".join(out)
    return None


def _normalize_import_path(path: str) -> str:
    """规范化 frontmatter 的可选 `path` 字段（目标子目录，支持多级）。

    - 统一正斜杠、去除首尾 `/`、压缩连续 `/`
    - 拒绝绝对路径（盘符/UNC）与目录穿越（`..`），防止写出 KB 之外
    """
    raw = (path or "").strip()
    if not raw:
        return ""
    if raw.startswith(("/", "\\")):  # 类 Unix 绝对路径 / 反斜杠根路径
        raise ValueError(f"非法子目录路径: {path!r}（不允许绝对路径）")
    raw = raw.replace("\\", "/")
    segments = [seg for seg in raw.split("/") if seg and seg not in (".", "..")]
    if segments != [seg for seg in raw.split("/") if seg]:
        raise ValueError(f"非法子目录路径: {path!r}（不允许 .. 或空段）")
    if ":" in segments[0]:  # 盘符路径（C:/...）
        raise ValueError(f"非法子目录路径: {path!r}（不允许绝对路径）")
    return "/".join(segments)


def _build_section(
    fm_lines: list[str],
    body_lines: list[str],
    source_name: str,
    seg_idx: int,
) -> ImportSection:
    fm_text = "\n".join(fm_lines)
    try:
        frontmatter = yaml.safe_load(fm_text) if fm_text.strip() else {}
    except yaml.YAMLError:
        frontmatter = {}
    if not isinstance(frontmatter, dict):
        frontmatter = {}

    body = "\n".join(body_lines).strip()
    concepts = frontmatter.get("concepts") or []
    kp_ids = [c.get("id") for c in concepts if isinstance(c, dict) and c.get("id")]

    return ImportSection(
        frontmatter=frontmatter,
        body=body,
        kp_ids=kp_ids,
        source_name=source_name,
        segment_index=seg_idx,
    )


# ── 2. 预扫描冲突 ──────────────────────────────────────────────────


def pre_scan_import(sections: list[ImportSection], kb_path: str) -> ImportScanResult:
    """预扫描所有 section，检测 KP id 冲突。"""
    source_names = sorted({s.source_name for s in sections if s.source_name})
    total_files = len(source_names) or 1
    total_sections = len(sections)
    total_kp_declarations = sum(len(s.kp_ids) for s in sections)

    conflicts: list[ImportConflict] = []

    # 1) 收集导入 KP 声明及其来源信息
    import_kp_info: dict[str, list[tuple[str, int, str]]] = {}  # kp_id -> [(source, line_in_file, name)]
    for section in sections:
        concepts = section.frontmatter.get("concepts") or []
        for concept in concepts:
            if not isinstance(concept, dict):
                continue
            kp_id = concept.get("id")
            if not kp_id:
                continue
            # 计算该 concept 在导入文件中的行号
            line_no = _find_concept_line(section, kp_id)
            name = concept.get("name") or kp_id
            import_kp_info.setdefault(kp_id, []).append(
                (section.source_name, line_no, name)
            )

    # 2) 检测导入文件内部的重复 id
    seen_ids: dict[str, tuple[str, int]] = {}  # kp_id -> (source, line)
    for kp_id, entries in import_kp_info.items():
        if len(entries) > 1:
            # 第一个声明视为"已有"，后续的视为冲突
            first_source, first_line, first_name = entries[0]
            seen_ids[kp_id] = (first_source, first_line)
            for source, line_no, name in entries[1:]:
                conflicts.append(ImportConflict(
                    kp_id=kp_id,
                    import_source=f"{source} 段{sections[0].segment_index}" if not _find_section_index(sections, source, line_no) else f"{source} 段{_find_section_index(sections, source, line_no)}",
                    import_line=line_no,
                    existing_file=f"(导入内重复) {first_source}",
                    existing_name=first_name,
                ))
        else:
            seen_ids[kp_id] = (entries[0][0], entries[0][1])

    # 3) 构建已有知识库 KP 索引
    if os.path.isdir(kb_path):
        kb_index = build_kp_index(kb_path)
        by_id = kb_index.get("by_id") or {}
    else:
        by_id = {}

    # 4) 与已有知识库交叉
    for kp_id, entries in import_kp_info.items():
        if kp_id in by_id:
            existing_entries = by_id[kp_id]
            if existing_entries:
                ex = existing_entries[0]
                for source, line_no, name in entries:
                    conflicts.append(ImportConflict(
                        kp_id=kp_id,
                        import_source=f"{source} 段{_find_section_index(sections, source, line_no)}",
                        import_line=line_no,
                        existing_file=ex.file,
                        existing_name=ex.name,
                    ))

    # 5) 生成冲突报告
    conflict_report = _format_conflict_report(
        total_files, total_sections, total_kp_declarations, conflicts
    )

    return ImportScanResult(
        total_files=total_files,
        total_sections=total_sections,
        total_kp_declarations=total_kp_declarations,
        conflicts=conflicts,
        has_conflicts=bool(conflicts),
        conflict_report=conflict_report,
    )


def _find_concept_line(section: ImportSection, kp_id: str) -> int:
    """估算 concept 声明在原始文件中的行号。"""
    # 重新从 frontmatter 文本中查找行号
    fm_text = yaml.safe_dump(section.frontmatter.get("concepts") or [], allow_unicode=True, sort_keys=False)
    for i, line in enumerate(fm_text.splitlines()):
        if f"id: {kp_id}" in line or f"id: '{kp_id}'" in line or f'id: "{kp_id}"' in line:
            return i + 1
    return 0


def _find_section_index(sections: list[ImportSection], source_name: str, line_no: int) -> int:
    """查找 source_name 和行号对应的 segment_index。"""
    for s in sections:
        if s.source_name == source_name:
            return s.segment_index + 1  # 1-based for display
    return 1


def _format_conflict_report(
    total_files: int,
    total_sections: int,
    total_kp: int,
    conflicts: list[ImportConflict],
) -> str:
    if not conflicts:
        return f"[导入冲突报告]\n共扫描 {total_files} 个文件、{total_sections} 个段落、{total_kp} 个 KP 声明，无冲突。"

    lines = [
        f"[导入冲突报告]",
        f"共扫描 {total_files} 个文件、{total_sections} 个段落、{total_kp} 个 KP 声明，发现 {len(conflicts)} 个冲突：",
        "",
    ]
    for i, c in enumerate(conflicts, 1):
        lines.append(f"冲突 {i}：")
        lines.append(f"  KP id: {c.kp_id}")
        lines.append(f"  导入来源: {c.import_source} (第{c.import_line}行)" if c.import_line else f"  导入来源: {c.import_source}")
        lines.append(f"  已有位置: {c.existing_file} → {c.existing_name}")
        lines.append("")

    lines.append("建议操作：")
    lines.append("- 若需保留两者，请将导入文件中的 id 改为不同值")
    lines.append("- 若需覆盖已有，请在导入界面选择\"覆盖\"")
    lines.append("- 若需跳过，请在导入界面选择\"跳过\"")

    return "\n".join(lines)


# ── 3. 执行导入 ──────────────────────────────────────────────────


def execute_import(
    sections: list[ImportSection],
    kb_path: str,
    conflict_resolution: dict | None = None,
) -> ImportResult:
    """执行导入，将 sections 写入知识库。"""
    conflict_resolution = conflict_resolution or {}

    files_written = 0
    sidecars_written = 0
    kp_imported = 0
    kp_skipped = 0
    kp_renamed = 0
    kp_overwritten = 0
    errors: list[str] = []

    # 确保 kb_path 存在
    os.makedirs(kb_path, exist_ok=True)
    sidecar_dir = Path(kb_path) / ".memoria" / "sidecars"
    sidecar_dir.mkdir(parents=True, exist_ok=True)

    for section in sections:
        try:
            # 确定需要跳过 / 重命名 / 覆盖的 KP
            skip_ids: set[str] = set()
            rename_map: dict[str, str] = {}  # old_id -> new_id
            overwrite_ids: set[str] = set()

            for kp_id in section.kp_ids:
                resolution = conflict_resolution.get(kp_id, "")
                if resolution == "skip":
                    skip_ids.add(kp_id)
                elif resolution == "overwrite":
                    overwrite_ids.add(kp_id)
                elif isinstance(resolution, str) and resolution.startswith("rename:"):
                    new_id = resolution[len("rename:"):]
                    rename_map[kp_id] = new_id

            # 如果所有 KP 都被跳过，跳过整个 section
            active_ids = [kid for kid in section.kp_ids if kid not in skip_ids]
            if not active_ids and section.kp_ids:
                kp_skipped += len(section.kp_ids)
                continue

            kp_skipped += len(skip_ids)
            kp_renamed += len(rename_map)
            kp_overwritten += len(overwrite_ids)

            # 处理 frontmatter 中的 rename
            frontmatter = _apply_renames_to_frontmatter(section.frontmatter, rename_map)
            concepts = frontmatter.get("concepts") or []

            # 处理 body 中的 rename：替换 [[old_id]] 和 [[old_id|text]]
            body = _apply_renames_to_body(section.body, rename_map)

            # 确定输出文件名（含可选子目录 path，支持多级文件夹组织）
            active_concepts = [c for c in concepts if isinstance(c, dict) and c.get("id") not in skip_ids]
            if active_concepts:
                filename = active_concepts[0].get("id", "") + ".md"
            else:
                filename = f"section-{section.segment_index}.md"
            rel_dir = _normalize_import_path(section.frontmatter.get("path") or "")
            rel_path = f"{rel_dir}/{filename}" if rel_dir else filename

            # 写入 .md 文件（path 字段仅作为导入指令，不写入文档 frontmatter）
            md_path = os.path.join(kb_path, rel_path)
            os.makedirs(os.path.dirname(md_path), exist_ok=True)
            out_fm = {k: v for k, v in frontmatter.items() if k != "path"}
            md_content = compose_markdown(body, out_fm)

            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md_content)
            files_written += 1

            # 自动生成 sidecar（镜像目录随 rel_path 自动落到 .memoria/sidecars/ 下）
            sidecar_data = auto_generate_sidecar(rel_path, body, active_concepts)
            save_sidecar_for_md(md_path, kb_path, sidecar_data)
            sidecars_written += 1

            kp_imported += len(active_ids)

        except Exception as exc:
            errors.append(f"段 {section.segment_index} ({section.source_name}): {exc}")

    # 最终构建知识库
    build_report = None
    try:
        build_report = build_knowledge_base(kb_path)
    except Exception as exc:
        errors.append(f"构建知识库失败: {exc}")

    return ImportResult(
        status="ok" if not errors else "partial",
        files_written=files_written,
        sidecars_written=sidecars_written,
        kp_imported=kp_imported,
        kp_skipped=kp_skipped,
        kp_renamed=kp_renamed,
        kp_overwritten=kp_overwritten,
        errors=errors,
        build_report=build_report,
    )


def _apply_renames_to_frontmatter(frontmatter: dict, rename_map: dict[str, str]) -> dict:
    """在 frontmatter 的 concepts 中应用 rename。"""
    if not rename_map:
        return frontmatter

    fm = dict(frontmatter)
    concepts = fm.get("concepts") or []
    new_concepts = []
    for concept in concepts:
        if not isinstance(concept, dict):
            new_concepts.append(concept)
            continue
        c = dict(concept)
        old_id = c.get("id", "")
        if old_id in rename_map:
            c["id"] = rename_map[old_id]
        new_concepts.append(c)
    fm["concepts"] = new_concepts
    return fm


def _apply_renames_to_body(body: str, rename_map: dict[str, str]) -> str:
    """在 body 中替换 [[old_id]] 和 [[old_id|text]] 为新 id。"""
    if not rename_map:
        return body

    def replace_wikilink(match: re.Match) -> str:
        target = match.group(1)
        display = match.group(2)
        new_target = rename_map.get(target, target)
        if display:
            return f"[[{new_target}|{display}]]"
        return f"[[{new_target}]]"

    # 匹配 [[id]] 或 [[id|text]]
    pattern = r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]"
    return re.sub(pattern, replace_wikilink, body)


# ── 4. Sidecar 自动生成 ──────────────────────────────────────────


def auto_generate_sidecar(rel_path: str, body: str, concepts: list[dict]) -> dict:
    """根据 body 标题和 frontmatter concepts 自动生成 sidecar。"""
    # 1. 找出所有 ## 和 ### 标题及行号
    headings = _find_headings(body)

    # 2. 为每个 concept 匹配标题
    knowledge_points: list[dict] = []
    for concept in concepts:
        if not isinstance(concept, dict):
            continue
        kp_id = concept.get("id", "")
        kp_name = concept.get("name", "")
        weight = concept.get("weight")
        tags = concept.get("tags")

        # 按 name 匹配标题
        heading_idx = _match_heading(headings, kp_name)

        if heading_idx is not None:
            heading = headings[heading_idx]
            start_snippet = heading["text"]
            # end_snippet: 该标题到下一个标题之间的最后一行
            if heading_idx + 1 < len(headings):
                end_line = headings[heading_idx + 1]["line"] - 2  # 上一个非空行
            else:
                end_line = len(body.splitlines()) - 1

            body_lines = body.splitlines()
            if 0 <= end_line < len(body_lines):
                end_snippet = body_lines[end_line].strip()
            else:
                end_snippet = start_snippet

            kp_entry = {
                "id": kp_id,
                "name": kp_name,
                "range": {
                    "start": {"snippet": start_snippet},
                    "end": {"snippet": end_snippet},
                },
            }
        else:
            # 没有找到匹配标题，创建无 range 的 KP
            kp_entry = {
                "id": kp_id,
                "name": kp_name,
            }

        if weight is not None:
            kp_entry["weight"] = weight
        if tags is not None:
            kp_entry["tags"] = tags

        knowledge_points.append(kp_entry)

    return {
        "schema_version": SIDECAR_SCHEMA_VERSION,
        "file": rel_path,
        "knowledge_points": knowledge_points,
        "links": [],
        "edges": [],
    }


def _find_headings(body: str) -> list[dict]:
    """查找 body 中所有 ## 和 ### 标题。"""
    headings: list[dict] = []
    for i, line in enumerate(body.splitlines()):
        stripped = line.strip()
        if stripped.startswith("## ") or stripped.startswith("### "):
            # 去掉 ### 前缀，保留标题文本
            title = stripped.lstrip("#").strip()
            headings.append({"line": i, "text": stripped, "title": title})
    return headings


def _match_heading(headings: list[dict], kp_name: str) -> int | None:
    """将 concept name 与标题匹配，返回标题索引。"""
    if not kp_name:
        return None
    for i, h in enumerate(headings):
        if h["title"] == kp_name:
            return i
    # 模糊匹配：标题包含 kp_name 或 kp_name 包含标题
    for i, h in enumerate(headings):
        if kp_name in h["title"] or h["title"] in kp_name:
            return i
    return None
