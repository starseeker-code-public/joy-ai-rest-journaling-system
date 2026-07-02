"""Worker process: consumes journal.created events and runs sentiment analysis."""
import logging
import time
from dotenv import load_dotenv

from app.utils.event_consumer import EventConsumer
from app.utils.logging_config import configure_logging
from app.utils.tracing import configure_tracing, instrument_pika
from app.utils.event_publisher import EventPublisher
from app.utils.events import JOURNAL_ANALYZED, JOURNAL_CREATED, JOURNAL_TRANSCRIBED
from app.services.ai_ledger import BUDGET_BLOCK, BUDGET_WARN
from app.services.analysis_service import AnalysisService
from app.services.journal_service import JournalService

logger = logging.getLogger('joy.analysis')

MAX_CONTENT_CHARS = 5000


def make_handler(analysis_service: AnalysisService, journal_service: JournalService,
                 publisher=None, ledger=None):
    def handle(routing_key: str, payload: dict) -> None:
        if not isinstance(payload, dict):
            logger.warning('skipping non-dict payload')
            return
        journal_id = payload.get('id')
        user_id = payload.get('user_id')
        if not journal_id or not user_id:
            logger.warning('skipping payload missing id or user_id')
            return
        event_id = payload.get('event_id')
        if ledger is not None:
            status = ledger.budget_status(user_id)
            if status == BUDGET_BLOCK:
                logger.warning('budget exceeded, skipping analysis user_id=%s', user_id)
                # Zero-cost row so the skip is visible in /api/me/usage
                ledger.record(user_id, 'sentiment_blocked', analysis_service.model_name,
                              entry_id=journal_id,
                              dedupe_key=f'blocked:{event_id}' if event_id else None)
                return
            if status == BUDGET_WARN:
                logger.warning('budget nearly exhausted user_id=%s', user_id)
        content = (payload.get('content') or '')[:MAX_CONTENT_CHARS]
        started = time.perf_counter()
        result = analysis_service.analyze(content)
        if ledger is not None and result is not None:
            ledger.record(
                user_id, 'sentiment', analysis_service.model_name,
                entry_id=journal_id,
                duration_s=round(time.perf_counter() - started, 3),
                dedupe_key=f'sentiment:{event_id}' if event_id else None,
            )
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
    configure_tracing('joy-analysis-worker')
    instrument_pika()
    analysis = AnalysisService()
    journal_service = JournalService()
    publisher = EventPublisher()
    consumer = EventConsumer(
        queue_name='journal-analysis',
        # journal.transcribed reruns sentiment over freshly transcribed audio
        routing_keys=[JOURNAL_CREATED, JOURNAL_TRANSCRIBED],
    )
    from app.services.ai_ledger import AILedger
    handler = make_handler(analysis, journal_service, publisher=publisher, ledger=AILedger())
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
