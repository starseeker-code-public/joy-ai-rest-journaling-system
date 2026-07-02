"""Retry helper for workers talking to flaky backends."""
import logging
import time

logger = logging.getLogger(__name__)


def with_retry(operation, description: str, max_attempts: int = 5, base_seconds: float = 1):
    """Run `operation` with exponential backoff on failure.

    Re-raises after the last attempt so callers (e.g. event consumers) can
    nack the message instead of acking a write that never happened.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except Exception:
            if attempt == max_attempts:
                logger.exception('%s failed after %d attempts', description, max_attempts)
                raise
            delay = base_seconds * 2 ** (attempt - 1)
            logger.warning('%s failed (attempt %d/%d), retrying in %.0fs',
                           description, attempt, max_attempts, delay)
            time.sleep(delay)
