"""pywebview 窗口宿主（开发默认）。"""

from __future__ import annotations

import sys

import webview

from memoria.app.window_win32 import (
    begin_caption_drag,
    dpi_scale,
    is_maximized,
    move_window,
    normal_bounds,
    show_window_state,
    start_system_drag,
)

# 文件夹对话框尺寸控制机制：Windows 按"可执行文件名"分别保存对话框的
# 位置/大小状态（微软文档原话），打包态 Memoria.exe 曾记住"最大化"尺寸，
# 导致每次弹出文件夹选择器都全屏。修复：SetClientGuid 指定**每次全新**的
# 客户端 GUID——该 GUID 从未有过保存状态，对话框必然以系统默认尺寸打开，
# 从机制上杜绝"按 exe 记忆的全屏状态"被套用。见 _vista_folder_picker。
def _vista_folder_picker(parent_handle, initial_directory: str | None = None):
    """现代文件夹选择对话框（IFileDialog）——复刻 pywebview winforms
    OpenFolderDialog 的反射调用，并加入 SetClientGuid(Guid.NewGuid())：

    每次弹窗分配一个全新客户端 GUID，对话框状态（位置/大小/最大化）
    不再读取按可执行文件名保存的历史状态，必然以系统默认尺寸弹出，
    彻底规避打包态"全屏"问题。

    返回选中目录元组；用户取消返回 None；反射链路异常直接上抛，
    由调用方（pick_directory）回退 pywebview 原生实现。
    """
    from System import Array, Guid, Object, UInt32  # noqa: PLC0415
    import System.Windows.Forms as WinForms  # noqa: PLC0415
    from System.Reflection import Assembly, BindingFlags  # noqa: PLC0415

    flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic
    wf_asm = Assembly.LoadWithPartialName("System.Windows.Forms")
    i_file_dialog_type = wf_asm.GetType(
        "System.Windows.Forms.FileDialogNative+IFileDialog"
    )
    open_file_dialog_type = wf_asm.GetType(
        "System.Windows.Forms.OpenFileDialog"
    )
    file_dialog_type = wf_asm.GetType("System.Windows.Forms.FileDialog")

    dialog = WinForms.OpenFileDialog()
    dialog.InitialDirectory = initial_directory or ""
    dialog.Title = "选择知识库文件夹"
    dialog.Filter = "Folders|\n"
    dialog.AddExtension = False
    dialog.CheckFileExists = False
    dialog.DereferenceLinks = True
    dialog.Multiselect = False
    dialog.RestoreDirectory = True

    i_file_dialog = open_file_dialog_type.GetMethod(
        "CreateVistaDialog", flags
    ).Invoke(dialog, [])
    open_file_dialog_type.GetMethod(
        "OnBeforeVistaDialog", flags
    ).Invoke(dialog, [i_file_dialog])
    options = file_dialog_type.GetMethod("GetOptions", flags).Invoke(
        dialog, []
    )
    fos_pick_folders = (
        wf_asm.GetType("System.Windows.Forms.FileDialogNative+FOS")
        .GetField("FOS_PICKFOLDERS")
        .GetValue(None)
    )
    i_file_dialog_type.GetMethod("SetOptions", flags).Invoke(
        i_file_dialog, [options.op_BitwiseOr(fos_pick_folders)]
    )

    # —— 尺寸控制：全新客户端 GUID → 无任何历史保存状态 → 默认尺寸 ——
    set_client_guid = i_file_dialog_type.GetMethod("SetClientGuid", flags)
    if set_client_guid is not None:
        try:
            set_client_guid.Invoke(i_file_dialog, [Guid.NewGuid()])
        except Exception:  # noqa: BLE001  GUID 设置失败不影响弹出
            pass
    # ——

    events_ctor = wf_asm.GetType(
        "System.Windows.Forms.FileDialog+VistaDialogEvents"
    ).GetConstructor(flags, None, [file_dialog_type], [])
    advise_args = Array[Object](
        [events_ctor.Invoke([dialog]), UInt32(0)]
    )
    i_file_dialog_type.GetMethod("Advise", flags).Invoke(
        i_file_dialog, advise_args
    )
    dw_cookie = advise_args.GetValue(1)
    try:
        result = i_file_dialog_type.GetMethod("Show", flags).Invoke(
            i_file_dialog,
            [parent_handle if parent_handle else None],
        )
        if result == 0:
            return tuple(dialog.FileNames)
        return None  # 用户取消
    finally:
        i_file_dialog_type.GetMethod("Unadvise", flags).Invoke(
            i_file_dialog, [UInt32(dw_cookie)]
        )


class PyWebViewHost:
    kind = "pywebview"

    def __init__(self, *, frameless: bool = False) -> None:
        self.frameless = frameless
        self._maximized = False
        self._saved_bounds: tuple[int, int, int, int] | None = None

    @property
    def maximized(self) -> bool:
        # 读取真实窗口状态（用户可能通过 Aero Snap / 系统命令最大化）
        if sys.platform == "win32":
            window = self._window()
            if window is not None:
                cur = is_maximized(window)
                if cur is not None:
                    self._maximized = cur
        return self._maximized

    def _window(self):
        return webview.windows[0] if webview.windows else None

    def pick_directory(self) -> str | None:
        window = self._window()
        if window is None:
            return None
        try:
            native = getattr(window, "native", None)
            handle = getattr(native, "Handle", None) if native is not None else None
            # 自建 IFileDialog（SetClientGuid 尺寸控制）；取消返回 None 直接返回，
            # 绝不二次弹出 pywebview 原生对话框（打包态会触发全屏状态）
            result = _vista_folder_picker(handle)
            return result[0] if result else None
        except Exception:  # noqa: BLE001
            # 仅反射链路异常时回退 pywebview 原生实现，保证功能可用
            result = window.create_file_dialog(webview.FileDialog.FOLDER)
            return result[0] if result else None

    def pick_import_files(self) -> list[str]:
        window = self._window()
        if window is None:
            return []
        result = window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=True,
            file_types=("Text Files (*.txt;*.md)", "All Files (*.*)"),
        )
        return list(result) if result else []

    def minimize(self) -> None:
        window = self._window()
        if window is None:
            raise RuntimeError("窗口不可用")
        if sys.platform == "win32":
            # ShowWindow(SW_MINIMIZE)：直接走系统状态机，触发 DWM 原生
            # 最小化动画（窗口向下渐变飞向任务栏），绕过 WinForms 拦截
            if not show_window_state(window, 6):  # SW_MINIMIZE
                raise RuntimeError("窗口不可用")
            return
        window.minimize()

    def close(self) -> None:
        window = self._window()
        if window is None:
            raise RuntimeError("窗口不可用")
        window.destroy()

    def resize(self, width: int, height: int, anchor: str) -> None:
        if self._maximized:
            raise RuntimeError("已最大化，无法调整大小")
        window = self._window()
        if window is None:
            raise RuntimeError("窗口不可用")
        from webview.window import FixPoint

        anchors = {
            "n": FixPoint.SOUTH | FixPoint.WEST | FixPoint.EAST,
            "s": FixPoint.NORTH | FixPoint.WEST | FixPoint.EAST,
            "e": FixPoint.NORTH | FixPoint.SOUTH | FixPoint.WEST,
            "w": FixPoint.NORTH | FixPoint.SOUTH | FixPoint.EAST,
            "nw": FixPoint.SOUTH | FixPoint.EAST,
            "ne": FixPoint.SOUTH | FixPoint.WEST,
            "sw": FixPoint.NORTH | FixPoint.EAST,
            "se": FixPoint.NORTH | FixPoint.WEST,
        }
        fix = anchors.get(str(anchor or "se"), FixPoint.NORTH | FixPoint.WEST)
        window.resize(int(width), int(height), fix)

    def move_to(self, x: int, y: int) -> None:
        # 实时读取真实最大化状态（Aero Snap / 原生拖动还原后缓存可能过期）
        if self.maximized:
            raise RuntimeError("已最大化")
        window = self._window()
        if window is None:
            raise RuntimeError("窗口不可用")
        if sys.platform == "win32" and self.frameless:
            # 前端 screenX/screenY 为 DIP，SetWindowPos 需物理像素
            scale = dpi_scale(window)
            px = int(int(x) * scale)
            py = int(int(y) * scale)
            if not move_window(window, px, py):
                raise RuntimeError("窗口不可用")
        else:
            window.move(int(x), int(y))

    def toggle_maximize(self) -> bool:
        window = self._window()
        if window is None:
            raise RuntimeError("窗口不可用")

        if sys.platform == "win32":
            # ShowWindow(SW_MAXIMIZE / SW_RESTORE)：直接走系统状态机，
            # 触发 DWM 原生最大化/还原动画 + 自动避开任务栏；状态实时读取
            cur = bool(is_maximized(window))
            cmd = 3 if not cur else 9  # SW_MAXIMIZE / SW_RESTORE
            if not show_window_state(window, cmd):
                raise RuntimeError("窗口不可用")
            self._maximized = not cur
            return self._maximized

        if self._maximized:
            window.restore()
            self._maximized = False
        else:
            window.maximize()
            self._maximized = True
        return self._maximized

    def restore_from_drag(
        self, screen_x: float, screen_y: float, ratio_x: float
    ) -> tuple[int, int, int, int]:
        if not self._maximized:
            if self._saved_bounds:
                x, y, w, h = self._saved_bounds
                return x, y, w, h
            return 0, 0, 1280, 860

        window = self._window()
        if window is None:
            raise RuntimeError("窗口不可用")

        ratio = max(0.0, min(1.0, float(ratio_x)))
        titlebar_y = 17
        if self._saved_bounds:
            _, _, w, h = self._saved_bounds
        else:
            nb = normal_bounds(window) if sys.platform == "win32" else None
            w, h = (nb[2], nb[3]) if nb else (1280, 860)
        scale = dpi_scale(window) if sys.platform == "win32" else 1.0
        px = int(float(screen_x) * scale - ratio * w)
        py = int(float(screen_y) * scale - titlebar_y)

        if sys.platform == "win32" and self.frameless:
            # 先还原（触发还原动画）再定位到鼠标，否则最大化状态下 SetWindowPos 无效
            show_window_state(window, 9)  # SW_RESTORE
            move_window(window, px, py)
        else:
            window.restore()
            window.move(px, py)
            window.resize(w, h)
        self._maximized = False
        # JS 端用 DIP 计算（e.screenX 为 DIP），统一返回 DIP 数值
        return int(px / scale), int(py / scale), int(w / scale), int(h / scale)

    def start_move(self) -> None:
        """系统级窗口拖动（ReleaseCapture + WM_NCLBUTTONDOWN HTCAPTION）：
        无边框窗口获得原生拖动体验，Aero Snap 生效。"""
        window = self._window()
        if window is None:
            return
        if sys.platform != "win32":
            return
        start_system_drag(window)

    def begin_drag(self) -> None:
        """前端检测到标题栏拖拽动作后调用：PostMessage 给窗口，由 WndProc
        （UI 线程）发起原生标题栏拖动（ReleaseCapture + WM_NCLBUTTONDOWN
        HTCAPTION），鼠标捕获 / Aero Snap / 最大化下拉还原全部原生处理。"""
        window = self._window()
        if window is None:
            return
        if sys.platform != "win32":
            return
        begin_caption_drag(window)
