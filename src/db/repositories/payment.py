import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.db.enums.payment import PaymentCurrencyEnum
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
