import asyncio
import contextlib
import signal

from faststream.rabbit import RabbitBroker

from src.core import logger, settings, shutdown_logging
from src.db import (
    PaymentOutbox,
    PaymentOutboxRepository,
    async_session_maker,
    engine,
)
from src.workers.rabbitmq_settings import (
    NEW_QUEUE_ROUTING_KEY,
    PAYMENTS_EXCHANGE,
    setup_rabbitmq_topology,
)

CLEANUP_BATCH = 5000


async def _sleep(
    stop: asyncio.Event,
    seconds: float,
):
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)


async def _publish(
    broker: RabbitBroker,
    event: PaymentOutbox,
):
    headers = {k: v for k, v in (event.headers or {}).items() if v is not None}
    headers["event_type"] = event.event_type
    await broker.publish(
        event.payload,
        exchange=PAYMENTS_EXCHANGE,
        routing_key=NEW_QUEUE_ROUTING_KEY,
        message_id=str(event.id),
        correlation_id=(event.headers or {}).get("correlation_id"),
        headers=headers,
        persist=True,  # сохранение на диск
        timeout=10,  # publish confirm
    )


async def relay_once(broker: RabbitBroker):
    async with async_session_maker() as session, session.begin():
        outbox = PaymentOutboxRepository(session)
        events = await outbox.list(settings.OUTBOX_BATCH_SIZE)
        if not events:
            return 0, 0

        results = await asyncio.gather(
            *(_publish(broker=broker, event=event) for event in events),
            return_exceptions=True,
        )

        failed = 0
        published_ids = []

        for event, result in zip(events, results, strict=True):
            if isinstance(result, BaseException):
                failed += 1
                await logger.awarning(
                    "outbox.publish_failed",
                    event_id=str(event.id),
                    error=repr(result),
                )
                await outbox.mark_failed(event.id, repr(result))
            else:
                published_ids.append(event.id)

        await outbox.mark_published(published_ids)
        return len(published_ids), failed


async def publish_loop(
    broker: RabbitBroker,
    stop: asyncio.Event,
):
    while not stop.is_set():
        try:
            published, failed = await relay_once(broker)
        except Exception:
            await logger.aexception("outbox.relay_iteration_failed")
            published, failed = 0, 1

        if published:
            await logger.adebug("outbox.published", count=published)
        if published >= settings.OUTBOX_BATCH_SIZE:
            continue
        await _sleep(stop, 1.0 if failed else settings.OUTBOX_POLL_INTERVAL_SECONDS)


async def cleanup_loop(stop: asyncio.Event):
    while not stop.is_set():
        await _sleep(stop, settings.OUTBOX_CLEANUP_INTERVAL_SECONDS)
        if stop.is_set():
            return

        try:
            total = 0
            while not stop.is_set():
                async with async_session_maker() as session, session.begin():
                    deleted = await PaymentOutboxRepository(session).delete(
                        hours=settings.OUTBOX_RETENTION_HOURS,
                        limit=CLEANUP_BATCH,
                    )
                total += deleted
                if deleted < CLEANUP_BATCH:
                    break
            if total:
                await logger.ainfo("outbox.cleaned", deleted=total)
        except Exception:
            await logger.aexception("outbox.cleanup_failed")


async def main_relay():
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    broker = RabbitBroker(url=settings.build_rabbitmq_url(), logger=None)

    try:
        async with broker:
            await setup_rabbitmq_topology(broker)
            await logger.ainfo("relay.started", batch_size=settings.OUTBOX_BATCH_SIZE)
            async with asyncio.TaskGroup() as tg:
                tg.create_task(publish_loop(broker, stop))
                tg.create_task(cleanup_loop(stop))
    finally:
        await logger.ainfo("relay.stopped")
        await engine.dispose()
        shutdown_logging()


if __name__ == "__main__":
    asyncio.run(main_relay())
