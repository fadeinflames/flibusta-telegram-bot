import logging
import os
import sys
from datetime import datetime, UTC
from logging.handlers import RotatingFileHandler

from json_log_formatter import JSONFormatter, _json_serializable

from src import config

# Silence noisy HTTP libraries
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)


class CustomJSONFormatter(JSONFormatter):
    def to_json(self, record):
        try:
            return self.json_lib.dumps(record, ensure_ascii=False, default=_json_serializable)
        except (TypeError, ValueError, OverflowError):
            try:
                return self.json_lib.dumps(record)
            except (TypeError, ValueError, OverflowError):
                return "{}"

    def json_record(self, message, extra, record):
        result = {}
        if "time" not in extra:
            result["time"] = datetime.now(UTC)

        result["levelname"] = record.levelname
        result["message"] = message
        result.update(extra)

        if record.exc_info:
            result["exc_info"] = self.formatException(record.exc_info)

        return result


_json_formatter = CustomJSONFormatter()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger with JSON file + stream handlers.

    Handlers are added only once per logger name, preventing duplicates
    when the function is called multiple times with the same name.
    """
    logger = logging.getLogger(name)

    # Avoid adding handlers twice
    if logger.handlers:
        return logger

    logger.propagate = False

    # ── File handler with rotation ──
    os.makedirs(config.LOGS_DIR, exist_ok=True)
    file_handler = RotatingFileHandler(
        filename=config.LOG_FILE,
        encoding="utf-8",
        maxBytes=10 * 1024 * 1024,  # 10 MB per file
        backupCount=5,
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(_json_formatter)
    logger.addHandler(file_handler)

    # ── Console handler ──
    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(_json_formatter)
    logger.addHandler(stream_handler)

    return logger
