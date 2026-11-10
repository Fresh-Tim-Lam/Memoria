"""Dev 批注板可拖动（2026-11-10，人要求「好让我操作别的 UI」）。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANNOTATOR = ROOT / "tools" / "dev-annotator" / "annotator.js"


def test_annotation_board_is_draggable_and_position_is_saved() -> None:
    src = ANNOTATOR.read_text(encoding="utf-8")
    # 标题栏起拖，按钮点击不能触发拖动
    assert "barEl.addEventListener('pointerdown'" in src
    assert "e.target.closest('button')" in src
    assert "memoria.dev.annotator.pos.v1" in src
    # 视口夹紧 + 位置持久化 + 双击复位
    assert "function clampPos(" in src
    assert "localStorage.setItem(POS_KEY" in src
    assert "barEl.addEventListener('dblclick'" in src
    assert "applyPos(null)" in src
    # 拖动视觉反馈
    assert "cursor: grab" in src
    assert ".wrap.is-dragging .bar" in src
