"""Worker process: mirrors journal events from RabbitMQ into ClickHouse."""
import logging
from dotenv import load_dotenv

from app.utils.event_consumer import EventConsumer
from app.utils.events import JOURNAL_ANALYZED, JOURNAL_CREATED, JOURNAL_DELETED, JOURNAL_UPDATED
from app.utils.retry import with_retry
from app.services.analytics_service import AnalyticsService

logger = logging.getLogger('joy.analytics_sink')


def make_handler(analytics_service: AnalyticsService):
    def handle(routing_key: str, payload: dict) -> None:
        if not isinstance(payload, dict) or not payload.get('id') or not payload.get('user_id'):
            logger.warning('skipping malformed payload for %s', routing_key)
            return
        with_retry(
            lambda: analytics_service.record_event(routing_key, payload),
            f'record {routing_key} journal_id={payload["id"]}',
        )
        logger.info('recorded %s journal_id=%s', routing_key, payload['id'])
    return handle


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )
    analytics = AnalyticsService()
    with_retry(analytics.ensure_schema, 'ensure schema')

    consumer = EventConsumer(
        queue_name='journal-analytics-sink',
        routing_keys=[JOURNAL_CREATED, JOURNAL_UPDATED, JOURNAL_DELETED, JOURNAL_ANALYZED],
    )
    handler = make_handler(analytics)
    logger.info('Analytics sink starting...')
    try:
        consumer.consume(handler)
    except KeyboardInterrupt:
        logger.info('Analytics sink stopping')
    finally:
        consumer.close()


if __name__ == '__main__':
    main()
