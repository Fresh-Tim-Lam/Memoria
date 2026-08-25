"""桌面窗口宿主协议：与 UI 框架（pywebview / PyQt6）解耦。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class WindowHost(Protocol):
    """窗口原生能力抽象；UIAPI 窗口相关方法委托给此协议。"""

    kind: str
    frameless: bool

    @property
    def maximized(self) -> bool: ...

    def pick_directory(self) -> str | None: ...

    def pick_import_files(self) -> list[str]: ...

    def minimize(self) -> None: ...

    def close(self) -> None: ...

    def resize(self, width: int, height: int, anchor: str) -> None: ...

    def move_to(self, x: int, y: int) -> None: ...

    def toggle_maximize(self) -> bool: ...

    def restore_from_drag(
        self, screen_x: float, screen_y: float, ratio_x: float
    ) -> tuple[int, int, int, int]: ...

    def start_move(self) -> None: ...
