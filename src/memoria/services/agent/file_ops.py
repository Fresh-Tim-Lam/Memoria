"""文件级写原语的实现：新建 / 重命名 `.md`（重命名含全库 `[[stem]]` 引用级联）。

设计来源：`docs/design/agent-plugin-design.md §7` 的 2.4（新建 `.md`）与 2.6（重命名 / 移动）。
两条纪律：

1. **预演与落地用同一批原子函数**：`rename_plan()` 只读地算出"这次重命名会牵动哪些文件"，
   用的是被包装的 `DocumentService.rename_file()` 自己那套（`build_kp_index()` /
   `replace_link_id_in_markdown()` / `migrate_sidecar_kp_refs()`）⇒ 预演不可能与落地漂移，
   而且这份清单就是 apply 的 **pre-image 备份集**（撤销要能把这些文件逐一还原）。
2. **落盘只经服务层**：`apply_create_file()` / `apply_rename_file()` 只做薄包装，
   不自己 `open(..., "w")`。

**为什么"删除整文件"（§7 的 2.5 / `kb.file.delete`）本轮不做**：设计 §2.6 的写原语目录把它标成
**默认关**（"开关属 §2.1 暂缓的 `config` 参数面"），§7 2.5 也写明"建议不设 `auto`"。在权限档
（§4 Q7）与 `config` 面定案之前，agent 侧**不暴露**删除 op —— 删除不可恢复，宁可先不给。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from memoria.services.kp_index import build_kp_index
from memoria.services.kp_rename import migrate_sidecar_kp_refs, replace_link_id_in_markdown
from memoria.storage.markdown import strip_frontmatter
from memoria.storage.scanner import collect_md_files
from memoria.storage.sidecar import load_sidecar_for_md


def normalize_new_name(new_name: str) -> str | None:
    """与 `rename_file()` 同口径的"新文件名"（只允许文件名、保持所在目录）；非法回 `None`。"""
    name = (new_name or "").strip().replace("\\", "/").strip("/")
    if not name or name in (".", "..") or "/" in name:
        return None
    if not name.lower().endswith(".md"):
        name += ".md"
    return name


def rename_plan(kb_path: str, old_rel: str, new_name: str) -> dict:
    """重命名的**只读预演**：会不会被拒、会牵动哪些文件。**零落盘**。

    返回 `{ok, code?, message?, from, to, kp_shadow, md_files[], sidecar_files[], affected[]}`；
    `affected` = 该事务必须**备份**的路径（旧文件、新文件、被改写的正文与侧车）。
    """
    name = normalize_new_name(new_name)
    if name is None:
        return {"ok": False, "code": "bad_field", "message": "new_name 非法（只能是文件名，可省 .md 后缀）"}
    parent = old_rel.rsplit("/", 1)[0] if "/" in old_rel else ""
    new_rel = f"{parent}/{name}" if parent else name
    if new_rel == old_rel:
        return {"ok": False, "code": "bad_field", "message": "new_name 与原名相同（没有变化）"}
    if os.path.exists(os.path.join(kb_path, new_rel)):
        return {"ok": False, "code": "target_exists", "message": f"目标已存在：{new_rel}"}
    old_stem = os.path.splitext(os.path.basename(old_rel))[0]
    new_stem = os.path.splitext(os.path.basename(name))[0]
    index = build_kp_index(kb_path)
    other = index["file_stems"].get(new_stem)
    if other and other != old_rel:
        return {"ok": False, "code": "stem_conflict", "message": f"新文件名 id『{new_stem}』已被 {other} 占用"}
    # 旧 stem 被某 KP id 遮蔽时，`[[oldStem]]` 解析到知识点而非文件 ⇒ 引用不必改写（同服务层判定）
    kp_shadow = bool(index["by_id"].get(old_stem))
    md_files: list[str] = []
    sidecar_files: list[str] = []
    for rel in collect_md_files(kb_path):
        rel_norm = rel.replace("\\", "/")
        full = os.path.join(kb_path, rel)
        if not kp_shadow:
            with open(full, "r", encoding="utf-8") as handle:
                body, _fm = strip_frontmatter(handle.read())
            _new_body, count = replace_link_id_in_markdown(body, old_stem, new_stem)
            if count:
                md_files.append(rel_norm)
        sidecar = load_sidecar_for_md(full, kb_path)
        if isinstance(sidecar, Mapping) and sidecar:
            changed = 0 if kp_shadow else migrate_sidecar_kp_refs(dict(sidecar), old_stem, new_stem)
            if rel_norm == new_rel and str(sidecar.get("file") or "") != new_rel:
                changed += 1
            if changed:
                sidecar_files.append(rel_norm)
    affected = sorted({old_rel, new_rel, *md_files, *sidecar_files})
    return {
        "ok": True,
        "from": old_rel,
        "to": new_rel,
        "kp_shadow": kp_shadow,
        "md_files": sorted(set(md_files)),
        "sidecar_files": sorted(set(sidecar_files)),
        "affected": affected,
    }


# ── 图片引用行（§7 的 4.1）：**只写正文那一行**，图片入库不归这里 ─────────────────────────
# 语法权威是 `docs/reference/preview-formats.md` §4.2/§4.3（人 UI 的 `image-tools.js` 是既有实现）：
# 路径 = **知识库根相对**（推荐 `.memoria/images/x.png`）；含空格/中文用尖括号 `<…>` 包；
# 显示属性写在 **title 位**：`![alt](url "width=300,align=center")`。
# 本函数只**拼这一行**，然后把行交给 `body_edit` 的 `insert`（行级原语）落地 ⇒ 备份/回滚/审计/
# 撤销/预览全部沿用。
#
# **本轮不做**（如实登记）：① **图片入库**（`import_image` 有"目标文件名要先去重才知道"的时序问题，
# 备份集在写前拿不到目标名 ⇒ 需要一个设计决定，先不开）；② **改 alt / 属性**（属性语法权威在人 UI，
# 后端没有同一份实现，重写一份会漂移）；③ **移动 / 删除图片**（§7 4.5/4.6 属后线、删除类默认关）。

#: 允许作为图片引用的扩展名（与 `DocumentService._IMAGE_EXTENSIONS` 同一集合，**不另写一份**）
IMAGE_EXTENSIONS: frozenset[str] = frozenset((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico"))


def image_ref_line(kb_path: str, path: str, alt: str = "", attrs: str = "") -> str:
    """拼一行图片引用（`![alt](<路径> "属性")`）；路径非法/文件不存在即抛 `EditError`。"""
    from memoria.services.agent.body_edit import EditError

    raw = (path or "").strip().replace("\\", "/")
    if not raw:
        raise EditError("missing_field", "缺 path（库内相对图片路径）")
    if raw.startswith("/") or ".." in raw.split("/"):
        raise EditError("path_rejected", f"图片路径必须是**库内相对**路径（不许绝对路径或 ..）：{path!r}")
    if os.path.splitext(raw)[1].lower() not in IMAGE_EXTENSIONS:
        raise EditError("bad_field", f"不是图片扩展名（允许 {sorted(IMAGE_EXTENSIONS)}）：{raw!r}")
    if not os.path.isfile(os.path.join(kb_path, raw)):
        raise EditError("image_not_found", f"库内找不到这张图片：{raw}")
    target = f"<{raw}>" if (" " in raw or any(ord(ch) > 127 for ch in raw)) else raw
    title = f' "{str(attrs).strip()}"' if str(attrs or "").strip() else ""
    return f"![{str(alt or '').strip()}]({target}{title})"


def apply_create_file(service: Any, rel_path: str, body: str = "") -> dict:
    """新建 `.md`（父目录自动建、缺 `.md` 后缀自动补）—— 薄包装 `DocumentService.create_file()`。"""
    result = service.create_file(rel_path, body or "")
    if isinstance(result, Mapping) and result.get("status") == "ok":
        return {"status": "ok", "rel_path": str(result.get("path") or rel_path), "created": True}
    return {
        "status": "error",
        "code": "create_failed",
        "message": str((result or {}).get("message") or "新建文件失败"),
    }


def apply_rename_file(service: Any, rel_path: str, new_name: str) -> dict:
    """重命名 `.md`（含侧车 / manifest / pending / 图片注册表 / 全库引用级联）—— 薄包装服务入口。"""
    result = service.rename_file(rel_path, new_name)
    if isinstance(result, Mapping) and result.get("status") == "ok":
        return {"status": "ok", "rel_path": str(result.get("path") or ""), "renamed": True}
    return {
        "status": "error",
        "code": "rename_failed",
        "message": str((result or {}).get("message") or "重命名失败"),
    }
