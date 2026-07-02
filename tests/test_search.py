from unittest.mock import MagicMock

import pytest
import mongomock

from app.routes.journal_routes import register_journal_routes
from app.services.journal_service import JournalService
from app.services.search_service import SearchService, INDEX_NAME
from app.utils import retry as retry_module
from search_indexer import backfill, make_handler
from tests.conftest import register_and_login as _register_and_login


class FakeIndices:
    def __init__(self):
        self.created = []
        self.existing = set()

    def exists(self, index):
        return index in self.existing

    def create(self, index, body):
        self.existing.add(index)
        self.created.append((index, body))


class FakeOpenSearch:
    """Records index/delete/search calls; returns canned search hits."""

    def __init__(self, hits=None):
        self.indices = FakeIndices()
        self.indexed = {}
        self.deleted = []
        self.search_bodies = []
        self._hits = hits or []

    def index(self, index, id, body):
        self.indexed[id] = (index, body)

    def delete(self, index, id, params=None):
        self.deleted.append((index, id))

    def search(self, index, body):
        self.search_bodies.append((index, body))
        return {'hits': {'hits': [{'_source': h} for h in self._hits]}}


@pytest.fixture
def fake_client():
    return FakeOpenSearch()


@pytest.fixture
def service(fake_client):
    return SearchService(client=fake_client)


# --- SearchService: indexing ---

def test_ensure_index_creates_once(service, fake_client):
    service.ensure_index()
    service.ensure_index()
    assert len(fake_client.indices.created) == 1
    assert fake_client.indices.created[0][0] == INDEX_NAME


def test_index_entry_projects_indexed_fields_only(service, fake_client):
    entry = {
        'id': 'e1', 'user_id': 'u1', 'title': 'T', 'content': 'C',
        'tags': ['a'], 'kind': 'text', 'mood': 5, 'date': '2026-07-01T00:00:00+00:00',
        'ai': {'sentiment': {'label': 'positive'}},
    }
    service.index_entry(entry)
    index, body = fake_client.indexed['e1']
    assert index == INDEX_NAME
    assert 'ai' not in body
    assert body['title'] == 'T'
    assert body['user_id'] == 'u1'


def test_delete_entry(service, fake_client):
    service.delete_entry('e1')
    assert fake_client.deleted == [(INDEX_NAME, 'e1')]


# --- SearchService: query building ---

def _query_of(fake_client):
    return fake_client.search_bodies[-1][1]


def test_search_always_scopes_to_user(service, fake_client):
    service.search('u1')
    body = _query_of(fake_client)
    assert {'term': {'user_id': 'u1'}} in body['query']['bool']['filter']


def test_search_with_q_uses_multi_match(service, fake_client):
    service.search('u1', q='sunny day')
    body = _query_of(fake_client)
    assert body['query']['bool']['must'] == [
        {'multi_match': {'query': 'sunny day', 'fields': ['title^2', 'content']}}
    ]
    assert body['sort'] == ['_score']


def test_search_without_q_sorts_by_date_desc(service, fake_client):
    service.search('u1')
    body = _query_of(fake_client)
    assert 'must' not in body['query']['bool']
    assert body['sort'] == [{'date': {'order': 'desc'}}]


def test_search_filters_tags_kind_and_dates(service, fake_client):
    service.search('u1', tags=['work'], kind='text', date_from='2026-01-01', date_to='2026-06-30')
    filters = _query_of(fake_client)['query']['bool']['filter']
    assert {'terms': {'tags': ['work']}} in filters
    assert {'term': {'kind': 'text'}} in filters
    assert {'range': {'date': {'gte': '2026-01-01', 'lt': '2026-06-30||+1d/d'}}} in filters


def test_search_limit_is_capped(service, fake_client):
    service.search('u1', limit=5000)
    assert _query_of(fake_client)['size'] == 100


def test_search_returns_sources():
    client = FakeOpenSearch(hits=[{'id': 'e1', 'title': 'Hello'}])
    results = SearchService(client=client).search('u1', q='hello')
    assert results == [{'id': 'e1', 'title': 'Hello'}]


# --- indexer handler ---

def test_handler_indexes_created_and_updated(service, fake_client):
    handle = make_handler(service)
    handle('journal.created', {'id': 'e1', 'user_id': 'u1', 'title': 'A'})
    handle('journal.updated', {'id': 'e1', 'user_id': 'u1', 'title': 'B'})
    assert fake_client.indexed['e1'][1]['title'] == 'B'


def test_handler_deletes_on_deleted_event(service, fake_client):
    handle = make_handler(service)
    handle('journal.deleted', {'id': 'e1', 'user_id': 'u1'})
    assert fake_client.deleted == [(INDEX_NAME, 'e1')]


def test_handler_skips_malformed_payloads(service, fake_client):
    handle = make_handler(service)
    handle('journal.created', 'not-a-dict')
    handle('journal.created', {'user_id': 'u1'})  # missing id
    assert fake_client.indexed == {}


def test_handler_retries_transient_failures(service, fake_client, monkeypatch):
    monkeypatch.setattr(retry_module.time, 'sleep', lambda s: None)
    failures = {'left': 2}
    original = fake_client.index

    def flaky_index(index, id, body):
        if failures['left'] > 0:
            failures['left'] -= 1
            raise ConnectionError('opensearch briefly down')
        original(index, id, body)

    fake_client.index = flaky_index
    make_handler(service)('journal.created', {'id': 'e1', 'user_id': 'u1'})
    assert 'e1' in fake_client.indexed


def test_handler_raises_after_exhausting_retries(service, fake_client, monkeypatch):
    monkeypatch.setattr(retry_module.time, 'sleep', lambda s: None)

    def always_fail(index, id, body):
        raise ConnectionError('opensearch down')

    fake_client.index = always_fail
    with pytest.raises(ConnectionError):
        make_handler(service)('journal.created', {'id': 'e1', 'user_id': 'u1'})


def test_backfill_indexes_all_entries(service, fake_client):
    coll = mongomock.MongoClient()['joy']['journals']
    svc = JournalService(collection=coll)
    ids = {svc.create('u1', f'Entry {n}', 'body')['id'] for n in range(3)}
    assert backfill(service, coll) == 3
    assert set(fake_client.indexed) == ids
    # Raw Mongo docs carry _id; the index body must not
    assert all('_id' not in body for _, body in fake_client.indexed.values())


# --- journal events feeding the indexer ---

def test_update_publishes_journal_updated():
    coll = mongomock.MongoClient()['joy']['journals']
    publisher = MagicMock()
    svc = JournalService(collection=coll, publisher=publisher)
    entry = svc.create('user-1', 'Old', 'body')
    publisher.reset_mock()
    svc.update('user-1', entry['id'], title='New')
    routing_key, payload = publisher.publish.call_args.args
    assert routing_key == 'journal.updated'
    assert payload['title'] == 'New'


def test_update_of_missing_entry_publishes_nothing():
    coll = mongomock.MongoClient()['joy']['journals']
    publisher = MagicMock()
    svc = JournalService(collection=coll, publisher=publisher)
    svc.update('user-1', 'nope', title='New')
    publisher.publish.assert_not_called()


def test_noop_update_publishes_nothing():
    coll = mongomock.MongoClient()['joy']['journals']
    publisher = MagicMock()
    svc = JournalService(collection=coll, publisher=publisher)
    entry = svc.create('user-1', 'T', 'body')
    publisher.reset_mock()
    svc.update('user-1', entry['id'])  # empty patch
    publisher.publish.assert_not_called()


def test_delete_publishes_journal_deleted():
    coll = mongomock.MongoClient()['joy']['journals']
    publisher = MagicMock()
    svc = JournalService(collection=coll, publisher=publisher)
    entry = svc.create('user-1', 'T', 'body')
    publisher.reset_mock()
    svc.delete('user-1', entry['id'])
    routing_key, payload = publisher.publish.call_args.args
    assert routing_key == 'journal.deleted'
    assert payload['id'] == entry['id']
    assert payload['user_id'] == 'user-1'
    assert payload['date'] == entry['date']  # lets consumers target the entry's week


def test_delete_of_missing_entry_publishes_nothing():
    coll = mongomock.MongoClient()['joy']['journals']
    publisher = MagicMock()
    svc = JournalService(collection=coll, publisher=publisher)
    svc.delete('user-1', 'nope')
    publisher.publish.assert_not_called()


# --- search endpoint ---

@pytest.fixture
def app(mongo, make_app):
    journal_service = JournalService(collection=mongo['journals'])
    search = SearchService(client=FakeOpenSearch(hits=[{'id': 'e1', 'title': 'Hit'}]))
    return make_app(
        lambda a: register_journal_routes(a, service=journal_service, search_service=search)
    )


def test_search_requires_auth(client):
    assert client.get('/api/journals/search?q=x').status_code == 401


def test_search_returns_results(client, auth_headers):
    res = client.get('/api/journals/search?q=hello', headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json() == [{'id': 'e1', 'title': 'Hit'}]


def test_search_invalid_dates_return_400(client, auth_headers):
    assert client.get('/api/journals/search?from=nope', headers=auth_headers).status_code == 400
    assert client.get('/api/journals/search?to=20260101', headers=auth_headers).status_code == 400


def test_search_invalid_limit_returns_400(client, auth_headers):
    assert client.get('/api/journals/search?limit=abc', headers=auth_headers).status_code == 400
    assert client.get('/api/journals/search?limit=0', headers=auth_headers).status_code == 400
    assert client.get('/api/journals/search?limit=-3', headers=auth_headers).status_code == 400
    # Unicode digits pass isdigit() but not int(); must still be a 400, not 500
    assert client.get('/api/journals/search?limit=²', headers=auth_headers).status_code == 400


def test_search_route_does_not_shadow_get_by_id(client, auth_headers):
    created = client.post('/api/journals', json={'title': 'X'}, headers=auth_headers).get_json()
    res = client.get(f'/api/journals/{created["id"]}', headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()['id'] == created['id']


def test_search_unavailable_returns_503(mongo, make_app):
    class ExplodingClient:
        def search(self, index, body):
            raise ConnectionError('opensearch down')

    journal_service = JournalService(collection=mongo['journals'])
    search = SearchService(client=ExplodingClient())
    app = make_app(
        lambda a: register_journal_routes(a, service=journal_service, search_service=search)
    )
    with app.test_client() as client:
        headers = _register_and_login(client)
        res = client.get('/api/journals/search?q=x', headers=headers)
        assert res.status_code == 503


def test_search_without_service_returns_503(mongo, make_app):
    journal_service = JournalService(collection=mongo['journals'])
    app = make_app(lambda a: register_journal_routes(a, service=journal_service))
    with app.test_client() as client:
        headers = _register_and_login(client)
        assert client.get('/api/journals/search?q=x', headers=headers).status_code == 503


def test_search_passes_all_params_through(mongo, make_app):
    fake = FakeOpenSearch()
    journal_service = JournalService(collection=mongo['journals'])
    app = make_app(
        lambda a: register_journal_routes(
            a, service=journal_service, search_service=SearchService(client=fake)
        )
    )
    with app.test_client() as client:
        headers = _register_and_login(client)
        client.get(
            '/api/journals/search?q=sun&tags=work,life&kind=text&from=2026-01-01&to=2026-02-01&limit=5',
            headers=headers,
        )
    body = fake.search_bodies[-1][1]
    filters = body['query']['bool']['filter']
    assert {'terms': {'tags': ['work', 'life']}} in filters
    assert {'term': {'kind': 'text'}} in filters
    assert body['size'] == 5
    assert body['query']['bool']['must'][0]['multi_match']['query'] == 'sun'
