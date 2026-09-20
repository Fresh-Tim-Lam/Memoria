"""引用板块（R 线）的离线单测：只读引用解析 `resolve_reference` + 只读引用审计 `audit_references`。

口径来源：`docs/design/agent-capabilities.md` §6.5「引用完整性：让模型写的路径真的可用（P / V / L 三路线）」
（台账行 `docs/todo.md:265` 的 AG07）。覆盖：

① 五类库内引用各有「可解析 / 悬空 / 多义 / 越界拒绝」样例：`@路径`（含 `@"带空格"` 与目录尾斜杠）、
   `dsh-session:`、`[[…]]`、`文件:行号`（含 `#L12-L30` 区间 —— **L 路线读时投影已落地**：正常回 `ok`、
   倒置回 `invalid`、任一端越界回 `not_found`）、`![](...)`；
② V2 分级收敛（精确 → 唯一 basename → 唯一后缀）与「任一级 >1 即 `ambiguous` 并不猜」；
③ V1 归一化（NFKC / 剥包裹标点 / 去 `./`）与 `@a.md（说明）` 这类正文标注的截断；
④ `audit_references` 在 fixture 库上同时报出多种问题：条数、检查名、形状与「已达上限」提示；
⑤ 两工具注册进 `KB_TOOL_NAMES`、声明 `read_only=True`、schema `additionalProperties:false`；
⑥ 边界：空参数 / 未知 kind / 超长输入 / 未知引用形态 / `path` 越界与不存在；
⑦ 零写入：调用前后库内文件清单逐字不变。
"""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from memoria.services.agent.llm import ToolCall
from memoria.services.agent.session.reference import encode_session_uri
from memoria.services.agent.tools import (
    INVALID_ARGUMENTS_CODE,
    KB_TOOL_NAMES,
    ToolRegistry,
    build_kb_tools,
)
from memoria.services.agent.tools.kb import (
    REFERENCE_AUDIT_MAX_ISSUES,
    REFERENCE_KINDS,
    REFERENCE_MAX_CHARS,
    _audit_references,
    _resolve_reference,
)

URI_OK = encode_session_uri("demo-s1")
URI_ZOMBIE = encode_session_uri("nope-9")
URI_ILLEGAL_ID = encode_session_uri("../evil")

#: 「脏」文档：五类引用各含正常 + 坏样例（行号即断言用的位置锚）。
DIRTY_MD = "\n".join(
    [
        "# A 文档",
        "",
        "见 @notes/b.md 与 @notes/missing.md。",
        "",
        '越界引用 @../outside.md 与 @"notes/A B.md"。',
        "",
        "多义 @same.md（dup1 / dup2 各一份），目录 @notes/ 与 @nodir/。",
        "",
        "[[b-kp]] 与 [[ghost]] 与 [[dup-kp]]。",
        "",
        "参考 notes/c.md:3、notes/c.md:999、notes/c.md#L2-L4。",
        "",
        "![pic](.memoria/images/pic.png)",
        "![gone](.memoria/images/nope.png)",
        "![sp](.memoria/images/my pic.png)",
        "![unreg](.memoria/images/unregistered.png)",
        "",
        f"会话 @[上次]({URI_OK})、@[坏](dsh-session:%%%)、@[僵尸]({URI_ZOMBIE})、@[越界]({URI_ILLEGAL_ID})。",
        "",
        "区间倒置 notes/c.md#L5-L3、区间越界 notes/c.md#L2-L999（末尾追加，不动上方行号锚）。",
        "",
    ]
)

#: 全库审计在 fixture 上应当报出的问题分布（逐条与 `_REFERENCE_AUDIT_CHECKS` 的检查名对齐）。
EXPECTED_CHECKS = {
    "file_reference.missing": 2,  # @notes/missing.md（悬空文件）+ @nodir/（悬空目录）
    "file_reference.outside_root": 1,  # @../outside.md
    "file_reference.ambiguous": 1,  # @same.md → dup1/same.md、dup2/same.md
    "session_reference.invalid_uri": 1,  # dsh-session:%%%
    "session_reference.invalid_id": 1,  # 规范 URI 但 id 含 `..`
    "session_reference.session_not_found": 1,  # nope-9
    "kp_link.body_not_attached": 3,  # [[b-kp]] / [[ghost]] / [[dup-kp]]
    "kp_link.unresolved_target": 1,  # [[ghost]]
    "kp_link.ambiguous_target": 1,  # [[dup-kp]]（两文件同 id）
    "anchor.line_out_of_range": 2,  # notes/c.md:999 + 区间末端越界 notes/c.md#L2-L999
    "anchor.range_inverted": 1,  # 区间倒置 notes/c.md#L5-L3（L 路线落地后才可校验）
    "image.unregistered": 1,  # ![sp](.memoria/images/my pic.png)
    "image.missing": 1,  # ![gone](...)
    "image.not_registered": 1,  # ![unreg](.memoria/images/unregistered.png)
}


def _sidecar(
    rel: str,
    kp_id: str,
    start_snippet: str,
    end_snippet: str,
    end_line: int,
    *,
    name: str | None = None,
) -> str:
    return "\n".join(
        [
            "schema_version: 1",
            f"file: {rel}",
            "knowledge_points:",
            f"- id: {kp_id}",
            f"  name: {name or kp_id}",
            "  range:",
            "    start:",
            f"      snippet: '{start_snippet}'",
            "      line_hint: 1",
            "    end:",
            f"      snippet: '{end_snippet}'",
            f"      line_hint: {end_line}",
            "links: []",
            "edges: []",
            "",
        ]
    )


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    """最小知识库：脏文档 + 五类引用的正常/坏样例 + 会话文件 + 图片注册表。"""
    root = tmp_path / "kb"
    for sub in (
        "notes",
        "sub",
        "dup1",
        "dup2",
        ".memoria/images",
        ".memoria/sidecars/notes",
        ".memoria/sidecars/dup1",
        ".memoria/sidecars/dup2",
        ".memoria/agent/sessions",
    ):
        (root / sub).mkdir(parents=True, exist_ok=True)

    (root / "notes" / "a.md").write_text(DIRTY_MD, encoding="utf-8")
    (root / "notes" / "b.md").write_text("# B 文档\n\n乙知识点正文。\n", encoding="utf-8")
    (root / "notes" / "A B.md").write_text("# 带空格\n\n含空格的路径。\n", encoding="utf-8")
    (root / "sub" / "c.md").write_text("# C 文档\n\n第一行。\n第二行。\n第三行。\n第四行。\n", encoding="utf-8")
    for dup in ("dup1", "dup2"):
        (root / dup / "same.md").write_text(f"# {dup}\n\n同一 id 的另一处。\n", encoding="utf-8")
        (root / ".memoria" / "sidecars" / dup / "same.memoria.yaml").write_text(
            _sidecar(f"{dup}/same.md", "dup-kp", f"# {dup}", "同一 id 的另一处。", 3), encoding="utf-8"
        )
    (root / ".memoria" / "sidecars" / "notes" / "b.memoria.yaml").write_text(
        _sidecar("notes/b.md", "b-kp", "# B 文档", "乙知识点正文。", 3, name="乙知识点"), encoding="utf-8"
    )

    for name in ("pic.png", "my pic.png", "unregistered.png"):
        (root / ".memoria" / "images" / name).write_bytes(PNG_BYTES)
    (root / ".memoria" / "images" / "registry.json").write_text(
        json.dumps({"refs": {"pic.png": ["notes/a.md"]}}, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    header = {
        "v": 1,
        "type": "session/header",
        "time": 1,
        "data": {"id": "demo-s1", "createdAt": 1, "kb": str(root), "agent": "memoria-agent-loop"},
    }
    turn = {"v": 1, "type": "user/message", "seq": 0, "time": 2, "data": {"text": "第一句提问"}}
    (root / ".memoria" / "agent" / "sessions" / "demo-s1.jsonl").write_text(
        json.dumps(header, ensure_ascii=False) + "\n" + json.dumps(turn, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return root


def registry_for(kb: Path) -> ToolRegistry:
    return ToolRegistry(build_kb_tools(str(kb)))


def invoke(kb: Path, name: str, **arguments: Any) -> Any:
    return registry_for(kb).invoke(ToolCall(id="c1", name=name, arguments=json.dumps(arguments)))


def status_line(text: str) -> str:
    return next(row for row in text.splitlines() if row.startswith("- 状态："))


def issue_rows(text: str) -> list[str]:
    return [row for row in text.splitlines() if row.startswith("- [")]


def checks_of(text: str) -> Counter:
    """`- [severity] <check> @ <where> …` → 检查名计数（split 三段：`-`、`[severity]`、检查名）。"""
    return Counter(row.split()[2] for row in issue_rows(text))


def snapshot(root: Path) -> list[str]:
    out: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            out.append(os.path.relpath(os.path.join(dirpath, name), root).replace("\\", "/"))
    return sorted(out)


# —— ① `@路径` ——


def test_file_reference_exact_suffix_and_quoted_space(kb: Path) -> None:
    exact = invoke(kb, "resolve_reference", reference="@notes/b.md")
    assert not exact.is_error
    assert "类型：file" in exact.content and "状态：ok" in exact.content
    assert "知识库文档 notes/b.md（共 3 行，1 个知识点）" in exact.content
    assert 'read_document(path="notes/b.md")' in exact.content

    # V2 唯一后缀收敛：`sub/c.md` 未写目录 ⇒ 收敛到 sub/c.md
    converged = invoke(kb, "resolve_reference", reference="@c.md")
    assert "状态：ok" in converged.content
    assert "归一化目标：sub/c.md" in converged.content
    assert "按唯一 unique_basename 收敛" in converged.content

    # `@"…"` 含空格（上游 formatFileMention 形态）+ 目录尾斜杠
    quoted = invoke(kb, "resolve_reference", reference='@"notes/A B.md"')
    assert "状态：ok" in quoted.content and "归一化目标：notes/A B.md" in quoted.content
    directory = invoke(kb, "resolve_reference", reference="@notes/")
    assert "状态：ok" in directory.content and "目录 notes/（其下 3 个文件）" in directory.content


def test_file_reference_missing_ambiguous_and_escape(kb: Path) -> None:
    missing = invoke(kb, "resolve_reference", reference="@notes/missing.md")
    assert "状态：not_found" in missing.content
    assert "三级都未命中" in missing.content

    ambiguous = invoke(kb, "resolve_reference", reference="@same.md")
    assert "状态：ambiguous" in ambiguous.content
    assert "dup1/same.md" in ambiguous.content and "dup2/same.md" in ambiguous.content
    assert "程序不猜" in ambiguous.content

    escaped = invoke(kb, "resolve_reference", reference="@../outside.md")
    assert "状态：rejected" in escaped.content and "fail-closed" in escaped.content

    no_dir = invoke(kb, "resolve_reference", reference="@nodir/")
    assert "状态：not_found" in no_dir.content and "库内没有该目录" in no_dir.content

    # 正文标注不是路径：`@same.md（…）` 归一化时截断到 `（`
    assert "归一化目标：same.md" in invoke(kb, "resolve_reference", reference="@same.md（说明）").content


# —— ② 会话引用 ——


def test_session_reference_ok_not_found_invalid_and_illegal_id(kb: Path) -> None:
    ok = invoke(kb, "resolve_reference", reference=f"@[上次]({URI_OK})")
    assert "类型：session" in ok.content and "状态：ok" in ok.content
    assert "会话 `demo-s1`（标题：第一句提问）" in ok.content

    bare = invoke(kb, "resolve_reference", reference=URI_OK)  # 裸 URI 也认
    assert "状态：ok" in bare.content

    zombie = invoke(kb, "resolve_reference", reference=f"@[僵尸]({URI_ZOMBIE})")
    assert "状态：not_found" in zombie.content and "会话按库分" in zombie.content

    bad_uri = invoke(kb, "resolve_reference", reference="@[坏](dsh-session:%%%)")
    assert "状态：invalid" in bad_uri.content and "URI 非规范" in bad_uri.content

    illegal = invoke(kb, "resolve_reference", reference=f"@[越界]({URI_ILLEGAL_ID})")
    assert "状态：rejected" in illegal.content and "会话 id 非法" in illegal.content


# —— ③ `[[…]]` ——


def test_kp_link_ok_unresolved_and_ambiguous(kb: Path) -> None:
    ok = invoke(kb, "resolve_reference", reference="[[b-kp]]")
    assert "类型：kp_link" in ok.content and "状态：ok" in ok.content
    assert "b-kp（乙知识点）· notes/b.md:1" in ok.content
    assert "别名" in ok.content  # 别名/挂接需文档上下文 ⇒ 指向 audit_references

    ghost = invoke(kb, "resolve_reference", reference="[[ghost]]")
    assert "状态：not_found" in ghost.content
    assert "未找到知识点或文件: ghost" in ghost.content  # 复用 resolve_link_target() 的原文口径

    ambiguous = invoke(kb, "resolve_reference", reference="[[dup-kp]]")
    assert "状态：ambiguous" in ambiguous.content
    assert "dup1/same.md:1" in ambiguous.content and "dup2/same.md:1" in ambiguous.content

    # 显式 kind 与自动识别一致
    forced = invoke(kb, "resolve_reference", reference="[[b-kp]]", kind="kp_link")
    assert "状态：ok" in forced.content


# —— ④ 锚点 ——


def test_anchor_ok_range_ok_inverted_out_of_range_and_escape(kb: Path) -> None:
    ok = invoke(kb, "resolve_reference", reference="notes/c.md:3")
    assert "类型：anchor" in ok.content and "状态：ok" in ok.content
    assert "sub/c.md 第 3 行：第一行。" in ok.content

    # 全角冒号 + `L` 前缀（AG07 登记的口径）
    fullwidth = invoke(kb, "resolve_reference", reference="notes/c.md：L4")
    assert "状态：ok" in fullwidth.content and "第 4 行" in fullwidth.content

    beyond = invoke(kb, "resolve_reference", reference="notes/c.md:999")
    assert "状态：not_found" in beyond.content and "正文共 6 行" in beyond.content

    # L 路线（读时投影）：区间解析到**当前正文行**并校验两端（本轮从 `unsupported` 升级为 `ok`）
    ranged = invoke(kb, "resolve_reference", reference="notes/c.md#L2-L4")
    assert "状态：ok" in ranged.content
    assert "sub/c.md 第 2-4 行（3 行）" in ranged.content
    assert "末行 第二行。" in ranged.content
    assert 'read_document(path="sub/c.md", offset=2, limit=3)' in ranged.content

    # 选区引用 token：`@路径#L12-L30`（含单行 `#L12`）与 `@"带空格 路径"#L12-L30`
    at_ranged = invoke(kb, "resolve_reference", reference="@notes/c.md#L2-L4")
    assert "状态：ok" in at_ranged.content and "第 2-4 行" in at_ranged.content
    at_single = invoke(kb, "resolve_reference", reference="@notes/c.md#L4")
    assert "状态：ok" in at_single.content and "第 4 行：第二行。" in at_single.content
    spaced = invoke(kb, "resolve_reference", reference='@"notes/A B.md"#L1-L2')
    assert "状态：ok" in spaced.content and "notes/A B.md 第 1-2 行" in spaced.content

    # 区间倒置 ⇒ `invalid`（明确报错，不猜）
    inverted = invoke(kb, "resolve_reference", reference="notes/c.md#L5-L3")
    assert "状态：invalid" in inverted.content and "行区间倒置" in inverted.content
    assert "@notes/c.md#L5-L3" not in inverted.content  # 不含正文，只回行号与建议

    # 区间任一端越界 ⇒ `not_found`（报出越界的那一端）
    over_end = invoke(kb, "resolve_reference", reference="notes/c.md#L2-L999")
    assert "状态：not_found" in over_end.content and "第 999 行超出" in over_end.content
    over_start = invoke(kb, "resolve_reference", reference="notes/c.md#L0-L2")
    assert "状态：not_found" in over_start.content and "第 0 行超出" in over_start.content

    escaped = invoke(kb, "resolve_reference", reference="../outside.md:3")
    assert "状态：rejected" in escaped.content

    missing_file = invoke(kb, "resolve_reference", reference="ghost.md:3")
    assert "状态：not_found" in missing_file.content and "锚点文件在库内不存在" in missing_file.content


# —— ⑤ 图片 ——


def test_image_ok_missing_unregistered_and_registry_absent(kb: Path) -> None:
    ok = invoke(kb, "resolve_reference", reference="![pic](.memoria/images/pic.png)")
    assert "类型：image" in ok.content and "状态：ok" in ok.content
    assert "registry.json 已登记（引用方：notes/a.md）" in ok.content

    missing = invoke(kb, "resolve_reference", reference="![gone](.memoria/images/nope.png)")
    assert "状态：not_found" in missing.content

    # 裸 URL 含空白 ⇒ 注册规则识别不到（保存时可能被当作未引用清理）
    unregistered = invoke(kb, "resolve_reference", reference="![sp](.memoria/images/my pic.png)")
    assert "状态：invalid" in unregistered.content
    assert "归一化目标：.memoria/images/my pic.png" in unregistered.content
    assert "尖括号形式" in unregistered.content

    escaped = invoke(kb, "resolve_reference", reference="![x](../../x.png)")
    assert "状态：unsupported" in escaped.content  # 非库内图片引用：明确说「不支持」而不是瞎解析

    # 注册表缺失：登记状态无法判定，但文件存在仍算 ok（不伪造「已登记」）
    os.remove(kb / ".memoria" / "images" / "registry.json")
    absent = invoke(kb, "resolve_reference", reference="![pic](.memoria/images/pic.png)")
    assert "状态：ok" in absent.content and "registry.json` 缺失" in absent.content


# —— ⑥ 边界 ——


def test_resolve_reference_argument_boundaries(kb: Path) -> None:
    empty = invoke(kb, "resolve_reference", reference="")
    assert empty.is_error and empty.output.code == INVALID_ARGUMENTS_CODE

    missing_arg = invoke(kb, "resolve_reference")
    assert missing_arg.is_error and missing_arg.output.code == INVALID_ARGUMENTS_CODE

    unknown_kind = invoke(kb, "resolve_reference", reference="notes/c.md:3", kind="bogus")
    assert unknown_kind.is_error and unknown_kind.output.code == INVALID_ARGUMENTS_CODE

    oversized = invoke(kb, "resolve_reference", reference="x" * (REFERENCE_MAX_CHARS + 1))
    assert oversized.is_error and oversized.output.code == INVALID_ARGUMENTS_CODE
    assert "reference 过长" in oversized.content

    undetectable = invoke(kb, "resolve_reference", reference="just some words")
    assert undetectable.is_error and undetectable.output.code == INVALID_ARGUMENTS_CODE
    assert "无法识别引用类型" in undetectable.content

    # 直连工具体（绕过 schema 校验）时按同一语义失败
    direct_empty = _resolve_reference(str(kb), "")
    assert direct_empty.error and direct_empty.code == INVALID_ARGUMENTS_CODE
    direct_kind = _resolve_reference(str(kb), "notes/c.md:3", "bogus")
    assert direct_kind.error and "未知 kind" in direct_kind.text
    direct_long = _resolve_reference(str(kb), "x" * (REFERENCE_MAX_CHARS + 1))
    assert direct_long.error and f"上限 {REFERENCE_MAX_CHARS}" in direct_long.text

    extra_arg = invoke(kb, "resolve_reference", reference="notes/c.md:3", nope=1)
    assert extra_arg.is_error and extra_arg.output.code == INVALID_ARGUMENTS_CODE


# —— ⑦ 审计 ——


def test_audit_reports_every_reference_class_with_shape_and_cap_note(kb: Path) -> None:
    result = invoke(kb, "audit_references")
    assert not result.is_error
    assert "扫描 全库 6 篇 .md" in result.content  # notes/a.md、notes/b.md、notes/A B.md、sub/c.md、dup1+dup2/same.md

    counts = checks_of(result.content)
    assert dict(counts) == EXPECTED_CHECKS
    total = sum(EXPECTED_CHECKS.values())
    assert f"发现 {total} 个引用问题" in result.content
    assert "error 7 / warning 11" in result.content

    # 每条问题的形状：检查名 / 位置（文件:行）/ 目标 / 问题
    rows = issue_rows(result.content)
    assert len(rows) == total
    for row in rows:
        assert " 目标 " in row and "：" in row
    assert "- [error] file_reference.missing @ notes/a.md:3 目标 @notes/missing.md：" in result.content
    assert "- [warning] file_reference.ambiguous @ notes/a.md:7 目标 @same.md：" in result.content
    assert "- [warning] anchor.line_out_of_range @ notes/a.md:11 目标 notes/c.md:999：" in result.content
    assert "- [error] session_reference.invalid_id @ notes/a.md:18 目标 ../evil：" in result.content
    # 可复现的检查名清单
    assert "检查名（可用 resolve_reference 逐个复现）：file_reference.missing" in result.content
    assert "image.not_registered" in result.content
    assert "已达上限" not in result.content  # 未到顶 ⇒ 不出现上限提示


def test_audit_caps_issues_and_says_so(kb: Path) -> None:
    capped = invoke(kb, "audit_references", limit=3)
    assert len(issue_rows(capped.content)) == 3
    assert f"发现 {sum(EXPECTED_CHECKS.values())} 个引用问题（已列 3 条" in capped.content
    assert "（已达上限 3 条：还有" in capped.content and "请用 `path` 参数收窄" in capped.content

    bad_limit = invoke(kb, "audit_references", limit=REFERENCE_AUDIT_MAX_ISSUES + 1)
    assert bad_limit.is_error and bad_limit.output.code == INVALID_ARGUMENTS_CODE
    direct = _audit_references(str(kb), None, 0)
    assert direct.error and "limit 必须是" in direct.text


def test_audit_path_scope_and_argument_errors(kb: Path) -> None:
    clean = invoke(kb, "audit_references", path="sub/c.md")
    assert not clean.is_error and clean.content == "引用审计：扫描 指定文档 `sub/c.md`，未发现引用问题。"

    scoped = invoke(kb, "audit_references", path="notes/a.md")
    assert "扫描 指定文档 `notes/a.md`" in scoped.content
    assert dict(checks_of(scoped.content)) == EXPECTED_CHECKS

    missing = invoke(kb, "audit_references", path="notes/nope.md")
    assert missing.is_error and missing.output.code == "NOT_FOUND"

    for bad in ("../outside.md", "notes/b.txt"):
        out = invoke(kb, "audit_references", path=bad)
        assert out.is_error and out.output.code == INVALID_ARGUMENTS_CODE, bad

    extra = invoke(kb, "audit_references", nope="x")
    assert extra.is_error and extra.output.code == INVALID_ARGUMENTS_CODE


# —— ⑧ 注册 / schema / 只读 ——


def test_reference_tools_registered_declared_and_read_only(kb: Path) -> None:
    built = build_kb_tools(str(kb))
    assert tuple(tool.name for tool in built) == KB_TOOL_NAMES
    assert KB_TOOL_NAMES[-2:] == ("resolve_reference", "audit_references")

    registry = registry_for(kb)
    for name in ("resolve_reference", "audit_references"):
        tool = registry.get(name)
        assert tool is not None and tool.read_only
        assert tool.parameters["additionalProperties"] is False

    schemas = {schema.name: schema.parameters for schema in registry.schemas()}
    assert set(schemas["resolve_reference"]["properties"]) == {"reference", "kind"}
    assert schemas["resolve_reference"]["required"] == ["reference"]
    assert tuple(schemas["resolve_reference"]["properties"]["kind"]["enum"]) == REFERENCE_KINDS
    assert set(schemas["audit_references"]["properties"]) == {"path", "limit"}
    assert schemas["audit_references"]["properties"]["limit"]["maximum"] == REFERENCE_AUDIT_MAX_ISSUES


# —— ⑨ 区间**列号**（2026-09-20：选区引用 `#L3C2-L5C7`）——
# 列号 = **1 起的字符位置**（caret 语义：行首 = 1，行末 caret = 行长 + 1）⇒ 合法列 `1..len+1`；
# 缺列 = 「行首 / 行末」语义（不猜）；列越界 ⇒ `not_found`，同行起列 > 止列 ⇒ `invalid`。
# 触发行号空间 = `sub/c.md` 的正文行（`# C 文档` / 空 / `第一行。` / `第二行。` / `第三行。` / `第四行。`）。


def test_anchor_column_range_normal_mixed_inverted_and_out_of_range(kb: Path) -> None:
    ok = invoke(kb, "resolve_reference", reference="@sub/c.md#L3C2-L5C4")
    assert "状态：ok" in ok.content
    assert "sub/c.md 起 3:2 → 止 5:4（3 行）" in ok.content
    assert "首行 第一行。" in ok.content and "末行 第三行。" in ok.content
    assert 'read_document(path="sub/c.md", offset=3, limit=3)' in ok.content

    # 混合（各只写一端）：止端缺列 ⇒ 行末；起端缺列 ⇒ 行首
    tail_open = invoke(kb, "resolve_reference", reference="@sub/c.md#L3C2-L5")
    assert "状态：ok" in tail_open.content and "止 5:行末" in tail_open.content
    head_open = invoke(kb, "resolve_reference", reference="@sub/c.md#L3-L5C4")
    assert "状态：ok" in head_open.content and "起 3:行首" in head_open.content

    # 行长 + 1（行末 caret）是合法列
    eol = invoke(kb, "resolve_reference", reference="@sub/c.md#L3C5-L5C5")
    assert "状态：ok" in eol.content and "起 3:5 → 止 5:5" in eol.content

    # 同行区间 + 同行列倒置
    inline_ok = invoke(kb, "resolve_reference", reference="@sub/c.md#L3C2-L3C4")
    assert "状态：ok" in inline_ok.content and "起 3:2 → 止 3:4" in inline_ok.content
    inline_bad = invoke(kb, "resolve_reference", reference="@sub/c.md#L3C4-L3C2")
    assert "状态：invalid" in inline_bad.content and "列区间倒置" in inline_bad.content

    # 行倒置优先于列
    rows_bad = invoke(kb, "resolve_reference", reference="@sub/c.md#L5C7-L3C2")
    assert "状态：invalid" in rows_bad.content and "行区间倒置" in rows_bad.content

    # 列越界 ⇒ not_found（报出「哪一行第几列」与合法区间）
    col_bad = invoke(kb, "resolve_reference", reference="@sub/c.md#L3C99")
    assert "状态：not_found" in col_bad.content
    assert "第 3 行第 99 列超出" in col_bad.content and "合法列 1..5" in col_bad.content
    col_zero = invoke(kb, "resolve_reference", reference="@sub/c.md#L3C0")
    assert "状态：not_found" in col_zero.content and "第 3 行第 0 列超出" in col_zero.content

    # 非 `@` 形态（`文档#L…C…`）走同一段投影
    plain = invoke(kb, "resolve_reference", reference="sub/c.md#L3C2-L4C4")
    assert "状态：ok" in plain.content and "起 3:2 → 止 4:4" in plain.content

    # 向后兼容：老 token（无列）逐字照旧
    legacy = invoke(kb, "resolve_reference", reference="@sub/c.md#L3-L5")
    assert "状态：ok" in legacy.content and "sub/c.md 第 3-5 行（3 行）" in legacy.content


def test_anchor_column_counts_crlf_tabs_and_single_column(kb: Path) -> None:
    # CRLF + TAB：列号按**去掉行尾 CR/LF** 的字符数算（与 `_read_body_lines().splitlines()` 同口径），
    # TAB 计 1 个字符；第 1 行 `第一行` 共 3 字 ⇒ 行末 caret 列 = 4，第 5 列越界（证明 `\r` 没被算进去）。
    (kb / "notes" / "crlf.md").write_bytes("第一行\r\nAB\tCD\r\n".encode("utf-8"))
    eol = invoke(kb, "resolve_reference", reference="@notes/crlf.md#L1C1-L1C4")
    assert "状态：ok" in eol.content and "起 1:1 → 止 1:4" in eol.content
    tabbed = invoke(kb, "resolve_reference", reference="@notes/crlf.md#L2C3-L2C5")
    assert "状态：ok" in tabbed.content and "起 2:3 → 止 2:5" in tabbed.content
    beyond_crlf = invoke(kb, "resolve_reference", reference="@notes/crlf.md#L1C5")
    assert "状态：not_found" in beyond_crlf.content and "该行共 3 个字符，合法列 1..4" in beyond_crlf.content

    # 单列锚点（无区间）
    single = invoke(kb, "resolve_reference", reference="@notes/crlf.md#L2C2")
    assert "状态：ok" in single.content and "第 2 行第 2 列" in single.content


def test_audit_flags_column_out_of_range_and_inverted_range(kb: Path) -> None:
    doc = "\n".join(
        [
            "# 列号文档",
            "",
            "列越界 @sub/c.md#L3C99 与列倒置 @sub/c.md#L3C4-L3C2。",
            "",
            "正常 @sub/c.md#L3C2-L5C4。",
            "",
        ]
    )
    (kb / "notes" / "cols.md").write_text(doc, encoding="utf-8")
    scoped = invoke(kb, "audit_references", path="notes/cols.md")
    assert not scoped.is_error
    counts = checks_of(scoped.content)
    assert counts["anchor.line_out_of_range"] == 1  # 列越界（复用该检查名）
    assert counts["anchor.range_inverted"] == 1  # 同行列倒置（复用该检查名）
    assert counts["file_reference.missing"] == 0  # 区间 token 不被 ① 误报为悬空文件
    rows = issue_rows(scoped.content)
    assert any("第 3 行第 99 列超出" in row for row in rows)
    assert any("列区间倒置" in row for row in rows)


def test_reference_tools_do_not_write_the_kb(kb: Path) -> None:
    """零写入：两把工具调用前后，库内文件清单逐字不变。"""
    before = snapshot(kb)
    invoke(kb, "resolve_reference", reference="@notes/b.md")
    invoke(kb, "resolve_reference", reference="[[b-kp]]")
    invoke(kb, "resolve_reference", reference="![pic](.memoria/images/pic.png)")
    invoke(kb, "audit_references")
    invoke(kb, "audit_references", path="notes/a.md")
    assert snapshot(kb) == before
