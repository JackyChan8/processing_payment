from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarHTTPException

from src.core import logger
from src.exceptions import payment_exception
from src.schemas import response_schemas


def failed(
    status_code: int,
    message: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = response_schemas.FailedResponseModel(message=message)
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content=body.model_dump(mode="json"),
    )


def register_exception_handlers(app: FastAPI):
    @app.exception_handler(payment_exception.AppError)
    async def app_error_handler(request: Request, exc: payment_exception.AppError):
        return failed(exc.status_code, exc.message)

    @app.exception_handler(StarHTTPException)
    async def http_error_handler(request: Request, exc: StarHTTPException):
        return failed(exc.status_code, str(exc.detail), headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        items = [
            response_schemas.ValidationErrorItem(
                field=".".join(str(part) for part in err["loc"]),
                message=err["msg"],
                type=err["type"],
            )
            for err in exc.errors()
        ]
        body = response_schemas.ValidationFailedResponseModel(message="Ошибка валидации запроса", data=items)
        return JSONResponse(status_code=422, content=body.model_dump(mode="json"))

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        request_id = request.scope.get("state", {}).get("request_id")
        logger.exception(
            "unhandled_error",
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )

        headers = {"x-request-id": request_id} if request_id else None
        return failed(500, "Внутренняя ошибка сервера", headers=headers)
