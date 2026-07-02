from unittest.mock import MagicMock

import pytest
import mongomock

from app.routes.journal_routes import register_journal_routes
from app.services.journal_service import JournalService
from app.services.transcription_service import TranscriptionService
from transcription_worker import make_handler
from tests.conftest import register_and_login as _register_and_login


class StubTranscriber:
    def __init__(self, text='I felt calm today'):
        self.text = text
        self.calls = []

    def __call__(self, audio_path):
        self.calls.append(audio_path)
        return {'text': f' {self.text} '}


# --- transcription service ---

def test_transcribe_returns_text_and_cost_fields():
    service = TranscriptionService(transcriber=StubTranscriber('hello'))
    result = service.transcribe('/tmp/a.wav')
    assert result['text'] == 'hello'  # trimmed
    assert result['cost_usd'] == 0.0
    assert result['duration_s'] >= 0
    assert 'whisper' in result['model']


# --- set_transcript ---

def _svc(publisher=None):
    coll = mongomock.MongoClient()['joy']['journals']
    return JournalService(collection=coll, publisher=publisher)


def _voice_entry(svc, publisher=None):
    entry = svc.create('u1', 'Voice note', '', kind='voice')
    att = {'id': 'a1', 'object_key': 'u1/x/audio.wav', 'filename': 'audio.wav'}
    svc.add_attachment('u1', entry['id'], att)
    return entry


def test_set_transcript_fills_empty_content_and_attachment():
    publisher = MagicMock()
    svc = _svc(publisher)
    entry = _voice_entry(svc)
    publisher.reset_mock()
    transcription = {'text': 'I felt calm', 'model': 'whisper-tiny', 'duration_s': 1.2, 'cost_usd': 0.0}
    updated = svc.set_transcript('u1', entry['id'], 'a1', transcription)
    assert updated['content'] == 'I felt calm'
    assert updated['attachments'][0]['transcription'] == transcription
    routing_key, payload = publisher.publish.call_args.args
    assert routing_key == 'journal.transcribed'
    assert payload['content'] == 'I felt calm'


def test_set_transcript_preserves_existing_content():
    svc = _svc()
    entry = svc.create('u1', 'T', 'typed text', kind='voice')
    svc.add_attachment('u1', entry['id'], {'id': 'a1', 'object_key': 'k', 'filename': 'f'})
    updated = svc.set_transcript('u1', entry['id'], 'a1', {'text': 'spoken'})
    assert updated['content'] == 'typed text'
    assert updated['attachments'][0]['transcription']['text'] == 'spoken'


def test_set_transcript_unknown_targets_return_none():
    svc = _svc()
    entry = _voice_entry(svc)
    assert svc.set_transcript('u2', entry['id'], 'a1', {'text': 'x'}) is None
    assert svc.set_transcript('u1', entry['id'], 'nope', {'text': 'x'}) is None
    assert svc.set_transcript('u1', 'nope', 'a1', {'text': 'x'}) is None


def test_request_transcription_publishes_event():
    publisher = MagicMock()
    svc = _svc(publisher)
    entry = _voice_entry(svc)
    publisher.reset_mock()
    attachment = svc.request_transcription('u1', entry['id'], 'a1')
    assert attachment['id'] == 'a1'
    routing_key, payload = publisher.publish.call_args.args
    assert routing_key == 'journal.voice_uploaded'
    assert payload['attachment_id'] == 'a1'
    assert payload['object_key'] == 'u1/x/audio.wav'
    assert payload['user_id'] == 'u1'


# --- worker handler ---

def test_worker_transcribes_and_persists():
    transcriber = StubTranscriber('spoken words')
    transcription_service = TranscriptionService(transcriber=transcriber)
    journal = MagicMock()
    journal.set_transcript.return_value = {'id': 'e1'}
    storage = MagicMock()
    handle = make_handler(transcription_service, journal, storage)
    handle('journal.voice_uploaded', {
        'id': 'e1', 'user_id': 'u1', 'attachment_id': 'a1', 'object_key': 'u1/x/audio.wav',
    })
    storage.download_to.assert_called_once()
    assert storage.download_to.call_args.args[0] == 'u1/x/audio.wav'
    user_id, entry_id, attachment_id, result = journal.set_transcript.call_args.args
    assert (user_id, entry_id, attachment_id) == ('u1', 'e1', 'a1')
    assert result['text'] == 'spoken words'


def test_worker_skips_malformed_payloads():
    journal = MagicMock()
    storage = MagicMock()
    handle = make_handler(TranscriptionService(transcriber=StubTranscriber()), journal, storage)
    handle('journal.voice_uploaded', 'nope')
    handle('journal.voice_uploaded', {'id': 'e1', 'user_id': 'u1'})  # missing keys
    journal.set_transcript.assert_not_called()
    storage.download_to.assert_not_called()


# --- transcribe endpoint ---

@pytest.fixture
def app(mongo, make_app):
    publisher = MagicMock()
    journal_service = JournalService(collection=mongo['journals'], publisher=publisher)
    storage = MagicMock()
    storage.object_size.return_value = 1024
    storage.presign_upload.return_value = {
        'object_key': 'u1/k/a.wav', 'upload_url': 'http://minio.test/a.wav?put', 'expires_in': 600,
    }
    app = make_app(lambda a: register_journal_routes(
        a, service=journal_service, storage_service=storage))
    app.config['_publisher'] = publisher
    app.config['_storage'] = storage
    return app


def _attach(client, headers):
    entry = client.post('/api/journals', json={'title': 'V', 'kind': 'voice'}, headers=headers).get_json()
    grant = client.post(f'/api/journals/{entry["id"]}/attachments',
                        json={'filename': 'a.wav'}, headers=headers).get_json()
    return entry, grant['attachment']


def test_transcribe_requires_auth(client):
    assert client.post('/api/journals/e/attachments/a/transcribe').status_code == 401


def test_transcribe_queues_event(client, auth_headers, app):
    entry, attachment = _attach(client, auth_headers)
    res = client.post(f'/api/journals/{entry["id"]}/attachments/{attachment["id"]}/transcribe',
                      headers=auth_headers)
    assert res.status_code == 202
    publisher = app.config['_publisher']
    routing_keys = [c.args[0] for c in publisher.publish.call_args_list]
    assert 'journal.voice_uploaded' in routing_keys


def test_transcribe_before_upload_returns_409(client, auth_headers, app):
    app.config['_storage'].object_size.return_value = None
    entry, attachment = _attach(client, auth_headers)
    res = client.post(f'/api/journals/{entry["id"]}/attachments/{attachment["id"]}/transcribe',
                      headers=auth_headers)
    assert res.status_code == 409


def test_transcribe_unknown_attachment_returns_404(client, auth_headers):
    entry = client.post('/api/journals', json={'title': 'V'}, headers=auth_headers).get_json()
    assert client.post(f'/api/journals/{entry["id"]}/attachments/nope/transcribe',
                       headers=auth_headers).status_code == 404


def test_user_a_cannot_transcribe_user_b_attachment(client, app):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    entry, attachment = _attach(client, headers_a)
    res = client.post(f'/api/journals/{entry["id"]}/attachments/{attachment["id"]}/transcribe',
                      headers=headers_b)
    assert res.status_code == 404


def test_transcribe_non_audio_attachment_returns_400(client, auth_headers, app):
    entry = client.post('/api/journals', json={'title': 'V'}, headers=auth_headers).get_json()
    app.config['_storage'].presign_upload.return_value = {
        'object_key': 'u1/k/doc.pdf', 'upload_url': 'http://x?put', 'expires_in': 600,
    }
    grant = client.post(f'/api/journals/{entry["id"]}/attachments',
                        json={'filename': 'doc.pdf', 'content_type': 'application/pdf'},
                        headers=auth_headers).get_json()
    aid = grant['attachment']['id']
    res = client.post(f'/api/journals/{entry["id"]}/attachments/{aid}/transcribe', headers=auth_headers)
    assert res.status_code == 400


def test_transcribe_accepts_audio_by_extension_without_content_type(client, auth_headers):
    entry = client.post('/api/journals', json={'title': 'V'}, headers=auth_headers).get_json()
    grant = client.post(f'/api/journals/{entry["id"]}/attachments',
                        json={'filename': 'memo.ogg'}, headers=auth_headers).get_json()
    aid = grant['attachment']['id']
    res = client.post(f'/api/journals/{entry["id"]}/attachments/{aid}/transcribe', headers=auth_headers)
    assert res.status_code == 202


def test_set_transcript_returns_none_when_entry_deleted_mid_flight():
    svc = _svc()
    entry = _voice_entry(svc)
    # Simulate the entry vanishing between the worker's read and its write
    original_find_one = svc.collection.find_one

    def find_then_delete(query, *args, **kwargs):
        doc = original_find_one(query, *args, **kwargs)
        svc.collection.delete_one({'id': entry['id']})
        return doc

    svc.collection.find_one = find_then_delete
    assert svc.set_transcript('u1', entry['id'], 'a1', {'text': 'x'}) is None
