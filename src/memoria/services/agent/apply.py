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
    OP_DETACH_LINKS,
    OP_RENAME_FILE,
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
    return os.path.relpath(full_path, os.path.realpath(kb_path)).replace("\\", "/")


def affected_files(kb_path: str, rel_paths: Sequence[str]) -> list[str]:
    """该事务会碰的**全部**落盘目标（§2.3.2 第 1 条）：正文 + 其 sidecar + manifest + pending。

    sidecar 路径走 `sidecar_path_for()`（与存储层同一映射），**不另写一份**。
    """
    out: list[str] = []
    for rel in rel_paths:
        text = str(rel or "").strip().replace("\\", "/")
        if not text:
            continue
        out.append(text)
        out.append(_rel(kb_path, sidecar_path_for(os.path.join(kb_path, text), kb_path)))
    out.append(_rel(kb_path, manifest_path(kb_path)))
    out.append(_rel(kb_path, pending_path(kb_path)))
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
    #: 改正文的 op 按文件收集，循环结束后**每个文件合成一次** `edit_body`（`body_edit.splice`
    #: 内部按行号从大到小应用 ⇒ 每条的行号都以"编辑前"的正文为准，不需要调用方倒序）。
    #: 校验期已保证它们排在按行号锚定的 op **之后**（`body_edit_order`）⇒ 追加在 `calls` 末尾。
    body_edits: dict[str, dict[str, Any]] = {}
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
            bucket = body_edits.setdefault(rel, {"op_ids": [], "edits": []})
            if isinstance(parsed.get("edit"), Mapping):
                bucket["op_ids"].append(op_id)
                bucket["edits"].append(dict(parsed["edit"]))
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
    for rel, bucket in body_edits.items():
        if not bucket["edits"]:
            continue
        calls.append(
            {
                "op_id": "+".join(bucket["op_ids"]),
                "op": "edit_body",
                "primitive": "edit_body",
                "args": {"rel_path": rel, "edits": bucket["edits"]},
            }
        )
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


def _stale_error(stale: Sequence[str], *, kb_path: str | None = None, session_id: str | None = None) -> dict:
    """版本不一致 ⇒ 结构化 `stale_write`（供前端弹「重载 / 以我为准」；此刻零写入）。"""
    result = {
        "status": "error",
        "code": "stale_write",
        "message": "这些文件在校验之后被改动，整批拒绝（请重新校验 plan）：" + "、".join(sorted(stale)),
        "files": sorted(stale),
        "applied": [],
        "rolled_back": False,
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
) -> dict:
    """执行整批（all-or-nothing）。返回 `{status, txid, dir, applied[], files, warnings}`。

    失败语义：① 校验/编译不过 ⇒ **未建备份、未写盘**；② 备份预检失败 ⇒ **零写入**；
    ③ 任一原语失败 ⇒ 用该批次 pre-image **整批回滚**（回滚结果一并返回，不静默）。
    """
    from memoria.services.document import DocumentService

    service = service or DocumentService(kb_path=kb_path)
    # **写冲突保护（§9）**：调用方给了"用户看过的那一版"（`preview_plan()` 返回的 `base_versions`）
    # ⇒ **先比版本再谈 plan**：文件都变了，报"plan 非法"是误导（真实原因是内容过期）。
    if base_versions:
        stale = [rel for rel, want in base_versions.items() if rel_version(kb_path, rel) != want]
        if stale:
            return _stale_error(stale, kb_path=kb_path, session_id=session_id)
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
            return _stale_error(stale, kb_path=kb_path, session_id=session_id)

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
        }
        failed["audit"] = audit.append(kb_path, session_id, audit.EVENT_APPLY, failed)
        return failed

    posts = backup.record_post_images(kb_path, session_id, clean_txid)
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
        "warnings": compiled.get("warnings", []),
    }
    # 审计（§2.3.2 第 8 步）：写已完成 ⇒ 审计失败**不回滚**，但如实带回结果
    done["audit"] = audit.append(kb_path, session_id, audit.EVENT_APPLY, done)
    return done
