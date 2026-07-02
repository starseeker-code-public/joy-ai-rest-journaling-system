"""Worker process: consumes journal.created events and runs sentiment analysis."""
import logging
from dotenv import load_dotenv

from app.utils.event_consumer import EventConsumer
from app.utils.logging_config import configure_logging
from app.utils.event_publisher import EventPublisher
from app.utils.events import JOURNAL_ANALYZED, JOURNAL_CREATED
from app.services.analysis_service import AnalysisService
from app.services.journal_service import JournalService

logger = logging.getLogger('joy.analysis')

MAX_CONTENT_CHARS = 5000


def make_handler(analysis_service: AnalysisService, journal_service: JournalService, publisher=None):
    def handle(routing_key: str, payload: dict) -> None:
        if not isinstance(payload, dict):
            logger.warning('skipping non-dict payload')
            return
        journal_id = payload.get('id')
        user_id = payload.get('user_id')
        if not journal_id or not user_id:
            logger.warning('skipping payload missing id or user_id')
            return
        content = (payload.get('content') or '')[:MAX_CONTENT_CHARS]
        result = analysis_service.analyze(content)
        if result is None:
            logger.info('sentiment=none journal_id=%s (empty content)', journal_id)
            return
        updated = journal_service.set_sentiment(user_id, journal_id, result)
        logger.info(
            'sentiment=%s score=%.3f journal_id=%s',
            result['label'], result['score'], journal_id,
        )
        if publisher is not None and updated is not None:
            try:
                publisher.publish(JOURNAL_ANALYZED, {
                    'id': journal_id,
                    'user_id': user_id,
                    'date': updated.get('date'),
                    'sentiment': result,
                })
            except Exception:
                logger.exception('Failed to publish %s event', JOURNAL_ANALYZED)
    return handle


def main() -> None:
    load_dotenv()
    configure_logging()
    analysis = AnalysisService()
    journal_service = JournalService()
    publisher = EventPublisher()
    consumer = EventConsumer(
        queue_name='journal-analysis',
        routing_keys=[JOURNAL_CREATED],
    )
    handler = make_handler(analysis, journal_service, publisher=publisher)
    logger.info('Analysis worker starting...')
    try:
        consumer.consume(handler)
    except KeyboardInterrupt:
        logger.info('Analysis worker stopping')
    finally:
        consumer.close()
        publisher.close()


if __name__ == '__main__':
    main()
