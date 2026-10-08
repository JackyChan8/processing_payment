import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from src.db.enums.payment import PaymentCurrencyEnum
from src.db.models.payment import Payment
from src.services.gateway.service import (
    ExternalPaymentEmulationGateway,
)


class TestExternalPaymentEmulationGateway(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.gateway = ExternalPaymentEmulationGateway()

        self.payment = Payment(
            amount=Decimal("100.00"),
            currency=PaymentCurrencyEnum.RUB,
            description="Test",
            metadata_={},
            webhook_url="https://example.com/webhook",
        )

    async def test_charge_returns_success_when_random_value_is_below_success_rate(
        self,
    ):
        """
        Если random < success_rate, возвращает success=True и reason=None
        """
        with (
            patch(
                "src.services.gateway.service.random.uniform",
                return_value=0,
            ) as uniform_mock,
            patch(
                "src.services.gateway.service.random.random",
                return_value=0.1,
            ),
            patch(
                "src.services.gateway.service.asyncio.sleep",
                new=AsyncMock(),
            ) as sleep_mock,
        ):
            result = await self.gateway.charge(self.payment)

        self.assertTrue(result.success)
        self.assertIsNone(result.reason)
        uniform_mock.assert_called_once()
        sleep_mock.assert_awaited_once_with(0)

    async def test_charge_returns_failure_when_random_value_is_at_or_above_success_rate(
        self,
    ):
        """
        Если random >= success_rate, возвращает success=False и причину Платеж отклонен
        """
        with (
            patch(
                "src.services.gateway.service.random.uniform",
                return_value=0,
            ),
            patch(
                "src.services.gateway.service.random.random",
                return_value=0.9,
            ),
            patch(
                "src.services.gateway.service.asyncio.sleep",
                new=AsyncMock(),
            ),
        ):
            result = await self.gateway.charge(self.payment)

        self.assertFalse(result.success)
        self.assertEqual(
            result.reason,
            "Платеж отклонен",
        )

    async def test_charge_uses_configured_delay_range(self):
        """
        Проверяет, что задержка берётся из random.uniform, min <= max, и вызывается sleep с этим значением
        """
        with (
            patch(
                "src.services.gateway.service.random.uniform",
                return_value=3.5,
            ) as uniform_mock,
            patch(
                "src.services.gateway.service.random.random",
                return_value=0.1,
            ),
            patch(
                "src.services.gateway.service.asyncio.sleep",
                new=AsyncMock(),
            ) as sleep_mock,
        ):
            await self.gateway.charge(self.payment)

        uniform_mock.assert_called_once()
        min_delay, max_delay = uniform_mock.call_args.args
        self.assertLessEqual(min_delay, max_delay)
        sleep_mock.assert_awaited_once_with(3.5)
