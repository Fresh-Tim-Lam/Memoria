"""0.3.0 统一导入扫描/预览层（import-spec §4–§8）。

三种导入源（flat_file / md_dir / kb_bundle）在写入前统一归一为
ImportPreview：摘要、拟建/变更文件清单、KP 清单、冲突清单与 issues，
供前端「清单预览」与 Agent 反馈（JSON/Markdown）直接消费。

本模块只读（不写库）：扫描、指纹判定、冲突检测均无副作用；
执行（写文件/建 sidecar）在 import_executor 中按 decisions 应用。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from memoria.services.import_engine import _normalize_import_path, parse_flat_file
from memoria.services.kp_index import build_kp_index
from memoria.storage.markdown import compose_markdown
from memoria.storage.sidecar import SIDECAR_SUFFIX

FLAT_FILE = "flat_file"
MD_DIR = "md_dir"
KB_BUNDLE = "kb_bundle"
KINDS = (FLAT_FILE, MD_DIR, KB_BUNDLE)


def _iter_kb_files(kb_path: str) -> list[Path]:
    """列出 KB 内全部 .md（排除 .memoria 内部）。"""
    root = Path(kb_path)
    if not root.is_dir():
        return []
    return sorted(
        p for p in root.rglob("*.md") if ".memoria" not in p.parts
    )


def _existing_file_map(kb_path: str) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for p in _iter_kb_files(kb_path):
        rel = p.relative_to(kb_path).as_posix()
        out[rel] = p
    return out


def _existing_kp_ids(kb_path: str) -> dict[str, dict]:
    if not os.path.isdir(kb_path):
        return {}
    try:
        index = build_kp_index(kb_path)
    except Exception:
        return {}
    by_id = index.get("by_id") or {}
    out: dict[str, dict] = {}
    for kid, entries in by_id.items():
        first = entries[0] if entries else None
        out[kid] = (
            {"file": first.file, "name": first.name}
            if first is not None
            else {}
        )
    return out


def _is_idempotent_kp(ex: dict, rel_path: str, action: str) -> bool:
    """幂等重导判定：目标文件无变更且库内该 KP 同处此文件 →
    导入不会改写任何内容，无需决策，不构成冲突（消除幂等重导的冲突噪声）。"""
    return action == "unchanged" and ex.get("file") == rel_path


@dataclass
class PlannedFile:
    rel_path: str
    action: str  # new | overwrite | rename | skip | unchanged
    source: str = ""
    kp_ids: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


@dataclass
class PlannedKp:
    id: str
    name: str = ""
    tags: list = field(default_factory=list)
    file: str = ""
    source: str = "concept"  # concept | plain（纯文件无 KP 时不产生该对象）
    range_missing: bool = False
    issues: list[str] = field(default_factory=list)


@dataclass
class ConflictItem:
    kind: str  # file_exists | kp_id_taken
    subject: str
    options: list[str] = field(default_factory=list)
    detail: str = ""


@dataclass
class ImportPreview:
    kind: str
    source_label: str
    summary: dict = field(default_factory=dict)
    files: list[PlannedFile] = field(default_factory=list)
    kp: list[PlannedKp] = field(default_factory=list)
    conflicts: list[ConflictItem] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    def as_json(self) -> dict:
        return {
            "schema_version": "1.0",
            "import": {"kind": self.kind, "source": self.source_label},
            "summary": self.summary,
            "files": [
                {
                    "rel_path": f.rel_path,
                    "action": f.action,
                    "kp_ids": f.kp_ids,
                    "issues": f.issues,
                }
                for f in self.files
            ],
            "kp": [
                {
                    "id": k.id,
                    "name": k.name,
                    "tags": k.tags,
                    "range": None if k.range_missing else "pending",
                    "source": k.source,
                    "issues": k.issues,
                }
                for k in self.kp
            ],
            "conflicts": [
                {
                    "kind": c.kind,
                    "subject": c.subject,
                    "options": c.options,
                    "detail": c.detail,
                }
                for c in self.conflicts
            ],
            "issues": self.issues,
        }

    def as_markdown(self) -> str:
        lines = [f"# 导入预览：{self.kind}", ""]
        lines.append("## 摘要")
        lines.append(
            "新建文件 {files_new} · 覆盖 {files_overwrite} · 重命名 {files_rename} · "
            "跳过 {files_skip} · 无变更 {files_unchanged} · 新增 KP {kp_new} · "
            "冲突 {conflicts}".format(**self.summary)
        )
        lines += ["", "## 文件"]
        for f in self.files:
            lines.append(f"- `{f.rel_path}` · {f.action}")
            if f.kp_ids:
                lines.append(f"  KP: {', '.join(f.kp_ids)}")
            for issue in f.issues:
                lines.append(f"  ⚠ {issue}")
        lines += ["", "## 知识点"]
        for k in self.kp:
            note = "（待配置范围）" if k.range_missing else ""
            lines.append(f"- `{k.id}` {k.name} · {', '.join(k.tags)}{note}")
        lines += ["", "## 冲突"]
        if not self.conflicts:
            lines.append("无")
        for c in self.conflicts:
            lines.append(f"- {c.kind}: {c.subject} · 可选 {', '.join(c.options)} — {c.detail}")
        if self.issues:
            lines += ["", "## 其它提示"]
            for issue in self.issues:
                lines.append(f"- {issue}")
        return "\n".join(lines)


# ── 指纹与动作判定 ────────────────────────────────────────────────


def _decide_file_action(
    rel_path: str,
    content: str,
    existing_map: dict[str, Path],
) -> str:
    """按内容指纹判断动作：unchanged / new / overwrite（重命名由前端决策）。"""
    existing = existing_map.get(rel_path)
    if existing is None:
        return "new"
    try:
        old = existing.read_text(encoding="utf-8")
    except OSError:
        return "overwrite"
    if old == content:
        return "unchanged"
    return "overwrite"


# ── 源解析器 ──────────────────────────────────────────────────────


def _preview_flat(sources: list[dict], kb_path: str) -> ImportPreview:
    """sources: [{"name": str, "content": str}]（content 已读取的平面文本）。"""
    existing = _existing_file_map(kb_path)
    existing_kp = _existing_kp_ids(kb_path)
    preview = ImportPreview(kind=FLAT_FILE, source_label=", ".join(s["name"] for s in sources))
    seen_kp_dup: dict[str, str] = {}

    for src in sources:
        name = src.get("name") or "粘贴内容"
        content = src.get("content") or ""
        for section in parse_flat_file(content, source_name=name):
            concepts = [c for c in (section.frontmatter.get("concepts") or []) if isinstance(c, dict)]
            active = [c for c in concepts if c.get("id")]
            if not active:
                continue
            rel_dir = ""
            try:
                rel_dir = _normalize_import_path(section.frontmatter.get("path") or "")
            except ValueError as exc:
                preview.issues.append(f"{name} 段{section.segment_index}: {exc}")
            filename = f"{active[0].get('id')}.md"
            rel_path = f"{rel_dir}/{filename}" if rel_dir else filename
            out_fm = {k: v for k, v in section.frontmatter.items() if k != "path"}
            content_out = compose_markdown(section.body, out_fm)
            action = _decide_file_action(rel_path, content_out, existing)

            kp_ids = []
            for concept in active:
                kid = str(concept.get("id") or "")
                if not kid:
                    continue
                kp_ids.append(kid)
                prev = seen_kp_dup.get(kid)
                if prev and prev != rel_path:
                    preview.conflicts.append(
                        ConflictItem(
                            kind="kp_id_taken",
                            subject=kid,
                            options=["skip", "overwrite", "rename"],
                            detail=f"导入文件内重复（{prev} 与 {rel_path}）",
                        )
                    )
                elif kid in existing_kp:
                    ex = existing_kp[kid]
                    if not _is_idempotent_kp(ex, rel_path, action):
                        preview.conflicts.append(
                            ConflictItem(
                                kind="kp_id_taken",
                                subject=kid,
                                options=["skip", "overwrite", "rename"],
                                detail=f"库内已有：{ex.get('file')} / {ex.get('name')}",
                            )
                        )
                seen_kp_dup[kid] = rel_path
                preview.kp.append(
                    PlannedKp(
                        id=kid,
                        name=str(concept.get("name") or kid),
                        tags=concept.get("tags") or [],
                        file=rel_path,
                    )
                )
            if action == "overwrite" and kp_ids and any(k in existing_kp for k in kp_ids):
                preview.conflicts.append(
                    ConflictItem(
                        kind="file_exists",
                        subject=rel_path,
                        options=["skip", "overwrite", "rename"],
                        detail=f"目标文件已存在且内容不同（{existing.get(rel_path)}）",
                    )
                )
            preview.files.append(
                PlannedFile(rel_path=rel_path, action=action, source=name, kp_ids=kp_ids)
            )
    _finalize_summary(preview)
    return preview


def expand_md_source_pairs(sources: list[dict]) -> list[tuple[str, str]]:
    """md_dir 源展开为 (绝对路径, 目标 rel)。

    源可为单文件或目录：目录递归收集 .md 并保留目录内相对结构；
    src 带 root 时，目标 rel 相对该 root（多文件/混选时保持子目录层级）。
    """
    out: list[tuple[str, str]] = []
    for src in sources:
        p = Path(src.get("path") or "")
        root = Path(src["root"]) if src.get("root") else None
        if p.is_dir():
            for md in sorted(p.rglob("*.md")):
                if ".memoria" in md.parts:
                    continue
                out.append((str(md), md.relative_to(p).as_posix()))
        elif p.is_file() and p.suffix.lower() == ".md":
            rel = f"{p.stem}.md"
            if root and root.is_dir():
                try:
                    rel = p.relative_to(root).as_posix()
                except ValueError:
                    rel = f"{p.stem}.md"
            out.append((str(p), rel))
    return out


def _preview_md_dir(sources: list[dict], kb_path: str) -> ImportPreview:
    """sources: [{"path": 文件或目录}]；无 frontmatter → 纯文件入库。"""
    existing = _existing_file_map(kb_path)
    existing_kp = _existing_kp_ids(kb_path)
    preview = ImportPreview(kind=MD_DIR, source_label=", ".join(s.get("path", "") for s in sources))
    used_names: set[str] = set()

    for abs_path, rel_path in expand_md_source_pairs(sources):
        p = Path(abs_path)
        try:
            content = p.read_text(encoding="utf-8")
        except OSError as exc:
            preview.issues.append(f"{p}: 读取失败 {exc}")
            continue
        fm, body = _split_frontmatter(content)
        concepts = [c for c in (fm.get("concepts") or []) if isinstance(c, dict) and c.get("id")]
        action = _decide_file_action(rel_path, content, existing)
        if rel_path in used_names:
            preview.conflicts.append(
                ConflictItem(
                    kind="file_exists",
                    subject=rel_path,
                    options=["skip", "overwrite", "rename"],
                    detail="同批源文件中存在重名文件",
                )
            )
        else:
            used_names.add(rel_path)
        if action == "overwrite":
            preview.conflicts.append(
                ConflictItem(
                    kind="file_exists",
                    subject=rel_path,
                    options=["skip", "overwrite", "rename"],
                    detail=f"目标文件已存在且内容不同（{existing.get(rel_path)}）",
                )
            )
        kp_ids = []
        for concept in concepts:
            kid = str(concept.get("id") or "")
            kp_ids.append(kid)
            if kid in existing_kp:
                ex = existing_kp[kid]
                if not _is_idempotent_kp(ex, rel_path, action):
                    preview.conflicts.append(
                        ConflictItem(
                            kind="kp_id_taken",
                            subject=kid,
                            options=["skip", "overwrite", "rename"],
                            detail=f"库内已有：{ex.get('file')} / {ex.get('name')}",
                        )
                    )
            preview.kp.append(
                PlannedKp(
                    id=kid,
                    name=str(concept.get("name") or kid),
                    tags=concept.get("tags") or [],
                    file=rel_path,
                    range_missing=True,
                    issues=["concepts 未含行号范围，入库后请配置"] if not _has_ranges(fm) else [],
                )
            )
        preview.files.append(
            PlannedFile(rel_path=rel_path, action=action, source=str(p), kp_ids=kp_ids)
        )
    _finalize_summary(preview)
    return preview


def _preview_kb_bundle(sources: list[dict], kb_path: str) -> ImportPreview:
    """sources: [{"path": 包目录绝对路径}]（md + .memoria/sidecars/*.memoria.yaml）。"""
    existing = _existing_file_map(kb_path)
    existing_kp = _existing_kp_ids(kb_path)
    preview = ImportPreview(kind=KB_BUNDLE, source_label=", ".join(s["path"] for s in sources))
    sidecar_dir = Path(sources[0]["path"]) / ".memoria" / "sidecars" if sources else None

    for src in sources:
        root = Path(src["path"])
        if not root.is_dir():
            preview.issues.append(f"{root}: 不是目录")
            continue
        for md in sorted(root.rglob("*.md")):
            if ".memoria" in md.parts:
                continue
            rel = md.relative_to(root).as_posix()
            try:
                content = md.read_text(encoding="utf-8")
            except OSError as exc:
                preview.issues.append(f"{md}: 读取失败 {exc}")
                continue
            action = _decide_file_action(rel, content, existing)
            kp_ids: list[str] = []
            if sidecar_dir is not None:
                sc = _bundle_sidecar_for(sidecar_dir, rel)
                if sc is not None:
                    for kp in sc.get("knowledge_points") or []:
                        kid = str(kp.get("id") or "")
                        if not kid:
                            continue
                        kp_ids.append(kid)
                        if kid in existing_kp:
                            ex = existing_kp[kid]
                            if not _is_idempotent_kp(ex, rel, action):
                                preview.conflicts.append(
                                    ConflictItem(
                                        kind="kp_id_taken",
                                        subject=kid,
                                        options=["skip", "overwrite", "rename"],
                                        detail=f"库内已有：{ex.get('file')} / {ex.get('name')}",
                                    )
                                )
                        preview.kp.append(
                            PlannedKp(
                                id=kid,
                                name=str(kp.get("name") or kid),
                                tags=kp.get("tags") or [],
                                file=rel,
                                range_missing=not _has_kp_range(kp),
                            )
                        )
            preview.files.append(
                PlannedFile(rel_path=rel, action=action, source=str(md), kp_ids=kp_ids)
            )
    _finalize_summary(preview)
    return preview


def _bundle_sidecar_for(sidecar_dir: Path, rel_path: str) -> dict | None:
    """包内 sidecar 按 md 相对路径镜像映射（与库内约定一致）：
    rel='sub/a.md' → .memoria/sidecars/sub/a.memoria.yaml；
    无镜像时回退包内同层扁平命名（旧包布局）。"""
    rel = str(rel_path or "").replace("\\", "/")
    if not rel:
        return None
    candidates = []
    if rel.endswith(".md"):
        candidates.append(sidecar_dir / (rel[: -3] + SIDECAR_SUFFIX))
        candidates.append(sidecar_dir / (Path(rel).stem + SIDECAR_SUFFIX))
    for cand in candidates:
        if not cand.is_file():
            continue
        try:
            data = yaml.safe_load(cand.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(data, dict):
            return data
    return None


def _has_kp_range(kp: dict) -> bool:
    rng = kp.get("range") or {}
    return bool(rng.get("start") and rng.get("end"))


def _has_ranges(fm: dict) -> bool:
    return bool(fm.get("concepts") is not None) and any(
        isinstance(c, dict) and (c.get("range") or c.get("line_start"))
        for c in (fm.get("concepts") or [])
    )


def _split_frontmatter(content: str) -> tuple[dict, str]:
    text = content.lstrip("\ufeff")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm_text = text[3:end].strip()
            body = text[end + 4 :].lstrip("\n")
            try:
                fm = yaml.safe_load(fm_text)
            except yaml.YAMLError:
                fm = {}
            return (fm if isinstance(fm, dict) else {}), body
    return {}, content


def _finalize_summary(preview: ImportPreview) -> None:
    counts = {"new": 0, "overwrite": 0, "rename": 0, "skip": 0, "unchanged": 0}
    for f in preview.files:
        counts[f.action] = counts.get(f.action, 0) + 1
    # kp_new 只计「会实际写库」的 KP：源文件无变更（unchanged）时不产生任何写
    # 作，其声明 KP 不计入新增，保证幂等重导摘要呈现为 0 变更。
    action_by_file = {f.rel_path: f.action for f in preview.files}
    kp_new = sum(
        1 for k in preview.kp if action_by_file.get(k.file, "") not in ("", "unchanged")
    )
    preview.summary = {
        "files_new": counts["new"],
        "files_overwrite": counts["overwrite"],
        "files_rename": counts["rename"],
        "files_skip": counts["skip"],
        "files_unchanged": counts["unchanged"],
        "kp_new": kp_new,
        "conflicts": len(preview.conflicts),
    }


RESOLVERS = {
    FLAT_FILE: _preview_flat,
    MD_DIR: _preview_md_dir,
    KB_BUNDLE: _preview_kb_bundle,
}


def build_import_preview(kind: str, sources: list[dict], kb_path: str) -> ImportPreview:
    if kind not in RESOLVERS:
        raise ValueError(f"不支持的导入源 kind={kind!r}")
    return RESOLVERS[kind](sources, kb_path)
