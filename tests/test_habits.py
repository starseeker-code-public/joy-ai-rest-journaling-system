import pytest
import mongomock
from flask import Flask
from app.routes.habit_routes import register_habit_routes
from app.routes.auth_routes import register_auth_routes
from app.services.habit_service import HabitService, VALID_FREQUENCIES
from app.services.user_service import UserService
from app.utils.rate_limiter import RateLimiter


@pytest.fixture
def service():
    coll = mongomock.MongoClient()['joy']['habits']
    return HabitService(collection=coll)


@pytest.fixture
def app():
    mongo = mongomock.MongoClient()['joy']
    app = Flask(__name__)
    app.config['TESTING'] = True
    user_service = UserService(collection=mongo['users'])
    habit_service = HabitService(collection=mongo['habits'])
    permissive = RateLimiter(max_attempts=1000, window_seconds=60)
    register_auth_routes(app, user_service=user_service, login_limiter=permissive)
    register_habit_routes(app, service=habit_service)
    return app


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


def _register_and_login(client, email='a@example.com', password='secret123'):
    client.post('/auth/register', json={'email': email, 'password': password})
    token = client.post('/auth/login', json={'email': email, 'password': password}).get_json()['token']
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def auth_headers(client):
    return _register_and_login(client)


# --- creation: happy path ---

def test_create_returns_entry_with_all_fields(service):
    habit = service.create('user-1', 'Meditate', target_freq='daily')
    assert habit['id']
    assert habit['user_id'] == 'user-1'
    assert habit['name'] == 'Meditate'
    assert habit['target_freq'] == 'daily'
    assert 'created_at' in habit


def test_create_strips_whitespace_from_name(service):
    habit = service.create('user-1', '  Read books  ')
    assert habit['name'] == 'Read books'


def test_create_defaults_target_freq_to_daily(service):
    habit = service.create('user-1', 'Walk')
    assert habit['target_freq'] == 'daily'


def test_create_accepts_weekly(service):
    habit = service.create('user-1', 'Long run', target_freq='weekly')
    assert habit['target_freq'] == 'weekly'


def test_create_persists_to_collection(service):
    habit = service.create('user-1', 'Stretch')
    stored = service.collection.find_one({'id': habit['id']})
    assert stored is not None
    assert stored['user_id'] == 'user-1'
    assert stored['name'] == 'Stretch'


def test_create_returns_no_internal_id(service):
    habit = service.create('user-1', 'Stretch')
    assert '_id' not in habit


# --- creation: validation ---

def test_create_empty_name_raises(service):
    with pytest.raises(ValueError, match='name'):
        service.create('user-1', '')


def test_create_whitespace_only_name_raises(service):
    with pytest.raises(ValueError, match='name'):
        service.create('user-1', '   ')


def test_create_non_string_name_raises(service):
    with pytest.raises(ValueError, match='name'):
        service.create('user-1', 123)


def test_create_invalid_target_freq_raises(service):
    with pytest.raises(ValueError, match='target_freq'):
        service.create('user-1', 'Read', target_freq='hourly')


# --- ownership ---

def test_create_preserves_distinct_user_ids(service):
    a = service.create('user-a', 'Habit A')
    b = service.create('user-b', 'Habit B')
    assert a['user_id'] != b['user_id']
    assert service.collection.find_one({'id': a['id']})['user_id'] == 'user-a'
    assert service.collection.find_one({'id': b['id']})['user_id'] == 'user-b'


# --- schema sanity ---

def test_valid_frequencies_constant_pin():
    """Catch silent expansion of allowed frequencies — schema changes should be deliberate."""
    assert VALID_FREQUENCIES == {'daily', 'weekly'}


# --- list ---

def test_get_all_empty(service):
    assert service.get_all('user-1') == []


def test_get_all_returns_user_habits(service):
    service.create('user-1', 'A')
    service.create('user-1', 'B')
    result = service.get_all('user-1')
    assert {h['name'] for h in result} == {'A', 'B'}


def test_get_all_isolates_users(service):
    service.create('user-a', 'Mine')
    service.create('user-b', 'Theirs')
    a_habits = service.get_all('user-a')
    assert len(a_habits) == 1
    assert a_habits[0]['name'] == 'Mine'


# --- get one ---

def test_get_one_returns_entry(service):
    created = service.create('user-1', 'Run')
    fetched = service.get_one('user-1', created['id'])
    assert fetched['id'] == created['id']
    assert fetched['name'] == 'Run'


def test_get_one_unknown_id_returns_none(service):
    assert service.get_one('user-1', 'nonexistent') is None


def test_get_one_foreign_user_returns_none(service):
    created = service.create('user-a', 'Private')
    assert service.get_one('user-b', created['id']) is None


# --- update ---

def test_update_name(service):
    created = service.create('user-1', 'Old')
    updated = service.update('user-1', created['id'], name='New')
    assert updated['name'] == 'New'
    assert updated['target_freq'] == 'daily'


def test_update_target_freq(service):
    created = service.create('user-1', 'Run', target_freq='daily')
    updated = service.update('user-1', created['id'], target_freq='weekly')
    assert updated['target_freq'] == 'weekly'
    assert updated['name'] == 'Run'


def test_update_partial_preserves_other_fields(service):
    created = service.create('user-1', 'Keep', target_freq='weekly')
    updated = service.update('user-1', created['id'], name='Changed')
    assert updated['name'] == 'Changed'
    assert updated['target_freq'] == 'weekly'


def test_update_empty_body_returns_unchanged(service):
    created = service.create('user-1', 'Same', target_freq='weekly')
    updated = service.update('user-1', created['id'])
    assert updated['name'] == 'Same'
    assert updated['target_freq'] == 'weekly'


def test_update_unknown_id_returns_none(service):
    assert service.update('user-1', 'nonexistent', name='X') is None


def test_update_foreign_user_returns_none(service):
    created = service.create('user-a', 'Private')
    assert service.update('user-b', created['id'], name='hijacked') is None
    # Original entry unchanged
    assert service.get_one('user-a', created['id'])['name'] == 'Private'


def test_update_invalid_name_raises(service):
    created = service.create('user-1', 'OK')
    with pytest.raises(ValueError, match='name'):
        service.update('user-1', created['id'], name='   ')


def test_update_invalid_target_freq_raises(service):
    created = service.create('user-1', 'OK')
    with pytest.raises(ValueError, match='target_freq'):
        service.update('user-1', created['id'], target_freq='hourly')


# --- delete ---

def test_delete_returns_true(service):
    created = service.create('user-1', 'Bye')
    assert service.delete('user-1', created['id']) is True


def test_delete_entry_is_gone(service):
    created = service.create('user-1', 'Gone')
    service.delete('user-1', created['id'])
    assert service.get_one('user-1', created['id']) is None


def test_delete_unknown_id_returns_false(service):
    assert service.delete('user-1', 'nonexistent') is False


def test_delete_foreign_user_returns_false(service):
    created = service.create('user-a', 'Protected')
    assert service.delete('user-b', created['id']) is False
    # Entry still there for the rightful owner
    assert service.get_one('user-a', created['id']) is not None


# =============================================================================
# HTTP-layer tests (using Flask test client)
# =============================================================================

# --- auth gate ---

def test_http_list_without_token_returns_401(client):
    assert client.get('/api/habits').status_code == 401


def test_http_create_without_token_returns_401(client):
    assert client.post('/api/habits', json={'name': 'X'}).status_code == 401


def test_http_get_one_without_token_returns_401(client):
    assert client.get('/api/habits/some-id').status_code == 401


def test_http_update_without_token_returns_401(client):
    assert client.put('/api/habits/some-id', json={'name': 'X'}).status_code == 401


def test_http_delete_without_token_returns_401(client):
    assert client.delete('/api/habits/some-id').status_code == 401


# --- list ---

def test_http_list_empty(client, auth_headers):
    res = client.get('/api/habits', headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json() == []


def test_http_list_contains_created(client, auth_headers):
    client.post('/api/habits', json={'name': 'Meditate'}, headers=auth_headers)
    client.post('/api/habits', json={'name': 'Read'}, headers=auth_headers)
    data = client.get('/api/habits', headers=auth_headers).get_json()
    assert {h['name'] for h in data} == {'Meditate', 'Read'}


# --- create ---

def test_http_create_returns_201(client, auth_headers):
    res = client.post('/api/habits', json={'name': 'Run', 'target_freq': 'weekly'}, headers=auth_headers)
    assert res.status_code == 201
    data = res.get_json()
    assert data['name'] == 'Run'
    assert data['target_freq'] == 'weekly'
    assert 'id' in data
    assert 'created_at' in data
    assert 'user_id' in data


def test_http_create_defaults_target_freq(client, auth_headers):
    res = client.post('/api/habits', json={'name': 'Stretch'}, headers=auth_headers)
    assert res.get_json()['target_freq'] == 'daily'


def test_http_create_missing_name_returns_400(client, auth_headers):
    assert client.post('/api/habits', json={}, headers=auth_headers).status_code == 400


def test_http_create_invalid_target_freq_returns_400(client, auth_headers):
    res = client.post('/api/habits', json={'name': 'X', 'target_freq': 'hourly'}, headers=auth_headers)
    assert res.status_code == 400


# --- get one ---

def test_http_get_one_returns_entry(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'X'}, headers=auth_headers).get_json()
    res = client.get(f'/api/habits/{created["id"]}', headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()['id'] == created['id']


def test_http_get_one_unknown_returns_404(client, auth_headers):
    assert client.get('/api/habits/nonexistent', headers=auth_headers).status_code == 404


# --- update ---

def test_http_update(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'Old'}, headers=auth_headers).get_json()
    res = client.put(f'/api/habits/{created["id"]}', json={'name': 'New'}, headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()['name'] == 'New'


def test_http_update_unknown_returns_404(client, auth_headers):
    assert client.put('/api/habits/nonexistent', json={'name': 'X'}, headers=auth_headers).status_code == 404


def test_http_update_invalid_target_freq_returns_400(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'X'}, headers=auth_headers).get_json()
    res = client.put(f'/api/habits/{created["id"]}', json={'target_freq': 'hourly'}, headers=auth_headers)
    assert res.status_code == 400


# --- delete ---

def test_http_delete_returns_204(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'Bye'}, headers=auth_headers).get_json()
    assert client.delete(f'/api/habits/{created["id"]}', headers=auth_headers).status_code == 204


def test_http_delete_then_get_returns_404(client, auth_headers):
    created = client.post('/api/habits', json={'name': 'Gone'}, headers=auth_headers).get_json()
    client.delete(f'/api/habits/{created["id"]}', headers=auth_headers)
    assert client.get(f'/api/habits/{created["id"]}', headers=auth_headers).status_code == 404


def test_http_delete_unknown_returns_404(client, auth_headers):
    assert client.delete('/api/habits/nonexistent', headers=auth_headers).status_code == 404


# --- ownership at HTTP layer ---

def test_http_user_a_cannot_list_user_b_habits(client):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    client.post('/api/habits', json={'name': 'A-private'}, headers=headers_a)
    assert client.get('/api/habits', headers=headers_b).get_json() == []


def test_http_user_a_cannot_read_user_b_habit(client):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    a = client.post('/api/habits', json={'name': 'A-private'}, headers=headers_a).get_json()
    assert client.get(f'/api/habits/{a["id"]}', headers=headers_b).status_code == 404


def test_http_user_a_cannot_delete_user_b_habit(client):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    a = client.post('/api/habits', json={'name': 'A-private'}, headers=headers_a).get_json()
    assert client.delete(f'/api/habits/{a["id"]}', headers=headers_b).status_code == 404
