# 配套单测：被测语义移植自 deepseek-harness `packages/skill`（`skill` 注册表 /
# `skill-filesystem` 目录 provider / `tool-skill` 模型面）（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""技能（skill）的离线单测：规则照搬上游、结构按本地偏差重落。

覆盖：
① 名字语法 `^[a-z0-9]+(?:-[a-z0-9]+)*$`（上游 `skill/src/index.ts:21`）；
② 发现规则：平铺 `<name>.md` 与目录包 `<name>/SKILL.md` 两种形态、**只认根的下一层**
   （嵌套 `**/SKILL.md` 不发现）、资源基目录分别是"该目录"与"根本身"；
③ frontmatter 契约：首行必须是 `---`、闭合须独占一行、YAML 必须是对象、必填 `name`+`description`；
   任一不满足 ⇒ **跳过该文件**（不抛、不影响别的技能）；
④ 宽松布尔表（`true/yes/on/1` ↔ `false/no/off/0`）与**旧键拒绝**（`modelInvocable` 等须写 kebab 形式）；
⑤ `disable-model-invocation: true` ⇒ 目录里没有它、`skill` 工具也拒，**只能由 `/name` 手势带进来**；
⑥ 同名遮蔽：`<name>` 目录包胜 `<name>.md` 平铺包（同 rank 按目录内序），后者只 warn；
⑦ 两段式：**只改正文**时目录摘要不变、`load_skill()` 现读到新正文（不缓存正文）；
⑧ 渲染：目录行形状 + description 空白折叠/500 截断、`<skill_content>` 三明治且**正文逐字不转义**；
⑨ 工具：按**精确名**加载；非法名 / 未知名 / 不可调用三类错误各自稳定；
⑩ 提示词门控：`skill` 工具在场**且目录非空**才出「可用技能」段（空段消失）；
⑪ 只读纪律：发现 / 加载 / 调工具之后，整库**逐字节不变**；
⑫ `/name` 用户手势：正则边界（空白包围、不吃路径与分数）、first-seen 去重、未知名与
   `user-invocable: false` 一律**保持普通散文**、注入位次在**本轮请求最末**且**不落盘**。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from memoria.services.agent import prompt, skills
from memoria.services.agent.ask import ask
from memoria.services.agent.llm import FinishEvent, FinishReason, LlmRequest, TextDelta, ToolCall
from memoria.services.agent.prompt import build_system_prompt
from memoria.services.agent.tools import ToolRegistry, build_kb_tools
from memoria.services.agent.tools.kb import SKILL_NOT_INVOCABLE_CODE

FLAT = """---
name: weekly-review
description:   每周复盘   的固定流程
whenToUse: 用户说「复盘这周」时
---

# 周复盘

第一步：读本周会话。
"""


def _pack(name: str, description: str, body: str, extra: str = "") -> str:
    return f"---\nname: {name}\ndescription: {description}\n{extra}---\n\n{body}\n"


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    """最小知识库：两种技能形态 + 各种非法文件 + 一个资源文件。"""
    root = tmp_path / "kb"
    bucket = root / ".memoria" / "agent" / "skills"
    (bucket / "deep-work").mkdir(parents=True)
    (bucket / "nested" / "inner").mkdir(parents=True)
    (root / ".memoria" / "agent").mkdir(parents=True, exist_ok=True)

    (bucket / "weekly-review.md").write_text(FLAT, encoding="utf-8")
    (bucket / "deep-work" / "SKILL.md").write_text(
        _pack("deep-work", "深度工作法", "# 深度工作\n\n按块排时间。"), encoding="utf-8"
    )
    (bucket / "deep-work" / "template.md").write_text("资源文件", encoding="utf-8")
    # 嵌套一层 ⇒ 上游**不发现**（只认扫描根的下一层）
    (bucket / "nested" / "inner" / "SKILL.md").write_text(
        _pack("inner", "不该被发现的技能", "正文"), encoding="utf-8"
    )
    # 同名遮蔽：`shadow.md`（平铺）vs `shadow/SKILL.md`（目录包）⇒ 目录包胜（目录内序在前）
    (bucket / "shadow").mkdir()
    (bucket / "shadow" / "SKILL.md").write_text(_pack("shadow", "目录包版本", "目录包正文"), encoding="utf-8")
    (bucket / "shadow.md").write_text(_pack("shadow", "平铺版本", "平铺正文"), encoding="utf-8")
    # 三类非法
    (bucket / "no-frontmatter.md").write_text("# 光秃秃\n\n没有 frontmatter。\n", encoding="utf-8")
    (bucket / "missing-fields.md").write_text(_pack("ok-name", "", "缺 description"), encoding="utf-8")
    (bucket / "bad-name.md").write_text(_pack("Bad_Name", "名字非法", "正文"), encoding="utf-8")
    (bucket / "legacy.md").write_text(
        _pack("legacy", "用了废弃键", "正文", extra="modelInvocable: true\n"), encoding="utf-8"
    )
    (bucket / "quiet.md").write_text(
        _pack("quiet", "只给用户用", "正文", extra="disable-model-invocation: true\n"), encoding="utf-8"
    )
    (bucket / "readme.txt").write_text("不是 md，不参与发现", encoding="utf-8")
    return root


def _facts(root: Path) -> dict[str, str]:
    """整库逐文件 sha256（只读纪律的证据）。"""
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _names(kb: Path) -> list[str]:
    return [skill.name for skill in skills.discover_skills(str(kb))]


def registry_for(kb: Path) -> ToolRegistry:
    return ToolRegistry(build_kb_tools(str(kb), session_id="session-20260922T200000Z-skills"))


def invoke_skill(kb: Path, **arguments):
    return registry_for(kb).invoke(
        ToolCall(id="c1", name="skill", arguments=json.dumps(arguments, ensure_ascii=False))
    )


class FakeProvider:
    """按脚本产出流式事件的假 provider（本文件只用"一步文本答复"）。"""

    name = "fake"

    def __init__(self, script: Sequence[Sequence[Any]] = ()) -> None:
        self.script: list[list[Any]] = [list(step) for step in script]
        self.requests: list[LlmRequest] = []

    def stream(self, request: LlmRequest) -> Iterator[Any]:
        self.requests.append(request)
        step = self.script.pop(0) if self.script else [
            TextDelta("好的。"),
            FinishEvent(reason=FinishReason.STOP),
        ]
        yield from step


# ── ① 名字语法 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["a", "ab", "weekly-review", "a1-b2-c3", "9x"])
def test_is_skill_name_accepts_kebab_case(name: str) -> None:
    assert skills.is_skill_name(name) is True


@pytest.mark.parametrize("name", ["", "Bad", "bad_name", "-bad", "bad-", "bad--name", "带中文", "a b"])
def test_is_skill_name_rejects_non_kebab(name: str) -> None:
    assert skills.is_skill_name(name) is False


# ── ② 发现规则 ────────────────────────────────────────────────────────────────


def test_discovers_flat_and_directory_packages_but_not_nested(kb: Path) -> None:
    found = skills.discover_skills(str(kb))
    # 按名字排序；`quiet` 也在（上游 `list()` 返回**调用中性**的摘要，是否可调用由消费者过滤）
    assert [skill.name for skill in found] == ["deep-work", "quiet", "shadow", "weekly-review"]
    by_name = {skill.name: skill for skill in found}
    # 平铺包：资源基目录 = 根本身；目录包：资源基目录 = 该目录
    assert Path(by_name["weekly-review"].base_dir).name == "skills"
    assert Path(by_name["deep-work"].base_dir).name == "deep-work"
    assert "inner" not in by_name, "嵌套 `**/SKILL.md` 上游不发现（只认根的下一层）"


def test_non_markdown_entries_are_ignored(kb: Path) -> None:
    """`readme.txt` 既不构成技能也不报错（既非目录、也非 `.md`）。"""
    assert "readme" not in _names(kb)


# ── ③ frontmatter 契约 ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "why"),
    [
        ("# 没有 frontmatter\n", "首行不是 `---`"),
        ("---\nname: x\n", "闭合 `---` 缺失"),
        ("---\n- a\n- b\n---\n正文\n", "YAML 不是对象（是数组）"),
        ("---\nname: [1,2\n---\n正文\n", "YAML 非法"),
    ],
)
def test_parse_frontmatter_rejects_malformed(raw: str, why: str) -> None:
    assert skills.parse_frontmatter(raw) is None, why


def test_parse_frontmatter_splits_body_without_touching_it() -> None:
    parsed = skills.parse_frontmatter("---\nname: a-b\ndescription: 说明\n---\n\n正文一行\n第二行\n")
    assert parsed is not None
    data, body = parsed
    assert data["name"] == "a-b" and data["description"] == "说明"
    assert body == "\n正文一行\n第二行\n"


def test_invalid_files_are_skipped_without_breaking_the_rest(kb: Path) -> None:
    """缺 frontmatter / 缺字段 / 名字非法 / 废弃键 ⇒ 各自跳过，其余技能照常可用。"""
    names = _names(kb)
    for bad in ("no-frontmatter", "ok-name", "Bad_Name", "legacy"):
        assert bad not in names, f"{bad} 不该进目录"
    assert "weekly-review" in names and "deep-work" in names


# ── ④ 宽松布尔 + 旧键拒绝 ─────────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["true", "yes", "on", "1", "TRUE", "Yes"])
def test_boolean_truthy_forms_disable_model_invocation(kb: Path, value: str) -> None:
    """宽松布尔表（上游 `:1018-1037`）：真值形态等同 `true` ⇒ 不进模型目录、工具也拒。"""
    path = kb / ".memoria" / "agent" / "skills" / "flag.md"
    path.write_text(_pack("flag", "开关测试", "正文", extra=f"disable-model-invocation: {value}\n"), encoding="utf-8")
    found = {skill.name: skill for skill in skills.discover_skills(str(kb))}
    assert found["flag"].model_invocable is False  # 仍被**发现**（调用中性），只是不可模型调用
    assert "flag" not in skills.render_skill_catalog(list(found.values()))


@pytest.mark.parametrize("value", ["nonsense", "2", "maybe"])
def test_boolean_invalid_forms_skip_the_file(kb: Path, value: str) -> None:
    path = kb / ".memoria" / "agent" / "skills" / "flag.md"
    path.write_text(_pack("flag", "开关测试", "正文", extra=f"disable-model-invocation: {value}\n"), encoding="utf-8")
    assert "flag" not in _names(kb)


def test_legacy_invocation_key_is_rejected_not_silently_accepted(kb: Path) -> None:
    """`modelInvocable` 之类的 camelCase 旧键**必须报错跳过**（上游 `:1012-1016`）。"""
    assert "legacy" not in _names(kb)
    # 同一份 frontmatter 换成 kebab 键就能用 ⇒ 证明拒的是键名而不是别的东西
    (kb / ".memoria" / "agent" / "skills" / "legacy.md").write_text(
        _pack("legacy", "用了规范键", "正文", extra="disable-model-invocation: false\n"), encoding="utf-8"
    )
    assert "legacy" in _names(kb)


# ── ⑤ `disable-model-invocation` 的两面 ───────────────────────────────────────


def test_non_invocable_skill_is_hidden_from_the_catalog_and_refused_by_the_tool(kb: Path) -> None:
    found = {skill.name: skill for skill in skills.discover_skills(str(kb))}
    assert found["quiet"].model_invocable is False  # 仍被**发现**（注册表全留）
    assert "quiet" not in skills.render_skill_catalog(list(found.values())), "不进模型目录"
    result = invoke_skill(kb, name="quiet")
    assert result.is_error is True and result.output.code == SKILL_NOT_INVOCABLE_CODE
    assert "disable-model-invocation" in result.content


def test_user_invocable_defaults_true(kb: Path) -> None:
    found = {skill.name: skill for skill in skills.discover_skills(str(kb))}
    assert found["weekly-review"].user_invocable is True
    assert found["weekly-review"].model_invocable is True


# ── ⑥ 同名遮蔽 ────────────────────────────────────────────────────────────────


def test_same_name_shadowing_prefers_the_directory_package(kb: Path) -> None:
    """`shadow/`（目录包）与 `shadow.md`（平铺）同名 ⇒ 目录内序在前，目录包胜。"""
    winner = next(skill for skill in skills.discover_skills(str(kb)) if skill.name == "shadow")
    assert Path(winner.path).name == "SKILL.md"
    loaded = skills.load_skill(str(kb), "shadow")
    assert loaded is not None and loaded.description == "目录包版本"


# ── ⑦ 两段式（正文不缓存）────────────────────────────────────────────────────


def test_body_is_reread_on_load_while_the_catalog_summary_stays(kb: Path) -> None:
    before = {skill.name: skill.description for skill in skills.discover_skills(str(kb))}
    target = kb / ".memoria" / "agent" / "skills" / "weekly-review.md"
    target.write_text(FLAT.replace("第一步：读本周会话。", "第一步：改成读上周会话。"), encoding="utf-8")

    after = {skill.name: skill.description for skill in skills.discover_skills(str(kb))}
    assert after == before, "只改正文 ⇒ 目录摘要逐字不变"
    loaded = skills.load_skill(str(kb), "weekly-review")
    assert loaded is not None and "改成读上周会话" in loaded.content, "正文每次 load 现读"


def test_load_skill_returns_none_for_unknown_or_illegal_name(kb: Path) -> None:
    assert skills.load_skill(str(kb), "nope") is None
    assert skills.load_skill(str(kb), "Bad_Name") is None
    assert skills.load_skill(str(kb), "") is None


# ── ⑧ 渲染 ────────────────────────────────────────────────────────────────────


def test_catalog_renders_entries_and_normalizes_description(kb: Path) -> None:
    section = skills.render_skill_catalog(skills.discover_skills(str(kb)))
    assert section.startswith("## 可用技能")
    assert "- `weekly-review`：每周复盘 的固定流程" in section  # 多余空白被折叠成一个空格
    assert "加载之前不要照摘要臆测技能内容" in section
    assert "何时用：" in section and "用户说「复盘这周」时" in section


def test_catalog_description_is_truncated_to_500_chars(kb: Path) -> None:
    (kb / ".memoria" / "agent" / "skills" / "long-desc.md").write_text(
        _pack("long-desc", "长" * 600, "正文"), encoding="utf-8"
    )
    section = skills.render_skill_catalog(skills.discover_skills(str(kb)))
    line = next(row for row in section.splitlines() if row.startswith("- `long-desc`"))
    assert line.endswith("...") and len(line) < 520


def test_catalog_escapes_angle_brackets_in_description(kb: Path) -> None:
    (kb / ".memoria" / "agent" / "skills" / "esc.md").write_text(
        _pack("esc", "含 <script> 的描述", "正文"), encoding="utf-8"
    )
    section = skills.render_skill_catalog(skills.discover_skills(str(kb)))
    assert "&lt;script&gt;" in section and "<script>" not in section


def test_empty_catalog_renders_nothing(kb: Path) -> None:
    assert skills.render_skill_catalog(()) == ""


def test_skill_content_wrapper_embeds_body_verbatim(kb: Path) -> None:
    (kb / ".memoria" / "agent" / "skills" / "verbatim.md").write_text(
        _pack("verbatim", "正文保真", "```\nif a < b && c > d: pass\n```"), encoding="utf-8"
    )
    loaded = skills.load_skill(str(kb), "verbatim")
    assert loaded is not None
    rendered = skills.render_skill_content(loaded)
    assert rendered.startswith('<skill_content name="verbatim">')
    assert "<skill_resources>" in rendered
    assert "本技能的资源基目录：" in rendered
    assert rendered.index("<skill_resources>") < rendered.index("<skill_instructions>"), "资源提示在前"
    assert "if a < b && c > d: pass" in rendered, "正文**逐字**（可信本地内容，不转义）"
    assert rendered.rstrip().endswith("</skill_content>")


# ── ⑨ 工具面 ──────────────────────────────────────────────────────────────────


def test_skill_tool_loads_by_exact_name(kb: Path) -> None:
    result = invoke_skill(kb, name="deep-work")
    assert result.is_error is False, result.content
    assert '<skill_content name="deep-work">' in result.content
    assert "按块排时间。" in result.content


@pytest.mark.parametrize("name", ["Bad_Name", "bad name", "-x"])
def test_skill_tool_rejects_illegal_name(kb: Path, name: str) -> None:
    result = invoke_skill(kb, name=name)
    assert result.is_error is True and result.output.code == "INVALID_ARGUMENTS"


def test_skill_tool_reports_unknown_name_with_the_available_list(kb: Path) -> None:
    result = invoke_skill(kb, name="not-there")
    assert result.is_error is True and result.output.code == "NOT_FOUND"
    assert "weekly-review" in result.content, "错误里必须给出本轮可用技能，便于模型改口"


def test_skill_tool_is_registered_read_only_and_in_the_tool_names(kb: Path) -> None:
    from memoria.services.agent.tools import KB_TOOL_NAMES

    tool = registry_for(kb).get("skill")
    assert tool is not None and tool.read_only is True
    assert "skill" in KB_TOOL_NAMES


# ── ⑩ 提示词门控 ──────────────────────────────────────────────────────────────


def _schemas(kb: Path, *, with_skill: bool) -> list:
    rows = [tool.schema() for tool in build_kb_tools(str(kb))]
    return rows if with_skill else [row for row in rows if row.name != "skill"]


def test_catalog_section_appears_only_with_the_tool_and_a_non_empty_catalog(kb: Path) -> None:
    with_tool = build_system_prompt(str(kb), tools=_schemas(kb, with_skill=True), model="m")
    assert "## 可用技能" in with_tool

    without_tool = build_system_prompt(str(kb), tools=_schemas(kb, with_skill=False), model="m")
    assert "## 可用技能" not in without_tool, "门控同上游：`skill` 工具不在场就不给目录"


def test_catalog_section_disappears_when_there_are_no_skills(tmp_path: Path) -> None:
    empty = tmp_path / "empty-kb"
    (empty / ".memoria" / "agent").mkdir(parents=True)
    text = build_system_prompt(str(empty), tools=_schemas(empty, with_skill=True), model="m")
    assert "## 可用技能" not in text, "零技能 ⇒ 不出空段（上游首次发布且零技能同样不发）"


# ── ⑪ 只读纪律 ────────────────────────────────────────────────────────────────


def test_discovery_load_and_tool_write_nothing(kb: Path) -> None:
    before = _facts(kb)
    skills.discover_skills(str(kb))
    skills.load_skill(str(kb), "weekly-review")
    invoke_skill(kb, name="deep-work")
    invoke_skill(kb, name="not-there")
    build_system_prompt(str(kb), tools=_schemas(kb, with_skill=True), model="m")
    assert _facts(kb) == before


# ── ⑫ `/name` 用户手势（2026-09-22 补；上游 `tool-skill/src/index.ts:163-204`）──────────────────


def test_gesture_is_whitespace_bounded_and_deduplicated() -> None:
    """正则逐字照搬上游 `:409`：空白包围、可出现在**任意位置**、不误吃路径与分数。"""
    assert skills.invoked_names("先按 /weekly-review 走一遍") == ["weekly-review"]
    assert skills.invoked_names("/a 与 /b 再 /a") == ["a", "b"], "first-seen 序去重"
    assert skills.invoked_names("看 /usr/bin 与 5/8 与 /x/y") == [], "第二个 `/` 或非边界字符打断匹配"
    assert skills.invoked_names("a/weekly-review b") == [], "左侧必须是行首或空白"
    assert skills.invoked_names("") == []


def test_gesture_keeps_unknown_and_user_disabled_names_as_plain_prose(kb: Path) -> None:
    """上游 `:191-195`：手势命中不了注册表就仍是普通散文 —— 不报错、不注入。"""
    (kb / ".memoria" / "agent" / "skills" / "staff-only.md").write_text(
        _pack("staff-only", "只给模型用", "正文", extra="user-invocable: false\n"), encoding="utf-8"
    )
    assert "weekly-review" in skills.render_invocations(str(kb), "/weekly-review")
    assert skills.render_invocations(str(kb), "/not-there") == "", "未知名不报错、不注入"
    assert skills.render_invocations(str(kb), "/staff-only") == "", "`user-invocable: false` ⇒ 手势不认"
    assert skills.render_invocations(str(kb), "没有手势") == ""


def test_gesture_is_the_only_entry_to_a_disable_model_invocation_skill(kb: Path) -> None:
    """`quiet` 不进目录、`skill` 工具也拒（⑤），但 `/quiet` 能把它带进来（上游 `:175-176`）。"""
    rendered = skills.render_invocations(str(kb), "请按 /quiet 来")
    assert '<skill_content name="quiet">' in rendered and "正文" in rendered


def test_invocation_block_is_appended_at_the_very_end(kb: Path) -> None:
    """位次（上游 `:165-170`）：**本轮请求最末**（时间读数之后）⇒ 要照做的材料离答复最近。"""
    block = prompt.render_skill_invocation(str(kb), "/deep-work")
    assert block.startswith('\n\n<skill_content name="deep-work">')
    assert block.rstrip().endswith("</skill_content>")
    assert prompt.render_skill_invocation(str(kb), "没有手势") == ""


def test_ask_injects_the_gesture_into_the_turn_request_without_persisting_it(kb: Path) -> None:
    provider = FakeProvider()
    result = ask(str(kb), "按 /weekly-review 走一遍", provider=provider, model="fake-model")

    sent = provider.requests[0].messages[-1].content
    assert '<skill_content name="weekly-review">' in sent
    assert sent.index("第一步：读本周会话。") > sent.index("当前本地时间："), "注入在时间读数之后"
    assert sent.rstrip().endswith("</skill_content>"), "注入在**最末**"

    raw = Path(result.session_path).read_text(encoding="utf-8")
    assert "按 /weekly-review 走一遍" in raw, "会话日志里仍是用户原文"
    assert "<skill_content" not in raw, "注入只进本轮请求，**不落盘**（同快照口径）"


def test_ask_leaves_a_plain_question_with_slashes_untouched(kb: Path) -> None:
    """没有命中手势 ⇒ 请求里不出现任何注入块（`/usr/bin` 这类路径不算手势）。"""
    provider = FakeProvider()
    ask(str(kb), "讲讲 /usr/bin 是什么", provider=provider, model="fake-model")
    assert "<skill_content" not in provider.requests[0].messages[-1].content
