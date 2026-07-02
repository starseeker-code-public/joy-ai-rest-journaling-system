from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import mongomock
from minio.error import S3Error

from app.routes.journal_routes import register_journal_routes
from app.services.journal_service import JournalService
from app.services.storage_service import (
    MAX_ATTACHMENT_BYTES,
    ObjectMissing,
    ObjectTooLarge,
    StorageService,
    _sanitize_filename,
)
from tests.conftest import register_and_login as _register_and_login

_OLD = datetime.now(timezone.utc) - timedelta(days=1)
_FRESH = datetime.now(timezone.utc)


def _no_such_key(key):
    return S3Error(SimpleNamespace(status=404), 'NoSuchKey', 'missing', key, 'rid', 'hid')


class FakeMinio:
    def __init__(self):
        self.buckets = set()
        self.objects = {}  # key -> (size, last_modified)
        self.deleted = []

    def put(self, key, size=10, modified=_OLD):
        self.objects[key] = (size, modified)

    def bucket_exists(self, bucket):
        return bucket in self.buckets

    def make_bucket(self, bucket):
        self.buckets.add(bucket)

    def presigned_put_object(self, bucket, key, expires):
        return f'http://minio.test/{bucket}/{key}?put'

    def presigned_get_object(self, bucket, key, expires):
        return f'http://minio.test/{bucket}/{key}?get'

    def stat_object(self, bucket, key):
        if key not in self.objects:
            raise _no_such_key(key)
        size, _ = self.objects[key]
        return SimpleNamespace(size=size)

    def remove_object(self, bucket, key):
        self.objects.pop(key, None)
        self.deleted.append(key)

    def list_objects(self, bucket, recursive=False):
        return [
            SimpleNamespace(object_name=k, last_modified=modified)
            for k, (_, modified) in sorted(self.objects.items())
        ]


@pytest.fixture
def fake_minio():
    return FakeMinio()


@pytest.fixture
def storage(fake_minio):
    return StorageService(client=fake_minio, bucket='test-bucket')


# --- storage service ---

def test_sanitize_filename():
    assert _sanitize_filename('my photo.jpg') == 'my_photo.jpg'
    assert _sanitize_filename('../../etc/passwd') == '.._.._etc_passwd'
    assert _sanitize_filename('   ') == 'file'
    assert len(_sanitize_filename('x' * 500)) == 128


def test_ensure_bucket_idempotent(storage, fake_minio):
    storage.ensure_bucket()
    storage.ensure_bucket()
    assert fake_minio.buckets == {'test-bucket'}


def test_presign_upload_namespaces_key_by_user(storage):
    grant = storage.presign_upload('user-1', 'pic.png')
    assert grant['object_key'].startswith('user-1/')
    assert grant['object_key'].endswith('/pic.png')
    assert grant['upload_url'].endswith(f"{grant['object_key']}?put")
    assert grant['expires_in'] == 600


def test_presign_download(storage, fake_minio):
    fake_minio.put('user-1/abc/pic.png')
    grant = storage.presign_download('user-1/abc/pic.png')
    assert grant['download_url'].endswith('user-1/abc/pic.png?get')


def test_presign_download_missing_object_raises(storage):
    with pytest.raises(ObjectMissing):
        storage.presign_download('user-1/never/uploaded.png')


def test_presign_download_oversized_object_deleted_and_raises(storage, fake_minio):
    fake_minio.put('u1/big/blob.bin', size=MAX_ATTACHMENT_BYTES + 1)
    with pytest.raises(ObjectTooLarge):
        storage.presign_download('u1/big/blob.bin')
    assert 'u1/big/blob.bin' in fake_minio.deleted


def test_cleanup_orphans_deletes_unreferenced_only(storage, fake_minio):
    fake_minio.put('u1/a/keep.png')
    fake_minio.put('u1/b/orphan.png')
    deleted = storage.cleanup_orphans({'u1/a/keep.png'})
    assert deleted == ['u1/b/orphan.png']
    assert 'u1/a/keep.png' in fake_minio.objects


def test_cleanup_orphans_spares_fresh_objects(storage, fake_minio):
    fake_minio.put('u1/new/inflight.png', modified=_FRESH)
    assert storage.cleanup_orphans(set()) == []
    assert 'u1/new/inflight.png' in fake_minio.objects


# --- journal service attachment metadata ---

def test_add_and_get_attachment():
    coll = mongomock.MongoClient()['joy']['journals']
    svc = JournalService(collection=coll)
    entry = svc.create('u1', 'T', 'body')
    att = {'id': 'a1', 'object_key': 'u1/x/f.png', 'filename': 'f.png'}
    updated = svc.add_attachment('u1', entry['id'], att)
    assert updated['attachments'] == [att]
    assert svc.get_attachment('u1', entry['id'], 'a1') == att
    assert svc.get_attachment('u2', entry['id'], 'a1') is None


def test_remove_attachment_returns_metadata():
    coll = mongomock.MongoClient()['joy']['journals']
    svc = JournalService(collection=coll)
    entry = svc.create('u1', 'T', 'body')
    att = {'id': 'a1', 'object_key': 'u1/x/f.png', 'filename': 'f.png'}
    svc.add_attachment('u1', entry['id'], att)
    removed = svc.remove_attachment('u1', entry['id'], 'a1')
    assert removed == att
    assert svc.get_one('u1', entry['id'])['attachments'] == []
    assert svc.remove_attachment('u1', entry['id'], 'a1') is None


def test_referenced_object_keys_across_entries():
    coll = mongomock.MongoClient()['joy']['journals']
    svc = JournalService(collection=coll)
    e1 = svc.create('u1', 'A', '')
    e2 = svc.create('u2', 'B', '')
    svc.add_attachment('u1', e1['id'], {'id': 'a1', 'object_key': 'k1'})
    svc.add_attachment('u2', e2['id'], {'id': 'a2', 'object_key': 'k2'})
    assert svc.referenced_object_keys() == {'k1', 'k2'}


# --- routes ---

@pytest.fixture
def app(mongo, make_app, storage):
    journal_service = JournalService(collection=mongo['journals'])
    return make_app(
        lambda a: register_journal_routes(a, service=journal_service, storage_service=storage)
    )


def _entry(client, headers):
    return client.post('/api/journals', json={'title': 'X'}, headers=headers).get_json()


def test_attachment_routes_require_auth(client):
    assert client.post('/api/journals/e/attachments', json={'filename': 'a'}).status_code == 401
    assert client.get('/api/journals/e/attachments/a').status_code == 401
    assert client.delete('/api/journals/e/attachments/a').status_code == 401


def test_create_attachment_returns_upload_grant(client, auth_headers):
    entry = _entry(client, auth_headers)
    res = client.post(f'/api/journals/{entry["id"]}/attachments',
                      json={'filename': 'photo.jpg', 'content_type': 'image/jpeg'},
                      headers=auth_headers)
    assert res.status_code == 201
    body = res.get_json()
    assert body['upload_url'].startswith('http://minio.test/')
    assert body['attachment']['filename'] == 'photo.jpg'
    assert body['attachment']['content_type'] == 'image/jpeg'
    # Metadata persisted on the entry
    entry_after = client.get(f'/api/journals/{entry["id"]}', headers=auth_headers).get_json()
    assert len(entry_after['attachments']) == 1


def test_create_attachment_missing_filename_returns_400(client, auth_headers):
    entry = _entry(client, auth_headers)
    assert client.post(f'/api/journals/{entry["id"]}/attachments', json={}, headers=auth_headers).status_code == 400


def test_create_attachment_unknown_entry_returns_404(client, auth_headers):
    assert client.post('/api/journals/nope/attachments', json={'filename': 'a.png'}, headers=auth_headers).status_code == 404


def test_download_attachment_returns_presigned_url(client, auth_headers, fake_minio):
    entry = _entry(client, auth_headers)
    created = client.post(f'/api/journals/{entry["id"]}/attachments',
                          json={'filename': 'f.png'}, headers=auth_headers).get_json()
    aid = created['attachment']['id']
    fake_minio.put(created['attachment']['object_key'])  # simulate the upload
    res = client.get(f'/api/journals/{entry["id"]}/attachments/{aid}', headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()['download_url'].endswith('?get')


def test_download_before_upload_returns_409(client, auth_headers):
    entry = _entry(client, auth_headers)
    created = client.post(f'/api/journals/{entry["id"]}/attachments',
                          json={'filename': 'f.png'}, headers=auth_headers).get_json()
    aid = created['attachment']['id']
    res = client.get(f'/api/journals/{entry["id"]}/attachments/{aid}', headers=auth_headers)
    assert res.status_code == 409


def test_oversized_upload_returns_413_and_detaches(client, auth_headers, fake_minio):
    entry = _entry(client, auth_headers)
    created = client.post(f'/api/journals/{entry["id"]}/attachments',
                          json={'filename': 'big.bin'}, headers=auth_headers).get_json()
    aid = created['attachment']['id']
    key = created['attachment']['object_key']
    fake_minio.put(key, size=MAX_ATTACHMENT_BYTES + 1)
    res = client.get(f'/api/journals/{entry["id"]}/attachments/{aid}', headers=auth_headers)
    assert res.status_code == 413
    assert key in fake_minio.deleted
    # Metadata detached too
    assert client.get(f'/api/journals/{entry["id"]}/attachments/{aid}', headers=auth_headers).status_code == 404


def test_prune_dangling_metadata():
    from scripts.cleanup_orphans import prune_dangling_metadata
    coll = mongomock.MongoClient()['joy']['journals']
    journals = JournalService(collection=coll)
    fake = FakeMinio()
    storage = StorageService(client=fake, bucket='b')
    entry = journals.create('u1', 'T', '')
    old_iso = _OLD.isoformat()
    journals.add_attachment('u1', entry['id'], {'id': 'kept', 'object_key': 'k1', 'created_at': old_iso})
    journals.add_attachment('u1', entry['id'], {'id': 'ghost', 'object_key': 'k2', 'created_at': old_iso})
    journals.add_attachment('u1', entry['id'], {'id': 'fresh', 'object_key': 'k3', 'created_at': _FRESH.isoformat()})
    fake.put('k1')  # only k1 was actually uploaded
    assert prune_dangling_metadata(journals, storage) == 1
    remaining = {a['id'] for a in journals.get_one('u1', entry['id'])['attachments']}
    assert remaining == {'kept', 'fresh'}


def test_delete_attachment_removes_object_and_metadata(client, auth_headers, fake_minio):
    entry = _entry(client, auth_headers)
    created = client.post(f'/api/journals/{entry["id"]}/attachments',
                          json={'filename': 'f.png'}, headers=auth_headers).get_json()
    aid = created['attachment']['id']
    key = created['attachment']['object_key']
    assert client.delete(f'/api/journals/{entry["id"]}/attachments/{aid}', headers=auth_headers).status_code == 204
    assert key in fake_minio.deleted
    assert client.get(f'/api/journals/{entry["id"]}/attachments/{aid}', headers=auth_headers).status_code == 404


def test_user_a_cannot_touch_user_b_attachments(client):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    entry = client.post('/api/journals', json={'title': 'A'}, headers=headers_a).get_json()
    created = client.post(f'/api/journals/{entry["id"]}/attachments',
                          json={'filename': 'f.png'}, headers=headers_a).get_json()
    aid = created['attachment']['id']
    assert client.post(f'/api/journals/{entry["id"]}/attachments', json={'filename': 'x'}, headers=headers_b).status_code == 404
    assert client.get(f'/api/journals/{entry["id"]}/attachments/{aid}', headers=headers_b).status_code == 404
    assert client.delete(f'/api/journals/{entry["id"]}/attachments/{aid}', headers=headers_b).status_code == 404


def test_storage_outage_returns_503(mongo, make_app):
    class ExplodingStorage:
        def presign_upload(self, user_id, filename):
            raise ConnectionError('minio down')

    journal_service = JournalService(collection=mongo['journals'])
    app = make_app(lambda a: register_journal_routes(
        a, service=journal_service, storage_service=ExplodingStorage()))
    with app.test_client() as client:
        headers = _register_and_login(client)
        entry = client.post('/api/journals', json={'title': 'X'}, headers=headers).get_json()
        res = client.post(f'/api/journals/{entry["id"]}/attachments',
                          json={'filename': 'f.png'}, headers=headers)
        assert res.status_code == 503