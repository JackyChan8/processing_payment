from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api import api_v1, payment_errors
from src.core import logger, settings, shutdown_logging
from src.db import engine
from src.middleware import RequestLogMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await logger.ainfo("Service Successfully Launched")
        yield
    finally:
        await logger.ainfo("Service Successfully Completed")
        await engine.dispose()
        shutdown_logging()  # сбрасывает очередь на диск


app = FastAPI(
    lifespan=lifespan,
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    summary=settings.APP_SUMMARY,
    docs_url=settings.APP_SWAGGER_PATH,
    description=settings.APP_DESCRIPTION,
)

# Exceptions
payment_errors.register_exception_handlers(app)

# Middlewares
app.add_middleware(RequestLogMiddleware)

# Routers
app.include_router(api_v1.payment_router, prefix="/api/v1")
