"""标题解析（**唯一实现**）与 KP range 提议。

## 一、本模块是 heading 语义的唯一落点（task-120 / R-D2）

仓库原有**两套** heading 正则，语义不一致 = 并行事实源：

| 原位置 | 原正则 | 问题 |
|---|---|---|
| `services/document.py:420` | `^(#{1,6})\\s+` | 不判围栏代码块 ⇒ 代码内 `# 注释` 被当 heading |
| `services/heading_proposals.py` | `^(#{2,6})\\s+` | 同上，且**漏掉全部 h1**（实测语料 279 个） |

2026-10-25 起两者都走本模块的 `scan_headings()`。**新增消费者禁止自写 heading 正则**
（自写即成为第二事实源；`scripts/benchmark/maintenance/section_headings_census.py` 会断言）。

**为什么扫描器放在本模块而不是 `services/agent/section_index.py`**：
`document.py`（services）已经依赖 `range_proposals` → `heading_proposals` 这条链；
若把扫描器放进 `services/agent/`，`services.document` 就要反依赖 agent 子包，
而 `services/agent/__init__.py` 明文承诺"本包自身不导入任何子模块，避免…"——
把 agent 包塞进 document 的依赖闭包会让这条承诺变成刀尖。
故：**扫描器在 services 层（本模块），agent 层（`section_index.py`）作为消费者 import**，
依赖方向与既有架构一致（agent → services）。

## 二、契约来源

`artifacts/agent/verify/debate/assumptions/as-section-range.md` §0 C1–C5、§4 D.1–D.5
（`AS-SECTION-RANGE` = 有条件成立）：

- **C1** 先剔 frontmatter 与围栏代码块，再做 heading 匹配
- **C2** 重名消歧靠 `parent_path` + `line_no` 双锚（本模块提供两者，不做消歧决策）
- **C3** 无法唯一时必须报错，**不得取首个**（因此本模块**不提供** `find_first`）
- **C4** 每个 heading 携带**原文件 1-based 行号**，调用方可按行号二次寻址
- **C5** 级别范围**写死在一处**：`HEADING_LEVEL_MIN` / `HEADING_LEVEL_MAX`（= 1 / 6）

## 三、与实测基线的等价性（必须成立）

本实现复现 `as-section-range-measure.json` 的**围栏感知**口径：
真 heading **3517**（h1 **279**）、朴素口径 3609、围栏误判 **92**、重名 **33** 组、级别分布
`{1:279, 2:1574, 3:1545, 4:118, 5:1}`。
复现脚本：`scripts/benchmark/maintenance/section_headings_census.py`（不一致即非零退出）。

## 四、明确不做

- 不做大小写折叠：D.1 规定默认不折叠；需要时调用方显式传 `ci=True`
- 不解析 Setext heading（`===` / `---` 下划线式）：基线测量也未计入，保持同口径
- 不剥 frontmatter 后重排行号：**行号必须指向原文件**（C4），故只做"跳过"而非"删除"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from memoria.range.constants import SNIPPET_MAX_LEN

# ── C5：级别范围写死在这一个地方 ────────────────────────────────────────────
HEADING_LEVEL_MIN = 1
HEADING_LEVEL_MAX = 6

#: **唯一的** heading 行首正则（`^(#{1,6})\s+`）。
#: 与 `document.py` 原口径一致（含 h1）；`heading_proposals` 原来漏 h1，统一后以本正则为准。
HEADING_RE = re.compile(r"^(#{%d,%d})\s+" % (HEADING_LEVEL_MIN, HEADING_LEVEL_MAX))

#: 围栏代码块开/闭标记（``` 或 ~~~，≥3 个同字符）
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")

#: 行首 `#` 串 + 其后空白（从 raw 行取标题文本）
_LEADING_HASHES_RE = re.compile(r"^#{%d,%d}\s*" % (HEADING_LEVEL_MIN, HEADING_LEVEL_MAX))

#: ATX 闭合标记（`## 标题 ##` → `标题`）
_TRAILING_HASHES_RE = re.compile(r"\s+#+\s*$")

#: 内部连续空白
_WS_RE = re.compile(r"\s+")

# ── 提议策略（**不是**扫描器级别范围；D.5 要求分开命名）────────────────────
#: 哪些级别值得提议成 KP range。
#: 2026-10-25（task-120 R-D2）：由历史值 2 改为 1 —— 与 C5 的扫描范围一致，
#: 修复"漏全部 h1"（实测语料 279 个）。若产品上不想给 h1 提议整篇 range，
#: 把本值改回 2 即可（**只改这一处，不动正则**）。
PROPOSABLE_LEVEL_MIN = 1
PROPOSABLE_LEVEL_MAX = 6


@dataclass(frozen=True, slots=True)
class Heading:
    """一个 heading 的**纯观测**（不含任何消歧决策）。

    - `parent_path`：根到父级的归一化标题链（同级重名只有它能区分，C2）
    - `line_no`：**原文件 1-based 行号**（可直接回填 `#L<n>` 锚点，C4）
    """

    index0: int
    """0-based 行索引（供内部切片）。"""
    line_no: int
    """1-based 行号（对外唯一寻址单位，C4）。"""
    level: int
    """级别 1..6。"""
    raw: str
    """原始行（已 strip，仍含 `#`）。"""
    title: str
    """归一化标题（去 `#`、去 ATX 闭合 `#`、空白折叠；**不**折叠大小写）。"""
    parent_path: tuple[str, ...] = field(default_factory=tuple)
    """父级标题链（归一化文本），用于 C2 消歧。"""

    def ident(self) -> dict:
        """稳定可序列化身份（错误码 payload / 候选列表用）。"""
        return {
            "line_no": self.line_no,
            "level": self.level,
            "title": self.title,
            "parent_path": list(self.parent_path),
        }


def split_lines(body: str) -> list[str]:
    """按 `\\n` 切行（**不用** `splitlines()`，避免额外切分 `\\u2028` 等，保持与基线同口径）。"""
    return body.split("\n")


def frontmatter_end_line0(lines: list[str]) -> int:
    """frontmatter 结束行的 0-based 索引（含）；无 frontmatter 返回 -1。

    口径与基线一致：仅当**首行** strip 后为 `---`，且能找到后续 strip 后为 `---` 的行时成立。
    找不到闭合线 ⇒ 视为无 frontmatter（不把整篇当 frontmatter，避免整篇丢 heading）。
    """
    if not lines:
        return -1
    if lines[0].strip() != "---":
        return -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return i
    return -1


def fence_ranges(lines: list[str]) -> list[tuple[int, int]]:
    """围栏代码块区间（0-based，闭区间）。

    闭合条件与基线一致：**同字符**且长度 **≥** 开启者长度。未闭合 ⇒ 延伸到文末。
    """
    ranges: list[tuple[int, int]] = []
    start = -1
    ch: str | None = None
    open_len = 0
    for i, line in enumerate(lines):
        m = _FENCE_RE.match(line.strip())
        if not m:
            continue
        run = m.group(1)
        c = run[0]
        n = len(run)
        if start < 0:
            start, ch, open_len = i, c, n
        elif c == ch and n >= open_len:
            ranges.append((start, i))
            start, ch, open_len = -1, None, 0
    if start >= 0:
        ranges.append((start, len(lines) - 1))
    return ranges


def normalize_title(raw_or_title: str, *, ci: bool = False) -> str:
    """归一化标题（D.1）：strip → 去行首 `#` → 去 ATX 闭合 `#` → 空白折叠 →（可选）折小写。"""
    t = raw_or_title.strip()
    t = _LEADING_HASHES_RE.sub("", t)
    t = _TRAILING_HASHES_RE.sub("", t)
    t = _WS_RE.sub(" ", t).strip()
    return t.lower() if ci else t


def scan_headings(body: str) -> list[Heading]:
    """扫描 body 的全部 heading（frontmatter / 围栏内跳过），按行号升序返回。

    这是全仓 heading 语义的**唯一入口**。返回值携带 `line_no`（原文件行号）与
    `parent_path`（C2 双锚之一）；消歧由调用方按 C3 处理（**多候选必须报错**）。
    """
    lines = split_lines(body)
    fm_end = frontmatter_end_line0(lines)
    fences = fence_ranges(lines)

    in_fence = bytearray(len(lines))
    for a, b in fences:
        for i in range(a, min(b + 1, len(lines))):
            in_fence[i] = 1

    out: list[Heading] = []
    stack: list[tuple[int, str]] = []
    for idx, line in enumerate(lines):
        if idx <= fm_end:
            continue
        if in_fence[idx]:
            continue
        m = HEADING_RE.match(line)
        if not m:
            continue
        level = len(m.group(1))
        raw = line.strip()
        title = normalize_title(raw)
        while stack and stack[-1][0] >= level:
            stack.pop()
        out.append(
            Heading(
                index0=idx,
                line_no=idx + 1,
                level=level,
                raw=raw,
                title=title,
                parent_path=tuple(t for _, t in stack),
            )
        )
        stack.append((level, title))
    return out


def heading_index(headings: list[Heading], *, ci: bool = False) -> dict[str, list[Heading]]:
    """`归一化标题 -> [Heading]` 索引（供 C2/C3 消歧；**不**做"取首个"）。"""
    idx: dict[str, list[Heading]] = {}
    for h in headings:
        key = h.title.lower() if ci else h.title
        idx.setdefault(key, []).append(h)
    return idx


def candidates_by_title(headings: list[Heading], title: str, *, ci: bool = False) -> list[Heading]:
    """按标题取候选（0..n 个）。**返回全部候选**，不做消歧、不取首个（C3）。"""
    want = normalize_title(title, ci=ci)
    if ci:
        want = want.lower()
    return [h for h in headings if (h.title.lower() if ci else h.title) == want]


def level_distribution(headings: list[Heading]) -> dict[int, int]:
    """级别分布（级别 -> 计数），供 outline 与诊断用。"""
    dist: dict[int, int] = {lvl: 0 for lvl in range(HEADING_LEVEL_MIN, HEADING_LEVEL_MAX + 1)}
    for h in headings:
        dist[h.level] = dist.get(h.level, 0) + 1
    return dist


def propose_ranges_from_headings(body: str) -> list[dict]:
    """按 heading 提议 KP range（本模块的**第一个消费者**，也是原唯一功能）。

    与原实现一致之处：range 从自身行到"下一条级别 ≤ 自身的 heading"之前（含尾随空行裁剪），
    `start.snippet` 为原始标题行，`end.snippet` 为末行前缀。

    因改用 `scan_headings()` 而**有意改变**的两点（均为修复，见 R-D2）：
    1. 围栏代码块内的 `# ...` 不再产生提议（原：会凭空多出"节"）；
    2. h1 现在会被提议（`PROPOSABLE_LEVEL_MIN = 1`；原 `{2,6}` 漏 279 个）。
    """
    lines = split_lines(body)
    heads = [
        h for h in scan_headings(body) if PROPOSABLE_LEVEL_MIN <= h.level <= PROPOSABLE_LEVEL_MAX
    ]

    proposals: list[dict] = []
    for idx, head in enumerate(heads):
        line_i = head.index0
        depth = head.level
        end_i = len(lines) - 1
        for later in heads[idx + 1 :]:
            if later.level <= depth:
                end_i = later.index0 - 1
                break
        while end_i > line_i and not lines[end_i].strip():
            end_i -= 1
        end_line = lines[end_i].strip() if end_i >= line_i else head.raw
        proposals.append(
            {
                "name": head.title,
                "range": {
                    "start": {"snippet": head.raw, "line_hint": head.line_no},
                    "end": {"snippet": end_line[:SNIPPET_MAX_LEN], "line_hint": end_i + 1},
                },
                "proposed": True,
            }
        )
    return proposals


__all__ = [
    "HEADING_LEVEL_MIN",
    "HEADING_LEVEL_MAX",
    "HEADING_RE",
    "PROPOSABLE_LEVEL_MIN",
    "PROPOSABLE_LEVEL_MAX",
    "Heading",
    "split_lines",
    "frontmatter_end_line0",
    "fence_ranges",
    "normalize_title",
    "scan_headings",
    "heading_index",
    "candidates_by_title",
    "level_distribution",
    "propose_ranges_from_headings",
]
