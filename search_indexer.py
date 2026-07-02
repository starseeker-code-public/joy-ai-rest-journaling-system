"""Worker process: keeps the OpenSearch journal index in sync with the event bus.

On startup it backfills the index from MongoDB (idempotent — documents are
indexed by id), so entries created before the indexer first ran, or while it
was down, become searchable. After that it consumes journal.* events.
"""
import logging
import time
from dotenv import load_dotenv

from app.utils.event_consumer import EventConsumer
from app.utils.events import JOURNAL_CREATED, JOURNAL_DELETED, JOURNAL_UPDATED
from app.services.search_service import SearchService

logger = logging.getLogger('joy.search_indexer')

MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 1


def _with_retry(operation, description: str):
    """Retry transient search-backend failures with exponential backoff.

    Re-raises after the last attempt so the consumer nacks the message
    instead of acking a write that never happened.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return operation()
        except Exception:
            if attempt == MAX_ATTEMPTS:
                logger.exception('%s failed after %d attempts', description, MAX_ATTEMPTS)
                raise
            delay = BACKOFF_BASE_SECONDS * 2 ** (attempt - 1)
            logger.warning('%s failed (attempt %d/%d), retrying in %ds',
                           description, attempt, MAX_ATTEMPTS, delay)
            time.sleep(delay)


def make_handler(search_service: SearchService):
    def handle(routing_key: str, payload: dict) -> None:
        if not isinstance(payload, dict) or not payload.get('id'):
            logger.warning('skipping malformed payload for %s', routing_key)
            return
        if routing_key == JOURNAL_DELETED:
            _with_retry(lambda: search_service.delete_entry(payload['id']),
                        f'delete journal_id={payload["id"]}')
            logger.info('deleted journal_id=%s from index', payload['id'])
        else:
            _with_retry(lambda: search_service.index_entry(payload),
                        f'index journal_id={payload["id"]}')
            logger.info('indexed journal_id=%s (%s)', payload['id'], routing_key)
    return handle


def backfill(search_service: SearchService, collection) -> int:
    """Index every journal in Mongo. Idempotent; returns the count indexed."""
    count = 0
    for entry in collection.find({}):
        search_service.index_entry(entry)
        count += 1
    return count


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )
    from app.db import get_db

    search = SearchService()
    consumer = EventConsumer(
        queue_name='journal-search-indexer',
        routing_keys=[JOURNAL_CREATED, JOURNAL_UPDATED, JOURNAL_DELETED],
    )
    # Bind the queue first so events published during the backfill buffer
    # in RabbitMQ instead of being dropped by the exchange.
    consumer.declare()

    _with_retry(search.ensure_index, 'ensure index')
    indexed = _with_retry(lambda: backfill(search, get_db()['journals']), 'backfill')
    logger.info('Backfill complete: %d entries indexed', indexed)

    handler = make_handler(search)
    logger.info('Search indexer starting...')
    try:
        consumer.consume(handler)
    except KeyboardInterrupt:
        logger.info('Search indexer stopping')
    finally:
        consumer.close()


if __name__ == '__main__':
    main()
