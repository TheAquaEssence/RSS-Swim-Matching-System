"""HTTP host validation for the loopback-only desktop backend."""

from __future__ import annotations

from collections.abc import Sequence

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})


def _valid_port(value: str) -> bool:
    if not value.isascii() or not value.isdecimal():
        return False
    port = int(value)
    return 1 <= port <= 65535


def is_allowed_loopback_host(value: str) -> bool:
    """Accept an exact supported loopback hostname and optional valid port."""

    value = value.lower()
    if value in LOOPBACK_HOSTS:
        return True
    host, separator, port = value.rpartition(":")
    return separator == ":" and host in LOOPBACK_HOSTS and _valid_port(port)


class LoopbackHostMiddleware:
    """Reject HTTP requests whose Host header is not a supported loopback host.

    Starlette's TestClient uses the synthetic host ``testserver``. It is
    accepted only when the ASGI peer is TestClient's synthetic ``testclient``
    peer, so no production HTTP client can opt into the testing exception by
    changing its Host header.
    """

    def __init__(
        self,
        app: ASGIApp,
        security_headers: Sequence[tuple[str, str]] = (),
    ) -> None:
        self.app = app
        self.security_headers = tuple(security_headers)

    @staticmethod
    def _is_testclient(scope: Scope, host: str) -> bool:
        client = scope.get("client")
        return bool(client and client[0] == "testclient" and host == "testserver")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        host = Headers(scope=scope).get("host", "")
        if is_allowed_loopback_host(host) or self._is_testclient(scope, host):
            await self.app(scope, receive, send)
            return

        response = JSONResponse(
            {"ok": False, "error": "Invalid request host"},
            status_code=400,
            headers=dict(self.security_headers),
        )
        await response(scope, receive, send)
