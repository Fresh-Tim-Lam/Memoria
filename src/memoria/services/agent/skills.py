# 语义移植自 deepseek-harness packages/skill/{skill, skill-filesystem, tool-skill}
# （MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""技能（skill）：**声明式目录包 + 渐进披露**的本地落法。

上游三包分工：`skill` = 注册表（provider 合并 / rank 遮蔽 / 目录与正文两段式）、
`skill-filesystem` = 本地目录 provider（根表 + frontmatter 解析）、`tool-skill` = 模型面
（`skill` 工具 + 会话目录 + `/name` 手势）。**本模块落前两者的规则 + `tool-skill` 的 `/name` 手势**，
外加工具与提示词需要的渲染函数；注册表的"层"、watcher、"持久目录消息"三块**有意不落**（见偏差）。

## 照搬的规则（逐条注明上游出处）

| 规则 | 上游 |
|---|---|
| 名字语法 `^[a-z0-9]+(?:-[a-z0-9]+)*$` | `skill/src/index.ts:21` |
| 根表 + rank（`project-dsh` 100 / `project-agents` 200 / `runtime` 250 / `custom` 300 / `user-dsh` 400 / `user-agents` 500 / `bundled` 600） | `skill-filesystem/src/index.ts:28`、`:36-40` |
| 发现：平铺 `<name>.md` 或 `<name>/SKILL.md`；**只认根的下一层**（嵌套 `**/SKILL.md` 不发现） | `skill-filesystem/src/index.ts:723-751` |
| frontmatter：必填 `name` + `description`，可选 `whenToUse` / `disable-model-invocation` / `user-invocable` | `:797-840`、`:1000-1010` |
| 宽松布尔（`true/yes/on/1`、`false/no/off/0`）；**旧键一律拒**（须写 kebab 形式，不认 `modelInvocable`） | `:1012-1037` |
| `disable-model-invocation: true` ⇒ 不进模型目录；`user-invocable` 缺省 true | `:1004-1009` |
| 同名遮蔽：`rank` → 注册序 → 目录内序，高优先者胜、后者仅 warn | `skill/src/index.ts:807-811`、`:567-581` |
| 渲染 `<skill_content>` / `<skill_resources>` / `<skill_instructions>`；name 走属性转义、提示语走文本转义、**正文逐字不转义**（技能是**可信本地内容**） | `skill/src/index.ts:170-228` |
| 目录行 `- `name`: description`；description 空白折叠 + 500 截断加 `...` | `tool-skill/src/index.ts:319-321`、`:391-394` |
| 目录段文案（"只有摘要，**加载前不要照做**"） | `tool-skill/src/index.ts:254-277` |
| `skill` 工具：按**精确名**加载；非法名 / 未知名 / 不可模型调用各自报错 | `tool-skill/src/index.ts:127-160` |
| `/name` 用户手势：空白包围的 `/name` **任意位置**、first-seen 去重、未知名**保持普通散文**、只认 `user-invocable`、注入**追加在所有其它注入之后** | `tool-skill/src/index.ts:163-204`、`:409`、`:418-430` |

## 本地偏差（有意，逐条登记）

1. **只吃一个根**：`<库>/.memoria/agent/skills/**`（source `kb`，rank 100）。上游按 cwd **向上找 `.git`** 定"工程根"，
   再叠 `~/.dsh`、`~/.agents` —— Memoria 没有"工程根"概念（app 从任意 cwd 启动，**库才是边界**），
   而库外根会破坏"允许根"纪律（`tools/kb.py::_read_roots()` 今天只有库根）⇒ 全局根**留待拍板**。
   根表仍按上游形状写成表，将来加根是一行的事。
2. **不做 watcher**：上游 `skill-filesystem` 用 ~350 行 Chokidar（root/ancestor 双模、rewatch、stability/poll、
   maxProjects 淘汰）做失效通知。本地无 fs 事件服务，而技能目录小、frontmatter 解析便宜 ⇒ **每轮重建目录**
   （`build_system_prompt()` 每轮都调）。
3. **不做注册表的"层"**：上游 `SkillRegistry` 建在 Cordis `Service` + `ScopedLayers` 上（global 层 + 每 agent
   scope 链，近者胜）。本地只有一个 agent（`main`）、无插件运行时 ⇒ 塌成**单层扁平合并**，
   scope 与"按 (cwd, scope 链, revision) 缓存目录"那套整体删掉。
4. **不做"持久目录消息"**：上游把目录作为**一条可原地替换的 user 消息**（`source.kind='skill-catalog'`，
   按条目 digest 决定是否重发）写进会话。本地没有 pre-step 挂钩与消息 source 概念 ⇒ 目录落成
   **system 提示的一段**（与 `FILE_REFERENCE_SECTION` 同构），**不落盘**（与时间上下文/模型切换告知同口径）。
5. **`/name` 用户手势：2026-09-22 补齐**（`commands.py` 落地后 ⇒ 上游要求的前置已就位）。`invoked_names()` /
   `render_invocations()` 落在本**文件末**，注入点见 `prompt.render_skill_invocation()`（由 `ask()` 拼在本轮
   请求**最末**）。唯一保留的偏差：注入**只进本轮请求、不落盘**（同跨会话快照口径）—— 上游把它持久化成
   `source.kind='skill-invocation'` 的 user 消息，故跨轮仍在；本地要跨轮须先有"消息 source"概念（见偏差 4）。
6. **本地新增的硬边界**：单文件 > `MAX_SKILL_BYTES` 一律跳过（技能正文直接进模型上下文，不许无限大）；
   技能文件必须是 UTF-8。**未移植** `metadata` 字段（本地无消费方，解析出来也无处可用）。

**信任口径**：技能正文按上游当**可信本地内容**（逐字进 `<skill_instructions>`，不转义）。它的能力边界是
"**给模型的指令**"——**绕不过写路径**：任何库内改动仍要过 `propose_write` → 计划校验 → 审批档 → 写前备份 →
可整批撤销 ⇒ 最坏后果是"模型做了它本来不会做的**库内**改动"，不是任意代码执行。
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import yaml

logger = logging.getLogger(__name__)

__all__ = [
    "CATALOG_DESCRIPTION_MAX_LENGTH",
    "MAX_SKILL_BYTES",
    "SKILLS_DIR",
    "SKILL_FILE_NAME",
    "SkillDefinition",
    "SkillRoot",
    "SkillSummary",
    "discover_skills",
    "invoked_names",
    "is_skill_name",
    "load_skill",
    "render_invocations",
    "render_skill_catalog",
    "render_skill_content",
    "SKILL_GESTURE",
    "skill_roots",
]

#: 技能名语法（上游 `skill/src/index.ts:21` 逐字）。
_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

#: 技能目录（相对库根）—— 上游的 `project-dsh` 根（`.dsh/skills`）在本地换成库内固定目录。
SKILLS_DIR = (".memoria", "agent", "skills")
#: 目录包形态的技能正文文件名（上游只认这一个名字）。
SKILL_FILE_NAME = "SKILL.md"
#: 单个技能文件上限（本地新增，见模块头偏差 6）。
MAX_SKILL_BYTES = 64 * 1024
#: 目录里 description 的渲染上限（上游 `tool-skill` 的 `catalogDescriptionMaxLength` 默认值）。
CATALOG_DESCRIPTION_MAX_LENGTH = 500

#: 拒绝的旧 frontmatter 键 → 应改用的规范键（上游 `:1012-1016`；写成 kebab 形式后再解析）。
_LEGACY_INVOCATION_KEYS = {
    "disableModelInvocation": "disable-model-invocation",
    "modelInvocable": "disable-model-invocation",
    "userInvocable": "user-invocable",
}


@dataclass(frozen=True, slots=True)
class SkillRoot:
    """一个扫描根（上游 `SkillRoot` 的本地最小版：路径 + 来源标签 + rank）。"""

    path: str
    source: str
    rank: int


@dataclass(frozen=True, slots=True)
class SkillSummary:
    """技能的**发现态**：目录里能看到的元数据（不含正文）。"""

    name: str
    description: str
    when_to_use: str = ""
    model_invocable: bool = True
    user_invocable: bool = True
    source: str = ""
    rank: int = 0
    path: str = ""
    base_dir: str = ""


@dataclass(frozen=True, slots=True)
class SkillDefinition(SkillSummary):
    """技能的**加载态**：元数据 + 正文（每次 `load_skill()` 现读盘）。"""

    content: str = ""


def is_skill_name(name: str) -> bool:
    """是否合法技能名（kebab-case，小写字母/数字以 `-` 连接）。"""
    return bool(_SKILL_NAME_RE.match(str(name or "")))


def skill_roots(kb_path: str) -> tuple[SkillRoot, ...]:
    """扫描根表（**按 rank 升序**，rank 小者优先）。

    本地今天只有一个根（库内），表形状照上游保留 ⇒ 将来要加"全局技能根"只需在此追加一行
    （但库外根要先过"允许根"这道纪律，见模块头偏差 1）。
    """
    return (SkillRoot(path=os.path.join(os.path.abspath(kb_path), *SKILLS_DIR), source="kb", rank=100),)


def parse_frontmatter(raw: str) -> tuple[Mapping[str, object], str] | None:
    """拆出 YAML frontmatter 与正文（上游 `parseFrontmatter`，`:917-943`）。

    规则逐条一致：**首行必须是 `---`**；闭合 `---` 须独占一行；YAML 必须是**对象**。
    任一条不满足或 YAML 非法 ⇒ `None`（调用方跳过该文件并 warn），不抛。
    """
    first_line_end = raw.find("\n")
    if first_line_end < 0:
        return None
    if raw[:first_line_end].rstrip("\r") != "---":
        return None
    start = first_line_end + 1
    line_start = start
    while line_start <= len(raw):
        next_newline = raw.find("\n", line_start)
        line_end = len(raw) if next_newline < 0 else next_newline
        if raw[line_start:line_end].rstrip("\r") == "---":
            body_start = len(raw) if next_newline < 0 else next_newline + 1
            try:
                parsed = yaml.safe_load(raw[start:line_start])
            except yaml.YAMLError:
                return None
            if not isinstance(parsed, Mapping):
                return None
            return parsed, raw[body_start:]
        if next_newline < 0:
            return None
        line_start = next_newline + 1
    return None


def _frontmatter_boolean(data: Mapping[str, object], key: str) -> bool | None:
    """frontmatter 布尔的**宽松**读法（上游 `:1018-1037` 逐条）。

    真：`true` / `1` / `"1"` / `"true"` / `"yes"` / `"on"`；假：`false` / `0` / `"0"` / `"false"` / `"no"` / `"off"`；
    键不存在 ⇒ `None`；其余取值 ⇒ 抛 `ValueError`（上游抛 `TypeError` ⇒ 该文件被忽略）。
    """
    if key not in data:
        return None
    value = data[key]
    if isinstance(value, bool):
        return value
    if value == 1:
        return True
    if value == 0:
        return False
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "yes", "on", "1"):
            return True
        if text in ("false", "no", "off", "0"):
            return False
    raise ValueError(f"frontmatter 字段 `{key}` 必须是布尔值（现在取到 {value!r}）")


def _invocation_policy(data: Mapping[str, object]) -> tuple[bool, bool]:
    """`(model_invocable, user_invocable)`（上游 `:1000-1010`）。

    先**拒旧键**（`modelInvocable` 等 camelCase 形式已废弃，报错并指路 kebab 键），
    再按两个 kebab 键取值；缺省 `model_invocable=True`、`user_invocable=True`
    （即除显式 `disable-model-invocation: true` 外都可被模型加载）。
    """
    for legacy, canonical in _LEGACY_INVOCATION_KEYS.items():
        if legacy in data:
            raise ValueError(f"frontmatter 字段 `{legacy}` 已废弃，请改用 `{canonical}`")
    disable_model = _frontmatter_boolean(data, "disable-model-invocation")
    user_invocable = _frontmatter_boolean(data, "user-invocable")
    return disable_model is not True, user_invocable is not False


def _read_skill_text(path: str) -> str | None:
    """读一个技能文件（UTF-8、单文件上限）；读不到/非 UTF-8/超限 ⇒ `None`（warn 后跳过）。"""
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    if size > MAX_SKILL_BYTES:
        logger.warning("[agent-skill] 技能文件超过单文件上限（%d>%d），已跳过：%s", size, MAX_SKILL_BYTES, path)
        return None
    try:
        with open(path, "rb") as handle:
            raw = handle.read(MAX_SKILL_BYTES + 1)
    except OSError as exc:
        logger.warning("[agent-skill] 技能文件不可读，已跳过：%s（%r）", path, exc)
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        logger.warning("[agent-skill] 技能文件不是 UTF-8，已跳过：%s", path)
        return None


def _parse_skill(path: str, *, base_dir: str, source: str, rank: int) -> SkillDefinition | None:
    """读 + 解析一个技能文件；任何一条不合法都回 `None` 并 warn（上游 `parseSkillFile`，`:797-840`）。"""
    raw = _read_skill_text(path)
    if raw is None:
        return None
    parsed = parse_frontmatter(raw)
    if parsed is None:
        logger.warning("[agent-skill] 技能文件缺少或含非法 YAML frontmatter，已跳过：%s", path)
        return None
    data, body = parsed
    name = data.get("name")
    description = data.get("description")
    if not isinstance(name, str) or not name or not isinstance(description, str) or not description:
        logger.warning("[agent-skill] 技能文件 frontmatter 必须同时给 `name` 与 `description`，已跳过：%s", path)
        return None
    if not is_skill_name(name):
        logger.warning("[agent-skill] 技能名非法（须 kebab-case）：%r（%s）", name, path)
        return None
    try:
        model_invocable, user_invocable = _invocation_policy(data)
    except ValueError as exc:
        logger.warning("[agent-skill] 技能文件调用策略非法，已跳过：%s（%s）", path, exc)
        return None
    when_to_use = data.get("whenToUse")
    return SkillDefinition(
        name=name,
        description=description,
        when_to_use=when_to_use if isinstance(when_to_use, str) else "",
        model_invocable=model_invocable,
        user_invocable=user_invocable,
        source=source,
        rank=rank,
        path=path,
        base_dir=base_dir,
        content=body.strip(),
    )


def _locator_for(root: SkillRoot, entry_path: str, entry_name: str, is_dir: bool) -> tuple[str, str] | None:
    """目录项 → `(技能文件路径, 资源基目录)`；不构成技能（非 `.md`、既非文件也非目录）⇒ `None`。

    上游只认**根的下一层**两种形态（`:723-733`）：`<name>/SKILL.md`（目录包，资源基目录 = 该目录）
    与 `<name>.md`（平铺包，资源基目录 = 根本身）⇒ 再深一层的 `SKILL.md` **不发现**。
    """
    if is_dir:
        return os.path.join(entry_path, SKILL_FILE_NAME), entry_path
    if entry_name.endswith(".md"):
        return entry_path, root.path
    return None


def _as_summary(skill: SkillDefinition) -> SkillSummary:
    """`SkillDefinition` → `SkillSummary`（目录不该带正文；上游同口径）。"""
    return SkillSummary(
        name=skill.name,
        description=skill.description,
        when_to_use=skill.when_to_use,
        model_invocable=skill.model_invocable,
        user_invocable=skill.user_invocable,
        source=skill.source,
        rank=skill.rank,
        path=skill.path,
        base_dir=skill.base_dir,
    )


def discover_skills(kb_path: str) -> tuple[SkillSummary, ...]:
    """按根表扫描出**目录**（`SkillSummary`，不含正文），同名按 rank 遮蔽。**只读、不落盘**。

    合并规则照上游（`skill/src/index.ts:807-811`、`:567-581`）：候选按 `rank` → 根表内序 → 目录内序排序，
    同名只留第一个（其余记 warn）；返回按名字排序（上游 `compareSkillSummary`）。
    """
    candidates: list[SkillSummary] = []
    for root in sorted(skill_roots(kb_path), key=lambda item: item.rank):
        try:
            entries = sorted(os.listdir(root.path))
        except OSError:
            continue  # 根不存在/不可读：静默跳过（上游把它当"这个根没有技能"）
        for entry_name in entries:
            entry_path = os.path.join(root.path, entry_name)
            is_dir = os.path.isdir(entry_path)
            if not is_dir and not os.path.isfile(entry_path):
                continue
            locator = _locator_for(root, entry_path, entry_name, is_dir)
            if locator is None:
                continue
            parsed = _parse_skill(locator[0], base_dir=locator[1], source=root.source, rank=root.rank)
            if parsed is not None:
                candidates.append(_as_summary(parsed))
    ordered = sorted(enumerate(candidates), key=lambda item: (item[1].rank, item[0]))
    winners: dict[str, SkillSummary] = {}
    for _index, skill in ordered:
        if skill.name in winners:
            logger.warning("[agent-skill] 同名技能「%s」被更高优先者遮蔽：%s", skill.name, skill.path)
            continue
        winners[skill.name] = skill
    return tuple(winners[name] for name in sorted(winners))


def load_skill(kb_path: str, name: str) -> SkillDefinition | None:
    """按名加载技能**正文**（每次现读盘 ⇒ 正文改动立刻生效，上游 `get()` 同口径）。

    未知名、文件已消失、或解析不再合法 ⇒ `None`。**不经目录缓存**：先 `discover_skills()` 定位赢家，
    再重读该文件拿正文（= 上游"目录只给摘要、正文 load 时才读"的落法）。
    """
    wanted = str(name or "").strip()
    if not is_skill_name(wanted):
        return None
    winner = next((skill for skill in discover_skills(kb_path) if skill.name == wanted), None)
    if winner is None:
        return None
    return _parse_skill(winner.path, base_dir=winner.base_dir, source=winner.source, rank=winner.rank)


def escape_text(value: str) -> str:
    """模型可见正文里的转义（上游 `escapeText`，`:226-228`）：`&` / `<` / `>`。"""
    return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_attr(value: str) -> str:
    """属性值转义（上游 `escapeAttr`，`:216-218`）：`&` / `"` / `<`。"""
    return str(value or "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def normalize_description(value: str, max_length: int = CATALOG_DESCRIPTION_MAX_LENGTH) -> str:
    """目录里 description 的归一（上游 `catalogDescription`，`tool-skill:391-394`）：空白折叠 + 截断加 `...`。"""
    normalized = " ".join(str(value or "").split())
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 3]}..."


def render_skill_catalog(skills: Sequence[SkillSummary]) -> str:
    """把**可模型调用**的技能渲染成 system 提示里的目录段（上游目录消息的中文落法，`tool-skill:254-277`）。

    空目录 ⇒ `""`（不注入空段；上游在"零技能且从未发布"时同样不发目录）。
    门控由调用方（`prompt.build_system_prompt`）按"`skill` 工具是否在场"决定。
    """
    entries = [
        f"- `{skill.name}`：{escape_text(normalize_description(skill.description))}"
        for skill in skills
        if skill.model_invocable
    ]
    if not entries:
        return ""
    summary = [skill for skill in skills if skill.model_invocable]
    detail: list[str] = []
    for skill in summary:
        if skill.when_to_use.strip():
            detail.append(f"- `{skill.name}`：{escape_text(skill.when_to_use.strip())}")
    return "\n".join(
        [
            "## 可用技能",
            "",
            "技能是**可复用的任务说明书**。本轮可用技能如下（**只有摘要**）：",
            "",
            *entries,
            *(["", "何时用：", *detail] if detail else []),
            "",
            "1. 用户点名某个技能、或当前任务明显匹配某条描述时，**先用 `skill` 工具按精确技能名加载它**，"
            "再照它的完整说明行事；",
            "2. **加载之前不要照摘要臆测技能内容**（摘要只够你判断「要不要加载」，它不是说明书本身）；",
            "3. 一次加载一个：确有多个匹配就分别加载，全部加载完再动手。",
        ]
    )


def render_skill_content(skill: SkillDefinition) -> str:
    """把已加载技能渲染成模型可见的 `<skill_content>` 块（上游 `renderSkillContent`，`skill/src/index.ts:170-183`）。

    形状逐字对齐：`<skill_resources>` 给资源基目录提示、`<skill_instructions>` 里是**正文原文**
    （可信本地内容，**不转义** —— 转义会破坏技能里的代码/公式）。本地每个技能都有资源基目录
    （目录包 = 该目录本身、平铺包 = 根目录），故不做上游那种"没有基目录"的降级分支。
    """
    return "\n".join(
        [
            f'<skill_content name="{_escape_attr(skill.name)}">',
            "<skill_resources>",
            f"本技能的资源基目录：{escape_text(skill.base_dir)}",
            "技能里提到的相对路径都相对该目录解析；**按需**再读取其中的资源，不要一次全读。",
            "</skill_resources>",
            "",
            "<skill_instructions>",
            skill.content,
            "</skill_instructions>",
            "</skill_content>",
        ]
    )


# ── `/name` 用户手势（2026-09-22 追加；对齐上游 `tool-skill/src/index.ts:163-204`）──────────────
# 整段追加在文件末尾 ⇒ 上方所有 `<文件>:<行号>` 锚点零漂移（`__all__` 的同名条目见上）。
#
# **上游口径**（逐条注明出处）：
# ① 手势 = **空白包围**的 `/name` 记号，可出现在文本**任意位置**（`SKILL_GESTURE`，`:409` 逐字）；
#    第二个 `/` 或任何非边界字符打断匹配 ⇒ `/usr/bin`、`5/8` 不会被误判；
# ② **只扫直接用户文本** —— 其它来源伪造不了手势（`:171-174`、`:418-430`）；
# ③ 候选名按 **first-seen 序**去重（上游 `names.includes()`，`:426`）；
# ④ 逐个查注册表：**未知名 / 用户禁用的技能一律保持普通散文**（`:191-195`）—— 手势不是本边界认可的声明；
# ⑤ 命中者把 `renderSkillContent()` 的结果作为**注入的指令上下文**，**追加在所有其它注入之后**
#    （背景在前、要照做的材料在末，最贴近模型的答复；`:165-170`）；
# ⑥ 这是 `disable-model-invocation` 技能的**唯一入口**（目录与 `skill` 工具都看不见它们，`:175-176`）；
# ⑦ 与**命令注册表是两个互不相干的闭命名空间**（`:172-174`）：命令行在宿主侧先解析（`commands.py`），
#    令牌命中不了任何技能就仍是普通散文 —— 该顺序在 `ask()` 里天然成立（命令先分流，未命中才走到本文）。
#
# **本地偏差**：注入**只进本轮请求、不落盘**（同跨会话快照口径）；上游把它持久化成
# `source.kind='skill-invocation'` 的 user 消息，故跨轮仍在（见模块头偏差 5）。

#: `/name` 手势正则（上游 `tool-skill/src/index.ts:409` 逐字；`re` 无 `g` 旗标 ⇒ 用 `finditer` 扫全部）。
SKILL_GESTURE = re.compile(r"(^|\s)/([a-z0-9]+(?:-[a-z0-9]+)*)(?=\s|$)")


def invoked_names(text: str) -> list[str]:
    """文本里的 `/name` 手势名，按 **first-seen 序**去重（上游 `invokedSkillNames`，`:418-430`）。

    **只做语法匹配、不查注册表**（上游同口径：回的是候选名）；未知名由 `render_invocations()` 过滤。
    扫的是**直接用户输入**，故宿主自己拼出来的文本（会话标题、`@提及` 改写出的 `@label`）伪造不了手势。
    """
    found: list[str] = []
    for match in SKILL_GESTURE.finditer(str(text or "")):
        name = match.group(2)
        if name and name not in found:
            found.append(name)
    return found


def render_invocations(kb_path: str, text: str) -> str:
    """把文本里的 `/name` 手势渲染成待注入的技能块（多块以空行相接；无命中 ⇒ `""`）。

    `load_skill()` 回 `None`（未知名 / 文件已消失）或 `user_invocable is False` ⇒ **跳过并保持普通散文**
    （上游 `:195`）。正文经 `render_skill_content()` 进 `<skill_instructions>` 时**逐字不转义**
    （技能是可信本地内容，见模块头"信任口径"）。
    """
    blocks: list[str] = []
    for name in invoked_names(text):
        skill = load_skill(kb_path, name)
        if skill is None or not skill.user_invocable:
            continue
        blocks.append(render_skill_content(skill))
    return "\n\n".join(blocks)
