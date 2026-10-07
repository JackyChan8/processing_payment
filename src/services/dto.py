from dataclasses import dataclass

from src.db import Payment


@dataclass(slots=True)
class PaymentCreateResult:
    payment: Payment
    created: bool
