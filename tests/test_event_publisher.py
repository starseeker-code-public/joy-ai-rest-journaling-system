import json
from unittest.mock import MagicMock
from app.utils.event_publisher import EventPublisher
from app.utils.events import EXCHANGE_NAME, EXCHANGE_TYPE


def _make_publisher_with_mock():
    connection = MagicMock()
    channel = MagicMock()
    connection.is_closed = False
    connection.is_open = True
    channel.is_closed = False
    connection.channel.return_value = channel
    pub = EventPublisher(url='amqp://test/', connection_factory=lambda: connection)
    return pub, connection, channel


def test_publish_declares_exchange_once_then_publishes():
    pub, _, channel = _make_publisher_with_mock()
    pub.publish('journal.created', {'id': 'abc'})
    channel.exchange_declare.assert_called_once_with(
        exchange=EXCHANGE_NAME,
        exchange_type=EXCHANGE_TYPE,
        durable=True,
    )
    channel.basic_publish.assert_called_once()


def test_publish_sends_json_payload_with_routing_key():
    pub, _, channel = _make_publisher_with_mock()
    pub.publish('journal.created', {'id': 'abc', 'title': 'Hello'})
    call = channel.basic_publish.call_args
    assert call.kwargs['exchange'] == EXCHANGE_NAME
    assert call.kwargs['routing_key'] == 'journal.created'
    assert json.loads(call.kwargs['body']) == {'id': 'abc', 'title': 'Hello'}


def test_publish_uses_persistent_delivery_mode():
    pub, _, channel = _make_publisher_with_mock()
    pub.publish('journal.created', {'id': 'abc'})
    props = channel.basic_publish.call_args.kwargs['properties']
    assert props.delivery_mode == 2
    assert props.content_type == 'application/json'


def test_repeated_publish_reuses_channel():
    pub, connection, channel = _make_publisher_with_mock()
    pub.publish('journal.created', {'id': '1'})
    pub.publish('journal.updated', {'id': '1'})
    assert connection.channel.call_count == 1
    assert channel.exchange_declare.call_count == 1
    assert channel.basic_publish.call_count == 2


def test_close_closes_connection_and_clears_channel():
    pub, connection, _ = _make_publisher_with_mock()
    pub.publish('journal.created', {'id': '1'})
    pub.close()
    connection.close.assert_called_once()
    assert getattr(pub._local, 'connection', None) is None
    assert getattr(pub._local, 'channel', None) is None


def test_reopens_after_close():
    pub, connection, _ = _make_publisher_with_mock()
    pub.publish('journal.created', {'id': '1'})
    pub.close()

    new_connection = MagicMock()
    new_channel = MagicMock()
    new_connection.is_closed = False
    new_connection.is_open = True
    new_channel.is_closed = False
    new_connection.channel.return_value = new_channel
    pub._connection_factory = lambda: new_connection

    pub.publish('journal.created', {'id': '2'})
    new_channel.basic_publish.assert_called_once()


def test_publisher_is_thread_safe():
    """Each thread gets its own connection; publishes don't interleave channels."""
    import threading
    from collections import defaultdict
    connections_seen: dict[int, object] = {}
    factory_lock = threading.Lock()

    def make_conn():
        connection = MagicMock()
        channel = MagicMock()
        connection.is_closed = False
        connection.is_open = True
        channel.is_closed = False
        connection.channel.return_value = channel
        with factory_lock:
            connections_seen[threading.get_ident()] = connection
        return connection

    pub = EventPublisher(url='amqp://test/', connection_factory=make_conn)
    barrier = threading.Barrier(4)

    def worker():
        barrier.wait()
        pub.publish('journal.created', {'thread': threading.get_ident()})

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()

    # Each thread observed its own connection (4 distinct connections)
    assert len(connections_seen) == 4
    assert len(set(id(c) for c in connections_seen.values())) == 4
