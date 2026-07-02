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

    def publish(self, routing_key: str, payload: dict) -> None:
        self._ensure_channel()
        self._local.channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=routing_key,
            body=json.dumps(payload).encode('utf-8'),
            properties=pika.BasicProperties(
                content_type='application/json',
                delivery_mode=2,
            ),
        )

    def close(self) -> None:
        connection = getattr(self._local, 'connection', None)
        if connection and connection.is_open:
            connection.close()
        self._local.connection = None
        self._local.channel = None
