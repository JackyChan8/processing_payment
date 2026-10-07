__all__ = (
    "logger",
    "settings",
    "shutdown_logging",
)

from src.core.config import settings
from src.core.logging import logger, shutdown_logging
