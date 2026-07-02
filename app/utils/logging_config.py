"""structlog configuration shared by the API and the workers.

LOG_FORMAT=json switches to machine-readable output (one JSON object per
line); anything else renders human-friendly console lines. Standard-library
loggers (pika, werkzeug, our existing logging.getLogger modules) are routed
through the same processor chain so every line comes out in one format.
"""
import logging
import os
import sys

import structlog

_SHARED_PROCESSORS = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt='iso', utc=True),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
]


def configure_logging(level: int | None = None) -> None:
    if level is None:
        level = getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper(), logging.INFO)
    json_output = os.getenv('LOG_FORMAT', 'console').lower() == 'json'
    renderer = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *_SHARED_PROCESSORS,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_SHARED_PROCESSORS,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
