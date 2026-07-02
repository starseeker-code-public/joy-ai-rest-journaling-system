"""Aggregated health: the API plus every backing service it depends on."""
import logging
import os
from functools import lru_cache
from flask import jsonify

logger = logging.getLogger(__name__)


# Clients are cached: /health is polled every few seconds (gateway
# healthcheck, monitors) and per-request client construction would churn
# connections. lru_cache also keeps construction lazy and import-light.

@lru_cache(maxsize=1)
def _redis_client():
    from app.utils.redis_rate_limiter import default_redis_client
    return default_redis_client()


@lru_cache(maxsize=1)
def _opensearch_client():
    from app.services.search_service import _default_client
    return _default_client()


@lru_cache(maxsize=1)
def _clickhouse_client():
    from app.services.analytics_service import _default_client
    return _default_client()


def _check_mongo():
    from app.db import get_db
    get_db().command('ping')


def _check_redis():
    _redis_client().ping()


def _check_rabbitmq():
    import pika
    url = os.getenv('RABBITMQ_URL', 'amqp://joy:joy@localhost:5673/')
    params = pika.URLParameters(url)
    params.socket_timeout = 2
    params.blocked_connection_timeout = 2
    connection = pika.BlockingConnection(params)
    connection.close()


def _check_opensearch():
    if not _opensearch_client().ping():
        raise ConnectionError('opensearch ping failed')


def _check_clickhouse():
    _clickhouse_client().command('SELECT 1')


DEFAULT_CHECKS = {
    'mongo': _check_mongo,
    'redis': _check_redis,
    'rabbitmq': _check_rabbitmq,
    'opensearch': _check_opensearch,
    'clickhouse': _check_clickhouse,
}


def register_health_routes(app, checks=None):
    if checks is None:
        checks = DEFAULT_CHECKS

    @app.route('/health', methods=['GET'])
    def health():
        services = {}
        for name, check in checks.items():
            try:
                check()
                services[name] = 'healthy'
            except Exception:
                logger.warning('health check failed for %s', name, exc_info=True)
                services[name] = 'unhealthy'
        degraded = any(state != 'healthy' for state in services.values())
        body = {'status': 'degraded' if degraded else 'healthy', 'services': services}
        return jsonify(body), 200
