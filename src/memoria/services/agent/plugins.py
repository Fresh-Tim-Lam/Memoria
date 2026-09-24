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
    "ActivePlugins", "OP_TOOL_IDS", "active_plugins", "builtin_dir", "capability_note", "user_dir",
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
        """该 `tool_id` 对应的**核心原语名**（落盘实现；插件自己不写盘）。

        2026-09-24：**出网族（`net.*`）没有落盘原语** —— 它在 `NET_CATALOG` 里指向实现入口
        （`web.WebClient.search` / `.fetch`）。两张表**并集**才是"合法 `tool_id`"的全集（见文件尾
        「出网原语目录」块）。
        """
        return TOOL_CATALOG.get(self.tool_id) or NET_CATALOG[self.tool_id]


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
            if tool_id not in TOOL_CATALOG and tool_id not in NET_CATALOG:
                errors.append(
                    _issue(
                        "unknown_tool",
                        plugin_id,
                        f"`tool_id` 不在核心原语目录（写族 `kb.*` + 出网族 `net.*`）里：{tool_id!r}"
                        f"（可选：{', '.join(sorted(TOOL_CATALOG | NET_CATALOG))}）",
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
        normalized, _issues = normalize_plugin_config(plugin_id, config)
        out[plugin_id] = {"on": bool(item.get("on", True)), "config": normalized}
    return out


def set_enabled(kb_path: str, plugin_id: str, on: bool, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """写回库级 `enabled[]`（**条目存在即启用**；`on=False` 时保留条目但置假，便于回切）。

    **只动 `enabled[]`**：文件里其它键（未来可能有的库级扩展位）原样保留 ⇒ 不做"整文件覆写"。

    `config`（2026-09-24 起**有了第一例 schema**，见文件尾「库级参数 schema」块）：形状非法
    ⇒ **拒写**（返回 `{status:"error", code:"bad_plugin_config"}`，不静默丢字段）。
    """
    import tempfile

    normalized, issues = normalize_plugin_config(plugin_id, config)
    if issues:
        return {
            "status": "error",
            "code": "bad_plugin_config",
            "message": str(issues[0].get("message") or "参数形状非法"),
            "issues": issues,
        }

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
    merged = {"on": bool(on), "config": normalized}
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


# ── 2026-09-22 追加：**契约接线** —— 让声明面真正生效（`active_plugins()`）──────────────────────
#
# 为什么加这一段：上面那套（解析 / 校验 / 三来源发现 / 库级启停）此前**没有任何生产调用者**
# ⇒ 声明文件写不写、库里启不启用，对"模型此刻能用哪些能力"毫无影响（`docs/design/dsh-agent-port.md §8`
# 记的欠债：**「`capabilities.json` 零命中 ⇒ 今天是『直接工具』而非声明式插件」**）。本段把三件事接上：
# ① **算能力面** = `active_plugins(kb_path)`；② **闸 op** = `plan.validate_plan()` 用 `ActivePlugins.op_available()`；
# ③ **告诉模型** = `propose_write` 的工具描述末尾附 `capability_note()`。
#
# 三条口径（本地判断，已登记进 `agent-plugin-design.md §5` 同日至此行）：
#   1. **库级注册表缺失 ⇒ 内置默认全启用**（fail-open）：注册表随库走、可后补，而内置声明**随版本分发**
#      ⇒ 存量库（今天全都没有 `capabilities.json`）不会因为这次接线突然写不了。文件一旦存在，
#      **以它为准**（`enabled[]` 条目存在即启用；`on: false` = 停用；没列到的内置插件 = 停用）。
#   2. **一份声明都没有 ⇒ 不闸**（只告警）：契约没参与（例如从残缺拷贝里跑），此时行为 = 接线之前。
#   3. **声明装载出错 ⇒ 闸到底**（fail-closed）：`errors` 非空时 `tool_ids` 为空 ⇒ 所有写 op 被拒，
#      并把错误原样带出去。内置声明是随版本分发的，其破绽由单测拦（`tests/test_agent_plugins.py`
#      钉住"随包那份声明零 error 零 warning"）⇒ 不该在生产里以"写不了"的形式暴露。

#: **能力动作类（`kb.*`）↔ 写入 op 动词**（`plan.py::KNOWN_OPS`）—— 命名桥的**第二半**
#: （第一半 = `TOOL_CATALOG`：`kb.*` → 落盘原语）。契约用 `kb.*` 说话，校验/落盘用 op 动词说话，
#: 这两张表就是唯一的翻译处。一个 op 可落在**多个**动作类上（`upsert_kp`：建点走 `kb.kp.create`、
#: 改点走 `kb.kp.update`）⇒ 值为元组，门控判据 = **任一门动作类启用即可用**（见 `op_available()`）。
OP_TOOL_IDS: dict[str, tuple[str, ...]] = {
    "upsert_kp": ("kb.kp.create", "kb.kp.update"),
    "attach_links": ("kb.link.attach",),
    "detach_links": ("kb.link.detach",),
    "set_kp_range": ("kb.kp.update",),
    "rename_kp": ("kb.kp.rename",),
    "delete_kp": ("kb.kp.delete",),
    "upsert_edge": ("kb.link.create",),
    "replace_lines": ("kb.file.edit",),
    "insert_lines": ("kb.file.edit",),
    "delete_lines": ("kb.file.edit",),
    "upsert_block": ("kb.file.edit",),
    "insert_image_ref": ("kb.file.edit",),
    "create_file": ("kb.file.create",),
    "rename_file": ("kb.file.rename",),
    "delete_file": ("kb.file.delete",),
    "move_file": ("kb.file.move",),
    "rebuild_manifest": ("kb.manifest.rebuild",),
}


@dataclass(frozen=True, slots=True)
class ActivePlugins:
    """某个库**此刻生效**的能力面（`active_plugins()` 的产物）。"""

    declarations: tuple[PluginDeclaration, ...] = ()
    """**已启用**的声明（按装载顺序）。"""
    tool_ids: frozenset[str] = frozenset()
    """已启用的能力动作类（`kb.*`）—— 这张集合就是本库的写能力面。"""
    warnings: tuple[Mapping[str, Any], ...] = ()
    errors: tuple[Mapping[str, Any], ...] = ()
    registry_present: bool = False
    """库级注册表（`<库>/.memoria/agent/capabilities.json`）是否存在 —— 决定上面口径 1 走哪条分支。"""
    declarations_seen: int = 0
    """装载到的声明条数（含全部来源）—— 用它区分"契约没参与"与"参与了但一条都没启用"。"""
    configs: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    """库级参数（2026-09-24）：`{插件 id: 归一后的 config}`（schema 见文件尾「库级参数 schema」块）。

    只有"注册表在且该插件被启用"时才有条目；注册表缺失（fail-open 分支）⇒ 空表 —— 此时
    **逐库参数不存在**，消费方（如出网域名名单）应回落到机器级默认。
    """

    @property
    def enforced(self) -> bool:
        """能力闸是否**生效**（口径 2/3：有声明 ⇒ 生效；装载出错 ⇒ 也生效且更该闸）。"""
        return self.declarations_seen > 0 or bool(self.errors)

    def op_available(self, verb: str) -> bool:
        """这个 op 动作类在本库**可用吗**（未登记动作类 / 闸未生效 ⇒ 放行；未知 op 由 `plan.py` 自己拒）。"""
        ids = OP_TOOL_IDS.get(str(verb))
        if not ids or not self.enforced:
            return True
        return any(tool_id in self.tool_ids for tool_id in ids)


def builtin_dir() -> str:
    """内置声明目录（随版本分发、只读）：`resources/agent-capabilities/`；不存在 ⇒ 空串。"""
    try:
        from memoria.app.runtime import resources_dir

        path = str(resources_dir() / "agent-capabilities")
    except Exception:  # 运行期目录解析失败不应成为致命错误（口径 2 会兜住"没有声明"）
        return ""
    return path if os.path.isdir(path) else ""


def user_dir() -> str:
    """用户导入目录：`<配置目录>/plugins`（与 `config/agent.json` 同一层）；不存在 ⇒ 空串。"""
    try:
        from memoria.services.agent.llm.config import config_file_path

        path = str(config_file_path().parent / USER_PLUGINS_DIRNAME)
    except Exception:
        return ""
    return path if os.path.isdir(path) else ""


def active_plugins(kb_path: str, *, builtin: str | None = None, user: str | None = None) -> ActivePlugins:
    """算本库的能力面：**发现 → 与库级 `enabled[]` 求交 → 得 `tool_ids`**（口径见本节头注三条）。"""
    result = load_declarations(
        str(kb_path),
        builtin_dir=builtin_dir() if builtin is None else builtin,
        user_dir=user_dir() if user is None else user,
    )
    registry_present = os.path.isfile(kb_registry_path(str(kb_path)))
    seen = len(result.declarations)
    if result.errors:  # 口径 3：装载出错 ⇒ 闸到底（`tool_ids` 为空 ⇒ 写 op 全拒）
        return ActivePlugins(
            declarations=(),
            tool_ids=frozenset(),
            warnings=result.warnings,
            errors=result.errors,
            registry_present=registry_present,
            declarations_seen=seen,
        )
    if registry_present:  # 口径 1 后半：注册表在 ⇒ 以它为准（条目存在即启用；没列到 = 停用）
        enablement = kb_enablement(str(kb_path))
        enabled = tuple(d for d in result.declarations if bool((enablement.get(d.id) or {}).get("on", False)))
        configs = {d.id: dict((enablement.get(d.id) or {}).get("config") or {}) for d in enabled}
    else:  # 口径 1 前半：注册表缺失 ⇒ 内置默认全启用（存量库不被这次接线掐断写能力）
        enabled = result.declarations
        configs = {}
    return ActivePlugins(
        declarations=enabled,
        tool_ids=frozenset(tool.tool_id for decl in enabled for tool in decl.tools),
        warnings=result.warnings,
        errors=(),
        registry_present=registry_present,
        declarations_seen=seen,
        configs=configs,
    )


def capability_note(active: ActivePlugins) -> str:
    """给**模型**看的能力面说明（附在 `propose_write` 的描述末尾）；闸未生效 ⇒ 空串（行为同接线前）。"""
    if not active.enforced:
        return ""
    if not active.tool_ids:
        loaded = "、".join(f"{d.id}（{d.name}）" for d in active.declarations) or "无"
        return (
            "\n\n**本库的写能力当前未启用**：已装载的声明里没有任何启用条目（" + loaded + "）"
            "⇒ 本会话**所有写入 op 都会被拒**，错误码 `capability_disabled`。"
            "需要写时，请让用户在库设置里启用相应能力插件（库级 `enabled[]`），不要绕路。"
        )
    return (
        "\n\n**本库已启用的能力动作**："
        + "、".join(f"`{tool_id}`" for tool_id in sorted(active.tool_ids))
        + "。未列出的动作类会被拒（错误码 `capability_disabled`）—— 遇到它请如实告诉用户"
        "「这个能力在本库没启用」，不要改用别的 op 硬凑。"
    )


# ── 出网原语目录 + 库级参数 schema（2026-09-24；N 线插件化第二片，对应 [agent-capabilities.md §2.5/§2.6]
#    的 N1 行「一次性把 `net.*` 原语加进目录」）────────────────────────────────────────────────
# 这一块落两件**契约外但必要**的接线（都已登记进设计文档与变更台账）：
# ① **出网原语目录 `NET_CATALOG`**：写族 `TOOL_CATALOG` 的值是**落盘原语名**，而 `net.*` 没有落盘
#    原语（它不写盘）—— 实现入口是 `services/agent/web.py::WebClient.search/.fetch`。故单列一张表，
#    由 `parse_declaration()` 与 `ToolDeclaration.primitive` 取**并集**（写族 + 出网族）；
# ② **"工具级能力闸"的参数/schema 之一半**：N 的两把工具**不走 plan**（见 §2.3 的写管线），所以
#    `plan.validate_plan()` 那道闸够不到它们 ⇒ 闸改落在 `tools/kb.py::_outbound_guard()`（按
#    `active_plugins(kb).tool_ids` 判），命名桥就是下面的 `NET_TOOL_IDS`；
# ③ **库级参数 schema 的第一例**：库级注册表 `{id, on, config}` 的 `config` 位此前"保留但不校验"
#    （§2.1 v1 无参数 schema）⇒ 这里给 `web-fetch` 定义第一个 `{allow?: str[], deny?: str[]}`，
#    归一化复用 `web.parse_domains()`（**同一份判据**，绝不另立一套）。读侧归一（坏值丢弃、不静默
#    生效），写侧拒写（`set_enabled()` 见 issues 即返回 `bad_plugin_config`）。
# 整段追加在文件末尾 ⇒ 上方所有 `<文件>:<行号>` 锚点零漂移。

#: 出网族 `tool_id` → 实现入口（**无落盘**；与 `TOOL_CATALOG` 的语义差别就在这句注释里）。
NET_CATALOG: dict[str, str] = {
    "net.search": "web.WebClient.search",
    "net.fetch": "web.WebClient.fetch",
}

#: 库级参数 schema（**第一例**）：`{插件 id: (参数名, …)}`。没列到的插件 = 不接受任何参数
#: （写侧给 `config` 会被拒 —— 免得出现"配了但没人消费"的死参数位）。
PARAM_SCHEMAS: dict[str, tuple[str, ...]] = {"web-fetch": ("allow", "deny")}

#: 本地工具名 → 出网 `tool_id`（工具级闸的命名桥；与 `OP_TOOL_IDS` 同族，只是那边的值域是写 op）。
NET_TOOL_IDS: dict[str, str] = {"web_search": "net.search", "fetch_url": "net.fetch"}


def normalize_plugin_config(plugin_id: str, config: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """库级 `config` 归一 + 校验 ⇒ `(归一后的 dict, issues)`；`issues` 非空 ⇒ 调用方**应拒写**。

    规则（schema 见 `PARAM_SCHEMAS`）：

    · **不在 schema 里的插件** ⇒ **原样保留**、不校验（"只增不改"：未来插件先能把参数存进来，
      等它自己的 schema 落地再消费）；
    · **在 schema 里的插件**：值按 `web.parse_domains()` 归一（字符串或字符串数组都收；非法写法
      丢弃并**如实报条数**）；多余/未知的键 ⇒ `unknown_param`（拒写）。
    """
    if config in (None, ""):
        return {}, []
    if not isinstance(config, Mapping):
        return {}, [_cfg_issue(plugin_id, "bad_config", "`config` 必须是对象")]
    data = {str(key): value for key, value in config.items()}
    if not data:
        return {}, []
    allowed = PARAM_SCHEMAS.get(plugin_id)
    if allowed is None:
        return dict(data), []  # 没 schema 的插件：值位保留、原样透传（不消费、不校验）
    issues: list[dict[str, Any]] = [
        _cfg_issue(plugin_id, "unknown_param", f"未知参数 `{key}`（可用：{', '.join(allowed)}）")
        for key in sorted(set(data) - set(allowed))
    ]
    out: dict[str, Any] = {}
    from memoria.services.agent.web import parse_domains  # 延迟导入：web 层不反向依赖本模块

    for key in allowed:
        if key not in data:
            continue
        raw = data[key]
        if isinstance(raw, (list, tuple)):
            items = [str(item) for item in raw]
        elif isinstance(raw, str):
            items = [raw]
        else:
            issues.append(_cfg_issue(plugin_id, "bad_config", f"`config.{key}` 必须是字符串数组"))
            continue
        parsed = parse_domains(" ".join(items))
        dropped = len([item for item in items if item.strip()]) - len(parsed)
        if dropped > 0:
            issues.append(
                _cfg_issue(plugin_id, "bad_config", f"`config.{key}` 有 {dropped} 条无法识别的写法（域名写错了）")
            )
        out[key] = list(parsed)
    return out, issues


def _cfg_issue(plugin_id: str, kind: str, message: str) -> dict[str, Any]:
    return {"kind": kind, "id": plugin_id, "message": message, "path": ""}
