"""源码完整性守卫：**每个 `src/**/*.py` 都必须能被编译**，且首行不得有前导空白/BOM。

为什么需要这条（2026-09-21 真实事故）：`body_edit.py` 磁盘上第 1 行被写进了一个**前导空格**
⇒ `IndentationError: unexpected indent`。写路径里所有 `edit_body` 调用都会在**导入**这一步炸掉，
而工具层把它包成一句与参数无关的 `TOOL_FAILED —— unexpected indent (body_edit.py, line 1)`：
调用方（模型与人）看到的是"工具坏了但不知道坏了什么"，连着四次提议全废 —— **这正是本文件要防的**。

它同时兜住另外两类"静默变坏"：
- **BOM**：`\ufeff` 打头的文件在部分解释器/工具链下会以奇怪方式报错（本仓统一不带 BOM）；
- **首行缩进**：模块第一条语句被缩进 ⇒ 直接 IndentationError（就是本次事故）。

代价：遍历 `src/**` 逐文件 `compile()`，几百毫秒级；比"等用户撞上"便宜得多。
"""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"

_SOURCES = sorted(_SRC.rglob("*.py"))


def test_there_are_sources_to_check() -> None:
    """守卫自身别空转（找不到源码说明路径写错了，那样这条守卫会永远通过）。"""
    assert len(_SOURCES) > 50, f"只找到 {len(_SOURCES)} 个 .py，路径可能不对：{_SRC}"


@pytest.mark.parametrize("path", _SOURCES, ids=[p.relative_to(_ROOT).as_posix() for p in _SOURCES])
def test_source_compiles(path: Path) -> None:
    """`compile()` 一遍（= 解释器真正加载时会做的事）；失败即报"哪个文件、第几行、什么错"。"""
    text = path.read_text(encoding="utf-8")
    try:
        compile(text, str(path), "exec")
    except SyntaxError as exc:  # pragma: no cover — 触发时就是要让它红
        raise AssertionError(
            f"{path.relative_to(_ROOT).as_posix()} 编译失败：{type(exc).__name__}: {exc.msg}"
            f"（第 {exc.lineno} 行：{text.splitlines()[exc.lineno - 1] if exc.lineno else ''!r}）"
        ) from exc


@pytest.mark.parametrize("path", _SOURCES, ids=[p.relative_to(_ROOT).as_posix() for p in _SOURCES])
def test_source_first_line_is_clean(path: Path) -> None:
    """首行不许有前导空白 / BOM —— 2026-09-21 的 `body_edit.py` 事故就是这条没守住。"""
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"{path.name} 带 UTF-8 BOM"
    first = path.read_text(encoding="utf-8").split("\n", 1)[0]
    assert first == first.lstrip(), f"{path.name} 首行有前导空白：{first[:40]!r}"
