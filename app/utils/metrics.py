"""Prometheus metrics: per-route latency plus business counters and gauges.

Request metrics are recorded by before/after hooks; business gauges that
live in the analytics store (sentiment distribution, active users) are
pulled from ClickHouse at scrape time by a custom collector so worker
processes don't each need their own metrics endpoint.
"""
import time

import structlog
from flask import g, request, Response
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from prometheus_client.core import GaugeMetricFamily

logger = structlog.get_logger('joy.metrics')

REGISTRY = CollectorRegistry()

REQUEST_LATENCY = Histogram(
    'joy_http_request_duration_seconds',
    'HTTP request latency by route',
    ['method', 'endpoint', 'status'],
    registry=REGISTRY,
)

ENTRIES_CREATED = Counter(
    'joy_journal_entries_created_total',
    'Journal entries created via the API',
    registry=REGISTRY,
)

HABIT_CHECKS = Counter(
    'joy_habit_checks_total',
    'Habit check-ins recorded via the API',
    registry=REGISTRY,
)

GOALS_CREATED = Counter(
    'joy_goals_created_total',
    'Goals created via the API',
    registry=REGISTRY,
)


class AnalyticsCollector:
    """Scrape-time gauges backed by ClickHouse (sentiment mix, active users)."""

    def __init__(self, analytics_service):
        self.analytics = analytics_service

    def collect(self):
        try:
            rows = self.analytics.sentiment_distribution()
        except Exception:
            logger.warning('analytics collector unavailable (sentiment)', exc_info=True)
            rows = []
        sentiment = GaugeMetricFamily(
            'joy_sentiment_entries',
            'Live journal entries by latest sentiment label',
            labels=['label'],
        )
        for label, count in rows:
            sentiment.add_metric([label], count)
        yield sentiment

        active = GaugeMetricFamily(
            'joy_active_users_7d',
            'Users with journal activity in the last 7 days',
        )
        try:
            active.add_metric([], self.analytics.active_user_count(days=7))
        except Exception:
            logger.warning('analytics collector unavailable (active users)', exc_info=True)
        yield active


_analytics_collector = None


def register_metrics(app, analytics_service=None) -> None:
    global _analytics_collector
    if analytics_service is not None:
        # Replace any previous collector (tests build many apps per process)
        if _analytics_collector is not None:
            REGISTRY.unregister(_analytics_collector)
        _analytics_collector = AnalyticsCollector(analytics_service)
        REGISTRY.register(_analytics_collector)

    @app.before_request
    def start_timer():
        g.metrics_started = time.perf_counter()

    @app.after_request
    def record_request(response):
        started = getattr(g, 'metrics_started', None)
        if started is not None and request.endpoint != 'metrics':
            REQUEST_LATENCY.labels(
                method=request.method,
                # Sentinel keeps 404 floods visible without unbounded labels
                endpoint=request.endpoint or 'unmatched',
                status=response.status_code,
            ).observe(time.perf_counter() - started)
        return response

    @app.route('/metrics', methods=['GET'])
    def metrics():
        return Response(generate_latest(REGISTRY), content_type=CONTENT_TYPE_LATEST)
