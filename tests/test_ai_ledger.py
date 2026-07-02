from unittest.mock import MagicMock

import pytest
import mongomock

from app.routes.usage_routes import register_usage_routes
from app.services.ai_ledger import AILedger, BUDGET_BLOCK, BUDGET_OK, BUDGET_WARN
from tests.conftest import register_and_login as _register_and_login


@pytest.fixture
def ledger():
    return AILedger(collection=mongomock.MongoClient()['joy']['ai_calls'])


# --- recording & rollups ---

def test_record_returns_full_call(ledger):
    call = ledger.record('u1', 'sentiment', 'distilbert', entry_id='e1', duration_s=0.4)
    assert call['user_id'] == 'u1'
    assert call['kind'] == 'sentiment'
    assert call['cost_usd'] == 0.0
    assert 'called_at' in call and 'id' in call


def test_usage_rolls_up_today_and_month(ledger):
    ledger.record('u1', 'sentiment', 'm', cost_usd=0.01)
    ledger.record('u1', 'transcription', 'w', cost_usd=0.02)
    ledger.record('u2', 'sentiment', 'm', cost_usd=5.0)  # other user
    usage = ledger.usage('u1')
    assert usage['today']['calls'] == 2
    assert usage['today']['cost_usd'] == 0.03
    assert usage['today']['by_kind'] == {'sentiment': 1, 'transcription': 1}
    assert usage['month']['calls'] == 2
    assert usage['budget_status'] == BUDGET_OK
    assert usage['daily_budget_usd'] is None


# --- budget enforcement ---

def test_budget_status_thresholds(ledger, monkeypatch):
    monkeypatch.setenv('AI_DAILY_BUDGET_USD', '1.00')
    assert ledger.budget_status('u1') == BUDGET_OK
    ledger.record('u1', 'transcription', 'w', cost_usd=0.85)
    assert ledger.budget_status('u1') == BUDGET_WARN
    ledger.record('u1', 'transcription', 'w', cost_usd=0.20)
    assert ledger.budget_status('u1') == BUDGET_BLOCK


def test_budget_unset_or_invalid_means_unlimited(ledger, monkeypatch):
    ledger.record('u1', 'transcription', 'w', cost_usd=999)
    monkeypatch.delenv('AI_DAILY_BUDGET_USD', raising=False)
    assert ledger.budget_status('u1') == BUDGET_OK
    monkeypatch.setenv('AI_DAILY_BUDGET_USD', 'not-a-number')
    assert ledger.budget_status('u1') == BUDGET_OK


# --- worker integration ---

def test_analysis_worker_records_and_blocks(monkeypatch, ledger):
    from analysis_worker import make_handler
    analysis = MagicMock()
    analysis.analyze.return_value = {'label': 'positive', 'score': 0.9}
    analysis.model_name = 'distilbert'
    journal = MagicMock()
    journal.set_sentiment.return_value = {'id': 'e1'}
    handler = make_handler(analysis, journal, ledger=ledger)

    handler('journal.created', {'id': 'e1', 'user_id': 'u1', 'content': 'hey'})
    assert ledger.usage('u1')['today']['by_kind'] == {'sentiment': 1}

    monkeypatch.setenv('AI_DAILY_BUDGET_USD', '0.50')
    ledger.record('u1', 'transcription', 'w', cost_usd=1.0)
    analysis.analyze.reset_mock()
    handler('journal.created', {'id': 'e2', 'user_id': 'u1', 'content': 'hey'})
    analysis.analyze.assert_not_called()  # hard-blocked


def test_transcription_worker_records_cost(ledger):
    from transcription_worker import make_handler
    from app.services.transcription_service import TranscriptionService

    class Stub:
        def __call__(self, path):
            return {'text': 'hi'}

    journal = MagicMock()
    journal.set_transcript.return_value = {'id': 'e1'}
    storage = MagicMock()
    handler = make_handler(TranscriptionService(transcriber=Stub()), journal, storage, ledger=ledger)
    handler('journal.voice_uploaded', {
        'id': 'e1', 'user_id': 'u1', 'attachment_id': 'a1', 'object_key': 'k.wav',
    })
    usage = ledger.usage('u1')
    assert usage['today']['by_kind'] == {'transcription': 1}


def test_transcription_worker_blocks_over_budget(monkeypatch, ledger):
    from transcription_worker import make_handler
    monkeypatch.setenv('AI_DAILY_BUDGET_USD', '0.10')
    ledger.record('u1', 'transcription', 'w', cost_usd=0.5)
    transcription = MagicMock()
    journal = MagicMock()
    storage = MagicMock()
    handler = make_handler(transcription, journal, storage, ledger=ledger)
    handler('journal.voice_uploaded', {
        'id': 'e1', 'user_id': 'u1', 'attachment_id': 'a1', 'object_key': 'k.wav',
    })
    storage.download_to.assert_not_called()
    transcription.transcribe.assert_not_called()


# --- /api/me/usage endpoint ---

@pytest.fixture
def app(mongo, make_app, ledger):
    app = make_app(lambda a: register_usage_routes(a, ledger=ledger))
    app.config['_ledger'] = ledger
    return app


def test_usage_requires_auth(client):
    assert client.get('/api/me/usage').status_code == 401


def test_usage_returns_rollup_for_current_user(client, auth_headers, app):
    ledger = app.config['_ledger']
    me = client.get('/auth/me', headers=auth_headers).get_json()['id']
    ledger.record(me, 'sentiment', 'm', cost_usd=0.001)
    body = client.get('/api/me/usage', headers=auth_headers).get_json()
    assert body['today']['calls'] == 1
    assert body['month']['cost_usd'] == 0.001
    assert body['budget_status'] == 'ok'


def test_usage_backend_outage_returns_503(mongo, make_app):
    class Exploding:
        def usage(self, user_id):
            raise ConnectionError('mongo down')

    app = make_app(lambda a: register_usage_routes(a, ledger=Exploding()))
    with app.test_client() as client:
        headers = _register_and_login(client)
        assert client.get('/api/me/usage', headers=headers).status_code == 503


def test_record_with_dedupe_key_is_idempotent(ledger):
    ledger.record('u1', 'transcription', 'w', cost_usd=0.5, dedupe_key='transcription:evt-1')
    ledger.record('u1', 'transcription', 'w', cost_usd=0.5, dedupe_key='transcription:evt-1')
    usage = ledger.usage('u1')
    assert usage['today']['calls'] == 1
    assert usage['today']['cost_usd'] == 0.5


def test_blocked_calls_recorded_visibly(monkeypatch, ledger):
    from analysis_worker import make_handler
    monkeypatch.setenv('AI_DAILY_BUDGET_USD', '0.10')
    ledger.record('u1', 'transcription', 'w', cost_usd=1.0)
    analysis = MagicMock()
    analysis.model_name = 'distilbert'
    handler = make_handler(analysis, MagicMock(), ledger=ledger)
    handler('journal.created', {'id': 'e1', 'user_id': 'u1', 'content': 'x', 'event_id': 'evt-9'})
    assert ledger.usage('u1')['today']['by_kind'].get('sentiment_blocked') == 1
    analysis.analyze.assert_not_called()


def test_publisher_stamps_event_id():
    from app.utils.event_publisher import EventPublisher
    import json as _json
    connection = MagicMock()
    channel = MagicMock()
    connection.is_closed = False
    connection.is_open = True
    channel.is_closed = False
    connection.channel.return_value = channel
    pub = EventPublisher(url='amqp://test/', connection_factory=lambda: connection)
    pub.publish('journal.created', {'id': 'e1'})
    body = channel.basic_publish.call_args.kwargs['body']
    payload = _json.loads(body)
    assert payload['id'] == 'e1'
    assert len(payload['event_id']) == 36
