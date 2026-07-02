import atexit
import os
from dotenv import load_dotenv

load_dotenv()

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from app.routes.journal_routes import register_journal_routes
from app.routes.auth_routes import register_auth_routes
from app.routes.habit_routes import register_habit_routes
from app.routes.goal_routes import register_goal_routes
from app.routes.analytics_routes import register_analytics_routes
from app.routes.insight_routes import register_insight_routes
from app.routes.health_routes import register_health_routes
from app.routes.usage_routes import register_usage_routes
from app.utils.logging_config import configure_logging
from app.utils.request_logging import register_request_logging
from app.utils.metrics import register_metrics
from app.services.analytics_service import AnalyticsService
from app.utils.tracing import configure_tracing, instrument_flask, instrument_pika
from app.services.storage_service import StorageService
from app.utils.event_publisher import EventPublisher
from app.services.search_service import SearchService
from app.utils.redis_rate_limiter import RedisRateLimiter
from app.utils.user_cache import UserCache

DEFAULT_SECRET_KEY = 'dev-secret-key-change-me-in-production-12345'


def _is_debug() -> bool:
    return os.getenv('DEBUG', 'True').lower() in ('true', '1', 't')


def _check_secret_key() -> None:
    if _is_debug():
        return
    secret = os.getenv('SECRET_KEY')
    if not secret or secret == DEFAULT_SECRET_KEY:
        raise RuntimeError(
            'SECRET_KEY must be set to a non-default value when DEBUG is disabled. '
            'Generate a strong key (>= 32 bytes) and set it via the environment.'
        )


def create_app() -> Flask:
    _check_secret_key()
    configure_logging()
    configure_tracing('joy-api')
    instrument_pika()
    app = Flask(__name__)
    instrument_flask(app)
    register_request_logging(app)
    # Trust one proxy hop (the nginx gateway) so request.remote_addr is the
    # real client IP — otherwise the login rate limiter would collapse every
    # gateway user into a single bucket.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    publisher = EventPublisher()
    atexit.register(publisher.close)
    # Client construction is lazy: no connection happens until a search runs
    register_journal_routes(
        app,
        publisher=publisher,
        search_service=SearchService(),
        storage_service=StorageService(),
    )
    # Redis-backed limiter/cache (both fail open if Redis is down)
    register_auth_routes(
        app,
        login_limiter=RedisRateLimiter(max_attempts=5, window_seconds=15 * 60),
        user_cache=UserCache(),
    )
    register_habit_routes(app)
    register_goal_routes(app)
    analytics = AnalyticsService()
    register_analytics_routes(app, service=analytics)
    register_insight_routes(app)
    register_health_routes(app)
    register_usage_routes(app)
    register_metrics(app, analytics_service=analytics)

    return app


app = create_app()


if __name__ == '__main__':
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 5000))
    app.run(host=host, port=port, debug=_is_debug())
