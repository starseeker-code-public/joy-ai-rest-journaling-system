import json
import os
import threading
import pika
from app.utils.events import EXCHANGE_NAME, EXCHANGE_TYPE


class EventPublisher:
    """Thin pika wrapper that publishes JSON messages to a topic exchange.

    Connection and channel are thread-local so the publisher can be shared
    safely across threads (e.g., a threaded WSGI worker). Each thread
    opens its own connection on first publish and reuses it. `close()`
    closes the connection bound to the calling thread only; other threads'
    connections will be cleaned up on process exit.
    """

    def __init__(self, url: str | None = None, connection_factory=None):
        # Default matches the compose broker's host-published port (5673)
        self.url = url or os.getenv('RABBITMQ_URL', 'amqp://joy:joy@localhost:5673/')
        self._connection_factory = connection_factory or self._default_connection_factory
        self._local = threading.local()

    def _default_connection_factory(self):
        return pika.BlockingConnection(pika.URLParameters(self.url))

    def _ensure_channel(self):
        connection = getattr(self._local, 'connection', None)
        channel = getattr(self._local, 'channel', None)
        if (
            connection is None
            or connection.is_closed
            or channel is None
            or channel.is_closed
        ):
            connection = self._connection_factory()
            channel = connection.channel()
            channel.exchange_declare(
                exchange=EXCHANGE_NAME,
                exchange_type=EXCHANGE_TYPE,
                durable=True,
            )
            self._local.connection = connection
            self._local.channel = channel

    def _reset(self) -> None:
        connection = getattr(self._local, 'connection', None)
        try:
            if connection and connection.is_open:
                connection.close()
        except Exception:
            pass  # already broken; dropping the reference is all that matters
        self._local.connection = None
        self._local.channel = None

    def publish(self, routing_key: str, payload: dict) -> None:
        # A stable per-event id lets at-least-once consumers deduplicate
        # side effects (e.g. the AI cost ledger) across redeliveries.
        if isinstance(payload, dict) and 'event_id' not in payload:
            from uuid import uuid4
            payload = {**payload, 'event_id': str(uuid4())}
        body = json.dumps(payload).encode('utf-8')
        properties = pika.BasicProperties(
            content_type='application/json',
            delivery_mode=2,
        )
        try:
            self._ensure_channel()
            self._local.channel.basic_publish(
                exchange=EXCHANGE_NAME,
                routing_key=routing_key,
                body=body,
                properties=properties,
            )
        except pika.exceptions.AMQPError:
            # A long-idle connection may be dead without is_closed knowing it
            # (broker reset, heartbeat timeout). Reconnect once and retry.
            self._reset()
            self._ensure_channel()
            self._local.channel.basic_publish(
                exchange=EXCHANGE_NAME,
                routing_key=routing_key,
                body=body,
                properties=properties,
            )

    def close(self) -> None:
        connection = getattr(self._local, 'connection', None)
        if connection and connection.is_open:
            connection.close()
        self._local.connection = None
        self._local.channel = None
