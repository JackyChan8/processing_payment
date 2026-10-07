import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core import logger, settings
from src.db import Payment, PaymentRepository, PaymentStatusEnum
from src.exceptions import processing_exception
from src.services.gateway import ExternalPaymentEmulationGateway
from src.services.webhook import WebhookSender


class PaymentProcessor:
    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        gateway: ExternalPaymentEmulationGateway,
        webhook: WebhookSender,
    ):
        self._session_maker = session_maker
        self._gateway = gateway
        self._webhook = webhook

    async def _processing_start(
        self,
        payment_id: uuid.UUID,
    ) -> Payment | None:
        async with self._session_maker() as session, session.begin():
            return await PaymentRepository(session).processing_start(
                payment_id=payment_id,
                seconds=settings.PROCESSING_SECONDS,
            )

    async def _get(
        self,
        payment_id: uuid.UUID,
    ) -> Payment | None:
        async with self._session_maker() as session:
            return await PaymentRepository(session).get(payment_id=payment_id)

    async def _processing_finish(
        self,
        payment_id: uuid.UUID,
        status: PaymentStatusEnum,
        faile_reason: str | None,
    ):
        async with self._session_maker() as session, session.begin():
            return await PaymentRepository(session).processing_finish(
                payment_id=payment_id,
                status=status,
                faile_reason=faile_reason,
            )

    async def _processing_reset(
        self,
        payment_id: uuid.UUID,
    ):
        async with self._session_maker() as session, session.begin():
            return await PaymentRepository(session).processing_reset(
                payment_id=payment_id,
            )

    async def _webhook_call(
        self,
        payment_id: uuid.UUID,
        *,
        is_delivery: bool,
    ):
        async with self._session_maker() as session, session.begin():
            return await PaymentRepository(session).webhook_call(
                payment_id=payment_id,
                is_delivery=is_delivery,
            )

    async def _notification(
        self,
        payment: Payment,
    ):
        try:
            await self._webhook.send(payment)
        except (
            processing_exception.WebhookTemporaryError,
            processing_exception.PermanentError,
        ):
            await self._webhook_call(
                payment_id=payment.id,
                is_delivery=False,
            )
            raise
        await self._webhook_call(
            payment_id=payment.id,
            is_delivery=True,
        )
        await logger.ainfo("payment.webhook_delivered")

    async def _charge(
        self,
        payment: Payment,
    ):
        started = time.perf_counter()

        try:
            result = await self._gateway.charge(payment)
            status = (
                PaymentStatusEnum.SUCCEEDED
                if result.success
                else PaymentStatusEnum.FAILED
            )
            finished = await self._processing_finish(
                payment_id=payment.id,
                status=status,
                faile_reason=result.reason,
            )
        except Exception:
            await self._processing_reset(payment.id)
            raise

        if finished is None:
            finished = await self._get(payment.id)

        await logger.ainfo(
            "payment.processed",
            status=finished.status.value,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return finished

    async def process(
        self,
        payment_id: uuid.UUID,
    ):
        payment = await self._processing_start(payment_id)

        if payment is not None:
            payment = await self._charge(payment)
        else:
            payment = await self._get(payment_id)
            if payment is None:
                raise PermissionError(f"Платеж не найден {payment_id}")
            if payment.status == PaymentStatusEnum.PENDING:
                raise processing_exception.PaymentBusyError(str(payment_id))

        if payment.webhook_delivered_at is not None:
            await logger.ainfo("payment.webhook_already_delivered")
            return
        await self._notification(payment)
