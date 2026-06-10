"""End-to-end test: EventPublisher → in-memory broker → EventConsumer."""
from collections import defaultdict, deque
from types import SimpleNamespace
from app.utils.event_publisher import EventPublisher
from app.utils.event_consumer import EventConsumer


def _topic_matches(pattern: str, routing_key: str) -> bool:
    """Minimal topic match: '*' matches one word, no '#' support."""
    p, k = pattern.split('.'), routing_key.split('.')
    if len(p) != len(k):
        return False
    return all(seg == '*' or seg == kseg for seg, kseg in zip(p, k))


class FakeBroker:
    def __init__(self):
        self.exchanges: set[str] = set()
        self.queues: dict[str, deque] = defaultdict(deque)
        self.bindings: list[tuple[str, str, str]] = []  # (queue, exchange, pattern)

    def declare_exchange(self, name: str) -> None:
        self.exchanges.add(name)

    def declare_queue(self, name: str) -> None:
        _ = self.queues[name]  # touch to create

    def bind(self, queue: str, exchange: str, routing_key: str) -> None:
        self.bindings.append((queue, exchange, routing_key))

    def publish(self, exchange: str, routing_key: str, body: bytes) -> None:
        for queue, ex, pattern in self.bindings:
            if ex == exchange and _topic_matches(pattern, routing_key):
                self.queues[queue].append((routing_key, body))


class FakeChannel:
    def __init__(self, broker: FakeBroker):
        self.broker = broker
        self.is_closed = False
        self._consumer_queue: str | None = None
        self._consumer_callback = None
        self.acked: list[int] = []
        self.nacked: list[int] = []

    def exchange_declare(self, exchange, exchange_type, durable=False):
        self.broker.declare_exchange(exchange)

    def queue_declare(self, queue, durable=False):
        self.broker.declare_queue(queue)

    def queue_bind(self, queue, exchange, routing_key):
        self.broker.bind(queue, exchange, routing_key)

    def basic_publish(self, exchange, routing_key, body, properties=None):
        self.broker.publish(exchange, routing_key, body)

    def basic_consume(self, queue, on_message_callback):
        self._consumer_queue = queue
        self._consumer_callback = on_message_callback

    def basic_ack(self, delivery_tag):
        self.acked.append(delivery_tag)

    def basic_nack(self, delivery_tag, requeue=False):
        self.nacked.append(delivery_tag)

    def start_consuming(self):
        queue = self.broker.queues[self._consumer_queue]
        tag = 0
        while queue:
            routing_key, body = queue.popleft()
            tag += 1
            method = SimpleNamespace(routing_key=routing_key, delivery_tag=tag)
            self._consumer_callback(self, method, None, body)


class FakeConnection:
    def __init__(self, broker: FakeBroker):
        self.broker = broker
        self.is_open = True
        self.is_closed = False
        self._channel: FakeChannel | None = None

    def channel(self):
        if self._channel is None:
            self._channel = FakeChannel(self.broker)
        return self._channel

    def close(self):
        self.is_open = False
        self.is_closed = True


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
