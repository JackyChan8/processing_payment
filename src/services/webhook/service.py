import hashlib
import hmac
import json
import time

import httpx

from src.core import settings
from src.db.models.payment import Payment
from src.exceptions import processing_exception


class WebhookSender:
    """
    Вебхук
    """

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def start(self):
        """
        Настройка при старте
        """
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.WEBHOOK_TIMEOUT_SECONDS, connect=2.0),
            limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
            follow_redirects=False,
        )

    async def close(self):
        """
        Закрытия клиента
        """
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def _build_payload(payment: Payment):
        return {
            "event": f"payment.{payment.status.value}",
            "payment_id": str(payment.id),
            "status": payment.status.value,
            "amount": f"{payment.amount:.2f}",
            "currency": payment.currency.value,
            "description": payment.description,
            "metadata": payment.metadata_,
            "faile_reason": payment.faile_reason,
            "created_at": payment.created_at.isoformat(),
            "processed_at": payment.processed_at.isoformat()
            if payment.processed_at
            else None,
        }

    async def send(
        self,
        payment: Payment,
    ):
        """
        Отправка
        """
        if self._client is None:
            raise RuntimeError("Не запущен")

        body = json.dumps(
            self._build_payload(payment),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        timestamp = str(int(time.time()))
        signature = hmac.new(
            key=settings.WEBHOOK_SECRET.get_secret_value().encode(),
            msg=timestamp.encode() + b"." + body,
            digestmod=hashlib.sha256,
        ).hexdigest()

        try:
            response = await self._client.post(
                payment.webhook_url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Id": str(payment.id),
                    "X-Webhook-Timestamp": timestamp,
                    "X-Webhook-Signature": f"sha256={signature}",
                },
            )

        except httpx.HTTPError as exc:
            raise processing_exception.WebhookTemporaryError(
                f"{type(exc).__name__}: {exc}"
            ) from exc

        code = response.status_code
        if 200 <= code < 300:
            return
        if code in {408, 425, 429} or code >= 500:
            raise processing_exception.WebhookTemporaryError(
                f"Сбой при доставке уведомления {code}"
            )
        raise processing_exception.WebhookRejectedError(
            f"Сервер отклоняет вебхук {code}"
        )
