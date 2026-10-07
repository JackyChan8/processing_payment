import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.enums.outbox import OutboxStatusEnum
from src.db.models.base import BaseModel


class PaymentOutbox(BaseModel):
    """
    Outbox события для платежей
    """

    __tablename__ = "payments_outbox"

    aggregate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    headers: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    status: Mapped[OutboxStatusEnum] = mapped_column(
        Enum(
            OutboxStatusEnum,
            name="payments_outbox_status_enum",
            native_enum=True,
        ),
        nullable=False,
        default=OutboxStatusEnum.PENDING,
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index(
            "ix_payments_outbox_pending",
            "id",
            postgresql_where=(status == OutboxStatusEnum.PENDING),
        ),
    )
