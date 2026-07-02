import pytest
from flask import Flask, jsonify

from app.utils.metrics import (
    ENTRIES_CREATED,
    REGISTRY,
    AnalyticsCollector,
    register_metrics,
)


@pytest.fixture
def app():
    app = Flask('test')
    app.config['TESTING'] = True
    register_metrics(app)

    @app.route('/ping')
    def ping():
        return jsonify({'ok': True}), 200

    return app


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


def test_metrics_endpoint_exposes_prometheus_text(client):
    client.get('/ping')
    res = client.get('/metrics')
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert 'joy_http_request_duration_seconds' in body
    assert 'joy_journal_entries_created_total' in body


def test_request_latency_labeled_by_endpoint_and_status(client):
    client.get('/ping')
    body = client.get('/metrics').get_data(as_text=True)
    assert 'endpoint="ping"' in body
    assert 'status="200"' in body


def test_metrics_scrape_is_not_self_recorded(client):
    client.get('/metrics')
    body = client.get('/metrics').get_data(as_text=True)
    assert 'endpoint="metrics"' not in body


def test_entries_counter_increments(client):
    before = ENTRIES_CREATED._value.get()
    ENTRIES_CREATED.inc()
    assert ENTRIES_CREATED._value.get() == before + 1


def test_analytics_collector_yields_gauges():
    class FakeAnalytics:
        def sentiment_distribution(self):
            return [('positive', 7), ('negative', 2)]

        def active_user_count(self, days=7):
            return 3

    families = list(AnalyticsCollector(FakeAnalytics()).collect())
    by_name = {f.name: f for f in families}
    sentiment = by_name['joy_sentiment_entries']
    assert {(s.labels['label'], s.value) for s in sentiment.samples} == {('positive', 7.0), ('negative', 2.0)}
    active = by_name['joy_active_users_7d']
    assert active.samples[0].value == 3.0


def test_analytics_collector_survives_backend_outage():
    class Exploding:
        def sentiment_distribution(self):
            raise ConnectionError('down')

        def active_user_count(self, days=7):
            raise ConnectionError('down')

    families = list(AnalyticsCollector(Exploding()).collect())
    assert {f.name for f in families} == {'joy_sentiment_entries', 'joy_active_users_7d'}
    assert all(not f.samples or f.samples == [] for f in families if f.name == 'joy_sentiment_entries')


def test_register_metrics_with_analytics_is_rebindable(app):
    class FakeAnalytics:
        def sentiment_distribution(self):
            return []

        def active_user_count(self, days=7):
            return 0

    other = Flask('other')
    register_metrics(other, analytics_service=FakeAnalytics())
    # Re-registering with a new service must not raise (collector replaced)
    another = Flask('another')
    register_metrics(another, analytics_service=FakeAnalytics())


def test_unmatched_routes_use_sentinel_endpoint(client):
    client.get('/definitely/not/a/route')
    body = client.get('/metrics').get_data(as_text=True)
    assert 'endpoint="unmatched"' in body
    assert 'status="404"' in body
