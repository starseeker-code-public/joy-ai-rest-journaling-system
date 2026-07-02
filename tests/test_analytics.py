from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.routes.analytics_routes import register_analytics_routes
from app.services.analytics_service import AnalyticsService, COLUMNS, TABLE
from analytics_sink import make_handler
from tests.conftest import register_and_login as _register_and_login


class FakeClickHouse:
    """Records commands/inserts/queries; returns canned query rows."""

    def __init__(self, rows=None):
        self.commands = []
        self.inserts = []
        self.queries = []
        self._rows = rows or []

    def command(self, sql):
        self.commands.append(sql)

    def insert(self, table, rows, column_names=None):
        self.inserts.append((table, rows, column_names))

    def query(self, sql, parameters=None):
        self.queries.append((sql, parameters))
        return SimpleNamespace(result_rows=self._rows)


@pytest.fixture
def fake_client():
    return FakeClickHouse()


@pytest.fixture
def service(fake_client):
    return AnalyticsService(client=fake_client)


# --- schema & event recording ---

def test_ensure_schema_runs_create_table(service, fake_client):
    service.ensure_schema()
    assert len(fake_client.commands) == 1
    assert 'CREATE TABLE IF NOT EXISTS' in fake_client.commands[0]


def test_record_event_inserts_row_with_all_columns(service, fake_client):
    service.record_event('journal.created', {
        'id': 'e1', 'user_id': 'u1', 'mood': 7, 'tags': ['work'],
        'date': '2026-07-01T10:00:00+00:00',
    })
    table, rows, column_names = fake_client.inserts[0]
    assert table == TABLE
    assert column_names == COLUMNS
    row = dict(zip(column_names, rows[0]))
    assert row['event_type'] == 'journal.created'
    assert row['journal_id'] == 'e1'
    assert row['user_id'] == 'u1'
    assert row['entry_date'] == date(2026, 7, 1)
    assert row['mood'] == 7
    assert row['tags'] == ['work']
    assert row['sentiment_label'] == ''
    assert row['sentiment_score'] is None


def test_record_event_tolerates_missing_or_bad_date(service, fake_client):
    service.record_event('journal.deleted', {'id': 'e1', 'user_id': 'u1'})
    service.record_event('journal.created', {'id': 'e2', 'user_id': 'u1', 'date': 'garbage'})
    for _, rows, cols in fake_client.inserts:
        assert dict(zip(cols, rows[0]))['entry_date'] is None


def test_record_event_with_sentiment(service, fake_client):
    service.record_event('journal.analyzed', {
        'id': 'e1', 'user_id': 'u1',
        'sentiment': {'label': 'positive', 'score': 0.98},
    })
    row = dict(zip(COLUMNS, fake_client.inserts[0][1][0]))
    assert row['sentiment_label'] == 'positive'
    assert row['sentiment_score'] == 0.98
    assert row['mood'] is None
    assert row['tags'] == []


# --- aggregations ---

def test_mood_trend_builds_scoped_query_and_maps_rows():
    client = FakeClickHouse(rows=[(date(2026, 7, 1), 6.5, 2), (date(2026, 7, 2), 8.0, 1)])
    service = AnalyticsService(client=client)
    trend = service.mood_trend('u1', days=7)
    sql, params = client.queries[0]
    assert params == {'user_id': 'u1', 'days': 7}
    assert 'mood IS NOT NULL' in sql
    # Aggregates the latest state per journal, not raw events
    assert 'argMaxIf' in sql
    assert 'deleted = 0' in sql
    assert 'GROUP BY journal_id' in sql
    assert trend == [
        {'date': '2026-07-01', 'avg_mood': 6.5, 'entries': 2},
        {'date': '2026-07-02', 'avg_mood': 8.0, 'entries': 1},
    ]


def test_tag_frequency_builds_scoped_query_and_maps_rows():
    client = FakeClickHouse(rows=[('work', 5), ('life', 2)])
    service = AnalyticsService(client=client)
    tags = service.tag_frequency('u1', limit=2)
    sql, params = client.queries[0]
    assert params == {'user_id': 'u1', 'limit': 2}
    assert 'arrayJoin(tags)' in sql
    assert 'argMaxIf' in sql
    assert 'deleted = 0' in sql
    assert tags == [{'tag': 'work', 'count': 5}, {'tag': 'life', 'count': 2}]


# --- sink handler ---

def test_sink_records_created_updated_deleted_analyzed(fake_client, service):
    handle = make_handler(service)
    handle('journal.created', {'id': 'e1', 'user_id': 'u1', 'mood': 5})
    handle('journal.updated', {'id': 'e1', 'user_id': 'u1', 'mood': 6})
    handle('journal.deleted', {'id': 'e1', 'user_id': 'u1'})
    handle('journal.analyzed', {'id': 'e1', 'user_id': 'u1', 'sentiment': {'label': 'positive', 'score': 0.9}})
    assert len(fake_client.inserts) == 4


def test_sink_skips_malformed_payloads(fake_client, service):
    handle = make_handler(service)
    handle('journal.created', 'not-a-dict')
    handle('journal.created', {'user_id': 'u1'})  # no id
    handle('journal.created', {'id': 'e1'})  # no user_id
    assert fake_client.inserts == []


# --- analysis worker publishes journal.analyzed ---

def test_analysis_worker_publishes_analyzed_event():
    from analysis_worker import make_handler as make_analysis_handler
    analysis = MagicMock()
    analysis.analyze.return_value = {'label': 'positive', 'score': 0.9}
    journal = MagicMock()
    journal.set_sentiment.return_value = {'id': 'e1', 'date': '2026-07-01T10:00:00+00:00'}
    publisher = MagicMock()
    handler = make_analysis_handler(analysis, journal, publisher=publisher)
    handler('journal.created', {'id': 'e1', 'user_id': 'u1', 'content': 'Nice'})
    routing_key, payload = publisher.publish.call_args.args
    assert routing_key == 'journal.analyzed'
    assert payload == {
        'id': 'e1', 'user_id': 'u1', 'date': '2026-07-01T10:00:00+00:00',
        'sentiment': {'label': 'positive', 'score': 0.9},
    }


def test_analysis_worker_skips_publish_when_entry_gone():
    from analysis_worker import make_handler as make_analysis_handler
    analysis = MagicMock()
    analysis.analyze.return_value = {'label': 'positive', 'score': 0.9}
    journal = MagicMock()
    journal.set_sentiment.return_value = None  # entry deleted meanwhile
    publisher = MagicMock()
    handler = make_analysis_handler(analysis, journal, publisher=publisher)
    handler('journal.created', {'id': 'e1', 'user_id': 'u1', 'content': 'Nice'})
    publisher.publish.assert_not_called()


def test_analysis_worker_survives_publish_failure():
    from analysis_worker import make_handler as make_analysis_handler
    analysis = MagicMock()
    analysis.analyze.return_value = {'label': 'positive', 'score': 0.9}
    journal = MagicMock()
    journal.set_sentiment.return_value = {'id': 'e1'}
    publisher = MagicMock()
    publisher.publish.side_effect = RuntimeError('broker down')
    handler = make_analysis_handler(analysis, journal, publisher=publisher)
    handler('journal.created', {'id': 'e1', 'user_id': 'u1', 'content': 'Nice'})  # must not raise


# --- endpoints ---

@pytest.fixture
def app(mongo, make_app):
    rows_by_call = FakeClickHouse(rows=[(date(2026, 7, 1), 7.0, 3)])
    service = AnalyticsService(client=rows_by_call)
    return make_app(lambda a: register_analytics_routes(a, service=service))


def test_mood_trend_requires_auth(client):
    assert client.get('/api/analytics/mood-trend').status_code == 401


def test_tag_frequency_requires_auth(client):
    assert client.get('/api/analytics/tag-frequency').status_code == 401


def test_mood_trend_returns_rows(client, auth_headers):
    res = client.get('/api/analytics/mood-trend', headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json() == [{'date': '2026-07-01', 'avg_mood': 7.0, 'entries': 3}]


def test_mood_trend_invalid_days_returns_400(client, auth_headers):
    assert client.get('/api/analytics/mood-trend?days=abc', headers=auth_headers).status_code == 400
    assert client.get('/api/analytics/mood-trend?days=0', headers=auth_headers).status_code == 400
    assert client.get('/api/analytics/mood-trend?days=9999', headers=auth_headers).status_code == 400


def test_tag_frequency_invalid_limit_returns_400(client, auth_headers):
    assert client.get('/api/analytics/tag-frequency?limit=abc', headers=auth_headers).status_code == 400
    assert client.get('/api/analytics/tag-frequency?limit=0', headers=auth_headers).status_code == 400
    assert client.get('/api/analytics/tag-frequency?limit=101', headers=auth_headers).status_code == 400


def test_endpoints_return_503_when_clickhouse_down(mongo, make_app):
    class ExplodingClient:
        def query(self, sql, parameters=None):
            raise ConnectionError('clickhouse down')

    service = AnalyticsService(client=ExplodingClient())
    app = make_app(lambda a: register_analytics_routes(a, service=service))
    with app.test_client() as client:
        headers = _register_and_login(client)
        assert client.get('/api/analytics/mood-trend', headers=headers).status_code == 503
        assert client.get('/api/analytics/tag-frequency', headers=headers).status_code == 503
