import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status

from src.api.dependencies import get_payment_service, security_dependencies
from src.core import logger
from src.schemas import payment_schemas, response_schemas
from src.services import PaymentService

router = APIRouter(
    prefix="/payments",
    tags=["Платежи"],
    dependencies=[
        Depends(security_dependencies.verify_api_key),
    ]
)


@router.post(
    path="",
    description="Создание платежа",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=response_schemas.SuccessResponseModel[
        payment_schemas.PaymentAccepted
    ],
    responses=response_schemas.ERROR_RESPONSES,
)
async def payment_create(
    request: Request,
    response: Response,
    data: payment_schemas.PaymentCreate,
    payment_service: Annotated[PaymentService, Depends(get_payment_service)],
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=255
    ),
):
    correlation_id = getattr(request.state, "request_id", None)
    result = await payment_service.create_payment(
        data=data,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )

    await logger.ainfo(
        "payment.accepted",
        payment_id=str(result.payment.id),
        replayed=not result.created,
    )

    if result.created:
        message = "Платеж принят"
    else:
        message = "Платеж уже был создан ранее"
        response.headers["Idempotent-Replayed"] = "true"

    return response_schemas.SuccessResponseModel[payment_schemas.PaymentAccepted](
        message=message,
        data=payment_schemas.PaymentAccepted.model_validate(result.payment),
    )


@router.get(
    path="/{payment_id}",
    description="Получение информации о платеже",
    status_code=status.HTTP_200_OK,
    response_model=response_schemas.SuccessResponseModel[
        payment_schemas.PaymentInfoGet
    ],
    responses={
        **response_schemas.ERROR_RESPONSES,
        404: {
            "model": response_schemas.FailedResponseModel,
        }
    },
)
async def payment_info(
    payment_id: uuid.UUID,
    payment_service: Annotated[PaymentService, Depends(get_payment_service)],
):
    payment = await payment_service.get_payment(payment_id)

    return response_schemas.SuccessResponseModel[payment_schemas.PaymentInfoGet](
        message="Платеж успешно получен",
        data=payment_schemas.PaymentInfoGet.model_validate(payment),
    )
