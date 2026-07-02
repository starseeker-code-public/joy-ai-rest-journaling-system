"""Short-TTL Redis cache for /auth/me user lookups."""
import json
import logging

from app.utils.redis_rate_limiter import default_redis_client

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 60


class UserCache:
    """Caches safe user docs (no password_hash) by user id.

    TTL-based only: user profiles are immutable today, so 60s of staleness
    is acceptable and no invalidation hooks are needed yet. Fails open on
    Redis errors — a cache outage must not break authentication.
    """

    def __init__(self, client=None, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self.client = client if client is not None else default_redis_client()
        self.ttl_seconds = ttl_seconds

    def _key(self, user_id: str) -> str:
        return f'user:{user_id}'

    def get(self, user_id: str) -> dict | None:
        try:
            raw = self.client.get(self._key(user_id))
        except Exception:
            logger.exception('User cache unavailable (get)')
            return None
        return json.loads(raw) if raw else None

    def set(self, user_id: str, user: dict) -> None:
        try:
            self.client.set(self._key(user_id), json.dumps(user), ex=self.ttl_seconds)
        except Exception:
            logger.exception('User cache unavailable (set)')
