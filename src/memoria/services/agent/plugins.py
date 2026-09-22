# 设计来源（唯一事实源）：`docs/design/agent-plugin-design.md` §1「最小可用契约 v1（6 字段）」
# 上游事实对照：同文件 §3；原语取值目录：`docs/design/agent-capabilities.md` §「M3 首批写原语目录」

"""能力插件的**声明面**：发现、校验、启停。**本模块不含任何执行体**。

契约铁律（§1 末行）：**插件目录内不含可执行代码**（无 `.py` / `.js` / 脚本），只含**声明 JSON + 只读资源**
⇒ 插件的"能力"从来不是它自己的代码，而是**核心原语目录里的原语**被它**声明**出来（§1 `provides.tools[]`
的 `tool_id` **必须**取自核心原语目录）。因此本模块只做四件事：

1. **解析**：把一份声明 JSON 读成 `PluginDeclaration`（6 字段，字段表见 §1）；
2. **校验**：§1「校验规则」列的硬规矩 —— `id` kebab 且唯一、`tool_id` 必须在原语目录、
   `permissions` 必须是**库内相对 glob**（越界即拒）、**`permissions.write` 非空 ⇒ `approval.write ≠ auto`**
   （§1 的"安全下限"，也是 §10 P9 里"插件无法自行降档"的落点）；
3. **发现**：三个来源按固定顺序扫，同名 `id` **重复即装载失败**（§1：不静默取其一）；
4. **启停**：库级注册表 = `<库>/.memoria/agent/capabilities.json` 的 `enabled[]`（§1 库级实样：
   **条目存在即启用** ⇒ 契约层不再需要 `enabled` 字段）。

**三个来源**（顺序即优先级，先出现者的信息用于 UI 分组与"来源"展示）：

| 来源 | 位置 | 说明 |
|---|---|---|
| `builtin` | `resources/agent-capabilities/*.json` | 随版本分发、**只读**（§1 内置实样，示例为 `kb-write.json`） |
| `kb` | `<库>/.memoria/agent/capabilities.json` 里内联的声明（可选） | 随库走；本模块只认它的 `enabled[]`（见下） |
| `user` | `config/plugins/<id>/plugin.json` | **用户导入**（拖拽 zip 落位后所在处）；本模块只读，落位与解包属导入器 |

> **未做（如实）**：zip 导入 / 解包 / 签名与路径穿越防护属**导入器**（下一步），本模块只认"已经落好位的目录"；
> `gate` 的求值（`kb_has_sidecar` 之类）与 `constrain` 的应用点分别在工具门控与 `validate_plan`（§2.1.1 / §2.3.4），
> 不在本模块；`config` 的**值位**保留但不校验（v1 无参数 schema，§2）。
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "APPROVAL_VALUES",
    "DECL_VERSION",
    "GATE_VALUES",
    "PLUGIN_ID_RE",
    "TOOL_CATALOG",
    "LoadResult",
    "PluginDeclaration",
    "ToolDeclaration",
    "kb_enablement",
    "load_declarations",
    "parse_declaration",
    "set_enabled",
]

#: 声明文件的**信封版本**（§1：只增不改；不占字段位）。
DECL_VERSION = 1

#: `id` 语法（§1「校验规则」：英文 kebab-case、唯一）。
PLUGIN_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")

#: `approval` 的取值（§1 字段表；词汇对齐上游 `ApprovalOutcome` 的 fail-closed 口径，§3 第 4 条）。
APPROVAL_VALUES = ("auto", "confirm", "never")

#: `gate` 的取值（§1 `provides.tools[]`；"该动作类是否出现在模型可见工具面"）。
GATE_VALUES = ("always", "kb_has_sidecar")

#: **核心原语目录**（§1：`tool_id` 的取值目录；不在此表 ⇒ 拒绝装载）。
#: 左 = 声明里的 `tool_id`（`docs/design/agent-capabilities.md` §「M3 首批写原语目录」的**权威命名**），
#: 右 = 本仓库代码里的原语名（`services/agent/apply.py::PRIMITIVES` 的键）—— 这张对照表就是**唯一的命名桥**，
#: 两边任何一侧增删都应同步改这里（对照关系本身已登记进 `agent-plugin-design.md §5`）。
TOOL_CATALOG: dict[str, str] = {
    "kb.kp.create": "confirm_kp_range",
    "kb.kp.update": "update_kp",
    "kb.kp.delete": "delete_kp",
    "kb.kp.rename": "rename_kp_id",
    "kb.link.attach": "apply_link_instances",
    "kb.link.detach": "detach_link_instance",
    "kb.link.create": "create_edge",
    "kb.file.create": "create_file",
    "kb.file.rename": "rename_file",
    "kb.file.delete": "delete_file",
    "kb.file.move": "move_file",
    "kb.file.edit": "edit_body",
    "kb.manifest.rebuild": "rebuild_manifest",
}

#: **设计已列、代码未实现**的 `tool_id`（声明它们 ⇒ 专门错误 `tool_not_implemented`，而不是含糊地
#: 报"不在目录里"）。**2026-09-22 收缩**：`kb.link.create`（纯边 `create_edge`）已随"sidecar 结构 op"
#: 一起落地（`plan.OP_UPSERT_EDGE` / `apply._call_create_edge`）⇒ 移入上面的目录；同轮新增的还有
#: `kb.kp.delete`（`delete_kp`）与 `kb.kp.rename`（`rename_kp_id`）。**只剩 `kb.link.set_type`**：
#: 「改一条已有边的类型」在设计里是独立动作（`agent-capabilities.md:300`），代码侧今天没有等价原语
#: （`document.delete_edge` 能删、但没有原地改型）⇒ 待人的设计拍板后再补。
#: 反向缺口（登记）：代码原语 `delete_link_route` 尚无权威 `tool_id`（设计表未列）⇒ 未进任何一侧，
#: 待人的设计补齐后同步。
PLANNED_TOOLS: frozenset[str] = frozenset({"kb.link.set_type"})

#: §2「暂缓字段」：写进声明文件就是笔误（该表已逐条给出移出理由）⇒ 装载期给**专门告警**，
#: 但仍按"只增不改"**容忍**（未知键不拒载，只提示）。
DEFERRED_KEYS = frozenset(
    {"kind", "forbidden", "emits", "verify", "provenance", "unload", "enabled", "config", "prompt"}
)

#: **核心独占**的路径前缀（§1 末段：`kb-write` 的 `permissions.write` 明确**不含**这两处 ——
#: 审计事件与备份是**核心**写的 ⇒ 任何插件声明它们都属越界，直接拒载）。
CORE_ONLY_WRITE_PREFIXES = (".memoria/agent/sessions", ".memoria/agent/backups")

#: 内置声明目录（随版本分发、只读）与用户导入目录（相对**程序配置目录**）。
BUILTIN_DIRNAME = os.path.join("resources", "agent-capabilities")
USER_PLUGINS_DIRNAME = os.path.join("plugins")

#: 库级注册表文件名（§1 库级实样）。
KB_REGISTRY_NAME = "capabilities.json"


@dataclass(frozen=True, slots=True)
class ToolDeclaration:
    """一条工具声明（`provides.tools[]` 的一项）。"""

    tool_id: str
    gate: str = "always"
    constrain: Mapping[str, Any] = field(default_factory=dict)

    @property
    def primitive(self) -> str:
        """该 `tool_id` 对应的**核心原语名**（落盘实现；插件自己不写盘）。"""
        return TOOL_CATALOG[self.tool_id]


@dataclass(frozen=True, slots=True)
class PluginDeclaration:
    """一份**通过校验**的插件声明（§1 的 6 字段 + 来源信息）。"""

    id: str
    name: str
    tools: tuple[ToolDeclaration, ...]
    read: tuple[str, ...]
    write: tuple[str, ...]
    approval: Mapping[str, str]
    source: str
    """`builtin` / `kb` / `user` —— 供 UI 分组（§1 字段演进（一）：UI 先按来源分组）。"""
    path: str
    """声明文件所在处（人可核；装载告警里一并带出）。"""

    @property
    def writable(self) -> bool:
        """是否有写动作类（`permissions.write` 非空，§1）。"""
        return bool(self.write)


@dataclass(frozen=True, slots=True)
class LoadResult:
    """一次装载的结果：成功的声明 + 告警 + 错误（**错误非空 ⇒ 该来源整体不算数**）。"""

    declarations: tuple[PluginDeclaration, ...] = ()
    warnings: tuple[Mapping[str, Any], ...] = ()
    errors: tuple[Mapping[str, Any], ...] = ()


def _issue(kind: str, plugin_id: str, message: str, path: str = "") -> dict[str, Any]:
    return {"kind": kind, "id": plugin_id, "message": message, "path": path}


def _check_glob(value: Any, *, field_name: str, plugin_id: str, path: str, errors: list[dict]) -> list[str]:
    """`permissions.*` 的 glob 校验：**库内相对**、不得上跳/绝对/盘符（§1「校验规则」）。"""
    if not isinstance(value, list):
        errors.append(_issue("bad_field", plugin_id, f"`{field_name}` 必须是数组", path))
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip().replace("\\", "/")
        if not text:
            errors.append(_issue("bad_field", plugin_id, f"`{field_name}` 里有空条目", path))
            continue
        if text.startswith("/") or re.match(r"^[a-zA-Z]:", text):
            errors.append(_issue("bad_field", plugin_id, f"`{field_name}` 不得是绝对路径：{item!r}", path))
            continue
        if ".." in text.split("/"):
            errors.append(_issue("bad_field", plugin_id, f"`{field_name}` 不得上跳：{item!r}", path))
            continue
        out.append(text)
    return out


def parse_declaration(raw: Any, *, source: str, path: str = "") -> tuple[PluginDeclaration | None, list[dict], list[dict]]:
    """把一份声明 JSON 解析并校验成 `PluginDeclaration`。

    返回 `(声明 | None, warnings, errors)`；**`errors` 非空 ⇒ 声明为 `None`**（不静默取一半）。
    """
    warnings: list[dict] = []
    errors: list[dict] = []
    if not isinstance(raw, Mapping):
        return None, warnings, [_issue("bad_json", "", "声明必须是 JSON 对象", path)]

    plugin_id = str(raw.get("id") or "")
    if raw.get("v") != DECL_VERSION:
        errors.append(
            _issue("bad_envelope", plugin_id, f"`v` 必须是 {DECL_VERSION}（未知信封 ⇒ 拒载，§1「只增不改」）", path)
        )
    for key in raw:
        if key in DEFERRED_KEYS:
            warnings.append(
                _issue("deferred_field", plugin_id, f"`{key}` 是 §2 暂缓字段，不该写进声明文件（已忽略）", path)
            )
        elif key not in ("v", "id", "name", "provides", "permissions", "approval"):
            warnings.append(_issue("unknown_field", plugin_id, f"未知字段 `{key}`（已忽略，按「只增不改」容忍）", path))
    if not PLUGIN_ID_RE.match(plugin_id):
        errors.append(_issue("bad_id", plugin_id, f"`id` 非法（须 kebab-case）：{plugin_id!r}", path))

    provides = raw.get("provides")
    tools: list[ToolDeclaration] = []
    raw_tools = provides.get("tools") if isinstance(provides, Mapping) else None
    if not isinstance(raw_tools, Sequence) or isinstance(raw_tools, (str, bytes)) or not raw_tools:
        errors.append(_issue("bad_field", plugin_id, "`provides.tools` 必须是非空数组（§1 必填）", path))
    else:
        for item in raw_tools:
            if not isinstance(item, Mapping):
                errors.append(_issue("bad_field", plugin_id, "`provides.tools[]` 每项必须是对象", path))
                continue
            tool_id = str(item.get("tool_id") or "")
            if tool_id in PLANNED_TOOLS:
                errors.append(
                    _issue(
                        "tool_not_implemented",
                        plugin_id,
                        f"`tool_id` 设计已列但**代码未实现**（留 M3b）：{tool_id!r} ⇒ 现在声明它拿不到落盘实现",
                        path,
                    )
                )
                continue
            if tool_id not in TOOL_CATALOG:
                errors.append(
                    _issue(
                        "unknown_tool",
                        plugin_id,
                        f"`tool_id` 不在核心原语目录里：{tool_id!r}（可选：{', '.join(sorted(TOOL_CATALOG))}）",
                        path,
                    )
                )
                continue
            gate = str(item.get("gate") or "always")
            if gate not in GATE_VALUES:
                errors.append(_issue("bad_field", plugin_id, f"`gate` 取值非法：{gate!r}（可选：{', '.join(GATE_VALUES)}）", path))
                continue
            constrain = item.get("constrain") or {}
            if not isinstance(constrain, Mapping):
                errors.append(_issue("bad_field", plugin_id, "`constrain` 必须是对象", path))
                continue
            for sub in item:
                if sub not in ("tool_id", "gate", "constrain"):
                    warnings.append(_issue("unknown_field", plugin_id, f"`provides.tools[]` 未知子字段 `{sub}`（已忽略）", path))
            tools.append(ToolDeclaration(tool_id=tool_id, gate=gate, constrain=dict(constrain)))

    permissions = raw.get("permissions") if isinstance(raw.get("permissions"), Mapping) else {}
    read = _check_glob(permissions.get("read", []), field_name="permissions.read", plugin_id=plugin_id, path=path, errors=errors)
    write = _check_glob(
        permissions.get("write", []), field_name="permissions.write", plugin_id=plugin_id, path=path, errors=errors
    )
    for pattern in write:
        if pattern.startswith(CORE_ONLY_WRITE_PREFIXES):
            errors.append(
                _issue(
                    "core_only_path",
                    plugin_id,
                    f"`permissions.write` 不得包含核心独占路径：{pattern}（会话审计与备份由核心写，§1 末段）",
                    path,
                )
            )

    approval_raw = raw.get("approval") if isinstance(raw.get("approval"), Mapping) else None
    approval: dict[str, str] = {}
    if approval_raw is None:
        errors.append(_issue("bad_field", plugin_id, "`approval` 必填（`{read, write}`，§1）", path))
    else:
        for kind in ("read", "write"):
            value = str(approval_raw.get(kind) or "")
            if value not in APPROVAL_VALUES:
                errors.append(
                    _issue("bad_field", plugin_id, f"`approval.{kind}` 取值非法：{value!r}（可选：{', '.join(APPROVAL_VALUES)}）", path)
                )
                continue
            approval[kind] = value
        for key in approval_raw:
            if key not in ("read", "write"):
                warnings.append(_issue("unknown_field", plugin_id, f"`approval` 未知子字段 `{key}`（已忽略）", path))

    # §1 **安全下限**：有写动作类 ⇒ `approval.write` 不得为 `auto`（硬校验，§10 P9）
    if write and approval.get("write") == "auto":
        errors.append(
            _issue(
                "approval_too_loose",
                plugin_id,
                "`permissions.write` 非空 ⇒ `approval.write` 不得为 `auto`（§1 安全下限；插件无法自行降档）",
                path,
            )
        )

    if errors:
        return None, warnings, errors
    return (
        PluginDeclaration(
            id=plugin_id,
            name=str(raw.get("name") or "").strip() or plugin_id,  # §1：缺省回落 `id`
            tools=tuple(tools),
            read=tuple(read),
            write=tuple(write),
            approval=dict(approval),
            source=source,
            path=path,
        ),
        warnings,
        errors,
    )


def load_declarations(
    kb_path: str,
    *,
    builtin_dir: str | None = None,
    user_dir: str | None = None,
    extra: Iterable[tuple[str, Mapping[str, Any], str]] = (),
) -> LoadResult:
    """扫三个来源并校验；**同名 `id` 重复 ⇒ 装载失败**（§1：不静默取其一）。

    `extra` 供库级内联声明（`(source, raw, path)`）用 —— 库内声明的**正文**属 `capabilities.json` 的
    可选扩展位，本模块只做同样的校验，不解释它的语义。
    """
    found: dict[str, PluginDeclaration] = {}
    warnings: list[dict] = []
    errors: list[dict] = []

    def _absorb(raw: Any, source: str, path: str) -> None:
        declaration, warns, errs = parse_declaration(raw, source=source, path=path)
        warnings.extend(warns)
        if errs:
            errors.extend(errs)
            return
        assert declaration is not None
        if declaration.id in found:
            other = found[declaration.id]
            errors.append(
                _issue(
                    "duplicate_id",
                    declaration.id,
                    f"插件 `id` 重复（已在 {other.path or other.source} 装载过）⇒ 装载失败，不静默取其一",
                    path,
                )
            )
            return
        found[declaration.id] = declaration

    for source, directory in (("builtin", builtin_dir), ("user", user_dir)):
        if not directory or not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            full = os.path.join(directory, name)
            if os.path.isdir(full):
                full = os.path.join(full, "plugin.json")
                if not os.path.isfile(full):
                    continue
            elif not name.lower().endswith(".json"):
                continue
            try:
                with open(full, "r", encoding="utf-8") as handle:
                    raw = json.load(handle)
            except (OSError, ValueError) as exc:
                errors.append(_issue("unreadable", "", f"声明文件读不了或不是合法 JSON：{exc}", full))
                continue
            _absorb(raw, source, full)

    for source, raw, path in extra:
        _absorb(raw, source, path)

    if errors:
        return LoadResult(declarations=(), warnings=tuple(warnings), errors=tuple(errors))
    return LoadResult(declarations=tuple(found.values()), warnings=tuple(warnings), errors=())


# ── 库级启停（§1「库级启用实样」：`enabled[]` = 库级注册表，**条目存在即启用**）──────────────


def kb_registry_path(kb_path: str) -> str:
    """库级注册表文件：`<库>/.memoria/agent/capabilities.json`。"""
    return os.path.join(str(kb_path), ".memoria", "agent", KB_REGISTRY_NAME)


def kb_enablement(kb_path: str) -> dict[str, dict[str, Any]]:
    """读库级 `enabled[]` → `{id: {on, config}}`；文件不存在/损坏 ⇒ 空表（**不抛**）。"""
    path = kb_registry_path(kb_path)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return {}
    entries = raw.get("enabled") if isinstance(raw, Mapping) else None
    if not isinstance(entries, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item in entries:
        if not isinstance(item, Mapping):
            continue
        plugin_id = str(item.get("id") or "")
        if not plugin_id:
            continue
        config = item.get("config")
        out[plugin_id] = {"on": bool(item.get("on", True)), "config": dict(config) if isinstance(config, Mapping) else {}}
    return out


def set_enabled(kb_path: str, plugin_id: str, on: bool, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """写回库级 `enabled[]`（**条目存在即启用**；`on=False` 时保留条目但置假，便于回切）。

    **只动 `enabled[]`**：文件里其它键（未来可能有的库级扩展位）原样保留 ⇒ 不做"整文件覆写"。
    """
    import tempfile

    path = kb_registry_path(kb_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing: dict[str, Any] = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, Mapping):
                existing = dict(loaded)
        except (OSError, ValueError):
            existing = {}
    entries = existing.get("enabled")
    rows: list[dict[str, Any]] = [dict(item) for item in entries if isinstance(item, Mapping)] if isinstance(entries, list) else []
    merged = {"on": bool(on), "config": dict(config or {})}
    for row in rows:
        if str(row.get("id") or "") == str(plugin_id):
            row.update(merged)
            break
    else:
        rows.append({"id": str(plugin_id), **merged})
    payload = {"v": int(existing.get("v") or DECL_VERSION), **{k: v for k, v in existing.items() if k not in ("v", "enabled")}}
    payload["enabled"] = rows
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)
    return {"status": "ok", "path": path, "id": str(plugin_id), "on": bool(on)}
