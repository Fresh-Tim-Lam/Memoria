"""PyQt6 窗口宿主（发布壳；Phase 2/3 接入 Win32 hidden chrome）。"""



from __future__ import annotations



from typing import TYPE_CHECKING



from memoria.app.shell.shell_log import shell_log, shell_log_window



if TYPE_CHECKING:

    from PyQt6.QtWidgets import QMainWindow





class PyQt6Host:

    kind = "pyqt6"



    def __init__(self, window: QMainWindow, *, frameless: bool = False) -> None:

        self._window = window

        self.frameless = frameless

        self._saved_bounds: tuple[int, int, int, int] | None = None



    @property

    def maximized(self) -> bool:

        return self._window.isMaximized()



    def pick_directory(self) -> str | None:

        from PyQt6.QtWidgets import QFileDialog



        path = QFileDialog.getExistingDirectory(self._window, "选择知识库目录")

        return path or None



    def pick_import_files(self) -> list[str]:

        from PyQt6.QtWidgets import QFileDialog

        paths, _ = QFileDialog.getOpenFileNames(self._window, "选择导入文件", "", "文本文件 (*.txt);;Markdown (*.md);;所有文件 (*)")

        return paths or []

    def pick_image_file(self) -> str | None:

        from PyQt6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self._window, "选择图片", "", "图片文件 (*.png *.jpg *.jpeg *.gif *.svg *.webp *.bmp *.ico);;所有文件 (*)"
        )

        return path or None



    def minimize(self) -> None:

        shell_log_window(self._window, "host_minimize")

        self._window.showMinimized()



    def close(self) -> None:

        self._window.close()



    def resize(self, width: int, height: int, anchor: str) -> None:

        if self.maximized:

            raise RuntimeError("已最大化，无法调整大小")

        geo = self._window.geometry()

        x, y, w, h = geo.x(), geo.y(), geo.width(), geo.height()

        nw, nh = int(width), int(height)

        edge = str(anchor or "se")

        if "w" in edge:

            x += w - nw

        if "n" in edge:

            y += h - nh

        self._window.setGeometry(x, y, nw, nh)
        from memoria.app.shell.pyqt6_hidden_chrome import set_restore_target

        set_restore_target(self._window, (x, y, nw, nh))
        self._saved_bounds = (x, y, nw, nh)



    def move_to(self, x: int, y: int) -> None:

        if self.maximized:

            raise RuntimeError("已最大化")

        geo = self._window.geometry()

        self._window.setGeometry(int(x), int(y), geo.width(), geo.height())
        from memoria.app.shell.pyqt6_hidden_chrome import set_restore_target

        bounds = (int(x), int(y), geo.width(), geo.height())
        set_restore_target(self._window, bounds)
        self._saved_bounds = bounds



    def start_move(self) -> None:

        from memoria.app.shell.pyqt6_hidden_chrome import begin_system_move



        shell_log_window(self._window, "host_start_move")

        if not begin_system_move(self._window):

            shell_log("host_start_move_failed")

            raise RuntimeError("无法开始拖动窗口")



    def toggle_maximize(self) -> bool:

        from memoria.app.shell.pyqt6_hidden_chrome import (

            read_normal_bounds,

            store_normal_bounds,

            set_restore_target,

            sync_web_content_after_state_change,

            win32_maximize,

            win32_restore,

        )



        if self._window.isMaximized():

            shell_log_window(

                self._window, "host_toggle_restore", bounds=self._saved_bounds

            )

            win32_restore(self._window, self._saved_bounds)
            sync_web_content_after_state_change(self._window)
            return False



        bounds = read_normal_bounds(self._window)

        if bounds:

            self._saved_bounds = bounds

            set_restore_target(self._window, bounds)

        shell_log_window(self._window, "host_toggle_maximize", bounds=bounds)

        win32_maximize(self._window)

        sync_web_content_after_state_change(self._window)

        return True



    def restore_from_drag(

        self, screen_x: float, screen_y: float, ratio_x: float

    ) -> tuple[int, int, int, int]:

        from memoria.app.shell.pyqt6_hidden_chrome import win32_restore



        ratio = max(0.0, min(1.0, float(ratio_x)))

        titlebar_y = 17

        if self._saved_bounds:

            _, _, w, h = self._saved_bounds

        else:

            w, h = 1280, 860

        px = int(float(screen_x) - ratio * w)

        py = int(float(screen_y) - titlebar_y)

        bounds = (px, py, w, h)

        shell_log_window(self._window, "host_restore_from_drag", bounds=bounds)

        win32_restore(self._window, bounds)

        return px, py, w, h

    def set_toolbar_drag_exclusion(self, left_x: int) -> None:
        from memoria.app.shell.pyqt6_hidden_chrome import set_toolbar_drag_exclusion

        set_toolbar_drag_exclusion(self._window, left_x)

