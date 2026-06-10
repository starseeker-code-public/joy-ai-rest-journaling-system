"""Worker process: consumes journal.created events and runs sentiment analysis."""
import logging
from dotenv import load_dotenv

from app.utils.event_consumer import EventConsumer
from app.utils.events import JOURNAL_CREATED
from app.services.analysis_service import AnalysisService

logger = logging.getLogger('joy.analysis')


def make_handler(analysis_service: AnalysisService):
    def handle(routing_key: str, payload: dict) -> None:
        content = payload.get('content') or ''
        journal_id = payload.get('id')
        result = analysis_service.analyze(content)
        if result is None:
            logger.info('sentiment=none journal_id=%s (empty content)', journal_id)
            return
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
    consumer = EventConsumer(
        queue_name='journal-analysis',
        routing_keys=[JOURNAL_CREATED],
    )
    handler = make_handler(analysis)
    logger.info('Analysis worker starting...')
    try:
        consumer.consume(handler)
    except KeyboardInterrupt:
        logger.info('Analysis worker stopping')
    finally:
        consumer.close()


if __name__ == '__main__':
    main()
