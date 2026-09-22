# 语义移植自 deepseek-harness packages/interaction/permission-presets（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""审批档位（permission preset）：把「审批」这一个旋钮打成一档，档位可随会话回放。

上游 `dsh-permission-presets` 把**两个**旋钮（`sandbox/mode` + `approval/policy`）打包成用户
可见的命名档，档位以会话事件落盘（`permission/preset` + 两个整值旋钮事件），生效值 =
「最后一个覆盖事件 ?? 组合默认」，无匹配档时派生出**只读**的 `custom`（`index.ts:348-365`）。

本地只有**一个**旋钮（Memoria 没有 shell、不做进程隔离、不进沙箱 ⇒ `sandbox/mode` 不适用）：

| 上游 | 本地 |
|---|---|
| 旋钮 `sandbox/mode`（`read-only`/`workspace-write`/`danger-full-access`） | **不移植**：无 shell、无进程隔离；写范围由插件 `permissions.write` + realpath 前缀校验保证（`docs/design/agent-plugin-design.md` §2.3.1） |
| 旋钮 `approval/policy`（`ask`/`never`） | 取值扩为 `ask`/`auto`/`allow-all`（后两者为**本地新增值**；原名 `never` **已改名**，见下「改名与只读兼容」） |
| 会话事件 `permission/preset`（log-only 的**用户意图**） | 同名同义 |
| 生效值 = 最后一个覆盖事件 ?? 组合默认 | 同口径（`fold()` + `derive()`） |
| `custom` = 派生只读态，**不可作切换目标**、不进事件载荷 | 同名同义（`CUSTOM_PRESET`；`set_preset()` 对它直接报错） |
| `auto` 档由 `experimental/auto-review` 贡献（固定 bundle、仅当前会话） | 本地落成**常规档** `auto-approval`（人 2026-09-22 拍板「auto 保留闸门」） |
| `/permission <preset>` 命令 + 输入区 `PermissionSelect` + 设置页默认档 | 输入区 `#agent-permission` + 设置面板同族控件 + RPC `agent_permission_*`（本地无命令面） |
| 档位表由部署配置覆盖（`Config.presets`） | 档位表是**代码常量** `PRESETS`（本地未做"可配置档位表"） |
| `defaultPreset` 落 `settings` 命名空间 | 落 `config/agent.json: permission`（**按 agent 配**；人 2026-09-22 口径） |
| `session/end-seed`（子代理播种边界） | 不移植（本地无子代理） |

**三档语义**（人 2026-09-22 拍板：默认「自动审批」、`auto` 保留闸门）：

| 档（机器键，稳定英文） | 显示名 | `approval/policy` | 策略类 |
|---|---|---|---|
| `manual-approval` | 手动审批 | `ask` | `AskPolicy`（每个写类调用都挂起等应答） |
| `auto-approval`（**默认**） | 自动审批 | `auto` | `GuardedPolicy`（常规写自动放行，命中风险才问） |
| `all-access` | 完全访问 | `allow-all` | `DefaultApprovalPolicy`（不问、一律放行） |

**改名与只读兼容（2026-09-22，人：「改 never 命名避歧义」）**：本地这一档的语义是「不询问 ⇒ 一律放行」，
而上游 `never` 的准确含义恰好相反 —— 「不询问 ⇒ **需审批者一律拒绝**」（它成立是因为上游有 sandbox 档兜底：
`danger-full-access` 时无物需审批）。**同名反义**会让读上游文档的人（以及后来的维护者）误判 ⇒ 本地把旋钮值
改名为 **`allow-all`**。**历史事件仍按原样读**（会话日志是 append-only 的事实源）：`fold()` 用
`LEGACY_APPROVAL_POLICIES` 把旧值 `never` 读成 `allow-all`，绝不重解释旧日志、也不改写它们。
**兜底不靠闸门、靠写前备份 + 可整批撤销**（`services/agent/backup.py`）。

**机器键为什么不随界面语言变**：档位名要进会话事件（可回放、可审计），翻译一变历史就断；
故键是稳定英文，显示名走 UI 侧 i18n（后端中文名只作 zh 与未知键的回退事实源，口径同
`storage/sidecar_validate.py` 头注）。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from memoria.services.agent.approvals import (
    ApprovalPolicy,
    AskPolicy,
    DefaultApprovalPolicy,
    GuardedPolicy,
)

logger = logging.getLogger(__name__)

__all__ = [
    "APPROVAL_POLICIES",
    "CUSTOM_PRESET",
    "DEFAULT_PRESET",
    "EVENT_APPROVAL_POLICY",
    "EVENT_PRESET",
    "LEGACY_APPROVAL_POLICIES",
    "MAIN_AGENT",
    "PRESETS",
    "PRESET_NAMES",
    "KnobState",
    "PresetSpec",
    "catalog",
    "current",
    "default_preset",
    "derive",
    "fold",
    "pin_and_current",
    "policy_for",
    "policy_value",
    "set_preset",
    "state_view",
]

#: 无匹配档时的**派生只读**取值：可展示为「当前值」，但绝不作切换目标、绝不进事件载荷。
CUSTOM_PRESET = "custom"

#: 主 agent 的标识：会话档位**按 agent 归属**（多 agent 是后续设计，当前只有主 agent）。
MAIN_AGENT = "main"

#: 新会话默认档（人 2026-09-22 拍板）；可被 `config/agent.json: permission.<agent>` 覆盖。
DEFAULT_PRESET = "auto-approval"

#: 旋钮 `approval/policy` 的封闭词汇（`auto` / `allow-all` 为本地新增值，见模块 docstring）。
APPROVAL_POLICIES = ("ask", "auto", "allow-all")

#: **旧词汇的只读兼容**：`never` 曾是本地的 `allow-all`（2026-09-22 前），语义与上游同名反义 ⇒ 改名。
#: 会话日志是 append-only 的事实源，历史事件里的 `never` 必须继续读成 `allow-all`（绝不重解释）。
LEGACY_APPROVAL_POLICIES = {"never": "allow-all"}

#: 会话事件类型（信封字段名与上游逐字对齐；`payload` 只增不改）。
EVENT_PRESET = "permission/preset"
EVENT_APPROVAL_POLICY = "approval/policy"


@dataclass(frozen=True, slots=True)
class PresetSpec:
    """一档的旋钮 bundle 与展示信息（上游 `PresetSpec` 的本地版，去掉 `sandbox`）。"""

    approval: str
    """该档写入的 `approval/policy` 值。"""

    name: str
    """显示名（中文事实源；界面可按 `value` 覆盖为本地语言）。"""

    description: str = ""

    def __post_init__(self) -> None:
        if self.approval not in APPROVAL_POLICIES:
            raise ValueError(f"档位 bundle 的 approval 取值不在词汇内：{self.approval!r}")


#: 档位表：机器键 → bundle（**声明顺序即选择器顺序**，也是 `derive()` 的首匹配顺序）。
PRESETS: dict[str, PresetSpec] = {
    "manual-approval": PresetSpec("ask", "手动审批", "每次写入都等你确认后才落盘。"),
    "auto-approval": PresetSpec("auto", "自动审批", "常规写入自动放行；含删除类改动时仍会问你一次。"),
    "all-access": PresetSpec("allow-all", "完全访问", "任何工具调用都不再询问（仍写前备份、可整批撤销）。"),
}

#: 可切换的档位名（`custom` 不在内：它是派生态，不是档）。
PRESET_NAMES: tuple[str, ...] = tuple(PRESETS)


@dataclass(frozen=True, slots=True)
class KnobState:
    """档位折叠态：每个旋钮的**最后一个**覆盖事件取值；无覆盖则为 `None`（用默认值）。"""

    preset: str | None = None
    approval: str | None = None


def policy_value(name: str) -> str:
    """档位名 → 它写入的 `approval/policy` 值；未知档报错（fail-closed，绝不静默回落）。"""
    spec = PRESETS.get(str(name or ""))
    if spec is None:
        raise ValueError(f"未知审批档：{name!r}（可选：{', '.join(PRESET_NAMES)}）")
    return spec.approval


def fold(events: Iterable[Mapping[str, Any]]) -> KnobState:
    """按序折叠事件流 → 旋钮态（上游 `applyPermissionEvent` 的本地版）。

    只认**整值覆盖**语义：`permission/preset` 与 `approval/policy` 各取最后一条；
    取值不在词汇内的旋钮事件一律忽略（不做猜测，也不覆盖已知取值）。
    """
    preset: str | None = None
    approval: str | None = None
    for row in events:
        if not isinstance(row, Mapping):
            continue
        kind = str(row.get("type") or "")
        data = row.get("data") if isinstance(row.get("data"), Mapping) else {}
        if kind == EVENT_PRESET:
            value = str(data.get("preset") or "").strip()
            if value and value != CUSTOM_PRESET:  # 派生态不得进载荷（与上游同口径）
                preset = value
        elif kind == EVENT_APPROVAL_POLICY:
            value = str(data.get("policy") or "").strip()
            value = LEGACY_APPROVAL_POLICIES.get(value, value)  # 旧 `never` 读成 `allow-all`（只读兼容）
            if value in APPROVAL_POLICIES:
                approval = value
    return KnobState(preset, approval)


def derive(state: KnobState, default: str = DEFAULT_PRESET) -> str:
    """折叠态 → 生效档位名；`default` 是「无覆盖时的组合默认」。无匹配 ⇒ `custom`。

    上游在「多档共用同一 bundle」时让**上次选择**胜出（`index.ts:352-365`）；本地一个旋钮
    对一个档（1:1）故平局不可能出现，这里仍保留同一判定顺序，以便将来加第二个旋钮。
    """
    approval = state.approval or policy_value(default)
    if state.preset is not None:
        spec = PRESETS.get(state.preset)
        if spec is not None and spec.approval == approval:
            return state.preset
    for name, spec in PRESETS.items():
        if spec.approval == approval:
            return name
    return CUSTOM_PRESET


def default_preset(agent: str = MAIN_AGENT) -> str:
    """该 agent 的默认档：`config/agent.json: permission.<agent>` ?? `DEFAULT_PRESET`。

    配置文件是**用户可手改的边界**，故未知取值/读失败/形状不对一律回落到 `DEFAULT_PRESET`
    （不抛 —— 一个手改坏的字段不该让对话起不来）。
    """
    try:
        from memoria.services.agent.llm.config import permission_presets_map

        raw = permission_presets_map()
    except Exception as exc:  # noqa: BLE001 — 读配置失败不得影响问答
        logger.warning("[agent-permission] 读审批档配置失败，用默认档：%r", exc)
        return DEFAULT_PRESET
    name = str(raw.get(str(agent or "").strip()) or "").strip()
    return name if name in PRESETS else DEFAULT_PRESET


def current(events: Iterable[Mapping[str, Any]], agent: str = MAIN_AGENT) -> str:
    """会话**生效**档位名（按事件流折叠，不写盘）。"""
    return derive(fold(events), default_preset(agent))


def pin_and_current(session: Any, agent: str = MAIN_AGENT) -> str:
    """钉住本次会话的档位事实并返回生效档（`ask()` 每轮调一次）。

    对齐上游 `pinInitialPermission()`：**全新**会话落默认档的整值事件；已有覆盖的会话只补
    **缺失的**事实（`index.ts:432-460`）。本地无 `sandbox` 旋钮、无子代理播种 ⇒ 收敛为
    「缺 `permission/preset` 就补一条当前生效档」+「缺 `approval/policy` 就补一条其 bundle 值」。
    """
    state = fold(session.events())
    effective = derive(state, default_preset(agent))
    if effective not in PRESETS:  # 只可能发生在档位表被改小、而日志留着旧档时
        logger.warning("[agent-permission] 生效档不在表内（%s），本次不钉盘", effective)
        return effective
    if state.preset is None:
        session.append(EVENT_PRESET, {"preset": effective})
    if state.approval is None:
        session.append(EVENT_APPROVAL_POLICY, {"policy": policy_value(effective)})
    return effective


def set_preset(session: Any, name: str, agent: str = MAIN_AGENT) -> str:
    """切换档位：先落**用户意图**事件，再落**变化的旋钮**（上游 `apply()` 同序）。

    `name` 必须可切换（`custom` 与未知名一律报错）；已经是生效档时**不追加任何事件**
    （幂等，对齐上游 `if (current !== name) session.append(...)`）。
    """
    policy_value(name)  # 未知档在此报错
    state = fold(session.events())
    if derive(state, default_preset(agent)) != name:
        session.append(EVENT_PRESET, {"preset": name})
    if policy_value(name) != (state.approval or policy_value(default_preset(agent))):
        session.append(EVENT_APPROVAL_POLICY, {"policy": policy_value(name)})
    return name


def policy_for(name: str, kb_path: str = "") -> ApprovalPolicy:
    """档位名 → 审批策略实例（`ask`/`auto` 档的应答者由**审批桥**提供）。

    应答者只在「该库已挂载审批信道」时才有（`approval_bridge.answerer_for`）；无应答者时
    `AskPolicy` / `GuardedPolicy` 的**需审批**分支一律 `unavailable` ⇒ 拒绝（fail-closed）。
    """
    value = policy_value(name)
    if value == "allow-all":
        return DefaultApprovalPolicy()
    from memoria.services.agent import approval_bridge

    answerer = approval_bridge.answerer_for(kb_path)
    return AskPolicy(answerer) if value == "ask" else GuardedPolicy(answerer)


def catalog() -> list[dict[str, Any]]:
    """可档位清单（含派生只读的 `custom`）：喂输入区选择器与设置面板。"""
    options = [
        {"value": name, "name": spec.name, "description": spec.description}
        for name, spec in PRESETS.items()
    ]
    options.append({"value": CUSTOM_PRESET, "name": "自定义", "description": "当前审批旋钮不匹配任何档位。"})
    return options


def state_view(events: Iterable[Mapping[str, Any]] | None = None, agent: str = MAIN_AGENT) -> dict[str, Any]:
    """档位面视图：`{current, agent, default, options}`（无事件流时用该 agent 的默认档）。"""
    fallback = default_preset(agent)
    return {
        "current": derive(fold(events or ()), fallback),
        "agent": agent,
        "default": fallback,
        "options": catalog(),
    }
