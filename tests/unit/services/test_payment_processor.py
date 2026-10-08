import unittest
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.db.enums.payment import (
    PaymentCurrencyEnum,
    PaymentStatusEnum,
)
from src.db.models.payment import Payment
from src.exceptions.processing import (
    PaymentBusyError,
    PermanentError,
    WebhookTemporaryError,
)
from src.services.gateway.dto import GatewayResult
from src.services.payment_processor.service import PaymentProcessor


class TestPaymentProcessor(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.payment = Payment(
            id=uuid.uuid4(),
            idempotency_key="key",
            request_hash="hash",
            amount=Decimal("100.00"),
            currency=PaymentCurrencyEnum.RUB,
            description="Test payment",
            metadata_={"order_id": 1},
            status=PaymentStatusEnum.PENDING,
            webhook_url="https://example.com/webhook",
        )

        self.gateway = MagicMock()
        self.webhook = MagicMock()

        self.processor = PaymentProcessor(
            MagicMock(),
            self.gateway,
            self.webhook,
        )

    async def test_process_charges_payment_and_sends_webhook(self):
        finished = self.payment
        finished.status = PaymentStatusEnum.SUCCEEDED
        finished.webhook_delivered_at = None

        self.processor._processing_start = AsyncMock(
            return_value=self.payment,
        )
        self.processor._charge = AsyncMock(
            return_value=finished,
        )
        self.processor._notification = AsyncMock()

        await self.processor.process(self.payment.id)

        self.processor._processing_start.assert_awaited_once_with(
            self.payment.id,
        )
        self.processor._charge.assert_awaited_once_with(
            self.payment,
        )
        self.processor._notification.assert_awaited_once_with(
            finished,
        )

    async def test_process_raises_when_payment_not_found(self):
        """
        Если платежа нет, выбрасывает PermissionError Платеж не найден
        """
        self.processor._processing_start = AsyncMock(return_value=None)
        self.processor._get = AsyncMock(return_value=None)

        with self.assertRaisesRegex(
            PermissionError,
            "Платеж не найден",
        ):
            await self.processor.process(self.payment.id)

    async def test_process_raises_payment_busy_for_pending_payment(self):
        """
        Если платёж уже в pending, выбрасывает PaymentBusyError
        """
        self.processor._processing_start = AsyncMock(return_value=None)
        self.processor._get = AsyncMock(return_value=self.payment)

        with self.assertRaises(PaymentBusyError):
            await self.processor.process(self.payment.id)

    async def test_process_skips_webhook_when_already_delivered(self):
        """
        Если вебхук уже доставлен, notification не вызывается
        """
        self.payment.webhook_delivered_at = MagicMock()

        self.processor._processing_start = AsyncMock(
            return_value=self.payment,
        )
        self.processor._charge = AsyncMock(
            return_value=self.payment,
        )
        self.processor._notification = AsyncMock()

        with patch(
            "src.services.payment_processor.service.logger",
            new=AsyncMock(),
        ):
            await self.processor.process(self.payment.id)

        self.processor._notification.assert_not_awaited()

    async def test_process_sends_webhook_for_already_finished_payment(self):
        """
        Если платёж уже succeeded, но вебхук не отправлен, вызывается только notification
        """
        self.payment.status = PaymentStatusEnum.SUCCEEDED
        self.payment.webhook_delivered_at = None

        self.processor._processing_start = AsyncMock(return_value=None)
        self.processor._get = AsyncMock(return_value=self.payment)
        self.processor._charge = AsyncMock()
        self.processor._notification = AsyncMock()

        await self.processor.process(self.payment.id)

        self.processor._charge.assert_not_awaited()
        self.processor._notification.assert_awaited_once_with(
            self.payment,
        )

    async def test_process_skips_charge_and_webhook_when_everything_is_done(
        self,
    ):
        """
        Если платёж обработан и вебхук доставлен, не вызываются charge и notification
        """
        self.payment.status = PaymentStatusEnum.SUCCEEDED
        self.payment.webhook_delivered_at = MagicMock()

        self.processor._processing_start = AsyncMock(return_value=None)
        self.processor._get = AsyncMock(return_value=self.payment)
        self.processor._charge = AsyncMock()
        self.processor._notification = AsyncMock()

        with patch(
            "src.services.payment_processor.service.logger",
            new=AsyncMock(),
        ):
            await self.processor.process(self.payment.id)

        self.processor._charge.assert_not_awaited()
        self.processor._notification.assert_not_awaited()

    async def test_charge_marks_payment_succeeded(self):
        """
        При успехе шлюза вызывает processing_finish со статусом SUCCEEDED
        """
        self.gateway.charge = AsyncMock(
            return_value=GatewayResult(success=True),
        )
        finished = MagicMock(status=PaymentStatusEnum.SUCCEEDED)

        self.processor._processing_finish = AsyncMock(
            return_value=finished,
        )
        self.processor._processing_reset = AsyncMock()

        with patch(
            "src.services.payment_processor.service.logger",
            new=AsyncMock(),
        ):
            result = await self.processor._charge(self.payment)

        self.assertIs(result, finished)
        self.processor._processing_finish.assert_awaited_once_with(
            payment_id=self.payment.id,
            status=PaymentStatusEnum.SUCCEEDED,
            faile_reason=None,
        )
        self.processor._processing_reset.assert_not_awaited()

    async def test_charge_marks_payment_failed_when_gateway_rejects(self):
        """
        При отказе шлюза вызывает processing_finish со статусом FAILED
        """
        self.gateway.charge = AsyncMock(
            return_value=GatewayResult(
                success=False,
                reason="declined",
            ),
        )
        finished = MagicMock(status=PaymentStatusEnum.FAILED)

        self.processor._processing_finish = AsyncMock(
            return_value=finished,
        )

        with patch(
            "src.services.payment_processor.service.logger",
            new=AsyncMock(),
        ):
            result = await self.processor._charge(self.payment)

        self.assertIs(result, finished)
        self.processor._processing_finish.assert_awaited_once_with(
            payment_id=self.payment.id,
            status=PaymentStatusEnum.FAILED,
            faile_reason="declined",
        )

    async def test_charge_resets_processing_when_gateway_raises(self):
        """
        При ошибке шлюза вызывает processing_reset и пробрасывает ошибку
        """
        self.gateway.charge = AsyncMock(
            side_effect=RuntimeError("gateway unavailable"),
        )
        self.processor._processing_reset = AsyncMock()

        with self.assertRaisesRegex(
            RuntimeError,
            "gateway unavailable",
        ):
            await self.processor._charge(self.payment)

        self.processor._processing_reset.assert_awaited_once_with(
            self.payment.id,
        )

    async def test_charge_gets_payment_when_processing_finish_returns_none(self):
        """
        Если processing_finish вернул None, получаем платеж
        """
        self.gateway.charge = AsyncMock(
            return_value=GatewayResult(success=True),
        )
        refreshed = MagicMock(status=PaymentStatusEnum.SUCCEEDED)

        self.processor._processing_finish = AsyncMock(return_value=None)
        self.processor._get = AsyncMock(return_value=refreshed)

        with patch(
            "src.services.payment_processor.service.logger",
            new=AsyncMock(),
        ):
            result = await self.processor._charge(self.payment)

        self.assertIs(result, refreshed)
        self.processor._get.assert_awaited_once_with(self.payment.id)

    async def test_notification_marks_webhook_as_delivered(self):
        """
        При успешной отправке вебхука вызывает _webhook_call с True
        """
        self.webhook.send = AsyncMock()
        self.processor._webhook_call = AsyncMock()

        with patch(
            "src.services.payment_processor.service.logger",
            new=AsyncMock(),
        ):
            await self.processor._notification(self.payment)

        self.webhook.send.assert_awaited_once_with(self.payment)
        self.processor._webhook_call.assert_awaited_once_with(
            payment_id=self.payment.id,
            is_delivery=True,
        )

    async def test_notification_resets_delivery_flag_on_temporary_error(self):
        """
        Если WebhookTemporaryError вызывается _webhook_call с False
        """
        self.webhook.send = AsyncMock(
            side_effect=WebhookTemporaryError("timeout"),
        )
        self.processor._webhook_call = AsyncMock()

        with self.assertRaises(WebhookTemporaryError):
            await self.processor._notification(self.payment)

        self.processor._webhook_call.assert_awaited_once_with(
            payment_id=self.payment.id,
            is_delivery=False,
        )

    async def test_notification_resets_delivery_flag_on_permanent_error(self):
        """
        При PermanentError вызывает _webhook_call с False
        """
        self.webhook.send = AsyncMock(
            side_effect=PermanentError("rejected"),
        )
        self.processor._webhook_call = AsyncMock()

        with self.assertRaises(PermanentError):
            await self.processor._notification(self.payment)

        self.processor._webhook_call.assert_awaited_once_with(
            payment_id=self.payment.id,
            is_delivery=False,
        )

    async def test_processing_start_delegates_to_repository(self):
        """
        Вызывает processing_start с payment_id и seconds=60
        """
        session = MagicMock()
        transaction = MagicMock()
        session.begin.return_value = transaction

        class SessionContext:
            async def __aenter__(self):
                return session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        self.processor._session_maker.return_value = SessionContext()
        repository = MagicMock()
        repository.processing_start = AsyncMock(return_value=self.payment)

        with patch(
            "src.services.payment_processor.service.PaymentRepository",
            return_value=repository,
        ):
            result = await self.processor._processing_start(self.payment.id)

        self.assertIs(result, self.payment)
        repository.processing_start.assert_awaited_once_with(
            payment_id=self.payment.id,
            seconds=60,
        )

    async def test_get_delegates_to_repository(self):
        """
        Вызывает get с payment_id
        """
        session = MagicMock()

        class SessionContext:
            async def __aenter__(self):
                return session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        self.processor._session_maker.return_value = SessionContext()
        repository = MagicMock()
        repository.get = AsyncMock(return_value=self.payment)

        with patch(
            "src.services.payment_processor.service.PaymentRepository",
            return_value=repository,
        ):
            result = await self.processor._get(self.payment.id)

        self.assertIs(result, self.payment)
        repository.get.assert_awaited_once_with(payment_id=self.payment.id)

    async def test_processing_finish_delegates_to_repository(self):
        """
        Вызывает processing_finish с id, status, faile_reason
        """
        session = MagicMock()
        transaction = MagicMock()
        session.begin.return_value = transaction

        class SessionContext:
            async def __aenter__(self):
                return session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        self.processor._session_maker.return_value = SessionContext()
        repository = MagicMock()
        repository.processing_finish = AsyncMock(return_value=self.payment)

        with patch(
            "src.services.payment_processor.service.PaymentRepository",
            return_value=repository,
        ):
            result = await self.processor._processing_finish(
                self.payment.id,
                PaymentStatusEnum.SUCCEEDED,
                None,
            )

        self.assertIs(result, self.payment)
        repository.processing_finish.assert_awaited_once_with(
            payment_id=self.payment.id,
            status=PaymentStatusEnum.SUCCEEDED,
            faile_reason=None,
        )

    async def test_processing_reset_delegates_to_repository(self):
        """
        Вызывает processing_reset с payment_id
        """
        session = MagicMock()
        transaction = MagicMock()
        session.begin.return_value = transaction

        class SessionContext:
            async def __aenter__(self):
                return session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        self.processor._session_maker.return_value = SessionContext()
        repository = MagicMock()
        repository.processing_reset = AsyncMock(return_value=self.payment)

        with patch(
            "src.services.payment_processor.service.PaymentRepository",
            return_value=repository,
        ):
            result = await self.processor._processing_reset(self.payment.id)

        self.assertIs(result, self.payment)
        repository.processing_reset.assert_awaited_once_with(
            payment_id=self.payment.id,
        )

    async def test_webhook_call_delegates_to_repository(self):
        """
        вызывает webhook_call с payment_id, is_delivery
        """
        session = MagicMock()
        transaction = MagicMock()
        session.begin.return_value = transaction

        class SessionContext:
            async def __aenter__(self):
                return session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        self.processor._session_maker.return_value = SessionContext()
        repository = MagicMock()
        repository.webhook_call = AsyncMock(return_value=self.payment)

        with patch(
            "src.services.payment_processor.service.PaymentRepository",
            return_value=repository,
        ):
            result = await self.processor._webhook_call(
                self.payment.id,
                is_delivery=True,
            )

        self.assertIs(result, self.payment)
        repository.webhook_call.assert_awaited_once_with(
            payment_id=self.payment.id,
            is_delivery=True,
        )
