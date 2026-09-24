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
    NET_CATALOG,
    NET_TOOL_IDS,
    PLANNED_TOOLS,
    TOOL_CATALOG,
    active_plugins,
    builtin_dir,
    capability_note,
    kb_enablement,
    kb_registry_path,
    load_declarations,
    normalize_plugin_config,
    parse_declaration,
    set_enabled,
)
from memoria.services.agent.plan import PLAN_VERSION, validate_plan
from memoria.services.agent.tools import build_kb_tools
from memoria.services.agent.tools.kb import PROPOSE_TOOL_NAME

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


# —— 2026-09-24 追加：**库级参数 schema**（第一例 = `web-fetch` 的域名名单）+ 出网族目录 ——


def test_net_catalog_and_bridge_are_pinned() -> None:
    """出网族目录与"工具名 → `tool_id`"命名桥（工具级闸靠它；`plan` 那边有 `OP_TOOL_IDS`）。"""
    assert set(NET_CATALOG) == {"net.search", "net.fetch"}
    assert not set(NET_CATALOG) & set(TOOL_CATALOG), "两张目录互不重叠（族 ≠ 混装）"
    assert NET_TOOL_IDS == {"web_search": "net.search", "fetch_url": "net.fetch"}
    assert not set(NET_CATALOG) & set(PLANNED_TOOLS), "已落地的动作类不该还挂在'设计已列未实现'里"


def test_plugin_config_schema_normalises_and_rejects() -> None:
    """库级 `config` 归一口径：**有 schema 的插件**归一 + 坏写法**如实报告**；没 schema 的原样保留。"""
    ok, issues = normalize_plugin_config(
        "web-fetch", {"allow": ["Example.com", "*.sub.example.org"], "deny": "ads.example.com"}
    )
    assert issues == [] and ok == {"allow": ["example.com", "sub.example.org"], "deny": ["ads.example.com"]}

    bad, issues = normalize_plugin_config("web-fetch", {"allow": ["中文.com"]})
    assert bad == {"allow": []} and [issue["kind"] for issue in issues] == ["bad_config"], "坏写法要报，不许静默丢"

    _, issues = normalize_plugin_config("web-fetch", {"allow": [], "nope": 1})
    assert [issue["kind"] for issue in issues] == ["unknown_param"]

    _, issues = normalize_plugin_config("web-fetch", {"deny": 42})
    assert [issue["kind"] for issue in issues] == ["bad_config"]

    keep, issues = normalize_plugin_config("my-vision", {"threshold": 0.5})
    assert keep == {"threshold": 0.5} and issues == [], "没 schema 的插件：值位保留、原样透传（只增不改）"


def test_set_enabled_rejects_bad_config_and_keeps_good(tmp_path: Path) -> None:
    """写侧**拒写**（fail-closed）：坏写法不许进注册表 —— 否则读侧只能丢弃，人会以为"配上了"。"""
    assert set_enabled(str(tmp_path), "web-fetch", True, {"allow": ["ok.com"]})["status"] == "ok"
    rejected = set_enabled(str(tmp_path), "web-fetch", True, {"allow": ["中文.com"]})
    assert rejected["status"] == "error" and rejected["code"] == "bad_plugin_config"
    assert kb_enablement(str(tmp_path))["web-fetch"]["config"] == {"allow": ["ok.com"]}, "坏值没被写进去"


def test_active_plugins_carries_kb_config(tmp_path: Path) -> None:
    """`ActivePlugins.configs` 只带**启用**插件的归一化参数（注册表缺失 ⇒ 空表 ⇒ 回落机器级默认）。"""
    kb = tmp_path / "kb"
    (kb / ".memoria" / "agent").mkdir(parents=True)
    set_enabled(str(kb), "web-fetch", True, {"allow": ["docs.python.org"]})
    active = active_plugins(str(kb), builtin=builtin_dir(), user=None)
    assert active.registry_present is True
    assert active.configs == {"web-fetch": {"allow": ["docs.python.org"]}}
    set_enabled(str(kb), "web-fetch", False)
    assert active_plugins(str(kb), builtin=builtin_dir(), user=None).configs == {}, "停用的插件不带参数"


def test_set_enabled_updates_in_place_without_duplicating(tmp_path: Path) -> None:
    set_enabled(str(tmp_path), "p1", True)
    set_enabled(str(tmp_path), "p1", False)
    payload = json.loads(Path(kb_registry_path(str(tmp_path))).read_text(encoding="utf-8"))
    assert payload["v"] == DECL_VERSION
    assert [row["id"] for row in payload["enabled"]] == ["p1"]


# ── 2026-09-22 追加：**契约接线**（`active_plugins()` —— 让声明面真正生效）─────────────────────
# 钉住 `plugins.py` 末尾「契约接线」的三条口径，以及闸真的落在 `plan.validate_plan` / `propose_write`
# 描述上（在那之前这一整套没有生产调用者 ⇒ 声明写了也不生效）。口径来源：`dsh-agent-port.md §6.25`。


def _builtin_with(tmp_path: Path, *raws: dict[str, Any]) -> str:
    """临时内置目录（替代随包那份），供"换一份声明"的用例用。"""
    directory = tmp_path / "builtin"
    directory.mkdir(exist_ok=True)
    for index, raw in enumerate(raws):
        (directory / f"p{index}.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return str(directory)


#: 本文件那份**样例声明**（`KB_WRITE`）声明出来的动作类 —— 临时内置目录的用例拿它当"全部"的基准
#: （随包那份声明覆盖 `TOOL_CATALOG` 全集，由上面的 `test_shipped_...` 单独钉）。
SAMPLE_TOOL_IDS: frozenset[str] = frozenset(str(t["tool_id"]) for t in KB_WRITE["provides"]["tools"])


def test_shipped_builtin_declaration_is_clean_and_covers_the_whole_catalog() -> None:
    """随包那几份声明：**零 error、零 warning**，且把**两张原语目录**（写族 + 出网族）的每个动作类都声明出来。

    为什么钉这条：内置声明随版本分发（`packaging/build.py` 的 `_REQUIRED_RELEASE_RESOURCES` 也带了它），
    而"声明装载出错 ⇒ 闸到底"意味着它一破、所有写 op 都会被拒 ⇒ 这种破绽必须在 CI 拦住，不能留到生产。
    覆盖性同理：漏声明一个动作类 = 那个能力在**所有库**里不可用（而模型只会看到"没启用"）。
    2026-09-24：出网族（`NET_CATALOG` 的 `net.search` / `net.fetch`）也进同一份对照 —— 它们由
    `web-search.json` / `web-fetch.json` 覆盖，且是**逐库启停**的对象。
    """
    directory = builtin_dir()
    assert directory, "内置声明目录缺失：resources/agent-capabilities/（随包会漏，能力闸也就形同虚设）"
    result = load_declarations("", builtin_dir=directory, user_dir=None)
    assert result.errors == (), f"随包声明有 error：{result.errors}"
    assert result.warnings == (), f"随包声明有 warning（不该有）：{result.warnings}"
    declared = {tool.tool_id for decl in result.declarations for tool in decl.tools}
    catalog = set(TOOL_CATALOG) | set(NET_CATALOG)
    missing = sorted(catalog - declared)
    extra = sorted(declared - catalog)
    assert declared == catalog, f"声明与命名桥不一致：缺 {missing} / 多 {extra}"


def test_kb_without_registry_keeps_everything_enabled(tmp_path: Path) -> None:
    """口径 1 前半：库级注册表缺失 ⇒ 内置默认全启用（存量库不被这次接线掐断写能力）。"""
    kb = tmp_path / "kb"
    kb.mkdir()
    active = active_plugins(str(kb), builtin=_builtin_with(tmp_path, KB_WRITE), user=None)
    assert active.enforced is True and active.registry_present is False
    assert active.tool_ids == SAMPLE_TOOL_IDS
    assert active.op_available("upsert_kp") is True


def test_registry_makes_enablement_authoritative(tmp_path: Path) -> None:
    """口径 1 后半：注册表在 ⇒ 以它为准（`on:false` = 停用；`on:true` = 启用）。"""
    kb = tmp_path / "kb"
    kb.mkdir()
    builtin = _builtin_with(tmp_path, KB_WRITE)
    set_enabled(str(kb), "kb-write", False)
    off = active_plugins(str(kb), builtin=builtin, user=None)
    assert off.registry_present is True and off.enforced is True
    assert off.tool_ids == frozenset(), "关掉之后能力面必须是空的"
    assert off.op_available("upsert_kp") is False and off.op_available("create_file") is False
    set_enabled(str(kb), "kb-write", True)
    assert active_plugins(str(kb), builtin=builtin, user=None).tool_ids == SAMPLE_TOOL_IDS


def test_no_declaration_at_all_means_no_gate(tmp_path: Path) -> None:
    """口径 2：一份声明都没有 ⇒ 不闸（契约没参与），行为同接线前，且给模型的话术为空串。"""
    kb = tmp_path / "kb"
    kb.mkdir()
    active = active_plugins(str(kb), builtin=str(tmp_path / "nope"), user=None)
    assert active.enforced is False and active.declarations_seen == 0
    assert active.op_available("upsert_kp") is True
    assert capability_note(active) == ""


def test_broken_declaration_blocks_writes(tmp_path: Path) -> None:
    """口径 3：声明装载出错 ⇒ 闸到底（fail-closed）—— 宁可不写，也不在"能力面未知"时写。"""
    kb = tmp_path / "kb"
    kb.mkdir()
    broken = dict(KB_WRITE, id="Bad_Id")  # id 非 kebab ⇒ 校验失败
    active = active_plugins(str(kb), builtin=_builtin_with(tmp_path, broken), user=None)
    assert active.errors and active.declarations_seen == 0
    assert active.enforced is True
    assert active.tool_ids == frozenset()
    assert active.op_available("upsert_kp") is False


def test_capability_note_tells_the_model_what_is_enabled(tmp_path: Path) -> None:
    """给模型的话术两态：启用时点名动作类；全停时明说"会被拒"（不是让它去撞错）。"""
    kb = tmp_path / "kb"
    kb.mkdir()
    builtin = _builtin_with(tmp_path, KB_WRITE)
    note_on = capability_note(active_plugins(str(kb), builtin=builtin, user=None))
    assert "kb.kp.create" in note_on and "capability_disabled" in note_on
    set_enabled(str(kb), "kb-write", False)
    note_off = capability_note(active_plugins(str(kb), builtin=builtin, user=None))
    assert "未启用" in note_off and "capability_disabled" in note_off


def test_validate_plan_rejects_ops_of_a_disabled_capability(tmp_path: Path) -> None:
    """闸真的落在 `validate_plan` 上：库级关掉 `kb-write` ⇒ 该批 op 报 `capability_disabled`（拒整批）。

    这条是"契约**生效**"的核心证据 —— 在此之前，关不关 `enabled[]` 对写权限毫无影响。
    """
    kb = tmp_path / "kb"
    kb.mkdir()
    set_enabled(str(kb), "kb-write", False)
    plan = {
        "v": PLAN_VERSION,
        "txid": "20260922T000000Z-01",
        "intent": "测试用 plan",
        "ops": [{"op": "create_file", "op_id": "o1", "file": "notes/new.md", "content": "# 新文件\n"}],
    }
    checked = validate_plan(str(kb), plan)
    assert checked["status"] == "error"
    assert "capability_disabled" in {str(e["code"]) for e in checked["errors"]}, checked["errors"]


def test_validate_plan_has_no_capability_error_without_a_registry(tmp_path: Path) -> None:
    """对照组：注册表缺失（= 默认全启用）⇒ 同一个 op **不会**被能力闸拦（存量库照旧能写）。"""
    kb = tmp_path / "kb"
    kb.mkdir()
    plan = {
        "v": PLAN_VERSION,
        "txid": "20260922T000000Z-02",
        "intent": "测试用 plan",
        "ops": [{"op": "create_file", "op_id": "o1", "file": "notes/new.md", "content": "# 新文件\n"}],
    }
    codes = {str(e["code"]) for e in validate_plan(str(kb), plan)["errors"]}
    assert "capability_disabled" not in codes, codes


def test_propose_write_description_carries_the_kb_capability_note(tmp_path: Path) -> None:
    """工具描述里带"本库已启用的能力动作"（模型自己就知道边界，不必撞了才回头）。"""
    kb = tmp_path / "kb"
    kb.mkdir()
    tools = {tool.name: tool for tool in build_kb_tools(str(kb))}
    description = tools[PROPOSE_TOOL_NAME].description
    assert "本库已启用的能力动作" in description and "kb.kp.create" in description
    set_enabled(str(kb), "kb-write", False)
    off = {tool.name: tool for tool in build_kb_tools(str(kb))}[PROPOSE_TOOL_NAME].description
    assert "未启用" in off and "capability_disabled" in off


def test_plugin_gateway_lists_and_toggles(tmp_path: Path) -> None:
    """网关（`agent_plugins` / `agent_plugin_set`）：列声明与启用位，且**真的能库级启停**。

    这条是"人可用"的那一半 —— 契约再完整，没有口岸就只能手改 JSON（而 JSON 的路径又不在 UI 里）。
    """
    from memoria.presentation.api.ui import UIAPI

    kb = tmp_path / "kb"
    kb.mkdir()
    api = UIAPI(kb_path=str(kb))
    listed = api.agent_plugins()
    assert listed["status"] == "ok"
    assert listed["registry_present"] is False and listed["enforced"] is True
    row = next(item for item in listed["plugins"] if item["id"] == "kb-write")
    assert row["enabled"] is True and "kb.kp.create" in row["tools"]
    assert row["source"] == "builtin"
    turned_off = api.agent_plugin_set("kb-write", False)
    assert turned_off["registry_present"] is True and turned_off["tool_ids"] == []
    assert next(item for item in turned_off["plugins"] if item["id"] == "kb-write")["enabled"] is False
    assert Path(listed["registry_path"]).is_file(), "启停必须落到库级注册表文件上"
    back = api.agent_plugin_set("kb-write", True)
    assert "kb.kp.create" in back["tool_ids"]


def test_gateway_returns_kb_params_even_when_the_plugin_is_off(tmp_path: Path) -> None:
    """停用的插件**也要回填库级参数**（2026-09-24 真机踩到的静默数据丢失）。

    面板的就地编辑是"以 `row.config` 为底、只改一个键"→ 保存。若停用行列里 `config` 是空的，
    人在一个框里改一下就会把另一个已存的键**覆盖丢掉**。⇒ 参数回填与启用位解耦（工具面仍只认启用者）。
    """
    from memoria.presentation.api.ui import UIAPI

    kb = tmp_path / "kb"
    kb.mkdir()
    api = UIAPI(kb_path=str(kb))
    api.agent_plugin_set("web-fetch", True, None, {"allow": ["docs.python.org"], "deny": ["ads.example.com"]})
    off = api.agent_plugin_set("web-fetch", False)
    row = next(item for item in off["plugins"] if item["id"] == "web-fetch")
    assert row["enabled"] is False
    assert row["config"] == {"allow": ["docs.python.org"], "deny": ["ads.example.com"]}, "停用也要回填，供就地编辑"
    assert row["params"] == ["allow", "deny"]
    assert off["tool_ids"] == [], "工具面只认启用的那一个（停用即从能力面消失）"

    # 后端语义：`config` **按提交原样写**（"带全键"是面板的责任 —— 面板正是靠上面那条回填把底带全）
    saved = api.agent_plugin_set("web-fetch", False, None, {"allow": ["docs.python.org"]})
    kept = next(item for item in saved["plugins"] if item["id"] == "web-fetch")["config"]
    assert kept == {"allow": ["docs.python.org"]}, "提交什么就写什么（不合并、不猜）"


def test_gateway_rejects_bad_kb_param_shape(tmp_path: Path) -> None:
    """网关透传**拒写**：域名写法坏 ⇒ `bad_plugin_config` + 逐条 issues（面板原样显示）。"""
    from memoria.presentation.api.ui import UIAPI

    kb = tmp_path / "kb"
    kb.mkdir()
    api = UIAPI(kb_path=str(kb))
    bad = api.agent_plugin_set("web-fetch", True, None, {"allow": ["中文.com"]})
    assert bad["status"] == "error" and bad["code"] == "bad_plugin_config"
    assert bad["issues"] and bad["issues"][0]["kind"] == "bad_config"
    assert kb_enablement(str(kb)) == {}, "拒写的值不许落到注册表"


def test_plugin_gateway_needs_an_open_kb() -> None:
    """没开库 ⇒ 明确 `no_kb`（不猜一个默认库出来）。"""
    from memoria.presentation.api.ui import UIAPI

    api = UIAPI(kb_path=None)
    assert api.agent_plugins()["code"] == "no_kb"
    assert api.agent_plugin_set("kb-write", True)["code"] == "no_kb"
