# 设计来源（唯一事实源）：`docs/design/agent-plugin-design.md` §1（最小可用契约 v1）与 §2（暂缓字段）

"""能力插件**声明面**的规矩：6 字段校验、三来源发现、库级启停。

钉住的是 §1 那张「校验规则」列，尤其是两条**安全底**：

- `tool_id` **必须**在核心原语目录（不在 ⇒ 拒载，不静默降级）；
- `permissions.write` 非空 ⇒ `approval.write` **不得**为 `auto`（插件无法自行降档）。

以及一条**边界**：`permissions.write` 不得包含**核心独占**路径（会话审计 / 备份）——
§1 末段明确说这两处是核心写的，插件既写不了也不该声明。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from memoria.services.agent.plugins import (
    DECL_VERSION,
    PLANNED_TOOLS,
    TOOL_CATALOG,
    kb_enablement,
    kb_registry_path,
    load_declarations,
    parse_declaration,
    set_enabled,
)

#: §1 的**内置声明实样**（`resources/agent-capabilities/kb-write.json`）。
#: 第三条用 `kb.link.attach`（→ `apply_link_instances`：把正文里的纯文本挂成跳转）—— 它与实样原文写的
#: `kb.link.create`（→ `create_edge`：**纯边**，只写 sidecar `edges[]`、不碰正文）是**两个不同动作**，
#: 且**两者今天都装载得了**（2026-09-22 起 `kb.link.create` 随"sidecar 结构 op"一起落地，见
#: `test_link_create_and_attach_are_different_actions`）。这里取 `attach`，因为本文件的用例围绕
#: "建点 / 改点 / 连边"的**正文锚点**路径展开。
KB_WRITE: dict[str, Any] = {
    "v": 1,
    "id": "kb-write",
    "name": "写能力（建点 / 改点 / 连边 / 文件增删改）",
    "provides": {
        "tools": [
            {"tool_id": "kb.kp.create", "gate": "always"},
            {"tool_id": "kb.kp.update", "gate": "kb_has_sidecar"},
            {"tool_id": "kb.link.attach", "gate": "always", "constrain": {"type": {"enum_from": "graph.edge_types.EDGE_TYPES"}}},
        ]
    },
    "permissions": {
        "read": ["**/*.md", ".memoria/**"],
        "write": ["**/*.md", ".memoria/sidecars/**", ".memoria/manifest.yaml", ".memoria/pending.json"],
    },
    "approval": {"read": "auto", "write": "confirm"},
}


def decl(**patch: Any) -> dict[str, Any]:
    """在 §1 实样的基础上打补丁（浅替换顶层键）。"""
    out = json.loads(json.dumps(KB_WRITE))
    out.update(patch)
    return out


def codes(issues: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("kind") or "") for item in issues]


# —— ① 合法声明 ——


def test_the_v1_exemplar_loads_verbatim() -> None:
    declaration, warnings, errors = parse_declaration(KB_WRITE, source="builtin", path="kb-write.json")
    assert errors == [] and declaration is not None
    assert declaration.id == "kb-write" and declaration.writable is True
    assert [tool.tool_id for tool in declaration.tools] == ["kb.kp.create", "kb.kp.update", "kb.link.attach"]
    assert declaration.tools[1].gate == "kb_has_sidecar"
    assert declaration.tools[2].constrain == {"type": {"enum_from": "graph.edge_types.EDGE_TYPES"}}
    assert declaration.approval == {"read": "auto", "write": "confirm"}
    # 声明的 `tool_id` 一律能落到**核心原语**（插件自己不写盘）
    assert [tool.primitive for tool in declaration.tools] == ["confirm_kp_range", "update_kp", "apply_link_instances"]
    assert [item["kind"] for item in warnings] == []


def test_name_falls_back_to_id() -> None:
    declaration, _w, errors = parse_declaration(decl(name=""), source="builtin")
    assert errors == [] and declaration is not None and declaration.name == "kb-write"


def test_read_only_plugin_may_use_auto_write() -> None:
    """安全下限只管"有写动作类"时；纯只读插件 `approval.write=auto` 是允许的。"""
    raw = decl(permissions={"read": ["**/*.md"], "write": []}, approval={"read": "auto", "write": "auto"})
    declaration, _w, errors = parse_declaration(raw, source="builtin")
    assert errors == [] and declaration is not None and declaration.writable is False


@pytest.mark.parametrize("plugin_id", ["Kb-Write", "kb_write", "kb write", "写能力", "1kb", "-kb", "kb-"])
def test_bad_ids_are_rejected(plugin_id: str) -> None:
    declaration, _w, errors = parse_declaration(decl(id=plugin_id), source="builtin")
    assert declaration is None and "bad_id" in codes(errors)


def test_unknown_envelope_version_is_rejected() -> None:
    """§1「只增不改」：未知 `v` ⇒ 拒载（而不是猜着读）。"""
    declaration, _w, errors = parse_declaration(decl(v=2), source="builtin")
    assert declaration is None and "bad_envelope" in codes(errors)


# —— ② 原语目录（关键安全底）——


def test_tool_id_must_come_from_the_primitive_catalog() -> None:
    raw = decl(provides={"tools": [{"tool_id": "kb.evil.exec"}]})
    declaration, _w, errors = parse_declaration(raw, source="builtin")
    assert declaration is None and "unknown_tool" in codes(errors)
    assert "kb.kp.create" in errors[0]["message"]  # 报错要**可行动**：把可选目录列出来


def test_empty_tools_is_rejected() -> None:
    declaration, _w, errors = parse_declaration(decl(provides={"tools": []}), source="builtin")
    assert declaration is None and "bad_field" in codes(errors)


def test_bad_gate_value_is_rejected() -> None:
    raw = decl(provides={"tools": [{"tool_id": "kb.kp.create", "gate": "sometimes"}]})
    declaration, _w, errors = parse_declaration(raw, source="builtin")
    assert declaration is None and "bad_field" in codes(errors)


def test_gate_defaults_to_always() -> None:
    raw = decl(provides={"tools": [{"tool_id": "kb.kp.create"}]})
    declaration, _w, errors = parse_declaration(raw, source="builtin")
    assert errors == [] and declaration is not None and declaration.tools[0].gate == "always"


def test_catalog_covers_every_code_primitive() -> None:
    """命名桥的两侧必须都活着：目录里的每个原语名都要在 `apply.PRIMITIVES` 里找得到。"""
    from memoria.services.agent.apply import PRIMITIVES

    for tool_id, primitive in TOOL_CATALOG.items():
        assert primitive in PRIMITIVES, f"{tool_id} → {primitive} 在原语表里不存在"


@pytest.mark.parametrize("tool_id", sorted(PLANNED_TOOLS))
def test_planned_but_unimplemented_tools_are_rejected_with_their_own_code(tool_id: str) -> None:
    """设计已列、代码未实现（M3b）⇒ 专门错误码，别混成"不在目录里"。"""
    raw = decl(provides={"tools": [{"tool_id": tool_id}]})
    declaration, _w, errors = parse_declaration(raw, source="builtin")
    assert declaration is None and "tool_not_implemented" in codes(errors)


def test_catalog_and_planned_sets_do_not_overlap() -> None:
    assert not set(TOOL_CATALOG) & set(PLANNED_TOOLS)


def test_link_create_and_attach_are_different_actions() -> None:
    """`kb.link.create`（→ `create_edge`，**纯边**：只写 sidecar `edges[]`）与 `kb.link.attach`
    （→ `apply_link_instances`，包正文 `[[…]]` 并把锚挂上去）是**两个不同的动作**。

    这条以前靠"实样原文照抄会被拒"间接钉住（旧 `test_design_exemplar_drift_is_pinned`）；2026-09-22
    起 `kb.link.create` **已经落地** ⇒ 改为直接钉"两个 id 各归各的原语"，并断言原文那份声明现在
    **装载得过**（错的是文档旧注，不是声明本身）。
    **待人订正**：`docs/design/agent-capabilities.md:306` 仍写着 `kb.link.create` 的 op 形态"留 M3b"。
    """
    assert TOOL_CATALOG["kb.link.create"] == "create_edge"
    assert TOOL_CATALOG["kb.link.attach"] == "apply_link_instances"
    as_written = json.loads(json.dumps(KB_WRITE))
    as_written["provides"]["tools"][2]["tool_id"] = "kb.link.create"
    declaration, _w, errors = parse_declaration(as_written, source="builtin")
    assert not errors and declaration is not None
    assert declaration.tools[2].primitive == "create_edge"


# —— ③ 权限与审批（另两条安全底）——


def test_write_permission_with_auto_approval_is_rejected() -> None:
    raw = decl(approval={"read": "auto", "write": "auto"})
    declaration, _w, errors = parse_declaration(raw, source="builtin")
    assert declaration is None and "approval_too_loose" in codes(errors)


@pytest.mark.parametrize(
    "pattern",
    ["/etc/passwd", "C:/Windows/**", "../outside.md", "notes/../../escape.md"],
)
def test_escaping_globs_are_rejected(pattern: str) -> None:
    raw = decl(permissions={"read": [pattern], "write": ["**/*.md"]})
    declaration, _w, errors = parse_declaration(raw, source="builtin")
    assert declaration is None and "bad_field" in codes(errors)


@pytest.mark.parametrize("pattern", [".memoria/agent/sessions/**", ".memoria/agent/backups/**"])
def test_core_only_paths_cannot_be_claimed_for_write(pattern: str) -> None:
    """§1 末段：会话审计与备份是**核心**写的 ⇒ 插件声明它们算越界。"""
    raw = decl(permissions={"read": ["**/*.md"], "write": ["**/*.md", pattern]})
    declaration, _w, errors = parse_declaration(raw, source="builtin")
    assert declaration is None and "core_only_path" in codes(errors)


def test_read_permission_may_still_cover_the_agent_dir() -> None:
    """只读侧没有这条禁令（读备份/会话不越界）。"""
    raw = decl(permissions={"read": [".memoria/**"], "write": ["**/*.md"]})
    declaration, _w, errors = parse_declaration(raw, source="builtin")
    assert errors == [] and declaration is not None


def test_approval_is_required_and_must_use_the_vocabulary() -> None:
    declaration, _w, errors = parse_declaration(decl(approval={"read": "auto", "write": "maybe"}), source="builtin")
    assert declaration is None and "bad_field" in codes(errors)
    declaration2, _w2, errors2 = parse_declaration({k: v for k, v in KB_WRITE.items() if k != "approval"}, source="builtin")
    assert declaration2 is None and "bad_field" in codes(errors2)


# —— ④ 暂缓字段与未知字段：容忍但有话直说 ——


@pytest.mark.parametrize("key", ["kind", "emits", "forbidden", "unload", "enabled"])
def test_deferred_fields_warn_but_do_not_block(key: str) -> None:
    declaration, warnings, errors = parse_declaration(decl(**{key: "whatever"}), source="builtin")
    assert errors == [] and declaration is not None
    assert "deferred_field" in codes(list(warnings))


def test_unknown_fields_warn_but_do_not_block() -> None:
    """「只增不改」：未来版本新增的字段，旧读者要能忽略（不拒载）。"""
    declaration, warnings, errors = parse_declaration(decl(future_thing={"x": 1}), source="builtin")
    assert errors == [] and declaration is not None and "unknown_field" in codes(list(warnings))


# —— ⑤ 发现：三来源 + 重名即失败 ——


def test_loads_from_builtin_and_user_dirs(tmp_path: Path) -> None:
    builtin = tmp_path / "resources" / "agent-capabilities"
    builtin.mkdir(parents=True)
    (builtin / "kb-write.json").write_text(json.dumps(KB_WRITE, ensure_ascii=False), encoding="utf-8")
    user = tmp_path / "plugins"
    (user / "my-vision").mkdir(parents=True)
    (user / "my-vision" / "plugin.json").write_text(
        json.dumps(decl(id="my-vision", permissions={"read": ["**/*.png"], "write": []}, approval={"read": "auto", "write": "auto"}), ensure_ascii=False),
        encoding="utf-8",
    )
    result = load_declarations("", builtin_dir=str(builtin), user_dir=str(user))
    assert result.errors == ()
    assert {item.id: item.source for item in result.declarations} == {"kb-write": "builtin", "my-vision": "user"}


def test_duplicate_ids_fail_the_whole_load(tmp_path: Path) -> None:
    builtin = tmp_path / "b"
    builtin.mkdir()
    (builtin / "a.json").write_text(json.dumps(KB_WRITE, ensure_ascii=False), encoding="utf-8")
    user = tmp_path / "u"
    user.mkdir()
    (user / "b.json").write_text(json.dumps(KB_WRITE, ensure_ascii=False), encoding="utf-8")
    result = load_declarations("", builtin_dir=str(builtin), user_dir=str(user))
    assert result.declarations == ()  # §1：重复 ⇒ 装载失败，不静默取其一
    assert "duplicate_id" in codes(list(result.errors))


def test_broken_json_is_reported_not_swallowed(tmp_path: Path) -> None:
    builtin = tmp_path / "b"
    builtin.mkdir()
    (builtin / "broken.json").write_text("{ not json", encoding="utf-8")
    result = load_declarations("", builtin_dir=str(builtin))
    assert "unreadable" in codes(list(result.errors))


def test_missing_dirs_are_not_an_error(tmp_path: Path) -> None:
    result = load_declarations(str(tmp_path), builtin_dir=str(tmp_path / "nope"), user_dir=None)
    assert result == load_declarations(str(tmp_path), builtin_dir=None, user_dir=None) or result.errors == ()


# —— ⑥ 库级启停（`enabled[]`：条目存在即启用）——


def test_enablement_roundtrip_and_other_keys_are_preserved(tmp_path: Path) -> None:
    path = kb_registry_path(str(tmp_path))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps({"v": 1, "futureKey": {"keep": "me"}, "enabled": [{"id": "kb-write", "on": True, "config": {}}]}),
        encoding="utf-8",
    )
    assert kb_enablement(str(tmp_path))["kb-write"]["on"] is True

    set_enabled(str(tmp_path), "my-vision", True, {"backend": "paddleocr-vl"})
    set_enabled(str(tmp_path), "kb-write", False)
    rows = {row["id"]: row for row in json.loads(Path(path).read_text(encoding="utf-8"))["enabled"]}
    assert rows["kb-write"]["on"] is False  # 关掉是**置假**，条目留着便于回切
    assert rows["my-vision"]["config"] == {"backend": "paddleocr-vl"}
    assert json.loads(Path(path).read_text(encoding="utf-8"))["futureKey"] == {"keep": "me"}  # 不整文件覆写


def test_enablement_tolerates_missing_or_broken_file(tmp_path: Path) -> None:
    assert kb_enablement(str(tmp_path)) == {}
    path = kb_registry_path(str(tmp_path))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("{ broken", encoding="utf-8")
    assert kb_enablement(str(tmp_path)) == {}


def test_set_enabled_updates_in_place_without_duplicating(tmp_path: Path) -> None:
    set_enabled(str(tmp_path), "p1", True)
    set_enabled(str(tmp_path), "p1", False)
    payload = json.loads(Path(kb_registry_path(str(tmp_path))).read_text(encoding="utf-8"))
    assert payload["v"] == DECL_VERSION
    assert [row["id"] for row in payload["enabled"]] == ["p1"]
