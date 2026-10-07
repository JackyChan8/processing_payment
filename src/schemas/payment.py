import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
)

from src.db import PaymentCurrencyEnum, PaymentStatusEnum


class PaymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    amount: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=2, description="Сумма")]
    currency: PaymentCurrencyEnum = Field(description="Валюта")
    description: str = Field(min_length=1, max_length=500, description="Описание")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Метаданные")
    webhook_url: HttpUrl = Field(description="Webhook URL")

    @field_validator("metadata")
    @classmethod
    def _limit_metadata(cls, v: dict[str, Any]) -> dict[str, Any]:
        """
        Проверка на лимита на размер
        """
        if len(json.dumps(v, ensure_ascii=False).encode()) > 16 * 1024:
            raise ValueError("metadata must be <= 16 KB")
        return v

class PaymentAccepted(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: uuid.UUID = Field(
        validation_alias=AliasChoices("id", "payment_id"),
        description="ID Платежа",
    )
    status: PaymentStatusEnum = Field(description="Статус платежа")
    created_at: datetime = Field(description="Дата создания")


class PaymentInfoGet(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: uuid.UUID = Field(
        validation_alias=AliasChoices("id", "payment_id"),
        description="ID Платежа",
    )
    idempotency_key: str = Field(description="Идемпотентный ключ")
    amount: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=2, description="Сумма")]
    currency: PaymentCurrencyEnum = Field(description="Валюта")
    description: str = Field(min_length=1, max_length=500, description="Описание")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("metadata_", "metadata"),
        description="Метаданные",
    )
    status: PaymentStatusEnum = Field(description="Статус платежа")
    webhook_url: HttpUrl = Field(description="Webhook URL")
    created_at: datetime = Field(description="Дата создания")
    processed_at: datetime | None = Field(default=None, description="Дата обработки")
