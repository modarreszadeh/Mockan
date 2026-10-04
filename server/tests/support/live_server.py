"""Run an ASGI app on a real Uvicorn socket in a background thread (no mocking of the network)."""

import threading
import time

import uvicorn
from starlette.types import ASGIApp


class LiveServer:
    """A Uvicorn server on `127.0.0.1:<random port>`, started and stopped from the test thread."""

    def __init__(self, app: ASGIApp, *, lifespan: str = "on") -> None:
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=0,
            log_level="warning",
            lifespan=lifespan,  # type: ignore[arg-type]  # a plain str is accepted at runtime
            ws="websockets-sansio",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, name="live-server", daemon=True)

    @property
    def port(self) -> int:
        return int(self._server.servers[0].sockets[0].getsockname()[1])

    @property
    def host(self) -> str:
        return "127.0.0.1"

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    def start(self) -> LiveServer:
        self._thread.start()
        deadline = time.monotonic() + 15
        while not self._server.started:
            if not self._thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("The live test server did not start.")
            time.sleep(0.01)
        return self

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=15)
