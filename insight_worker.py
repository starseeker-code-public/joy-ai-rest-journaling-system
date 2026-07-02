"""Worker process: materializes weekly insights.

Two triggers:
- journal events (created/updated/deleted/analyzed) regenerate the insight for
  the week the entry belongs to (payload date, falling back to the current
  week), so edits, deletions, and backdated entries refresh the right week;
- a background scheduler periodically rebuilds the previous completed week for
  every active user, so finished weeks end up materialized even for users with
  no new activity.
"""
import logging
import os
import threading
import time
from datetime import date, timedelta
from dotenv import load_dotenv

from app.utils.event_consumer import EventConsumer
from app.utils.logging_config import configure_logging
from app.utils.tracing import configure_tracing, instrument_pika
from app.utils.events import JOURNAL_ANALYZED, JOURNAL_CREATED, JOURNAL_DELETED, JOURNAL_UPDATED
from app.utils.retry import with_retry
from app.utils.tools import utc_today
from app.services.insight_service import InsightService, week_start_of

logger = logging.getLogger('joy.insight')

DEFAULT_SCHEDULER_INTERVAL = 3600
# The analytics sink consumes the same events on a separate queue; give it a
# moment to land the write in ClickHouse before we aggregate. Any race that
# still slips through self-heals on the next event or scheduler tick.
DEFAULT_REFRESH_DELAY = 2.0
# How many trailing weeks the scheduler rebuilds each tick. Must cover the
# window an event race (or a backdated edit) could leave stale; a handful of
# weeks is cheap and guarantees eventual consistency for recent history.
SCHEDULER_WEEKS = int(os.getenv('INSIGHT_SCHEDULER_WEEKS', '5'))


def _parse_day(value) -> date | None:
    if isinstance(value, str) and len(value) >= 10:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            pass
    return None


def _weeks_of_payload(payload: dict) -> set[date]:
    """Weeks to refresh: the entry's week plus, for cross-week edits, the week
    it moved from. Falls back to the current week when no date is usable."""
    weeks = set()
    for key in ('date', 'previous_date'):
        day = _parse_day(payload.get(key))
        if day is not None:
            weeks.add(week_start_of(day))
    return weeks or {week_start_of(utc_today())}


def make_handler(insight_service: InsightService, delay_seconds: float | None = None):
    if delay_seconds is None:
        delay_seconds = float(os.getenv('INSIGHT_REFRESH_DELAY', str(DEFAULT_REFRESH_DELAY)))

    def handle(routing_key: str, payload: dict) -> None:
        if not isinstance(payload, dict) or not payload.get('user_id'):
            logger.warning('skipping malformed payload for %s', routing_key)
            return
        user_id = payload['user_id']
        weeks = _weeks_of_payload(payload)
        if delay_seconds:
            time.sleep(delay_seconds)
        for week in sorted(weeks):
            with_retry(
                lambda w=week: insight_service.generate_for_week(user_id, w),
                f'insight for user_id={user_id}',
            )
            logger.info('refreshed insight for user_id=%s week_of=%s', user_id, week.isoformat())
    return handle


def run_scheduler(insight_service: InsightService, interval_seconds: int, stop_event=None,
                  weeks: int = SCHEDULER_WEEKS):
    """Rebuild the trailing `weeks` weeks for all active users, forever.

    Covering a window (not just the previous week) means any staleness left by
    an event race, an analytics-sink lag, or a backdated edit is eventually
    repaired — oldest week first so the current week reflects the latest data.
    """
    stop_event = stop_event or threading.Event()
    while not stop_event.is_set():
        current_week = week_start_of(utc_today())
        for n in range(weeks - 1, -1, -1):
            week = current_week - timedelta(days=7 * n)
            try:
                count = insight_service.generate_for_active_users(week)
                logger.info('scheduler: generated %d insights for week of %s',
                            count, week.isoformat())
            except Exception:
                logger.exception('scheduler run failed for week of %s', week.isoformat())
        stop_event.wait(interval_seconds)


def main() -> None:
    load_dotenv()
    configure_logging()
    configure_tracing('joy-insight-worker')
    instrument_pika()
    insights = InsightService()
    interval = int(os.getenv('INSIGHT_SCHEDULER_INTERVAL', str(DEFAULT_SCHEDULER_INTERVAL)))
    # The scheduler gets its own service (and thus its own ClickHouse session):
    # clickhouse-connect sessions are not safe for concurrent queries across threads.
    threading.Thread(
        target=run_scheduler, args=(InsightService(), interval), daemon=True,
    ).start()

    consumer = EventConsumer(
        queue_name='journal-insights',
        routing_keys=[JOURNAL_CREATED, JOURNAL_UPDATED, JOURNAL_DELETED, JOURNAL_ANALYZED],
    )
    handler = make_handler(insights)
    logger.info('Insight worker starting...')
    try:
        consumer.consume(handler)
    except KeyboardInterrupt:
        logger.info('Insight worker stopping')
    finally:
        consumer.close()


if __name__ == '__main__':
    main()
