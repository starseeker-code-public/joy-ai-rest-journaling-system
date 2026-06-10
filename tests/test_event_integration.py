"""End-to-end test: EventPublisher → in-memory broker → EventConsumer."""

from app.utils.event_consumer import EventConsumer
from app.utils.event_publisher import EventPublisher
from tests.fakes import FakeBroker, FakeConnection


def _wire(broker: FakeBroker):
    """Returns (publisher, consumer) sharing the same fake broker."""
    pub_conn = FakeConnection(broker)
    cons_conn = FakeConnection(broker)
    publisher = EventPublisher(url='amqp://test/', connection_factory=lambda: pub_conn)
    consumer = EventConsumer(
        queue_name='test-queue',
        routing_keys=['journal.*'],
        url='amqp://test/',
        connection_factory=lambda: cons_conn,
    )
    return publisher, consumer, pub_conn, cons_conn


# --- tests ---


def test_published_event_reaches_consumer_handler():
    broker = FakeBroker()
    publisher, consumer, _, cons_conn = _wire(broker)
    received: list[tuple[str, dict]] = []

    consumer._setup()  # bind queue before publish
    publisher.publish('journal.created', {'id': 'abc', 'title': 'Hello'})
    consumer.consume(lambda rk, payload: received.append((rk, payload)))

    assert received == [('journal.created', {'id': 'abc', 'title': 'Hello'})]
    assert cons_conn.channel().acked == [1]
    assert cons_conn.channel().nacked == []


def test_wildcard_binding_matches_multiple_routing_keys():
    broker = FakeBroker()
    publisher, consumer, _, _ = _wire(broker)
    received: list[str] = []

    consumer._setup()
    publisher.publish('journal.created', {'id': '1'})
    publisher.publish('journal.updated', {'id': '1'})
    publisher.publish('journal.deleted', {'id': '1'})
    consumer.consume(lambda rk, _payload: received.append(rk))

    assert received == ['journal.created', 'journal.updated', 'journal.deleted']


def test_non_matching_routing_key_is_dropped():
    broker = FakeBroker()
    publisher, consumer, _, _ = _wire(broker)
    received: list[str] = []

    consumer._setup()
    publisher.publish('journal.created', {'id': 'x'})
    publisher.publish('habit.created', {'id': 'y'})  # not bound
    consumer.consume(lambda rk, _payload: received.append(rk))

    assert received == ['journal.created']


def test_publish_before_bind_is_lost():
    """Real topic exchanges drop messages with no matching binding at publish time."""
    broker = FakeBroker()
    publisher, consumer, _, _ = _wire(broker)
    received: list[str] = []

    publisher.publish('journal.created', {'id': 'lost'})  # no queue bound yet
    consumer._setup()
    consumer.consume(lambda rk, _payload: received.append(rk))

    assert received == []


def test_handler_error_nacks_message_without_requeue():
    broker = FakeBroker()
    publisher, consumer, _, cons_conn = _wire(broker)

    consumer._setup()
    publisher.publish('journal.created', {'id': 'x'})

    def failing_handler(rk, payload):
        raise RuntimeError('boom')

    consumer.consume(failing_handler)

    assert cons_conn.channel().acked == []
    assert cons_conn.channel().nacked == [1]
