"""
Structured JSON Logger for CloudWatch — single source of truth.

Produces one JSON object per log line so CloudWatch Insights can query:
    fields @timestamp, level, correlation_id, order_id, message
    | filter level = "ERROR"
    | sort @timestamp desc

Usage:
    from shared.logger import get_logger
    log = get_logger("orders.customer")
    log.info("order_created", order_id="ord_abc", restaurant_id="rest_xyz")
"""

import json
import logging
import os
import time
from typing import Any

_STANDARD_LOG_RECORD_FIELDS = set(logging.LogRecord(
    name="",
    level=0,
    pathname="",
    lineno=0,
    msg="",
    args=(),
    exc_info=None,
).__dict__.keys())


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON for CloudWatch Insights."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": getattr(record, "service", "unknown"),
        }

        # Attach all custom structured context fields passed via extra.
        for key, val in record.__dict__.items():
            if key in _STANDARD_LOG_RECORD_FIELDS:
                continue
            if key.startswith("_"):
                continue
            if key in ("message", "asctime") or key in log_entry:
                continue
            if val is not None:
                log_entry[key] = val

        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


class StructuredLogger(logging.LoggerAdapter):
    """Logger adapter that injects context fields into every log record."""

    def process(self, msg: str, kwargs: dict) -> tuple:
        # Bound context is the base; per-call extra overrides it.
        merged = {**self.extra, **kwargs.get("extra", {})}
        kwargs["extra"] = merged
        return msg, kwargs

    def bind(self, **context: Any) -> "StructuredLogger":
        """Return a new logger with additional bound context."""
        merged = {**self.extra, **context}
        return StructuredLogger(self.logger, merged)


_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
_SERVICE_NAME = os.environ.get("SERVICE_NAME", "arrive")
_configured = False


def _configure_root() -> None:
    global _configured
    if _configured:
        return
    root = logging.getLogger()
    root.setLevel(_LOG_LEVEL)
    for h in root.handlers[:]:
        root.removeHandler(h)
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)
    _configured = True


def get_logger(name: str, **initial_context: Any) -> StructuredLogger:
    """Get a structured logger for the given module name."""
    _configure_root()
    base = logging.getLogger(name)
    ctx: dict[str, Any] = {"service": _SERVICE_NAME}
    ctx.update(initial_context)
    return StructuredLogger(base, ctx)


def extract_correlation_id(event: dict) -> str:
    """Extract a correlation ID from an API Gateway event."""
    return (
        event.get("requestContext", {}).get("requestId", "")
        or event.get("headers", {}).get("x-amzn-requestid", "")
        or "no-correlation-id"
    )


class Timer:
    """Context manager for timing code blocks (elapsed in milliseconds)."""

    def __init__(self) -> None:
        self.start: float = 0
        self.elapsed_ms: float = 0

    def __enter__(self) -> "Timer":
        self.start = time.perf_counter()
        return self

    def __exit__(self, *_: Any) -> None:
        self.elapsed_ms = round((time.perf_counter() - self.start) * 1000, 1)
