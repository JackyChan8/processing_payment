import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update

from src.db.models.payment_outbox import OutboxStatusEnum, PaymentOutbox
from src.db.repositories.base import BaseRepository


class PaymentOutboxRepository(BaseRepository):
    async def create(
        self,
        *,
        aggregate_id: uuid.UUID,
        event_type: str,
        payload: dict,
        headers: dict,
    ):
        """
        Создания события
        """
        event = PaymentOutbox(
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            headers=headers,
        )
        self.session.add(event)
        await self.session.flush()
        return event


    async def list(
        self,
        limit: int,
    ) -> list[PaymentOutbox]:
        """
        Получения событий пачкой
        """
        query = (
            select(PaymentOutbox)
            .where(
                PaymentOutbox.status == OutboxStatusEnum.PENDING,
            )
            .order_by(PaymentOutbox.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(query)
        return list(result.scalars())

    async def mark_published(
        self,
        ids: list,
    ):
        """
        Установка статуса событиям опубликован
        """
        query = (
            update(PaymentOutbox)
            .where(
                PaymentOutbox.id.in_(ids),
            )
            .values(
                status=OutboxStatusEnum.PUBLISHED,
                published_at=func.now(),
            )
        )
        await self.session.execute(query)

    async def mark_failed(
        self,
        event_id: int,
        error: str,
    ):
        """
        Установка стутуса ошибки для события
        """
        query = (
            update(PaymentOutbox)
            .where(
                PaymentOutbox.id == event_id,
            )
            .values(
                attempts=PaymentOutbox.attempts + 1,
                last_error=error,
            )
        )
        await self.session.execute(query)

    async def delete(
        self,
        hours: int,
        limit: int,
    ) -> int:
        """
        Удаление событий
        """
        right_datetime = datetime.now(UTC) - timedelta(hours=hours)

        query_ids = (
            select(PaymentOutbox.id)
            .where(
                PaymentOutbox.status == OutboxStatusEnum.PUBLISHED,
                PaymentOutbox.published_at < right_datetime,
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        )

        query_main = (
            delete(PaymentOutbox)
            .where(
                PaymentOutbox.id.in_(query_ids)
            )
        )

        result = await self.session.execute(query_main)
        return result.rowcount or 0
