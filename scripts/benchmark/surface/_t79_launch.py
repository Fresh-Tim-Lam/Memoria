# -*- coding: utf-8 -*-
"""task-79 启动器：用**运行时替换的静态根**启动真实 Memoria（WebView2），不改 `src/**`。

用途：同 build 内 A/B 比较 `app.js` 变体（淘汰压力阈值 3/4/6/关闭、或修复前提交的 app.js）。
做法：
  1. `memoria.presentation.static_server._STATIC_ROOT` 指向调用方给的静态目录副本
     （副本里只替换 `app/js/app.js`，其余文件逐字节同仓库）；
  2. `memoria.app.shell.pywebview.UI_APP_INDEX` 同步指向副本；
  3. 仍走 `memoria.app.desktop.main()`，因此 DPI / UTF-8 / frameless / WebView2 启动路径
     与正常 `python -m memoria.app.desktop` 完全一致。

用法：
  python scripts/benchmark/surface/_t79_launch.py --static-root <abs dir>

环境变量由调用方设置（MEMORIA_MODE/MEMORIA_KB/MEMORIA_CONFIG_DIR/
WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS）；本脚本只负责静态根替换后启动。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--static-root", required=True, help="替换后的 ui/static 绝对路径")
    args = ap.parse_args()

    root = Path(args.static_root).resolve()
    app_index = root / "app" / "index.html"
    if not app_index.is_file():
        print(f"[t79-launch] 非法静态根（缺 app/index.html）：{root}", file=sys.stderr)
        return 2

    # 先污染“服务端静态根”，再导入会缓存 UI_APP_INDEX 的 shell 模块。
    import memoria.presentation.static_server as ss

    ss._STATIC_ROOT = str(root)

    import memoria.app.shell.pywebview as pv

    pv.UI_APP_INDEX = app_index

    print(f"[t79-launch] static_root={root}", flush=True)
    import memoria.app.desktop as desktop

    desktop.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
