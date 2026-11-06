"""开发态常驻批注看板注入。

为什么需要进程内注入：
- 外部 CDP 注入器要求先拿到 remote-debugging 端口，而直接运行
  ``.venv\\Scripts\\python.exe app.py`` 时端口/启动顺序并不受控；
- 开发看板必须在“直接 app.py 启动”下也稳定出现，且页面重载后自动恢复。

因此这里在 pywebview 窗口创建后启动一个 daemon 线程，直接调用
``window.evaluate_js`` 注入 ``tools/dev-annotator/annotator.js``，并周期性
调用其 ``ensureMounted``。仅在开发态启用，发布态/找不到脚本时静默跳过。
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

_LOG_LOCK = threading.Lock()


def _repo_root() -> Path | None:
    # src/memoria/app/dev_annotator.py -> repo root
    root = Path(__file__).resolve().parents[3]
    if (root / "tools" / "dev-annotator" / "annotator.js").is_file():
        return root
    # 冻结态/安装态没有 tools 目录；不要猜路径
    return None


def _log(root: Path, message: str) -> None:
    try:
        path = root / "artifacts" / "dev-annotator-inject.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_LOCK:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + message + "\n")
    except Exception:
        pass


def start_watch(window: Any, *, root: Path | None = None) -> bool:
    """启动开发看板 watchdog；返回是否已启动。

    只在开发态、看板脚本存在且未显式关闭时启动。线程不会阻止应用退出。
    """
    if os.environ.get("MEMORIA_NO_ANNOTATOR") == "1":
        return False
    try:
        from memoria.app.runtime import resolve_mode

        if resolve_mode() != "dev":
            return False
    except Exception:
        return False

    repo = root or _repo_root()
    if repo is None:
        return False
    script_path = repo / "tools" / "dev-annotator" / "annotator.js"
    try:
        script = script_path.read_text(encoding="utf-8")
    except Exception:
        return False

    expr = "(() => { " + script + " })()"
    probe = "(() => !!document.getElementById('__memoria_annotator_host__'))()"
    ensure = "(() => { window.__MEMORIA_ANNOTATOR__?.ensureMounted?.(); return true; })()"

    def _watch() -> None:
        _log(repo, "dev annotator watchdog started (in-process)")
        while True:
            try:
                if not window.evaluate_js(probe):
                    window.evaluate_js(expr)
                    _log(repo, "injected via in-process pywebview watchdog")
                else:
                    window.evaluate_js(ensure)
            except Exception:
                # 窗口尚未加载/正在关闭：继续低频重试
                pass
            time.sleep(1.5)

    threading.Thread(target=_watch, name="memoria-dev-annotator", daemon=True).start()
    return True


__all__ = ["start_watch"]
