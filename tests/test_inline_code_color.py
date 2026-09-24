"""行内代码 `` `文字` `` 配色的契约钉子（**对齐上游 dsh 的 web 客户端**）。

人：「对于 `文字` 这种样式，memoria 统一把他颜色改一下，和上游的这个样式的颜色对齐」。
上游口径（本地检出 `D:\\deepseek-harness` 可查，非推测）：

- `packages/client/ui-primitives/src/markdown/MarkdownText.module.css:146-156` —— 行内代码**只声明底色**
  （`background-color: var(--dsw-alias-markdown-inline-code)`），**不声明文字颜色**（随正文）；
- `packages/client/ui-theme/src/styles/design-platform.css:215`（亮）/ `:307`（暗）——
  亮 = `--dsw-static-neutral-bluish-100` = `rgb(235, 238, 242)`、暗 = `…-850` = `rgb(44, 44, 46)`。

本文件钉五件事：

1. `.markdown-body code` 的**底色**走新令牌 `--code-inline-bg`，并**带旧值兜底**（没令牌的主题退回旧观感）；
2. 文字颜色**随正文**（`color: inherit`）—— 旧值 `var(--warning)` 的橙色是本地自创、上游没有，
   正是人看到的那处不一致 ⇒ 这里钉"不许回到某个固定彩色"；
3. 两套主题的令牌取值**逐字等于上游**（暗 `rgb(44, 44, 46)` / 亮 `rgb(235, 238, 242)`），且浅色那档
   必须写在 `html[data-theme="light"]` 作用域里（否则压不过默认档）；
4. 注释里保留**上游出处**（令牌名 + 文件），便于下一个人核对；
5. **只有这一处**消费点（预览 / 对话正文 / 计划卡共用同一渲染器 ⇒ 改一处即"统一"）。
"""

from __future__ import annotations

import re
from pathlib import Path

_THEME = Path(__file__).resolve().parents[1] / "src" / "memoria" / "ui" / "static" / "theme"
_DARK = _THEME / "memoria.css"
_LIGHT = _THEME / "light.css"
_APP_CSS = Path(__file__).resolve().parents[1] / "src" / "memoria" / "ui" / "static" / "app" / "css" / "app.css"

#: 上游两套取值（逐字）
UPSTREAM_DARK = "rgb(44, 44, 46)"
UPSTREAM_LIGHT = "rgb(235, 238, 242)"


def _rule(css: str, selector: str) -> str:
    """取某条**行首锚定**的规则体（子串匹配会误取覆盖块，见 `test_file_tree_icons.py` 的教训）。"""
    found = re.search(r"^" + re.escape(selector) + r" \{([^}]*)\}", css, re.M)
    assert found, f"缺规则：{selector}"
    return found.group(1)


def test_inline_code_uses_the_new_background_token_with_fallback() -> None:
    """底色 = `--code-inline-bg`，并保留 `var(--bg-tertiary)` 兜底（没令牌的主题/文件不炸）。"""
    body = _rule(_DARK.read_text(encoding="utf-8"), ".markdown-body code")
    assert "background: var(--code-inline-bg, var(--bg-tertiary))" in body


def test_inline_code_text_takes_the_body_colour() -> None:
    """文字颜色**随正文**：上游不声明 color，本地就是 `inherit`；不许回到固定彩色（旧值 `--warning`）。"""
    body = _rule(_DARK.read_text(encoding="utf-8"), ".markdown-body code")
    assert "color: inherit" in body, "行内代码的文字颜色应随正文（上游同口径）"
    assert "--warning" not in body, "橙色文字是本地自创、上游没有 ⇒ 不许回到这个值"


def test_the_two_themes_carry_upstream_values_verbatim() -> None:
    """两套取值**逐字**等于上游（不是"看着差不多"）。"""
    dark = _DARK.read_text(encoding="utf-8")
    light = _LIGHT.read_text(encoding="utf-8")
    assert f"--code-inline-bg: {UPSTREAM_DARK};" in dark, f"暗色档应等于上游 {UPSTREAM_DARK}"
    assert f"--code-inline-bg: {UPSTREAM_LIGHT};" in light, f"亮色档应等于上游 {UPSTREAM_LIGHT}"
    # 浅色那档必须落在 light 主题作用域里，否则压不过 memoria.css 的 :root 默认值
    tail = light.rsplit('html[data-theme="light"]', 1)[1]
    assert f"--code-inline-bg: {UPSTREAM_LIGHT};" in tail


def test_comments_keep_the_upstream_provenance() -> None:
    """注释里留上游出处（令牌名 + 文件），下一个人能自己核对。"""
    dark = _DARK.read_text(encoding="utf-8")
    assert "--dsw-alias-markdown-inline-code" in dark
    assert "ui-theme/src/styles/design-platform.css" in dark
    assert "MarkdownText.module.css" in dark


def test_inline_code_is_styled_in_exactly_one_place() -> None:
    """"统一"= 只有 `.markdown-body` 这一处给行内代码上色；`app.css` 里不许再单独给 `code` 上色。"""
    app = _APP_CSS.read_text(encoding="utf-8")
    for line in app.splitlines():
        head = line.split("{", 1)[0]
        if re.search(r"\bcode\b", head) and "{" in line:
            assert not re.search(r"color:\s*(?!inherit)", line), f"app.css 里另有行内代码配色：{line.strip()}"
