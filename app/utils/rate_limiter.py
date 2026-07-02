from collections import defaultdict, deque
from threading import Lock
from time import monotonic


class RateLimiter:
    """In-memory token-bucket-style rate limiter.

    Not durable across restarts and not shared across workers. Production
    uses RedisRateLimiter (app/utils/redis_rate_limiter.py); this remains
    for tests and Redis-less local runs.
    """

    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._buckets: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        with self._lock:
            now = monotonic()
            cutoff = now - self.window_seconds
            bucket = self._buckets[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_attempts:
                return False
            bucket.append(now)
            return True
