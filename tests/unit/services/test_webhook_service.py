import hashlib
import hmac
import unittest
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from src.db.enums.payment import (
    PaymentCurrencyEnum,
    PaymentStatusEnum,
)
from src.db.models.payment import Payment
from src.exceptions.processing import (
    WebhookRejectedError,
    WebhookTemporaryError,
)
from src.services.webhook.service import WebhookSender


class TestWebhookSender(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.payment = Payment(
            id=uuid.uuid4(),
            idempotency_key="key",
            request_hash="hash",
            amount=Decimal("100.00"),
            currency=PaymentCurrencyEnum.RUB,
            description="Test payment",
            metadata_={"order_id": 1},
            status=PaymentStatusEnum.SUCCEEDED,
            faile_reason=None,
            webhook_url="https://example.com/webhook",
            created_at=datetime(
                2026,
                1,
                1,
                tzinfo=timezone.utc,
            ),
            processed_at=datetime(
                2026,
                1,
                1,
                0,
                0,
                1,
                tzinfo=timezone.utc,
            ),
        )

        self.sender = WebhookSender()
        self.client = MagicMock()
        self.sender._client = self.client

    async def test_send_raises_when_client_not_started(self):
        """
        Без start() отправка выбрасывает исключение RuntimeError Не запущен
        """
        sender = WebhookSender()

        with self.assertRaisesRegex(RuntimeError, "Не запущен"):
            await sender.send(self.payment)

    async def test_send_success(self):
        """
        С 200 делает один POST с заголовками, id, timestamp и sha256
        """
        self.client.post = AsyncMock(
            return_value=MagicMock(status_code=200),
        )

        with patch(
            "src.services.webhook.service.time.time",
            return_value=1700000000,
        ):
            await self.sender.send(self.payment)

        self.client.post.assert_awaited_once()
        _, kwargs = self.client.post.await_args

        self.assertEqual(
            kwargs["headers"]["Content-Type"],
            "application/json",
        )
        self.assertEqual(
            kwargs["headers"]["X-Webhook-Id"],
            str(self.payment.id),
        )
        self.assertEqual(
            kwargs["headers"]["X-Webhook-Timestamp"],
            "1700000000",
        )
        self.assertTrue(
            kwargs["headers"]["X-Webhook-Signature"].startswith("sha256="),
        )

    async def test_send_treats_2xx_as_success(self):
        """
        Код 204 считается успехом
        """
        self.client.post = AsyncMock(
            return_value=MagicMock(status_code=204),
        )

        await self.sender.send(self.payment)

    async def test_send_raises_temporary_error_for_408(self):
        """
        Код 408 исключение WebhookTemporaryError
        """
        self.client.post = AsyncMock(
            return_value=MagicMock(status_code=408),
        )

        with self.assertRaises(WebhookTemporaryError):
            await self.sender.send(self.payment)

    async def test_send_raises_temporary_error_for_425(self):
        """
        Код 424 исключение WebhookTemporaryError
        """
        self.client.post = AsyncMock(
            return_value=MagicMock(status_code=425),
        )

        with self.assertRaises(WebhookTemporaryError):
            await self.sender.send(self.payment)

    async def test_send_raises_temporary_error_for_429(self):
        """
        Код 429 исключение WebhookTemporaryError
        """
        self.client.post = AsyncMock(
            return_value=MagicMock(status_code=429),
        )

        with self.assertRaises(WebhookTemporaryError):
            await self.sender.send(self.payment)

    async def test_send_raises_temporary_error_for_503(self):
        """
        Код 503 исключение WebhookTemporaryError
        """
        self.client.post = AsyncMock(
            return_value=MagicMock(status_code=503),
        )

        with self.assertRaises(WebhookTemporaryError):
            await self.sender.send(self.payment)

    async def test_send_raises_rejected_error_for_400(self):
        """
        Код 400 исключение WebhookRejectedError
        """
        self.client.post = AsyncMock(
            return_value=MagicMock(status_code=400),
        )

        with self.assertRaises(WebhookRejectedError):
            await self.sender.send(self.payment)

    async def test_send_converts_http_error_to_temporary_error(self):
        self.client.post = AsyncMock(
            side_effect=httpx.ConnectError("connection failed"),
        )

        with self.assertRaises(WebhookTemporaryError):
            await self.sender.send(self.payment)

    async def test_signature_contains_expected_hmac(self):
        """
        Подпись валидная и имеет длину 71
        """
        self.client.post = AsyncMock(
            return_value=MagicMock(status_code=200),
        )

        with patch(
            "src.services.webhook.service.time.time",
            return_value=1700000000,
        ):
            await self.sender.send(self.payment)

        _, kwargs = self.client.post.await_args
        body = kwargs["content"]
        timestamp = kwargs["headers"]["X-Webhook-Timestamp"]
        actual = kwargs["headers"]["X-Webhook-Signature"]

        from src.core import settings

        expected_digest = hmac.new(
            key=settings.WEBHOOK_SECRET.get_secret_value().encode(),
            msg=timestamp.encode() + b"." + body,
            digestmod=hashlib.sha256,
        ).hexdigest()

        self.assertEqual(
            actual,
            f"sha256={expected_digest}",
        )
        self.assertEqual(len(actual), 7 + 64)

    async def test_start_creates_http_client(self):
        """
        Создаёт httpx клиент с follow_redirects=False
        """
        fake_client = MagicMock()

        with patch(
            "src.services.webhook.service.httpx.AsyncClient",
            return_value=fake_client,
        ) as client_cls:
            await self.sender.start()

        self.assertIs(self.sender._client, fake_client)
        client_cls.assert_called_once()

        kwargs = client_cls.call_args.kwargs
        self.assertFalse(kwargs["follow_redirects"])

    async def test_close_closes_client_and_resets_it(self):
        """
        Закрывает клиент и обнуляет client
        """
        self.client.aclose = AsyncMock()

        await self.sender.close()

        self.client.aclose.assert_awaited_once()
        self.assertIsNone(self.sender._client)

    async def test_close_is_safe_when_not_started(self):
        """
        close() без start() не падает
        """
        sender = WebhookSender()

        await sender.close()

        self.assertIsNone(sender._client)

    def test_build_payload_includes_processed_at(self):
        """
        Payload содержит event, id, статус, сумму, валюту, metadata, created_at, processed_at
        """
        payload = WebhookSender._build_payload(self.payment)

        self.assertEqual(
            payload["event"],
            "payment.succeeded",
        )
        self.assertEqual(
            payload["payment_id"],
            str(self.payment.id),
        )
        self.assertEqual(
            payload["status"],
            "succeeded",
        )
        self.assertEqual(
            payload["amount"],
            "100.00",
        )
        self.assertEqual(
            payload["currency"],
            "RUB",
        )
        self.assertEqual(
            payload["metadata"],
            {"order_id": 1},
        )
        self.assertEqual(
            payload["created_at"],
            self.payment.created_at.isoformat(),
        )
        self.assertEqual(
            payload["processed_at"],
            self.payment.processed_at.isoformat(),
        )

    def test_build_payload_sets_processed_at_to_none(self):
        """
        Если processed_at=None, в payload тоже None
        """
        self.payment.processed_at = None

        payload = WebhookSender._build_payload(self.payment)

        self.assertIsNone(payload["processed_at"])
