"""行级**正文**编辑（plan 原语 `kb.file.edit` 的实现）：**只动被点名的那些行**。

设计来源：`docs/design/agent-plugin-design.md §7` 的 2.1 / 2.2 / 2.3（「改正文段落 / 插入新段落 /
删除段落」）—— 那三行都标着「**需要新原语** `kb.file.edit`」，因为今天只有**整篇**入口
`DocumentService.save_document()`（`document.py:317`），没有行级入口。

三条硬口径：

1. **落盘仍走唯一入口** `DocumentService.save_document()` —— 保留 frontmatter、tmp + `os.replace`
   原子写、`_cache` 失效、manifest 记账全在那一处；本模块只负责"把正文算对"，**不自己开写路径**。
2. **只有被点名的行会变**：内部按 `splitlines(keepends=True)` 取行（带行尾），splice 后 `"".join()`
   ⇒ 未触及的行**逐字节**保持原样（不重排、不规范化换行、不动末尾空行与"最后一行无换行"的状态）。
   （`save_document` 会用已解析的 frontmatter **重新序列化** YAML —— 那是既有保存行为，人类编辑器
   同样如此；本模块不改它。）
3. **写前再核一次 `expect`**：`expect` 是调用方（plan）声明的"这几行现在是这个原文"；与**盘上**不符
   即拒（`expect_mismatch`）。它与 apply 的 `base_versions` 一起构成"文件级 + 内容级"双重过期保护。

编辑形态（`edits`，**1 起行号、含端点**）：

| mode | 字段 | 语义 |
|---|---|---|
| `replace` | `start`、`end`、`text`、`expect` | 用 `text`（可多行）替换 `start..end` 行 |
| `insert` | `after`、`text`、`expect` | 在 `after` 行**之后**插入 `text`（`after = 0` = 正文最前，此时 `expect` 必须为空） |
| `delete` | `start`、`end`、`expect` | 删除 `start..end` 行 |

多条编辑**一律按行号从大到小**应用 ⇒ 每条的行号都以"编辑前"的正文为准（调用方不必自己倒序、
也不会互相错位）。任何自检不过（越界 / 重叠 / `expect` 不符 / mode 未知）⇒ 抛 `EditError`，
**不猜、不改、不写**。
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any

from memoria.storage.markdown import strip_frontmatter

#: 编辑模式（只增不改）
MODE_REPLACE = "replace"
MODE_INSERT = "insert"
MODE_DELETE = "delete"
MODES: tuple[str, ...] = (MODE_REPLACE, MODE_INSERT, MODE_DELETE)

#: 错误信息里回显"盘上实际内容"的截断长度（够模型认出自己写错了，又不淹没结果）
_CLIP = 60


class EditError(ValueError):
    """一次编辑自检不过；`code` 是稳定错误码（plan 校验直接用它填 `errors[].code`）。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _clip(text: str) -> str:
    flat = (text or "").replace("\r", "").replace("\n", "⏎")
    return flat if len(flat) <= _CLIP else flat[:_CLIP] + "…"


def body_of(raw: str) -> str:
    """文件原文 → 正文（剥 frontmatter）。与 `plan._body_lines()` / `save_document()` 同一约定。"""
    body, _fm = strip_frontmatter(raw)
    return body


def _terminator(body: str) -> str:
    return "\r\n" if "\r\n" in body else "\n"


def _rows_of(text: str, term: str) -> list[str]:
    """把 `text` 切成**带行尾**的行；末尾单个换行只当终止符（不额外产生一个空行）。"""
    if not text:
        return []
    rows = text.split("\n")
    if rows and rows[-1] == "":
        rows.pop()
    return [row + term for row in rows]


def _line_of(spec: Any, *, field: str) -> int:
    """`{"line": n}` / 裸整数 → 正整数行号（1 起）。"""
    raw = spec.get("line") if isinstance(spec, Mapping) else spec
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise EditError("missing_field", f"{field} 必须是整数行号（1 起）") from exc
    return value


def edit_range(edit: Mapping) -> tuple[int, int]:
    """一条编辑**覆盖的旧行区间**（`insert` 视作锚点行自身，用于重叠检测与行号汇总）。"""
    mode = str(edit.get("mode") or "")
    if mode == MODE_INSERT:
        anchor = int(edit.get("after") or 0)
        return (max(anchor, 1), max(anchor, 1))
    return (_line_of(edit.get("start"), field="range.start"), _line_of(edit.get("end"), field="range.end"))


def _check_expect(plain: Sequence[str], start: int, end: int, expect: str, label: str) -> None:
    actual = "\n".join(plain[start - 1 : end])
    want = str(expect or "").replace("\r\n", "\n").strip("\n")
    if actual != want:
        raise EditError(
            "expect_mismatch",
            f"{label}：第 {start}-{end} 行的原文与 expect 不符（盘上现在是：{_clip(actual)}）",
        )


def _bounds(index: int, total: int, label: str) -> None:
    if index < 1 or index > total:
        raise EditError("range_out_of_bounds", f"{label}：行号越界（正文共 {total} 行）")


def normalize_edits(edits: Sequence[Mapping]) -> list[dict[str, Any]]:
    """逐条做**结构级**自检并规范化；返回按行号从大到小排好的副本（不碰正文）。

    结构级 = mode 已知 / 行号与 `after` 是整数 / 区间合法 / 文本非空 / 多条之间不重叠。
    """
    out: list[dict[str, Any]] = []
    for index, raw in enumerate(edits):
        edit = dict(raw)
        mode = str(edit.get("mode") or "")
        label = f"edits[{index}]"
        if mode not in MODES:
            raise EditError("bad_field", f"{label}：未知 mode {mode!r}（只允许 {MODES}）")
        text = str(edit.get("text") or "")
        if mode in (MODE_REPLACE, MODE_INSERT) and not text.strip():
            raise EditError("empty_text", f"{label}：text 不能为空（要删行请用 delete）")
        if mode == MODE_INSERT:
            if edit.get("after") is None:
                raise EditError("missing_field", f"{label}：缺 after（0 = 插到正文最前）")
            after = int(edit["after"])
            if after < 0:
                raise EditError("bad_field", f"{label}：after 不能为负（0 = 插到正文最前）")
            out.append({"mode": mode, "after": after, "expect": str(edit.get("expect") or ""), "text": text})
            continue
        start = _line_of(edit.get("start"), field=f"{label}.range.start")
        end = _line_of(edit.get("end"), field=f"{label}.range.end")
        if start < 1 or end < start:
            raise EditError("bad_field", f"{label}：行区间非法（start={start}, end={end}，须 1 ≤ start ≤ end）")
        out.append({"mode": mode, "start": start, "end": end, "expect": str(edit.get("expect") or ""), "text": text})
    out.sort(key=lambda item: int(item.get("start") or item.get("after") or 0), reverse=True)
    spans = [
        (int(item["start"]), int(item["end"])) for item in out if item["mode"] in (MODE_REPLACE, MODE_DELETE)
    ]
    for previous, current in zip(spans, spans[1:]):
        if current[1] >= previous[0]:
            raise EditError("overlapping_edits", f"两条编辑的行区间重叠：{current} 与 {previous}")
    return out


def check_edit(edit: Mapping, plain: Sequence[str]) -> None:
    """**内容级**自检（对给定的正文行空间）：行号界内 + `expect` 逐字相符。不符即抛 `EditError`。

    plan 校验（对读到的正文）与真正落盘（对**当下**盘上正文）用的是**同一个函数** ⇒ 两边口径
    不可能漂移。
    """
    total = len(plain)
    if str(edit.get("mode")) == MODE_INSERT:
        after = int(edit.get("after") or 0)
        if after > total:
            raise EditError("range_out_of_bounds", f"insert：after={after} 越界（正文共 {total} 行）")
        if after >= 1:
            _check_expect(plain, after, after, str(edit.get("expect") or ""), "insert")
        elif str(edit.get("expect") or "").strip():
            raise EditError("bad_field", "insert：after=0（插到最前）时不应给 expect")
        return
    start, end = int(edit.get("start") or 0), int(edit.get("end") or 0)
    _bounds(start, total, str(edit.get("mode")))
    _bounds(end, total, str(edit.get("mode")))
    _check_expect(plain, start, end, str(edit.get("expect") or ""), str(edit.get("mode")))



def splice(body: str, edits: Sequence[Mapping]) -> tuple[str, list[int], list[dict[str, Any]]]:
    """把若干条编辑应用到正文；返回 `(新正文, 受影响旧行号[升序], 逐行 diff)`。

    diff 行沿用既有确认卡的形状：删除的旧行给 `{line, before, after: null}`，
    新增行给 `{line, before: null, after}`（`line` 是**旧行空间**里的位置，便于人对照）。
    """
    term = _terminator(body)
    kept = body.splitlines(keepends=True)
    plain = body.splitlines()
    total = len(plain)
    if total == 0:  # 空正文：给一行空行当骨架，插入才有位置可言
        kept, plain, total = [""], [""], 1
    ordered = normalize_edits(edits)
    # **内容级自检全部先跑完**（都对着"编辑前"的正文行空间）—— 之后才动 `plain`/`kept`，
    # 这样每条编辑的行号语义始终是"编辑前"，多条之间不会互相错位。
    for edit in ordered:
        check_edit(edit, plain)
    changed: set[int] = set()
    diff: list[dict[str, Any]] = []
    trailing = body.endswith(("\n", "\r", "\v", "\f", "\u2028", "\u2029"))

    for edit in ordered:
        mode = edit["mode"]
        if mode == MODE_INSERT:
            after = int(edit["after"])
            rows = _rows_of(edit["text"], term)
            kept[after:after] = rows
            anchor = after + 1
            plain[after:after] = [row.rstrip("\r\n") for row in rows]
            changed.add(anchor)
            for row in rows:
                diff.append({"line": anchor, "before": None, "after": row.rstrip("\r\n")})
            continue
        start, end = int(edit["start"]), int(edit["end"])
        changed.update(range(start, end + 1))
        for line in range(start, end + 1):
            diff.append({"line": line, "before": plain[line - 1], "after": None})
        rows = _rows_of(edit["text"], term) if mode == MODE_REPLACE else []
        kept[start - 1 : end] = rows
        plain[start - 1 : end] = [row.rstrip("\r\n") for row in rows]
        for offset, row in enumerate(rows):
            diff.append({"line": start + offset, "before": None, "after": row.rstrip("\r\n")})

    new_body = "".join(kept)
    # 末尾换行状态：原来有就保留、原来没有就别多出来（只看最后一行有没有行尾）
    if new_body:
        ends_with_break = new_body.endswith(("\n", "\r", "\v", "\f", "\u2028", "\u2029"))
        if trailing and not ends_with_break:
            new_body += term
        elif not trailing and ends_with_break:
            new_body = new_body.rstrip("\r\n")
    diff.sort(key=lambda row: (int(row["line"]), 0 if row["before"] is not None else 1))
    return new_body, sorted(changed), diff


def apply_body_edits(service: Any, rel_path: str, edits: Sequence[Mapping]) -> dict:
    """原语入口：读**盘上**正文 → `splice()` → 经 `DocumentService.save_document()` 写回。

    `expect` 在这一步再核一次（对的是**当下**盘上内容）⇒ 即便 version 令牌之后有人插队，
    被点名的行一变也会立刻拒（`expect_mismatch`），不会把别人的改动覆盖掉。
    """
    kb_path = getattr(service, "kb_path", None)
    if not kb_path:
        return {"status": "error", "code": "no_kb", "message": "未打开知识库"}
    full = os.path.join(kb_path, rel_path)
    try:
        with open(full, "r", encoding="utf-8") as handle:
            raw = handle.read()
    except OSError as e:
        return {"status": "error", "code": "read_failed", "message": f"读取失败：{e}"}
    body = body_of(raw)
    try:
        new_body, changed, diff = splice(body, edits)
    except EditError as e:
        return {"status": "error", "code": e.code, "message": str(e)}
    if new_body == body:
        return {"status": "ok", "rel_path": rel_path, "lines_changed": [], "diff": [], "no_change": True}
    written = service.save_document(rel_path, new_body)
    if not isinstance(written, Mapping) or written.get("status") != "ok":
        return {
            "status": "error",
            "code": "write_failed",
            "message": str((written or {}).get("message") or "保存失败"),
            "lines_changed": changed,
        }
    return {
        "status": "ok",
        "rel_path": rel_path,
        "lines_changed": changed,
        "diff": diff,
        "lines": len(new_body.splitlines()),
    }
