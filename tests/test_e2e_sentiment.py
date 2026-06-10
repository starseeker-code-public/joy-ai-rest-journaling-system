"""Full pipeline: POST → publisher → fake broker → worker → set_sentiment → GET."""

from unittest.mock import MagicMock

import mongomock
from flask import Flask

from analysis_worker import make_handler
from app.routes.auth_routes import register_auth_routes
from app.routes.journal_routes import register_journal_routes
from app.services.journal_service import JournalService
from app.services.user_service import UserService
from app.utils.event_consumer import EventConsumer
from app.utils.event_publisher import EventPublisher
from app.utils.events import JOURNAL_CREATED
from app.utils.rate_limiter import RateLimiter
from tests.fakes import FakeBroker, FakeConnection


def test_create_to_sentiment_full_pipeline():
    broker = FakeBroker()
    mongo = mongomock.MongoClient()['joy']

    pub_conn = FakeConnection(broker)
    cons_conn = FakeConnection(broker)
    publisher = EventPublisher(url='amqp://test/', connection_factory=lambda: pub_conn)

    user_service = UserService(collection=mongo['users'])
    journal_service = JournalService(collection=mongo['journals'], publisher=publisher)

    app = Flask(__name__)
    app.config['TESTING'] = True
    permissive = RateLimiter(max_attempts=1000, window_seconds=60)
    register_auth_routes(app, user_service=user_service, login_limiter=permissive)
    register_journal_routes(app, service=journal_service)

    consumer = EventConsumer(
        queue_name='journal-analysis',
        routing_keys=[JOURNAL_CREATED],
        url='amqp://test/',
        connection_factory=lambda: cons_conn,
    )
    consumer._setup()  # bind queue before any publish

    analysis = MagicMock()
    analysis.analyze.return_value = {'label': 'positive', 'score': 0.95}
    handler = make_handler(analysis, journal_service)

    with app.test_client() as c:
        c.post('/auth/register', json={'email': 'a@example.com', 'password': 'secret123'})
        token = c.post('/auth/login', json={'email': 'a@example.com', 'password': 'secret123'}).get_json()['token']
        headers = {'Authorization': f'Bearer {token}'}

        created = c.post('/api/journals', json={'title': 'X', 'content': 'Good day'}, headers=headers).get_json()

        # Before the worker runs, sentiment endpoint reports pending
        pending = c.get(f'/api/journals/{created["id"]}/sentiment', headers=headers)
        assert pending.status_code == 202
        assert pending.headers.get('Retry-After') == '2'

        # Drive the worker: consumes the message that POST published
        consumer.consume(handler)

        # Worker must have called analyze with the journal content
        analysis.analyze.assert_called_once_with('Good day')

        # Sentiment endpoint now returns 200 with the analyzed result
        ready = c.get(f'/api/journals/{created["id"]}/sentiment', headers=headers)
        assert ready.status_code == 200
        body = ready.get_json()
        assert body['label'] == 'positive'
        assert body['score'] == 0.95
        assert 'analyzed_at' in body


def test_pipeline_with_empty_content_does_not_set_sentiment():
    """Empty-content entries should remain pending forever."""
    broker = FakeBroker()
    mongo = mongomock.MongoClient()['joy']

    pub_conn = FakeConnection(broker)
    cons_conn = FakeConnection(broker)
    publisher = EventPublisher(url='amqp://test/', connection_factory=lambda: pub_conn)

    user_service = UserService(collection=mongo['users'])
    journal_service = JournalService(collection=mongo['journals'], publisher=publisher)

    app = Flask(__name__)
    app.config['TESTING'] = True
    permissive = RateLimiter(max_attempts=1000, window_seconds=60)
    register_auth_routes(app, user_service=user_service, login_limiter=permissive)
    register_journal_routes(app, service=journal_service)

    consumer = EventConsumer(
        queue_name='journal-analysis',
        routing_keys=[JOURNAL_CREATED],
        url='amqp://test/',
        connection_factory=lambda: cons_conn,
    )
    consumer._setup()

    analysis = MagicMock()
    analysis.analyze.return_value = None  # empty content path
    handler = make_handler(analysis, journal_service)

    with app.test_client() as c:
        c.post('/auth/register', json={'email': 'a@example.com', 'password': 'secret123'})
        token = c.post('/auth/login', json={'email': 'a@example.com', 'password': 'secret123'}).get_json()['token']
        headers = {'Authorization': f'Bearer {token}'}

        created = c.post('/api/journals', json={'title': 'X', 'content': ''}, headers=headers).get_json()
        consumer.consume(handler)

        res = c.get(f'/api/journals/{created["id"]}/sentiment', headers=headers)
        assert res.status_code == 202  # still pending
