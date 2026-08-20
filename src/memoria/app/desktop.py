"""桌面应用启动入口（按 MEMORIA_SHELL 选择壳）。"""

from __future__ import annotations

import sys

from memoria.app.shell import launch_shell


class _SafeStream:
    """UTF-8 容错输出流：frozen/windowed 下 stdout/stderr 编码为 cp1252
    且不可 reconfigure，print 中文会 UnicodeEncodeError 导致启动崩溃；
    此流固定 UTF-8 + 写失败静默丢弃，永不出错。"""

    def __init__(self, real=None):
        self._real = real

    def write(self, s):
        if s is None:
            return 0
        if self._real is not None:
            try:
                self._real.write(s)
            except Exception:
                pass
        return len(s)

    def flush(self):
        if self._real is not None:
            try:
                self._real.flush()
            except Exception:
                pass

    def reconfigure(self, **kwargs):  # noqa: ARG002
        pass

    def isatty(self):
        return False

    def writable(self):
        return True

    @property
    def encoding(self):
        return "utf-8"


def _force_utf8_stdio() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        try:
            if stream is not None:
                stream.reconfigure(encoding="utf-8", errors="replace")
                continue
        except Exception:
            pass
        # windowed 模式 stdout/stderr 不可 reconfigure：替换为容错流
        try:
            setattr(sys, name, _SafeStream(stream))
        except Exception:
            pass


def main() -> None:
    _force_utf8_stdio()
    launch_shell()


if __name__ == "__main__":
    main()
