import json
from unittest.mock import MagicMock
from app.utils.event_consumer import EventConsumer
from app.utils.events import EXCHANGE_NAME


def _make_consumer_with_mock(routing_keys=None):
    connection = MagicMock()
    channel = MagicMock()
    connection.is_closed = False
    connection.is_open = True
    connection.channel.return_value = channel
    consumer = EventConsumer(
        queue_name='test-queue',
        routing_keys=routing_keys or ['journal.*'],
        url='amqp://test/',
        connection_factory=lambda: connection,
    )
    return consumer, connection, channel


def _make_method(routing_key='journal.created', delivery_tag=1):
    method = MagicMock()
    method.routing_key = routing_key
    method.delivery_tag = delivery_tag
    return method


def test_setup_declares_exchange_queue_and_bindings():
    consumer, _, channel = _make_consumer_with_mock(routing_keys=['journal.*', 'habit.*'])
    consumer._setup()
    channel.exchange_declare.assert_called_once()
    channel.queue_declare.assert_called_once_with(queue='test-queue', durable=True)
    bind_calls = channel.queue_bind.call_args_list
    assert len(bind_calls) == 2
    bound_keys = {c.kwargs['routing_key'] for c in bind_calls}
    assert bound_keys == {'journal.*', 'habit.*'}
    for c in bind_calls:
        assert c.kwargs['queue'] == 'test-queue'
        assert c.kwargs['exchange'] == EXCHANGE_NAME


def test_on_message_invokes_handler_and_acks():
    consumer, _, channel = _make_consumer_with_mock()
    handler = MagicMock()
    method = _make_method('journal.created', delivery_tag=7)
    body = json.dumps({'id': 'abc'}).encode('utf-8')
    consumer._on_message(handler, channel, method, None, body)
    handler.assert_called_once_with('journal.created', {'id': 'abc'})
    channel.basic_ack.assert_called_once_with(delivery_tag=7)
    channel.basic_nack.assert_not_called()


def test_on_message_nacks_without_requeue_on_handler_error():
    consumer, _, channel = _make_consumer_with_mock()
    handler = MagicMock(side_effect=RuntimeError('boom'))
    method = _make_method(delivery_tag=42)
    body = json.dumps({'id': 'abc'}).encode('utf-8')
    consumer._on_message(handler, channel, method, None, body)
    channel.basic_ack.assert_not_called()
    channel.basic_nack.assert_called_once_with(delivery_tag=42, requeue=False)


def test_on_message_nacks_on_invalid_json():
    consumer, _, channel = _make_consumer_with_mock()
    handler = MagicMock()
    method = _make_method(delivery_tag=9)
    consumer._on_message(handler, channel, method, None, b'not-json')
    handler.assert_not_called()
    channel.basic_nack.assert_called_once_with(delivery_tag=9, requeue=False)


def test_close_closes_connection_and_clears_channel():
    consumer, connection, _ = _make_consumer_with_mock()
    consumer._setup()
    consumer.close()
    connection.close.assert_called_once()
    assert consumer._connection is None
    assert consumer._channel is None
