"""Worker process: consumes journal.created events and runs sentiment analysis."""
import logging
from dotenv import load_dotenv

from app.utils.event_consumer import EventConsumer
from app.utils.events import JOURNAL_CREATED
from app.services.analysis_service import AnalysisService
from app.services.journal_service import JournalService

logger = logging.getLogger('joy.analysis')


def make_handler(analysis_service: AnalysisService, journal_service: JournalService):
    def handle(routing_key: str, payload: dict) -> None:
        content = payload.get('content') or ''
        journal_id = payload.get('id')
        user_id = payload.get('user_id')
        result = analysis_service.analyze(content)
        if result is None:
            logger.info('sentiment=none journal_id=%s (empty content)', journal_id)
            return
        journal_service.set_sentiment(user_id, journal_id, result)
        logger.info(
            'sentiment=%s score=%.3f journal_id=%s',
            result['label'], result['score'], journal_id,
        )
    return handle


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )
    analysis = AnalysisService()
    journal_service = JournalService()
    consumer = EventConsumer(
        queue_name='journal-analysis',
        routing_keys=[JOURNAL_CREATED],
    )
    handler = make_handler(analysis, journal_service)
    logger.info('Analysis worker starting...')
    try:
        consumer.consume(handler)
    except KeyboardInterrupt:
        logger.info('Analysis worker stopping')
    finally:
        consumer.close()


if __name__ == '__main__':
    main()
