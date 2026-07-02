import json
import logging
import os
import time
import pika
from app.utils.events import EXCHANGE_NAME, EXCHANGE_TYPE

logger = logging.getLogger(__name__)

RECONNECT_MAX_DELAY_SECONDS = 30


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
        # Default matches the compose broker's host-published port (5673)
        self.url = url or os.getenv('RABBITMQ_URL', 'amqp://joy:joy@localhost:5673/')
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

    def declare(self) -> None:
        """Declare and bind the durable queue without consuming.

        Lets a worker ensure events start buffering (e.g. before a slow
        startup task like a backfill) ahead of its consume() loop.
        """
        self._setup()

    def consume(self, handler) -> None:
        """Blocks. Invokes handler(routing_key, payload) for each message.

        Reconnects with backoff when the broker drops the connection
        (restart, network blip); the durable queue preserves messages
        across the gap. KeyboardInterrupt still propagates.
        """
        delay = 1
        while True:
            try:
                self._setup()
                self._channel.basic_consume(
                    queue=self.queue_name,
                    on_message_callback=lambda ch, m, p, b: self._on_message(handler, ch, m, p, b),
                )
                delay = 1  # connected: reset the backoff
                self._channel.start_consuming()
                return  # stopped cleanly (e.g. stop_consuming)
            except pika.exceptions.AMQPError:
                logger.warning('Broker connection lost; reconnecting in %ds', delay, exc_info=True)
                self.close()
                time.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY_SECONDS)

    def close(self) -> None:
        """Never raises: closing a half-dead connection can itself throw,
        and the reconnect loop relies on close() being safe."""
        try:
            if self._connection and self._connection.is_open:
                self._connection.close()
        except Exception:
            logger.debug('error closing dead connection', exc_info=True)
        self._connection = None
        self._channel = None
