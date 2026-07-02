"""Per-request log context and access logging for the Flask API.

Every request gets a request_id (honoring an inbound X-Request-ID so the
gateway or clients can correlate), bound into structlog contextvars so all
log lines emitted while handling the request carry it. A completion line
records method, path, status, duration, and user_id when authenticated.
"""
import re
import time
from uuid import uuid4

import structlog
from flask import g, request

logger = structlog.get_logger('joy.request')

# Inbound ids are attacker-controlled: cap length and charset so a crafted
# header can't bloat logs or inject terminal escapes.
_SAFE_REQUEST_ID = re.compile(r'^[A-Za-z0-9._-]{1,128}$')


def _inbound_request_id() -> str | None:
    value = request.headers.get('X-Request-ID', '')
    return value if _SAFE_REQUEST_ID.fullmatch(value) else None


def register_request_logging(app) -> None:
    @app.before_request
    def start_request():
        structlog.contextvars.clear_contextvars()
        request_id = _inbound_request_id() or str(uuid4())
        g.request_id = request_id
        g.request_started = time.perf_counter()
        structlog.contextvars.bind_contextvars(request_id=request_id)

    @app.after_request
    def log_request(response):
        started = getattr(g, 'request_started', None)
        if started is None:  # request short-circuited before our before_request
            return response
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        logger.info(
            'request',
            method=request.method,
            path=request.path,
            status=response.status_code,
            duration_ms=duration_ms,
            user_id=getattr(g, 'user_id', None),
        )
        response.headers['X-Request-ID'] = g.request_id
        return response
