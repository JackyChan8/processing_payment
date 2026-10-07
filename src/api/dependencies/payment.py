from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import PaymentOutboxRepository, PaymentRepository, get_async_session
from src.services import PaymentService


def get_payment_service(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> PaymentService:
    """
    Получение Payment Сервиса
    """
    return PaymentService(
        session=session,
        payments=PaymentRepository(session),
        outbox=PaymentOutboxRepository(session),
    )
