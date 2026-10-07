import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import payment_schemas
from src.db import (
    PaymentOutboxRepository,
    PaymentRepository,
)
from src.exceptions import payment_exception
from src.services.dto import PaymentCreateResult
from src.services.utils import compute_hash


class PaymentService:
    def __init__(
        self,
        session: AsyncSession,
        payments: PaymentRepository,
        outbox: PaymentOutboxRepository,
    ):
        self.session = session
        self.payments = payments
        self.outbox = outbox


    async def create_payment(
        self,
        idempotency_key: str,
        data: payment_schemas.PaymentCreate,
        correlation_id: str | None = None,
    ) -> PaymentCreateResult:
        # Создания хэш запроса
        request_hash = compute_hash(data)

        # Транзакция платежа
        async with self.session.begin():
            payment = await self.payments.create(
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                amount=data.amount,
                currency=data.currency,
                description=data.description,
                metadata=data.metadata,
                webhook_url=str(data.webhook_url),
            )
            if payment is not None:
                await self.outbox.create(
                    aggregate_id=payment.id,
                    event_type="payment.created",
                    payload={"payment_id": str(payment.id)},
                    headers={"version": 1, "correlation_id": correlation_id},
                )
                return PaymentCreateResult(payment, created=True)

        # Ошибка (retry)
        exist_payment = await self.payments.get_by_idempotency_key(idempotency_key)
        if exist_payment is None:
            raise RuntimeError("idempotency conflict without existing payment")

        if exist_payment.request_hash != request_hash:
            raise payment_exception.IdempotencyKeyConfllctError(idempotency_key)

        return PaymentCreateResult(exist_payment, created=False)

    async def get_payment(
        self,
        payment_id: uuid.UUID,
    ):
        payment = await self.payments.get(payment_id)
        if payment is None:
            raise payment_exception.PaymentNotFoundError()
        return payment
