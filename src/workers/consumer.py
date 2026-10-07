import asyncio
import uuid

import structlog
from faststream import FastStream
from faststream.middlewares import AckPolicy
from faststream.rabbit import Channel, RabbitBroker, RabbitMessage
from pydantic import BaseModel

from src.core import logger, settings, shutdown_logging
from src.db import async_session_maker, engine
from src.exceptions import processing_exception
from src.services import (
    ExternalPaymentEmulationGateway,
    WebhookSender,
)
from src.services.payment_processor.service import PaymentProcessor
from src.workers.rabbitmq_settings import (
    DEAD_LETTER_EXCHANGE,
    DEAD_QUEUE_ROUTING_KEY,
    PAYMENTS_EXCHANGE,
    PAYMENTS_NEW_QUEUE,
    retry_delay,
    retry_queue_name,
    setup_rabbitmq_topology,
)

broker = RabbitBroker(
    url=settings.build_rabbitmq_url(),
    default_channel=Channel(prefetch_count=settings.CONSUMER_PREFETCH),
    graceful_timeout=settings.CONSUMER_GRACEFUL_TIMEOUT_SECONDS,
    logger=None,
)

app = FastStream(broker)

webhook_sender = WebhookSender()
processor = PaymentProcessor(
    async_session_maker, ExternalPaymentEmulationGateway(), webhook_sender
)


class PaymentCreatedEvent(BaseModel):
    payment_id: uuid.UUID


async def _schedule_retry(
    event: PaymentCreatedEvent,
    msg: RabbitMessage,
    *,
    queue: str,
    attempt: int,
    error: str,
) -> None:
    """
    Публикация в очередь задержки
    """
    await broker.publish(
        event,
        queue=queue,
        persist=True,
        message_id=msg.message_id,
        correlation_id=msg.correlation_id,
        headers={"x-attempt": attempt, "x-last-error": error[:500]},
    )


async def _dead_letter(
    event: PaymentCreatedEvent,
    msg: RabbitMessage,
    *,
    attempt: int,
    error: str,
) -> None:
    """
    Публикация в Dead Letter Exchange для анализа
    """
    await broker.publish(
        event,
        exchange=DEAD_LETTER_EXCHANGE,
        routing_key=DEAD_QUEUE_ROUTING_KEY,
        persist=True,
        message_id=msg.message_id,
        correlation_id=msg.correlation_id,
        headers={"x-attempt": attempt, "x-error": error[:500]},
    )


@broker.subscriber(
    PAYMENTS_NEW_QUEUE,
    PAYMENTS_EXCHANGE,
    ack_policy=AckPolicy.REJECT_ON_ERROR,
)
async def handle_payment_new(
    event: PaymentCreatedEvent,
    msg: RabbitMessage,
):
    done = int((msg.headers or {}).get("x-attempt", 0))
    attempt = done + 1

    with structlog.contextvars.bound_contextvars(
        payment_id=str(event.payment_id),
        attempt=attempt,
        message_id=msg.message_id,
        correlation_id=msg.correlation_id,
    ):
        try:
            await processor.process(event.payment_id)
        except processing_exception.PaymentBusyError:
            await logger.ainfo("payment.busy")
            await _schedule_retry(
                event=event,
                msg=msg,
                queue=retry_queue_name(1),
                attempt=done,
                error="Платеж занят",
            )
        except processing_exception.PermanentError as exc:
            logger.error("payment.dead_lettered", reason="permanent", error=str(exc))
            await _dead_letter(event, msg, attempt=attempt, error=str(exc))

        except Exception as exc:
            if attempt >= settings.MAX_ATTEMPTS:
                logger.exception("payment.dead_lettered", reason="attempts_exhausted")
                await _dead_letter(event, msg, attempt=attempt, error=repr(exc))
            else:
                delay = retry_delay(attempt)
                logger.warning(
                    "payment.retry_scheduled", error=repr(exc), delay_seconds=delay
                )
                await _schedule_retry(
                    event,
                    msg,
                    queue=retry_queue_name(attempt),
                    attempt=attempt,
                    error=repr(exc),
                )


@app.on_startup
async def on_startup() -> None:
    """
    Настройки при запуске консюмера
    """
    await broker.connect()
    await setup_rabbitmq_topology(broker)
    await webhook_sender.start()

    await logger.ainfo(
        "consumer.started",
        prefetch=settings.CONSUMER_PREFETCH,
        max_attempts=settings.MAX_ATTEMPTS,
    )


@app.after_shutdown
async def after_shutdown() -> None:
    """
    Настройки при завершении консюмера
    """
    await webhook_sender.close()
    await engine.dispose()
    await logger.ainfo("consumer.stopped")

    shutdown_logging()


if __name__ == "__main__":
    asyncio.run(app.run())
