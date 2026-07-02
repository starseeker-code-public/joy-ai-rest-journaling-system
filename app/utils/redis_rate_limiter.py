"""Redis-backed fixed-window rate limiter, shared across workers/restarts."""
import logging
import os

logger = logging.getLogger(__name__)


def default_redis_client():
    import redis
    return redis.Redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6380/0'))


class RedisRateLimiter:
    """Drop-in replacement for the in-memory RateLimiter (same allow() interface).

    Counts attempts in a fixed window per key. Fails open when Redis is
    unreachable: an outage of the limiter backend must not lock every user
    out of login.
    """

    def __init__(self, max_attempts: int, window_seconds: int, client=None):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.client = client if client is not None else default_redis_client()

    def allow(self, key: str) -> bool:
        redis_key = f'ratelimit:{key}'
        try:
            pipe = self.client.pipeline()
            pipe.incr(redis_key)
            # nx: only set the TTL when the key has none, so the window
            # doesn't slide forward on every attempt (and a crash between
            # commands can't leave an immortal counter).
            pipe.expire(redis_key, self.window_seconds, nx=True)
            count, _ = pipe.execute()
        except Exception:
            logger.exception('Rate limiter backend unavailable; failing open')
            return True
        return count <= self.max_attempts
