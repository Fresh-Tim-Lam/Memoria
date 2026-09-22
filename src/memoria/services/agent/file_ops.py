"""文件级写原语的实现：新建 / 重命名 `.md`（重命名含全库 `[[stem]]` 引用级联）。

设计来源：`docs/design/agent-plugin-design.md §7` 的 2.4（新建 `.md`）与 2.6（重命名 / 移动）。
两条纪律：

1. **预演与落地用同一批原子函数**：`rename_plan()` 只读地算出"这次重命名会牵动哪些文件"，
   用的是被包装的 `DocumentService.rename_file()` 自己那套（`build_kp_index()` /
   `replace_link_id_in_markdown()` / `migrate_sidecar_kp_refs()`）⇒ 预演不可能与落地漂移，
   而且这份清单就是 apply 的 **pre-image 备份集**（撤销要能把这些文件逐一还原）。
2. **落盘只经服务层**：`apply_create_file()` / `apply_rename_file()` 只做薄包装，
   不自己 `open(..., "w")`。

**"删除整文件"（§7 的 2.5 / `kb.file.delete`）2026-09-22 起提供**，口径见 `delete_plan()`：正文里
还写着 `[[它]]` 的**别的**文档会被**硬拦**（删了就是悬空引用，要先在同一批里摘掉引用再删）；侧车里还挂着
指向它的链接/边只**警告**。删除**不可恢复**，故它是**风险 op**（逐条确认），但仍**可整批撤销**。
"""

from __future__ import annotations

import os
import re
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


# ── 删除整篇 `.md`（§7 的 2.5）：**2026-09-22 新增** ─────────────────────────────────────────
# 与 `rename_plan()` 同一套纪律：**预演与落地不漂移** —— 预演算出的"哪些引用会失去落点"就是校验期
# 拦人的依据；`apply_delete_file()` 仍是薄包装服务入口，不自己 `os.remove`。
#
# 为什么删除需要预演（而不是直接删）：wikilink 是**隐式**引用 —— 正文里一句 `[[名字]]` 在删除之前
# 完全合法，删除之后就成了悬空指向。人的 UI 上"删文件"是显式动作、后果自负；agent 是**无人值守**地
# 连提几批，必须先把这类后果算出来、列为**硬拦**，否则它会一边报"已写入"一边把全库引用打断。


def delete_plan(kb_path: str, rel: str) -> dict:
    """删除整篇 `.md` 的**只读预演**：能不能删、删了会让哪些引用失去落点。**零落盘**。

    返回 `{ok, code?, message?, rel, stem, ids[], referrers_md[], referrers_sidecar[], affected[]}`：

    - `ids` = 这次删除会让**指向它的 wikilink 失去落点**的那些 id：文件 stem（`[[文件名]]`）加上
      **它自己的侧车里定义的知识点 id**（`[[kp_id]]`）—— 除非该 id 在**别的文件**里还有一处定义
      （那就仍解析得到，不算失去落点）。
    - `referrers_md` = 正文里仍写着这些 `[[id]]` 的**其它**文档 ⇒ 调用方据此**硬拦**。
    - `referrers_sidecar` = 侧车里仍挂着指向这些 id 的链接 / 边的**其它**文档 ⇒ 只**警告**
      （那是派生数据，`validate_kb()` 会报出来；清理手段与正文引用不同）。
    - `affected` = 该事务必须**备份**的路径：被删的正文 + 它自己的侧车（**两者都会被删掉**，
      撤销要靠 pre-image 把它们写回来）。注意**正文引用者不在此列** —— 删除不会改写它们，
      它们只是"失去一个可解析目标"，没有字节变化。
    """
    # 局部导入：不动文件顶部（既有行号锚点零漂移）
    from memoria.storage.sidecar import sidecar_path_for

    rel_norm = str(rel or "").strip().replace("\\", "/")
    full = os.path.join(kb_path, rel_norm)
    if not rel_norm or not os.path.isfile(full):
        return {"ok": False, "code": "file_not_found", "message": f"文件不存在：{rel_norm}"}

    stem = os.path.splitext(os.path.basename(rel_norm))[0]
    index = build_kp_index(kb_path)
    own_ids = {
        str(entry.kp_id) for entry in index["entries"] if str(entry.file) == rel_norm and entry.kp_id
    }
    # `[[id]]` 的解析顺序里 KP id **遮蔽**同名文件 stem ⇒ 只有"全库再也没有第二处定义"的 id 才会因
    # 这次删除失去落点（与 `rename_plan()` 的 `kp_shadow` 同源，只是判据换成"别处还有没有"）。
    ids = sorted(
        target
        for target in ({stem} | own_ids)
        if not any(str(entry.file) != rel_norm for entry in (index["by_id"].get(target) or []))
    )

    #: 探测哨兵：`replace_link_id_in_markdown()` 在 old == new 时**短路返回 0** ⇒ 必须换一个不可能
    #: 撞上的名字才数得出引用（替换出来的文本直接丢掉）。
    probe = "\x00memoria-delete-probe"
    referrers_md: list[str] = []
    referrers_sidecar: list[str] = []
    for other in collect_md_files(kb_path):
        other_norm = other.replace("\\", "/")
        if other_norm == rel_norm:
            continue
        other_full = os.path.join(kb_path, other)
        with open(other_full, "r", encoding="utf-8") as handle:
            body, _fm = strip_frontmatter(handle.read())
        if any(replace_link_id_in_markdown(body, target, probe)[1] for target in ids):
            referrers_md.append(other_norm)
        sidecar = load_sidecar_for_md(other_full, kb_path)
        if (
            isinstance(sidecar, Mapping)
            and sidecar
            and any(migrate_sidecar_kp_refs(dict(sidecar), target, probe) for target in ids)
        ):
            referrers_sidecar.append(other_norm)

    sidecar_rel = os.path.relpath(sidecar_path_for(full, kb_path), kb_path).replace("\\", "/")
    return {
        "ok": True,
        "rel": rel_norm,
        "stem": stem,
        "ids": ids,
        "referrers_md": sorted(set(referrers_md)),
        "referrers_sidecar": sorted(set(referrers_sidecar)),
        "affected": sorted({rel_norm, sidecar_rel}),
    }


def apply_delete_file(service: Any, rel_path: str) -> dict:
    """删除整篇 `.md` 及其侧车 —— 薄包装 `DocumentService.delete_file()`（不自己 `os.remove`）。"""
    result = service.delete_file(rel_path)
    if isinstance(result, Mapping) and result.get("status") == "ok":
        return {"status": "ok", "rel_path": str(rel_path), "deleted": True}
    return {
        "status": "error",
        "code": "delete_failed",
        "message": str((result or {}).get("message") or "删除失败"),
    }


# ── 移动整篇 `.md` 到另一目录（§7 的 2.6 后半 / `kb.file.move`）：**2026-09-22 新增** ──────────
# **为什么现在能做**（推翻了之前"按 §6 R2 不做"的判定 —— 见 design §6.23）：Memoria 的寻址是
# **id / stem 寻址**（`[[id]]`），移动只改目录、不改 stem ⇒ 引用天然不断；图片引用按规范又是
# **库根相对**（`.memoria/images/x.png`）⇒ 同样不受影响。R2 真正管的是**"文件相对"写法**
# （`![x](img/a.png)`、`[y](../b.md)`）—— 那部分仍未落地 ⇒ 本模块**不猜**：`move_plan()` 在写前把
# 它**拦下来**（`move_breaks_relative_refs`），落盘只走 `document.move_file_document()`。
#
# 与 `rename_file` 的分工：`rename_file` 只改**文件名**（保持目录，并级联改写全库 `[[旧stem]]`）；
# `move_file` 只改**所在目录**（保持文件名，**不**改写任何正文）。

#: markdown 链接/图片的目标：`[text](target)` / `![alt](target)`（含 `<…>` 包裹写法）。
_MD_TARGET_RE = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)>\s]+)>?")


def _file_relative_refs(kb_path: str, rel: str) -> list[str]:
    """正文里**按文件所在目录**才能解析到的链接/图片目标（移动会打断它们）。**只读**。

    不算"文件相对"的四种写法：`#锚点`、带 scheme（`http:`/`data:`…）、`//` 协议相对、`/` 开头（库根绝对）。
    其余按**两种口径各试一次**：

    1. 按**库根**解析能读到 ⇒ 这是库内的**根相对**写法（Memoria 图片引用的规范形态）⇒ 不算；
    2. 否则按**文件所在目录**解析能读到 ⇒ 这是**文件相对**写法 ⇒ **算**（移动必断；§6 R2 未落地）；
    3. 两边都读不到（本来就是悬空引用）⇒ 不算（移动不会让它更坏），也不报。
    """
    full = os.path.join(kb_path, rel)
    try:
        with open(full, "r", encoding="utf-8") as handle:
            body, _fm = strip_frontmatter(handle.read())
    except OSError:
        return []
    base_dir = os.path.dirname(full)
    found: list[str] = []
    for target in _MD_TARGET_RE.findall(body):
        raw = str(target or "").strip()
        if not raw or raw.startswith(("#", "/", "//")) or ":" in raw.split("/")[0]:
            continue  # 锚点 / 库根绝对 / 协议相对 / 带 scheme ⇒ 与位置无关
        path_part = raw.split("#", 1)[0]
        if not path_part:
            continue
        if os.path.isfile(os.path.join(kb_path, *path_part.split("/"))):
            continue  # ① 库根相对（含 `.memoria/images/...` 这类规范写法）
        if os.path.isfile(os.path.join(base_dir, *path_part.split("/"))):
            found.append(raw)  # ② 文件相对 ⇒ 移动会打断
    return found


def normalize_target_dir(raw: Any) -> str:
    """把"目标目录"归一成**库内相对目录**（`""` = **库根**）。

    **空串 / `.` / `./` / 反斜杠写法 一律是库根** —— 这三种写法此前有三条不同下场（2026-09-22 真机取证，
    `docs/example/AAA_Vocab` 会话 23:08）：
    - `to_dir=""` ⇒ 计划期就被 `_safe_rel_dir()` 判 `path_rejected`（它内部 `_safe_rel_any()` 把空串
      当越界）—— 而**工具说明明写"空串 = 库根"** ⇒ 描述与行为自相矛盾；
    - `to_dir="."` ⇒ 计划期放行，**落地期**却被 `move_file_document()` 的"点开头 = 系统/隐藏目录"
      拒掉（`不能移动到系统/隐藏目录`）⇒ 同一件事两处口径不一致；
    - 模型最后只能拿 `tmp-move/` 当中转绕路（`vocab/x.md → tmp-move` 再 `tmp-move/x.md → vocab`）。

    归一化**收口在这一个函数**里，`move_plan()`（计划期）与 `apply_move_file()`（落地期）都调它
    ⇒ 两侧不可能再漂移。注意它**不代替**越界校验：归一后非空的值仍要过 `_safe_rel_dir()`。
    """
    text = str(raw or "").strip().replace("\\", "/").strip("/")
    return "" if text in ("", ".") else text


def move_plan(kb_path: str, rel: str, to_dir: str) -> dict:
    """移动的**只读预演**：能不能移、移了会牵动哪些文件。**零落盘**。

    返回 `{ok, code?, message?, from, to, blockers[], affected[]}`：

    - `blockers` = 正文里的**文件相对引用**（移动会打断它们，见 `_file_relative_refs()`）；
    - `affected` = 该事务必须**备份**的路径：源正文 + 目标正文 + 两侧的镜像侧车（+ 源文件的
      旧版同目录侧车，若存在）—— 移动＝"旧路径消失 + 新路径出现"，撤销要两边都能还原。
    """
    # 与 plan 校验**同一套路径闸**（不另写宽松判断）；局部导入不动文件顶部（既有行号锚点零漂移）
    from memoria.services.agent.tools.kb import _safe_rel, _safe_rel_dir
    from memoria.storage.sidecar import legacy_sidecar_path_for, sidecar_path_for

    rel_norm = _safe_rel(kb_path, rel)
    if rel_norm is None:
        return {"ok": False, "code": "path_rejected", "message": f"file 不在允许根内或不是 .md：{rel!r}"}
    full = os.path.join(kb_path, rel_norm)
    if not os.path.isfile(full):
        return {"ok": False, "code": "file_not_found", "message": f"文件不存在：{rel_norm}"}
    # 先把"库根"的三种写法归一，**再**做越界校验（空 ⇒ 库根，不必也不该过 `_safe_rel_dir()`）
    normalized = normalize_target_dir(to_dir)
    if normalized.startswith("."):
        # 与 `document.move_file_document()` 的「不能移动到系统/隐藏目录」**同一条规矩**（点开头）。
        # 挡在**计划期**：此前只有落地期那道检查，模型要等整批回滚才知道（真机里就是这么撞的）。
        return {"ok": False, "code": "path_rejected", "message": f"不能移动到系统/隐藏目录：{to_dir!r}"}
    target_dir = ""
    if normalized:
        checked_dir = _safe_rel_dir(kb_path, normalized)
        if checked_dir is None:
            return {"ok": False, "code": "path_rejected", "message": f"to_dir 不在允许根内或非法：{to_dir!r}"}
        target_dir = checked_dir
    parent = rel_norm.rsplit("/", 1)[0] if "/" in rel_norm else ""
    if target_dir == parent:
        return {
            "ok": False,
            "code": "same_dir",
            "message": "目标目录与当前目录相同（只想改文件名请用 `rename_file`）",
        }
    name = os.path.basename(rel_norm)
    new_rel = f"{target_dir}/{name}" if target_dir else name
    if os.path.exists(os.path.join(kb_path, new_rel)):
        return {"ok": False, "code": "target_exists", "message": f"目标已存在：{new_rel}"}
    blockers = _file_relative_refs(kb_path, rel_norm)
    if blockers:
        shown = "、".join(f"`{item}`" for item in blockers[:5])
        return {
            "ok": False,
            "code": "move_breaks_relative_refs",
            "message": (
                f"这篇文档里有**文件相对**的链接/图片（{shown}）—— 它们按文件所在目录解析，"
                "移动之后就断了。请先把这些引用改成**库根相对**（如 `.memoria/images/x.png`）"
                "或换成 `[[id]]`，再移动。"
            ),
            "blockers": blockers,
        }

    def _sc_rel(path: str) -> str:
        return os.path.relpath(path, kb_path).replace("\\", "/")

    affected = {rel_norm, new_rel, _sc_rel(sidecar_path_for(full, kb_path))}
    affected.add(_sc_rel(sidecar_path_for(os.path.join(kb_path, new_rel), kb_path)))
    legacy = legacy_sidecar_path_for(full)
    if os.path.isfile(legacy):
        affected.add(_sc_rel(legacy))
    return {
        "ok": True,
        "from": rel_norm,
        "to": new_rel,
        "to_dir": target_dir,
        "blockers": [],
        "affected": sorted(affected),
    }


def apply_move_file(service: Any, rel_path: str, to_dir: str) -> dict:
    """移动整篇 `.md` 到库内另一目录（保持文件名）—— 薄包装 `document.move_file_document()`。

    **落地前先归一 `to_dir`**（与 `move_plan()` 同一个 `normalize_target_dir()`）⇒ 计划期放行的写法，
    落地期必然也放行；尤其 `"."` / `""` 走到 `move_file_document()` 前已变成 `""`，不会再被它的
    "点开头 = 系统/隐藏目录"误伤（真机里模型正是撞在这条上）。
    """
    from memoria.services.document import move_file_document

    result = move_file_document(service, rel_path, normalize_target_dir(to_dir))
    if isinstance(result, Mapping) and result.get("status") == "ok":
        return {"status": "ok", "rel_path": str(result.get("path") or ""), "moved": True}
    return {
        "status": "error",
        "code": "move_failed",
        "message": str((result or {}).get("message") or "移动失败"),
    }


# ── 删 KP 前的悬空预警（2026-09-22 追加；§7 的 1.7 `kb.kp.delete`）──────────────────────────────
# 整段追加在文件末尾 ⇒ 上方所有 `<文件>:<行号>` 锚点零漂移。
#
# 为什么不复用 `delete_plan()` 的扫描：那一份是**按"整篇消失会让哪些 id 失去落点"**算的（文件 stem +
# 该文件定义的全部 KP），而这里只需要问"还有谁指向**这一个** kp_id"，口径不同（也少一层"别的文件还有
# 同一处定义就不再算失去落点"的判断）。故单独写一个小函数，用**同一批原子函数**
# （`replace_link_id_in_markdown` / `migrate_sidecar_kp_refs`）做探针 ⇒ 与落地路径同一套判据。


def kp_referrers(kb_path: str, kp_id: str, *, owner: str = "") -> dict[str, list[str]]:
    """只读扫描：全库**正文**与**侧车**里仍指向 `kp_id` 的文档（删 KP 前的悬空预警）。**零落盘**。

    返回 `{"md": [...], "sidecar": [...]}`：

    - `md` 含定义该 KP 的那一篇（它自己的正文也可能写着 `[[id]]`）；
    - `sidecar` **不含** `owner`（= 定义该 KP 的那篇）—— 它侧车里的那条 `knowledge_points[]` 正是
      **要删的东西本身**，算进来只会制造噪音。
    """
    wanted = str(kp_id or "").strip()
    if not wanted:
        return {"md": [], "sidecar": []}
    # 探针：`replace_link_id_in_markdown()` 在 old == new 时**短路返回 0**，故用一个不可能撞上的名字
    probe = "\x00memoria-kp-ref-probe"
    owner_norm = str(owner or "").strip().replace("\\", "/")
    md_hits: list[str] = []
    sidecar_hits: list[str] = []
    for rel in collect_md_files(kb_path):
        rel_norm = rel.replace("\\", "/")
        full = os.path.join(kb_path, rel)
        try:
            with open(full, "r", encoding="utf-8") as handle:
                body, _fm = strip_frontmatter(handle.read())
        except OSError:
            continue
        if replace_link_id_in_markdown(body, wanted, probe)[1]:
            md_hits.append(rel_norm)
        if rel_norm == owner_norm:
            continue
        sidecar = load_sidecar_for_md(full, kb_path)
        if isinstance(sidecar, Mapping) and sidecar and migrate_sidecar_kp_refs(dict(sidecar), wanted, probe):
            sidecar_hits.append(rel_norm)
    return {"md": sorted(set(md_hits)), "sidecar": sorted(set(sidecar_hits))}
