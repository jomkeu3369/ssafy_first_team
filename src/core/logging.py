import logging
import sys
from logging.handlers import TimedRotatingFileHandler

from rich.logging import RichHandler

from src.core.config import get_settings


RICH_FORMAT = "[%(filename)s:%(lineno)s] >> %(message)s"
FILE_HANDLER_FORMAT = (
    "[%(asctime)s] %(levelname)s [%(filename)s:%(funcName)s:%(lineno)s] >> %(message)s"
)
LOGGER_NAME = "localhub"


def setup_logging() -> logging.Logger:
    settings = get_settings()
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(settings.log_level.upper())

    if logger.handlers:
        return logger

    rich_handler = RichHandler(rich_tracebacks=True)
    rich_handler.setFormatter(logging.Formatter(RICH_FORMAT))
    logger.addHandler(rich_handler)

    settings.log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = TimedRotatingFileHandler(
        filename=settings.log_dir / "server.log",
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y%m%d"
    file_handler.setFormatter(logging.Formatter(FILE_HANDLER_FORMAT))
    logger.addHandler(file_handler)

    return logger


def get_logger() -> logging.Logger:
    return setup_logging()


def handle_exception(exc_type, exc_value, exc_traceback) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger = setup_logging()
    logger.error(
        "Unexpected exception",
        exc_info=(exc_type, exc_value, exc_traceback),
    )


sys.excepthook = handle_exception
