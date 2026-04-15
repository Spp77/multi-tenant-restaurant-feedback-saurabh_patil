"""
src/utils/logger.py
Structured JSON logger used across all modules.
Every log line is a JSON object — easy to ingest into AWS CloudWatch / Datadog.
"""
import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Formats every log record as a single-line JSON string."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        # Attach any extra fields passed via `extra={}` in the log call
        for key, value in record.__dict__.items():
            if key not in (
                "args", "asctime", "created", "exc_info", "exc_text",
                "filename", "funcName", "id", "levelname", "levelno",
                "lineno", "module", "msecs", "message", "msg", "name",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "thread", "threadName",
            ):
                log_obj[key] = value

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, default=str)


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Factory that returns a named logger with JSON output to stdout.

    Usage:
        from src.utils.logger import get_logger
        logger = get_logger(__name__)
        logger.info("Feedback received", extra={"tenant_id": "pizza-palace-123"})
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)

    logger.setLevel(level)
    logger.propagate = False   # avoid duplicate output from root logger
    return logger
