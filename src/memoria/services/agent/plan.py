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
from memoria.services.agent.body_edit import (
    BLOCK_KINDS,
    MODE_DELETE,
    MODE_INSERT,
    MODE_REPLACE,
    EditError,
    block_bounds,
    check_edit,
    normalize_edits,
    rebuild_block,
    splice,
)
from memoria.services.agent.tools.kb import _safe_rel
from memoria.services.link_instances import find_plain_text_in_line, unwrap_lines, wrap_plain_on_lines
from memoria.services.link_resolver import resolve_link_target
from memoria.storage.file_version import rel_version
from memoria.storage.markdown import strip_frontmatter
from memoria.storage.sidecar import load_sidecar_for_md

#: plan schema 版本（§2.3.3 信封的 `v`；破坏性变更才 +1）
PLAN_VERSION = 1

OP_UPSERT_KP = "upsert_kp"
OP_ATTACH_LINKS = "attach_links"
OP_DETACH_LINKS = "detach_links"
OP_SET_KP_RANGE = "set_kp_range"
OP_RENAME_KP = "rename_kp"
#: W 线第二步：**改正文行**（§7 的 2.1 / 2.2 / 2.3）—— 落点是原语 `kb.file.edit`
#: （`services/agent/body_edit.py`，薄包装 `DocumentService.save_document()`）
OP_REPLACE_LINES = "replace_lines"
OP_INSERT_LINES = "insert_lines"
OP_DELETE_LINES = "delete_lines"
#: 块级（§7 的 5.1 / 5.3 / 5.5）：**整块重建**代码块 / mermaid / 公式块 —— 语义上是"按整块替换"，
#: 因此复用 `body_edit` 的 `replace` 落地（不新增落盘原语；表格见 §7 5.2，本轮不给）
OP_UPSERT_BLOCK = "upsert_block"
#: 图片（§7 的 4.1）：**只插图片引用那一行**（图片入库/改属性/移动删除本轮不做，见 `file_ops`）
OP_INSERT_IMAGE_REF = "insert_image_ref"
#: 文件级（§7 的 2.4 / 2.6）：新建 `.md` / 重命名（含全库引用级联）—— 落点 `services/agent/file_ops.py`
OP_CREATE_FILE = "create_file"
OP_RENAME_FILE = "rename_file"
#: 删除整篇文档（2026-09-22 新增）：**风险 op** + 悬空引用先拦，见 `_validate_delete_file()`。
OP_DELETE_FILE = "delete_file"
#: 把整篇文档移到**另一个目录**（2026-09-22 新增）：只改目录、**保持文件名** ⇒ 不改写任何 `[[…]]`
#: 引用（id/stem 寻址不受路径影响）；正文里的**文件相对**链接/图片会被预演拦下（见 `_validate_move_file()`）。
OP_MOVE_FILE = "move_file"
#: KP↔KP 的**纯边**（2026-09-22 新增；设计 §7 1.2 的 `upsert_edge` → 原语 `kb.link.create`）：只写
#: sidecar 的 `edges[]`、**不碰正文**（要写正文锚点用 `attach_links`）。边类型只收 `reference` / `extend`
#: —— `contain` 由标题层级自动推导、**禁手标**（`<库>/.memoria/agent/kb-spec.zh-CN.md` §4）。
OP_UPSERT_EDGE = "upsert_edge"
#: 删除知识点（2026-09-22 新增；设计 §7 1.7 的 `delete_kp` → 原语 `kb.kp.delete`）：只删 sidecar 里的
#: KP 配置、**不改正文** ⇒ 正文里的 `[[id]]` 会变成悬空虚链。库规明确允许虚链（kb-spec §4）⇒ 只**警告**
#: 不拦（与 `delete_file` 对正文引用硬拦的分层理由：那里整篇消失、这里只是少一个可解析目标）。
OP_DELETE_KP = "delete_kp"
#: 重建 / 同步 **`manifest.yaml`**（2026-09-22 新增；设计 §7 6.3 的 `kb.manifest.rebuild`）：全库重扫磁盘、
#: 把文件清单与指纹整体重写一遍 —— 「清单陈旧」那一类（新文档未记入 / 指纹过期 / 历史错拼留下的陈旧
#: 条目）**只能靠它消**，此前 agent 侧一个能碰 manifest 的 op 都没有（真机报告原话："只能点构建"）。
#: **不带 `file`**（整库一件事）；**必须收尾**（它记录的是"这一批之后"的文件集）。
#: **前置硬闸**：库里有未修复的**路径变更** ⇒ 拒（先「修复路径」）—— 判定直接调
#: `document.sync_manifest()` 用的同一个 `detect_path_moves()`（单一事实源，不另写宽松判断）。
OP_REBUILD_MANIFEST = "rebuild_manifest"

#: 全部已知 op（**只增不改**）；不在表内 ⇒ 拒整批
KNOWN_OPS: tuple[str, ...] = (
    OP_UPSERT_KP,
    OP_ATTACH_LINKS,
    OP_DETACH_LINKS,
    OP_SET_KP_RANGE,
    OP_RENAME_KP,
    OP_REPLACE_LINES,
    OP_INSERT_LINES,
    OP_DELETE_LINES,
    OP_UPSERT_BLOCK,
    OP_INSERT_IMAGE_REF,
    OP_CREATE_FILE,
    OP_RENAME_FILE,
    OP_DELETE_FILE,
    OP_MOVE_FILE,
    OP_UPSERT_EDGE,
    OP_DELETE_KP,
    OP_REBUILD_MANIFEST,
)

#: M3a 首批（§10 P8 推荐①：三个 op 覆盖 KP 与链接两个动作类、两个方向；`set_kp_range` /
#: `rename_kp` 留 M3b —— 后者影响**全库**，门禁面过大）
M3A_OPS: tuple[str, ...] = (OP_UPSERT_KP, OP_ATTACH_LINKS, OP_DETACH_LINKS)

#: 编译器**已实现**的 op（其余 `KNOWN_OPS` 只登记不编译：出现即警告，编译不出任何原语调用，
#: apply 判 `empty_plan`）。**2026-09-22**：`rename_kp`（全库改 id）、`upsert_edge`（纯边）、
#: `delete_kp`（删 KP）三个 sidecar 结构 op 从"只登记"转为"已编译"，见各 `_validate_*` / `compile_plan` 分支。
COMPILED_OPS: tuple[str, ...] = (
    OP_UPSERT_KP,
    OP_ATTACH_LINKS,
    OP_DETACH_LINKS,
    OP_REPLACE_LINES,
    OP_INSERT_LINES,
    OP_DELETE_LINES,
    OP_UPSERT_BLOCK,
    OP_INSERT_IMAGE_REF,
    OP_CREATE_FILE,
    OP_RENAME_FILE,
    OP_DELETE_FILE,
    OP_MOVE_FILE,
    OP_RENAME_KP,
    OP_UPSERT_EDGE,
    OP_DELETE_KP,
    OP_REBUILD_MANIFEST,
)

#: **改正文行**的 op（会改变行数/行内容）。`upsert_block` / `insert_image_ref` 语义上是"整块替换 /
#: 插一行" ⇒ 同族：走同一套结构/内容级自检、同一份顺序规矩、同一个 `edit_body` 落地、同一套预览 diff。
BODY_EDIT_OPS: tuple[str, ...] = (
    OP_REPLACE_LINES,
    OP_INSERT_LINES,
    OP_DELETE_LINES,
    OP_UPSERT_BLOCK,
    OP_INSERT_IMAGE_REF,
)
#: **按行号锚定**的 op（行号以"当前正文"为准；`attach_links` / `detach_links` 的 lines、
#: `upsert_kp` 的 range）。它们不改行数；**顺序不再受限** —— 行号按批内视图里"那一刻的正文"算。
LINE_ANCHORED_OPS: tuple[str, ...] = (OP_UPSERT_KP, OP_ATTACH_LINKS, OP_DETACH_LINKS)
#: **文件级** op（新增/改名/删除/移动）。`create_file` 由**批内视图**顺手造出（同批后面的 op 立刻能按这个
#: 新文件算行号）；`rename_file` 会重写全库引用并搬路径、`delete_file` 会让指向它的引用变悬空
#: ⇒ 两者只允许**收尾**；`move_file` 只动**自己那一篇**（含它的侧车）⇒ 可以**连排多条**（见 `_check_rename_last()`）。
FILE_OPS: tuple[str, ...] = (OP_CREATE_FILE, OP_RENAME_FILE, OP_DELETE_FILE, OP_MOVE_FILE)
#: `FILE_OPS` 里**会动"路径"这个坐标系**的那些（`create_file` **不算**：它只是把新文件"种"进批内视图，
#: 同批后面的 op 照旧可以按它算行号 / 建点 / 挂链 —— 这条放行不能丢）。顺序规矩按本表判（见 `_check_rename_last()`）。
#: **2026-09-22** 追加 `rename_kp`：它不改路径，但会**全库改写正文**（`[[旧 id]]` → `[[新 id]]`），
#: 而批内视图并不跟着改写 ⇒ 它之后再按行/按原文校验的 op 都会基于**过期文本**（校验过、落地才对不上）。
#: 故与"动路径"同待遇：出现后只允许再排 `FILE_OPS`（见 `_check_rename_last()` 的两条规矩）。
PATH_MOVING_OPS: tuple[str, ...] = (OP_MOVE_FILE, OP_RENAME_FILE, OP_DELETE_FILE, OP_RENAME_KP)


#: 事务 id 形态（`<YYYYMMDD>T<HHMMSS>Z-<n>`；与 §2.3.2 的备份目录 `<txid>` 同格式同来源）
TXID_RE = re.compile(r"^\d{8}T\d{6}Z-\d+$")

#: 可由 plan 声明的边类型（`contain` 不由 plan 写 —— 它由"知识点包含关系"派生）
PLAN_EDGE_TYPES = frozenset({EDGE_REFERENCE, EDGE_EXTEND})


def base_versions(kb_path: str, rel_paths: Sequence[str]) -> dict[str, str]:
    """受影响正文的**当前版本快照**（§9 冲突保护的基准）。

    `preview_plan()` 把它发给调用方（前端/上层），apply 时再原样传回 ⇒ "看过预览的那一版"
    与"落地时的盘上版本"必须一致，否则整批拒（人不基于过期版本写、agent 同样不）。
    """
    return {rel: rel_version(kb_path, rel) for rel in sorted({str(r) for r in rel_paths if str(r)})}


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


class _View:
    """**批内顺序视图**（`validate_plan()` / `preview_plan()` 共用）：把**前序 op 的效果**在内存里
    叠起来，让后面的 op 看见"这一刻的正文与文件存在性"。

    为什么要有它：真实意图常常**天然有先后** —— 先把正文写进去、再按**新**行号建知识点、再挂跳转；
    新建一个文件之后紧接着给它建点。旧实现每个 op 都只对着**盘上原文**校验，于是这类意图只能拆成
    两批提，而确认卡是人工点的 ⇒ "半路停下"。有了视图，**一批就能写完**；`apply.compile_plan()`
    也改成按 op 顺序逐条落地（同一条纪律）⇒ 校验期算出的行号与落地时逐 op 看到的行号是**同一套语义**。

    视图只管两件事：**正文行**与**文件是否存在**。sidecar（KP/links）与"前序 upsert_kp 建过的 id"
    分别由 `DocumentService.check_kp_id()` 与 `pending_ids` 负责，不在这里重复建模。
    """

    def __init__(self, kb_path: str) -> None:
        self._kb = kb_path
        self._lines: dict[str, list[str]] = {}
        self._created: set[str] = set()

    def exists(self, rel: str) -> bool:
        """视图里的存在性：本批 `create_file` 造出来的文件**立刻**算存在。"""
        return rel in self._created or os.path.isfile(os.path.join(self._kb, rel))

    @property
    def created(self) -> set[str]:
        """本批 `create_file` 建出来的相对路径（供"新文件的 stem 也算可解析"用）。"""
        return set(self._created)

    def lines(self, rel: str) -> list[str]:
        """这一刻的正文行：首次访问读盘，之后读视图（与 `_body_lines` 同一行空间）。"""
        if rel not in self._lines:
            self._lines[rel] = _body_lines(self._kb, rel)
        return list(self._lines[rel])

    def put(self, rel: str, lines: Sequence[str]) -> None:
        self._lines[rel] = list(lines) or [""]

    def seed(self, rel: str, body: str) -> None:
        """`create_file`：用初始正文把文件"种"进视图（同批后面的 op 立刻能按它算行号）。"""
        self._created.add(rel)
        self.put(rel, body.splitlines())

    def put_edit(self, rel: str, edit: Mapping) -> None:
        """把一条**已通过自检**的编辑施加到视图（与落地用的是**同一个** `splice()`）。"""
        text, _, _ = splice("\n".join(self.lines(rel)), [dict(edit)])
        self.put(rel, text.splitlines())


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
            # 2026-09-22：把"它在哪篇"一并说出来 —— `check_kp_id()` 本来就回了 `files`，此前只用了
            # `message` ⇒ 模型读到"目标 id 已存在"却不知道**该把 `file` 指向哪里**，真机里它反复用
            # 同一个错的 `file` 重提（`kp_id_taken` ×2）。
            where = "、".join(f"`{item}`" for item in (checked.get("files") or [])[:3])
            errors.append(
                _err(
                    op_id,
                    "kp_id_taken",
                    f"id `{kp_id}` 已经存在**在别的文档**里"
                    + (f"：{where}" if where else "")
                    + " —— 要**改**那个知识点，把 `file` 指向它所在的那一篇（本文件已有同 id 时可直接改）；"
                    "要**新建**，换一个 id。",
                )
            )
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


def _count_plain_occurrences(row: str, anchor: str) -> int:
    """该行里锚文本的**可挂接处数**（用与包裹同一个原子函数枚举，口径一致）。"""
    count = 0
    offset = 0
    while offset <= len(row):
        idx = find_plain_text_in_line(row[offset:], anchor)
        if idx < 0:
            break
        count += 1
        offset += idx + len(anchor)
    return count


def _validate_attach_links(
    kb_path: str,
    op: Mapping,
    lines: Sequence[str],
    op_id: str,
    errors: list[dict],
    warnings: list[dict],
    pending_targets: set[str],
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
        # 同一批内**前序** op 刚建出来的目标对后 op 可见（§2.3.3 信封注释："前 op 的结果
        # 对后 op 可见（可'先建点、后连边'）"）—— 否则"建点 + 连边"这种最常见的 plan 永远校验不过。
        # 两类：① 前序 `upsert_kp` 建的 KP id；② 前序 `create_file` 新建文件的 stem（视图口径）。
        if target in pending_targets:
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
    pinned_spans: dict[int, tuple[int, int]] = {}
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
            raw_col = row.get("col")
            if raw_col is not None:
                # **列级指定**（1 起列号）：同一行里锚文本出现多处时，只有它能说清"包哪一处"。
                # 这里就核对"该列起恰好是锚文本"——不符即拒（后端还会再核一次，双保险）。
                try:
                    col = int(raw_col)
                except (TypeError, ValueError):
                    errors.append(_err(op_id, "missing_field", "occurrences[].col 必须是整数（1 起列号）"))
                    continue
                start0 = col - 1
                text = lines[line - 1]
                if start0 < 0 or text[start0 : start0 + len(anchor)] != anchor:
                    errors.append(_err(op_id, "col_mismatch", f"第 {line} 行 C{col} 处不是锚文本：{anchor}"))
                    continue
                pinned_spans[line] = (start0, start0 + len(anchor))
            chosen.append(line)
    # 同行多处且**没给列** ⇒ 只能按行取值（哪一处由后端决定）：如实警告，不假装精确
    ambiguous = sorted(
        ln
        for ln in set(chosen)
        if ln not in pinned_spans and _count_plain_occurrences(lines[ln - 1], anchor) > 1
    )
    if ambiguous:
        warnings.append(
            _warn(
                op_id,
                "ambiguous_occurrence",
                f"这些行里锚文本出现多处且未给 col（{ambiguous}）⇒ 包裹哪一处由后端按行取值决定；"
                "要精确到某一处请给 occurrences[].col（1 起列号）",
            )
        )
    return {
        "action": "wrap" if chosen else "noop",
        "anchor_text": anchor,
        "targets": targets,
        "edge_type": edge_type or None,
        "lines": sorted(chosen),
        "pinned_spans": pinned_spans,
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


def _range_line(value: Any) -> Any:
    """`range.start` / `range.end` 取行号：`{"line": n}` 与裸 `n` 都接受（同 `upsert_kp` 的宽容口径）。"""
    return value.get("line") if isinstance(value, Mapping) else value


def _body_edit_spec(verb: str, op: Mapping) -> dict[str, Any]:
    """plan op → `body_edit` 的编辑形态（**只做形状映射**；结构/内容级自检都交给 body_edit）。"""
    if verb == OP_INSERT_LINES:
        return {
            "mode": MODE_INSERT,
            "after": op.get("after"),
            "expect": op.get("expect") or "",
            "text": str(op.get("text") or ""),
        }
    rng = _as_dict(op.get("range"))
    return {
        "mode": MODE_REPLACE if verb == OP_REPLACE_LINES else MODE_DELETE,
        "start": _range_line(rng.get("start")),
        "end": _range_line(rng.get("end")),
        "expect": op.get("expect") or "",
        "text": str(op.get("text") or ""),
    }


def _validate_body_edit(op: Mapping, verb: str, lines: Sequence[str], op_id: str, errors: list[dict]) -> dict:
    """`replace_lines` / `insert_lines` / `delete_lines` 的共同校验。

    两段自检**都复用 `body_edit` 的同一批函数**（`normalize_edits` 结构级 + `check_edit` 内容级），
    因此"校验时能过"与"落盘时能过"是同一套判据 —— 包含 `expect` 与**盘上原文**逐字相符这一条
    （与 `attach_links` 的 `anchor_text` 同款口径：**不猜**）。
    """
    spec = _body_edit_spec(verb, op)
    try:
        normalized = normalize_edits([spec])[0]
        check_edit(normalized, list(lines))
    except EditError as e:
        errors.append(_err(op_id, e.code, str(e)))
        return {"action": "invalid"}
    return {"action": normalized["mode"], "edit": normalized}


def _validate_insert_image_ref(kb_path: str, op: Mapping, lines: Sequence[str], op_id: str, errors: list[dict]) -> dict:
    """图片引用（§7 4.1）：把 `![alt](<路径> "属性")` 插在某行之后 —— 行由 `file_ops` 拼、落地走 `insert`。"""
    from memoria.services.agent.file_ops import image_ref_line

    spec: dict[str, Any] = {
        "mode": MODE_INSERT,
        "after": op.get("after"),
        "expect": op.get("expect") or "",
        "text": "",
    }
    try:
        if spec["after"] is None:
            raise EditError("missing_field", "缺 after（插在这一行之后；0 = 正文最前）")
        spec["text"] = image_ref_line(
            kb_path,
            str(op.get("path") or ""),
            str(op.get("alt") or ""),
            str(op.get("attrs") or ""),
        )
        normalized = normalize_edits([spec])[0]
        check_edit(normalized, list(lines))
    except EditError as e:
        errors.append(_err(op_id, e.code, str(e)))
        return {"action": "invalid"}
    return {"action": "insert_image_ref", "edit": normalized, "image": str(op.get("path") or "")}


def _validate_upsert_block(op: Mapping, lines: Sequence[str], op_id: str, errors: list[dict]) -> dict:
    """块级重建（§7 5.1 / 5.3 / 5.5）：先核"这段区间**恰好**是个 `kind` 类围栏块"，
    再把 `content` 重建成含围栏的整块文本，之后**完全按改正文那一套**自检与落地（`replace`）。

    这样"块级"只多一条**语义校验**（块边界 / 类型 / 内容不许提前收尾），落盘仍是同一个
    `edit_body` ⇒ 备份、整批回滚、审计、撤销、预览一致性的口径**一处都不用另写**。
    """
    kind = str(op.get("kind") or "").strip()
    rng = _as_dict(op.get("range"))
    spec: dict[str, Any] = {
        "mode": MODE_REPLACE,
        "start": _range_line(rng.get("start")),
        "end": _range_line(rng.get("end")),
        "expect": op.get("expect") or "",
    }
    try:
        start = int(spec["start"])
        end = int(spec["end"])
    except (TypeError, ValueError):
        errors.append(_err(op_id, "missing_field", "range.start.line / range.end.line 必须是整数（1 起行号）"))
        return {"action": "invalid"}
    try:
        bounds = block_bounds(list(lines), start, end, kind)
        want_lang = str(op.get("lang") or "").strip() or str(bounds.get("lang") or "")
        spec["text"] = rebuild_block(kind, str(op.get("content") or ""), want_lang)
        normalized = normalize_edits([spec])[0]
        check_edit(normalized, list(lines))
    except EditError as e:
        errors.append(_err(op_id, e.code, str(e)))
        return {"action": "invalid"}
    return {"action": "upsert_block", "kind": kind, "lang": want_lang, "edit": normalized}


def _validate_create_file(view: _View, rel: str, op: Mapping, op_id: str, errors: list[dict]) -> dict:
    """新建 `.md`：文件**必须不存在**（按**批内视图**判 —— 本批刚建过的也算已存在），`body` 可选。"""
    if view.exists(rel):
        errors.append(_err(op_id, "file_exists", f"文件已存在（新建请换路径）：{rel}"))
        return {"action": "invalid"}
    body = str(op.get("body") or "")
    return {"action": "create", "resolved": {"path": rel, "lines": len(body.splitlines())}}


def _validate_rename_file(kb_path: str, rel: str, op: Mapping, op_id: str, errors: list[dict]) -> dict:
    """重命名 `.md`：预演（`file_ops.rename_plan()`）给出的就是**落地时会牵动的文件集**。"""
    from memoria.services.agent.file_ops import rename_plan

    plan = rename_plan(kb_path, rel, str(op.get("new_name") or ""))
    if not plan.get("ok"):
        errors.append(_err(op_id, str(plan.get("code") or "rename_rejected"), str(plan.get("message") or "")))
        return {"action": "invalid"}
    return {
        "action": "rename",
        "resolved": {
            "from": plan["from"],
            "to": plan["to"],
            "kp_shadow": plan["kp_shadow"],
            "md_files": plan["md_files"],
            "sidecar_files": plan["sidecar_files"],
            "affected": plan["affected"],
        },
    }


#: 探测"这篇文档还写着 `[[stem]]` 吗"用的哨兵 id（`replace_link_id_in_markdown()` 在 old == new 时
#: **短路返回 0**，所以数引用必须传一个不可能撞上的名字；替换出来的文本直接丢掉）。
_DELETE_REF_PROBE = "\x00memoria-delete-probe"


def _still_references_ids(view: _View, other: str, ids: Sequence[str]) -> bool:
    """**批内视图**里这篇文档是否仍写着 `[[id]]`（任一命中即可）—— 同批前面的 op 可能已经改掉它。"""
    from memoria.services.kp_rename import replace_link_id_in_markdown

    if not view.exists(other):
        return False
    text = "\n".join(view.lines(other))
    return any(replace_link_id_in_markdown(text, target, _DELETE_REF_PROBE)[1] for target in ids)


def _validate_delete_file(
    kb_path: str, rel: str, op_id: str, errors: list[dict], warnings: list[dict], view: _View
) -> dict:
    """删除整篇 `.md`：**悬空正文引用先拦**（按批内视图算），侧车引用只**警告**。

    语义与取舍见 `services/agent/file_ops.delete_plan()` 头注（三条硬约束：引用先拦 / 侧车警告 /
    风险 op + 备份可撤销）。为什么正文引用要**按视图**再判一次：`delete_plan()` 读的是**盘上**原文，
    而同批前面的 op 完全可能已经把引用改掉了（比如先 `replace_lines` 摘掉 `[[旧名]]`）⇒ 只看盘上
    会误杀这个合法意图。
    """
    from memoria.services.agent.file_ops import delete_plan

    plan = delete_plan(kb_path, rel)
    if not plan.get("ok"):
        errors.append(_err(op_id, str(plan.get("code") or "delete_rejected"), str(plan.get("message") or "")))
        return {"action": "invalid"}
    ids = [str(item) for item in (plan.get("ids") or [])] or [str(plan.get("stem") or "")]
    ids_text = "、".join(f"`[[{item}]]`" for item in ids[:4])
    blockers = [other for other in (plan.get("referrers_md") or []) if _still_references_ids(view, other, ids)]
    if blockers:
        shown = "、".join(blockers[:5])
        more = f"（共 {len(blockers)} 篇）" if len(blockers) > 5 else ""
        errors.append(
            _err(
                op_id,
                "delete_referenced",
                f"还有文档用 {ids_text} 指向它{more}：{shown}。删除会让这些引用变成悬空 —— "
                "请先把这些引用删掉或改掉（**放在同一批里、这条删除之前**），再删这个文件。",
            )
        )
        return {"action": "invalid"}
    sidecars = list(plan.get("referrers_sidecar") or [])
    if sidecars:
        warnings.append(
            _warn(
                op_id,
                "delete_leaves_edges",
                f"{len(sidecars)} 篇文档的侧车里还挂着指向这儿列出的 id 的链接/边 —— 删除后它们会变成"
                "悬空目标（`validate_kb` / `audit_kb` 会报出来）。要一起清理就先 `detach_links`。",
            )
        )
    return {
        "action": "delete",
        "resolved": {"path": rel, "ids": ids, "affected": plan.get("affected") or []},
    }


def _validate_move_file(kb_path: str, rel: str, op: Mapping, op_id: str, errors: list[dict]) -> dict:
    """移动到另一目录：预演（`file_ops.move_plan()`）判定"能不能移"。**不猜**。

    唯一会拦人的语义条件是**正文里的"文件相对"链接/图片**（`move_breaks_relative_refs`）：移动只改目录、
    不改 stem ⇒ `[[id]]` 与库根相对的图片引用都不受影响，但按文件所在目录解析的写法会断 —— 那正是设计
    §6 R2 未落地的部分，所以宁可让模型先把引用改成库根相对，也不"移动后悄悄断掉"。
    """
    from memoria.services.agent.file_ops import move_plan

    plan = move_plan(kb_path, rel, str(op.get("to_dir") or ""))
    if not plan.get("ok"):
        errors.append(_err(op_id, str(plan.get("code") or "move_rejected"), str(plan.get("message") or "")))
        return {"action": "invalid"}
    return {
        "action": "move",
        "resolved": {"from": plan["from"], "to": plan["to"], "affected": plan["affected"]},
    }


# ── 2026-09-22 追加：三个 sidecar 结构 op 的校验（设计 §7 的 1.2 / 1.7 / 1.8）──────────────────
# 三者都只动 sidecar（`edges[]` / `knowledge_points[]`）或"KP id 这个名字"，**不改正文行数**；
# `rename_kp` 例外地会**全库改写正文里的 `[[旧 id]]`**（同一行内替换、行数不变，故它只受
# `PATH_MOVING_OPS` 的顺序规矩约束）。
#
# 校验一律**转调既有原子函数**（`resolve_link_target` / `file_ops.kp_referrers` /
# `kp_rename.rename_kp_in_kb(dry_run=True)`），不另写宽松判断（模块头纪律 2）。


def _edge_targets_of(edge: Mapping) -> list[str]:
    """一条边的目标列表（`targets` 允许是字符串或数组 —— 与 `document.create_edge()` 同口径）。"""
    raw = edge.get("targets")
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    return [str(item).strip() for item in _as_list(raw) if str(item).strip()]


def _validate_upsert_edge(
    kb_path: str, rel: str, op: Mapping, op_id: str, errors: list[dict], pending_targets: set[str]
) -> dict:
    """建一条 KP↔KP 的**纯边**（只写 sidecar `edges[]`，不碰正文）。

    四条前置全部在**计划期**说出来（别等落盘才报）：① `source_id` 必须是**本文档**的定义（
    `document.create_edge()` 的硬约束 —— 边只能从本文档的点出发）；② `target_id` 必须可解析
    （同批前序 `upsert_kp` 刚建出来的算数）；③ 边类型只收 `reference` / `extend`
    （`contain` 由标题层级自动推导、禁手标）；④ 同型同源同目标已存在 ⇒ 先拒（否则落到
    `create_edge()` 才报，整批回滚、信息不聚焦）。
    """
    source_id = str(op.get("source_id") or "").strip()
    target_id = str(op.get("target_id") or "").strip()
    raw_edge = op.get("edge_type")
    if not source_id:
        errors.append(_err(op_id, "missing_field", "缺 source_id（边从哪个 KP 出发）"))
    if not target_id:
        errors.append(_err(op_id, "missing_field", "缺 target_id（边指向哪个 KP / 文件）"))
    if source_id and source_id == target_id:
        errors.append(_err(op_id, "bad_field", "source_id 与 target_id 不能相同（边不指向自己）"))
    edge_type = EDGE_REFERENCE
    if raw_edge not in (None, ""):
        raw_key = str(raw_edge).strip().lower()
        if raw_key not in PLAN_EDGE_TYPES:
            errors.append(_err(op_id, "bad_edge_type", f"edge_type 只接受 reference / extend：{raw_edge!r}"))
        else:
            edge_type = normalize_link_edge_type(raw_key)
    if errors:
        return {"action": "invalid"}
    kp_ids = {
        str(kp.get("id") or "").strip()
        for kp in _as_list(_sidecar_of(kb_path, rel).get("knowledge_points"))
        if isinstance(kp, Mapping)
    }
    if source_id not in kp_ids and source_id not in pending_targets:
        errors.append(
            _err(op_id, "source_not_in_file", f"source_id 不是本文档的知识点：{source_id}（边只能从本文档的点出发）")
        )
    if target_id not in pending_targets and resolve_link_target(kb_path, target_id).get("status") != "ok":
        errors.append(_err(op_id, "target_not_found", f"边的目标不可解析：{target_id}"))
    if errors:
        return {"action": "invalid"}
    for edge in _as_list(_sidecar_of(kb_path, rel).get("edges")):
        if not isinstance(edge, Mapping):
            continue
        if (
            str(edge.get("source_id") or "").strip() == source_id
            and target_id in _edge_targets_of(edge)
            and not edge.get("no_build")
        ):
            errors.append(
                _err(op_id, "edge_exists", f"已经有 {source_id} → {target_id} 的边了（要改类型请先 `detach_edge`）")
            )
            break
    if errors:
        return {"action": "invalid"}
    return {
        "action": "upsert_edge",
        "resolved": {"source_id": source_id, "target_id": target_id, "edge_type": edge_type},
    }


def _validate_delete_kp(
    kb_path: str, rel: str, op: Mapping, op_id: str, errors: list[dict], warnings: list[dict]
) -> dict:
    """删一个 KP（只删 sidecar 里的配置、**不改正文**）。

    悬空引用**只警告不拦** —— 库规明确允许虚链（`kb-spec` §4「指向尚不存在的 id：保留为虚链」），
    这与 `delete_file` 对正文引用硬拦是**有意不同的分层**：那里整篇文件消失，这里只是少一个
    可解析目标。警告照旧给出可行动的清理手段（`detach_links` / 改引用）。
    """
    from memoria.services.agent.file_ops import kp_referrers

    kp_id = str(op.get("kp_id") or "").strip()
    if not kp_id:
        errors.append(_err(op_id, "missing_field", "缺 kp_id"))
        return {"action": "invalid"}
    kp = next(
        (
            item
            for item in _as_list(_sidecar_of(kb_path, rel).get("knowledge_points"))
            if isinstance(item, Mapping) and str(item.get("id") or "").strip() == kp_id
        ),
        None,
    )
    if kp is None:
        errors.append(_err(op_id, "kp_not_found", f"本文档的侧车里没有这个知识点：{kp_id}"))
        return {"action": "invalid"}
    hits = kp_referrers(kb_path, kp_id, owner=rel)
    targets = sorted(set(hits["md"]) | set(hits["sidecar"]))
    if targets:
        shown = "、".join(f"`{item}`" for item in targets[:5])
        more = f"（共 {len(targets)} 篇）" if len(targets) > 5 else ""
        warnings.append(
            _warn(
                op_id,
                "delete_leaves_dangling",
                f"还有 {len(targets)} 篇文档指向 `{kp_id}`{more}：{shown} —— 删除后它们会变成**悬空虚链**"
                "（库规允许，`validate_kb` 会报出来）。要一起清理就先 `detach_links` 或把引用改掉。",
            )
        )
    return {"action": "delete_kp", "resolved": {"kp_id": kp_id}}


def _validate_rename_kp(kb_path: str, op: Mapping, op_id: str, errors: list[dict]) -> dict:
    """KP id 全库改名（正文 `[[旧 id]]` + 各 sidecar 引用**一起**改）。**不带 `file`**。

    预演走 `kp_rename.rename_kp_in_kb(dry_run=True)` —— **同一份实现**、只是不落盘 ⇒ 校验期给出的
    "会改哪些文件"与落地时改的必然是同一份清单；那份清单也就是 apply 的 **pre-image 备份集**
    （全库级联会把正文与侧车一起改掉，撤销必须能逐篇还原）。
    """
    from memoria.services.kp_rename import rename_kp_in_kb

    old_id = str(op.get("old_id") or "").strip()
    new_id = str(op.get("new_id") or "").strip()
    if not old_id or not new_id:
        errors.append(_err(op_id, "missing_field", "缺 old_id / new_id（全库改 KP id）"))
        return {"action": "invalid"}
    preview = rename_kp_in_kb(kb_path, old_id, new_id, dry_run=True)
    if preview.get("status") != "ok":
        errors.append(_err(op_id, "rename_kp_rejected", str(preview.get("message") or "改名被拒")))
        return {"action": "invalid"}
    affected = [str(row.get("path") or "") for row in _as_list(preview.get("md_files")) if isinstance(row, Mapping)]
    affected += [str(item) for item in _as_list(preview.get("sidecar_files"))]
    return {
        "action": "rename_kp",
        "resolved": {
            "old_id": old_id,
            "new_id": new_id,
            "md_files": _as_list(preview.get("md_files")),
            "sidecar_files": _as_list(preview.get("sidecar_files")),
            "affected": sorted({item for item in affected if item}),
        },
    }


def _validate_rebuild_manifest(kb_path: str, op_id: str, errors: list[dict]) -> dict:
    """重建 `manifest.yaml`（`kb.manifest.rebuild`）。**不带 `file`**。零参数。

    前置硬闸与界面「构建」按钮**完全同一道**：库里有**未修复的路径变更** ⇒ 拒（`detect_path_moves()`
    会按内容 hash 把 manifest 的"删了 + 加了"配对成 rename/move —— 那种状态下直接重建，等于把
    "文件搬到哪儿去了"这条元数据抹掉）。挡在**计划期**比落到 `apply` 才整批回滚好：模型能拿着
    这条错误直接改意图（先 `move_file`/`rename_file` 把路径定下来，或请人点「修复路径」）。
    """
    from memoria.storage.path_cascade import detect_path_moves

    moves = detect_path_moves(kb_path)
    if moves:
        shown = "、".join(
            f"`{row.get('from')}` → `{row.get('to')}`" for row in moves[:3] if isinstance(row, Mapping)
        )
        more = f"（共 {len(moves)} 处）" if len(moves) > 3 else ""
        errors.append(
            _err(
                op_id,
                "manifest_blocked_by_path_moves",
                f"库里有 {len(moves)} 处**未修复的路径变更**{more}：{shown} —— 先把路径定下来"
                "（同一批里用 `move_file` / `rename_file`，或请人在界面上点「修复路径」）再重建清单；"
                "这种状态下直接重建会让这些文件的元数据路径无法恢复。",
            )
        )
        return {"action": "invalid"}
    return {"action": "rebuild_manifest", "resolved": {"path": ".memoria/manifest.yaml"}}


def _validate_op(
    kb_path: str,
    op: Any,
    service: Any,
    errors: list[dict],
    warnings: list[dict],
    pending_targets: set[str],
    view: _View,
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
        # 2026-09-22：**空动词单列一句** —— 真机里模型真发了不带 `op` 的项，回的是
        # `未知 op：''`（它读不出"我少写了一个字段"）⇒ 现在是点名的字段级指引。
        if not verb:
            errors.append(
                _err(op_id, "unknown_op", "这一项缺 `op` 字段 —— 每个 `ops[]` 元素都必须写明动词（见工具说明 ①–⑯）与 `op_id`")
            )
        else:
            errors.append(_err(op_id, "unknown_op", f"未知 op：{verb!r}（本版支持的动词见工具说明 ①–⑯）"))
        return {"op": verb, "op_id": op_id, "action": "invalid"}
    if verb not in COMPILED_OPS:
        warnings.append(_warn(op_id, "op_not_compiled", f"{verb} 尚未实现编译器分支（本轮只登记，不编译）"))
    if verb in (OP_RENAME_KP, OP_REBUILD_MANIFEST):
        # 两个**库级 op**：都**没有 `file` 字段**（它们不是一个文档的事）⇒ 必须在 `_safe_rel()` 之前
        # 分流，否则空路径会被判 `path_rejected`（同 `OP_CREATE_FILE` 之所以要提前分流的位置理由）。
        # 观察闸对它们**天然豁免**（`observation.write_targets()` 按 `file` 收集目标，空 `file` 不入表）——
        # 那道闸管"别盲写你没读过的那个文件"，而全库级动作不可能要求模型读完库里每一篇；
        # 它们各自的闸是：`rename_kp` = 审批卡（在 `RISKY_OPS` 里）+ 收尾规矩；
        # `rebuild_manifest` = 前置硬闸（有未修复路径变更即拒）+ 收尾规矩。
        if verb == OP_RENAME_KP:
            return {"op": verb, "op_id": op_id, **_validate_rename_kp(kb_path, data, op_id, errors)}
        return {"op": verb, "op_id": op_id, **_validate_rebuild_manifest(kb_path, op_id, errors)}
    rel = _safe_rel(kb_path, str(data.get("file") or ""))
    if rel is None:
        errors.append(_err(op_id, "path_rejected", f"file 不在允许根内或不是 .md：{data.get('file')!r}"))
        return {"op": verb, "op_id": op_id, "action": "invalid"}
    if verb == OP_CREATE_FILE:  # 新建：文件**不**应存在 ⇒ 不能走下面的"必须已存在"检查
        detail = _validate_create_file(view, rel, data, op_id, errors)
        if detail.get("action") == "create":
            # 把文件"种"进视图 ⇒ 同批后面按它算行号的 op（建点 / 挂链 / 改正文）立刻成立
            view.seed(rel, str(data.get("body") or ""))
        return {"op": verb, "op_id": op_id, "file": rel, **detail}
    if not view.exists(rel):
        errors.append(_err(op_id, "file_not_found", f"文件不存在：{rel}"))
        return {"op": verb, "op_id": op_id, "action": "invalid"}
    lines = view.lines(rel)  # **这一刻**的正文（含本批前序 op 的效果）
    if verb == OP_UPSERT_KP:
        detail = _validate_upsert_kp(kb_path, data, lines, service, op_id, errors)
    elif verb == OP_ATTACH_LINKS:
        detail = _validate_attach_links(kb_path, data, lines, op_id, errors, warnings, pending_targets)
    elif verb == OP_DETACH_LINKS:
        detail = _validate_detach_links(kb_path, data, lines, _sidecar_of(kb_path, rel), op_id, errors)
    elif verb in BODY_EDIT_OPS:
        if verb == OP_UPSERT_BLOCK:
            detail = _validate_upsert_block(data, lines, op_id, errors)
        elif verb == OP_INSERT_IMAGE_REF:
            detail = _validate_insert_image_ref(kb_path, data, lines, op_id, errors)
        else:
            detail = _validate_body_edit(data, verb, lines, op_id, errors)
    elif verb == OP_RENAME_FILE:
        detail = _validate_rename_file(kb_path, rel, data, op_id, errors)
    elif verb == OP_DELETE_FILE:
        detail = _validate_delete_file(kb_path, rel, op_id, errors, warnings, view)
    elif verb == OP_MOVE_FILE:
        detail = _validate_move_file(kb_path, rel, data, op_id, errors)
    elif verb == OP_UPSERT_EDGE:
        detail = _validate_upsert_edge(kb_path, rel, data, op_id, errors, pending_targets)
    elif verb == OP_DELETE_KP:
        detail = _validate_delete_kp(kb_path, rel, data, op_id, errors, warnings)
    else:
        detail = {"action": "uncompiled"}  # set_kp_range：M3b 才编译
    parsed = {"op": verb, "op_id": op_id, "file": rel, **detail}
    if isinstance(parsed.get("edit"), Mapping):
        view.put_edit(rel, parsed["edit"])  # 视图推进：后面的 op 按**改写后**的行号算
    return parsed


def validate_plan(kb_path: str, plan: Any, *, service: Any = None) -> dict:
    """结构 + 语义校验（**不碰盘**），错误按 `op_id` 返回；任一错误都会导致"拒整批"。

    `service` 传 `DocumentService` 时复用其 `check_kp_id()`（人类 UI 同一条唯一性判定）；
    缺省自建一个（会走既有的首次装载语义 —— 调用方在应用内应传已装载实例）。

    **按 op 顺序校验**（`_View`）：每个 op 面对的是"前序 op 生效之后"的正文与文件集，
    因此"先改正文 → 再按新行号建知识点 → 再挂跳转"、"先新建文件 → 再给它建点"这类天然有先后的
    意图都能**在一批里**写完（旧实现只对着盘上原文校验，硬要拆成两批 ⇒ 确认卡人手点，必然半路停下）。
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
    #: 同一批内**前序** op 建出来的"可解析目标"（"先建点、后连边"的可见性集合；§2.3.3）：
    #: ① 前序 `upsert_kp` 的 KP id；② 前序 `create_file` 新建文件的 **stem**（视图口径）。
    pending_targets: set[str] = set()
    view = _View(kb_path)
    for raw in _as_list(data.get("ops")):
        parsed = _validate_op(kb_path, raw, service, errors, warnings, pending_targets, view)
        oid = str(parsed.get("op_id") or "")
        if oid and oid in seen:
            errors.append(_err(oid, "duplicate_op_id", f"op_id 在 plan 内重复：{oid}"))
        if oid:
            seen.add(oid)
        if parsed.get("op") == OP_UPSERT_KP and parsed.get("kp_id"):
            pending_targets.add(str(parsed["kp_id"]))
        elif parsed.get("op") == OP_CREATE_FILE and parsed.get("action") == "create":
            rel = str(parsed.get("file") or "")
            if rel:
                pending_targets.add(os.path.splitext(os.path.basename(rel))[0])
        ops.append(parsed)
    _check_rename_last(ops, errors)
    return {
        "status": "error" if errors else "ok",
        "v": data.get("v"),
        "txid": data.get("txid"),
        "intent": data.get("intent"),
        "errors": errors,
        "warnings": warnings,
        "ops": ops,
    }


def _check_rename_last(ops: Sequence[Mapping], errors: list[dict]) -> None:
    """文件级 op / 全库 op 的**顺序规矩**（`move_file` / `rename_file` / `delete_file` / `rename_kp`）。

    两条，都由**语义**决定（不是审批）：

    1. **一旦出现这类 op，其后不得再出现非文件级 op** —— `move_file` / `rename_file` / `delete_file`
       改的是"路径"这个坐标系；`rename_kp`（2026-09-22 并入本表）改的是**全库正文里的 id 字符串**，
       而批内视图并不跟着改写 ⇒ 后面的按行号 / 按 `expect` 原文的 op 会同时活在两套坐标系里。
       **`move_file` 之间可以连排**：每篇只动自己那一篇与它的侧车，**不改写别人的正文**（名字没变 ⇒
       `[[…]]` 不用改）⇒ 一批移 N 篇是安全的。
    2. `rename_file` / `delete_file` 必须是**最后一条**：它们在语义上还会牵动**别的**文档
       （前者改写全库 `[[旧stem]]`、后者让指向它的引用失去落点）⇒ 只允许收尾。
       它之前的 op 照常可以与它同批（先写正文 / 建点 / 挂链，最后定名或删除）。
       `rename_kp` 只受第 1 条约束（它后面仍可跟文件级 op，比如"先改 id 再挪目录"）。
    3. **`rebuild_manifest` 必须是最后一条**（2026-09-22 增加）：它把磁盘上"这一刻的文件集"写成清单，
       之后任何改文件集的 op（`create_file` / `rename_file` / `delete_file` / `move_file`）都会让它
       立刻过期 —— 那正是它要消掉的那类警告。故与"收尾"同级，不许有后继。

    旧的另外两条约束**已删除**（写机制全线放开，2026-09-21）：
    - `file_op_alone`：`create_file` 不再要求单独成批 —— `_View` 会把新文件"种"进批内视图，
      同批后面按它算行号的 op（建点 / 挂链 / 改正文）立刻成立；
    - `body_edit_order`：改正文不再必须排在按行号锚定的 op 之后 —— 行号一律按**批内顺序视图**
      里"那一刻的正文"算，`compile_plan()` 也按同一顺序逐条落地；顺带取消了"同文件多条改正文
      区间不得重叠"（按序施加时重叠是有定义的：第二条面向第一条的结果）。
    """
    first_file_op = next(
        (index for index, parsed in enumerate(ops) if str(parsed.get("op") or "") in PATH_MOVING_OPS), None
    )
    if first_file_op is not None:
        for parsed in list(ops)[first_file_op + 1 :]:
            verb = str(parsed.get("op") or "")
            if verb in FILE_OPS:
                continue
            errors.append(
                _err(
                    str(parsed.get("op_id") or ""),
                    "file_ops_must_be_last",
                    "`move_file` / `rename_file` / `delete_file` / `rename_kp` 之后不能再有别的 op —— "
                    "前三个改的是「路径」坐标系、`rename_kp` 会全库改写正文里的 id，"
                    "后面的 op 会活在两套坐标系里（要移多篇可以**连排**多条 `move_file`）。"
                    "请把这些 op 挪到 ops 末尾后重提。",
                )
            )
            break
    for index, parsed in enumerate(ops):
        verb = str(parsed.get("op") or "")
        if verb not in (OP_RENAME_FILE, OP_DELETE_FILE):
            continue
        if index != len(ops) - 1:
            op_id = str(parsed.get("op_id") or "")
            if verb == OP_RENAME_FILE:
                errors.append(
                    _err(
                        op_id,
                        "rename_must_be_last",
                        "rename_file 会重写全库引用并搬动路径 ⇒ 它必须是本批**最后一个** op"
                        "（它之前的改动可以与它同批）。请把这条改名挪到 ops 末尾后重提。",
                    )
                )
            else:
                errors.append(
                    _err(
                        op_id,
                        "delete_must_be_last",
                        "delete_file 会让指向它的引用一起失去落点 ⇒ 它必须是本批**最后一个** op"
                        "（要清理的引用放在它之前）。请把这条删除挪到 ops 末尾后重提。",
                    )
                )
    # 2026-09-22 增加：`rebuild_manifest` 也要收尾（它把"这一刻的文件集"写成清单，后继任何改文件集的
    # op 都会让它立刻过期 —— 那正是它要消掉的那类警告）。
    for index, parsed in enumerate(ops):
        if str(parsed.get("op") or "") != OP_REBUILD_MANIFEST:
            continue
        if index != len(ops) - 1:
            errors.append(
                _err(
                    str(parsed.get("op_id") or ""),
                    "manifest_must_be_last",
                    "rebuild_manifest 记的是「**这一刻**磁盘上的文件集」 ⇒ 它必须是本批**最后一个** op"
                    "（建/改名/删除/移动都放在它之前）。请把它挪到 ops 末尾后重提。",
                )
            )


def preview_plan(kb_path: str, plan: Any, *, service: Any = None) -> dict:
    """**dry-run**：在内存里算出"将改哪些文件、哪些行"，**零落盘**。

    先跑 `validate_plan`，有错就原样返回（不预览一个非法 plan）。三个 M3a op 都给出
    `lines_changed` + 逐行 before/after：`attach_links` 用 `wrap_plain_on_lines()`、
    `detach_links` 用 `unwrap_lines()` —— **与落地路径同一个原子函数** ⇒ 预览不可能漂移。
    """
    checked = validate_plan(kb_path, plan, service=service)
    if checked["status"] != "ok":
        return {**checked, "previewed": False, "files": []}
    by_id = {str(op.get("op_id") or ""): op for op in _as_list(_as_dict(plan).get("ops"))}
    files: dict[str, dict] = {}
    view = _View(kb_path)  # 与校验同一套顺序视图 ⇒ diff 里每行都是**落地时那一刻**的行
    for parsed in checked["ops"]:
        op_id = str(parsed.get("op_id") or "")
        rel = str(parsed.get("file") or "")
        bucket = files.setdefault(rel, {"file": rel, "ops": [], "lines_changed": []})
        entry = {"op_id": op_id, "op": parsed.get("op"), "action": parsed.get("action")}
        if parsed.get("op") == OP_UPSERT_KP:
            entry["resolved"] = parsed.get("resolved")
        elif parsed.get("op") == OP_ATTACH_LINKS:
            lines = view.lines(rel)  # **这一刻**的正文（本批前序 op 的效果已叠加）
            anchor = str(parsed.get("anchor_text") or "")
            chosen = [int(x) for x in _as_list(parsed.get("lines"))]
            # plan 给了 `occurrences[].col` ⇒ 用**钉住的 span**试算（与 apply 阶段给后端的
            # `selected_spans` 同一份数据 ⇒ 预览与落地不可能漂移）；没给就交给包裹函数自己定位
            # （`find_plain_text_in_line()`，与校验阶段的候选行判定同一个原子函数）。
            pinned = {
                int(k): (int(v[0]), "", int(v[1]))
                for k, v in _as_dict(parsed.get("pinned_spans")).items()
            }
            new_body, wrapped = wrap_plain_on_lines(
                "\n".join(lines), anchor, chosen, line_spans=pinned or None
            )
            new_lines = new_body.split("\n")
            changed = [i + 1 for i in range(min(len(lines), len(new_lines))) if lines[i] != new_lines[i]]
            entry["diff_available"] = True
            entry["wrapped"] = wrapped
            entry["lines_changed"] = changed
            entry["diff"] = [
                {"line": ln, "before": lines[ln - 1], "after": new_lines[ln - 1]} for ln in changed
            ]
            bucket["lines_changed"] = sorted(set(bucket["lines_changed"]) | set(changed))
            view.put(rel, new_lines)  # 视图推进：后面的 op 看到的是包裹之后的正文
        elif parsed.get("op") == OP_DETACH_LINKS:
            lines = view.lines(rel)
            anchor = str(parsed.get("anchor_text") or "")
            chosen = [int(x) for x in _as_list(parsed.get("lines"))]
            # 与 `detach_link_instance()` 内部同一个原子函数（`unwrap_lines`）⇒ 预览不可能与落地漂移
            new_body, unwrapped = unwrap_lines("\n".join(lines), anchor, chosen)
            new_lines = new_body.split("\n")
            changed = [i + 1 for i in range(min(len(lines), len(new_lines))) if lines[i] != new_lines[i]]
            entry["diff_available"] = True
            entry["unwrapped"] = unwrapped
            entry["lines_changed"] = changed
            entry["diff"] = [
                {"line": ln, "before": lines[ln - 1], "after": new_lines[ln - 1]} for ln in changed
            ]
            bucket["lines_changed"] = sorted(set(bucket["lines_changed"]) | set(changed))
            view.put(rel, new_lines)
        elif parsed.get("op") in BODY_EDIT_OPS:
            body = "\n".join(view.lines(rel))  # **这一刻**的正文（前序 op 的效果已叠加）
            edit = parsed.get("edit") or {}
            # 与落地**同一个** `splice()`（`body_edit`）⇒ 预览给出的一定是真正会写下去的那几行
            new_body, changed, diff = splice(body, [edit])
            entry["diff_available"] = True
            entry["lines_changed"] = changed
            entry["diff"] = diff
            entry["mode"] = edit.get("mode")
            entry["lines_after"] = len(new_body.splitlines())
            view.put(rel, new_body.splitlines())
            if parsed.get("kind"):  # `upsert_block`：让卡片能显示"整块重建（kind / lang）"
                entry["block"] = {"kind": parsed.get("kind"), "lang": parsed.get("lang") or ""}
            if parsed.get("image"):  # `insert_image_ref`：卡片显示引用的是哪张图
                entry["image"] = parsed.get("image")
            bucket["lines_changed"] = sorted(set(bucket["lines_changed"]) | set(changed))
        elif parsed.get("op") == OP_CREATE_FILE:
            resolved = parsed.get("resolved") or {}
            body = str((by_id.get(op_id) or {}).get("body") or "")
            entry["diff_available"] = True
            entry["created"] = resolved.get("path") or rel
            entry["diff"] = [
                {"line": index + 1, "before": None, "after": line}
                for index, line in enumerate(body.splitlines())
            ]
            view.seed(rel, body)  # 视图推进：同批后面按这个新文件算行号的 op 才有 diff 可算
        elif parsed.get("op") == OP_RENAME_FILE:
            resolved = parsed.get("resolved") or {}
            cascade = list(resolved.get("md_files") or [])
            entry["diff_available"] = False  # 没有"行级"变化可算：给的是路径级 + 被牵连的正文清单
            entry["rename"] = {"from": resolved.get("from"), "to": resolved.get("to")}
            entry["cascade"] = cascade
            entry["diff"] = [{"line": None, "before": resolved.get("from"), "after": resolved.get("to")}] + [
                {"line": None, "before": None, "after": f"引用将改写：{item}"} for item in cascade
            ]
        elif parsed.get("op") == OP_DELETE_FILE:
            resolved = parsed.get("resolved") or {}
            loss = [str(item) for item in (resolved.get("ids") or [])]
            entry["diff_available"] = False  # 没有"行级"变化可算：给的是路径级 + 将失去落点的 id
            entry["delete"] = {"path": resolved.get("path") or rel, "ids": loss}
            entry["diff"] = [{"line": None, "before": rel, "after": None}] + [
                {"line": None, "before": None, "after": f"将失去落点：[[{item}]]"} for item in loss
            ]
        elif parsed.get("op") == OP_MOVE_FILE:
            resolved = parsed.get("resolved") or {}
            entry["diff_available"] = False  # 没有"行级"变化可算：给的是路径级（正文一字未改）
            entry["move"] = {"from": resolved.get("from"), "to": resolved.get("to")}
            entry["diff"] = [
                {"line": None, "before": resolved.get("from"), "after": resolved.get("to")}
            ]
        bucket["ops"].append(entry)
    return {
        **checked,
        "previewed": True,
        "files": [files[key] for key in sorted(files)],
        # 版本基准：调用方拿着它去 apply（apply 会再比一次 ⇒ 预览与落地之间被改过就整批拒）
        "base_versions": base_versions(kb_path, [str(op.get("file") or "") for op in checked["ops"]]),
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
