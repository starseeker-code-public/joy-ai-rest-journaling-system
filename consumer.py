import logging
from dotenv import load_dotenv

load_dotenv()

from app.utils.event_consumer import EventConsumer
from app.utils.logging_config import configure_logging
from app.utils.tracing import configure_tracing, instrument_pika

configure_logging()
configure_tracing('joy-consumer')
instrument_pika()
logger = logging.getLogger('joy.consumer')


def log_event(routing_key: str, payload: dict) -> None:
    logger.info('event=%s payload=%s', routing_key, payload)


def main() -> None:
    consumer = EventConsumer(
        queue_name='journal-logger',
        routing_keys=['journal.*'],
    )
    logger.info('Consumer starting, waiting for events...')
    try:
        consumer.consume(log_event)
    except KeyboardInterrupt:
        logger.info('Consumer stopping')
    finally:
        consumer.close()


if __name__ == '__main__':
    main()
