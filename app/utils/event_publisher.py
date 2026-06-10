import json
import os
import pika

EXCHANGE_NAME = 'joy.events'
EXCHANGE_TYPE = 'topic'


class EventPublisher:
    """Thin pika wrapper that publishes JSON messages to a topic exchange.

    Connection and channel are opened lazily on first publish and reused
    across calls. Caller closes via `close()` when the publisher is no
    longer needed (e.g. application shutdown).
    """

    def __init__(self, url: str | None = None, connection_factory=None):
        self.url = url or os.getenv('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672/')
        self._connection_factory = connection_factory or self._default_connection_factory
        self._connection = None
        self._channel = None

    def _default_connection_factory(self):
        return pika.BlockingConnection(pika.URLParameters(self.url))

    def _ensure_channel(self):
        if self._connection is None or self._connection.is_closed:
            self._connection = self._connection_factory()
            self._channel = self._connection.channel()
            self._channel.exchange_declare(
                exchange=EXCHANGE_NAME,
                exchange_type=EXCHANGE_TYPE,
                durable=True,
            )

    def publish(self, routing_key: str, payload: dict) -> None:
        self._ensure_channel()
        self._channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=routing_key,
            body=json.dumps(payload).encode('utf-8'),
            properties=pika.BasicProperties(
                content_type='application/json',
                delivery_mode=2,
            ),
        )

    def close(self) -> None:
        if self._connection and self._connection.is_open:
            self._connection.close()
        self._connection = None
        self._channel = None
