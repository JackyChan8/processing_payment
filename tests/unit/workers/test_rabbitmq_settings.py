import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.workers.rabbitmq_settings import (
    DEAD_LETTER_EXCHANGE,
    DEAD_QUEUE_ROUTING_KEY,
    NEW_QUEUE_ROUTING_KEY,
    PAYMENTS_DEAD_QUEUE,
    PAYMENTS_EXCHANGE,
    PAYMENTS_NEW_QUEUE,
    build_retry_queues,
    retry_delay,
    retry_queue_name,
    setup_rabbitmq_topology,
)


class TestRabbitMqSettings(unittest.TestCase):
    def test_retry_delay_uses_exponential_backoff(self):
        """
        Задержка повтора растёт как base * 2^(attempt-1)
        """
        with patch(
            "src.workers.rabbitmq_settings.settings.RETRY_BASE_DELAY_SECONDS",
            5,
        ):
            self.assertEqual(
                retry_delay(1),
                5,
            )

            self.assertEqual(
                retry_delay(2),
                10,
            )

            self.assertEqual(
                retry_delay(3),
                20,
            )

    def test_retry_queue_name(self):
        """
        Имя очереди повтора: payments.retry.<attempt>
        """
        self.assertEqual(
            retry_queue_name(1),
            "payments.retry.1",
        )

        self.assertEqual(
            retry_queue_name(3),
            "payments.retry.3",
        )

    def test_build_retry_queues_creates_queue_for_each_attempt(self):
        """
        При MAX_ATTEMPTS=4 создаётся 3 очереди с TTL 5000, 10000, 20000
        """
        with (
            patch(
                "src.workers.rabbitmq_settings.settings.MAX_ATTEMPTS",
                4,
            ),
            patch(
                "src.workers.rabbitmq_settings.settings.RETRY_BASE_DELAY_SECONDS",
                5,
            ),
        ):
            queues = build_retry_queues()

        self.assertEqual(
            len(queues),
            3,
        )

        self.assertEqual(
            [queue.name for queue in queues],
            [
                "payments.retry.1",
                "payments.retry.2",
                "payments.retry.3",
            ],
        )

        self.assertEqual(
            queues[0].arguments["x-message-ttl"],
            5000,
        )

        self.assertEqual(
            queues[1].arguments["x-message-ttl"],
            10000,
        )

        self.assertEqual(
            queues[2].arguments["x-message-ttl"],
            20000,
        )

    def test_build_retry_queues_creates_at_least_one_queue(self):
        """
        При MAX_ATTEMPTS=1 всё равно создаётся одна очередь payments.retry.1
        """
        with patch(
            "src.workers.rabbitmq_settings.settings.MAX_ATTEMPTS",
            1,
        ):
            queues = build_retry_queues()

        self.assertEqual(
            [queue.name for queue in queues],
            ["payments.retry.1"],
        )


class TestSetupRabbitMqTopology(unittest.IsolatedAsyncioTestCase):
    async def test_setup_declares_exchanges_queues_and_bindings(self):
        """
        Объявляет exchanges и retry-очереди: new, dead. new, dead bind, retry только объявляются
        """
        exchange = MagicMock()
        dead_exchange = MagicMock()
        declared_queues = {}

        async def declare_queue(queue):
            declared_queues[queue.name] = MagicMock(bind=AsyncMock())
            return declared_queues[queue.name]

        broker = MagicMock()
        broker.declare_exchange = AsyncMock(
            side_effect=[exchange, dead_exchange],
        )
        broker.declare_queue = AsyncMock(side_effect=declare_queue)

        with patch(
            "src.workers.rabbitmq_settings.settings.MAX_ATTEMPTS",
            3,
        ):
            await setup_rabbitmq_topology(broker)

        self.assertEqual(
            [call.args[0] for call in broker.declare_exchange.await_args_list],
            [PAYMENTS_EXCHANGE, DEAD_LETTER_EXCHANGE],
        )
        self.assertEqual(
            list(declared_queues),
            [
                PAYMENTS_NEW_QUEUE.name,
                PAYMENTS_DEAD_QUEUE.name,
                "payments.retry.1",
                "payments.retry.2",
            ],
        )

        declared_queues[PAYMENTS_NEW_QUEUE.name].bind.assert_awaited_once_with(
            exchange=exchange,
            routing_key=NEW_QUEUE_ROUTING_KEY,
        )
        declared_queues[PAYMENTS_DEAD_QUEUE.name].bind.assert_awaited_once_with(
            exchange=dead_exchange,
            routing_key=DEAD_QUEUE_ROUTING_KEY,
        )
        declared_queues["payments.retry.1"].bind.assert_not_awaited()
        declared_queues["payments.retry.2"].bind.assert_not_awaited()
