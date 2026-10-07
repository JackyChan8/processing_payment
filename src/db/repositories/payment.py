import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.db.enums.payment import PaymentCurrencyEnum, PaymentStatusEnum
from src.db.models.payment import Payment
from src.db.repositories.base import BaseRepository


class PaymentRepository(BaseRepository):
    async def create(
        self,
        *,
        idempotency_key: str,
        request_hash: str,
        amount: Decimal,
        currency: PaymentCurrencyEnum,
        description: str,
        metadata: dict,
        webhook_url: str,
    ) -> Payment | None:
        """
        Создание платежа
        """
        query = (
            pg_insert(Payment)
            .values(
                id=uuid.uuid4(),
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                amount=amount,
                currency=currency,
                description=description,
                metadata_=metadata,
                webhook_url=webhook_url,
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
            .returning(Payment)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(
        self,
        key: str,
    ) -> Payment | None:
        """
        Получения по ключу
        """
        query = (
            select(Payment)
            .where(
                Payment.idempotency_key == key,
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get(
        self,
        payment_id: uuid.UUID,
    ) -> Payment | None:
        """
        Получения платежа
        """
        return await self.session.get(Payment, payment_id)

    async def processing_start(
        self,
        payment_id: uuid.UUID,
        seconds: int,
    ) -> Payment | None:
        """
        Начало обработки платежа
        """
        query = (
            update(Payment)
            .where(
                Payment.id == payment_id,
                Payment.status == PaymentStatusEnum.PENDING,
                or_(
                    Payment.processing_started_at.is_(None),
                    Payment.processing_started_at < func.now() - timedelta(seconds=seconds),
                ),
            )
            .values(
                processing_started_at=func.now(),
            )
            .returning(Payment)
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def processing_reset(
        self,
        payment_id: uuid.UUID,
    ):
        """
        Сброс обработки платежа в случае ошибки
        """
        query = (
            update(Payment)
            .where(
                Payment.id == payment_id,
                Payment.status == PaymentStatusEnum.PENDING,
            )
            .values(
                processing_started_at=None,
            )
        )
        await self.session.execute(query)

    async def processing_finish(
        self,
        payment_id: uuid.UUID,
        status: PaymentStatusEnum,
        faile_reason: str | None,
    ) -> Payment | None:
        """
        Конец обработки платежа
        """
        query = (
            update(Payment)
            .where(
                Payment.id == payment_id,
                Payment.status == PaymentStatusEnum.PENDING,
            )
            .values(
                status=status,
                faile_reason=faile_reason,
                processed_at=func.now(),
            )
            .returning(Payment)
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def webhook_call(
        self,
        payment_id: uuid.UUID,
        *,
        is_delivery: bool,
    ):
        """
        Вызов вебхука
        """
        values = {
            "webhook_attempts": Payment.webhook_attempts + 1,
        }
        if is_delivery:
            values["webhook_delivered_at"] = func.now()

        query = (
            update(Payment)
            .where(
                Payment.id == payment_id,
            )
            .values(**values)
        )
        await self.session.execute(query)
