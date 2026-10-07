from __future__ import annotations

import atexit
import logging
import logging.handlers
import os
import queue
import re
import socket
import sys
import time
from pathlib import Path
from typing import Any, cast

import structlog

from src.core.config import settings

_listener: _Listener | None = None
_queue_handler: DroppingQueueHandler | None = None


class DroppingQueueHandler(logging.handlers.QueueHandler):
    def __init__(self, q: queue.Queue) -> None:
        super().__init__(q)
        self.dropped = 0

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        return record

    def enqueue(self, record: logging.LogRecord) -> None:
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            self.dropped += 1


class _Listener(logging.handlers.QueueListener):
    def enqueue_sentinel(self) -> None:
        self.queue.put(self._sentinel)


def _instance_id() -> str:
    """
    Уникальный id экземпляра
    """
    host = re.sub(r"[^A-Za-z0-9_-]", "-", socket.gethostname()) or "host"
    return f"{host}.{os.getpid()}"


def _resolve_filename(filename: str, per_process: bool) -> str:
    if not per_process:
        return filename
    path = Path(filename)
    return f"{path.stem}.{_instance_id()}{path.suffix}"


def _cleanup_stale_logs(log_dir: Path, filename: str, keep_days: int) -> None:
    """
    Удаляет файлы умерших экземпляров
    """
    path = Path(filename)
    cutoff = time.time() - keep_days * 86_400
    for candidate in log_dir.glob(f"{path.stem}.*{path.suffix}*"):
        try:
            if candidate.is_file() and candidate.stat().st_mtime < cutoff:
                candidate.unlink()
        except OSError:
            pass


def setup_logging(
    *,
    level: str = "INFO",
    log_dir: str | Path = "logs",
    filename: str = "app.log",
    per_process: bool = False,
    queue_size: int = 100_000,
    backup_days: int = 14,
    console: bool = False,
    access_log_level: str = "WARNING",
) -> None:
    global _listener, _queue_handler
    if _listener is not None:
        return

    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    if per_process:
        _cleanup_stale_logs(log_dir, filename, backup_days)
    filename = _resolve_filename(filename, per_process)

    # Процессоры для логов
    foreign_pre_chain: list = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.ExtraAdder(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Обработчики
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_dir / filename,
        when="midnight",
        backupCount=backup_days,
        encoding="utf-8",
        utc=True,
        delay=True,
    )
    file_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=foreign_pre_chain,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.dict_tracebacks,
                structlog.processors.JSONRenderer(),
            ],
        )
    )
    handlers: list[logging.Handler] = [file_handler]

    if console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                foreign_pre_chain=foreign_pre_chain,
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()),
                ],
            )
        )
        handlers.append(console_handler)

    # Очередь и слушатель
    log_queue: queue.Queue = queue.Queue(maxsize=queue_size)
    _queue_handler = DroppingQueueHandler(log_queue)
    _listener = _Listener(log_queue, *handlers, respect_handler_level=True)
    _listener.start()

    # Root logger
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(_queue_handler)
    root.setLevel(level.upper())

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    logging.getLogger("uvicorn.access").setLevel(access_log_level.upper())

    atexit.register(shutdown_logging)


_loggers: dict[str, Any] = {}


class _AutoLogger:
    """
    Глобальный логгер: имя берётся из модуля, где вызван logger.info(...).

    Стоимость - одно обращение к кадру стека и поиск в dict (доли микросекунды);
    сами логгеры создаются один раз на модуль и кэшируются.
    """

    __slots__ = ()

    def __getattr__(self, attr: str) -> Any:
        if attr.startswith("__"):
            raise AttributeError(attr)
        name = sys._getframe(1).f_globals.get("__name__", "__main__")
        log = _loggers.get(name)
        if log is None:
            log = _loggers[name] = structlog.get_logger(name)
        return getattr(log, attr)


logger = cast("structlog.stdlib.BoundLogger", _AutoLogger())


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    Логгер с фиксированным именем (по умолчанию - имя вызывающего модуля)
    """
    if name is None:
        name = sys._getframe(1).f_globals.get("__name__", "__main__")
    return structlog.get_logger(name)


def shutdown_logging() -> None:
    """
    Дослать всё из очереди на диск и остановить поток. Вызывать при остановке приложения
    """
    global _listener, _queue_handler
    if _listener is None:
        return
    listener, handler = _listener, _queue_handler
    _listener = _queue_handler = None
    if handler is not None and handler.dropped:
        logging.getLogger("logging").warning("log records dropped: %d", handler.dropped)
    listener.stop()
    for h in listener.handlers:
        h.close()


def dropped_logs() -> int:
    """
    Сколько записей было отброшено из-за переполнения очереди (для метрик/healthcheck)
    """
    return _queue_handler.dropped if _queue_handler else 0


setup_logging(
    level=settings.LOG_LEVEL,
    log_dir=settings.LOG_DIR,
    filename=settings.LOG_FILENAME,
    per_process=settings.LOG_PER_PROCESS,
    queue_size=settings.LOG_QUEUE_SIZE,
    backup_days=settings.LOG_BACKUP_DAYS,
    console=settings.LOG_CONSOLE,
)
