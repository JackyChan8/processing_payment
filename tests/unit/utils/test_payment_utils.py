import unittest
from decimal import Decimal

from src.db.enums.payment import PaymentCurrencyEnum
from src.schemas.payment import PaymentCreate
from src.services.payment.utils import compute_hash


class TestComputeHash(unittest.TestCase):
    def make_payment(self, **overrides):
        data = {
            "amount": Decimal("100.00"),
            "currency": PaymentCurrencyEnum.RUB,
            "description": "Test payment",
            "metadata": {
                "order_id": 123,
                "customer": "alex",
            },
            "webhook_url": "https://example.com/webhook",
        }

        data.update(overrides)

        return PaymentCreate(**data)

    def test_same_data_produces_same_hash(self):
        """
        Одинаковые данные дают одинаковый хеш
        """
        first = self.make_payment()
        second = self.make_payment()

        self.assertEqual(
            compute_hash(first),
            compute_hash(second),
        )

    def test_metadata_key_order_does_not_change_hash(self):
        """
        Порядок ключей не влияет на хеш
        """
        first = self.make_payment(
            metadata={
                "a": 1,
                "b": 2,
            }
        )

        second = self.make_payment(
            metadata={
                "b": 2,
                "a": 1,
            }
        )

        self.assertEqual(
            compute_hash(first),
            compute_hash(second),
        )

    def test_different_amount_produces_different_hash(self):
        """
        Разная сумма даёт разный хеш
        """
        first = self.make_payment(
            amount=Decimal("100.00"),
        )

        second = self.make_payment(
            amount=Decimal("101.00"),
        )

        self.assertNotEqual(
            compute_hash(first),
            compute_hash(second),
        )

    def test_amount_is_normalized_to_two_decimal_places(self):
        """
        100 и 100.00 дают одинаковый хеш
        """
        first = self.make_payment(
            amount=Decimal("100"),
        )

        second = self.make_payment(
            amount=Decimal("100.00"),
        )

        self.assertEqual(
            compute_hash(first),
            compute_hash(second),
        )
