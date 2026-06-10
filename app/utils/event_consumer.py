import json
import logging
import os
import pika
from app.utils.events import EXCHANGE_NAME, EXCHANGE_TYPE

logger = logging.getLogger(__name__)


class EventConsumer:
    """Subscribes to a topic exchange and dispatches messages to a handler.

    The consumer declares a durable queue and binds it to each routing-key
    pattern provided. Messages are acknowledged on successful handler
    return; handler exceptions cause a non-requeueing nack so poison
    messages do not loop.
    """

    def __init__(
        self,
        queue_name: str,
        routing_keys: list[str],
        url: str | None = None,
        connection_factory=None,
    ):
        self.queue_name = queue_name
        self.routing_keys = routing_keys
        self.url = url or os.getenv('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672/')
        self._connection_factory = connection_factory or self._default_connection_factory
        self._connection = None
        self._channel = None

    def _default_connection_factory(self):
        return pika.BlockingConnection(pika.URLParameters(self.url))

    def _setup(self):
        if self._connection is None or self._connection.is_closed:
            self._connection = self._connection_factory()
            self._channel = self._connection.channel()
            self._channel.exchange_declare(
                exchange=EXCHANGE_NAME,
                exchange_type=EXCHANGE_TYPE,
                durable=True,
            )
            self._channel.queue_declare(queue=self.queue_name, durable=True)
            for key in self.routing_keys:
                self._channel.queue_bind(
                    queue=self.queue_name,
                    exchange=EXCHANGE_NAME,
                    routing_key=key,
                )

    def _on_message(self, handler, ch, method, properties, body):
        try:
            payload = json.loads(body)
            handler(method.routing_key, payload)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception:
            logger.exception('Handler failed for %s', method.routing_key)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def consume(self, handler) -> None:
        """Blocks. Invokes handler(routing_key, payload) for each message."""
        self._setup()
        self._channel.basic_consume(
            queue=self.queue_name,
            on_message_callback=lambda ch, m, p, b: self._on_message(handler, ch, m, p, b),
        )
        self._channel.start_consuming()

    def close(self) -> None:
        if self._connection and self._connection.is_open:
            self._connection.close()
        self._connection = None
        self._channel = None
