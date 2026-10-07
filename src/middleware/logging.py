import re
import time
import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.core.logging import logger

_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")

class RequestLogMiddleware:
    """
    Чистый ASGI middleware.
    Привязывает request_id/method/path к контексту: они автоматически попадут
    в каждый лог, написанный во время обработки запроса.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        for key, value in scope["headers"]:
            if key == b"x-request-id":
                candidate = value.decode("latin-1")
                if _REQUEST_ID_RE.fullmatch(candidate):
                    request_id = candidate
                break

        scope.setdefault("state", {})["request_id"] = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=scope["method"],
            path=scope["path"],
        )

        status = 500
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)["x-request-id"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # Трейсбек необработанного исключения залогирует сам uvicorn
            logger.info(
                "request_completed",
                status=status,
                duration_ms=round((time.perf_counter() - start) * 1000, 2),
            )
            structlog.contextvars.clear_contextvars()
