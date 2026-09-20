# 配套单测：被测调用面语义移植自 deepseek-harness `packages/fs/tool-fs`（`read` 的
# offset/limit 与三重 cap、`read_image` 的扩展名/签名判定）与 `packages/fs/tool-fs-search`
# （`glob`/`grep` 的参数、上限与输出形状）（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""上游读面（`read_document` 分页 / `glob` / `grep` / `read_image`）的离线单测。

覆盖：
① 分页边界（offset=0 / 中间 / 超尾；limit 上下限）与**续读提示可解析**；
② 未截断时与旧调用逐字兼容（含正文末尾换行）；
③ `glob` 的匹配口径（含 `/` 比整条路径、不含则比文件名）、上限与允许根之外/越界拒绝；
④ `grep` 的命中格式、`include` 校验、结果上限、二进制跳过与允许根之外拒绝；
⑤ `read_image` 的参数/格式校验与「缺『多媒体眼睛』插件」的明确拒绝（不伪造成功）；
⑥ 新工具注册与 `read_only`、`@路径` 段门控不回归；
⑦ 工具面 = 工作区根（**允许根列表**，今天 `[库根]`）：可见性由程序施加 —— `.memoria/**` 默认
   可见、VCS 内部目录（`.git` 等）仍不可见、允许根之外一律明确拒绝（错误码稳定）。
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from memoria.services.agent.llm import ToolCall
from memoria.services.agent.tools import (
    INVALID_ARGUMENTS_CODE,
    KB_TOOL_NAMES,
    UNKNOWN_TOOL_CODE,
    ToolRegistry,
    build_kb_tools,
)
from memoria.services.agent.tools.kb import (
    DEFAULT_READ_LIMIT,
    GLOB_MAX_RESULTS,
    GREP_MAX_LINE_BYTES,
    GREP_MAX_MATCHES,
    UNSUPPORTED_IMAGE_INPUT,
    _grep_tool,
    _read_document_call,
)
from memoria.storage.markdown import strip_frontmatter

SHORT_MD = """---
title: 短篇
---

# 短篇

正文第二段。
"""

# 30 行正文的长篇（frontmatter 不计入窗口行号，故正文行 = 1..30）。
LONG_MD = "---\ntitle: 长篇\n---\n\n" + "".join(f"第 {index} 行\n" for index in range(1, 31))

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    """最小知识库：长/短两篇 md + 子目录 + 非 md 文件 + 图片 + 二进制 + 需排除的目录。"""
    root = tmp_path / "kb"
    (root / "sub").mkdir(parents=True)
    (root / ".memoria" / "agent").mkdir(parents=True)
    (root / ".git").mkdir(parents=True)
    (root / "short.md").write_text(SHORT_MD, encoding="utf-8")
    (root / "long.md").write_text(LONG_MD, encoding="utf-8")
    (root / "sub" / "nested.md").write_text("# 嵌套\n\n子目录文档。\n", encoding="utf-8")
    (root / "notes.txt").write_text("多层感知机在这里出现一次\n", encoding="utf-8")
    (root / "sub" / "blob.bin").write_bytes("多层感知机\x00二进制\n".encode("utf-8"))
    (root / "img.png").write_bytes(PNG_BYTES)
    (root / "img.bmp").write_bytes(b"BM" + b"\x00" * 8)
    (root / "mismatch.jpg").write_bytes(PNG_BYTES)  # 扩展名与签名不一致
    (root / "fake.png").write_text("多层感知机并不是图片\n", encoding="utf-8")
    (root / ".memoria" / "agent" / "kb-spec.zh-CN.md").write_text("多层感知机（库内元数据）\n", encoding="utf-8")
    (root / ".git" / "config.md").write_text("多层感知机（VCS 元数据）\n", encoding="utf-8")
    return root


def registry_for(kb: Path) -> ToolRegistry:
    return ToolRegistry(build_kb_tools(str(kb)))


def invoke(kb: Path, name: str, **arguments: Any) -> Any:
    import json

    return registry_for(kb).invoke(ToolCall(id="c1", name=name, arguments=json.dumps(arguments)))


# —— ① / ② `read_document` 分页与向后兼容 ——


def test_read_document_without_params_is_byte_compatible(kb: Path) -> None:
    """不传 offset/limit ⇒ 正文与旧实现逐字一致（含末尾换行），且不出现 footer。"""
    body, _ = strip_frontmatter(SHORT_MD)
    result = invoke(kb, "read_document", path="short.md")

    assert not result.is_error
    assert result.content.endswith(body)  # 含正文末尾换行
    assert result.content.endswith("正文：\n" + body)
    assert "续读" not in result.content
    assert "截断" not in result.content


def test_read_document_paginates_and_hint_is_parseable(kb: Path) -> None:
    first = invoke(kb, "read_document", path="long.md", offset=1, limit=5)

    assert not first.is_error
    assert "文档 long.md：共 30 行" in first.content
    assert "第 1 行" in first.content.split("正文：")[1]
    assert "第 5 行" in first.content and "第 6 行" not in first.content
    hint = re.search(r"续读请把 offset 设为 (\d+)", first.content)
    assert hint is not None, first.content
    assert hint.group(1) == "6"
    assert "共 30 行" in first.content

    # 按提示续读：第二页从第 6 行起，直到末页不再有 footer
    second = invoke(kb, "read_document", path="long.md", offset=int(hint.group(1)), limit=5)
    window = second.content.split("正文：")[1]
    assert window.startswith("\n第 6 行")
    assert "第 10 行" in window and "第 11 行" not in window

    last = invoke(kb, "read_document", path="long.md", offset=26, limit=5)
    assert last.content.split("正文：")[1].startswith("\n第 26 行")
    assert "第 30 行" in last.content
    assert "续读" not in last.content  # 已到末尾 ⇒ 无 footer


def test_read_document_offset_and_limit_bounds(kb: Path) -> None:
    beyond = invoke(kb, "read_document", path="long.md", offset=31)
    assert beyond.is_error and beyond.output.code == "NOT_FOUND"
    assert "offset 31 超出范围" in beyond.content and "共 30 行" in beyond.content

    zero = invoke(kb, "read_document", path="long.md", offset=0)
    assert zero.is_error and zero.output.code == INVALID_ARGUMENTS_CODE

    too_many = invoke(kb, "read_document", path="long.md", limit=DEFAULT_READ_LIMIT + 1)
    assert too_many.is_error and too_many.output.code == INVALID_ARGUMENTS_CODE

    zero_limit = invoke(kb, "read_document", path="long.md", limit=0)
    assert zero_limit.is_error and zero_limit.output.code == INVALID_ARGUMENTS_CODE

    # 直连工具体（绕过 schema 校验）时按同一语义失败
    direct = _read_document_call(str(kb), {"path": "long.md", "limit": 10_000})
    assert direct.error and f"1..{DEFAULT_READ_LIMIT}" in direct.text


def test_read_document_char_budget_gives_continuation_hint(kb: Path) -> None:
    """正文超过 20,000 字符预算时给出续读 offset（旧实现只说「已截断」）。"""
    (kb / "huge.md").write_text("".join(f"第 {index} 行：" + "字" * 40 + "\n" for index in range(1, 601)), encoding="utf-8")
    result = invoke(kb, "read_document", path="huge.md")

    assert not result.is_error
    assert "正文已达 20000 字符预算" in result.content
    assert re.search(r"续读请把 offset 设为 (\d+)", result.content) is not None
    assert "共 600 行" in result.content


def test_read_document_offset_is_in_body_line_space(kb: Path) -> None:
    """offset 的行号口径 = 剥掉 frontmatter 的正文行号（与知识点锚点同一行空间）。"""
    window = invoke(kb, "read_document", path="long.md", offset=3, limit=1)
    assert window.content.split("正文：")[1].startswith("\n第 3 行")


# —— ③ `glob` ——


def test_glob_matches_paths_and_basename_rule(kb: Path) -> None:
    any_depth = invoke(kb, "glob", pattern="*.md")
    assert not any_depth.is_error
    assert "short.md" in any_depth.content and "long.md" in any_depth.content
    assert "sub/nested.md" in any_depth.content  # 不含 `/` ⇒ 比文件名（任意深度）

    rooted = invoke(kb, "glob", pattern="sub/*.md")
    assert "sub/nested.md" in rooted.content
    assert "long.md" not in rooted.content  # 含 `/` ⇒ 比整条路径

    non_md = invoke(kb, "glob", pattern="*.txt")
    assert "notes.txt" in non_md.content and ".md" not in non_md.content

    scoped = invoke(kb, "glob", pattern="*.md", path="sub")
    assert "nested.md" in scoped.content and "long.md" not in scoped.content


def test_glob_visibility_rules_and_rejects_escape(kb: Path) -> None:
    """可见性由程序施加：`.memoria/**` 默认可见、VCS 内部不可见；允许根之外一律拒绝。"""
    everything = invoke(kb, "glob", pattern="**/*.md")
    assert "sub/nested.md" in everything.content
    assert ".memoria/agent/kb-spec.zh-CN.md" in everything.content  # .memoria/** 默认可见（2026-09-20 改正）
    assert ".git" not in everything.content  # VCS 内部仍不可见（上游 GLOB_VCS_EXCLUDES）

    scoped = invoke(kb, "glob", pattern="*.md", path=".memoria/agent")
    assert "kb-spec.zh-CN.md" in scoped.content  # `.memoria` 可作搜索根

    escape = invoke(kb, "glob", pattern="*.md", path="../")
    assert escape.is_error and escape.output.code == INVALID_ARGUMENTS_CODE

    outside = invoke(kb, "glob", pattern="*.md", path="C:/Windows")
    assert outside.is_error  # 绝对路径（Windows 盘符）不被当作工作区相对目录

    missing = invoke(kb, "glob", pattern="*.md", path="nope")
    assert missing.is_error and missing.output.code == "NOT_FOUND"

    empty = invoke(kb, "glob", pattern="*.json")
    assert not empty.is_error and empty.content.startswith("未匹配到文件")


def test_glob_caps_results_and_reports_total(kb: Path) -> None:
    for index in range(GLOB_MAX_RESULTS + 20):
        (kb / f"bulk-{index:03d}.md").write_text(f"# {index}\n", encoding="utf-8")
    result = invoke(kb, "glob", pattern="bulk-*.md")

    rows = result.content.split("\n\n")[0].splitlines()
    assert len(rows) == GLOB_MAX_RESULTS
    assert f"匹配 {GLOB_MAX_RESULTS + 20} 个文件，仅显示最近修改的 {GLOB_MAX_RESULTS} 个" in result.content


def test_walk_skips_entry_resolving_outside_the_kb(
    kb: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """越界判定在**两侧都先 realpath**：解析到库外的条目既不列也不读。

    本机常无创建符号链接的权限（真符号链接用例会 `skip`），故用 monkeypatch 直接把一个条目的
    `realpath` 指向库外 —— 锁住的是同一条守卫（`_walk_kb_files` 的 realpath 前缀判定），
    且不依赖平台能力。**回归价值**：只归一化一侧（`abspath` vs `realpath`）会让整个库被误判为
    「库外」而静默返回空（Windows 8.3 短名 / junction 场景已实测踩到过）。
    """
    from memoria.services.agent.tools import kb as kb_module

    (kb / "link.md").write_text("库外文档内容\n", encoding="utf-8")
    outside = tmp_path / "elsewhere"
    real_realpath = os.path.realpath

    def fake_realpath(path: Any, *args: Any, **kwargs: Any) -> str:
        if os.path.basename(str(path)) == "link.md":
            return os.path.join(str(outside), "link.md")
        return real_realpath(path, *args, **kwargs)

    monkeypatch.setattr(kb_module.os.path, "realpath", fake_realpath)

    assert "link.md" not in invoke(kb, "glob", pattern="*.md").content
    assert "link.md" not in invoke(kb, "grep", pattern="库外文档内容").content
    assert "long.md" in invoke(kb, "glob", pattern="*.md").content  # 库内条目不受影响


# —— ③b 工具面 = 工作区根（允许根列表）——


def test_read_roots_is_allow_list_and_outside_is_explicitly_rejected(kb: Path, tmp_path: Path) -> None:
    """工具面挂在**允许根列表**上（今天 `[库根]`）；允许根之外是**明确拒绝**且错误码稳定。"""
    from memoria.services.agent.tools import kb as kb_module

    roots = kb_module._read_roots(str(kb))
    assert roots == (os.path.abspath(str(kb)),)  # 今天只有一个允许根：库根（= 工作区根）
    assert kb_module._resolve_in_read_roots(roots, "long.md") == (roots[0], "long.md")
    assert kb_module._resolve_in_read_roots(roots, "sub/nested.md") == (roots[0], "sub/nested.md")
    # `..` / 空路径一律 None（fail-closed；不因重构而放松）
    assert kb_module._resolve_in_read_roots(roots, "../outside.md") is None
    assert kb_module._resolve_in_read_roots(roots, "") is None
    # 结构上多根即放行：把外层目录加进列表后，原本被拒的路径可解析
    assert kb_module._resolve_in_read_roots((str(tmp_path),), "kb/long.md") == (
        os.path.abspath(str(tmp_path)),
        "kb/long.md",
    )

    (tmp_path / "outside.md").write_text("根外文档\n", encoding="utf-8")
    for name, arguments in (
        ("read_document", {"path": "../outside.md"}),
        ("glob", {"pattern": "*.md", "path": "../"}),
        ("grep", {"pattern": "x", "path": "../outside.md"}),
        ("read_image", {"file_path": "../img.png"}),
    ):
        result = invoke(kb, name, **arguments)
        assert result.is_error and result.output.code == INVALID_ARGUMENTS_CODE, name

    # `.memoria/**` 是知识库的一部分：默认可见（sidecar/manifest 维护需要看得见）
    doc = invoke(kb, "read_document", path=".memoria/agent/kb-spec.zh-CN.md")
    assert not doc.is_error and "多层感知机（库内元数据）" in doc.content


# —— ④ `grep` ——


def test_grep_groups_hits_by_file_with_line_numbers(kb: Path) -> None:
    result = invoke(kb, "grep", pattern="多层感知机")

    assert not result.is_error
    assert result.content.startswith("命中 3 处")  # 含 `.memoria/**`（默认可见）
    assert "notes.txt\nLine 1: 多层感知机在这里出现一次" in result.content
    assert "fake.png\nLine 1: 多层感知机并不是图片" in result.content
    assert ".memoria/agent/kb-spec.zh-CN.md\nLine 1: 多层感知机（库内元数据）" in result.content


def test_grep_include_filter_and_no_match(kb: Path) -> None:
    only_md = invoke(kb, "grep", pattern="多层感知机", include="*.md")
    assert "notes.txt" not in only_md.content  # txt 被 include 过滤
    assert ".memoria/agent/kb-spec.zh-CN.md" in only_md.content  # `.memoria/**` 默认可见

    braces = invoke(kb, "grep", pattern="多层感知机", include="*.{md,txt}")
    assert "notes.txt" in braces.content

    none = invoke(kb, "grep", pattern="多层感知机", include="*.json")
    assert none.content.startswith("未匹配到内容")

    bad_negation = invoke(kb, "grep", pattern="x", include="!*.md")
    assert bad_negation.is_error and bad_negation.output.code == INVALID_ARGUMENTS_CODE

    bad_list = invoke(kb, "grep", pattern="x", include="*.md,*.txt")
    assert bad_list.is_error and bad_list.output.code == INVALID_ARGUMENTS_CODE


def test_grep_rejects_bad_regex_and_escape(kb: Path) -> None:
    bad = invoke(kb, "grep", pattern="[unclosed")
    assert bad.is_error and bad.output.code == INVALID_ARGUMENTS_CODE
    assert "正则非法" in bad.content

    empty = invoke(kb, "grep", pattern="")
    assert empty.is_error and empty.output.code == INVALID_ARGUMENTS_CODE

    escape = invoke(kb, "grep", pattern="x", path="../outside.md")
    assert escape.is_error and escape.output.code == INVALID_ARGUMENTS_CODE

    missing = invoke(kb, "grep", pattern="x", path="nope.md")
    assert missing.is_error and missing.output.code == "NOT_FOUND"


def test_grep_skips_binary_and_keeps_metadata_visible(kb: Path) -> None:
    result = invoke(kb, "grep", pattern="多层感知机", path="sub")

    assert "blob.bin" not in result.content  # 含 NUL ⇒ 二进制跳过
    assert "1 个二进制文件已跳过" in result.content

    metadata = invoke(kb, "grep", pattern="库内元数据")
    assert ".memoria/agent/kb-spec.zh-CN.md" in metadata.content  # `.memoria/**` 默认可见
    assert "Line 1: 多层感知机（库内元数据）" in metadata.content

    vcs = invoke(kb, "grep", pattern="VCS 元数据")
    assert vcs.content.startswith("未匹配到内容")  # `.git` 仍不可见


def test_grep_caps_matches_and_previews_long_lines(kb: Path) -> None:
    (kb / "many.md").write_text("".join("命中目标\n" for _ in range(GREP_MAX_MATCHES + 12)), encoding="utf-8")
    (kb / "wide.md").write_text("命中目标" + "宽" * 4000 + "\n", encoding="utf-8")

    capped = invoke(kb, "grep", pattern="命中目标", include="many.md")
    assert capped.content.startswith(f"命中 {GREP_MAX_MATCHES}/{GREP_MAX_MATCHES + 12} 处")
    assert f"仅显示前 {GREP_MAX_MATCHES} 处" in capped.content

    preview = invoke(kb, "grep", pattern="命中目标", include="wide.md")
    line = [row for row in preview.content.splitlines() if row.startswith("Line 1: ")][0]
    body = line[len("Line 1: ") :]
    assert body.endswith("…")  # 截断标记
    assert len(body.encode("utf-8")) <= GREP_MAX_LINE_BYTES + len("…".encode("utf-8"))
    assert "宽" * 500 in body  # 2000 字节 ≈ 666 个「宽」（3 字节/字）


def test_grep_direct_call_shares_semantics(kb: Path) -> None:
    output = _grep_tool(str(kb), {"pattern": "嵌套", "path": "sub/nested.md"})
    assert not output.error and "sub/nested.md" in output.text and "Line 1: # 嵌套" in output.text


# —— ⑤ `read_image` ——


def test_read_image_validates_then_refuses(kb: Path) -> None:
    """校验通过也**不伪造成功**：缺『多媒体眼睛』插件（非读面缺口）⇒ 明确错误。"""
    ok = invoke(kb, "read_image", file_path="img.png")
    assert ok.is_error and ok.output.code == UNSUPPORTED_IMAGE_INPUT
    assert "本端点暂不支持图像输入" in ok.content and "image/png" in ok.content
    assert "多媒体眼睛" in ok.content  # 原因归类：缺多媒体插件（不是「provider 不支持 content part」）


def test_read_image_rejects_bad_extension_missing_and_escape(kb: Path) -> None:
    bad_extension = invoke(kb, "read_image", file_path="img.bmp")
    assert bad_extension.is_error and "只认 PNG/JPEG/WebP/GIF" in bad_extension.content

    fake = invoke(kb, "read_image", file_path="fake.png")
    assert fake.is_error and fake.output.code == INVALID_ARGUMENTS_CODE
    assert "文件内容不是受支持的图片格式" in fake.content

    mismatch = invoke(kb, "read_image", file_path="mismatch.jpg")
    assert mismatch.is_error and mismatch.output.code == INVALID_ARGUMENTS_CODE
    assert "扩展名 .jpg 声明 image/jpeg，但文件签名是 image/png" in mismatch.content

    missing = invoke(kb, "read_image", file_path="nope.png")
    assert missing.is_error and missing.output.code == "NOT_FOUND"

    escape = invoke(kb, "read_image", file_path="../img.png")
    assert escape.is_error and escape.output.code == INVALID_ARGUMENTS_CODE

    empty = invoke(kb, "read_image", file_path="")
    assert empty.is_error and empty.output.code == INVALID_ARGUMENTS_CODE


def test_read_image_detects_extension_less_signature(kb: Path) -> None:
    (kb / "noext").write_bytes(PNG_BYTES)
    result = invoke(kb, "read_image", file_path="noext")
    assert result.is_error and result.output.code == UNSUPPORTED_IMAGE_INPUT
    assert "image/png" in result.content


# —— ⑥ 注册与门控 ——


def test_new_read_tools_registered_and_read_only(kb: Path) -> None:
    registry = registry_for(kb)

    assert tuple(tool.name for tool in build_kb_tools(str(kb))) == KB_TOOL_NAMES
    # 读面三工具的相对次序不变（2026-09-20 会话查询家族追加在末尾，见 design/dsh-agent-port.md §6.17）
    read_face = ("glob", "grep", "read_image")
    assert tuple(name for name in registry.names() if name in read_face) == read_face
    for name in KB_TOOL_NAMES:
        tool = registry.get(name)
        assert tool is not None and tool.read_only, name

    unknown = registry.invoke(ToolCall(id="c", name="read_file", arguments="{}"))
    assert unknown.is_error and unknown.output.code == UNKNOWN_TOOL_CODE

    schemas: Mapping[str, Any] = {schema.name: schema.parameters for schema in registry.schemas()}
    assert set(schemas["glob"]["properties"]) == {"pattern", "path"}
    assert set(schemas["grep"]["properties"]) == {"pattern", "path", "include"}
    assert set(schemas["read_image"]["properties"]) == {"file_path"}
    assert schemas["read_document"]["properties"]["limit"]["maximum"] == DEFAULT_READ_LIMIT
