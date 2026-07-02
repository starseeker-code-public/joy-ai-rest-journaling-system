from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
import mongomock

from app.routes.insight_routes import register_insight_routes
from app.services.insight_service import InsightService, week_start_of, _compose
from insight_worker import make_handler, run_scheduler
from tests.conftest import register_and_login as _register_and_login

WEEK = date(2026, 6, 29)  # a Monday

EMPTY_STATS = {'entries': 0, 'avg_mood': None, 'positive': 0, 'negative': 0, 'top_tags': []}
FULL_STATS = {'entries': 4, 'avg_mood': 7.5, 'positive': 3, 'negative': 1, 'top_tags': ['work', 'gym']}
PREV_STATS = {'entries': 2, 'avg_mood': 6.0, 'positive': 1, 'negative': 1, 'top_tags': ['work']}


def _service(stats_by_week=None, active_users=None):
    analytics = MagicMock()
    if stats_by_week is not None:
        analytics.week_stats.side_effect = (
            lambda user_id, start, end: stats_by_week.get(start, EMPTY_STATS)
        )
    analytics.active_users.return_value = active_users or []
    coll = mongomock.MongoClient()['joy']['insights']
    return InsightService(collection=coll, analytics=analytics), analytics, coll


# --- week math ---

def test_week_start_of_monday_is_identity():
    assert week_start_of(date(2026, 6, 29)) == date(2026, 6, 29)


def test_week_start_of_mid_week():
    assert week_start_of(date(2026, 7, 2)) == date(2026, 6, 29)  # Thursday -> Monday


def test_week_start_of_sunday():
    assert week_start_of(date(2026, 7, 5)) == date(2026, 6, 29)


# --- composition ---

def test_compose_mentions_entries_and_mood():
    summary, highlights = _compose(FULL_STATS, PREV_STATS)
    assert 'You wrote 4 entries this week.' in summary
    assert 'Average mood was 7.5/10.' in summary
    assert 'Mood improved by 1.5 vs the previous week.' in highlights
    assert 'Most frequent topics: work, gym.' in highlights
    assert '3 of 4 analyzed entries read as positive.' in highlights


def test_compose_mood_dip_and_steady():
    dipped = dict(FULL_STATS, avg_mood=5.0)
    _, highlights = _compose(dipped, PREV_STATS)
    assert 'Mood dipped by 1 vs the previous week.' in highlights
    steady = dict(FULL_STATS, avg_mood=6.0)
    _, highlights = _compose(steady, PREV_STATS)
    assert 'Mood held steady vs the previous week.' in highlights


def test_compose_singular_entry_and_no_mood():
    stats = {'entries': 1, 'avg_mood': None, 'positive': 0, 'negative': 0, 'top_tags': []}
    summary, highlights = _compose(stats, EMPTY_STATS)
    assert summary == 'You wrote 1 entry this week.'
    assert highlights == []


def test_compose_no_prior_week_skips_delta():
    _, highlights = _compose(FULL_STATS, EMPTY_STATS)
    assert not any('previous week' in h for h in highlights)


# --- generation ---

def test_generate_for_week_stores_insight():
    service, analytics, coll = _service({WEEK: FULL_STATS, WEEK - timedelta(days=7): PREV_STATS})
    insight = service.generate_for_week('u1', WEEK)
    assert insight['period_start'] == '2026-06-29'
    assert insight['period_end'] == '2026-07-05'
    assert insight['stats'] == FULL_STATS
    assert 'id' in insight
    assert coll.count_documents({}) == 1


def test_generate_for_week_normalizes_to_monday():
    service, analytics, _ = _service({WEEK: FULL_STATS})
    insight = service.generate_for_week('u1', WEEK + timedelta(days=3))
    assert insight['period_start'] == '2026-06-29'


def test_generate_for_week_empty_week_returns_none():
    service, _, coll = _service({})
    assert service.generate_for_week('u1', WEEK) is None
    assert coll.count_documents({}) == 0


def test_generate_is_idempotent_per_week():
    service, _, coll = _service({WEEK: FULL_STATS})
    first = service.generate_for_week('u1', WEEK)
    second = service.generate_for_week('u1', WEEK)
    assert coll.count_documents({}) == 1
    assert first['id'] == second['id']


def test_generate_removes_stale_insight_when_week_empties():
    stats = {WEEK: dict(FULL_STATS)}
    service, analytics, coll = _service(stats)
    service.generate_for_week('u1', WEEK)
    assert coll.count_documents({}) == 1
    # All entries deleted: the week now aggregates to zero
    stats[WEEK] = EMPTY_STATS
    assert service.generate_for_week('u1', WEEK) is None
    assert coll.count_documents({}) == 0


def test_generate_for_active_users_counts_generated():
    stats = {WEEK: FULL_STATS}
    service, analytics, coll = _service(stats, active_users=['u1', 'u2'])
    assert service.generate_for_active_users(WEEK) == 2
    assert coll.count_documents({}) == 2


# --- worker handler & scheduler ---

def test_worker_handler_targets_week_of_payload_date():
    service = MagicMock()
    payload = {'id': 'e1', 'user_id': 'u1', 'date': '2026-06-10T08:00:00+00:00'}
    make_handler(service, delay_seconds=0)('journal.deleted', payload)
    user_id, week = service.generate_for_week.call_args.args
    assert user_id == 'u1'
    assert week == date(2026, 6, 8)  # Monday of the payload's week


def test_worker_handler_falls_back_to_today_without_date():
    from app.utils.tools import utc_today
    service = MagicMock()
    make_handler(service, delay_seconds=0)('journal.analyzed', {'id': 'e1', 'user_id': 'u1'})
    make_handler(service, delay_seconds=0)('journal.created', {'id': 'e2', 'user_id': 'u1', 'date': 'garbage'})
    for call in service.generate_for_week.call_args_list:
        assert call.args[1] == week_start_of(utc_today())


def test_worker_handler_skips_malformed():
    service = MagicMock()
    handle = make_handler(service, delay_seconds=0)
    handle('journal.analyzed', 'nope')
    handle('journal.analyzed', {'id': 'e1'})
    service.generate_for_week.assert_not_called()


def test_scheduler_generates_previous_week_and_stops():
    import threading
    from app.utils.tools import utc_today
    service = MagicMock()
    stop = threading.Event()

    def stop_after_call(week):
        stop.set()
        return 1

    service.generate_for_active_users.side_effect = stop_after_call
    run_scheduler(service, interval_seconds=0, stop_event=stop, weeks=3)
    weeks = [c.args[0] for c in service.generate_for_active_users.call_args_list]
    current = week_start_of(utc_today())
    # One full pass, oldest week first, ending at the current week
    assert weeks == [current - timedelta(days=14), current - timedelta(days=7), current]


def test_scheduler_survives_generation_failure():
    import threading
    service = MagicMock()
    stop = threading.Event()
    calls = {'n': 0}

    def fail_then_stop(week):
        calls['n'] += 1
        if calls['n'] >= 2:
            stop.set()
        raise RuntimeError('clickhouse down')

    service.generate_for_active_users.side_effect = fail_then_stop
    run_scheduler(service, interval_seconds=0, stop_event=stop)
    assert calls['n'] >= 2


# --- endpoint ---

@pytest.fixture
def app(mongo, make_app):
    analytics = MagicMock()
    analytics.week_stats.return_value = FULL_STATS
    service = InsightService(collection=mongo['insights'], analytics=analytics)
    app = make_app(lambda a: register_insight_routes(a, service=service))
    app.config['_insight_service'] = service
    return app


def test_insights_require_auth(client):
    assert client.get('/api/insights').status_code == 401


def test_insights_empty_list(client, auth_headers):
    res = client.get('/api/insights', headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json() == []


def _user_id(client, headers):
    return client.get('/auth/me', headers=headers).get_json()['id']


def test_insights_sorted_desc_and_user_scoped(client, app):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    service = app.config['_insight_service']
    uid_a = _user_id(client, headers_a)
    service.generate_for_week(uid_a, WEEK)
    service.generate_for_week(uid_a, WEEK - timedelta(days=7))

    rows = client.get('/api/insights', headers=headers_a).get_json()
    assert [r['period_start'] for r in rows] == ['2026-06-29', '2026-06-22']
    assert all('summary' in r and 'highlights' in r for r in rows)
    # User B sees none of user A's insights
    assert client.get('/api/insights', headers=headers_b).get_json() == []


def test_worker_handler_refreshes_both_weeks_on_cross_week_edit():
    service = MagicMock()
    payload = {
        'id': 'e1', 'user_id': 'u1',
        'date': '2026-07-02T10:00:00+00:00',           # this week
        'previous_date': '2026-06-10T09:00:00+00:00',  # week it moved from
    }
    make_handler(service, delay_seconds=0)('journal.updated', payload)
    weeks = sorted(c.args[1] for c in service.generate_for_week.call_args_list)
    assert weeks == [date(2026, 6, 8), date(2026, 6, 29)]  # Mondays of both weeks


def test_journal_update_publishes_previous_date():
    from app.services.journal_service import JournalService
    coll = mongomock.MongoClient()['joy']['journals']
    publisher = MagicMock()
    svc = JournalService(collection=coll, publisher=publisher)
    entry = svc.create('u1', 'T', 'body')
    publisher.reset_mock()
    updated = svc.update('u1', entry['id'], title='New')
    _, payload = publisher.publish.call_args.args
    assert payload['previous_date'] == entry['date']
    assert payload['date'] == updated['date']
    assert 'previous_date' not in updated  # API response stays clean
