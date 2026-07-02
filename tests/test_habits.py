from datetime import date, timedelta

import pytest
import mongomock

from app.routes.habit_routes import register_habit_routes
from app.services.habit_service import HabitService, daily_streak, weekly_streak
from app.utils.tools import utc_today
from tests.conftest import register_and_login as _register_and_login


@pytest.fixture
def app(mongo, make_app):
    habit_service = HabitService(collection=mongo['habits'], logs_collection=mongo['habit_logs'])
    return make_app(lambda app: register_habit_routes(app, service=habit_service))


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


@pytest.fixture
def auth_headers(client):
    return _register_and_login(client)


def _days_ago(n: int) -> str:
    # The service anchors "today" to UTC; local dates would flake near midnight.
    return (utc_today() - timedelta(days=n)).isoformat()


# --- auth gate ---

def test_list_without_token_returns_401(client):
    assert client.get('/api/habits').status_code == 401


def test_create_without_token_returns_401(client):
    assert client.post('/api/habits', json={'name': 'Run'}).status_code == 401


def test_check_without_token_returns_401(client):
    assert client.post('/api/habits/some-id/check').status_code == 401


def test_logs_without_token_returns_401(client):
    assert client.get('/api/habits/some-id/logs').status_code == 401


# --- create ---

def test_create_returns_201_with_defaults(client, auth_headers):
    res = client.post('/api/habits', json={'name': 'Run'}, headers=auth_headers)
    assert res.status_code == 201
    data = res.get_json()
    assert data['name'] == 'Run'
    assert data['frequency'] == 'daily'
    assert data['streak'] == 0
    assert 'id' in data
    assert 'created_at' in data
    assert 'user_id' in data


def test_create_weekly_habit(client, auth_headers):
    res = client.post('/api/habits', json={'name': 'Review', 'frequency': 'weekly'}, headers=auth_headers)
    assert res.status_code == 201
    assert res.get_json()['frequency'] == 'weekly'


def test_create_missing_name_returns_400(client, auth_headers):
    assert client.post('/api/habits', json={}, headers=auth_headers).status_code == 400


def test_create_blank_name_returns_400(client, auth_headers):
    assert client.post('/api/habits', json={'name': '   '}, headers=auth_headers).status_code == 400


def test_create_non_string_name_returns_400(client, auth_headers):
    assert client.post('/api/habits', json={'name': 42}, headers=auth_headers).status_code == 400


def test_create_invalid_frequency_returns_400(client, auth_headers):
    assert client.post('/api/habits', json={'name': 'X', 'frequency': 'hourly'}, headers=auth_headers).status_code == 400


def test_create_name_is_trimmed(client, auth_headers):
    res = client.post('/api/habits', json={'name': '  Run  '}, headers=auth_headers)
    assert res.get_json()['name'] == 'Run'


# --- list / get ---

def test_list_empty(client, auth_headers):
    res = client.get('/api/habits', headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json() == []


def test_list_contains_created_habits(client, auth_headers):
    client.post('/api/habits', json={'name': 'A'}, headers=auth_headers)
    client.post('/api/habits', json={'name': 'B'}, headers=auth_headers)
    data = client.get('/api/habits', headers=auth_headers).get_json()
    assert {h['name'] for h in data} == {'A', 'B'}


def test_get_one_returns_habit(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'Run'}, headers=auth_headers).get_json()
    res = client.get(f'/api/habits/{created["id"]}', headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()['id'] == created['id']


def test_get_one_unknown_id_returns_404(client, auth_headers):
    assert client.get('/api/habits/nonexistent', headers=auth_headers).status_code == 404


# --- update ---

def test_update_name(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'Old'}, headers=auth_headers).get_json()
    res = client.put(f'/api/habits/{created["id"]}', json={'name': 'New'}, headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()['name'] == 'New'


def test_update_frequency(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'X'}, headers=auth_headers).get_json()
    res = client.put(f'/api/habits/{created["id"]}', json={'frequency': 'weekly'}, headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()['frequency'] == 'weekly'


def test_update_invalid_frequency_returns_400(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'X'}, headers=auth_headers).get_json()
    assert client.put(f'/api/habits/{created["id"]}', json={'frequency': 'bogus'}, headers=auth_headers).status_code == 400


def test_update_empty_body_returns_unchanged(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'Same'}, headers=auth_headers).get_json()
    res = client.put(f'/api/habits/{created["id"]}', json={}, headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()['name'] == 'Same'


def test_update_unknown_id_returns_404(client, auth_headers):
    assert client.put('/api/habits/nonexistent', json={'name': 'X'}, headers=auth_headers).status_code == 404


# --- delete ---

def test_delete_returns_204_and_gone(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'Bye'}, headers=auth_headers).get_json()
    assert client.delete(f'/api/habits/{created["id"]}', headers=auth_headers).status_code == 204
    assert client.get(f'/api/habits/{created["id"]}', headers=auth_headers).status_code == 404


def test_delete_unknown_id_returns_404(client, auth_headers):
    assert client.delete('/api/habits/nonexistent', headers=auth_headers).status_code == 404


def test_delete_removes_logs(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'X'}, headers=auth_headers).get_json()
    client.post(f'/api/habits/{created["id"]}/check', headers=auth_headers)
    client.delete(f'/api/habits/{created["id"]}', headers=auth_headers)
    assert client.get(f'/api/habits/{created["id"]}/logs', headers=auth_headers).status_code == 404


# --- check-in ---

def test_check_defaults_to_today_and_streak_1(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'Run'}, headers=auth_headers).get_json()
    res = client.post(f'/api/habits/{created["id"]}/check', headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()['streak'] == 1


def test_check_is_idempotent_per_date(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'Run'}, headers=auth_headers).get_json()
    client.post(f'/api/habits/{created["id"]}/check', headers=auth_headers)
    client.post(f'/api/habits/{created["id"]}/check', headers=auth_headers)
    logs = client.get(f'/api/habits/{created["id"]}/logs', headers=auth_headers).get_json()
    assert len(logs) == 1


def test_check_with_explicit_date(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'Run'}, headers=auth_headers).get_json()
    res = client.post(f'/api/habits/{created["id"]}/check', json={'date': _days_ago(1)}, headers=auth_headers)
    assert res.status_code == 200
    logs = client.get(f'/api/habits/{created["id"]}/logs', headers=auth_headers).get_json()
    assert logs[0]['date'] == _days_ago(1)
    assert logs[0]['completed'] is True


def test_check_invalid_date_returns_400(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'Run'}, headers=auth_headers).get_json()
    assert client.post(f'/api/habits/{created["id"]}/check', json={'date': 'not-a-date'}, headers=auth_headers).status_code == 400
    assert client.post(f'/api/habits/{created["id"]}/check', json={'date': 20260101}, headers=auth_headers).status_code == 400


def test_check_future_date_returns_400(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'Run'}, headers=auth_headers).get_json()
    future = (utc_today() + timedelta(days=2)).isoformat()
    assert client.post(f'/api/habits/{created["id"]}/check', json={'date': future}, headers=auth_headers).status_code == 400


def test_check_one_day_ahead_is_allowed_for_tz_tolerance(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'Run'}, headers=auth_headers).get_json()
    tomorrow = (utc_today() + timedelta(days=1)).isoformat()
    assert client.post(f'/api/habits/{created["id"]}/check', json={'date': tomorrow}, headers=auth_headers).status_code == 200


def test_check_with_non_object_json_body_is_treated_as_empty(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'Run'}, headers=auth_headers).get_json()
    res = client.post(
        f'/api/habits/{created["id"]}/check',
        data='"2026-01-01"',
        content_type='application/json',
        headers=auth_headers,
    )
    # Non-object body is treated as empty → defaults to today → 200, not a crash
    assert res.status_code == 200


def test_create_with_non_object_json_body_returns_400(client, auth_headers):
    res = client.post('/api/habits', data='"Run"', content_type='application/json', headers=auth_headers)
    assert res.status_code == 400


def test_check_unknown_id_returns_404(client, auth_headers):
    assert client.post('/api/habits/nonexistent/check', headers=auth_headers).status_code == 404


# --- streaks over HTTP ---

def test_streak_counts_consecutive_days(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'Run'}, headers=auth_headers).get_json()
    for n in (0, 1, 2):
        client.post(f'/api/habits/{created["id"]}/check', json={'date': _days_ago(n)}, headers=auth_headers)
    res = client.get(f'/api/habits/{created["id"]}', headers=auth_headers)
    assert res.get_json()['streak'] == 3


def test_streak_broken_by_gap(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'Run'}, headers=auth_headers).get_json()
    for n in (0, 1, 3, 4):
        client.post(f'/api/habits/{created["id"]}/check', json={'date': _days_ago(n)}, headers=auth_headers)
    res = client.get(f'/api/habits/{created["id"]}', headers=auth_headers)
    assert res.get_json()['streak'] == 2


def test_streak_survives_unchecked_today(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'Run'}, headers=auth_headers).get_json()
    for n in (1, 2):
        client.post(f'/api/habits/{created["id"]}/check', json={'date': _days_ago(n)}, headers=auth_headers)
    res = client.get(f'/api/habits/{created["id"]}', headers=auth_headers)
    assert res.get_json()['streak'] == 2


# --- streak math (pure functions) ---

def test_daily_streak_empty():
    assert daily_streak(set(), date(2026, 7, 1)) == 0


def test_daily_streak_only_old_checks():
    today = date(2026, 7, 1)
    checked = {date(2026, 6, 1), date(2026, 6, 2)}
    assert daily_streak(checked, today) == 0


def test_daily_streak_counts_day_ahead_checkin():
    # Clients ahead of UTC may check in dated utc_today + 1; it must count.
    today = date(2026, 7, 1)
    assert daily_streak({date(2026, 7, 2)}, today) == 1
    assert daily_streak({date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 2)}, today) == 3


def test_weekly_streak_counts_week_ahead_checkin():
    today = date(2026, 7, 5)  # Sunday, ISO week 27
    checked = {date(2026, 7, 6), date(2026, 7, 1)}  # Monday week 28 + week 27
    assert weekly_streak(checked, today) == 2


def test_daily_streak_grace_day():
    today = date(2026, 7, 1)
    checked = {date(2026, 6, 30), date(2026, 6, 29)}
    assert daily_streak(checked, today) == 2


def test_daily_streak_across_month_boundary():
    today = date(2026, 7, 2)
    checked = {date(2026, 6, 29), date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 2)}
    assert daily_streak(checked, today) == 4


def test_weekly_streak_consecutive_weeks():
    today = date(2026, 7, 1)  # Wednesday, ISO week 27
    checked = {date(2026, 6, 29), date(2026, 6, 24), date(2026, 6, 17)}  # weeks 27, 26, 25
    assert weekly_streak(checked, today) == 3


def test_weekly_streak_grace_week():
    today = date(2026, 7, 1)  # week 27
    checked = {date(2026, 6, 24), date(2026, 6, 17)}  # weeks 26, 25 — nothing this week yet
    assert weekly_streak(checked, today) == 2


def test_weekly_streak_broken_by_missing_week():
    today = date(2026, 7, 1)  # week 27
    checked = {date(2026, 6, 29), date(2026, 6, 10)}  # weeks 27 and 24
    assert weekly_streak(checked, today) == 1


def test_weekly_streak_multiple_checks_one_week_count_once():
    today = date(2026, 7, 1)
    checked = {date(2026, 6, 29), date(2026, 6, 30), date(2026, 7, 1)}  # all week 27
    assert weekly_streak(checked, today) == 1


def test_weekly_streak_across_year_boundary():
    today = date(2026, 1, 7)  # ISO week 2 of 2026
    checked = {date(2026, 1, 5), date(2025, 12, 30)}  # week 2 of 2026, week 1 of 2026 (ISO)
    assert weekly_streak(checked, today) == 2


# --- ownership isolation ---

def test_user_a_cannot_list_user_b_habits(client):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    client.post('/api/habits', json={'name': 'A-private'}, headers=headers_a)
    assert client.get('/api/habits', headers=headers_b).get_json() == []


def test_user_a_cannot_read_user_b_habit(client):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    habit = client.post('/api/habits', json={'name': 'A-private'}, headers=headers_a).get_json()
    assert client.get(f'/api/habits/{habit["id"]}', headers=headers_b).status_code == 404


def test_user_a_cannot_update_user_b_habit(client):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    habit = client.post('/api/habits', json={'name': 'A-private'}, headers=headers_a).get_json()
    assert client.put(f'/api/habits/{habit["id"]}', json={'name': 'hacked'}, headers=headers_b).status_code == 404


def test_user_a_cannot_delete_user_b_habit(client):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    habit = client.post('/api/habits', json={'name': 'A-private'}, headers=headers_a).get_json()
    assert client.delete(f'/api/habits/{habit["id"]}', headers=headers_b).status_code == 404


def test_user_a_cannot_check_user_b_habit(client):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    habit = client.post('/api/habits', json={'name': 'A-private'}, headers=headers_a).get_json()
    assert client.post(f'/api/habits/{habit["id"]}/check', headers=headers_b).status_code == 404


def test_user_a_cannot_read_user_b_logs(client):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    habit = client.post('/api/habits', json={'name': 'A-private'}, headers=headers_a).get_json()
    client.post(f'/api/habits/{habit["id"]}/check', headers=headers_a)
    assert client.get(f'/api/habits/{habit["id"]}/logs', headers=headers_b).status_code == 404


# --- service-level ---

def test_storage_persists_across_service_instances():
    mongo = mongomock.MongoClient()['joy']
    s1 = HabitService(collection=mongo['habits'], logs_collection=mongo['habit_logs'])
    habit = s1.create('user-1', 'Persisted')
    s2 = HabitService(collection=mongo['habits'], logs_collection=mongo['habit_logs'])
    assert s2.get_one('user-1', habit['id']) is not None


def test_logs_collection_derived_from_habits_collection():
    mongo = mongomock.MongoClient()['joy']
    svc = HabitService(collection=mongo['habits'])
    habit = svc.create('user-1', 'Run')
    svc.check('user-1', habit['id'])
    assert svc.get_one('user-1', habit['id'])['streak'] == 1
    # Logs landed in the sibling habit_logs collection of the same database
    assert mongo['habit_logs'].count_documents({'habit_id': habit['id']}) == 1
