from typing import Any

from pydantic import BaseModel


class ResponseModel[T](BaseModel):
    status: bool
    message: str
    data: T | None = None


class FailedResponseModel(ResponseModel[None]):
    status: bool = False


class SuccessResponseModel[T](ResponseModel[T]):
    status: bool = True


class ValidationErrorItem(BaseModel):
    field: str
    message: str
    type: str


class ValidationFailedResponseModel(ResponseModel[list[ValidationErrorItem]]):
    status: bool = False


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {
        "model": FailedResponseModel,
        "description": "Ошибка авторизации",
    },
    409: {
        "model": FailedResponseModel,
        "description": "Конфликт идемпотентности",
    },
    422: {
        "model": ValidationFailedResponseModel,
        "description": "Ошибка валидации",
    },
}
