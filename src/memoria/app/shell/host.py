"""桌面窗口宿主协议：与 UI 框架（pywebview / PyQt6）解耦。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

# ── 窗口最小尺寸（px）：唯一事实源 ───────────────────────────────────────────
# 引用方：pywebview 壳（create_window min_size）、PyQt6 壳（setMinimumSize）、
# UIAPI 的 get_window_chrome/window_resize_to（前端按它夹取 JS 侧边缘缩放）、
# scripts/diag_webview.py。
# 取 1000×600 的理由：三栏并排所需宽度 = 左栏默认 17.5rem(280) + 右栏 dock 默认
# 22rem(352) + 文档区保底 CONTENT_MIN_PX(360) ≈ 992 → 取整 1000，使最小窗口下
# dock 仍能正常显示（不会被 `-agent-dock--auto-hidden` 自动隐藏）。高度沿用 600。
WINDOW_MIN_WIDTH = 1000
WINDOW_MIN_HEIGHT = 600


@runtime_checkable
class WindowHost(Protocol):
    """窗口原生能力抽象；UIAPI 窗口相关方法委托给此协议。"""

    kind: str
    frameless: bool

    @property
    def maximized(self) -> bool: ...

    def pick_directory(self) -> str | None: ...

    def pick_import_files(self) -> list[str]: ...

    def pick_image_file(self) -> str | None: ...

    def minimize(self) -> None: ...

    def close(self) -> None: ...

    def resize(self, width: int, height: int, anchor: str) -> None: ...

    def move_to(self, x: int, y: int) -> None: ...

    def toggle_maximize(self) -> bool: ...

    def restore_from_drag(
        self, screen_x: float, screen_y: float, ratio_x: float
    ) -> tuple[int, int, int, int]: ...

    def start_move(self) -> None: ...
