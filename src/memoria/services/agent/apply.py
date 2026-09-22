# 设计来源（权威）：`docs/design/agent-capabilities.md` §2.3.1（唯一写者 / 原语）、
# §2.3.2（备份与调用序）、§2.3.3（计划 API 与编译器）、§2.3.4（同一套校验器）。

"""写模块的 **apply 入口**（第二片 ②）：把声明式 plan 编成原语调用序列并执行。

**这是 agent 写路径上唯一能到达四个写原语的通道**（§2.3.1「原语的调用者唯一 = apply 入口」）。
调用序严格照 §2.3.2 第 4 条：

```
1. validate_plan()            ← 有错即拒整批（此时**尚未建任何备份**）
2. snapshot_pre_images(tx)    ← 写前 pre-image；失败 ⇒ 直接返回，**零写入**
3. 依次执行原语（下表）；任一步失败 ⇒ 用该批次 pre-image **整批回滚** + 返回 error
4. record_post_images(tx)     ← 撤销用的"写后哈希"
5. trim_backups()             ← 机会式清理（不进读热路径）
```

**原语白名单**（`PRIMITIVES`，逐条映射 §2.3.3 表的"编译到 · 唯一实现"列）：

| op | 原语（`DocumentService` 方法） |
|---|---|
| `upsert_kp` | `confirm_kp_range()`；带 `tags` / `description` / `aliases` 时再跟一条 `update_kp()` |
| `attach_links` | `apply_link_instances()` |
| `detach_links` | `mode="detach"` ⇒ 每行一条 `detach_link_instance()`；`mode="remove_route"` ⇒ `delete_link_route()` |

**本片不做**（留给第二片 ③④，如实登记）：`capability/apply` / `capability/backup` 事件与审计、
`approval` 逐条确认、RPC 暴露与前端确认卡。**撤销**（`restore_batch`）已由备份子系统提供，
其"审批 + 审计"仍属 ③；本模块只在**失败回滚**这一处调用它（`allow_unverified=True`，
理由见下）。
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any, Callable

from memoria.services.agent import audit, backup
from memoria.services.agent.plan import (
    BODY_EDIT_OPS,
    OP_ATTACH_LINKS,
    OP_CREATE_FILE,
    OP_DELETE_FILE,
    OP_DELETE_KP,
    OP_DETACH_LINKS,
    OP_MOVE_FILE,
    OP_REBUILD_MANIFEST,
    OP_RENAME_FILE,
    OP_RENAME_KP,
    OP_UPSERT_EDGE,
    OP_UPSERT_KP,
    base_versions as plan_base_versions,
    validate_plan,
)
from memoria.storage.constants import MEMORIA_DIR
from memoria.storage.file_version import rel_version
from memoria.storage.manifest import manifest_path
from memoria.storage.pending import pending_path
from memoria.storage.sidecar import sidecar_path_for


class _ApplyError(RuntimeError):
    """某个原语返回非 ok ⇒ 触发整批回滚。"""

    def __init__(self, call: Mapping, result: Mapping) -> None:
        super().__init__(str(result.get("message") or f"原语执行失败：{call.get('primitive')}"))
        self.call = dict(call)
        self.result = dict(result)


def _rel(kb_path: str, full_path: str) -> str:
    """库内相对路径。两侧都过 `realpath` —— Windows 的 **8.3 短名**（`LAMTIM~1`）、大小写、
    目录联结都会让"短名根 + 长名目标"的 `relpath` 算出 `../../..` 这种越界结果（实测踩过）。"""
    root = os.path.realpath(kb_path)
    return os.path.relpath(os.path.realpath(full_path), root).replace("\\", "/")


def affected_files(kb_path: str, rel_paths: Sequence[str]) -> list[str]:
    """该事务会碰的**全部**落盘目标（§2.3.2 第 1 条）：正文 + 其 sidecar + manifest + pending。

    sidecar 路径走 `sidecar_path_for()`（与存储层同一映射），**不另写一份**。
    """
    root = os.path.realpath(kb_path)
    out: list[str] = []
    for rel in rel_paths:
        text = str(rel or "").strip().replace("\\", "/")
        if not text:
            continue
        out.append(text)
        out.append(_rel(root, sidecar_path_for(os.path.join(root, text), root)))
    out.append(_rel(root, manifest_path(root)))
    out.append(_rel(root, pending_path(root)))
    deduped: list[str] = []
    for item in out:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def _call_confirm_kp_range(service: Any, args: Mapping) -> dict:
    return service.confirm_kp_range(
        args["rel_path"], args["kp_id"], args["name"], args["start_line"], args["end_line"]
    )


def _call_update_kp(service: Any, args: Mapping) -> dict:
    return service.update_kp(
        args["rel_path"],
        args["kp_id"],
        tags=args.get("tags") or None,
        description=args.get("description"),
        aliases=args.get("aliases") or None,
    )


def _call_apply_link_instances(service: Any, args: Mapping) -> dict:
    return service.apply_link_instances(
        args["rel_path"],
        args["anchor_text"],
        list(args["target_ids"]),
        list(args["selected_lines"]),
        display_text=args.get("display_text"),
        edge_type=args.get("edge_type"),
        relevance=args.get("relevance"),
        source_id=args.get("source_id"),
        # 同行多处时**唯一**能指定"包哪一处"的手段（plan 给了 `occurrences[].col` 才有）
        selected_spans=args.get("selected_spans") or None,
    )


def _call_detach_link_instance(service: Any, args: Mapping) -> dict:
    return service.detach_link_instance(args["rel_path"], args["anchor_text"], args["line_number"])


def _call_delete_link_route(service: Any, args: Mapping) -> dict:
    return service.delete_link_route(args["rel_path"], args["anchor_text"], occurrence=args.get("occurrence", 0))


def _call_edit_body(service: Any, args: Mapping) -> dict:
    """原语 `kb.file.edit`（§7 的 2.1/2.2/2.3）：行级改正文，落盘仍走 `save_document()`。"""
    from memoria.services.agent import body_edit

    return body_edit.apply_body_edits(service, args["rel_path"], list(args["edits"]))


def _call_create_file(service: Any, args: Mapping) -> dict:
    """原语 `kb.file.create`（§7 的 2.4）：新建 `.md`（可带初始正文）。"""
    from memoria.services.agent import file_ops

    return file_ops.apply_create_file(service, args["rel_path"], str(args.get("body") or ""))


def _call_rename_file(service: Any, args: Mapping) -> dict:
    """原语 `kb.file.rename`（§7 的 2.6）：重命名 `.md` + 全库 `[[stem]]` 级联。"""
    from memoria.services.agent import file_ops

    return file_ops.apply_rename_file(service, args["rel_path"], str(args["new_name"]))


def _call_delete_file(service: Any, args: Mapping) -> dict:
    """原语 `kb.file.delete`（§7 的 2.5）：删整篇 `.md` + 其侧车。"""
    from memoria.services.agent import file_ops

    return file_ops.apply_delete_file(service, args["rel_path"])


def _call_move_file(service: Any, args: Mapping) -> dict:
    """原语 `kb.file.move`（§7 的 2.6 后半）：把整篇 `.md` 移到另一目录（保持文件名）。"""
    from memoria.services.agent import file_ops

    return file_ops.apply_move_file(service, args["rel_path"], str(args.get("to_dir") or ""))


# ── 2026-09-22 追加：三个 sidecar 结构原语（§7 的 1.2 / 1.7 / 1.8）────────────────────────────
# 薄包装既有服务方法（`DocumentService.create_edge()` / `delete_kp()` / `rename_kp_id()`）——
# 与其它原语同一纪律：**不自己开文件**，落盘一律经服务层（§2.3.1）。


def _call_create_edge(service: Any, args: Mapping) -> dict:
    """原语 `kb.link.create`（§7 的 1.2）：写一条 KP↔KP 的**纯边**（只动 sidecar `edges[]`）。"""
    return service.create_edge(
        args["rel_path"],
        args["source_id"],
        args["target_id"],
        args["edge_type"],
        relevance=args.get("relevance"),
    )


def _call_delete_kp(service: Any, args: Mapping) -> dict:
    """原语 `kb.kp.delete`（§7 的 1.7）：删一个 KP 的 sidecar 配置（**不改正文**）。"""
    return service.delete_kp(args["rel_path"], args["kp_id"])


def _call_rename_kp_id(service: Any, args: Mapping) -> dict:
    """原语 `kb.kp.rename`（§7 的 1.8）：全库改 KP id（正文 wikilink + 各侧车引用**一起**改）。"""
    return service.rename_kp_id(args["old_id"], args["new_id"])


def _call_rebuild_manifest(service: Any, args: Mapping) -> dict:
    """原语 `kb.manifest.rebuild`（§7 的 6.3）：全库重扫磁盘、重写 `.memoria/manifest.yaml`。

    复用 `DocumentService.sync_manifest()` —— 它自带**前置硬闸**（有未修复的路径变更即拒），
    与界面上那个「构建」按钮走**同一份实现**（本地不另写一套重建逻辑）。
    """
    return service.sync_manifest()


#: 原语白名单：**只有**这些方法是 agent 写路径的落点（§2.3.1）
PRIMITIVES: dict[str, Callable[[Any, Mapping], dict]] = {
    "confirm_kp_range": _call_confirm_kp_range,
    "update_kp": _call_update_kp,
    "apply_link_instances": _call_apply_link_instances,
    "detach_link_instance": _call_detach_link_instance,
    "delete_link_route": _call_delete_link_route,
    "edit_body": _call_edit_body,
    "create_file": _call_create_file,
    "rename_file": _call_rename_file,
    "delete_file": _call_delete_file,
    "move_file": _call_move_file,
    "create_edge": _call_create_edge,
    "delete_kp": _call_delete_kp,
    "rename_kp_id": _call_rename_kp_id,
    "rebuild_manifest": _call_rebuild_manifest,
}


def compile_plan(kb_path: str, plan: Any, *, service: Any = None) -> dict:
    """校验 + 编译：`plan` → **原语调用序列**（有序）+ 受影响文件集。**不落盘**。"""
    checked = validate_plan(kb_path, plan, service=service)
    if checked["status"] != "ok":
        return {
            "status": "error",
            "code": "invalid_plan",
            "errors": checked.get("errors", []),
            "warnings": checked.get("warnings", []),
            "calls": [],
            "files": [],
        }
    calls: list[dict] = []
    #: 改正文的 op **一 op 一次** `edit_body`，且**就排在它本来的位置**上 —— 与校验期 `_View`
    #: 的推进顺序逐条对齐：每条编辑面对的都是"前序 op 落地之后"的盘上正文（`body_edit.splice()`
    #: 每次现读盘）。旧实现把同文件的编辑攒到末尾合成一次（当时规定"锚定 op 必须在改正文之前"），
    #: 那条规矩已随"写机制全线放开"删除。
    for parsed in checked["ops"]:
        verb = str(parsed.get("op") or "")
        op_id = str(parsed.get("op_id") or "")
        rel = str(parsed.get("file") or "")
        if verb == OP_UPSERT_KP:
            resolved = parsed.get("resolved") or {}
            start, end = resolved.get("start_line"), resolved.get("end_line")
            if not start or not end:
                return {
                    "status": "error",
                    "code": "compile_failed",
                    "message": f"{op_id}：range 未解析出具体行（{resolved}）",
                    "calls": [],
                    "files": [],
                }
            calls.append(
                {
                    "op_id": op_id,
                    "op": verb,
                    "primitive": "confirm_kp_range",
                    "args": {
                        "rel_path": rel,
                        "kp_id": parsed.get("kp_id"),
                        "name": parsed.get("name"),
                        "start_line": start,
                        "end_line": end,
                    },
                }
            )
            extras = {
                key: parsed.get(key)
                for key in ("tags", "description", "aliases")
                if parsed.get(key)
            }
            if extras:
                calls.append(
                    {
                        "op_id": op_id,
                        "op": verb,
                        "primitive": "update_kp",
                        "args": {"rel_path": rel, "kp_id": parsed.get("kp_id"), **extras},
                    }
                )
        elif verb == OP_ATTACH_LINKS:
            calls.append(
                {
                    "op_id": op_id,
                    "op": verb,
                    "primitive": "apply_link_instances",
                    "args": {
                        "rel_path": rel,
                        "anchor_text": parsed.get("anchor_text"),
                        "target_ids": parsed.get("targets") or [],
                        "selected_lines": parsed.get("lines") or [],
                        "selected_spans": parsed.get("pinned_spans") or None,
                        "display_text": parsed.get("display_text"),
                        "edge_type": parsed.get("edge_type"),
                        "relevance": parsed.get("relevance"),
                        "source_id": parsed.get("source_id"),
                    },
                }
            )
        elif verb == OP_DETACH_LINKS:
            raw_op = _raw_op(plan, op_id)
            mode = str((raw_op or {}).get("mode") or "detach")
            if mode == "remove_route":
                calls.append(
                    {
                        "op_id": op_id,
                        "op": verb,
                        "primitive": "delete_link_route",
                        "args": {
                            "rel_path": rel,
                            "anchor_text": parsed.get("anchor_text"),
                            "occurrence": int((raw_op or {}).get("occurrence") or 0),
                        },
                    }
                )
            else:
                for line in parsed.get("lines") or []:
                    calls.append(
                        {
                            "op_id": op_id,
                            "op": verb,
                            "primitive": "detach_link_instance",
                            "args": {"rel_path": rel, "anchor_text": parsed.get("anchor_text"), "line_number": int(line)},
                        }
                    )
        elif verb in BODY_EDIT_OPS:
            if isinstance(parsed.get("edit"), Mapping):
                calls.append(
                    {
                        "op_id": op_id,
                        "op": verb,
                        "primitive": "edit_body",
                        "args": {"rel_path": rel, "edits": [dict(parsed["edit"])]},
                    }
                )
        elif verb == OP_CREATE_FILE:
            raw_op = _raw_op(plan, op_id) or {}
            calls.append(
                {
                    "op_id": op_id,
                    "op": verb,
                    "primitive": "create_file",
                    "args": {"rel_path": rel, "body": str(raw_op.get("body") or "")},
                }
            )
        elif verb == OP_RENAME_FILE:
            resolved = parsed.get("resolved") or {}
            # 备份集必须**含级联牵动的全部文件**：否则整批回滚/撤销无法把它们逐一还原。
            # 另加图片注册表（`_update_registry_for_doc()` 会碰它；存在才加，避免无谓备份）。
            extra = [str(item) for item in (resolved.get("affected") or [])]
            registry = os.path.join(kb_path, MEMORIA_DIR, "images", "registry.json")
            if os.path.isfile(registry):
                extra.append(_rel(kb_path, registry))
            calls.append(
                {
                    "op_id": op_id,
                    "op": verb,
                    "primitive": "rename_file",
                    "args": {
                        "rel_path": rel,
                        "new_name": str((_raw_op(plan, op_id) or {}).get("new_name") or ""),
                        "affected": extra,
                    },
                }
            )
        elif verb == OP_DELETE_FILE:
            resolved = parsed.get("resolved") or {}
            # 备份集必须**含被删正文自己的侧车**（它随文件一起消失，撤销要靠 pre-image 写回来）。
            # 引用它的正文**不在**备份集里 —— 删除不改写它们，只是让它们失去落点。
            calls.append(
                {
                    "op_id": op_id,
                    "op": verb,
                    "primitive": "delete_file",
                    "args": {
                        "rel_path": rel,
                        "affected": [str(item) for item in (resolved.get("affected") or [])],
                    },
                }
            )
        elif verb == OP_MOVE_FILE:
            resolved = parsed.get("resolved") or {}
            # 备份集必须**含源与目标两侧**（源正文+侧车会消失、目标正文+侧车会出现）⇒ 否则撤销不完备
            calls.append(
                {
                    "op_id": op_id,
                    "op": verb,
                    "primitive": "move_file",
                    "args": {
                        "rel_path": rel,
                        "to_dir": str((_raw_op(plan, op_id) or {}).get("to_dir") or ""),
                        "affected": [str(item) for item in (resolved.get("affected") or [])],
                    },
                }
            )
        elif verb == OP_UPSERT_EDGE:
            resolved = parsed.get("resolved") or {}
            calls.append(
                {
                    "op_id": op_id,
                    "op": verb,
                    "primitive": "create_edge",
                    "args": {
                        "rel_path": rel,
                        "source_id": resolved.get("source_id"),
                        "target_id": resolved.get("target_id"),
                        "edge_type": resolved.get("edge_type"),
                        "relevance": (_raw_op(plan, op_id) or {}).get("relevance"),
                    },
                }
            )
        elif verb == OP_DELETE_KP:
            resolved = parsed.get("resolved") or {}
            # 备份集 = 这篇正文 + 它的侧车（KP 配置就在侧车里）⇒ `rel_path` 已能让 `affected_files()` 带出侧车
            calls.append(
                {
                    "op_id": op_id,
                    "op": verb,
                    "primitive": "delete_kp",
                    "args": {"rel_path": rel, "kp_id": resolved.get("kp_id")},
                }
            )
        elif verb == OP_RENAME_KP:
            resolved = parsed.get("resolved") or {}
            # **没有 `rel_path`**（全库级联）⇒ 备份集只能靠 `affected` 自报：`_validate_rename_kp()`
            # 用 `dry_run=True` 走**同一份** `rename_kp_in_kb()` 算出"会改哪些文件"，那份清单就是
            # apply 的 pre-image 备份集（正文 + 各侧车都要能逐篇还原）。
            calls.append(
                {
                    "op_id": op_id,
                    "op": verb,
                    "primitive": "rename_kp_id",
                    "args": {
                        "old_id": resolved.get("old_id"),
                        "new_id": resolved.get("new_id"),
                        "affected": [str(item) for item in (resolved.get("affected") or [])],
                    },
                }
            )
        elif verb == OP_REBUILD_MANIFEST:
            # 整库一件事：**没有 `rel_path`**（也不需要自报 `affected` —— `affected_files()` 无论
            # 有没有 `rel_path` 都会带上 manifest + pending，pre-image 因此完备）
            calls.append({"op_id": op_id, "op": verb, "primitive": "rebuild_manifest", "args": {}})
    rels: list[str] = []
    for call in calls:
        rels.append(str(call["args"].get("rel_path") or ""))
        # `rename_file` 的备份集：级联牵动的正文/侧车也必须在列（否则撤销不完整）
        rels.extend(str(item) for item in (call["args"].get("affected") or []))
    # 记下**校验时**每个受影响正文的版本：apply 之前再比一次 ⇒ "校验与落地之间被人改过"就整批拒
    # （§9 口径：盘上版本权威、不许基于过期版本写）。侧车/manifest/pending 由原语内部读写，
    # 它们的版本基准不适用同一套语义，故这里只钉正文。
    base_versions = plan_base_versions(kb_path, [r for r in rels if r])
    return {
        "status": "ok",
        "txid": checked.get("txid"),
        "intent": checked.get("intent"),
        "calls": calls,
        "files": affected_files(kb_path, rels),
        "base_versions": base_versions,
        "warnings": checked.get("warnings", []),
    }


def _raw_op(plan: Any, op_id: str) -> dict | None:
    if not isinstance(plan, Mapping):
        return None
    for op in plan.get("ops") or []:
        if isinstance(op, Mapping) and str(op.get("op_id") or "") == op_id:
            return dict(op)
    return None


def _stale_error(
    stale: Sequence[str], *, kb_path: str | None = None, session_id: str | None = None, auto: bool = False
) -> dict:
    """版本不一致 ⇒ 结构化 `stale_write`（供前端弹「重载 / 以我为准」；此刻零写入）。"""
    result = {
        "status": "error",
        "code": "stale_write",
        "message": "这些文件在校验之后被改动，整批拒绝（请重新校验 plan）：" + "、".join(sorted(stale)),
        "files": sorted(stale),
        "applied": [],
        "rolled_back": False,
        "auto": bool(auto),
    }
    result["audit"] = audit.append(kb_path, session_id, audit.EVENT_APPLY, result)
    return result


def recover_after_write(kb_path: str, rel_paths: Sequence[str] | None = None, *, service: Any = None) -> dict:
    """写/撤销之后的一致性恢复（§2.3.2 第 5 条）：**清该文件的解析缓存** + 跑 `validate_kb()`。

    撤销（`backup.restore_batch()`）是**直接写盘**、不走 `DocumentService.save_document()`，
    所以应用侧那份 `_cache` 会残留撤销前的解析 ⇒ 必须显式失效，否则界面显示的还是旧内容。

    注：`_cache` 是 `DocumentService` 的私有字段（同文件内的 `repair_path_cascade` 也这么清），
    这里从网关侧访问属**已知的私有触碰** —— 更干净的做法是加一个公开失效 API，已登记待办。
    """
    from memoria.services.document import DocumentService

    svc = service or DocumentService(kb_path=kb_path)
    cleared: list[str] = []
    cache = getattr(svc, "_cache", None)
    if isinstance(cache, dict):
        for rel in rel_paths or []:
            key = str(rel).replace("\\", "/")
            if cache.pop(key, None) is not None:
                cleared.append(key)
    report = svc.validate_kb()
    return {
        "status": "ok",
        "cache_cleared": cleared,
        "errors": report.get("errors"),
        "warnings": report.get("warnings"),
    }


def apply_plan(
    kb_path: str,
    plan: Any,
    *,
    session_id: str,
    txid: str | None = None,
    base_versions: dict | None = None,
    plugin: str | None = None,
    tool_id: str | None = None,
    service: Any = None,
    auto: bool = False,
) -> dict:
    """执行整批（all-or-nothing）。返回 `{status, txid, dir, applied[], files, warnings}`。

    失败语义：① 校验/编译不过 ⇒ **未建备份、未写盘**；② 备份预检失败 ⇒ **零写入**；
    ③ 任一原语失败 ⇒ 用该批次 pre-image **整批回滚**（回滚结果一并返回，不静默）。

    `auto`（2026-09-21 追加，可选）：本次写入是**没有人工闸门**的（agent 工具调用内直接落盘，
    见设计 §4 Q7）。只影响返回与审计里的标注（`auto: true`），不改变任何写入语义。
    """
    from memoria.services.document import DocumentService

    service = service or DocumentService(kb_path=kb_path)
    auto_flag = bool(auto)
    # **写冲突保护（§9）**：调用方给了"用户看过的那一版"（`preview_plan()` 返回的 `base_versions`）
    # ⇒ **先比版本再谈 plan**：文件都变了，报"plan 非法"是误导（真实原因是内容过期）。
    if base_versions:
        stale = [rel for rel, want in base_versions.items() if rel_version(kb_path, rel) != want]
        if stale:
            return _stale_error(stale, kb_path=kb_path, session_id=session_id, auto=auto_flag)
    compiled = compile_plan(kb_path, plan, service=service)
    if compiled["status"] != "ok":
        return {**compiled, "applied": [], "rolled_back": False}
    if not compiled["calls"]:
        return {"status": "error", "code": "empty_plan", "message": "plan 未编译出任何原语调用", "applied": []}

    # 调用方没给基准 ⇒ 用本次编译时记的那份做最低限度自检（等价于"单次 RPC 内没人插队"）。
    # 此时**尚未建备份、未写盘** —— agent 不基于过期版本写、也不静默赢。
    if not base_versions:
        stale = [
            rel
            for rel, want in (compiled.get("base_versions") or {}).items()
            if rel_version(kb_path, rel) != want
        ]
        if stale:
            return _stale_error(stale, kb_path=kb_path, session_id=session_id, auto=auto_flag)

    clean_txid = str(txid or compiled.get("txid") or "").strip()
    snapshot = backup.snapshot_pre_images(
        kb_path, session_id, clean_txid, compiled["files"], plugin=plugin, tool_id=tool_id
    )
    if snapshot["status"] != "ok":
        # 备份失败 ⇒ **不写**（fail-closed；不降级为"无备份的写入"）
        refused = {
            "status": "error",
            "code": snapshot.get("code") or "backup_failed",
            "message": snapshot.get("message") or "写前备份失败",
            "txid": clean_txid,
            "applied": [],
            "rolled_back": False,
            "auto": auto_flag,
        }
        refused["audit"] = audit.append(kb_path, session_id, audit.EVENT_APPLY, refused)
        return refused

    # **起点快照**（人 2026-09-21）：把"这次对话开始前的那一版"固化一份，且**不参与批次 FIFO 淘汰**
    # ⇒ 撤销总能回到**对话起点**（不再"最多回退到保留窗口"）。这一层就是 git 里那个稳定的 base。
    # fail-closed：写不进去就整批不写 —— 否则会出现"能写、却撤不回"。
    origin = backup.ensure_origin(kb_path, session_id, clean_txid, compiled["files"])
    if origin.get("status") != "ok":
        refused = {
            "status": "error",
            "code": origin.get("code") or "backup_failed",
            "message": f"起点快照写入失败 ⇒ 本次不写（避免“能写却撤不回”）：{origin.get('message') or ''}",
            "txid": clean_txid,
            "applied": [],
            "rolled_back": False,
            "auto": auto_flag,
        }
        refused["audit"] = audit.append(kb_path, session_id, audit.EVENT_APPLY, refused)
        return refused

    applied: list[dict] = []
    try:
        for call in compiled["calls"]:
            primitive = str(call["primitive"])
            handler = PRIMITIVES.get(primitive)
            if handler is None:  # 白名单之外的落点不存在（防御未来误加）
                raise _ApplyError(call, {"status": "error", "message": f"未登记的原语：{primitive}"})
            try:
                result = handler(service, call["args"])
            except (ValueError, RuntimeError) as e:
                # 原语的"拒绝"也可以**抛**而不是返回错误字典（如精确 span 与锚文本不符）⇒ 同样整批回滚
                raise _ApplyError(call, {"status": "error", "message": str(e)}) from e
            if not isinstance(result, Mapping) or result.get("status") != "ok":
                raise _ApplyError(call, result if isinstance(result, Mapping) else {"message": str(result)})
            applied.append({"op_id": call["op_id"], "primitive": primitive, "status": "ok"})
    except _ApplyError as exc:
        written = sorted({str(item["args"].get("rel_path") or "") for item in compiled["calls"][: len(applied) + 1]})
        rollback = backup.restore_batch(
            kb_path,
            session_id,
            clean_txid,
            rel_paths=affected_files(kb_path, [rel for rel in written if rel]),
            # 事务中途回滚：此刻**还没有** post.json（它由本函数最后一步落），
            # 且自快照以来唯一的写者就是本事务自己 ⇒ 显式跳过"外部改动保护"。
            allow_unverified=True,
            audit=False,  # 事务内回滚不是"用户撤销" ⇒ 不记 capability/undo（apply 失败事件已记全貌）
        )
        failed = {
            "status": "error",
            "code": "apply_failed",
            "message": str(exc),
            "txid": clean_txid,
            "failed": {"op_id": exc.call.get("op_id"), "primitive": exc.call.get("primitive"), "result": exc.result},
            "applied": applied,
            "rolled_back": rollback.get("status") == "ok",
            "rollback": rollback,
            "auto": auto_flag,
        }
        failed["audit"] = audit.append(kb_path, session_id, audit.EVENT_APPLY, failed)
        return failed

    posts = backup.record_post_images(kb_path, session_id, clean_txid)
    # **写后镜像**（人 2026-09-21）：给本批存一份"写完之后的样子" ⇒ 栈里「重做一步」的依据。
    # 近邻几步保持原始文件（redo 零解压），更深的由 `compact_after_images()` 压成 zip。
    # **fail-open**：写已成功、无法回滚 ⇒ 失败只记 warnings（后果是"这一步不可重做"，撤销仍可用）。
    after = backup.snapshot_after_images(kb_path, session_id, clean_txid)
    # **压栈**：新写入从当前指针处**截断**（丢掉旧的 redo 分支）再压入 ⇒ 指针 = 最新一步
    push = backup.push_stack(kb_path, session_id, clean_txid)
    compact = backup.compact_after_images(kb_path, session_id)
    after_warnings: list[str] = []
    if after.get("status") != "ok":
        after_warnings.append(
            f"写后镜像未存成（这一步将无法「重做」）：{after.get('message') or after.get('code') or ''}"
        )
    if push.get("status") != "ok":
        after_warnings.append(f"栈指针未落盘（下次按批次表推断）：{push.get('message') or ''}")
    trim = backup.trim_backups(kb_path, session_id)
    done = {
        "status": "ok",
        "txid": clean_txid,
        "dir": snapshot["dir"],
        "intent": compiled.get("intent"),
        "applied": applied,
        "files": compiled["files"],
        "backup": {"txid": clean_txid, "files": [row["rel_path"] for row in snapshot["files"]], "bytes": snapshot["bytes"]},
        "post_images": posts.get("status") == "ok",
        "trimmed": trim.get("evicted", []),
        "warnings": list(compiled.get("warnings", [])) + after_warnings,
        # 栈式撤销 / 重做（只增字段）：这一步在栈里的坐标 + 写后镜像是否就绪 + 本轮压缩了哪几批
        "after_images": after.get("status") == "ok",
        "stack": {"cursor": push.get("cursor"), "total": push.get("total"), "dropped": push.get("dropped", [])},
        "compacted": compact.get("compacted", []),
        "auto": auto_flag,
    }
    # 审计（§2.3.2 第 8 步）：写已完成 ⇒ 审计失败**不回滚**，但如实带回结果
    done["audit"] = audit.append(kb_path, session_id, audit.EVENT_APPLY, done)
    return done
