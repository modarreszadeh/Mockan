"""structlog configuration (JSON or console) with bound context variables (arch §12.2)."""

import logging
import sys
from typing import Any

import structlog

from mockan.infrastructure.masking import mask_event_dict


def configure_logging(level: str = "INFO", log_format: str = "json") -> None:
    """Configure structlog (and the stdlib root logger) once at process start."""
    numeric = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
    logging.basicConfig(level=numeric, format="%(message)s", stream=sys.stdout, force=True)
    renderer: Any = (
        structlog.dev.ConsoleRenderer()
        if log_format == "console"
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            mask_event_dict,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )


def bind_log_context(**values: Any) -> None:
    """Bind `developer`, `service`, `source`, `rule_id`, `trace_id`... to every later log line."""
    structlog.contextvars.bind_contextvars(**values)


def clear_log_context() -> None:
    structlog.contextvars.clear_contextvars()
