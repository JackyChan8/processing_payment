from faststream.rabbit import (
    ExchangeType,
    RabbitBroker,
    RabbitExchange,
    RabbitQueue,
)

from src.core import settings

NEW_QUEUE_ROUTING_KEY = "payments.new"
DEAD_QUEUE_ROUTING_KEY = "payments.dead"

PAYMENTS_EXCHANGE = RabbitExchange(
    "payments",
    type=ExchangeType.DIRECT,
    durable=True,
)
DEAD_LETTER_EXCHANGE = RabbitExchange(
    "payments.dlx",
    type=ExchangeType.DIRECT,
    durable=True,
)

PAYMENTS_NEW_QUEUE = RabbitQueue(
    "payments.new",
    durable=True,
    routing_key=NEW_QUEUE_ROUTING_KEY,
    arguments={
        "x-dead-letter-exchange": "payments.dlx",
        "x-dead-letter-routing-key": DEAD_QUEUE_ROUTING_KEY,
    },
)
PAYMENTS_DEAD_QUEUE = RabbitQueue(
    "payments.dead",
    durable=True,
    routing_key=DEAD_QUEUE_ROUTING_KEY,
)


def retry_delay(failed_attempts: int) -> float:
    """
    Задержка между попытками
    """
    return settings.RETRY_BASE_DELAY_SECONDS * 2 ** (failed_attempts - 1)


def retry_queue_name(failed_attempts: int) -> str:
    """
    Имя очереди с попытками
    """
    return f"payments.retry.{failed_attempts}"


def build_retry_queues() -> list[RabbitQueue]:
    """
    Очередь с задержкой
    """
    return [
        RabbitQueue(
            retry_queue_name(num),
            durable=True,
            arguments={
                "x-message-ttl": int(retry_delay(num) * 1000),
                "x-dead-letter-exchange": "payments",
                "x-dead-letter-routing-key": NEW_QUEUE_ROUTING_KEY,
            },
        )
        for num in range(1, max(settings.MAX_ATTEMPTS, 2))
    ]


async def setup_rabbitmq_topology(broker: RabbitBroker):
    """
    Объявляет топологию RabbitMQ для платежей
    """
    exchange = await broker.declare_exchange(PAYMENTS_EXCHANGE)
    dead_exchange = await broker.declare_exchange(DEAD_LETTER_EXCHANGE)

    queue = await broker.declare_queue(PAYMENTS_NEW_QUEUE)
    await queue.bind(
        exchange=exchange,
        routing_key=NEW_QUEUE_ROUTING_KEY,
    )

    dead_queue = await broker.declare_queue(PAYMENTS_DEAD_QUEUE)
    await dead_queue.bind(
        exchange=dead_exchange,
        routing_key=DEAD_QUEUE_ROUTING_KEY,
    )

    for retry_queue in build_retry_queues():
        await broker.declare_queue(retry_queue)
