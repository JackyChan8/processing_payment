import unittest
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.db.enums.payment import PaymentCurrencyEnum
from src.db.models.payment import Payment
from src.exceptions.payment import (
    IdempotencyKeyConfllctError,
    PaymentNotFoundError,
)
from src.schemas.payment import PaymentCreate
from src.services.payment.service import PaymentService


class AsyncTransaction:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TestPaymentService(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session = MagicMock()

        self.session.begin.side_effect = (
            lambda: AsyncTransaction(self.session)
        )

        self.payments = MagicMock()
        self.outbox = MagicMock()

        self.service = PaymentService(
            self.session,
            self.payments,
            self.outbox,
        )

        self.payment = Payment(
            id=uuid.uuid4(),
            idempotency_key="key-1",
            request_hash="hash",
            amount=Decimal("100.00"),
            currency=PaymentCurrencyEnum.RUB,
            description="Test",
            metadata_={"order_id": 1},
            webhook_url="https://example.com/webhook",
        )

        self.data = PaymentCreate(
            amount=Decimal("100.00"),
            currency=PaymentCurrencyEnum.RUB,
            description="Test",
            metadata={"order_id": 1},
            webhook_url="https://example.com/webhook",
        )

    async def test_create_payment_creates_payment_and_outbox(self):
        """
        Создаёт платёж и outbox событие
        """
        self.payments.create = AsyncMock(
            return_value=self.payment,
        )

        self.outbox.create = AsyncMock()

        result = await self.service.create_payment(
            "key-1",
            self.data,
            "corr-1",
        )

        self.assertTrue(result.created)
        self.assertIs(result.payment, self.payment)

        self.payments.create.assert_awaited_once()

        self.outbox.create.assert_awaited_once_with(
            aggregate_id=self.payment.id,
            event_type="payment.created",
            payload={
                "payment_id": str(self.payment.id),
            },
            headers={
                "version": 1,
                "correlation_id": "corr-1",
            },
        )

    # Повторный запрос с тем же ключом и теми же данными: новый платёж не
    # создаётся, возвращается уже существующий, а в outbox ничего не добавляется.
    async def test_create_payment_returns_existing_payment_for_same_request(
        self,
    ):
        self.payments.create = AsyncMock(
            return_value=None,
        )

        self.payments.get_by_idempotency_key = AsyncMock(
            return_value=self.payment,
        )

        with patch(
            "src.services.payment.service.compute_hash",
            return_value=self.payment.request_hash,
        ):
            result = await self.service.create_payment(
                "key-1",
                self.data,
            )

        self.assertFalse(result.created)
        self.assertIs(result.payment, self.payment)

        self.outbox.create.assert_not_called()

    async def test_create_payment_raises_on_idempotency_conflict(self):
        """
        При одинаковом ключе и хеше возвращает существующий платёж и не пишет в outbox
        """
        self.payments.create = AsyncMock(
            return_value=None,
        )

        self.payments.get_by_idempotency_key = AsyncMock(
            return_value=self.payment,
        )

        with patch(
            "src.services.payment.service.compute_hash",
            return_value="different-hash",
        ):
            with self.assertRaises(IdempotencyKeyConfllctError):
                await self.service.create_payment(
                    "key-1",
                    self.data,
                )

    async def test_create_payment_raises_if_conflict_has_no_existing_payment(
        self,
    ):
        """
        При конфликте без найденного платежа выбрасывает исключение с idempotency conflict
        """
        self.payments.create = AsyncMock(
            return_value=None,
        )

        self.payments.get_by_idempotency_key = AsyncMock(
            return_value=None,
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "idempotency conflict",
        ):
            await self.service.create_payment(
                "key-1",
                self.data,
            )

    async def test_get_payment_returns_payment(self):
        """
        Возвращает платёж
        """
        self.payments.get = AsyncMock(
            return_value=self.payment,
        )

        result = await self.service.get_payment(
            self.payment.id,
        )

        self.assertIs(result, self.payment)

        self.payments.get.assert_awaited_once_with(
            self.payment.id,
        )

    async def test_get_payment_raises_when_payment_does_not_exist(self):
        """
        Если платежа нет, выбрасывает исключение PaymentNotFoundError
        """
        self.payments.get = AsyncMock(
            return_value=None,
        )

        with self.assertRaises(PaymentNotFoundError):
            await self.service.get_payment(
                uuid.uuid4(),
            )
