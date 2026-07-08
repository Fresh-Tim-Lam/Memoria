"""桌面应用启动入口（按 MEMORIA_SHELL 选择壳）。"""

from __future__ import annotations

from memoria.app.shell import launch_shell


def main() -> None:
    launch_shell()


if __name__ == "__main__":
    main()
