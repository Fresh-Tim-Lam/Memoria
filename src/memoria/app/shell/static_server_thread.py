"""后台静态资源 HTTP 服务（PyQt6 壳加载前端）。"""

from __future__ import annotations

import socket
import threading
from wsgiref.simple_server import WSGIServer, make_server
from memoria.presentation.static_server import create_app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class StaticServerThread:
    def __init__(self, host: str = "127.0.0.1", port: int | None = None) -> None:
        self.host = host
        self.port = port if port is not None else _free_port()
        self._server: WSGIServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def start(self) -> str:
        app = create_app()
        self._server = make_server(self.host, self.port, app)
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="memoria-static", daemon=True
        )
        self._thread.start()
        return self.url

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server = None
