from unittest.mock import MagicMock
import pytest
import mongomock
from flask import Flask, jsonify
from app.routes.journal_routes import register_journal_routes
from app.routes.auth_routes import register_auth_routes
from app.services.journal_service import JournalService
from app.services.user_service import UserService
from app.utils.rate_limiter import RateLimiter


@pytest.fixture
def app():
    mongo = mongomock.MongoClient()['joy']
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['_test_journals_collection'] = mongo['journals']
    user_service = UserService(collection=mongo['users'])
    journal_service = JournalService(collection=mongo['journals'])
    permissive = RateLimiter(max_attempts=1000, window_seconds=60)
    register_auth_routes(app, user_service=user_service, login_limiter=permissive)
    register_journal_routes(app, service=journal_service)

    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({'status': 'healthy'}), 200

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


# --- auth gate ---

def test_list_without_token_returns_401(client):
    assert client.get('/api/journals').status_code == 401


def test_create_without_token_returns_401(client):
    assert client.post('/api/journals', json={'title': 'X'}).status_code == 401


def test_get_one_without_token_returns_401(client):
    assert client.get('/api/journals/some-id').status_code == 401


def test_update_without_token_returns_401(client):
    assert client.put('/api/journals/some-id', json={'title': 'X'}).status_code == 401


def test_delete_without_token_returns_401(client):
    assert client.delete('/api/journals/some-id').status_code == 401


def test_invalid_token_returns_401(client):
    assert client.get('/api/journals', headers={'Authorization': 'Bearer bad.token'}).status_code == 401


# --- list ---

def test_list_empty(client, auth_headers):
    res = client.get('/api/journals', headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json() == []


def test_list_contains_created_entries(client, auth_headers):
    client.post('/api/journals', json={'title': 'A'}, headers=auth_headers)
    client.post('/api/journals', json={'title': 'B'}, headers=auth_headers)
    data = client.get('/api/journals', headers=auth_headers).get_json()
    assert len(data) == 2
    assert {e['title'] for e in data} == {'A', 'B'}


# --- create ---

def test_create_returns_201_with_all_fields(client, auth_headers):
    res = client.post('/api/journals', json={'title': 'Day 1', 'content': 'Good day'}, headers=auth_headers)
    assert res.status_code == 201
    data = res.get_json()
    assert data['title'] == 'Day 1'
    assert data['content'] == 'Good day'
    assert 'id' in data
    assert 'date' in data
    assert 'user_id' in data


def test_create_content_defaults_to_empty(client, auth_headers):
    res = client.post('/api/journals', json={'title': 'No content'}, headers=auth_headers)
    assert res.status_code == 201
    assert res.get_json()['content'] == ''


def test_create_missing_title_returns_400(client, auth_headers):
    assert client.post('/api/journals', json={'content': 'No title'}, headers=auth_headers).status_code == 400


def test_create_empty_body_returns_400(client, auth_headers):
    assert client.post('/api/journals', json={}, headers=auth_headers).status_code == 400


# --- get single ---

def test_get_one_returns_entry(client, auth_headers):
    created = client.post('/api/journals', json={'title': 'Entry'}, headers=auth_headers).get_json()
    res = client.get(f'/api/journals/{created["id"]}', headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()['id'] == created['id']


def test_get_one_unknown_id_returns_404(client, auth_headers):
    assert client.get('/api/journals/nonexistent-id', headers=auth_headers).status_code == 404


# --- update ---

def test_update_title_and_content(client, auth_headers):
    created = client.post('/api/journals', json={'title': 'Old', 'content': 'Old'}, headers=auth_headers).get_json()
    res = client.put(f'/api/journals/{created["id"]}', json={'title': 'New', 'content': 'New'}, headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data['title'] == 'New'
    assert data['content'] == 'New'


def test_update_partial_preserves_other_fields(client, auth_headers):
    created = client.post('/api/journals', json={'title': 'Keep', 'content': 'Keep'}, headers=auth_headers).get_json()
    res = client.put(f'/api/journals/{created["id"]}', json={'title': 'Changed'}, headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data['title'] == 'Changed'
    assert data['content'] == 'Keep'


def test_update_unknown_id_returns_404(client, auth_headers):
    assert client.put('/api/journals/nonexistent-id', json={'title': 'X'}, headers=auth_headers).status_code == 404


# --- delete ---

def test_delete_returns_204(client, auth_headers):
    created = client.post('/api/journals', json={'title': 'Bye'}, headers=auth_headers).get_json()
    assert client.delete(f'/api/journals/{created["id"]}', headers=auth_headers).status_code == 204


def test_delete_entry_is_gone(client, auth_headers):
    created = client.post('/api/journals', json={'title': 'Gone'}, headers=auth_headers).get_json()
    client.delete(f'/api/journals/{created["id"]}', headers=auth_headers)
    assert client.get(f'/api/journals/{created["id"]}', headers=auth_headers).status_code == 404


def test_delete_unknown_id_returns_404(client, auth_headers):
    assert client.delete('/api/journals/nonexistent-id', headers=auth_headers).status_code == 404


# --- sentiment endpoint ---

def test_get_sentiment_without_token_returns_401(client):
    assert client.get('/api/journals/some-id/sentiment').status_code == 401


def test_get_sentiment_unknown_id_returns_404(client, auth_headers):
    assert client.get('/api/journals/nonexistent/sentiment', headers=auth_headers).status_code == 404


def test_get_sentiment_returns_202_while_pending(client, auth_headers):
    created = client.post('/api/journals', json={'title': 'X', 'content': 'hi'}, headers=auth_headers).get_json()
    res = client.get(f'/api/journals/{created["id"]}/sentiment', headers=auth_headers)
    assert res.status_code == 202
    assert res.get_json() == {'status': 'pending'}


def test_get_sentiment_returns_200_after_analysis(client, auth_headers, app):
    created = client.post('/api/journals', json={'title': 'X', 'content': 'Good day'}, headers=auth_headers).get_json()
    # Simulate the worker writing back via the shared collection
    coll = app.config['_test_journals_collection']
    coll.update_one(
        {'id': created['id']},
        {'$set': {'ai.sentiment': {'label': 'positive', 'score': 0.95, 'analyzed_at': '2026-06-10T00:00:00Z'}}},
    )
    res = client.get(f'/api/journals/{created["id"]}/sentiment', headers=auth_headers)
    assert res.status_code == 200
    body = res.get_json()
    assert body['label'] == 'positive'
    assert body['score'] == 0.95
    assert body['analyzed_at'] == '2026-06-10T00:00:00Z'


def test_get_sentiment_user_a_cannot_read_user_b(client):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    a_entry = client.post('/api/journals', json={'title': 'A'}, headers=headers_a).get_json()
    assert client.get(f'/api/journals/{a_entry["id"]}/sentiment', headers=headers_b).status_code == 404


# --- ownership isolation ---

def test_user_a_cannot_list_user_b_entries(client):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    client.post('/api/journals', json={'title': 'A-private'}, headers=headers_a)
    res = client.get('/api/journals', headers=headers_b)
    assert res.status_code == 200
    assert res.get_json() == []


def test_user_a_cannot_read_user_b_entry(client):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    a_entry = client.post('/api/journals', json={'title': 'A-private'}, headers=headers_a).get_json()
    assert client.get(f'/api/journals/{a_entry["id"]}', headers=headers_b).status_code == 404


def test_user_a_cannot_update_user_b_entry(client):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    a_entry = client.post('/api/journals', json={'title': 'A-private'}, headers=headers_a).get_json()
    assert client.put(f'/api/journals/{a_entry["id"]}', json={'title': 'hacked'}, headers=headers_b).status_code == 404


def test_user_a_cannot_delete_user_b_entry(client):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    a_entry = client.post('/api/journals', json={'title': 'A-private'}, headers=headers_a).get_json()
    assert client.delete(f'/api/journals/{a_entry["id"]}', headers=headers_b).status_code == 404


# --- enriched fields: defaults ---

def test_create_has_default_mood_tags_kind(client, auth_headers):
    res = client.post('/api/journals', json={'title': 'X'}, headers=auth_headers)
    data = res.get_json()
    assert data['mood'] is None
    assert data['tags'] == []
    assert data['kind'] == 'text'
    assert data['ai'] == {}


# --- enriched fields: mood ---

def test_create_with_mood(client, auth_headers):
    res = client.post('/api/journals', json={'title': 'X', 'mood': 7}, headers=auth_headers)
    assert res.status_code == 201
    assert res.get_json()['mood'] == 7


def test_create_mood_out_of_range_returns_400(client, auth_headers):
    assert client.post('/api/journals', json={'title': 'X', 'mood': 0}, headers=auth_headers).status_code == 400
    assert client.post('/api/journals', json={'title': 'X', 'mood': 11}, headers=auth_headers).status_code == 400


def test_create_mood_non_int_returns_400(client, auth_headers):
    assert client.post('/api/journals', json={'title': 'X', 'mood': 'high'}, headers=auth_headers).status_code == 400
    assert client.post('/api/journals', json={'title': 'X', 'mood': True}, headers=auth_headers).status_code == 400


def test_update_mood(client, auth_headers):
    entry = client.post('/api/journals', json={'title': 'X', 'mood': 5}, headers=auth_headers).get_json()
    res = client.put(f'/api/journals/{entry["id"]}', json={'mood': 8}, headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()['mood'] == 8


def test_update_invalid_mood_returns_400(client, auth_headers):
    entry = client.post('/api/journals', json={'title': 'X'}, headers=auth_headers).get_json()
    assert client.put(f'/api/journals/{entry["id"]}', json={'mood': 99}, headers=auth_headers).status_code == 400


# --- enriched fields: tags ---

def test_create_with_tags(client, auth_headers):
    res = client.post('/api/journals', json={'title': 'X', 'tags': ['work', 'urgent']}, headers=auth_headers)
    assert res.status_code == 201
    assert res.get_json()['tags'] == ['work', 'urgent']


def test_create_invalid_tags_returns_400(client, auth_headers):
    assert client.post('/api/journals', json={'title': 'X', 'tags': 'work'}, headers=auth_headers).status_code == 400
    assert client.post('/api/journals', json={'title': 'X', 'tags': [1, 2]}, headers=auth_headers).status_code == 400


def test_update_tags(client, auth_headers):
    entry = client.post('/api/journals', json={'title': 'X', 'tags': ['old']}, headers=auth_headers).get_json()
    res = client.put(f'/api/journals/{entry["id"]}', json={'tags': ['new', 'tags']}, headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()['tags'] == ['new', 'tags']


# --- enriched fields: kind ---

def test_create_with_kind(client, auth_headers):
    res = client.post('/api/journals', json={'title': 'X', 'kind': 'voice'}, headers=auth_headers)
    assert res.status_code == 201
    assert res.get_json()['kind'] == 'voice'


def test_create_invalid_kind_returns_400(client, auth_headers):
    assert client.post('/api/journals', json={'title': 'X', 'kind': 'bogus'}, headers=auth_headers).status_code == 400


def test_update_kind(client, auth_headers):
    entry = client.post('/api/journals', json={'title': 'X'}, headers=auth_headers).get_json()
    res = client.put(f'/api/journals/{entry["id"]}', json={'kind': 'summary'}, headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()['kind'] == 'summary'


# --- update edge cases ---

def test_update_empty_body_returns_unchanged(client, auth_headers):
    entry = client.post(
        '/api/journals',
        json={'title': 'Original', 'content': 'Stuff', 'mood': 5},
        headers=auth_headers,
    ).get_json()
    res = client.put(f'/api/journals/{entry["id"]}', json={}, headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data['title'] == 'Original'
    assert data['content'] == 'Stuff'
    assert data['mood'] == 5


def test_update_can_clear_content_to_empty_string(client, auth_headers):
    entry = client.post('/api/journals', json={'title': 'X', 'content': 'something'}, headers=auth_headers).get_json()
    res = client.put(f'/api/journals/{entry["id"]}', json={'content': ''}, headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()['content'] == ''


# --- health ---

def test_health_returns_healthy(client):
    res = client.get('/health')
    assert res.status_code == 200
    assert res.get_json() == {'status': 'healthy'}


# --- storage ---

def test_storage_persists_across_service_instances():
    coll = mongomock.MongoClient()['joy']['journals']
    s1 = JournalService(collection=coll)
    entry = s1.create('user-1', 'Persisted', 'content')
    s2 = JournalService(collection=coll)
    assert s2.get_one('user-1', entry['id']) is not None


# --- event publishing ---

def test_create_publishes_journal_created_event():
    coll = mongomock.MongoClient()['joy']['journals']
    publisher = MagicMock()
    svc = JournalService(collection=coll, publisher=publisher)
    entry = svc.create('user-1', 'Hello', 'body', mood=7, tags=['a'])
    publisher.publish.assert_called_once()
    routing_key, payload = publisher.publish.call_args.args
    assert routing_key == 'journal.created'
    assert payload['id'] == entry['id']
    assert payload['user_id'] == 'user-1'
    assert payload['title'] == 'Hello'
    assert payload['mood'] == 7
    assert payload['tags'] == ['a']


def test_create_succeeds_when_publisher_fails():
    coll = mongomock.MongoClient()['joy']['journals']
    publisher = MagicMock()
    publisher.publish.side_effect = RuntimeError('broker down')
    svc = JournalService(collection=coll, publisher=publisher)
    entry = svc.create('user-1', 'Still saved', 'body')
    assert entry['id']
    assert svc.get_one('user-1', entry['id']) is not None


def test_create_without_publisher_is_a_noop():
    coll = mongomock.MongoClient()['joy']['journals']
    svc = JournalService(collection=coll)
    entry = svc.create('user-1', 'No publisher', 'body')
    assert entry['id']


def test_post_journals_publishes_event_end_to_end():
    """HTTP-layer wiring: POST /api/journals must reach publisher.publish."""
    mongo = mongomock.MongoClient()['joy']
    publisher = MagicMock()
    app = Flask(__name__)
    app.config['TESTING'] = True
    user_service = UserService(collection=mongo['users'])
    journal_service = JournalService(collection=mongo['journals'], publisher=publisher)
    permissive = RateLimiter(max_attempts=1000, window_seconds=60)
    register_auth_routes(app, user_service=user_service, login_limiter=permissive)
    register_journal_routes(app, service=journal_service)

    with app.test_client() as c:
        c.post('/auth/register', json={'email': 'a@example.com', 'password': 'secret123'})
        token = c.post('/auth/login', json={'email': 'a@example.com', 'password': 'secret123'}).get_json()['token']
        headers = {'Authorization': f'Bearer {token}'}
        res = c.post('/api/journals', json={'title': 'Via HTTP', 'mood': 5}, headers=headers)

    assert res.status_code == 201
    publisher.publish.assert_called_once()
    routing_key, payload = publisher.publish.call_args.args
    assert routing_key == 'journal.created'
    assert payload['title'] == 'Via HTTP'
    assert payload['mood'] == 5


# --- sentiment persistence ---

def test_set_sentiment_writes_to_ai_subdoc():
    coll = mongomock.MongoClient()['joy']['journals']
    svc = JournalService(collection=coll)
    entry = svc.create('user-1', 'X', 'content')
    sentiment = {'label': 'positive', 'score': 0.9}
    updated = svc.set_sentiment('user-1', entry['id'], sentiment)
    assert updated['ai']['sentiment']['label'] == 'positive'
    assert updated['ai']['sentiment']['score'] == 0.9
    assert 'analyzed_at' in updated['ai']['sentiment']


def test_set_sentiment_is_user_scoped():
    coll = mongomock.MongoClient()['joy']['journals']
    svc = JournalService(collection=coll)
    entry = svc.create('user-1', 'X', 'content')
    result = svc.set_sentiment('user-2', entry['id'], {'label': 'positive', 'score': 0.9})
    assert result is None
    # Original entry untouched
    assert svc.get_one('user-1', entry['id'])['ai'] == {}


def test_set_sentiment_unknown_id_returns_none():
    coll = mongomock.MongoClient()['joy']['journals']
    svc = JournalService(collection=coll)
    result = svc.set_sentiment('user-1', 'nonexistent', {'label': 'positive', 'score': 0.9})
    assert result is None


def test_set_sentiment_overwrites_previous_sentiment():
    coll = mongomock.MongoClient()['joy']['journals']
    svc = JournalService(collection=coll)
    entry = svc.create('user-1', 'X', 'content')
    svc.set_sentiment('user-1', entry['id'], {'label': 'positive', 'score': 0.5})
    updated = svc.set_sentiment('user-1', entry['id'], {'label': 'negative', 'score': 0.9})
    assert updated['ai']['sentiment']['label'] == 'negative'
    assert updated['ai']['sentiment']['score'] == 0.9
