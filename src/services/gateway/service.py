import asyncio
import random

from src.core import settings
from src.db import Payment
from src.services.gateway.dto import GatewayResult


class ExternalPaymentEmulationGateway:
    """
    Эмуляция внешнего платежного шлюза
    """

    async def charge(
        self,
        payment: Payment,
    ) -> GatewayResult:
        await asyncio.sleep(
            random.uniform(
                settings.GATEWAY_MIN_DELAY_SECONDS,
                settings.GATEWAY_MAX_DELAY_SECONDS,
            )
        )
        if random.random() < settings.GATEWAY_SUCCESS_RATE:
            return GatewayResult(success=True)
        return GatewayResult(
            success=False,
            reason="Платеж отклонен",
        )
