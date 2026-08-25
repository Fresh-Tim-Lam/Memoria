"""QWebChannel RPC：将 UIAPI 方法暴露给 PyQt6 WebEngine。"""

from __future__ import annotations

import json
import traceback
from typing import Any

from PyQt6.QtCore import QObject, pyqtSlot

from memoria.app.shell.shell_log import shell_log


class UIAPIRpc(QObject):
    """单槽 RPC 包装，避免为每个 API 方法单独声明 pyqtSlot。"""

    def __init__(self, api: Any) -> None:
        super().__init__()
        self._api = api

    @pyqtSlot(result=bool)
    def startMove(self) -> bool:
        """同步槽：须在 JS mousedown 时立即调用，否则系统拖动无效。"""
        host = getattr(self._api, "_host", None)
        if host is None:
            shell_log("rpc_startMove", ok=False, reason="no_host")
            return False
        try:
            host.start_move()
            shell_log("rpc_startMove", ok=True)
            return True
        except Exception as exc:
            shell_log("rpc_startMove", ok=False, error=str(exc))
            return False

    @pyqtSlot(int)
    def setToolbarDragExclusion(self, left_x: int) -> None:
        """顶栏右侧（知识库路径、窗口按钮）不参与原生拖拽。"""
        host = getattr(self._api, "_host", None)
        if host is None or not hasattr(host, "set_toolbar_drag_exclusion"):
            return
        host.set_toolbar_drag_exclusion(left_x)

    @pyqtSlot(str, str, result=str)
    def invoke(self, method: str, args_json: str) -> str:
        if method in ("window_toggle_maximize", "window_minimize", "window_start_move"):
            shell_log("rpc_invoke", method=method, args=args_json)
        try:
            args = json.loads(args_json) if args_json else []
            if not isinstance(args, list):
                args = [args]
            fn = getattr(self._api, method, None)
            if fn is None or not callable(fn):
                return json.dumps(
                    {"status": "error", "message": f"未知方法: {method}"},
                    ensure_ascii=False,
                )
            result = fn(*args)
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps(
                {
                    "status": "error",
                    "message": str(e),
                    "trace": traceback.format_exc(limit=3),
                },
                ensure_ascii=False,
            )
