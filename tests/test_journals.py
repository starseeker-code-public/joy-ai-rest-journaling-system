import pytest
import mongomock
from flask import Flask
from app.routes.journal_routes import register_journal_routes
from app.services.journal_service import JournalService


@pytest.fixture
def collection():
    return mongomock.MongoClient()['joy']['journals']


@pytest.fixture
def client(collection):
    app = Flask(__name__)
    app.config['TESTING'] = True
    service = JournalService(collection=collection)
    register_journal_routes(app, service=service)
    with app.test_client() as c:
        yield c


# --- list ---

def test_list_empty(client):
    res = client.get('/api/journals')
    assert res.status_code == 200
    assert res.get_json() == []


def test_list_contains_created_entries(client):
    client.post('/api/journals', json={'title': 'A'})
    client.post('/api/journals', json={'title': 'B'})
    data = client.get('/api/journals').get_json()
    assert len(data) == 2
    assert {e['title'] for e in data} == {'A', 'B'}


# --- create ---

def test_create_returns_201_with_all_fields(client):
    res = client.post('/api/journals', json={'title': 'Day 1', 'content': 'Good day'})
    assert res.status_code == 201
    data = res.get_json()
    assert data['title'] == 'Day 1'
    assert data['content'] == 'Good day'
    assert 'id' in data
    assert 'date' in data


def test_create_content_defaults_to_empty(client):
    res = client.post('/api/journals', json={'title': 'No content'})
    assert res.status_code == 201
    assert res.get_json()['content'] == ''


def test_create_missing_title_returns_400(client):
    assert client.post('/api/journals', json={'content': 'No title'}).status_code == 400


def test_create_empty_body_returns_400(client):
    assert client.post('/api/journals', json={}).status_code == 400


# --- get single ---

def test_get_one_returns_entry(client):
    created = client.post('/api/journals', json={'title': 'Entry'}).get_json()
    res = client.get(f'/api/journals/{created["id"]}')
    assert res.status_code == 200
    assert res.get_json()['id'] == created['id']


def test_get_one_unknown_id_returns_404(client):
    assert client.get('/api/journals/nonexistent-id').status_code == 404


# --- update ---

def test_update_title_and_content(client):
    created = client.post('/api/journals', json={'title': 'Old', 'content': 'Old'}).get_json()
    res = client.put(f'/api/journals/{created["id"]}', json={'title': 'New', 'content': 'New'})
    assert res.status_code == 200
    data = res.get_json()
    assert data['title'] == 'New'
    assert data['content'] == 'New'


def test_update_partial_preserves_other_fields(client):
    created = client.post('/api/journals', json={'title': 'Keep', 'content': 'Keep'}).get_json()
    res = client.put(f'/api/journals/{created["id"]}', json={'title': 'Changed'})
    assert res.status_code == 200
    data = res.get_json()
    assert data['title'] == 'Changed'
    assert data['content'] == 'Keep'


def test_update_unknown_id_returns_404(client):
    assert client.put('/api/journals/nonexistent-id', json={'title': 'X'}).status_code == 404


# --- delete ---

def test_delete_returns_204(client):
    created = client.post('/api/journals', json={'title': 'Bye'}).get_json()
    assert client.delete(f'/api/journals/{created["id"]}').status_code == 204


def test_delete_entry_is_gone(client):
    created = client.post('/api/journals', json={'title': 'Gone'}).get_json()
    client.delete(f'/api/journals/{created["id"]}')
    assert client.get(f'/api/journals/{created["id"]}').status_code == 404


def test_delete_unknown_id_returns_404(client):
    assert client.delete('/api/journals/nonexistent-id').status_code == 404


# --- storage ---

def test_storage_persists_across_service_instances():
    coll = mongomock.MongoClient()['joy']['journals']
    s1 = JournalService(collection=coll)
    entry = s1.create('Persisted', 'content')
    s2 = JournalService(collection=coll)
    assert s2.get_one(entry['id']) is not None
