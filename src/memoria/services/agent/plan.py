# 设计来源：`docs/design/agent-capabilities.md` §2.3.3（计划 API）、§2.3.4（编译器与校验器）、
# §2.6（M3a 最小闭环）；契约与插件面以 `docs/design/agent-plugin-design.md` 为准。

"""写模块第一片：**计划 API 的只读骨架**（schema + 校验器 + dry-run 预览 + 目标解析）。

**这一步一个字都不写盘。** 模块只做三件事：把 agent 产出的**声明式 plan** 校验成"能落地"、
把落地后的**行级变化**在内存里算出来给人看、把 plan 里的目标解析成候选。真正的落盘
（pre-image 备份 → 四原语 → 审计）属下一片（apply 入口），本模块**不提供**任何 apply 函数。

> **"零落盘"的精确含义**（实测钉住，2026-09-20）：**不写任何事实源**（`md` / `sidecar` /
> `manifest` / `pending` 逐字节不变）。复用既有只读 API 时可能碰**可再生缓存**：
> `resolve_link_target()` → `build_kp_index()` 会补写 `.memoria/cache/search_aux/kp/*.json`
> （[AGENTS.md §1](../../../../AGENTS.md) 明确 `cache/**` 不作为事实源）。测试
> `tests/test_agent_plan.py::test_preview_plan_gives_a_diff_and_writes_nothing` 逐文件钉住这一点。

口径（三条硬约束，与设计文档逐条对应）：

1. **失败即拒整批（all-or-nothing）**：一次 `validate_plan` 要么说清"哪条 op 的哪个字段不对"，
   要么说"可落地"；**不下发"只应用合法子集"**（§2.3.3「失败语义」）。错误按 `op_id` 定位，
   便于模型自查后**重写整批**。
2. **同一套校验器，两个消费者**（§2.3.4 硬不变量）：路径、KP id、链接目标、正文匹配
   一律**转调人类 UI 已走的同一批函数**（`_safe_rel` / `DocumentService.check_kp_id` /
   `resolve_link_target` / `scan_link_text_matches` / `normalize_link_edge_type`），
   **不另写宽松判断** —— 否则会出现"人 UI 拒绝、agent 放行"的漂移。
3. **未知即拒**：未知 op 或未知 `v` ⇒ 拒整批（§10 P12 推荐①的"只增不改"）⇒
   格式演进（新增 op / 新增字段）不必改提示词，且**程序可验**。

plan 信封（字段只增不改）：`{"v": 1, "txid": "...", "intent": "人话一句", "ops": [...]}`。
op 通用字段：`op`（动词名）/ `op_id`（plan 内唯一）/ `file`（库内相对 `.md` 路径）。
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from typing import Any

from memoria.graph.edge_types import EDGE_EXTEND, EDGE_REFERENCE, normalize_link_edge_type
from memoria.range.constants import SNIPPET_MAX_LEN
from memoria.range.locator import resolve_range
from memoria.services.agent.tools.kb import _safe_rel
from memoria.services.link_instances import find_plain_text_in_line, wrap_plain_on_lines
from memoria.services.link_resolver import resolve_link_target
from memoria.storage.markdown import strip_frontmatter
from memoria.storage.sidecar import load_sidecar_for_md

#: plan schema 版本（§2.3.3 信封的 `v`；破坏性变更才 +1）
PLAN_VERSION = 1

OP_UPSERT_KP = "upsert_kp"
OP_ATTACH_LINKS = "attach_links"
OP_DETACH_LINKS = "detach_links"
OP_SET_KP_RANGE = "set_kp_range"
OP_RENAME_KP = "rename_kp"

#: 全部已知 op（**只增不改**）；不在表内 ⇒ 拒整批
KNOWN_OPS: tuple[str, ...] = (
    OP_UPSERT_KP,
    OP_ATTACH_LINKS,
    OP_DETACH_LINKS,
    OP_SET_KP_RANGE,
    OP_RENAME_KP,
)

#: M3a 首批（§10 P8 推荐①：三个 op 覆盖 KP 与链接两个动作类、两个方向；`set_kp_range` /
#: `rename_kp` 留 M3b —— 后者影响**全库**，门禁面过大）
M3A_OPS: tuple[str, ...] = (OP_UPSERT_KP, OP_ATTACH_LINKS, OP_DETACH_LINKS)

#: 事务 id 形态（`<YYYYMMDD>T<HHMMSS>Z-<n>`；与 §2.3.2 的备份目录 `<txid>` 同格式同来源）
TXID_RE = re.compile(r"^\d{8}T\d{6}Z-\d+$")

#: 可由 plan 声明的边类型（`contain` 不由 plan 写 —— 它由"知识点包含关系"派生）
PLAN_EDGE_TYPES = frozenset({EDGE_REFERENCE, EDGE_EXTEND})


def _err(op_id: str, code: str, message: str) -> dict[str, str]:
    return {"op_id": op_id, "code": code, "message": message}


def _warn(op_id: str, code: str, message: str) -> dict[str, str]:
    return {"op_id": op_id, "code": code, "message": message}


def _as_dict(value: Any) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list:
    return list(value) if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else []


def _body_lines(kb_path: str, rel: str) -> list[str]:
    """读正文行（剥 frontmatter）；与 `read_document` 同一行空间 ⇒ 行号可直接对齐。

    刻意直接读盘而不借 `DocumentService._read_body()`（跨模块借私有名），语义与其一致：
    `strip_frontmatter` + `splitlines()`，空文件保证至少一行。
    """
    full = os.path.join(kb_path, rel)
    with open(full, "r", encoding="utf-8") as handle:
        body, _ = strip_frontmatter(handle.read())
    return body.splitlines() or [""]


def _sidecar_of(kb_path: str, rel: str) -> dict:
    sidecar = load_sidecar_for_md(os.path.join(kb_path, rel), kb_path)
    return dict(sidecar) if isinstance(sidecar, Mapping) else {}


def _normalize_range_spec(spec: Any, lines: Sequence[str], *, what: str, op_id: str, errors: list[dict]) -> dict:
    """把 plan 给的 `{line, snippet?}` 归一成 `resolve_range` 要的 `{line_hint, snippet}`。

    行非空是硬规则（对齐既有 `kp_range_start_empty` / `kp_range_end_empty` 的语义）：
    落在空行上直接拒 —— 否则落到 sidecar 的 range 指向一片空白。
    """
    data = _as_dict(spec)
    try:
        line = int(data.get("line"))
    except (TypeError, ValueError):
        errors.append(_err(op_id, "missing_field", f"{what}.line 必须是整数"))
        return {}
    if line < 1:
        errors.append(_err(op_id, "bad_field", f"{what}.line 必须 ≥ 1"))
        return {}
    if line > len(lines):
        errors.append(_err(op_id, "bad_field", f"{what}.line={line} 超出文件行数（{len(lines)}）"))
        return {}
    row = lines[line - 1]
    if not row.strip():
        errors.append(_err(op_id, "range_line_empty", f"{what}.line={line} 是空行"))
        return {}
    snippet = str(data.get("snippet") or "").strip()
    return {"line_hint": line, "snippet": snippet[:SNIPPET_MAX_LEN] or row.strip()[:SNIPPET_MAX_LEN]}


def _check_envelope(plan: Any, errors: list[dict], warnings: list[dict]) -> dict:
    if not isinstance(plan, Mapping):
        errors.append(_err("", "bad_envelope", "plan 必须是对象"))
        return {}
    data = dict(plan)
    raw_v = data.get("v")
    if raw_v != PLAN_VERSION:
        errors.append(_err("", "bad_plan_version", f"不支持的 plan 版本：{raw_v!r}（本编译器只认 {PLAN_VERSION}）"))
    txid = str(data.get("txid") or "").strip()
    if not txid:
        errors.append(_err("", "missing_field", "缺 txid"))
    elif not TXID_RE.match(txid):
        # 格式不合只警告：txid 由前端/上层生成，形态漂移不该整批拒（备份目录名仍可用）
        warnings.append(_warn("", "txid_format", f"txid 形态非常规：{txid}"))
    if not str(data.get("intent") or "").strip():
        errors.append(_err("", "missing_field", "缺 intent（人话一句，用于审计与确认卡标题）"))
    ops = data.get("ops")
    if not isinstance(ops, Sequence) or isinstance(ops, (str, bytes)) or not ops:
        errors.append(_err("", "missing_field", "ops 必须是非空数组"))
        return data
    return data


def _validate_upsert_kp(kb_path: str, op: Mapping, lines: Sequence[str], service: Any, op_id: str, errors: list[dict]) -> dict:
    kp_id = str(op.get("kp_id") or "").strip()
    name = str(op.get("name") or "").strip()
    if not kp_id:
        errors.append(_err(op_id, "missing_field", "缺 kp_id"))
    if not name:
        errors.append(_err(op_id, "missing_field", "缺 name"))
    if kp_id and service is not None:
        # 复用人类 UI 的同一函数：全局唯一；**本文件已有同 id ⇒ 可更新**（幂等键 `(file, kp_id)`）
        checked = service.check_kp_id(kp_id, str(op.get("file") or ""))
        if not checked.get("available", False):
            errors.append(_err(op_id, "kp_id_taken", str(checked.get("message") or f"目标 id 已存在：{kp_id}")))
    start = _normalize_range_spec(_as_dict(op.get("range")).get("start"), lines, what="range.start", op_id=op_id, errors=errors)
    end = _normalize_range_spec(_as_dict(op.get("range")).get("end"), lines, what="range.end", op_id=op_id, errors=errors)
    if start and end and start["line_hint"] > end["line_hint"]:
        errors.append(_err(op_id, "range_invalid", "range.start.line 必须 ≤ range.end.line"))
        return {"action": "invalid"}
    resolved = resolve_range(lines, start, end) if start and end else {}
    if start and end and not resolved.get("ok"):
        errors.append(_err(op_id, "range_invalid", f"range 解析失败：{resolved.get('error') or '未命中'}"))
        return {"action": "invalid"}
    exists = False
    if kp_id and service is not None:
        exists = bool(service.check_kp_id(kp_id, str(op.get("file") or "")).get("exists_in_file"))
    return {
        "action": "update" if exists else "create",
        "kp_id": kp_id,
        "name": name,
        "resolved": {"start_line": resolved.get("start_line"), "end_line": resolved.get("end_line")},
        "tags": [str(t) for t in _as_list(op.get("tags"))],
    }


def _validate_attach_links(
    kb_path: str, op: Mapping, lines: Sequence[str], op_id: str, errors: list[dict], pending_ids: set[str]
) -> dict:
    anchor = str(op.get("anchor_text") or "").strip()
    if not anchor:
        errors.append(_err(op_id, "missing_field", "缺 anchor_text"))
        return {"action": "invalid"}
    targets = [str(t).strip() for t in _as_list(op.get("targets")) if str(t).strip()]
    if not targets:
        errors.append(_err(op_id, "missing_field", "targets 必须是非空数组"))
        return {"action": "invalid"}
    for target in targets:
        # 同一 plan 内**前序** `upsert_kp` 刚建的点对后 op 可见（§2.3.3 信封注释："前 op 的结果
        # 对后 op 可见（可'先建点、后连边'）"）—— 否则"建点 + 连边"这种最常见的 plan 永远校验不过。
        if target in pending_ids:
            continue
        # 「目标必须可解析」：ambiguous / not_found 一律拒整批（§2.3.3 校验列）
        resolved = resolve_link_target(kb_path, target)
        if resolved.get("status") != "ok":
            code = "target_ambiguous" if resolved.get("status") == "ambiguous" else "target_not_found"
            errors.append(_err(op_id, code, f"链接目标不可解析：{target}（{resolved.get('status')}）"))
    raw_edge = op.get("edge_type")
    edge_type = ""
    if raw_edge not in (None, ""):
        # 先按**原始值**卡白名单（`normalize_link_edge_type()` 对未知值一律回落 `reference`，
        # 单看归一化结果会把 `contain` / `prerequisite` 放行 ⇒ 必须卡原值），再归一化存值。
        raw_key = str(raw_edge).strip().lower()
        if raw_key not in PLAN_EDGE_TYPES:
            errors.append(_err(op_id, "bad_edge_type", f"edge_type 只接受 reference / extend：{raw_edge!r}"))
        else:
            edge_type = normalize_link_edge_type(raw_key)
    # 纯文本出现由 `find_plain_text_in_line()` 定位 —— 它就是 `wrap_plain_on_lines()` 内部用的
    # 同一个原子函数（**同一套校验器**：候选行与最终包裹位置由构造保证一致）。
    # 实测口径（2026-09-20）：`scan_link_text_matches()` **不返回**纯文本出现（它匹配的是既有
    # wikilink 路由 + 模糊建议；对纯文本正文只回 `'。注意力机'` 这类建议命中）
    # ⇒ 设计稿 §2.3.3「编译器要解析」列写的 `scan_link_text_matches` 对纯文本不成立，已记入偏差。
    plain_lines = [idx for idx, row in enumerate(lines, start=1) if find_plain_text_in_line(row, anchor) >= 0]
    wrapped_lines = [idx for idx, row in enumerate(lines, start=1) if "[[" + anchor + "]]" in row]
    matched_lines = set(plain_lines) | set(wrapped_lines)
    occurrences = op.get("occurrences")
    if occurrences is None:
        chosen = sorted(plain_lines)
        if not chosen:
            errors.append(_err(op_id, "occurrence_not_found", f"正文里找不到锚文本：{anchor}"))
    else:
        chosen = []
        for item in _as_list(occurrences):
            row = _as_dict(item)
            try:
                line = int(row.get("line"))
            except (TypeError, ValueError):
                errors.append(_err(op_id, "missing_field", "occurrences[].line 必须是整数"))
                continue
            if line not in matched_lines:
                errors.append(_err(op_id, "occurrence_not_found", f"第 {line} 行没有可挂接的锚文本：{anchor}"))
                continue
            expected = str(row.get("matched_text") or "").strip()
            if expected and expected != anchor:
                # 前置核对（§2.3.3「需新增的最小能力」第 2 条）：纯文本出现被**逐字**匹配，
                # 故 plan 声明的 matched_text 必须与锚文本逐字相同（子串/近似一律拒）。
                errors.append(_err(op_id, "occurrence_mismatch", f"第 {line} 行匹配文本不符：plan={expected!r} 实际={anchor!r}"))
                continue
            chosen.append(line)
    return {
        "action": "wrap" if chosen else "noop",
        "anchor_text": anchor,
        "targets": targets,
        "edge_type": edge_type or None,
        "lines": sorted(chosen),
        "candidates": sorted(plain_lines),
    }


def _validate_detach_links(kb_path: str, op: Mapping, lines: Sequence[str], sidecar: Mapping, op_id: str, errors: list[dict]) -> dict:
    anchor = str(op.get("anchor_text") or "").strip()
    if not anchor:
        errors.append(_err(op_id, "missing_field", "缺 anchor_text"))
        return {"action": "invalid"}
    mode = str(op.get("mode") or "detach").strip()
    if mode not in ("detach", "remove_route"):
        errors.append(_err(op_id, "bad_field", f"mode 非法：{mode}（只接受 detach / remove_route）"))
    entry = None
    for link in _as_list(sidecar.get("links")):
        if isinstance(link, Mapping) and str(link.get("anchor_text") or "").strip() == anchor:
            entry = dict(link)
            break
    if entry is None:
        errors.append(_err(op_id, "anchor_not_in_sidecar", f"sidecar 里没有这条锚：{anchor}"))
        return {"action": "invalid"}
    instance_lines = {
        int(inst.get("line"))
        for inst in _as_list(entry.get("instances"))
        if isinstance(inst, Mapping) and inst.get("line")
    }
    chosen: list[int] = []
    for item in _as_list(op.get("occurrences")):
        row = _as_dict(item)
        try:
            line = int(row.get("line"))
        except (TypeError, ValueError):
            errors.append(_err(op_id, "missing_field", "occurrences[].line 必须是整数"))
            continue
        if line < 1 or line > len(lines):
            errors.append(_err(op_id, "bad_field", f"occurrences[].line={line} 超出文件行数"))
            continue
        text = lines[line - 1]
        if line not in instance_lines and "[[" not in text:
            errors.append(_err(op_id, "occurrence_not_found", f"第 {line} 行既不是已挂接实例、也不含 [[…]]"))
            continue
        chosen.append(line)
    if not chosen:
        errors.append(_err(op_id, "missing_field", "occurrences 必须给出至少一行（detach 按行定位）"))
    return {"action": mode, "anchor_text": anchor, "lines": sorted(chosen)}


def _validate_op(
    kb_path: str, op: Any, service: Any, errors: list[dict], warnings: list[dict], pending_ids: set[str]
) -> dict:
    if not isinstance(op, Mapping):
        errors.append(_err("", "bad_envelope", "ops[] 的元素必须是对象"))
        return {"op": "", "op_id": "", "action": "invalid"}
    data = dict(op)
    op_id = str(data.get("op_id") or "").strip()
    verb = str(data.get("op") or "").strip()
    if not op_id:
        errors.append(_err("", "missing_field", "op 缺 op_id"))
    if verb not in KNOWN_OPS:
        # 未知即拒（P12 推荐①）：不静默忽略，否则"旧编译器偷偷少做一步"不可见
        errors.append(_err(op_id, "unknown_op", f"未知 op：{verb!r}"))
        return {"op": verb, "op_id": op_id, "action": "invalid"}
    if verb not in M3A_OPS:
        warnings.append(_warn(op_id, "op_not_in_m3a", f"{verb} 不在 M3a 首批（本轮只读骨架不编译它）"))
    rel = _safe_rel(kb_path, str(data.get("file") or ""))
    if rel is None:
        errors.append(_err(op_id, "path_rejected", f"file 不在允许根内或不是 .md：{data.get('file')!r}"))
        return {"op": verb, "op_id": op_id, "action": "invalid"}
    if not os.path.isfile(os.path.join(kb_path, rel)):
        errors.append(_err(op_id, "file_not_found", f"文件不存在：{rel}"))
        return {"op": verb, "op_id": op_id, "action": "invalid"}
    lines = _body_lines(kb_path, rel)
    if verb == OP_UPSERT_KP:
        detail = _validate_upsert_kp(kb_path, data, lines, service, op_id, errors)
    elif verb == OP_ATTACH_LINKS:
        detail = _validate_attach_links(kb_path, data, lines, op_id, errors, pending_ids)
    elif verb == OP_DETACH_LINKS:
        detail = _validate_detach_links(kb_path, data, lines, _sidecar_of(kb_path, rel), op_id, errors)
    else:
        detail = {"action": "uncompiled"}  # set_kp_range / rename_kp：M3b 才编译
    return {"op": verb, "op_id": op_id, "file": rel, **detail}


def validate_plan(kb_path: str, plan: Any, *, service: Any = None) -> dict:
    """结构 + 语义校验（**不碰盘**），错误按 `op_id` 返回；两条都会导致"拒整批"。

    `service` 传 `DocumentService` 时复用其 `check_kp_id()`（人类 UI 同一条唯一性判定）；
    缺省自建一个（会走既有的首次装载语义 —— 调用方在应用内应传已装载实例）。
    """
    errors: list[dict] = []
    warnings: list[dict] = []
    data = _check_envelope(plan, errors, warnings)
    if not data:
        return {"status": "error", "errors": errors, "warnings": warnings, "ops": []}
    if service is None:
        from memoria.services.document import DocumentService

        service = DocumentService(kb_path=kb_path)
    seen: set[str] = set()
    ops: list[dict] = []
    #: 同一 plan 内**前序** op 新建的 KP id（"先建点、后连边"的可见性集合；§2.3.3）
    pending_ids: set[str] = set()
    for raw in _as_list(data.get("ops")):
        parsed = _validate_op(kb_path, raw, service, errors, warnings, pending_ids)
        oid = str(parsed.get("op_id") or "")
        if oid and oid in seen:
            errors.append(_err(oid, "duplicate_op_id", f"op_id 在 plan 内重复：{oid}"))
        if oid:
            seen.add(oid)
        if parsed.get("op") == OP_UPSERT_KP and parsed.get("kp_id"):
            pending_ids.add(str(parsed["kp_id"]))
        ops.append(parsed)
    return {
        "status": "error" if errors else "ok",
        "v": data.get("v"),
        "txid": data.get("txid"),
        "intent": data.get("intent"),
        "errors": errors,
        "warnings": warnings,
        "ops": ops,
    }


def preview_plan(kb_path: str, plan: Any, *, service: Any = None) -> dict:
    """**dry-run**：在内存里算出"将改哪些文件、哪些行"，**零落盘**。

    先跑 `validate_plan`，有错就原样返回（不预览一个非法 plan）。能算出行级 diff 的 op
    （`upsert_kp` / `attach_links`）给出 `lines_changed` + 逐行 before/after；算不出的
    （`detach_links`，其落盘动作在 `detach_link_instance` 内）如实标 `diff_available: false`，
    只给"将作用于哪些行"。
    """
    checked = validate_plan(kb_path, plan, service=service)
    if checked["status"] != "ok":
        return {**checked, "previewed": False, "files": []}
    by_id = {str(op.get("op_id") or ""): op for op in _as_list(_as_dict(plan).get("ops"))}
    files: dict[str, dict] = {}
    for parsed in checked["ops"]:
        op_id = str(parsed.get("op_id") or "")
        rel = str(parsed.get("file") or "")
        bucket = files.setdefault(rel, {"file": rel, "ops": [], "lines_changed": []})
        entry = {"op_id": op_id, "op": parsed.get("op"), "action": parsed.get("action")}
        if parsed.get("op") == OP_UPSERT_KP:
            entry["resolved"] = parsed.get("resolved")
        elif parsed.get("op") == OP_ATTACH_LINKS:
            lines = _body_lines(kb_path, rel)
            anchor = str(parsed.get("anchor_text") or "")
            chosen = [int(x) for x in _as_list(parsed.get("lines"))]
            # 不传 `line_spans`：包裹位置由 `wrap_plain_on_lines()` 内部用 `find_plain_text_in_line()`
            # 自己定位 —— 与校验阶段的候选行判定**同一个原子函数**，构造上不可能漂移。
            new_body, wrapped = wrap_plain_on_lines("\n".join(lines), anchor, chosen)
            new_lines = new_body.split("\n")
            changed = [i + 1 for i in range(min(len(lines), len(new_lines))) if lines[i] != new_lines[i]]
            entry["diff_available"] = True
            entry["wrapped"] = wrapped
            entry["lines_changed"] = changed
            entry["diff"] = [
                {"line": ln, "before": lines[ln - 1], "after": new_lines[ln - 1]} for ln in changed
            ]
            bucket["lines_changed"] = sorted(set(bucket["lines_changed"]) | set(changed))
        elif parsed.get("op") == OP_DETACH_LINKS:
            entry["diff_available"] = False  # 落盘动作在 detach_link_instance 内，本片不试算其正文结果
            entry["lines"] = parsed.get("lines")
            bucket["lines_changed"] = sorted(set(bucket["lines_changed"]) | set(_as_list(parsed.get("lines"))))
        bucket["ops"].append(entry)
    return {
        **checked,
        "previewed": True,
        "files": [files[key] for key in sorted(files)],
    }


def resolve_target(kb_path: str, target: str) -> dict:
    """`resolve` 只读面：KP id / 文件 stem → 候选（`ok` / `ambiguous` / `not_found`）。

    直接转调人类 UI 同一条 `resolve_link_target()`；本函数只把结果收成稳定形状。
    """
    raw = (target or "").strip()
    if not raw:
        return {"status": "not_found", "target": raw, "candidates": [], "message": "空目标"}
    resolved = resolve_link_target(kb_path, raw)
    status = str(resolved.get("status") or "not_found")
    if status == "error":
        status = "not_found"
    return {
        "status": status,
        "target": raw,
        "match": resolved.get("match"),
        "candidates": _as_list(resolved.get("candidates")),
    }
