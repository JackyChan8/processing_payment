import uuid

from sqlalchemy import select

from src.db.models.payment_outbox import PaymentOutbox, OutboxStatusEnum
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
